"""Run agent subprocesses with output capture and timeout enforcement.

This module handles the mechanics of executing agent commands — spawning
processes, enforcing timeouts, capturing output, and writing log files.
The engine module uses these functions but owns the orchestration: state
updates, event emission, and loop control.

Two execution modes are supported:

- **Streaming** (``_run_agent_streaming``) — line-by-line stdout reading
  via ``Popen``, used for agents that emit JSON streams (e.g. Claude Code).
- **Blocking** (``_run_agent_blocking``) — ``subprocess.run`` with optional
  output capture, used for all other agents.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from ralphify._events import OutputStream
from ralphify._output import (
    IS_WINDOWS,
    SESSION_KWARGS,
    SUBPROCESS_TEXT_KWARGS,
    ProcessResult,
    collect_output,
    warn,
)
from ralphify.adapters import CLIAdapter, select_adapter

_log = logging.getLogger(__name__)

_counter_write_failure_logged = False
"""Module-level latch so the wind-down counter write failure logs only once."""

# ── Callback type aliases ──────────────────────────────────────────────
# Used across the streaming and blocking execution paths for callbacks
# that observe live agent output.

ActivityCallback = Callable[[dict[str, Any]], None]
"""Receives parsed JSON activity dicts from the agent's stream."""

OutputLineCallback = Callable[[str, OutputStream], None]
"""Receives raw output lines with their stream name ("stdout"/"stderr")."""

ToolUseCallback = Callable[[str, int], None]
"""Invoked by both the streaming path (as lines arrive) and the blocking
path (after the subprocess exits, during post-hoc counting).  Best-effort:
exceptions are swallowed so a buggy subscriber cannot kill the agent loop.
"""


def _call_safely(callback: Callable[..., Any] | None, *args: Any) -> None:
    """Invoke an observer *callback* with *args*, swallowing any exception.

    Used for best-effort observer callbacks during output draining: a
    raising callback must never stop the drain loop or leave the reader
    thread hung.
    """
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:
        pass


# Typed constants for the OutputStream literal so the type checker enforces
# that only "stdout" / "stderr" ever reach ``on_output_line``.
_STDOUT: OutputStream = "stdout"
_STDERR: OutputStream = "stderr"

# JSON stream event types and fields for result extraction.
_RESULT_EVENT_TYPE = "result"
_RESULT_FIELD = "result"

# Log file naming — timestamp format and iteration zero-padding width.
_LOG_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
_LOG_ITERATION_PAD_WIDTH = 3

# Seconds to wait for graceful shutdown after SIGTERM before escalating to SIGKILL.
_SIGTERM_GRACE_PERIOD = 3

# Seconds to wait for reader threads to drain during cleanup.
# Generous bound: after parent-side pipe close, EOF propagates within
# milliseconds — 5s is headroom for slow kernels / loaded CI boxes.
_THREAD_JOIN_TIMEOUT = 5.0

# Seconds to wait for the agent process to exit after a kill signal.
_PROCESS_WAIT_TIMEOUT = 5.0

# Tempdir prefix for per-iteration wind-down hook config.  Surfaces in
# ``$TMPDIR`` listings so users can spot stale dirs after a crash.
_HOOK_TEMPDIR_PREFIX = "ralphify-"

# Counter filename when ``log_dir`` is unset and the file lives inside
# the per-iteration tempdir.  When ``log_dir`` is set, the counter lives
# at ``<log_dir>/<iter>.turncount``.
_COUNTER_FILENAME = "turncount"
_COUNTER_LOG_SUFFIX = ".turncount"
_COUNTER_PAD_WIDTH = _LOG_ITERATION_PAD_WIDTH


def _extract_result_text_from_lines(lines: list[str] | None) -> str | None:
    """Return the last string payload from any JSON ``result`` event in *lines*."""
    if lines is None:
        return None

    result_text = None
    for line in lines:
        extracted = _extract_result_text_from_line(line)
        if extracted is not None:
            result_text = extracted
    return result_text


def _extract_result_text_from_line(line: str) -> str | None:
    """Return the string payload from a single JSON ``result`` event line."""
    try:
        parsed = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    if (
        isinstance(parsed, dict)
        and parsed.get("type") == _RESULT_EVENT_TYPE
        and isinstance(parsed.get(_RESULT_FIELD), str)
    ):
        return parsed[_RESULT_FIELD]
    return None


