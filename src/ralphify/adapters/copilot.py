"""GitHub Copilot CLI adapter (alpha).

The standalone ``copilot`` binary (GA 2026-02-25) ships a
``--output-format json`` mode that is **only loosely documented**.  This
adapter does best-effort counting based on the empirical shapes seen in
the ralphify test corpus; unknown event types return ``None`` rather
than crashing.

Capability matrix:

- ``counts_what = "tool_use"`` with an alpha caveat — counting accuracy
  depends on ongoing schema discovery (see :file:`docs/agents.md`).
- ``supports_streaming = False`` — event schema is unverified, so the
  adapter falls through the blocking path and avoids per-line parsing.
- ``renders_structured_peek = False`` — peek panel stays in raw-line mode.
- ``supports_soft_wind_down = False`` — Copilot has no hook system as of
  2026-04, so ``install_wind_down_hook`` raises :class:`NotImplementedError`
  (which the engine downgrades to hard-cap-only).
"""

from __future__ import annotations

import json
from pathlib import Path

from ralphify._promise import has_promise_completion
from ralphify.adapters._protocol import ADAPTERS, AdapterEvent, CountsWhat


COPILOT_BINARY_STEM = "copilot"
"""Binary stem (``Path(cmd[0]).stem``) that identifies the standalone Copilot CLI.

Note: this is the GA ``copilot`` binary, NOT the ``gh copilot`` subcommand.
The ``gh`` stem is deliberately excluded because ``gh`` hosts many other
subcommands that have nothing to do with AI agents.
"""

_OUTPUT_FORMAT_FLAGS: tuple[str, ...] = ("--output-format", "json")

_TOOL_USE_EVENT_TYPES: frozenset[str] = frozenset(
    {"tool_use", "tool_call", "ToolCall", "ToolUse"}
)
_RESULT_EVENT_TYPES: frozenset[str] = frozenset(
    {"result", "response", "final", "Final", "Complete"}
)


class CopilotAdapter:
    """Best-effort adapter for the standalone Copilot CLI."""

    name: str = "copilot"
    counts_what: CountsWhat = "tool_use"
    supports_streaming: bool = False
    renders_structured_peek: bool = False
    supports_soft_wind_down: bool = False
    # Copilot runs on the blocking path with no stream parsing today; the
    # promise tag must be located somewhere in the captured stdout.
    requires_full_stdout_for_completion: bool = True

    def matches(self, cmd: list[str]) -> bool:
        if not cmd:
            return False
        return Path(cmd[0]).stem == COPILOT_BINARY_STEM

    def build_command(self, cmd: list[str]) -> list[str]:
        """Ensure ``--output-format json`` is present.

        Idempotent: running twice yields the same command. If the caller
        already supplied ``--output-format <other>``, the existing value is
        overwritten with ``json`` — we cannot honor a user-chosen format
        while still emitting a parseable event stream.
        """
        result = list(cmd)
        output_format_flag, output_format_value = _OUTPUT_FORMAT_FLAGS
        try:
            format_index = result.index(output_format_flag)
        except ValueError:
            result.extend(_OUTPUT_FORMAT_FLAGS)
        else:
            value_index = format_index + 1
            if value_index < len(result):
                result[value_index] = output_format_value
            else:
                result.append(output_format_value)
        return result

    def parse_event(self, line: str) -> AdapterEvent | None:
        """Parse best-effort; return ``None`` for unknown shapes.

        The Copilot event schema is ``[unverified]`` in the spec — this
        method intentionally errs on the side of *not* inventing events
        so the turn cap is never inflated by false positives.
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

        event_type = parsed.get("type") or parsed.get("event") or parsed.get("kind")
        if not isinstance(event_type, str):
            return None

        if event_type in _TOOL_USE_EVENT_TYPES:
            name = parsed.get("name") or parsed.get("tool")
            return AdapterEvent(
                kind="tool_use",
                name=name if isinstance(name, str) else None,
                raw=parsed,
            )
        if event_type in _RESULT_EVENT_TYPES:
            return AdapterEvent(kind="result", raw=parsed)
        return None

    def extract_completion_signal(
        self,
        *,
        result_text: str | None,
        stdout: str | None,
        user_signal: str,
    ) -> bool:
        """Scan the entire stdout for the promise tag.

        Without a verified event schema there is no reliable per-event
        extraction path; the whole-stdout scan is the safest fallback.
        *result_text* is unused — Copilot runs on the blocking path and
        does not produce a streaming result event today.
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
            "Copilot CLI has no hook system as of 2026-04; max_turns "
            "will hard-kill without soft wind-down signal."
        )


ADAPTERS.append(CopilotAdapter())
