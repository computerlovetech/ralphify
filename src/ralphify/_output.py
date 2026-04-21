"""Combine and format subprocess output."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

# Platform flag used by _agent.py and cli.py to guard Windows-specific code
# paths (process-group handling, console encoding).  Centralised here next to
# SUBPROCESS_TEXT_KWARGS so platform-aware modules import from one place.
IS_WINDOWS = sys.platform == "win32"

# Shared subprocess kwargs for text-mode execution with UTF-8 decoding.
# Every subprocess.run / subprocess.Popen call that reads text output should
# unpack these to ensure consistent encoding behavior across the codebase.
SUBPROCESS_TEXT_KWARGS: dict[str, Any] = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
    "bufsize": 1,  # Line-buffered: readline() returns as soon as a newline
    # arrives instead of filling an 8KB readahead buffer.  Critical for the
    # streaming path where peek must flow line-at-a-time.
}

# Subprocess kwargs that isolate child processes in their own session/group.
# On POSIX this uses start_new_session so the child and all its descendants
# form a separate process group that can be killed together.
SESSION_KWARGS: dict[str, Any] = {} if IS_WINDOWS else {"start_new_session": True}


@dataclass(slots=True)
class ProcessResult:
    """Base result for any subprocess execution.

    Shared by :class:`~ralphify._runner.RunResult` and
    :class:`~ralphify._agent.AgentResult` so the common *success*
    logic lives in one place.

    *returncode* is the process exit code, or ``None`` when the process
    timed out.  *timed_out* makes the timeout condition explicit — prefer
    checking ``timed_out`` over ``returncode is None``.
    """

    returncode: int | None
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """Whether the process exited successfully (code 0, no timeout)."""
        return self.returncode == 0 and not self.timed_out


def ensure_str(value: str | bytes) -> str:
    """Decode *value* to a string if it is bytes, passing strings through.

    Uses UTF-8 with replacement so non-decodable bytes never raise.
    """
    return value if isinstance(value, str) else value.decode("utf-8", errors="replace")


def collect_output(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> str:
    """Combine stdout and stderr into a single string.

    Handles both str and bytes (as returned by subprocess.TimeoutExpired),
    decoding bytes as UTF-8 with replacement for non-decodable characters.
    """
    parts: list[str] = []
    for stream in (stdout, stderr):
        if stream:
            text = ensure_str(stream)
            if parts and not parts[-1].endswith("\n"):
                parts.append("\n")
            parts.append(text)
    return "".join(parts)


def warn(message: str) -> None:
    """Print a warning message to stderr with the ``ralphify:`` prefix.

    Used by low-level modules (agent, keypress) for operational warnings
    that should be visible even when Rich console rendering is not active.
    """
    print(f"ralphify: warning: {message}", file=sys.stderr)


_COUNT_THOUSANDS = 1_000
_COUNT_MILLIONS = 1_000_000
_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60


def format_count(n: int) -> str:
    """Format *n* as a compact human-readable count string.

    Returns ``"500"`` for sub-thousand, ``"1.5k"`` for sub-million,
    and ``"1.5M"`` for larger values.  Used in console rendering for
    token counts and similar metrics.

    Handles the boundary where rounding ``k`` crosses into ``M`` —
    e.g. 999_950 → ``"1.0M"`` instead of ``"1000.0k"`` (same guard
    as :func:`format_duration`'s 59.95 → ``"1m 0s"``).
    """
    if n >= _COUNT_MILLIONS:
        return f"{n / _COUNT_MILLIONS:.1f}M"
    if n >= _COUNT_THOUSANDS:
        # Use rounded value to avoid "1000.0k" when rounding crosses
        # into the next unit (same guard as format_duration's 59.95→1m).
        if round(n / _COUNT_THOUSANDS, 1) >= _COUNT_THOUSANDS:
            return f"{n / _COUNT_MILLIONS:.1f}M"
        return f"{n / _COUNT_THOUSANDS:.1f}k"
    return str(n)


def format_duration(seconds: float) -> str:
    """Format *seconds* as a compact human-readable duration string.

    Returns ``"12.3s"`` for sub-minute, ``"2m 30s"`` for sub-hour,
    and ``"1h 15m"`` for longer durations.  Used in CLI output and
    event data for iteration timing.
    """
    if round(seconds, 1) < _SECONDS_PER_MINUTE:
        return f"{seconds:.1f}s"
    # Use rounded total to avoid edge cases like 59.95 → "0m 60s".
    # int(…+0.5) gives standard "round half up" instead of Python's
    # round() which uses banker's rounding (round-half-to-even) — the
    # latter silently drops 0.5s when the total is even (e.g. 90.5→90).
    total = int(seconds + 0.5)
    minutes = total // _SECONDS_PER_MINUTE
    if minutes < _MINUTES_PER_HOUR:
        secs = total % _SECONDS_PER_MINUTE
        return f"{minutes}m {secs}s"
    hours = minutes // _MINUTES_PER_HOUR
    mins = minutes % _MINUTES_PER_HOUR
    return f"{hours}h {mins}m"
