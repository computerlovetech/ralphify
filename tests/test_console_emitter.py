"""Tests for the ConsoleEmitter rich terminal renderer."""

import threading

import pytest
from rich.console import Console

from ralphify._console_emitter import (
    FULLSCREEN_PEEK_KEY,
    NEXT_ITERATION_KEY,
    PEEK_TOGGLE_KEY,
    PREV_ITERATION_KEY,
    ConsoleEmitter,
    _FullscreenPeek,
    _IterationPanel,
    _IterationSpinner,
    _SinglePanelNavigator,
    _agent_renders_structured_peek,
    _format_run_info,
    _format_summary,
    _scrollbar_metrics,
    _shorten_path,
)
from ralphify._events import Event, EventType


def _make_event(event_type, **data):
    return Event(type=event_type, run_id="test-run", data=data)


def _capture_emitter():
    """Return a ConsoleEmitter and Console that captures output."""
    console = Console(record=True, width=120)
    emitter = ConsoleEmitter(console)
    return emitter, console


class TestEmitDispatch:
    def test_unknown_event_type_does_not_raise(self):
        emitter, _ = _capture_emitter()
        # AGENT_ACTIVITY now has a handler but _structured_agent is False
        # so it should return silently
        emitter.emit(_make_event(EventType.AGENT_ACTIVITY, raw={"type": "system"}))


class TestPeekToggle:
    def test_peek_disabled_by_default_drops_output_lines(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line="hello world",
                stream="stdout",
                iteration=1,
            )
        )
        assert "hello world" not in console.export_text()

    def test_toggle_peek_enables_rendering(self):
        emitter, console = _capture_emitter()
        assert emitter.toggle_peek() is True
        # Start an iteration so a spinner with a scroll buffer exists.
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line="visible line",
                stream="stdout",
                iteration=1,
            )
        )
        spinner = emitter._active_renderable
        assert spinner is not None
        assert any("visible line" in line.plain for line in spinner._scroll_lines)
        emitter._stop_live()

    def test_toggle_peek_off_keeps_buffering_but_hides_lines(self):
        """At the emitter layer, AGENT_OUTPUT_LINE events that reach the
        spinner are always buffered regardless of peek state — the
        visibility flag controls *rendering*, not capture.  (For raw
        agents the engine still gates forwarding via
        ``wants_agent_output_lines`` so the echo-at-end path keeps
        working; this test exercises the emitter contract directly.)"""
        emitter, console = _capture_emitter()
        emitter.toggle_peek()  # on
        assert emitter.toggle_peek() is False  # off
        # Start an iteration so a spinner exists.
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line="buffered while peek off",
                stream="stdout",
                iteration=1,
            )
        )
        spinner = emitter._active_renderable
        assert spinner is not None
        # Buffer keeps recording even with peek off…
        assert any(
            "buffered while peek off" in line.plain for line in spinner._scroll_lines
        )
        # …but visibility flag is off so the panel hides the feed.
        assert spinner._peek_visible is False
        emitter._stop_live()

    def test_toggle_peek_prints_status_banner(self):
        emitter, console = _capture_emitter()
        emitter.toggle_peek()
        output = console.export_text()
        assert (
            "peek off" in output
            or "live output on" in output
            or "live activity on" in output
        )
        emitter.toggle_peek()
        assert "peek off" in console.export_text()

    def test_concurrent_peek_writes_do_not_interleave(self):
        """Two threads hammering ``_on_agent_output_line`` while peek is on
        must produce whole, un-interleaved lines — proving the console lock
        is serialising writes across threads.
        """
        emitter, console = _capture_emitter()
        emitter.toggle_peek()  # turn peek on (console.is_terminal is False
        # in record mode, so the default is off; we flip it explicitly).
        # Start an iteration so a spinner with a scroll buffer exists.
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))

        line_a = "A" * 50
        line_b = "B" * 50
        iterations = 20

        def worker(line: str) -> None:
            for _ in range(iterations):
                emitter._on_agent_output_line(
                    {"line": line, "stream": "stdout", "iteration": 1}
                )

        threads = [
            threading.Thread(target=worker, args=(line_a,)),
            threading.Thread(target=worker, args=(line_b,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        spinner = emitter._active_renderable
        assert spinner is not None
        # Each worker adds ``iterations`` whole copies of its line to the
        # scroll buffer.  If the lock is working, both substrings appear
        # exactly that many times; any interleaving would split one of them.
        all_text = "\n".join(line.plain for line in spinner._scroll_lines)
        assert all_text.count(line_a) == iterations
        assert all_text.count(line_b) == iterations
        emitter._stop_live()

    def test_toggle_peek_survives_console_print_error(self):
        """If ``_console.print`` raises inside ``toggle_peek``, the emitter
        must remain functional for subsequent calls."""
        from unittest.mock import patch

        emitter, console = _capture_emitter()
        with patch.object(console, "print", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                emitter.toggle_peek()
        # The flag should still have been flipped (peek was off, now on).
        assert emitter._peek_enabled is True
        # Emitter is still usable — a subsequent toggle succeeds.
        assert emitter.toggle_peek() is False
        assert "peek off" in console.export_text()

    def test_peek_line_escapes_rich_markup(self):
        """Raw agent lines may contain ``[…]`` that Rich would treat as
        markup — escape so the literal text is preserved."""
        emitter, console = _capture_emitter()
        emitter.toggle_peek()
        # Start an iteration so a spinner with a scroll buffer exists.
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line="[bold red]not markup[/]",
                stream="stdout",
                iteration=1,
            )
        )
        spinner = emitter._active_renderable
        assert spinner is not None
        assert any(
            "[bold red]not markup[/]" in line.plain for line in spinner._scroll_lines
        )
        emitter._stop_live()

    def test_run_started_shows_ralph_name(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="my-ralph",
                agent="aider",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "my-ralph" in output
        assert "Running:" in output

    def test_run_started_shows_timeout(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=120,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "2m 0s" in output

    def test_run_started_shows_command_count(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=0,
                commands=3,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "3 commands" in output

    def test_run_started_singular_command(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=0,
                commands=1,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "1 command" in output
        # Should not say "1 commands"
        assert "1 commands" not in output

    def test_run_started_shows_max_iterations(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=0,
                commands=0,
                max_iterations=5,
                delay=0,
            )
        )
        output = console.export_text()
        assert "max 5 iterations" in output

    def test_run_started_no_info_line_when_no_config(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        # Should still show the ralph name header
        assert "Running:" in output
        # But no info line with dots separator
        assert "·" not in output

    def test_run_started_combines_info(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="test",
                agent="aider",
                timeout=60,
                commands=2,
                max_iterations=3,
                delay=0,
            )
        )
        output = console.export_text()
        assert "timeout 1m 0s" in output
        assert "2 commands" in output
        assert "max 3 iterations" in output
        assert "·" in output

    def test_startup_hint_shown_when_peek_on_by_default(self):
        emitter, console = _capture_emitter()
        # Force peek on (recording consoles default to off)
        emitter._peek_enabled = True
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="my-ralph",
                agent="aider",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "press p to hide" in output

    def test_startup_hint_structured_for_claude(self, monkeypatch):
        from ralphify.adapters import select_adapter

        claude_adapter = select_adapter(["claude"])
        monkeypatch.setattr(claude_adapter, "renders_structured_peek", True)
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="my-ralph",
                agent="claude --dangerously-skip-permissions",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "live activity on" in output

    def test_startup_hint_raw_for_non_claude(self):
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="my-ralph",
                agent="aider --yes",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "live output on" in output

    def test_no_startup_hint_when_peek_off(self):
        emitter, console = _capture_emitter()
        # Peek is already off by default for recording consoles, but be explicit
        emitter._peek_enabled = False
        emitter.emit(
            _make_event(
                EventType.RUN_STARTED,
                ralph_name="my-ralph",
                agent="aider",
                timeout=0,
                commands=0,
                max_iterations=None,
                delay=0,
            )
        )
        output = console.export_text()
        assert "live activity on" not in output
        assert "live output on" not in output
        assert "press p" not in output

    def test_toggle_peek_on_after_off_shows_catchup_state(self):
        """Activity that arrived while peek was off must show up when peek
        is toggled back on — that's the whole point of preserving the
        buffer across toggles instead of clearing it."""
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter._structured_agent = True
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))

        def _emit_tool(name: str, arg: str) -> None:
            emitter.emit(
                _make_event(
                    EventType.AGENT_ACTIVITY,
                    raw={
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": name,
                                    "input": {"file_path": arg}
                                    if name == "Read"
                                    else {"command": arg},
                                }
                            ]
                        },
                    },
                    iteration=1,
                )
            )

        _emit_tool("Read", "/tmp/seen-while-on.py")
        # Toggle off — buffer keeps the first event…
        emitter.toggle_peek()
        # …new activity continues to land in the buffer while peek is off.
        _emit_tool("Bash", "echo hidden-but-buffered")
        # Toggle back on — both the original and the catch-up event are
        # in the buffer, so the user sees current state, not stale state.
        emitter.toggle_peek()
        panel = emitter._active_renderable
        assert panel is not None
        plains = [line.plain for line in panel._scroll_lines]
        assert any("seen-while-on.py" in p for p in plains)
        assert any("hidden-but-buffered" in p for p in plains)
        assert panel._peek_visible is True
        emitter._stop_live()

    def test_toggle_peek_off_preserves_scroll_buffer(self):
        """Toggling peek off must NOT clear the scroll buffer — the panel
        keeps its history so the user can toggle peek back on and pick up
        where they left off (with any new activity that arrived in the
        meantime)."""
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter._structured_agent = True
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        # Emit some activity to populate the scroll buffer
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "input": {"file_path": "/tmp/foo.py"},
                            }
                        ]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert len(panel._scroll_lines) == 1
        before = list(panel._scroll_lines)
        # Toggle peek off — buffer should be preserved, visibility flipped.
        emitter.toggle_peek()
        assert panel._scroll_lines == before
        assert panel._peek_visible is False
        # Toggling peek back on restores visibility, buffer still intact.
        emitter.toggle_peek()
        assert panel._scroll_lines == before
        assert panel._peek_visible is True
        emitter._stop_live()

    def test_toggle_peek_in_live_sets_peek_message(self):
        """Toggling peek with an active Live sets a message on the renderable."""
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        # Toggle peek off — should set peek message on the spinner
        emitter.toggle_peek()
        spinner = emitter._active_renderable
        assert spinner is not None
        assert spinner._peek_message is not None
        assert "peek off" in spinner._peek_message.plain
        emitter._stop_live()

    def test_toggle_peek_without_live_prints_to_console(self):
        """Toggling peek without an active Live prints to the console."""
        emitter, console = _capture_emitter()
        # No iteration started — no Live display
        emitter.toggle_peek()
        output = console.export_text()
        assert "live output on" in output or "peek off" in output