def _try_graceful_group_kill(proc: subprocess.Popen[Any]) -> bool:
    """Attempt to kill the process via its POSIX process group.

    Sends SIGTERM, waits briefly, then escalates to SIGKILL if needed.
    Only acts when the process is a session leader (pgid == pid) to avoid
    accidentally killing the caller's group in tests.

    Returns ``True`` if the group kill succeeded, ``False`` if the caller
    should fall back to ``proc.kill()``.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (OSError, ProcessLookupError):
        return False

    if pgid != proc.pid:
        return False

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return False

    try:
        proc.wait(timeout=_SIGTERM_GRACE_PERIOD)
        return True
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(pgid, signal.SIGKILL)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_process_group(proc: subprocess.Popen[Any]) -> None:
    """Kill the agent process and its entire process group.

    On POSIX, attempts a graceful group kill (SIGTERM → SIGKILL) via
    :func:`_try_graceful_group_kill`.  Falls back to ``proc.kill()``
    on Windows, when the process already exited, or if the group kill fails.

    Short-circuits when ``proc.pid`` is ``None`` or non-positive — these
    are sentinel values used by test mocks.  A non-positive pid would also
    be dangerous to pass to ``os.getpgid`` / ``os.killpg`` (pid 0 means
    the caller's own process group).
    """
    if proc.pid is None or proc.pid <= 0:
        return
    if not IS_WINDOWS and proc.poll() is None:
        if _try_graceful_group_kill(proc):
            return
    proc.kill()


def _ensure_process_dead(proc: subprocess.Popen[Any]) -> None:
    """Kill the agent process if still running, then wait for exit.

    Safe to call multiple times — no-ops when the process has already
    exited.  Used in ``finally`` and exception-handler blocks to
    guarantee the child is reaped before we move on.

    The wait is bounded so that a stuck process (e.g. grandchild holding
    a session) cannot hang the CLI forever.
    """
    if proc.poll() is None:
        _kill_process_group(proc)
    try:
        proc.wait(timeout=_PROCESS_WAIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        warn(f"agent process did not exit within {_PROCESS_WAIT_TIMEOUT}s after kill")


def _close_pipes(proc: subprocess.Popen[Any]) -> None:
    """Close parent-side stdout/stderr pipe file descriptors.

    Forces EOF to propagate to reader threads even when grandchild
    processes have inherited the write end of the pipe.  The pump
    thread's ``readline()`` wakes with ``OSError`` (EBADF), which
    ``_pump_stream`` catches, so the thread exits and ``join()``
    returns promptly.

    Uses ``os.close()`` on the raw fd rather than ``pipe.close()``
    because Python's ``TextIOWrapper`` / ``BufferedReader`` hold an
    internal lock during ``readline()``.  Calling ``pipe.close()``
    from the main thread would block waiting for that lock — exactly
    the hang we're trying to break.  ``os.close()`` bypasses the
    Python lock and directly invalidates the fd at the OS level.

    Safe to call multiple times or on already-closed pipes.
    """
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                os.close(pipe.fileno())
            except Exception:
                pass


def _finalize_pipes(proc: subprocess.Popen[Any]) -> None:
    """Mark parent-side pipe file objects as closed at the Python level.

    Called AFTER :func:`_close_pipes` and :func:`_drain_readers` to set
    the ``closed`` flag on the Python file objects.  This prevents
    "Bad file descriptor" warnings when the garbage collector finalizes
    the objects whose underlying fd was already closed by
    :func:`_close_pipes`.

    Must be called after reader threads have exited — the pipe's
    internal lock is held during ``readline()``, so ``close()`` would
    block on a live thread.
    """
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                pass


def _deliver_prompt(proc: subprocess.Popen[Any], prompt: str) -> None:
    """Write *prompt* to the agent's stdin and close the pipe.

    Silently handles ``BrokenPipeError`` — the agent may exit before
    consuming the full prompt, which is a normal (if uncommon) lifecycle
    event.
    """
    assert proc.stdin is not None
    try:
        proc.stdin.write(prompt)
    except BrokenPipeError:
        pass
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass


@dataclass(slots=True)
class AgentResult(ProcessResult):
    """Result of running the agent subprocess."""

    elapsed: float = 0.0
    log_file: Path | None = None
    result_text: str | None = None
    captured_stdout: str | None = None
    captured_stderr: str | None = None
    # Tool-use events the adapter reported for this iteration; ``0`` when
    # no adapter was active or the adapter's ``counts_what != "tool_use"``.
    tool_use_count: int = 0
    # True when the cap was reached and the agent process was terminated
    # (streaming) or the cap was exceeded post-hoc (blocking path).
    turn_capped: bool = False


@dataclass(slots=True)
class _WindDownContext:
    """Per-iteration tempdir and counter state for soft wind-down hooks.

    Built by :func:`_setup_wind_down` for adapters whose
    ``supports_soft_wind_down`` is True and a ``max_turns`` cap is
    configured.  Carries the env-var overrides the spawned agent needs,
    plus the cleanup hook called from the streaming path's ``finally``.
    """

    tempdir: Path
    counter_path: Path
    env_overrides: dict[str, str]

    def cleanup(self) -> None:
        try:
            self.counter_path.unlink()
        except (FileNotFoundError, OSError):
            pass
        shutil.rmtree(self.tempdir, ignore_errors=True)


@dataclass(frozen=True, slots=True)
class _StreamResult:
    """Accumulated output from reading the agent's JSON stream."""

    stdout_lines: tuple[str, ...] | None
    result_text: str | None
    timed_out: bool
    tool_use_count: int = 0
    turn_capped: bool = False


def _write_log(
    log_dir: Path | None,
    iteration: int,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> Path | None:
    """Write iteration output to a timestamped log file if logging is configured.

    Returns the log file path, or ``None`` when *log_dir* is not set.
    """
    if log_dir is None:
        return None
    timestamp = datetime.now(timezone.utc).strftime(_LOG_TIMESTAMP_FORMAT)
    log_file = log_dir / f"{iteration:0{_LOG_ITERATION_PAD_WIDTH}d}_{timestamp}.log"
    log_file.write_text(collect_output(stdout, stderr), encoding="utf-8")
    return log_file


def _readline_pump(
    stdout: IO[str],
    line_queue: queue.Queue[str | None],
) -> None:
    """Read *stdout* line-by-line and put each line into *line_queue*.

    Sends a ``None`` sentinel on EOF or pipe error so the consumer can
    distinguish "no more data" from "still waiting".  Runs on a daemon
    thread started by :func:`_read_agent_stream`.
    """
    try:
        for line in iter(stdout.readline, ""):
            line_queue.put(line)
    except (ValueError, OSError):
        # Pipe closed concurrently (e.g. after timeout kill) — exit cleanly.
        pass
    finally:
        line_queue.put(None)  # EOF sentinel


def _read_agent_stream(
    stdout: IO[str],
    deadline: float | None,
    on_activity: ActivityCallback | None,
    on_output_line: OutputLineCallback | None = None,
    *,
    capture_stdout: bool = True,
    adapter: CLIAdapter | None = None,
    max_turns: int | None = None,
    on_tool_use: ToolUseCallback | None = None,
) -> _StreamResult:
    """Read the agent's JSON stream line-by-line until EOF or timeout.

    Uses a background reader thread that feeds lines into a
    :class:`queue.Queue`.  The main thread pulls from the queue with a
    bounded wait derived from *deadline*, so the timeout is enforced even
    when the agent produces no output (a silent hang).  This is
    cross-platform — ``select.select`` on pipes only works on POSIX.

    ``SUBPROCESS_TEXT_KWARGS`` sets ``bufsize=1`` (line-buffered), so
    ``readline()`` in the reader thread returns as soon as a newline
    arrives instead of filling an 8 KB readahead buffer.  Combined with
    the queue, peek lines flow one-at-a-time.

    Parses each non-empty line as JSON.  Valid JSON objects are forwarded
    to *on_activity* (if provided).  The ``result`` field from
    ``{"type": "result"}`` events is captured as *result_text*.

    Lines that aren't valid JSON are silently collected for logging but
    not forwarded — this keeps the caller working even if the agent
    emits non-JSON diagnostics to stdout.

    Returns early with ``timed_out=True`` when the deadline is exceeded,
    leaving the caller responsible for killing the subprocess.

    When *capture_stdout* is ``False``, stdout is still drained and parsed but
    not retained in memory.  This keeps the streaming path lightweight when no
    later completion-signal parsing or log writing needs the raw bytes.
    """
    stdout_lines: list[str] | None = [] if capture_stdout else None
    result_text: str | None = None
    tool_use_count = 0
    turn_capped = False
    count_tool_use = adapter is not None and adapter.counts_what == "tool_use"

    line_q: queue.Queue[str | None] = queue.Queue()
    threading.Thread(target=_readline_pump, args=(stdout, line_q), daemon=True).start()

    while True:
        # Compute how long we can wait for the next line.
        if deadline is not None:
            # Clamp to 0 so that an already-expired deadline still does a
            # non-blocking drain of queued lines before returning — lines
            # the reader thread already buffered are not silently lost.
            get_timeout: float | None = max(deadline - time.monotonic(), 0)
        else:
            get_timeout = None

        try:
            line = line_q.get(timeout=get_timeout)
        except queue.Empty:
            # Deadline expired while waiting for a line.
            return _StreamResult(
                stdout_lines=tuple(stdout_lines) if stdout_lines is not None else None,
                result_text=result_text,
                timed_out=True,
                tool_use_count=tool_use_count,
                turn_capped=turn_capped,
            )

        if line is None:  # EOF sentinel from reader thread
            return _StreamResult(
                stdout_lines=tuple(stdout_lines) if stdout_lines is not None else None,
                result_text=result_text,
                timed_out=False,
                tool_use_count=tool_use_count,
                turn_capped=turn_capped,
            )

        if stdout_lines is not None:
            stdout_lines.append(line)
        _call_safely(on_output_line, line.rstrip("\r\n"), _STDOUT)

        stripped = line.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict):
                    if parsed.get("type") == _RESULT_EVENT_TYPE and isinstance(
                        parsed.get(_RESULT_FIELD), str
                    ):
                        result_text = parsed[_RESULT_FIELD]
                    _call_safely(on_activity, parsed)

            if count_tool_use and adapter is not None:
                event = adapter.parse_event(stripped)
                if event is not None and event.kind == "tool_use":
                    tool_use_count += 1
                    _call_safely(on_tool_use, event.name or "", tool_use_count)
                    if max_turns is not None and tool_use_count >= max_turns:
                        return _StreamResult(
                            stdout_lines=(
                                tuple(stdout_lines)
                                if stdout_lines is not None
                                else None
                            ),
                            result_text=result_text,
                            timed_out=False,
                            tool_use_count=tool_use_count,
                            turn_capped=True,
                        )

        # Also check deadline after processing — if the reader thread
        # already queued many lines, this prevents unbounded processing
        # past the deadline.
        if deadline is not None and time.monotonic() > deadline:
            return _StreamResult(
                stdout_lines=tuple(stdout_lines) if stdout_lines is not None else None,
                result_text=result_text,
                timed_out=True,
                tool_use_count=tool_use_count,
                turn_capped=turn_capped,
            )


def _run_agent_streaming(
    cmd: list[str],
    stdin_text: str | None,
    timeout: float | None,
    log_dir: Path | None,
    iteration: int,
    on_activity: ActivityCallback | None = None,
    on_output_line: OutputLineCallback | None = None,
    capture_result_text: bool = False,
    capture_stdout: bool = False,
    adapter: CLIAdapter | None = None,
    max_turns: int | None = None,
    on_tool_use: ToolUseCallback | None = None,
    env: dict[str, str] | None = None,
) -> AgentResult:
    """Run the agent subprocess with line-by-line streaming of JSON output.

    Used for adapters whose ``supports_streaming`` flag is True (e.g. Claude
    Code's ``--output-format stream-json``, Codex's ``--json``).  The command
    list *must already include* any adapter-required flags —
    :func:`execute_agent` calls ``adapter.build_command`` before dispatching.

    *stdin_text* is the adapter-resolved prompt payload: a string when the
    agent reads its prompt from stdin (the writer thread delivers it), or
    ``None`` for arg-delivery agents whose prompt already lives in *cmd*.
    When ``None``, stdin is wired to ``DEVNULL`` so the child gets immediate
    EOF and no writer thread runs.

    Stream processing is delegated to :func:`_read_agent_stream`; this
    function owns the subprocess lifecycle (spawn, stdin delivery, timeout
    kill, and cleanup via ``try/finally``).

    stderr is drained concurrently on a background reader thread so large
    stderr volume can't deadlock the child on a full OS pipe buffer while
    the main thread is reading stdout.
    """
    start = time.monotonic()
    deadline = (start + timeout) if timeout is not None else None

    capture_stdout_text = log_dir is not None or capture_stdout
    pipe_stderr = log_dir is not None or on_output_line is not None
    capture_stderr_text = log_dir is not None
    pipe_stdin = stdin_text is not None

    writer_thread: threading.Thread | None = None
    stderr_lines: list[str] | None = [] if capture_stderr_text else None
    stderr_thread: threading.Thread | None = None

    spawn_env = _build_spawn_env(env)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if pipe_stdin else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if pipe_stderr else None,
        env=spawn_env,
        **SUBPROCESS_TEXT_KWARGS,
        **SESSION_KWARGS,
    )
    try:
        # Popen with PIPE guarantees non-None streams; guard explicitly
        # so the type checker narrows and -O mode cannot skip the check.
        if proc.stdout is None:
            raise RuntimeError("subprocess.Popen failed to create PIPE stdout")
        if pipe_stdin and proc.stdin is None:
            raise RuntimeError("subprocess.Popen failed to create PIPE stdin")
        if pipe_stderr and proc.stderr is None:
            raise RuntimeError("subprocess.Popen failed to create PIPE stderr")

        # Start the stderr pump BEFORE writing stdin so large prompts can't
        # deadlock against an agent that writes substantial diagnostics to
        # stderr while still reading its stdin.
        if proc.stderr is not None:
            stderr_thread = _start_pump_thread(
                proc.stderr, stderr_lines, _STDERR, on_output_line
            )

        # Deliver the prompt on a background thread so that a blocked write
        # (child not reading stdin, pipe buffer full) cannot prevent
        # proc.wait / deadline checks from firing.  Killing the process
        # group unblocks the write with BrokenPipeError, which
        # _deliver_prompt already swallows.  Arg-delivery agents
        # (stdin_text is None) skip this entirely.
        if stdin_text is not None:
            writer_thread = _start_writer_thread(proc, stdin_text)

        stream = _read_agent_stream(
            proc.stdout,
            deadline,
            on_activity,
            on_output_line,
            capture_stdout=capture_stdout_text,
            adapter=adapter,
            max_turns=max_turns,
            on_tool_use=on_tool_use,
        )

        if stream.timed_out or stream.turn_capped:
            _kill_process_group(proc)
        proc.wait()
    finally:
        _cleanup_agent(proc, stderr_thread, writer_thread)

    stdout = "".join(stream.stdout_lines) if stream.stdout_lines is not None else None
    stderr = "".join(stderr_lines) if stderr_lines is not None else None

    log_file = _write_log(log_dir, iteration, stdout, stderr)

    return AgentResult(
        returncode=None if stream.timed_out else proc.returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
        result_text=stream.result_text,
        timed_out=stream.timed_out,
        captured_stdout=stdout if capture_stdout_text else None,
        captured_stderr=stderr if capture_stderr_text else None,
        tool_use_count=stream.tool_use_count,
        turn_capped=stream.turn_capped,
    )


