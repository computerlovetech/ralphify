"""opencode CLI adapter.

opencode delivers the prompt as a positional argument (``opencode run
"<prompt>"``) rather than on stdin, and emits newline-delimited JSON when
invoked with ``--format json``.  Each line looks like::

    {"type": "<event>", "part": {...}}

This adapter is the first *arg-delivery* adapter: :meth:`deliver_prompt`
appends the prompt to argv and returns ``stdin_text=None`` so ``_agent.py``
spawns the child with ``stdin=DEVNULL`` and runs no writer thread.

Event mapping:

- ``tool_use`` -> ``AdapterEvent(kind="tool_use", ...)`` (name best-effort
  from ``part``).
- ``step_finish`` -> ``AdapterEvent(kind="result", ...)`` (carries token /
  cost data in ``part`` that this adapter does not surface).
- ``step_start`` / ``text`` / ``tool_result`` -> ``AdapterEvent(kind="message")``
  so callers can render them without counting against the turn cap.
- unknown / malformed -> ``None`` (MUST NOT raise, for parity with the
  other adapters).

Completion detection mirrors :mod:`codex`: opencode has no terminal
``{"type":"result"}`` line that the streaming reader extracts into
``result_text``, so the adapter scans the full stdout buffer for the
``<promise>...</promise>`` tag.
"""

from __future__ import annotations

import json
from pathlib import Path

from ralphify._promise import has_promise_completion
from ralphify.adapters._protocol import (
    ADAPTERS,
    AdapterEvent,
    CountsWhat,
    Invocation,
)


OPENCODE_BINARY_STEM = "opencode"
"""Binary stem (``Path(cmd[0]).stem``) that identifies the opencode CLI."""

_FORMAT_FLAGS: tuple[str, ...] = ("--format", "json")

_TOOL_USE_EVENT = "tool_use"
_RESULT_EVENT = "step_finish"
_MESSAGE_EVENTS: frozenset[str] = frozenset({"step_start", "text", "tool_result"})


class OpenCodeAdapter:
    """Parses opencode's ``--format json`` event stream; delivers prompt by arg."""

    name: str = "opencode"
    counts_what: CountsWhat = "tool_use"
    supports_streaming: bool = True
    # The console peek panel only understands Claude's stream-json schema
    # today, so keep opencode in raw-line peek mode (as with codex).
    renders_structured_peek: bool = False
    # opencode has no hook system; soft wind-down is a Phase-3 stub anyway.
    supports_soft_wind_down: bool = False
    # opencode emits no terminal ``{"type":"result"}`` line that the
    # streaming reader extracts into ``result_text``; the full stdout
    # buffer is the only source for promise-tag scanning.
    requires_full_stdout_for_completion: bool = True

    def matches(self, cmd: list[str]) -> bool:
        if not cmd:
            return False
        return Path(cmd[0]).stem == OPENCODE_BINARY_STEM

    def build_command(self, cmd: list[str]) -> list[str]:
        """Ensure ``--format json`` is present.

        Idempotent: running twice yields the same command. If the caller
        already supplied ``--format <other>``, the existing value is
        overwritten with ``json`` — we cannot honor a user-chosen format
        while still emitting a parseable event stream.
        """
        result = list(cmd)
        format_flag, format_value = _FORMAT_FLAGS
        try:
            format_index = result.index(format_flag)
        except ValueError:
            result.extend(_FORMAT_FLAGS)
        else:
            value_index = format_index + 1
            if value_index < len(result):
                result[value_index] = format_value
            else:
                result.append(format_value)
        return result

    def deliver_prompt(self, cmd: list[str], prompt: str) -> Invocation:
        """Append the prompt as a positional arg; opencode does not read stdin."""
        return Invocation(argv=[*cmd, prompt], stdin_text=None)

    def parse_event(self, line: str) -> AdapterEvent | None:
        """Classify one JSONL line as tool_use / result / message.

        Empty lines, non-JSON payloads, and non-dict JSON return ``None``.
        Never raises on garbage input (FR-5).
        """
        stripped = line.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None

        event_type = parsed.get("type")
        if event_type == _TOOL_USE_EVENT:
            return AdapterEvent(
                kind="tool_use",
                name=_tool_name(parsed),
                raw=parsed,
            )
        if event_type == _RESULT_EVENT:
            return AdapterEvent(kind="result", raw=parsed)
        if event_type in _MESSAGE_EVENTS:
            return AdapterEvent(kind="message", raw=parsed)
        return None

    def extract_completion_signal(
        self,
        *,
        result_text: str | None,
        stdout: str | None,
        user_signal: str,
    ) -> bool:
        """Scan the full stdout for the ``<promise>{signal}</promise>`` tag.

        *result_text* is unused — opencode never populates it through the
        streaming reader (no ``{"type":"result"}`` lines).  The engine opts
        into ``requires_full_stdout_for_completion`` to make sure *stdout*
        is supplied when promise detection is requested.
        """
        del result_text
        if stdout is None:
            return False
        return has_promise_completion(stdout, user_signal)

    def install_wind_down_hook(
        self,
        tempdir: Path,
        counter_path: Path,
        cap: int,
        grace: int,
    ) -> dict[str, str]:
        raise NotImplementedError(
            "opencode has no hook system; soft wind-down is scheduled for "
            "Phase 3 of the CLI adapter layer spec."
        )


def _tool_name(parsed: dict) -> str | None:
    """Best-effort extraction of the tool name from a ``tool_use`` event.

    opencode nests event data under ``part``; the tool name may live there
    or at the top level depending on the build.  Returns ``None`` when no
    string name is found.
    """
    for key in ("name", "tool", "tool_name"):
        value = parsed.get(key)
        if isinstance(value, str):
            return value
    part = parsed.get("part")
    if isinstance(part, dict):
        for key in ("name", "tool", "tool_name"):
            value = part.get(key)
            if isinstance(value, str):
                return value
    return None


ADAPTERS.append(OpenCodeAdapter())