class TestStructuredPeek:
    """Tests for the structured activity rendering (Claude agents)."""

    def _make_structured_emitter(self):
        console = Console(record=True, width=120)
        emitter = ConsoleEmitter(console)
        emitter._peek_enabled = True
        emitter._structured_agent = True
        return emitter, console

    def test_agent_output_line_early_returns_for_claude(self):
        """When structured rendering is active, raw output lines are suppressed."""
        emitter, console = self._make_structured_emitter()
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line='{"type":"system","subtype":"init"}',
                stream="stdout",
                iteration=1,
            )
        )
        assert console.export_text().strip() == ""

    def test_non_claude_agent_keeps_raw_line_rendering(self):
        """Non-claude agents still get dim raw-line rendering inside Live."""
        emitter, console = _capture_emitter()
        emitter._peek_enabled = True
        emitter._structured_agent = False
        # Start an iteration so there's a spinner with a scroll buffer
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_OUTPUT_LINE,
                line="raw agent output",
                stream="stdout",
                iteration=1,
            )
        )
        spinner = emitter._active_renderable
        assert spinner is not None
        assert any("raw agent output" in line.plain for line in spinner._scroll_lines)
        emitter._stop_live()

    def test_tool_use_scroll_line(self):
        """Tool use events are buffered inside the panel's scroll buffer."""
        emitter, console = self._make_structured_emitter()
        # Start an iteration so there's a panel
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "uv run pytest"},
                            }
                        ]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert len(panel._scroll_lines) == 1
        assert "Bash" in panel._scroll_lines[0].plain
        assert "uv run pytest" in panel._scroll_lines[0].plain
        emitter._stop_live()

    def test_assistant_text_scroll_line(self):
        """Assistant text events are buffered inside the panel's scroll buffer."""
        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "I'll fix the bug now."}]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert any("fix the bug" in line.plain for line in panel._scroll_lines)
        emitter._stop_live()

    def test_thinking_produces_scroll_lines(self):
        """Thinking blocks appear in the scroll buffer as dim italic text."""
        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "thinking", "thinking": "let me think..."}]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert len(panel._scroll_lines) == 1
        assert "let me think..." in panel._scroll_lines[0].plain
        emitter._stop_live()

    def test_rate_limit_scroll_line(self):
        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "rate_limit_event",
                    "rate_limit_info": {
                        "status": "rate_limited",
                        "resetsAt": "2026-01-01T00:00:00Z",
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert any("rate limit" in line.plain for line in panel._scroll_lines)
        assert any("rate_limited" in line.plain for line in panel._scroll_lines)
        emitter._stop_live()

    def test_unknown_type_silently_dropped(self):
        """Unknown event types are silently dropped, not errors."""
        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={"type": "completely_unknown_event"},
                iteration=1,
            )
        )
        emitter._stop_live()
        # No crash, no error output
        assert "error" not in console.export_text().lower()

    def test_parse_exception_caught_and_logged_once(self):
        """If the panel.apply() raises, the emitter logs once and drops subsequent events."""
        from unittest.mock import patch

        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))

        # Monkeypatch the panel to raise
        with patch.object(
            emitter._active_renderable, "apply", side_effect=ValueError("parse boom")
        ):
            emitter.emit(
                _make_event(
                    EventType.AGENT_ACTIVITY,
                    raw={"type": "assistant", "message": {"content": []}},
                    iteration=1,
                )
            )

        assert emitter._peek_broken is True

        # Subsequent events should be silently dropped (no crash)
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={"type": "assistant", "message": {"content": []}},
                iteration=1,
            )
        )
        # The flag stays set — only one warning was printed
        assert emitter._peek_broken is True
        emitter._stop_live()

    def test_iteration_end_resets_peek_broken(self):
        """Starting a new iteration resets the _peek_broken flag."""
        emitter, console = self._make_structured_emitter()
        emitter._peek_broken = True
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=2))
        assert emitter._peek_broken is False
        emitter._stop_live()

    def test_peek_off_still_buffers_activity(self):
        """Activity events keep flowing into the panel buffer when peek
        is off — visibility is hidden but the underlying state is up to
        date so toggling peek back on shows current activity."""
        emitter, console = self._make_structured_emitter()
        emitter._peek_enabled = False
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "echo hi"},
                            }
                        ]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        # Buffer captures activity even with peek off…
        assert len(panel._scroll_lines) == 1
        assert "Bash" in panel._scroll_lines[0].plain
        # …but the visibility flag was carried over from the disabled
        # peek state by _create_panel_unlocked.
        assert panel._peek_visible is False
        emitter._stop_live()

    def test_tool_error_scroll_line(self):
        """Tool result errors are buffered inside the panel's scroll buffer."""
        emitter, console = self._make_structured_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.AGENT_ACTIVITY,
                raw={
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "abc",
                                "is_error": True,
                                "content": "File not found: foo.py",
                            }
                        ]
                    },
                },
                iteration=1,
            )
        )
        panel = emitter._active_renderable
        assert panel is not None
        assert any("tool error" in line.plain for line in panel._scroll_lines)
        assert any("File not found" in line.plain for line in panel._scroll_lines)
        emitter._stop_live()


