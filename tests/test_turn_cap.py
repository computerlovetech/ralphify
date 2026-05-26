"""Turn-cap enforcement and soft wind-down across adapters.

Covers the behaviours that distinguish how each adapter participates in
``max_turns``:

- Streaming adapters that count tool uses (claude / codex / opencode) are
  preempted at the cap.
- Adapters that count nothing (crush) treat ``max_turns`` as a no-op.
- Adapters with no hook system (copilot / crush / opencode / generic)
  downgrade soft wind-down to hard-cap-only via ``NotImplementedError``.
- The engine emits ``ITERATION_TURN_CAPPED`` and fans the signal to hooks.
"""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch

import ralphify._agent as agent_mod
from helpers import drain_events, event_types, make_config, make_state

from ralphify._agent import (
    AgentResult,
    _atomic_write_counter,
    _count_tool_uses_post_hoc,
    _read_agent_stream,
    _run_agent_blocking,
    _setup_wind_down,
    _wrap_tool_use_with_counter,
)
from ralphify._events import EventType, QueueEmitter
from ralphify.adapters import select_adapter
from ralphify.adapters.claude import ClaudeAdapter
from ralphify.adapters.codex import CodexAdapter
from ralphify.adapters.copilot import CopilotAdapter
from ralphify.adapters.crush import CrushAdapter
from ralphify.adapters.opencode import OpenCodeAdapter
from ralphify.engine import run_loop
from ralphify.hooks import NoOpAgentHook


class _RecordingHook(NoOpAgentHook):
    """Hook that records the turn-cap callbacks it receives."""

    def __init__(self) -> None:
        self.capped: list[int] = []
        self.tool_uses: list[tuple[str, int]] = []

    def on_turn_capped(self, *, iteration: int, count: int) -> None:
        self.capped.append(count)

    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None:
        self.tool_uses.append((tool_name, count))


# ── opencode: counts_what == "tool_use" feeds the cap ──────────────────


def test_opencode_tool_use_events_count_toward_cap() -> None:
    """opencode tool_use events are counted and preempt at the cap."""
    adapter = OpenCodeAdapter()
    stream = io.StringIO(
        '{"type":"tool_use","name":"read"}\n'
        '{"type":"text","part":{"text":"thinking"}}\n'
        '{"type":"tool_use","name":"edit"}\n'
        '{"type":"tool_use","name":"bash"}\n'
    )
    seen: list[tuple[str, int]] = []

    result = _read_agent_stream(
        stream,
        deadline=None,
        on_activity=None,
        adapter=adapter,
        max_turns=2,
        on_tool_use=lambda name, count: seen.append((name, count)),
    )

    # The third tool_use is never reached: the cap fires at 2.
    assert result.turn_capped is True
    assert result.tool_use_count == 2
    assert seen == [("read", 1), ("edit", 2)]


def test_opencode_counts_without_cap_do_not_trip() -> None:
    """With no cap, opencode counts every tool use and never caps."""
    adapter = OpenCodeAdapter()
    stream = io.StringIO(
        '{"type":"tool_use","name":"read"}\n'
        '{"type":"tool_use","name":"edit"}\n'
        '{"type":"tool_use","name":"bash"}\n'
    )

    result = _read_agent_stream(
        stream, deadline=None, on_activity=None, adapter=adapter, max_turns=None
    )

    assert result.turn_capped is False
    assert result.tool_use_count == 3


# ── crush: counts_what == "none" makes max_turns a no-op ───────────────


def test_crush_max_turns_is_graceful_noop() -> None:
    """crush emits no countable events, so the cap can never fire."""
    adapter = CrushAdapter()
    stdout_lines = [
        "Did some work.\n",
        "<promise>COMPLETE</promise>\n",
    ]

    count, capped = _count_tool_uses_post_hoc(
        adapter=adapter,
        stdout_lines=stdout_lines,
        max_turns=1,
        on_tool_use=lambda name, c: None,
    )

    assert count == 0
    assert capped is False


# ── soft wind-down downgrade to hard-cap-only ──────────────────────────