def _pump_stream(
    stream: IO[str],
    buffer: list[str] | None,
    stream_name: OutputStream,
    on_output_line: OutputLineCallback | None,
) -> None:
    """Read *stream* line by line, optionally appending to *buffer* and forwarding to the callback.

    When *buffer* is ``None`` lines are forwarded to the callback without
    accumulating — this avoids unbounded memory growth when no log file
    will be written.

    Runs on a background thread so stdout and stderr can be drained
    concurrently without deadlocking the child subprocess.

    Exception handling:

    - **Callback exceptions** are caught per-line so that a raising
      callback never kills the drain loop.  The line is still buffered.
    - **``ValueError`` / ``OSError``** from ``readline`` (e.g. the pipe
      was closed concurrently) cause a clean exit so ``join()`` returns.
    """
    try:
        for line in iter(stream.readline, ""):
            if buffer is not None:
                buffer.append(line)
            _call_safely(on_output_line, line.rstrip("\r\n"), stream_name)
    except (ValueError, OSError):
        # Pipe closed concurrently — exit cleanly so join() returns.
        pass


def _start_writer_thread(
    proc: subprocess.Popen[Any],
    prompt: str,
) -> threading.Thread:
    """Create and start a daemon thread that delivers *prompt* to *proc*'s stdin.

    A thin wrapper around :func:`_deliver_prompt` that eliminates the repeated
    ``Thread(…, daemon=True) / .start()`` boilerplate across the streaming and
    blocking execution paths.
    """
    thread = threading.Thread(target=_deliver_prompt, args=(proc, prompt), daemon=True)
    thread.start()
    return thread