class TestIterationLifecycle:
    def test_iteration_started_prints_header(self):
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter._stop_live()  # clean up the Live display started by the handler
        output = console.export_text()
        assert "Iteration 1" in output

    def test_peek_lines_do_not_splice_between_iteration_header_and_spinner(self):
        """The iteration header print and spinner start are covered by a
        single lock acquisition, preventing peek lines from splicing
        between them."""
        emitter, console = _capture_emitter()
        emitter.toggle_peek()  # enable peek (off by default for recording consoles)

        # Verify the lock is held when _create_panel_unlocked executes
        lock_held_during_start = []
        original_start = emitter._create_panel_unlocked

        def instrumented_start():
            lock_held_during_start.append(emitter._console_lock.locked())
            return original_start()

        emitter._create_panel_unlocked = instrumented_start

        barrier = threading.Barrier(2, timeout=5)
        peek_marker = "SPLICE_TEST_PEEK"

        def peek_worker():
            barrier.wait()
            for _ in range(20):
                emitter._on_agent_output_line(
                    {"line": peek_marker, "stream": "stdout", "iteration": 1}
                )

        t = threading.Thread(target=peek_worker)
        t.start()
        barrier.wait()

        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        t.join()
        emitter._stop_live()

        # _create_panel_unlocked must have run while _console_lock was held
        assert lock_held_during_start == [True]

        output = console.export_text()
        lines = [line.strip() for line in output.splitlines() if line.strip()]

        # The iteration header must exist and not be contaminated by peek content
        header_indices = [i for i, line in enumerate(lines) if "Iteration 1" in line]
        assert header_indices, f"Iteration header not found in output: {lines}"
        assert peek_marker not in lines[header_indices[0]]

    @pytest.mark.parametrize(
        "event_type,detail,expected",
        [
            (EventType.ITERATION_COMPLETED, "completed (5s)", "completed (5s)"),
            (
                EventType.ITERATION_FAILED,
                "failed with exit code 1 (3s)",
                "failed with exit code 1",
            ),
            (EventType.ITERATION_TIMED_OUT, "timed out after 2m 0s", "timed out"),
        ],
    )
    def test_iteration_ended_shows_detail(self, event_type, detail, expected):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                event_type,
                iteration=1,
                detail=detail,
                log_file=None,
                result_text=None,
            )
        )
        output = console.export_text()
        assert expected in output

    def test_iteration_ended_shows_log_file(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file="/tmp/log.txt",
                result_text=None,
            )
        )
        output = console.export_text()
        assert "/tmp/log.txt" in output

    def test_log_file_with_brackets_not_corrupted(self):
        """Log file paths containing bracket patterns must not be
        swallowed by Rich markup interpretation."""
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file="/tmp/[2024-01-01]/001.log",
                result_text=None,
            )
        )
        output = console.export_text()
        assert "[2024-01-01]" in output

    def test_iteration_ended_shows_result_text(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text="All tests passed",
            )
        )
        output = console.export_text()
        assert "All tests passed" in output

    def test_result_text_renders_markdown(self):
        """Agent result text should be rendered as markdown, preserving
        structure like headers and lists."""
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text="# Summary\n\n- Item one\n- Item two",
            )
        )
        output = console.export_text()
        assert "Summary" in output
        assert "Item one" in output
        assert "Item two" in output