def test_wind_down_downgrades_for_adapters_without_hooks(tmp_path) -> None:
    """copilot / crush / opencode / generic have no hook system → no setup."""
    for adapter in (
        CopilotAdapter(),
        CrushAdapter(),
        OpenCodeAdapter(),
        select_adapter(["echo"]),  # GenericAdapter fallback
    ):
        ctx = _setup_wind_down(
            adapter=adapter,
            max_turns=5,
            max_turns_grace=2,
            log_dir=None,
            iteration=1,
        )
        assert ctx is None, f"{adapter.name} should not set up wind-down"


def test_wind_down_setup_for_supporting_adapters() -> None:
    """claude / codex write hook config and return an env override."""
    for adapter in (ClaudeAdapter(), CodexAdapter()):
        ctx = _setup_wind_down(
            adapter=adapter,
            max_turns=5,
            max_turns_grace=2,
            log_dir=None,
            iteration=1,
        )
        assert ctx is not None, f"{adapter.name} should set up wind-down"
        try:
            assert ctx.counter_path.read_text(encoding="utf-8") == "0"
            assert ctx.env_overrides  # non-empty config-dir override
        finally:
            ctx.cleanup()
        assert not ctx.tempdir.exists()


def test_wind_down_skipped_when_grace_zero() -> None:
    """Grace of 0 opts out of the warning window even for claude."""
    ctx = _setup_wind_down(
        adapter=ClaudeAdapter(),
        max_turns=5,
        max_turns_grace=0,
        log_dir=None,
        iteration=1,
    )
    assert ctx is None


# ── engine surfaces the cap as an event + hook callback ────────────────


def test_engine_emits_turn_capped_event_and_fans_to_hook(tmp_path) -> None:
    """A capped iteration emits ITERATION_TURN_CAPPED and notifies the hook."""
    hook = _RecordingHook()
    config = make_config(tmp_path, max_turns=3, max_iterations=1, hooks=[hook])
    state = make_state()
    emitter = QueueEmitter()

    with patch("ralphify.engine.execute_agent") as mock_execute:
        mock_execute.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            tool_use_count=3,
            turn_capped=True,
        )
        run_loop(config, state, emitter)

    types = event_types(drain_events(emitter))
    assert EventType.ITERATION_TURN_CAPPED in types
    assert hook.capped == [3]
    # A capped iteration counts as completed, not failed.
    assert state.completed == 1
    assert state.failed == 0


# ── blocking path forces buffering so the post-hoc cap can count ───────


def test_blocking_path_forces_buffering_for_post_hoc_cap(tmp_path) -> None:
    """A blocking adapter with max_turns must buffer stdout to count tool uses.

    Regression: post-hoc counting re-scans ``stdout_lines``, which is
    ``None`` unless ``log_dir``/``capture_stdout`` forces buffering.  Before
    the fix, a blocking adapter (Copilot) with ``max_turns`` set but no log
    dir reported ``tool_use_count == 0`` and never set ``turn_capped`` — the
    cap was a silent no-op.  Buffering must now be forced whenever a cap is
    set on a tool-use-counting adapter.
    """
    script = (
        'print(\'{"type":"tool_use","name":"read"}\'); '
        'print(\'{"type":"tool_use","name":"edit"}\'); '
        'print(\'{"type":"tool_use","name":"bash"}\')'
    )

    result = _run_agent_blocking(
        [sys.executable, "-c", script],
        stdin_text="",
        timeout=10,
        log_dir=None,  # no log buffering
        iteration=1,
        capture_stdout=False,  # caller did not request capture
        adapter=CopilotAdapter(),
        max_turns=2,
    )

    # All three tool uses are counted post-hoc; 3 >= cap of 2 → capped.
    assert result.tool_use_count == 3
    assert result.turn_capped is True


def test_blocking_path_no_buffering_without_cap(tmp_path) -> None:
    """Without a cap, the blocking path stays unbuffered and counts nothing."""
    script = 'print(\'{"type":"tool_use","name":"read"}\')'

    result = _run_agent_blocking(
        [sys.executable, "-c", script],
        stdin_text="",
        timeout=10,
        log_dir=None,
        iteration=1,
        capture_stdout=False,
        adapter=CopilotAdapter(),
        max_turns=None,  # no cap → no forced buffering, no post-hoc count
    )

    assert result.tool_use_count == 0
    assert result.turn_capped is False


