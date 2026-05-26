"""Tests for the :mod:`ralphify.hooks` lifecycle hook protocol."""

from __future__ import annotations

from typing import Any

import pytest

from ralphify.hooks import (
    AgentHook,
    CombinedAgentHook,
    HOOK_EVENT_NAMES,
    NoOpAgentHook,
    ShellAgentHook,
)


class _RecordingHook(NoOpAgentHook):
    """Records every call for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def on_iteration_started(self, *, iteration: int) -> None:
        self.calls.append(("on_iteration_started", {"iteration": iteration}))

    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None:
        self.calls.append(
            (
                "on_tool_use",
                {"iteration": iteration, "tool_name": tool_name, "count": count},
            )
        )

    def on_turn_capped(self, *, iteration: int, count: int) -> None:
        self.calls.append(("on_turn_capped", {"iteration": iteration, "count": count}))


class _RaisingHook(NoOpAgentHook):
    """Always raises — used to verify fanout isolation."""

    def on_iteration_started(self, *, iteration: int) -> None:
        raise RuntimeError("boom")


def test_noop_hook_satisfies_protocol() -> None:
    hook = NoOpAgentHook()
    assert isinstance(hook, AgentHook)


def test_combined_fanout_delivers_to_all_hooks() -> None:
    h1 = _RecordingHook()
    h2 = _RecordingHook()
    combined = CombinedAgentHook([h1, h2])

    combined.on_iteration_started(iteration=3)
    combined.on_tool_use(iteration=3, tool_name="Bash", count=1)

    assert h1.calls == [
        ("on_iteration_started", {"iteration": 3}),
        ("on_tool_use", {"iteration": 3, "tool_name": "Bash", "count": 1}),
    ]
    assert h2.calls == h1.calls


def test_combined_fanout_isolates_exceptions() -> None:
    raising = _RaisingHook()
    recording = _RecordingHook()
    combined = CombinedAgentHook([raising, recording])

    combined.on_iteration_started(iteration=1)

    assert recording.calls == [("on_iteration_started", {"iteration": 1})]


def test_combined_fanout_skips_missing_methods() -> None:
    class _PartialHook:
        def on_iteration_started(self, *, iteration: int) -> None:
            pass

    combined = CombinedAgentHook([_PartialHook()])
    combined.on_turn_capped(iteration=1, count=10)


def test_shell_hook_rejects_unknown_event() -> None:
    with pytest.raises(ValueError, match="unknown hook event"):
        ShellAgentHook("on_nonexistent_event", "true")


def test_shell_hook_swallows_nonzero_exit(caplog: pytest.LogCaptureFixture) -> None:
    hook = ShellAgentHook("on_iteration_started", "false")
    with caplog.at_level("WARNING", logger="ralphify.hooks"):
        hook.on_iteration_started(iteration=1)
    assert any("exited 1" in record.message for record in caplog.records)


def test_shell_hook_swallows_missing_binary(caplog: pytest.LogCaptureFixture) -> None:
    hook = ShellAgentHook(
        "on_iteration_started", "/nonexistent/command/that/does/not/exist"
    )
    with caplog.at_level("WARNING", logger="ralphify.hooks"):
        hook.on_iteration_started(iteration=1)
    assert any("failed to start" in record.message for record in caplog.records)


def test_shell_hook_pipes_payload_to_stdin(tmp_path: Any) -> None:
    out = tmp_path / "payload.json"
    hook = ShellAgentHook(
        "on_iteration_started",
        f"sh -c 'cat > {out}'",
    )
    hook.on_iteration_started(iteration=7)
    assert out.exists()
    assert '"iteration": 7' in out.read_text()


def test_hook_event_names_cover_protocol_methods() -> None:
    # Sanity: HOOK_EVENT_NAMES should equal the AgentHook method surface.
    expected = {
        name
        for name in dir(NoOpAgentHook)
        if name.startswith("on_") and not name.startswith("_")
    }
    assert HOOK_EVENT_NAMES == expected