class TestCommandsCompleted:
    def test_shows_command_count(self):
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.COMMANDS_COMPLETED, count=3))
        output = console.export_text()
        assert "3 ran" in output

    def test_no_output_when_zero_count(self):
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.COMMANDS_COMPLETED, count=0))
        output = console.export_text()
        assert output.strip() == ""


class TestLogMessage:
    def test_info_message(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(EventType.LOG_MESSAGE, message="Waiting 5s...", level="info")
        )
        output = console.export_text()
        assert "Waiting 5s..." in output

    def test_error_message(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(EventType.LOG_MESSAGE, message="Run crashed", level="error")
        )
        output = console.export_text()
        assert "Run crashed" in output

    def test_error_with_traceback(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.LOG_MESSAGE,
                message="Run crashed",
                level="error",
                traceback="Traceback:\n  File ...",
            )
        )
        output = console.export_text()
        assert "Traceback:" in output

    def test_error_message_with_brackets_not_corrupted(self):
        """Error messages containing bracket patterns must not be
        swallowed by Rich markup interpretation."""
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.LOG_MESSAGE,
                message="Run crashed: KeyError('[bold]')",
                level="error",
            )
        )
        output = console.export_text()
        assert "[bold]" in output

    def test_info_message_with_brackets_not_corrupted(self):
        """Info messages containing bracket patterns must not be
        swallowed by Rich markup interpretation."""
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.LOG_MESSAGE,
                message="Processing [section] data",
                level="info",
            )
        )
        output = console.export_text()
        assert "[section]" in output

    def test_traceback_with_brackets_not_corrupted(self):
        """Traceback text containing bracket patterns must not be
        swallowed by Rich markup interpretation."""
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.LOG_MESSAGE,
                message="Run crashed",
                level="error",
                traceback="KeyError: '[red]missing[/red]'",
            )
        )
        output = console.export_text()
        assert "[red]missing[/red]" in output


class TestRunStopped:
    def test_completed_shows_summary(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=5,
                completed=4,
                failed=1,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        assert "5 iterations" in output
        assert "4 succeeded" in output
        assert "1 failed" in output

    def test_completed_shows_separator(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=3,
                completed=3,
                failed=0,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        assert "──" in output

    def test_completed_with_timeouts(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=3,
                completed=2,
                failed=1,
                timed_out_count=1,
            )
        )
        output = console.export_text()
        assert "1 timed out" in output
        # timed_out_count is subset of failed — only non-timeout failures shown as "failed"
        assert "failed" not in output

    def test_completed_with_mixed_failures_and_timeouts(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=5,
                completed=3,
                failed=2,
                timed_out_count=1,
            )
        )
        output = console.export_text()
        assert "3 succeeded" in output
        assert "1 failed" in output
        assert "1 timed out" in output

    def test_non_completed_reason_skips_summary(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="user_requested",
                total=2,
                completed=1,
                failed=0,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        # Non-completed runs don't print the summary line
        assert "Done:" not in output

    def test_run_stopped_stops_active_live_display(self):
        emitter, console = _capture_emitter()
        # Start a live display via iteration_started, then stop via run_stopped
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        assert emitter._live is not None
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="user_requested",
                total=1,
                completed=0,
                failed=0,
                timed_out_count=0,
            )
        )
        assert emitter._live is None

    def test_completed_all_succeeded(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=3,
                completed=3,
                failed=0,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        assert "3 succeeded" in output
        assert "failed" not in output
        assert "timed out" not in output

    def test_completed_singular_iteration(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=1,
                completed=1,
                failed=0,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        assert "1 iteration" in output
        assert "1 iterations" not in output

    def test_completed_plural_iterations(self):
        emitter, console = _capture_emitter()
        emitter.emit(
            _make_event(
                EventType.RUN_STOPPED,
                reason="completed",
                total=3,
                completed=3,
                failed=0,
                timed_out_count=0,
            )
        )
        output = console.export_text()
        assert "3 iterations" in output


class TestFormatSummary:
    def test_all_succeeded(self):
        assert _format_summary(3, 3, 0, 0) == "3 iterations — 3 succeeded"

    def test_singular_iteration(self):
        assert _format_summary(1, 1, 0, 0) == "1 iteration — 1 succeeded"

    def test_with_failures(self):
        result = _format_summary(5, 4, 1, 0)
        assert "4 succeeded" in result
        assert "1 failed" in result
        assert "timed out" not in result

    def test_with_timeouts_only(self):
        result = _format_summary(3, 2, 1, 1)
        assert "2 succeeded" in result
        assert "1 timed out" in result
        # timed_out_count is subset of failed — no separate "failed" category
        assert "failed" not in result

    def test_with_mixed_failures_and_timeouts(self):
        result = _format_summary(5, 3, 2, 1)
        assert "3 succeeded" in result
        assert "1 failed" in result
        assert "1 timed out" in result

    def test_all_failed(self):
        result = _format_summary(3, 0, 3, 0)
        assert "0 succeeded" in result
        assert "3 failed" in result


class TestFormatRunInfo:
    def test_empty_when_no_config(self):
        assert _format_run_info(timeout=0, command_count=0, max_iterations=None) == ""
        assert (
            _format_run_info(timeout=None, command_count=0, max_iterations=None) == ""
        )

    def test_timeout_only(self):
        result = _format_run_info(timeout=120, command_count=0, max_iterations=None)
        assert result == "timeout 2m 0s"

    def test_commands_only(self):
        assert (
            _format_run_info(timeout=0, command_count=3, max_iterations=None)
            == "3 commands"
        )

    def test_singular_command(self):
        assert (
            _format_run_info(timeout=0, command_count=1, max_iterations=None)
            == "1 command"
        )

    def test_max_iterations_only(self):
        assert (
            _format_run_info(timeout=0, command_count=0, max_iterations=5)
            == "max 5 iterations"
        )

    def test_singular_iteration(self):
        assert (
            _format_run_info(timeout=0, command_count=0, max_iterations=1)
            == "max 1 iteration"
        )

    def test_all_fields(self):
        result = _format_run_info(timeout=60, command_count=2, max_iterations=3)
        assert "timeout 1m 0s" in result
        assert "2 commands" in result
        assert "max 3 iterations" in result
        assert " · " in result

    def test_zero_timeout_excluded(self):
        result = _format_run_info(timeout=0, command_count=2, max_iterations=None)
        assert "timeout" not in result

    def test_negative_timeout_excluded(self):
        result = _format_run_info(timeout=-1, command_count=2, max_iterations=None)
        assert "timeout" not in result


class TestEchoOutput:
    def test_echo_does_not_tear_live_spinner(self):
        """Echo output routed through the iteration-ended event must not
        interleave with Rich Live spinner frames — Live is stopped first."""
        emitter, console = _capture_emitter()
        # Start Live via iteration start
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        assert emitter._live is not None
        # End iteration with echo data (simulates peek-off + log-dir)
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text=None,
                echo_stdout="line one\nline two\nline three\n",
                echo_stderr=None,
            )
        )
        assert emitter._live is None
        output = console.export_text()
        assert "line one" in output
        assert "line two" in output
        assert "line three" in output
        # Echo text and status line should both appear cleanly
        assert "completed (1s)" in output
        # No Rich Live spinner frame characters interleaved in the echoed text
        for char in ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"):
            for line in output.splitlines():
                if "line one" in line or "line two" in line or "line three" in line:
                    assert char not in line

    def test_echo_not_shown_when_absent(self):
        """When no echo data is present, only the status line appears."""
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text=None,
            )
        )
        output = console.export_text()
        assert "completed (1s)" in output

    def test_echo_stderr_rendered(self):
        """stderr echo output is rendered when present."""
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text=None,
                echo_stdout=None,
                echo_stderr="warning: something\n",
            )
        )
        output = console.export_text()
        assert "warning: something" in output

    def test_echo_without_trailing_newline_does_not_collide_with_status(self):
        """When echo output lacks a trailing newline, the status line must
        still start on its own line — not appended to the last echo line."""
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text=None,
                echo_stdout="partial output",
                echo_stderr=None,
            )
        )
        output = console.export_text()
        # The status line must be on its own line, not merged with echo output
        for line in output.splitlines():
            if "completed (1s)" in line:
                assert "partial output" not in line, (
                    "Status line collided with echo output on the same line"
                )