# ── counter callback isolates a raising subscriber ─────────────────────


def test_wrap_counter_swallows_subscriber_exception(tmp_path) -> None:
    """A raising on_tool_use subscriber must not crash the wrapped callback.

    Regression: the wrapped counter callback invoked the downstream
    subscriber directly, bypassing _call_safely and contradicting the
    ToolUseCallback swallow-exceptions contract.
    """
    counter_path = tmp_path / "counter"

    def boom(name: str, count: int) -> None:
        raise RuntimeError("subscriber blew up")

    wrapped = _wrap_tool_use_with_counter(boom, counter_path)
    assert wrapped is not None

    # Must not propagate, and the counter write must still have happened.
    wrapped("read", 1)
    assert counter_path.read_text(encoding="utf-8") == "1"


# ── wind-down grace is clamped below the cap ───────────────────────────


def test_wind_down_grace_clamped_below_cap() -> None:
    """grace >= max_turns is clamped so the shim threshold can't collapse to 0.

    Regression: an unclamped grace (reachable via the Python API, which
    does not validate it the way the CLI does) was passed straight to the
    shim, whose threshold ``max(cap - grace, 0)`` then fired the wind-down
    nudge on the very first tool use.
    """
    ctx = _setup_wind_down(
        adapter=ClaudeAdapter(),
        max_turns=3,
        max_turns_grace=10,  # exceeds the cap
        log_dir=None,
        iteration=1,
    )
    assert ctx is not None
    try:
        settings = json.loads(
            (ctx.tempdir / "settings.json").read_text(encoding="utf-8")
        )
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        # Tail of the shim command is "... <cap> <grace> claude".
        parts = command.split()
        assert parts[-1] == "claude"
        cap_arg, grace_arg = int(parts[-3]), int(parts[-2])
        assert cap_arg == 3
        assert grace_arg == 2  # clamped from 10 to max(cap - 1, 0)
    finally:
        ctx.cleanup()


# ── orphaned counter file is cleaned up on NotImplementedError ─────────


class _RaisingHookAdapter:
    """Minimal adapter that claims wind-down support but raises on install.

    Exercises the defensive ``NotImplementedError`` branch of
    ``_setup_wind_down`` — no shipped adapter currently reaches it, since
    non-supporting adapters bail at the capability-flag check first.
    """

    name = "raiser"
    supports_soft_wind_down = True

    def install_wind_down_hook(self, *, tempdir, counter_path, cap, grace):
        raise NotImplementedError


def test_counter_removed_when_install_raises(tmp_path) -> None:
    """The log_dir counter file must not be orphaned if install raises.

    Regression: the NotImplementedError branch removed only the tempdir,
    leaving the "0" counter file behind when it lived in log_dir.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    ctx = _setup_wind_down(
        adapter=_RaisingHookAdapter(),
        max_turns=3,
        max_turns_grace=2,
        log_dir=log_dir,
        iteration=1,
    )

    assert ctx is None
    leftover = list(log_dir.iterdir())
    assert leftover == [], f"counter file orphaned in log_dir: {leftover}"


# ── counter-write failure is logged once, not silently swallowed ───────


def test_counter_write_failure_logs_once(tmp_path, caplog) -> None:
    """A failing counter write logs one WARNING; repeats stay quiet.

    Regression: _atomic_write_counter swallowed all OSError silently, so a
    persistently-broken wind-down left no operator signal.
    """
    bad_path = tmp_path / "missing-dir" / "counter"  # parent does not exist
    original_latch = agent_mod._counter_write_failure_logged
    agent_mod._counter_write_failure_logged = False
    try:
        with caplog.at_level("WARNING", logger="ralphify._agent"):
            _atomic_write_counter(bad_path, 1)
            _atomic_write_counter(bad_path, 2)  # second failure must be quiet
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "wind-down" in warnings[0].getMessage().lower()
    finally:
        agent_mod._counter_write_failure_logged = original_latch
