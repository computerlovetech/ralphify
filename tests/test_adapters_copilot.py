"""Tests for the Copilot CLI adapter (alpha)."""

from __future__ import annotations

import json

import pytest

from ralphify.adapters import select_adapter
from ralphify.adapters.copilot import CopilotAdapter


def test_matches_copilot_binary_stem() -> None:
    adapter = CopilotAdapter()
    assert adapter.matches(["copilot"]) is True
    assert adapter.matches(["/opt/copilot/bin/copilot"]) is True
    # Deliberately does NOT match the gh subcommand
    assert adapter.matches(["gh"]) is False
    assert adapter.matches([]) is False


def test_build_command_appends_json_flags() -> None:
    adapter = CopilotAdapter()
    assert adapter.build_command(["copilot"]) == [
        "copilot",
        "--output-format",
        "json",
    ]


def test_build_command_is_idempotent() -> None:
    adapter = CopilotAdapter()
    once = adapter.build_command(["copilot"])
    twice = adapter.build_command(once)
    assert once == twice


def test_parse_tool_use_variants() -> None:
    adapter = CopilotAdapter()
    for event_type in ("tool_use", "tool_call", "ToolCall", "ToolUse"):
        line = json.dumps({"type": event_type, "name": "Edit"})
        event = adapter.parse_event(line)
        assert event is not None
        assert event.kind == "tool_use"
        assert event.name == "Edit"


def test_parse_result_variants() -> None:
    adapter = CopilotAdapter()
    for event_type in ("result", "response", "final", "Complete"):
        event = adapter.parse_event(json.dumps({"type": event_type}))
        assert event is not None
        assert event.kind == "result"


def test_parse_unknown_returns_none() -> None:
    """Unknown event types must NOT count against the turn cap."""
    adapter = CopilotAdapter()
    assert adapter.parse_event(json.dumps({"type": "SomethingElse"})) is None
    assert adapter.parse_event(json.dumps({"type": "progress"})) is None


def test_parse_missing_type_returns_none() -> None:
    adapter = CopilotAdapter()
    assert adapter.parse_event(json.dumps({"name": "Edit"})) is None


def test_parse_malformed_returns_none() -> None:
    adapter = CopilotAdapter()
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("") is None


def test_parse_event_with_alternate_key_names() -> None:
    """Covers ``event`` / ``kind`` alternative type keys."""
    adapter = CopilotAdapter()
    event = adapter.parse_event(json.dumps({"event": "tool_use", "name": "Bash"}))
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name == "Bash"


def test_extract_completion_signal_scans_stdout() -> None:
    adapter = CopilotAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text=None,
            stdout="chat chatter <promise>MARKER</promise> more text",
            user_signal="MARKER",
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout="no marker here", user_signal="MARKER"
        )
        is False
    )


def test_extract_completion_signal_returns_false_when_stdout_missing() -> None:
    adapter = CopilotAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=None, user_signal="MARKER"
        )
        is False
    )


def test_install_wind_down_hook_raises_not_implemented(tmp_path) -> None:
    adapter = CopilotAdapter()
    with pytest.raises(NotImplementedError, match="no hook system"):
        adapter.install_wind_down_hook(tmp_path, tmp_path / "counter", 10, 2)


def test_capability_flags() -> None:
    adapter = CopilotAdapter()
    assert adapter.name == "copilot"
    assert adapter.counts_what == "tool_use"
    assert adapter.supports_streaming is False
    assert adapter.renders_structured_peek is False
    assert adapter.supports_soft_wind_down is False
    assert adapter.requires_full_stdout_for_completion is True


def test_registered_in_adapters_registry() -> None:
    selected = select_adapter(["copilot"])
    assert isinstance(selected, CopilotAdapter)
