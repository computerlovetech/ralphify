"""Combine, truncate, and format subprocess output.

Output from checks and contexts is capped at :data:`MAX_OUTPUT_LEN`
characters (5 000) to avoid blowing up the agent's context window.
"""

from __future__ import annotations

MAX_OUTPUT_LEN = 5000


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
            parts.append(stream if isinstance(stream, str) else stream.decode("utf-8", errors="replace"))
    return "".join(parts)


def truncate_output(text: str, max_len: int = MAX_OUTPUT_LEN) -> str:
    """Truncate *text* to *max_len* characters, appending an indicator if trimmed."""
    if len(text) > max_len:
        return text[:max_len] + "\n... (truncated)"
    return text


def format_duration(seconds: float) -> str:
    """Format *seconds* as a compact human-readable duration string.

    Returns ``"12.3s"`` for sub-minute, ``"2m 30s"`` for sub-hour,
    and ``"1h 15m"`` for longer durations.  Used in CLI output and
    event data for iteration timing.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
