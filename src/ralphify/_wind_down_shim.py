"""Hook shim invoked by agent CLIs to inject a soft wind-down message.

Claude (PreToolUse) and Codex (PostToolUse Bash matcher) both treat
exit-code 0 + a JSON payload on stdout as the standard injection
channel for hook output.  The JSON shape differs per CLI, so this shim
is dispatched by an ``agent`` argument.

Invocation::

    python -m ralphify._wind_down_shim <counter_path> <cap> <grace> <agent>

The shim reads the running tool-use count from ``counter_path``
(written by ``_agent.py`` after every parsed tool_use event) and emits
the wind-down message only when ``count >= cap - grace``.  Any failure
(missing file, malformed integer, unknown agent, missing args) is
treated as a no-op so a buggy hook can never break the agent loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


CLAUDE = "claude"
CODEX = "codex"

_VALID_AGENTS: frozenset[str] = frozenset({CLAUDE, CODEX})


def _build_message(count: int, cap: int) -> str:
    """Return the user-facing wind-down sentence.

    Phrased as instruction the agent can act on directly so the next
    one-or-two turns are spent finishing rather than mid-task work that
    will be SIGTERM'd anyway.
    """
    return (
        f"You have used {count} of {cap} tool uses. "
        "Wrap up your work in the next 1-2 turns."
    )


def _claude_payload(message: str) -> dict[str, Any]:
    """Build the Claude PreToolUse ``additionalContext`` payload.

    Matches the schema documented in the Claude Code hook reference: an
    ``hookSpecificOutput`` object whose ``hookEventName`` is the source
    event and whose ``additionalContext`` is appended to the agent's
    context window before the tool runs.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        }
    }


def _codex_payload(message: str) -> dict[str, Any]:
    """Build the Codex PostToolUse ``systemMessage`` payload.

    Codex's hook output schema treats ``systemMessage`` as a free-form
    string injected into the conversation — the analogue of Claude's
    ``additionalContext`` for the matched tool event.
    """
    return {"systemMessage": message}


def _read_counter(path: Path) -> int:
    """Return the integer stored in *path*, or ``0`` for any failure mode.

    ``_agent.py`` writes ``"0"`` before spawn and atomic-replaces the
    file on every tool_use event.  A missing file just before the first
    write or a partially-written file mid-rename both reasonably
    represent ``count == 0``.
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return 0
    try:
        return int(text or "0")
    except ValueError:
        return 0


def _resolve_agent_payload(
    agent: str,
    message: str,
) -> dict[str, Any] | None:
    if agent == CLAUDE:
        return _claude_payload(message)
    if agent == CODEX:
        return _codex_payload(message)
    return None


def main(argv: list[str]) -> int:
    """Entry point for ``python -m ralphify._wind_down_shim``.

    All failures return ``0`` (no-op + no output) so a misbehaving hook
    is observably absent rather than disruptive — the worst case is the
    soft wind-down does not fire and the hard SIGTERM cap takes over.
    """
    if len(argv) < 5:
        return 0
    counter_path = Path(argv[1])
    try:
        cap = int(argv[2])
        grace = int(argv[3])
    except ValueError:
        return 0
    agent = argv[4]
    if agent not in _VALID_AGENTS:
        return 0

    count = _read_counter(counter_path)
    threshold = max(cap - grace, 0)
    if count < threshold:
        return 0

    payload = _resolve_agent_payload(agent, _build_message(count, cap))
    if payload is None:
        return 0
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(list(sys.argv)))