class TestIterationSpinner:
    def test_renders_elapsed_time(self):
        spinner = _IterationSpinner()
        console = Console(record=True, width=80)
        console.print(spinner)
        output = console.export_text()
        # Should contain a duration string (e.g. "0.0s")
        assert "s" in output

    def test_stop_live_is_idempotent(self):
        emitter, _ = _capture_emitter()
        # Calling _stop_live when no Live is active should not raise
        assert emitter._live is None
        emitter._stop_live()
        assert emitter._live is None

    def test_full_iteration_lifecycle_cleans_up_live(self):
        emitter, console = _capture_emitter()
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        assert emitter._live is not None
        emitter.emit(
            _make_event(
                EventType.ITERATION_COMPLETED,
                iteration=1,
                detail="completed (1s)",
                log_file=None,
                result_text=None,
            )
        )
        assert emitter._live is None


class TestIterationPanel:
    def test_panel_renders_elapsed(self):
        panel = _IterationPanel()
        console = Console(record=True, width=80)
        console.print(panel)
        output = console.export_text()
        assert "s" in output

    def test_apply_tool_use_updates_counters(self):
        panel = _IterationPanel()
        panel.apply(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/tmp/foo.py"},
                        }
                    ]
                },
            }
        )
        assert panel._tool_count == 1
        assert panel._tool_categories.get("read") == 1
        assert len(panel._scroll_lines) == 1
        assert "Read" in panel._scroll_lines[0].plain

    def test_apply_system_init_sets_model(self):
        panel = _IterationPanel()
        panel.apply({"type": "system", "subtype": "init", "model": "claude-opus-4-6"})
        assert panel._model == "claude-opus-4-6"

    def test_apply_usage_updates_tokens(self):
        panel = _IterationPanel()
        panel.apply(
            {
                "type": "assistant",
                "message": {
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 200,
                    },
                    "content": [],
                },
            }
        )
        assert panel._input_tokens == 100
        assert panel._output_tokens == 50
        assert panel._cache_read_tokens == 200

    def test_apply_unknown_type_returns_none(self):
        panel = _IterationPanel()
        assert panel.apply({"type": "totally_unknown"}) is None

    def test_format_tokens_does_not_double_count_cached_input(self):
        """The Anthropic API's input_tokens already includes cache_read_input_tokens
        as a subset.  _format_tokens must not add them again — that would inflate
        the displayed total (e.g. 1000 input + 800 cached → wrong ctx 1.8k instead
        of correct ctx 1.0k)."""
        panel = _IterationPanel()
        panel._input_tokens = 1000
        panel._cache_read_tokens = 800
        panel._output_tokens = 200
        result = panel._format_tokens()
        assert "ctx 1.0k" in result, (
            f"Expected ctx 1.0k (input_tokens already includes cache), got: {result!r}"
        )

    def test_apply_stores_scroll_lines_in_buffer(self):
        """apply() stores scroll lines in the internal buffer."""
        panel = _IterationPanel()
        panel.apply(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "ls"},
                        }
                    ]
                },
            }
        )
        assert len(panel._scroll_lines) == 1
        assert "Bash" in panel._scroll_lines[0].plain

    def test_scroll_lines_rendered_in_panel(self):
        """Scroll lines appear in the panel's rendered output."""
        panel = _IterationPanel()
        panel.add_scroll_line("[dim]🔧 Read  /tmp/foo.py[/]")
        console = Console(record=True, width=80)
        console.print(panel)
        output = console.export_text()
        assert "Read" in output
        assert "/tmp/foo.py" in output

    def test_clear_scroll_empties_buffer(self):
        panel = _IterationPanel()
        panel.add_scroll_line("[dim]line1[/]")
        panel.add_scroll_line("[dim]line2[/]")
        assert len(panel._scroll_lines) == 2
        panel.clear_scroll()
        assert len(panel._scroll_lines) == 0

    def test_peek_message_shown_when_no_scroll_lines(self):
        """Peek message is rendered when scroll buffer is empty."""
        panel = _IterationPanel()
        panel.set_peek_message("[dim]peek off[/]")
        console = Console(record=True, width=80)
        console.print(panel)
        output = console.export_text()
        assert "peek off" in output

    def test_peek_message_hidden_when_scroll_lines_present(self):
        """Peek message is NOT rendered when scroll lines are present."""
        panel = _IterationPanel()
        panel.set_peek_message("[dim]peek off[/]")
        panel.add_scroll_line("[dim]tool output[/]")
        console = Console(record=True, width=80)
        console.print(panel)
        output = console.export_text()
        assert "peek off" not in output
        assert "tool output" in output