def _start_pump_thread(
    stream: IO[str],
    buffer: list[str] | None,
    stream_name: OutputStream,
    on_output_line: OutputLineCallback | None,
) -> threading.Thread:
    """Create and start a daemon thread that drains *stream*.

    When *buffer* is not ``None``, lines are accumulated for later log
    writing.  When ``None``, lines are only forwarded to the callback.

    A thin wrapper around :func:`_pump_stream` that eliminates the repeated
    ``Thread(…, daemon=True) / .start()`` boilerplate in the streaming and
    blocking execution paths.
    """
    thread = threading.Thread(
        target=_pump_stream,
        args=(stream, buffer, stream_name, on_output_line),
        daemon=True,
    )
    thread.start()
    return thread


def _drain_readers(
    *threads: threading.Thread | None,
    timeout: float = _THREAD_JOIN_TIMEOUT,
) -> None:
    """Join reader threads, skipping any that are ``None``.

    Used in ``finally`` blocks to ensure background pump threads finish
    draining before the caller continues.  Logs a warning to stderr for
    any thread that fails to exit within the timeout — this is visible
    feedback that a grandchild may be holding a pipe open and the log
    may be incomplete.
    """
    for thread in threads:
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                warn(
                    f"reader thread {thread.name!r} did not exit within"
                    f" {timeout}s — log output may be incomplete"
                )


