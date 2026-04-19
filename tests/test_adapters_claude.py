"""Tests for the Claude stream-json adapter."""

from __future__ import annotations

import json

import pytest

from ralphify.adapters import select_adapter
from ralphify.adapters.claude import ClaudeAdapter


def _assistant_event(*blocks: dict) -> str:
    """Build one JSON line matching Claude's assistant message schema."""
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": list(blocks)},
        }
    )


def _result_event(result_text: str) -> str:
    return json.dumps({"type": "result", "result": result_text})


def test_matches_claude_binary_stem() -> None:
    adapter = ClaudeAdapter()
    assert adapter.matches(["claude"]) is True
    assert adapter.matches(["/usr/local/bin/claude"]) is True
    assert adapter.matches(["claude", "--print"]) is True
    assert adapter.matches(["codex"]) is False
    assert adapter.matches([]) is False


def test_build_command_appends_stream_flags() -> None:
    adapter = ClaudeAdapter()
    result = adapter.build_command(["claude"])
    assert result == ["claude", "--output-format", "stream-json", "--verbose"]


def test_build_command_is_idempotent() -> None:
    adapter = ClaudeAdapter()
    once = adapter.build_command(["claude"])
    twice = adapter.build_command(once)
    assert once == twice


def test_build_command_preserves_user_flags() -> None:
    adapter = ClaudeAdapter()
    result = adapter.build_command(["claude", "--print", "-p"])
    assert result[:3] == ["claude", "--print", "-p"]
    assert "--output-format" in result
    assert "stream-json" in result


def test_parse_tool_use_event() -> None:
    adapter = ClaudeAdapter()
    line = _assistant_event({"type": "tool_use", "name": "Bash", "input": {}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name == "Bash"


def test_parse_result_event() -> None:
    adapter = ClaudeAdapter()
    event = adapter.parse_event(_result_event("done"))
    assert event is not None
    assert event.kind == "result"


def test_parse_ignores_thinking_blocks() -> None:
    adapter = ClaudeAdapter()
    line = _assistant_event({"type": "thinking", "thinking": "planning..."})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "message"


def test_parse_malformed_json_returns_none() -> None:
    adapter = ClaudeAdapter()
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("") is None
    assert adapter.parse_event("   \n") is None


def test_parse_non_dict_json_returns_none() -> None:
    adapter = ClaudeAdapter()
    assert adapter.parse_event("[1, 2, 3]") is None
    assert adapter.parse_event('"just a string"') is None


def test_parse_tool_use_with_non_string_name() -> None:
    """Defensive: tool_use blocks with missing name must not raise."""
    adapter = ClaudeAdapter()
    line = _assistant_event({"type": "tool_use", "input": {}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name is None


def test_parse_skips_first_non_tool_use_block() -> None:
    adapter = ClaudeAdapter()
    line = _assistant_event(
        {"type": "text", "text": "thinking out loud"},
        {"type": "tool_use", "name": "Edit", "input": {}},
    )
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name == "Edit"


def test_extract_completion_signal_from_result_text() -> None:
    adapter = ClaudeAdapter()
    result_text = "<promise>DONE</promise>"
    assert (
        adapter.extract_completion_signal(
            result_text=result_text, stdout=None, user_signal="DONE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=result_text, stdout=None, user_signal="OTHER"
        )
        is False
    )


def test_extract_completion_signal_ignores_raw_stdout() -> None:
    """ClaudeAdapter only inspects ``result_text``; the streaming reader
    extracts the terminal assistant message there.  Promise tags embedded
    in raw stdout (e.g. ``status`` or ``assistant`` JSON) must not trigger
    completion."""
    adapter = ClaudeAdapter()
    stdout = "raw text <promise>MARKER</promise> trailing"
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=stdout, user_signal="MARKER"
        )
        is False
    )


def test_extract_completion_signal_handles_missing_result_text() -> None:
    adapter = ClaudeAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=None, user_signal="DONE"
        )
        is False
    )
    assert (
        adapter.extract_completion_signal(
            result_text="", stdout=None, user_signal="DONE"
        )
        is False
    )


def test_install_wind_down_hook_raises_not_implemented(tmp_path) -> None:
    adapter = ClaudeAdapter()
    with pytest.raises(NotImplementedError):
        adapter.install_wind_down_hook(tmp_path, tmp_path / "counter", 10, 2)


def test_capability_flags() -> None:
    adapter = ClaudeAdapter()
    assert adapter.name == "claude"
    assert adapter.counts_what == "tool_use"
    assert adapter.supports_streaming is True
    assert adapter.renders_structured_peek is True
    assert adapter.supports_soft_wind_down is True
    assert adapter.requires_full_stdout_for_completion is False


def test_registered_in_adapters_registry() -> None:
    """Import side-effect registration should hand back the Claude adapter."""
    selected = select_adapter(["claude"])
    assert isinstance(selected, ClaudeAdapter)