class TestIterationSpinnerScrollLines:
    def test_scroll_lines_rendered_in_spinner(self):
        """Scroll lines appear in the spinner's rendered output."""
        spinner = _IterationSpinner()
        spinner.add_scroll_line("[dim]raw output line[/]")
        console = Console(record=True, width=80)
        console.print(spinner)
        output = console.export_text()
        assert "raw output line" in output

    def test_clear_scroll_empties_spinner_buffer(self):
        spinner = _IterationSpinner()
        spinner.add_scroll_line("[dim]line1[/]")
        assert len(spinner._scroll_lines) == 1
        spinner.clear_scroll()
        assert len(spinner._scroll_lines) == 0

    def test_peek_message_shown_in_spinner(self):
        spinner = _IterationSpinner()
        spinner.set_peek_message("[dim]live output on[/]")
        console = Console(record=True, width=80)
        console.print(spinner)
        output = console.export_text()
        assert "live output on" in output


class TestAgentRendersStructuredPeek:
    """Verify the emitter routes through :func:`select_adapter`."""

    def test_claude_adapter_reports_structured_peek(self, monkeypatch):
        from ralphify.adapters import select_adapter
        from ralphify.adapters.claude import ClaudeAdapter

        adapter = select_adapter(["claude"])
        assert isinstance(adapter, ClaudeAdapter)
        monkeypatch.setattr(adapter, "renders_structured_peek", True)
        assert _agent_renders_structured_peek("claude") is True
        assert (
            _agent_renders_structured_peek("claude --dangerously-skip-permissions")
            is True
        )
        assert _agent_renders_structured_peek("/usr/local/bin/claude -p") is True

    def test_unknown_agent_falls_back_to_generic(self):
        # conftest forces every adapter's renders_structured_peek to False;
        # the GenericAdapter fallback also reports False.
        assert _agent_renders_structured_peek("aider --yes") is False

    def test_empty_string_is_not_structured(self):
        assert _agent_renders_structured_peek("") is False

    def test_invalid_shlex_is_not_structured(self):
        assert _agent_renders_structured_peek("claude 'unterminated") is False


def _populate_buffer(spinner, count: int, prefix: str = "line") -> None:
    """Fill an IterationSpinner scroll buffer with numbered lines."""
    for i in range(count):
        spinner.add_scroll_line(f"{prefix} {i:04d}")


class TestFullscreenPeekView:
    """Unit tests for the _FullscreenPeek renderable state model."""

    def _make_view(self, count: int = 100) -> _FullscreenPeek:
        spinner = _IterationSpinner()
        _populate_buffer(spinner, count)
        return _FullscreenPeek(_SinglePanelNavigator(spinner), 1)

    def test_default_follows_tail(self):
        view = self._make_view(200)
        assert view._auto_scroll is True
        assert view._offset == 0

    def test_scroll_up_disables_auto_scroll(self):
        view = self._make_view(200)
        view._console_height = 40
        view.scroll_up(5)
        assert view._auto_scroll is False
        assert view._offset == 5

    def test_scroll_down_back_to_bottom_re_enables_follow(self):
        view = self._make_view(200)
        view._console_height = 40
        view.scroll_up(10)
        assert view._auto_scroll is False
        view.scroll_down(10)
        assert view._auto_scroll is True
        assert view._offset == 0

    def test_scroll_up_clamped_to_top(self):
        view = self._make_view(30)
        view._console_height = 40  # visible = 38 > 30, so max_offset = 0
        view.scroll_up(100)
        assert view._offset == 0

    def test_scroll_to_top_clamps_to_max_offset(self):
        view = self._make_view(500)
        view._console_height = 40  # visible = 38
        view.scroll_to_top()
        # 500 total - 38 visible = 462
        assert view._offset == 462
        assert view._auto_scroll is False

    def test_scroll_to_bottom_re_enables_follow(self):
        view = self._make_view(500)
        view._console_height = 40
        view.scroll_to_top()
        view.scroll_to_bottom()
        assert view._offset == 0
        assert view._auto_scroll is True

    def test_render_shows_newest_by_default(self):
        view = self._make_view(20)
        console = Console(record=True, width=120, height=15, force_terminal=True)
        console.print(view)
        output = console.export_text()
        # With height 15 and chrome 2, visible = 13, so the last lines
        # (0019 down to 0007) should appear.
        assert "line 0019" in output
        assert "line 0000" not in output

    def test_render_shows_top_after_scroll_to_top(self):
        view = self._make_view(100)
        console = Console(record=True, width=120, height=15, force_terminal=True)
        # First render sets _console_height.
        console.print(view)
        view.scroll_to_top()
        console2 = Console(record=True, width=120, height=15, force_terminal=True)
        console2.print(view)
        output = console2.export_text()
        assert "line 0000" in output
        assert "line 0099" not in output

    def test_render_pads_when_buffer_shorter_than_viewport(self):
        view = self._make_view(3)
        console = Console(record=True, width=120, height=20, force_terminal=True)
        console.print(view)
        output = console.export_text()
        assert "line 0000" in output
        assert "line 0002" in output
        # Footer hint should still render
        assert "exit" in output

    def test_empty_buffer_shows_waiting_message(self):
        view = _FullscreenPeek(_SinglePanelNavigator(_IterationSpinner()), 1)
        console = Console(record=True, width=120, height=15, force_terminal=True)
        console.print(view)
        assert "waiting for activity" in console.export_text()