def _cleanup_agent(
    proc: subprocess.Popen[Any],
    *threads: threading.Thread | None,
) -> None:
    """Perform the full four-step shutdown for a piped agent subprocess.

    1. Kill the process if still running and wait for exit.
    2. Close parent-side pipe fds to unblock reader threads.
    3. Join reader/writer threads to drain remaining output.
    4. Finalize Python pipe objects to suppress GC warnings.

    Used in ``finally`` blocks of the streaming and blocking capture
    paths, which previously duplicated this exact sequence inline.
    """
    _ensure_process_dead(proc)
    _close_pipes(proc)
    _drain_readers(*threads)
    _finalize_pipes(proc)


def _run_agent_blocking(
    cmd: list[str],
    stdin_text: str | None,
    timeout: float | None,
    log_dir: Path | None,
    iteration: int,
    on_output_line: OutputLineCallback | None = None,
    capture_result_text: bool = False,
    capture_stdout: bool = False,
    adapter: CLIAdapter | None = None,
    max_turns: int | None = None,
    on_tool_use: ToolUseCallback | None = None,
    env: dict[str, str] | None = None,
) -> AgentResult:
    """Run the agent subprocess and return the result.

    *stdin_text* is the adapter-resolved prompt payload: a string when the
    agent reads its prompt from stdin (the writer thread delivers it), or
    ``None`` for arg-delivery agents whose prompt already lives in *cmd*.
    When ``None``, stdin is wired to ``DEVNULL`` and no writer thread runs.

    Conditionally pipes stdout/stderr based on whether any subscriber
    needs the output:

    - **Inherit** (``on_output_line is None and log_dir is None``) —
      stdout/stderr are not piped; the child writes directly to the
      parent's file descriptors.  No reader threads, no buffering.
    - **Callback only** (``on_output_line`` set, no log dir) — reader
      threads forward lines to the callback without accumulating them,
      avoiding unbounded memory growth.
    - **Buffered capture** (``log_dir`` or ``capture_stdout`` set) —
       reader threads accumulate lines for log writing or later completion
       parsing; lines are also forwarded to the callback if provided.

    The subprocess is started in its own process group so that on
    ``KeyboardInterrupt`` or timeout the entire child tree can be killed
    via :func:`_kill_process_group`.

    Returns ``returncode=None`` when the process times out.
    Raises ``FileNotFoundError`` if the command binary does not exist.
    """
    start = time.monotonic()
    # Blocking-path adapters count tool uses post-hoc by re-scanning the
    # captured stdout (see _count_tool_uses_post_hoc), so a cap is only
    # enforceable when the bytes are buffered.  Force buffering when a cap
    # is set on a tool-use-counting adapter, otherwise tool_use_count would
    # always be 0 and turn_capped would never fire.
    needs_post_hoc_count = (
        max_turns is not None
        and adapter is not None
        and adapter.counts_what == "tool_use"
    )
    capture_stdout_text = log_dir is not None or capture_stdout or needs_post_hoc_count
    capture_stderr_text = log_dir is not None
    pipe_stdout = (
        capture_stdout_text or on_output_line is not None or capture_result_text
    )
    pipe_stderr = capture_stderr_text or on_output_line is not None
    pipe_stdin = stdin_text is not None

    # When no subscriber needs the bytes, stdout/stderr are left
    # un-piped so the child writes directly to the terminal.  When
    # capture is needed, reader threads drain stdout/stderr
    # concurrently.  Lines are only accumulated into buffers when a
    # log file will be written; otherwise the callback alone observes
    # them, avoiding unbounded memory growth.
    returncode: int | None = None
    timed_out = False
    writer_thread: threading.Thread | None = None
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None
    stdout_lines: list[str] | None = [] if capture_stdout_text else None
    stderr_lines: list[str] | None = [] if capture_stderr_text else None
    result_text: str | None = None

    def _on_output_line(line: str, stream_name: OutputStream) -> None:
        nonlocal result_text
        if capture_result_text and stream_name == _STDOUT:
            extracted = _extract_result_text_from_line(line)
            if extracted is not None:
                result_text = extracted
        if on_output_line is not None:
            on_output_line(line, stream_name)

    spawn_env = _build_spawn_env(env)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if pipe_stdin else subprocess.DEVNULL,
        stdout=subprocess.PIPE if pipe_stdout else None,
        stderr=subprocess.PIPE if pipe_stderr else None,
        env=spawn_env,
        **SUBPROCESS_TEXT_KWARGS,
        **SESSION_KWARGS,
    )
    try:
        if pipe_stdin and proc.stdin is None:
            raise RuntimeError("subprocess.Popen failed to create PIPE stdin")
        if pipe_stdout:
            if proc.stdout is None:
                raise RuntimeError("subprocess.Popen failed to create PIPE stdout")
            stdout_thread = _start_pump_thread(
                proc.stdout, stdout_lines, _STDOUT, _on_output_line
            )
        if pipe_stderr:
            if proc.stderr is None:
                raise RuntimeError("subprocess.Popen failed to create PIPE stderr")
            stderr_thread = _start_pump_thread(
                proc.stderr, stderr_lines, _STDERR, _on_output_line
            )

        # Arg-delivery agents (stdin_text is None) get DEVNULL stdin and no
        # writer thread; the prompt already lives in the spawned argv.
        if stdin_text is not None:
            writer_thread = _start_writer_thread(proc, stdin_text)

        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _ensure_process_dead(proc)
            timed_out = True
    finally:
        _cleanup_agent(proc, stdout_thread, stderr_thread, writer_thread)

    stdout = "".join(stdout_lines) if stdout_lines is not None else None
    stderr = "".join(stderr_lines) if stderr_lines is not None else None
    log_file = _write_log(log_dir, iteration, stdout, stderr)

    tool_use_count, turn_capped = _count_tool_uses_post_hoc(
        adapter=adapter,
        stdout_lines=stdout_lines,
        max_turns=max_turns,
        on_tool_use=on_tool_use,
    )

    return AgentResult(
        returncode=None if timed_out else returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
        result_text=result_text or _extract_result_text_from_lines(stdout_lines),
        timed_out=timed_out,
        captured_stdout=stdout if capture_stdout_text else None,
        captured_stderr=stderr if capture_stderr_text else None,
        tool_use_count=tool_use_count,
        turn_capped=turn_capped,
    )


