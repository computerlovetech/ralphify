"""Claude Code adapter.

Claude is the only CLI shipping a stable ``--output-format stream-json``
protocol today; its structured events drive the peek panel and power
per-event tool-use counting.  Every Claude iteration emits:

1. A ``system`` init event with the model name.
2. Zero or more ``assistant`` messages whose ``content`` list may include
   ``tool_use``, ``thinking``, and ``text`` blocks.
3. Zero or more ``user`` messages (tool results echoed back).
4. A terminal ``result`` event carrying the final assistant text.

Tool-use counting is scoped to ``assistant`` messages; we ignore
``tool_use`` blocks echoed back by ``user`` events so each invocation is
counted exactly once.
"""

from __future__ import annotations

import json
from pathlib import Path

from ralphify._promise import has_promise_completion
from ralphify.adapters._protocol import ADAPTERS, AdapterEvent, CountsWhat


CLAUDE_BINARY_STEM = "claude"
"""Binary stem (``Path(cmd[0]).stem``) that identifies the Claude CLI."""

_OUTPUT_FORMAT_FLAG = "--output-format"
_OUTPUT_FORMAT_VALUE = "stream-json"
_VERBOSE_FLAG = "--verbose"

_EVENT_TYPE_ASSISTANT = "assistant"
_EVENT_TYPE_RESULT = "result"
_BLOCK_TYPE_TOOL_USE = "tool_use"


class ClaudeAdapter:
    """Parses Claude's stream-json output and supports soft wind-down."""

    name: str = "claude"
    counts_what: CountsWhat = "tool_use"
    supports_streaming: bool = True
    renders_structured_peek: bool = True
    supports_soft_wind_down: bool = True
    # Claude's final assistant text already arrives as ``agent.result_text``
    # via the stream-json ``result`` event, so the engine does not need to
    # buffer the full stdout to scan for the promise tag.
    requires_full_stdout_for_completion: bool = False

    def matches(self, cmd: list[str]) -> bool:
        if not cmd:
            return False
        return Path(cmd[0]).stem == CLAUDE_BINARY_STEM

    def build_command(self, cmd: list[str]) -> list[str]:
        """Ensure ``--output-format stream-json --verbose`` is present.

        Idempotent: running twice yields the same command. If the caller
        already supplied ``--output-format <other>``, the existing value is
        overwritten with ``stream-json`` — we cannot honor a user-chosen
        format while still emitting a parseable event stream.
        """
        result = list(cmd)
        try:
            format_index = result.index(_OUTPUT_FORMAT_FLAG)
        except ValueError:
            result.extend([_OUTPUT_FORMAT_FLAG, _OUTPUT_FORMAT_VALUE])
        else:
            value_index = format_index + 1
            if value_index < len(result):
                result[value_index] = _OUTPUT_FORMAT_VALUE
            else:
                result.append(_OUTPUT_FORMAT_VALUE)
        if _VERBOSE_FLAG not in result:
            result.append(_VERBOSE_FLAG)
        return result

    def parse_event(self, line: str) -> AdapterEvent | None:
        """Parse one stream-json line into an :class:`AdapterEvent`.

        Empty lines, non-JSON payloads, and non-dict JSON return ``None``.
        ``result`` events return ``AdapterEvent(kind="result")``. An
        ``assistant`` event whose content contains a ``tool_use`` block
        returns the first such block as ``AdapterEvent(kind="tool_use")``;
        Claude emits one tool_use block per assistant message, so
        single-event dispatch matches the protocol. Every other parsed
        event dict — including non-tool-use ``assistant`` messages —
        returns ``AdapterEvent(kind="message")`` so callers can still
        render them without counting against the turn cap.
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
        if event_type == _EVENT_TYPE_RESULT:
            return AdapterEvent(kind="result", raw=parsed)
        if event_type != _EVENT_TYPE_ASSISTANT:
            return AdapterEvent(kind="message", raw=parsed)

        for block in _iter_content_blocks(parsed):
            if block.get("type") == _BLOCK_TYPE_TOOL_USE:
                name = block.get("name")
                return AdapterEvent(
                    kind="tool_use",
                    name=name if isinstance(name, str) else None,
                    raw=parsed,
                )
        return AdapterEvent(kind="message", raw=parsed)

    def extract_completion_signal(
        self,
        *,
        result_text: str | None,
        stdout: str | None,
        user_signal: str,
    ) -> bool:
        """Scan the streaming-extracted result text for ``<promise>{signal}</promise>``.

        Claude's terminal ``result`` event carries the last assistant
        message as a plain string, which the streaming reader already
        captures into :attr:`AgentResult.result_text`.  Using *result_text*
        directly avoids buffering the full stdout — large transcripts can
        run into many megabytes per iteration.

        Only the parsed result text is considered — raw JSON from
        ``status`` or ``assistant`` messages can legitimately echo
        ``<promise>...</promise>`` substrings that must not trigger
        completion.

        *stdout* is unused (Claude does not need a fallback because the
        streaming path always populates *result_text* on a successful run);
        it stays in the signature for protocol parity.
        """
        del stdout
        if result_text is None:
            return False
        return has_promise_completion(result_text, user_signal)

    def install_wind_down_hook(
        self,
        tempdir: Path,
        counter_path: Path,
        cap: int,
        grace: int,
    ) -> dict[str, str]:
        raise NotImplementedError(
            "Claude soft wind-down (settings.json PreToolUse hook) is scheduled "
            "for Phase 3 of the CLI adapter layer spec."
        )


def _iter_content_blocks(raw: dict) -> list[dict]:
    """Return the ``message.content`` list, filtered to dict blocks only."""
    message = raw.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


ADAPTERS.append(ClaudeAdapter())