class TestScrollbarMetrics:
    """Unit tests for _scrollbar_metrics pure calculation."""

    def test_no_scrollbar_when_buffer_fits(self):
        sb = _scrollbar_metrics(total=10, visible=20, offset=0)
        assert sb.show is False

    def test_no_scrollbar_when_exact_fit(self):
        sb = _scrollbar_metrics(total=20, visible=20, offset=0)
        assert sb.show is False

    def test_scrollbar_shown_when_buffer_exceeds_viewport(self):
        sb = _scrollbar_metrics(total=100, visible=20, offset=0)
        assert sb.show is True

    def test_thumb_at_bottom_when_offset_zero(self):
        sb = _scrollbar_metrics(total=100, visible=20, offset=0)
        assert sb.show is True
        # offset=0 means following tail; thumb should be at the bottom
        # of the track (frac=1.0 → thumb_start = track_space).
        track_space = 20 - sb.thumb_size
        assert sb.thumb_start == track_space

    def test_thumb_at_top_when_offset_at_max(self):
        total, visible = 100, 20
        max_offset = total - visible  # 80
        sb = _scrollbar_metrics(total=total, visible=visible, offset=max_offset)
        assert sb.show is True
        assert sb.thumb_start == 0

    def test_thumb_size_proportional_to_viewport(self):
        sb = _scrollbar_metrics(total=100, visible=20, offset=0)
        # thumb_size = max(1, 20*20 // 100) = 4
        assert sb.thumb_size == 4

    def test_thumb_size_minimum_one(self):
        sb = _scrollbar_metrics(total=10000, visible=10, offset=0)
        # 10*10 // 10000 = 0 → clamped to 1
        assert sb.thumb_size == 1

    def test_midpoint_offset(self):
        total, visible = 200, 40
        max_offset = total - visible  # 160
        mid_offset = max_offset // 2  # 80
        sb = _scrollbar_metrics(total=total, visible=visible, offset=mid_offset)
        assert sb.show is True
        # Thumb should be roughly in the middle of the track
        track_space = visible - sb.thumb_size
        assert 0 < sb.thumb_start < track_space

    def test_empty_buffer(self):
        sb = _scrollbar_metrics(total=0, visible=20, offset=0)
        assert sb.show is False


