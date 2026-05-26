"""Golden-file regression tests for adapter parsing.

Each fixture is a captured (or close-to-captured) stream from one of
the supported CLIs.  The tests walk every line and assert on the
resulting :class:`AdapterEvent` sequence and completion-signal scan.
When a CLI's schema changes, these tests fail first and point the
maintainer at the fixture that needs updating.
"""

from __future__ import annotations

from pathlib import Path

from ralphify.adapters.claude import ClaudeAdapter
from ralphify.adapters.codex import CodexAdapter
from ralphify.adapters.copilot import CopilotAdapter
from ralphify.adapters.crush import CrushAdapter
from ralphify.adapters.opencode import OpenCodeAdapter


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adapters"


def _parse_kinds(adapter, text: str) -> list[str]:
    """Return the ``kind`` of every non-None event in the fixture."""
    kinds: list[str] = []
    for line in text.splitlines():
        event = adapter.parse_event(line)
        if event is not None:
            kinds.append(event.kind)
    return kinds


def test_claude_golden_stream() -> None:
    text = (FIXTURES_DIR / "claude_basic_run.jsonl").read_text()
    adapter = ClaudeAdapter()

    kinds = _parse_kinds(adapter, text)
    # 3 tool_use blocks + 1 result; other assistant messages become
    # ``message`` events that the turn counter ignores.
    assert kinds.count("tool_use") == 3
    assert kinds.count("result") == 1

    # Claude reads completion solely from the streaming-extracted result_text.
    result_text = _last_result_text(text)
    assert (
        adapter.extract_completion_signal(
            result_text=result_text, stdout=None, user_signal="COMPLETE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=result_text, stdout=None, user_signal="OTHER"
        )
        is False
    )


def test_codex_golden_stream() -> None:
    text = (FIXTURES_DIR / "codex_basic_run.jsonl").read_text()
    adapter = CodexAdapter()

    kinds = _parse_kinds(adapter, text)
    # 2 CommandExecution + CollabToolCall + msg-nested McpToolCall = 4 tool_use.
    assert kinds.count("tool_use") == 4
    # TaskComplete *and* TurnCompleted both count as result.
    assert kinds.count("result") == 2
    assert kinds.count("turn") == 1  # TurnStarted only; TurnCompleted wins as result

    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="COMPLETE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="MISSING"
        )
        is False
    )


def test_copilot_golden_stream() -> None:
    text = (FIXTURES_DIR / "copilot_basic_run.jsonl").read_text()
    adapter = CopilotAdapter()

    kinds = _parse_kinds(adapter, text)
    # 3 canonical-type tool uses; ``progress`` is unknown and dropped.
    assert kinds.count("tool_use") == 3
    assert kinds.count("result") == 1

    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="COMPLETE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="NOPE"
        )
        is False
    )


def test_opencode_golden_stream() -> None:
    text = (FIXTURES_DIR / "opencode_basic_run.jsonl").read_text()
    adapter = OpenCodeAdapter()

    kinds = _parse_kinds(adapter, text)
    # 3 tool_use parts + 1 step_finish (result); step_start / text are
    # message events that do not count against the turn cap.
    assert kinds.count("tool_use") == 3
    assert kinds.count("result") == 1
    # opencode counts tool uses, so these events feed the turn cap.
    assert adapter.counts_what == "tool_use"

    # opencode emits no streaming result line; completion is scanned from
    # the full stdout buffer.
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="COMPLETE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="ABSENT"
        )
        is False
    )


def test_crush_golden_stream() -> None:
    # crush emits plain text/markdown only — no structured events to parse,
    # so nothing counts against max_turns (counts_what == "none").
    adapter = CrushAdapter()
    text = "Did the work.\n<promise>COMPLETE</promise>\n"

    assert _parse_kinds(adapter, text) == []
    assert adapter.counts_what == "none"

    # Completion is still scanned from the full stdout buffer.
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=text, user_signal="COMPLETE"
        )
        is True
    )


def _last_result_text(text: str) -> str | None:
    """Return the last ``result`` event's payload from a Claude stream."""
    import json

    latest: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(parsed, dict)
            and parsed.get("type") == "result"
            and isinstance(parsed.get("result"), str)
        ):
            latest = parsed["result"]
    return latest
