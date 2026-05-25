"""Tests for the Charm Crush CLI adapter."""

from __future__ import annotations

import pytest

from ralphify.adapters import Invocation, select_adapter
from ralphify.adapters.crush import CrushAdapter


def test_matches_crush_binary_stem() -> None:
    adapter = CrushAdapter()
    assert adapter.matches(["crush"]) is True
    assert adapter.matches(["crush", "run"]) is True
    assert adapter.matches(["/opt/homebrew/bin/crush", "run"]) is True
    assert adapter.matches(["claude"]) is False
    assert adapter.matches([]) is False


def test_build_command_appends_quiet() -> None:
    adapter = CrushAdapter()
    assert adapter.build_command(["crush", "run"]) == ["crush", "run", "--quiet"]


def test_build_command_is_idempotent() -> None:
    adapter = CrushAdapter()
    once = adapter.build_command(["crush", "run"])
    twice = adapter.build_command(once)
    assert once == twice


def test_build_command_respects_existing_quiet_flags() -> None:
    adapter = CrushAdapter()
    assert adapter.build_command(["crush", "run", "--quiet"]) == [
        "crush",
        "run",
        "--quiet",
    ]
    assert adapter.build_command(["crush", "run", "-q"]) == ["crush", "run", "-q"]


def test_deliver_prompt_uses_stdin() -> None:
    adapter = CrushAdapter()
    cmd = ["crush", "run", "--quiet"]
    inv = adapter.deliver_prompt(cmd, "p")
    assert inv == Invocation(cmd, "p")
    assert inv.stdin_text == "p"


def test_parse_event_always_returns_none() -> None:
    """crush has no structured stream; nothing parses, and nothing raises."""
    adapter = CrushAdapter()
    assert adapter.parse_event('{"type": "tool_use"}') is None
    assert adapter.parse_event("plain prose line") is None
    assert adapter.parse_event("not json") is None
    assert adapter.parse_event("") is None


def test_extract_completion_signal_scans_stdout() -> None:
    adapter = CrushAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text=None,
            stdout="chatter <promise>MARKER</promise> more text",
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


def test_extract_completion_signal_ignores_result_text() -> None:
    """result_text is never populated for crush; only stdout counts."""
    adapter = CrushAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text="<promise>MARKER</promise>",
            stdout="no marker in stdout",
            user_signal="MARKER",
        )
        is False
    )


def test_extract_completion_signal_returns_false_when_stdout_missing() -> None:
    adapter = CrushAdapter()
    assert (
        adapter.extract_completion_signal(
            result_text=None, stdout=None, user_signal="MARKER"
        )
        is False
    )


def test_install_wind_down_hook_raises_not_implemented(tmp_path) -> None:
    adapter = CrushAdapter()
    with pytest.raises(NotImplementedError, match="no hook system"):
        adapter.install_wind_down_hook(tmp_path, tmp_path / "counter", 10, 2)


def test_capability_flags() -> None:
    adapter = CrushAdapter()
    assert adapter.name == "crush"
    assert adapter.counts_what == "none"
    assert adapter.supports_streaming is False
    assert adapter.renders_structured_peek is False
    assert adapter.supports_soft_wind_down is False
    assert adapter.requires_full_stdout_for_completion is True


def test_registered_in_adapters_registry() -> None:
    selected = select_adapter(["crush", "run"])
    assert isinstance(selected, CrushAdapter)
