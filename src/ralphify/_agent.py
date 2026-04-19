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
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
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

# ── Callback type aliases ──────────────────────────────────────────────
# Used across the streaming and blocking execution paths for callbacks
# that observe live agent output.

ActivityCallback = Callable[[dict[str, Any]], None]
"""Receives parsed JSON activity dicts from the agent's stream."""

OutputLineCallback = Callable[[str, OutputStream], None]
"""Receives raw output lines with their stream name ("stdout"/"stderr")."""

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


@dataclass(frozen=True, slots=True)
class _StreamResult:
    """Accumulated output from reading the agent's JSON stream."""

    stdout_lines: tuple[str, ...] | None
    result_text: str | None
    timed_out: bool


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

    line_q: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(target=_readline_pump, args=(stdout, line_q), daemon=True)
    reader.start()

    while True:
        # Compute how long we can wait for the next line.
        if deadline is not None:
            remaining = deadline - time.monotonic()
            # Use max(remaining, 0) so that an already-expired deadline
            # still does a non-blocking drain of queued lines before
            # returning — lines the reader thread already buffered are
            # not silently lost.
            get_timeout: float | None = max(remaining, 0)
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
            )

        if line is None:  # EOF sentinel from reader thread
            return _StreamResult(
                stdout_lines=tuple(stdout_lines) if stdout_lines is not None else None,
                result_text=result_text,
                timed_out=False,
            )

        if stdout_lines is not None:
            stdout_lines.append(line)
        if on_output_line is not None:
            try:
                on_output_line(line.rstrip("\r\n"), _STDOUT)
            except Exception:
                # Callback is best-effort; draining must not stop.
                pass

        stripped = line.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                if parsed.get("type") == _RESULT_EVENT_TYPE and isinstance(
                    parsed.get(_RESULT_FIELD), str
                ):
                    result_text = parsed[_RESULT_FIELD]
                if on_activity is not None:
                    try:
                        on_activity(parsed)
                    except Exception:
                        # Callback is best-effort; draining must not stop.
                        pass

        # Also check deadline after processing — if the reader thread
        # already queued many lines, this prevents unbounded processing
        # past the deadline.
        if deadline is not None and time.monotonic() > deadline:
            return _StreamResult(
                stdout_lines=tuple(stdout_lines) if stdout_lines is not None else None,
                result_text=result_text,
                timed_out=True,
            )


def _run_agent_streaming(
    cmd: list[str],
    prompt: str,
    timeout: float | None,
    log_dir: Path | None,
    iteration: int,
    on_activity: ActivityCallback | None = None,
    on_output_line: OutputLineCallback | None = None,
    capture_result_text: bool = False,
    capture_stdout: bool = False,
) -> AgentResult:
    """Run the agent subprocess with line-by-line streaming of JSON output.

    Used for adapters whose ``supports_streaming`` flag is True (e.g. Claude
    Code's ``--output-format stream-json``, Codex's ``--json``).  The command
    list *must already include* any adapter-required flags —
    :func:`execute_agent` calls ``adapter.build_command`` before dispatching.

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

    writer_thread: threading.Thread | None = None
    stderr_lines: list[str] | None = [] if capture_stderr_text else None
    stderr_thread: threading.Thread | None = None

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if pipe_stderr else None,
        **SUBPROCESS_TEXT_KWARGS,
        **SESSION_KWARGS,
    )
    try:
        # Popen with PIPE guarantees non-None streams; guard explicitly
        # so the type checker narrows and -O mode cannot skip the check.
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("subprocess.Popen failed to create PIPE streams")
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
        # _deliver_prompt already swallows.
        writer_thread = _start_writer_thread(proc, prompt)

        stream = _read_agent_stream(
            proc.stdout,
            deadline,
            on_activity,
            on_output_line,
            capture_stdout=capture_stdout_text,
        )

        if stream.timed_out:
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
            if on_output_line is not None:
                try:
                    on_output_line(line.rstrip("\r\n"), stream_name)
                except Exception:
                    # Callback is best-effort; draining must not stop.
                    pass
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
    prompt: str,
    timeout: float | None,
    log_dir: Path | None,
    iteration: int,
    on_output_line: OutputLineCallback | None = None,
    capture_result_text: bool = False,
    capture_stdout: bool = False,
) -> AgentResult:
    """Run the agent subprocess and return the result.

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
    capture_stdout_text = log_dir is not None or capture_stdout
    capture_stderr_text = log_dir is not None
    pipe_stdout = (
        capture_stdout_text or on_output_line is not None or capture_result_text
    )
    pipe_stderr = capture_stderr_text or on_output_line is not None

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

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE if pipe_stdout else None,
        stderr=subprocess.PIPE if pipe_stderr else None,
        **SUBPROCESS_TEXT_KWARGS,
        **SESSION_KWARGS,
    )
    try:
        if proc.stdin is None:
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

        writer_thread = _start_writer_thread(proc, prompt)

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

    return AgentResult(
        returncode=None if timed_out else returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
        result_text=result_text or _extract_result_text_from_lines(stdout_lines),
        timed_out=timed_out,
        captured_stdout=stdout if capture_stdout_text else None,
        captured_stderr=stderr if capture_stderr_text else None,
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
) -> AgentResult:
    """Run the agent subprocess, auto-selecting streaming or blocking mode.

    The *adapter* argument (or :func:`select_adapter` when omitted) decides
    which execution path runs: adapters whose ``supports_streaming`` flag is
    True take the line-streaming path that drives ``on_activity`` callbacks;
    all others take the blocking path with concurrent stdout/stderr drain.
    ``adapter.build_command(cmd)`` is applied before spawning, so the CLI
    receives any flags the adapter requires (e.g. Claude's
    ``--output-format stream-json --verbose`` or Codex's ``--json``).

    This is the single entry point the engine should use — callers don't need
    to know which execution mode is selected.
    """
    if adapter is None:
        adapter = select_adapter(cmd)
    cmd = adapter.build_command(cmd)
    supports_streaming = adapter.supports_streaming
    if capture_stdout is None:
        capture_stdout = log_dir is not None or (
            not supports_streaming and on_output_line is None and capture_result_text
        )

    if supports_streaming:
        return _run_agent_streaming(
            cmd,
            prompt,
            timeout,
            log_dir,
            iteration,
            on_activity=on_activity,
            on_output_line=on_output_line,
            capture_result_text=capture_result_text,
            capture_stdout=capture_stdout,
        )
    return _run_agent_blocking(
        cmd,
        prompt,
        timeout,
        log_dir,
        iteration,
        on_output_line=on_output_line,
        capture_result_text=capture_result_text,
        capture_stdout=capture_stdout,
    )