def execute_agent(
    cmd: list[str],
    prompt: str,
    *,
    timeout: float | None,
    log_dir: Path | None,
    iteration: int,
    adapter: CLIAdapter | None = None,
    on_activity: ActivityCallback | None = None,
    on_output_line: OutputLineCallback | None = None,
    capture_result_text: bool = False,
    capture_stdout: bool | None = None,
    max_turns: int | None = None,
    max_turns_grace: int = 0,
    on_tool_use: ToolUseCallback | None = None,
) -> AgentResult:
    """Run the agent subprocess, auto-selecting streaming or blocking mode.

    The *adapter* argument (or :func:`select_adapter` when omitted) decides
    which execution path runs: adapters whose ``supports_streaming`` flag is
    True take the line-streaming path that drives ``on_activity`` callbacks;
    all others take the blocking path with concurrent stdout/stderr drain.
    ``adapter.build_command(cmd)`` is applied before spawning, so the CLI
    receives any flags the adapter requires (e.g. Claude's
    ``--output-format stream-json --verbose`` or Codex's ``--json``).

    When *max_turns* is set, the streaming path counts adapter-reported
    tool-use events and terminates the subprocess once the cap is reached.
    The blocking path cannot preempt but records the post-hoc count.
    *max_turns_grace* enables a soft wind-down: if the adapter supports it,
    a per-iteration tempdir is set up with a counter file and environment
    variables pointing the agent at ``_wind_down_shim`` so it can warn the
    agent when the cap is ``grace`` tool-uses away.

    This is the single entry point the engine should use — callers don't need
    to know which execution mode is selected.
    """
    if adapter is None:
        adapter = select_adapter(cmd)
    cmd = adapter.build_command(cmd)
    # Let the adapter decide where the prompt goes: stdin adapters return
    # the command unchanged with ``stdin_text=prompt``; arg-delivery adapters
    # (e.g. opencode) append the prompt to argv and return ``stdin_text=None``
    # so the child is spawned with ``stdin=DEVNULL`` and no writer thread.
    inv = adapter.deliver_prompt(cmd, prompt)
    supports_streaming = adapter.supports_streaming
    if capture_stdout is None:
        capture_stdout = log_dir is not None or (
            not supports_streaming and on_output_line is None and capture_result_text
        )

    wind_down = _setup_wind_down(
        adapter=adapter,
        max_turns=max_turns,
        max_turns_grace=max_turns_grace,
        log_dir=log_dir,
        iteration=iteration,
    )
    wrapped_on_tool_use = _wrap_tool_use_with_counter(
        on_tool_use=on_tool_use,
        counter_path=wind_down.counter_path if wind_down is not None else None,
    )
    env = wind_down.env_overrides if wind_down is not None else None

    try:
        if supports_streaming:
            return _run_agent_streaming(
                inv.argv,
                inv.stdin_text,
                timeout,
                log_dir,
                iteration,
                on_activity=on_activity,
                on_output_line=on_output_line,
                capture_result_text=capture_result_text,
                capture_stdout=capture_stdout,
                adapter=adapter,
                max_turns=max_turns,
                on_tool_use=wrapped_on_tool_use,
                env=env,
            )
        return _run_agent_blocking(
            inv.argv,
            inv.stdin_text,
            timeout,
            log_dir,
            iteration,
            on_output_line=on_output_line,
            capture_result_text=capture_result_text,
            capture_stdout=capture_stdout,
            adapter=adapter,
            max_turns=max_turns,
            on_tool_use=wrapped_on_tool_use,
            env=env,
        )
    finally:
        if wind_down is not None:
            wind_down.cleanup()


