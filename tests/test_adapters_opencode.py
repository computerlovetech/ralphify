"""Tests for the opencode CLI adapter (arg-delivery)."""

from __future__ import annotations

import json

import pytest

from ralphify.adapters import CLIAdapter, Invocation, select_adapter
from ralphify.adapters.opencode import OpenCodeAdapter


def test_matches_opencode_binary_stem() -> None:
    adapter = OpenCodeAdapter()
    assert adapter.matches(["opencode"]) is True
    assert adapter.matches(["/usr/local/bin/opencode"]) is True
    assert adapter.matches(["opencode", "run"]) is True
    assert adapter.matches(["claude"]) is False
    assert adapter.matches(["codex"]) is False
    assert adapter.matches([]) is False


def test_build_command_appends_format_json() -> None:
    adapter = OpenCodeAdapter()
    assert adapter.build_command(["opencode", "run"]) == [
        "opencode",
        "run",
        "--format",
        "json",
    ]


def test_build_command_is_idempotent() -> None:
    adapter = OpenCodeAdapter()
    once = adapter.build_command(["opencode", "run"])
    twice = adapter.build_command(once)
    assert once == twice == ["opencode", "run", "--format", "json"]


def test_build_command_overwrites_other_format_value() -> None:
    adapter = OpenCodeAdapter()
    result = adapter.build_command(["opencode", "run", "--format", "text"])
    assert result == ["opencode", "run", "--format", "json"]


def test_build_command_appends_value_when_format_flag_is_last() -> None:
    """A dangling ``--format`` with no value gets ``json`` appended, not crash."""
    adapter = OpenCodeAdapter()
    result = adapter.build_command(["opencode", "run", "--format"])
    assert result == ["opencode", "run", "--format", "json"]


def test_deliver_prompt_appends_prompt_as_arg_with_no_stdin() -> None:
    adapter = OpenCodeAdapter()
    inv = adapter.deliver_prompt(["opencode", "run", "--format", "json"], "hello")
    assert inv == Invocation(["opencode", "run", "--format", "json", "hello"], None)
    assert inv.stdin_text is None


def test_deliver_prompt_preserves_special_characters() -> None:
    """No shell involved — quotes / $() / newlines pass through as one argv element."""
    adapter = OpenCodeAdapter()
    prompt = 'fix "$(rm -rf /)" and\nmove on'
    inv = adapter.deliver_prompt(["opencode", "run"], prompt)
    assert inv.argv == ["opencode", "run", prompt]
    assert inv.stdin_text is None


def test_parse_tool_use_event_with_name() -> None:
    adapter = OpenCodeAdapter()
    line = json.dumps({"type": "tool_use", "part": {"name": "Edit"}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name == "Edit"


def test_parse_tool_use_event_top_level_name() -> None:
    adapter = OpenCodeAdapter()
    line = json.dumps({"type": "tool_use", "name": "Bash", "part": {}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name == "Bash"


def test_parse_tool_use_event_without_name() -> None:
    adapter = OpenCodeAdapter()
    line = json.dumps({"type": "tool_use", "part": {}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.name is None


def test_parse_step_finish_is_result() -> None:
    adapter = OpenCodeAdapter()
    line = json.dumps({"type": "step_finish", "part": {"tokens": 42, "cost": 0.01}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "result"
    # Token / cost data is captured in raw but not surfaced as fields.
    assert event.raw == {"type": "step_finish", "part": {"tokens": 42, "cost": 0.01}}


@pytest.mark.parametrize("event_type", ["step_start", "text", "reasoning", "error"])
def test_parse_message_events(event_type: str) -> None:
    adapter = OpenCodeAdapter()
    line = json.dumps({"type": event_type, "part": {}})
    event = adapter.parse_event(line)
    assert event is not None
    assert event.kind == "message"


def test_parse_unknown_event_returns_none() -> None:
    adapter = OpenCodeAdapter()
    assert adapter.parse_event(json.dumps({"type": "something_new"})) is None


def test_parse_malformed_never_raises() -> None:
    adapter = OpenCodeAdapter()
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("") is None
    assert adapter.parse_event("   \n") is None
    assert adapter.parse_event("42") is None
    assert adapter.parse_event("[1, 2, 3]") is None
    assert adapter.parse_event('"just a string"') is None
    assert adapter.parse_event("{") is None
    # No "type" key at all.
    assert adapter.parse_event(json.dumps({"part": {"name": "x"}})) is None


def test_extract_completion_signal_from_stdout() -> None:
    adapter = OpenCodeAdapter()
    stdout = "\n".join(
        [
            json.dumps({"type": "step_start", "part": {}}),
            json.dumps({"type": "tool_use", "part": {"name": "Edit"}}),
            "<promise>DONE</promise>",
        ]
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=stdout, user_signal="DONE"
        )
        is True
    )
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=stdout, user_signal="OTHER"
        )
        is False
    )


def test_extract_completion_signal_returns_false_when_stdout_missing() -> None:
    adapter = OpenCodeAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text="<promise>DONE</promise>", stdout=None, user_signal="DONE"
        )
        is False
    )


def test_install_wind_down_hook_raises_not_implemented(tmp_path) -> None:
    adapter = OpenCodeAdapter()
    with pytest.raises(NotImplementedError):
        adapter.install_wind_down_hook(tmp_path, tmp_path / "counter", 10, 2)


def test_capability_flags() -> None:
    adapter = OpenCodeAdapter()
    assert adapter.name == "opencode"
    assert adapter.counts_what == "tool_use"
    assert adapter.supports_streaming is True
    assert adapter.renders_structured_peek is False
    assert adapter.supports_soft_wind_down is False
    assert adapter.requires_full_stdout_for_completion is True


def test_satisfies_protocol() -> None:
    assert isinstance(OpenCodeAdapter(), CLIAdapter)


def test_registered_in_adapters_registry() -> None:
    selected = select_adapter(["opencode", "run"])
    assert isinstance(selected, OpenCodeAdapter)