class TestFullscreenPeekEmitter:
    """Integration tests for fullscreen peek on ConsoleEmitter."""

    def _make_emitter_with_iteration(self, structured: bool = True):
        console = Console(record=True, width=120)
        emitter = ConsoleEmitter(console)
        emitter._peek_enabled = True
        emitter._structured_agent = structured
        emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=1))
        return emitter, console

    def test_enter_without_iteration_prints_hint(self):
        emitter, console = _capture_emitter()
        assert emitter.enter_fullscreen() is False
        assert "no iterations" in console.export_text()
        assert emitter._fullscreen_view is None

    def test_enter_with_structured_iteration_creates_view(self):
        emitter, console = self._make_emitter_with_iteration(structured=True)
        try:
            assert emitter.enter_fullscreen() is True
            assert emitter._fullscreen_view is not None
            assert emitter._fullscreen_live is not None
            assert emitter._fullscreen_view._source is emitter._active_renderable
            assert emitter._fullscreen_view.iteration_id == 1
        finally:
            emitter._stop_live()

    def test_enter_with_raw_iteration_uses_spinner(self):
        emitter, console = self._make_emitter_with_iteration(structured=False)
        try:
            assert emitter.enter_fullscreen() is True
            assert emitter._fullscreen_view is not None
            assert emitter._fullscreen_view._source is emitter._active_renderable
        finally:
            emitter._stop_live()

    def test_double_enter_is_noop(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            first = emitter._fullscreen_view
            emitter.enter_fullscreen()
            assert emitter._fullscreen_view is first
        finally:
            emitter._stop_live()

    def test_exit_restores_compact_live(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            assert emitter._live is None
            emitter.exit_fullscreen()
            assert emitter._fullscreen_view is None
            assert emitter._fullscreen_live is None
            # Compact Live is back, still pointing at the same panel.
            assert emitter._live is not None
            assert emitter._active_renderable is not None
        finally:
            emitter._stop_live()

    def test_exit_without_enter_is_noop(self):
        emitter, _ = _capture_emitter()
        emitter.exit_fullscreen()  # should not raise
        assert emitter._fullscreen_view is None

    def test_iteration_end_keeps_fullscreen_and_archives_panel(self):
        """Ending an iteration while fullscreen is active must NOT drop
        the user out of the alt screen.  The finished panel moves into
        the history ring buffer so the user can keep browsing it (and
        any future iterations) via [ / ] without leaving fullscreen."""
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            panel_before = emitter._active_renderable
            assert panel_before is not None
            emitter.emit(
                _make_event(
                    EventType.ITERATION_COMPLETED,
                    iteration=1,
                    detail="completed (1s)",
                    log_file=None,
                    result_text=None,
                )
            )
            # Fullscreen still up.
            assert emitter._fullscreen_view is not None
            assert emitter._fullscreen_live is not None
            # Active iteration cleared, but the panel lives on in history.
            assert emitter._active_renderable is None
            assert emitter._current_iteration is None
            assert emitter._iteration_history.get(1) is panel_before
            # Frozen with the right outcome — surfaced in the header.
            assert panel_before._outcome == "completed"
            assert panel_before._end is not None
            # The fullscreen view still resolves to that same panel.
            assert emitter._fullscreen_view._source is panel_before
        finally:
            emitter._stop_live()

    def test_iteration_end_status_print_deferred_during_fullscreen(self):
        """Status lines that would normally print at iteration end must
        be deferred while fullscreen is active and replayed on exit so
        the terminal scrollback eventually shows them."""
        emitter, console = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            emitter.emit(
                _make_event(
                    EventType.ITERATION_COMPLETED,
                    iteration=1,
                    detail="completed (1s)",
                    log_file=None,
                    result_text=None,
                )
            )
            # Nothing printed yet — the deferred queue is non-empty.
            assert emitter._deferred_renders, "iteration-end print should be deferred"
            assert "Iteration 1 completed" not in console.export_text()
            emitter.exit_fullscreen()
            # Replayed on exit.
            assert "Iteration 1 completed" in console.export_text()
            assert not emitter._deferred_renders
        finally:
            emitter._stop_live()

    def test_navigation_browses_archived_iterations(self):
        """[ / ] move between iterations; previous iterations stay
        browsable after they end."""
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            # Finish iter 1 inside fullscreen so it gets archived.
            emitter.enter_fullscreen()
            emitter.emit(
                _make_event(
                    EventType.ITERATION_COMPLETED,
                    iteration=1,
                    detail="completed (1s)",
                    log_file=None,
                    result_text=None,
                )
            )
            # Start iter 2 — still inside fullscreen.
            emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=2))
            view = emitter._fullscreen_view
            assert view is not None
            # We started fullscreen on iter 1 and stayed there.
            assert view.iteration_id == 1
            assert emitter.iteration_ids() == [1, 2]
            # ] moves forward to iter 2 (the live one).
            emitter.handle_key(NEXT_ITERATION_KEY)
            assert view.iteration_id == 2
            assert emitter.is_live(2) is True
            # ] again is a no-op (already on the newest).
            emitter.handle_key(NEXT_ITERATION_KEY)
            assert view.iteration_id == 2
            # [ goes back to iter 1.
            emitter.handle_key(PREV_ITERATION_KEY)
            assert view.iteration_id == 1
            # [ again is a no-op (already on the oldest).
            emitter.handle_key(PREV_ITERATION_KEY)
            assert view.iteration_id == 1
        finally:
            emitter._stop_live()

    def test_history_eviction_protects_viewed_iteration(self):
        """When more than _MAX_HISTORY_ITERATIONS finish during a
        fullscreen session, the iteration the user is viewing must
        survive — eviction skips it and drops the next-oldest instead."""
        from ralphify._console_emitter import _MAX_HISTORY_ITERATIONS

        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            # We're parked on iter 1 in fullscreen; finish enough
            # iterations after it that iter 1 would normally be evicted.
            for i in range(2, _MAX_HISTORY_ITERATIONS + 5):
                emitter.emit(
                    _make_event(
                        EventType.ITERATION_COMPLETED,
                        iteration=i - 1,
                        detail="completed (1s)",
                        log_file=None,
                        result_text=None,
                    )
                ) if i > 2 else None
                emitter.emit(_make_event(EventType.ITERATION_STARTED, iteration=i))
            assert 1 in emitter._iteration_history
            assert len(emitter._iteration_order) <= _MAX_HISTORY_ITERATIONS
        finally:
            emitter._stop_live()

    def test_activity_updates_buffer_while_fullscreen(self):
        """Agent activity events must keep populating the underlying
        panel while the user is inside fullscreen peek — so when they
        exit (or use follow mode) they see the latest state."""
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            panel = emitter._fullscreen_view._source
            assert isinstance(panel, _IterationPanel)
            before = len(panel._scroll_lines)
            emitter.emit(
                _make_event(
                    EventType.AGENT_ACTIVITY,
                    raw={
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Read",
                                    "input": {"file_path": "/tmp/x.py"},
                                }
                            ]
                        },
                    },
                    iteration=1,
                )
            )
            assert len(panel._scroll_lines) == before + 1
        finally:
            emitter._stop_live()

    def test_handle_key_p_toggles_compact_peek(self):
        emitter, _ = _capture_emitter()
        emitter.handle_key(PEEK_TOGGLE_KEY)
        assert emitter._peek_enabled is True
        emitter.handle_key(PEEK_TOGGLE_KEY)
        assert emitter._peek_enabled is False

    def test_handle_key_shift_p_enters_fullscreen(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.handle_key(FULLSCREEN_PEEK_KEY)
            assert emitter._fullscreen_view is not None
        finally:
            emitter._stop_live()

    def test_handle_key_shift_p_exits_when_active(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.handle_key(FULLSCREEN_PEEK_KEY)
            assert emitter._fullscreen_view is not None
            emitter.handle_key(FULLSCREEN_PEEK_KEY)
            assert emitter._fullscreen_view is None
        finally:
            emitter._stop_live()

    def test_handle_key_q_exits_fullscreen(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            emitter.handle_key("q")
            assert emitter._fullscreen_view is None
        finally:
            emitter._stop_live()

    def test_handle_key_scroll_keys_move_offset(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            panel = emitter._active_renderable
            assert panel is not None
            _populate_buffer(panel, 500)
            emitter.enter_fullscreen()
            view = emitter._fullscreen_view
            assert view is not None
            view._console_height = 40

            assert view._offset == 0
            emitter.handle_key("k")
            assert view._offset == 1
            emitter.handle_key("j")
            assert view._offset == 0

            emitter.handle_key("b")  # page up
            assert view._offset > 0
            prev = view._offset
            emitter.handle_key(" ")  # page down
            assert view._offset < prev

            emitter.handle_key("g")  # top
            assert view._auto_scroll is False
            emitter.handle_key("G")  # bottom
            assert view._auto_scroll is True
            assert view._offset == 0
        finally:
            emitter._stop_live()

    def test_handle_key_unknown_key_in_fullscreen_ignored(self):
        emitter, _ = self._make_emitter_with_iteration(structured=True)
        try:
            emitter.enter_fullscreen()
            # Should not raise or exit
            emitter.handle_key("z")
            assert emitter._fullscreen_view is not None
        finally:
            emitter._stop_live()


class TestShortenPath:
    def test_absolute_path_no_double_slash(self):
        """Absolute paths outside $HOME should produce '/…/' not '//…/'."""
        path = "/usr/local/lib/python3.14/site-packages/something/file.py"
        result = _shorten_path(path, max_len=30)
        assert not result.startswith("//"), f"Double slash in shortened path: {result}"
        assert result.startswith("/"), f"Should keep leading slash: {result}"