def _build_spawn_env(overrides: dict[str, str] | None) -> dict[str, str] | None:
    """Compose a spawn environment merging *overrides* onto ``os.environ``.

    Returns ``None`` when no overrides are requested so ``Popen`` inherits
    the parent's environment directly (the common case).
    """
    if not overrides:
        return None
    merged = os.environ.copy()
    merged.update(overrides)
    return merged


def _setup_wind_down(
    *,
    adapter: CLIAdapter,
    max_turns: int | None,
    max_turns_grace: int,
    log_dir: Path | None,
    iteration: int,
) -> _WindDownContext | None:
    """Prepare the per-iteration tempdir + counter for soft wind-down.

    Returns ``None`` — skipping the hook wiring entirely — when any of the
    preconditions are not met:

    - *max_turns* is unset (no cap = nothing to wind down toward).
    - *max_turns_grace* is ``0`` (user opted out of the warning window).
    - The adapter's ``supports_soft_wind_down`` flag is ``False``.
    - The adapter's ``install_wind_down_hook`` raises
      ``NotImplementedError`` (e.g. Copilot has no hook system today).

    The tempdir is created with a ``ralphify-`` prefix so stale dirs are
    easy to spot in ``$TMPDIR`` after a crash.  The counter file lives in
    *log_dir* when logging is enabled (so it's co-located with the
    iteration log) and inside the tempdir otherwise.  Either way the
    caller must invoke :meth:`_WindDownContext.cleanup` in its ``finally``.
    """
    if max_turns is None or max_turns_grace <= 0:
        return None
    if not adapter.supports_soft_wind_down:
        return None
    # Clamp the grace below the cap.  A grace >= max_turns is reachable via
    # the library API (RunConfig does not validate it the way the CLI does);
    # left unclamped the shim's threshold (max(cap - grace, 0)) collapses to
    # 0 and injects the wind-down nudge on the very first tool use.
    effective_grace = min(max_turns_grace, max(max_turns - 1, 0))
    tempdir = Path(tempfile.mkdtemp(prefix=_HOOK_TEMPDIR_PREFIX))
    counter_path = _resolve_counter_path(log_dir, iteration, tempdir)
    _atomic_write_counter(counter_path, 0)
    try:
        env_overrides = adapter.install_wind_down_hook(
            tempdir=tempdir,
            counter_path=counter_path,
            cap=max_turns,
            grace=effective_grace,
        )
    except NotImplementedError:
        # counter_path may live in log_dir rather than the tempdir, so
        # removing the tempdir alone would orphan the "0" counter file in
        # the log directory.  Remove it explicitly, best-effort.
        with suppress(OSError):
            counter_path.unlink(missing_ok=True)
        shutil.rmtree(tempdir, ignore_errors=True)
        return None
    return _WindDownContext(
        tempdir=tempdir,
        counter_path=counter_path,
        env_overrides=env_overrides,
    )


