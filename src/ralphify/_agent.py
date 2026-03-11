"""Run agent subprocesses with output capture and timeout enforcement.

This module handles the mechanics of executing agent commands — spawning
processes, enforcing timeouts, capturing output, and writing log files.
The engine module uses these functions but owns the orchestration: state
updates, event emission, and loop control.

Two execution modes are supported:

- **Streaming** (``run_agent_streaming``) — line-by-line stdout reading
  via ``Popen``, used for agents that emit JSON streams (e.g. Claude Code).
- **Blocking** (``run_agent``) — ``subprocess.run`` with optional output
  capture, used for all other agents.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from ralphify._output import collect_output


class AgentResult(NamedTuple):
    """Result of running the agent subprocess."""

    returncode: int | None  # None means timed out
    elapsed: float
    log_file: Path | None


def _write_log(
    log_path_dir: Path,
    iteration: int,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> Path:
    """Write iteration output to a timestamped log file and return the path."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_path_dir / f"{iteration:03d}_{timestamp}.log"
    log_file.write_text(collect_output(stdout, stderr))
    return log_file


def _is_claude_command(cmd: list[str]) -> bool:
    """Return True if the command looks like Claude Code (supports stream-json)."""
    if not cmd:
        return False
    binary = Path(cmd[0]).name
    return binary == "claude"


def run_agent_streaming(
    cmd: list[str],
    prompt: str,
    timeout: float | None,
    log_path_dir: Path | None,
    iteration: int,
    on_activity: Callable[[dict], None] | None = None,
) -> AgentResult:
    """Run the agent subprocess with line-by-line streaming of JSON output.

    Used for agents that support ``--output-format stream-json`` (e.g. Claude
    Code).  Each JSON line is passed to *on_activity* (if provided) so the
    caller can emit events or update UI.

    Falls back gracefully if any line is not valid JSON — it is still
    collected for logging but not forwarded as structured data.

    Timeout is enforced manually between line reads (``Popen`` has no
    built-in timeout on iteration).  A ``try/finally`` ensures the child
    process is cleaned up even on unexpected errors.
    """
    stream_cmd = cmd + ["--output-format", "stream-json", "--verbose"]
    start = time.monotonic()
    deadline = (start + timeout) if timeout else None
    stdout_lines: list[str] = []
    stderr_data = ""
    returncode: int | None = None

    proc = subprocess.Popen(
        stream_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Guaranteed non-None because we passed PIPE for all three streams.
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None

        # Send prompt and close stdin so the agent can start.
        proc.stdin.write(prompt)
        proc.stdin.close()

        timed_out = False
        for line in proc.stdout:
            if deadline and time.monotonic() > deadline:
                proc.kill()
                proc.wait()
                timed_out = True
                break
            stdout_lines.append(line)
            stripped = line.strip()
            if stripped and on_activity is not None:
                try:
                    parsed = json.loads(stripped)
                    on_activity(parsed)
                except json.JSONDecodeError:
                    pass
            sys.stdout.write(line)

        if not timed_out:
            # stdout exhausted — process finished normally.
            proc.wait()
            returncode = proc.returncode

        stderr_data = proc.stderr.read()
        if stderr_data:
            sys.stderr.write(stderr_data)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    log_file: Path | None = None
    if log_path_dir:
        log_file = _write_log(log_path_dir, iteration, "".join(stdout_lines), stderr_data)

    return AgentResult(
        returncode=returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
    )


def run_agent(
    cmd: list[str],
    prompt: str,
    timeout: float | None,
    log_path_dir: Path | None,
    iteration: int,
) -> AgentResult:
    """Run the agent subprocess, optionally write logs, and return the result.

    When *log_path_dir* is set, output is captured, written to a log file,
    then echoed to stdout/stderr so the user still sees it live.  When unset,
    output streams directly to the terminal (no capture overhead).

    Returns ``returncode=None`` when the process times out.
    Raises ``FileNotFoundError`` if the command binary does not exist.
    """
    start = time.monotonic()
    log_file: Path | None = None
    returncode: int | None = None

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            timeout=timeout,
            capture_output=bool(log_path_dir),
        )
        if log_path_dir:
            log_file = _write_log(log_path_dir, iteration, result.stdout, result.stderr)
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
        returncode = result.returncode
    except subprocess.TimeoutExpired as e:
        if log_path_dir:
            log_file = _write_log(log_path_dir, iteration, e.stdout, e.stderr)

    return AgentResult(
        returncode=returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
    )