def _resolve_counter_path(
    log_dir: Path | None,
    iteration: int,
    tempdir: Path,
) -> Path:
    """Pick the counter file location: co-located with the log or inside tempdir."""
    if log_dir is not None:
        filename = f"{iteration:0{_COUNTER_PAD_WIDTH}d}{_COUNTER_LOG_SUFFIX}"
        return log_dir / filename
    return tempdir / _COUNTER_FILENAME


def _atomic_write_counter(counter_path: Path, value: int) -> None:
    """Write *value* to *counter_path* via rename so readers never see a partial int.

    Best-effort: on any I/O failure the caller proceeds without wind-down
    state — the warning subscription is advisory, not required.  The first
    failure is logged once at WARNING so a silently-disabled wind-down is
    greppable; subsequent failures stay quiet to avoid per-iteration spam.
    """
    global _counter_write_failure_logged
    try:
        tmp_path = counter_path.with_name(counter_path.name + ".tmp")
        tmp_path.write_text(str(value), encoding="utf-8")
        os.replace(tmp_path, counter_path)
    except OSError as exc:
        if not _counter_write_failure_logged:
            _counter_write_failure_logged = True
            _log.warning(
                "soft wind-down counter write to %s failed (%s); "
                "wind-down will not fire this run",
                counter_path,
                exc,
            )


def _wrap_tool_use_with_counter(
    on_tool_use: ToolUseCallback | None,
    counter_path: Path | None,
) -> ToolUseCallback | None:
    """Return a callback that atomically updates *counter_path* on each tool-use.

    Returns *on_tool_use* unchanged when no counter file is in play, so the
    streaming path only pays for the disk write when wind-down is active.
    """
    if counter_path is None:
        return on_tool_use

    def _wrapped(name: str, count: int) -> None:
        _atomic_write_counter(counter_path, count)
        _call_safely(on_tool_use, name, count)

    return _wrapped


def _count_tool_uses_post_hoc(
    *,
    adapter: CLIAdapter | None,
    stdout_lines: list[str] | None,
    max_turns: int | None,
    on_tool_use: ToolUseCallback | None,
) -> tuple[int, bool]:
    """Re-scan captured stdout for tool-use events when the blocking path runs.

    Blocking-path adapters (no structured event stream) cannot preempt the
    subprocess, so the cap is reported — not enforced — by scanning the
    accumulated stdout after the child exits.  ``turn_capped`` is ``True``
    when the post-hoc count reached *max_turns*, so the engine can emit the
    same ``ITERATION_TURN_CAPPED`` event either way.
    """
    if adapter is None or adapter.counts_what != "tool_use" or not stdout_lines:
        return 0, False
    count = 0
    for line in stdout_lines:
        event = adapter.parse_event(line)
        if event is None or event.kind != "tool_use":
            continue
        count += 1
        _call_safely(on_tool_use, event.name or "", count)
    turn_capped = max_turns is not None and count >= max_turns
    return count, turn_capped
