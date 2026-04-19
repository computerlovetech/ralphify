"""Tests for the run engine."""

import threading
import time
from unittest.mock import patch

import pytest
from helpers import (
    MOCK_RUN_COMMAND,
    MOCK_SUBPROCESS,
    drain_events,
    event_types,
    events_of_type,
    fail_proc,
    make_config,
    make_state,
    ok_proc,
    ok_run_result,
    timeout_proc,
)
from rich.console import Console

from ralphify._agent import AgentResult
from ralphify._console_emitter import ConsoleEmitter
from ralphify._events import BoundEmitter, EventType, NullEmitter, QueueEmitter
from ralphify._run_types import Command, RunStatus
from ralphify._runner import RunResult
from ralphify.engine import (
    _assemble_prompt,
    _delay_if_needed,
    _handle_control_signals,
    _run_commands,
    run_loop,
)


class TestRunLoop:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_single_iteration(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.completed == 1
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert mock_run.call_count == 1

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_multiple_iterations(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=3)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert state.completed == 3
        assert mock_run.call_count == 3

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_failed_iterations_counted(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=2)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert state.completed == 0
        assert state.failed == 2

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_stop_on_error(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=5, stop_on_error=True)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert mock_run.call_count == 1
        assert state.failed == 1

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_stop_on_error_sets_failed_status(self, mock_run, tmp_path):
        """When stop_on_error triggers, status should be FAILED, not COMPLETED."""
        config = make_config(tmp_path, max_iterations=5, stop_on_error=True)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.status == RunStatus.FAILED
        events = drain_events(q)
        stop_event = events_of_type(events, EventType.RUN_STOPPED)[0]
        assert stop_event.data["reason"] == "error"

    @patch(MOCK_SUBPROCESS, side_effect=timeout_proc)
    def test_timeout_counted(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1, timeout=5)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert state.timed_out_count == 1
        assert state.failed == 1

    @patch(MOCK_SUBPROCESS)
    def test_prompt_read_from_ralph_file(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc()
        config = make_config(tmp_path, "my prompt text", max_iterations=1, credit=False)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert mock_run.return_value.stdin.write.call_args.args[0] == "my prompt text"

    @patch(MOCK_SUBPROCESS)
    def test_log_dir_creates_files(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc(stdout_text="output\n")
        log_dir = tmp_path / "logs"
        config = make_config(tmp_path, max_iterations=2, log_dir=log_dir)
        state = make_state()

        run_loop(config, state, NullEmitter())

        log_files = sorted(log_dir.iterdir())
        assert len(log_files) == 2
        assert log_files[0].name.startswith("001_")
        assert log_files[1].name.startswith("002_")


class TestPromiseCompletionSignals:
    @patch("ralphify.engine.execute_agent")
    def test_tagged_promise_does_not_stop_by_default(
        self, mock_execute_agent, tmp_path
    ):
        """Without ``stop_on_completion_signal`` the loop must run all iterations.

        A non-streaming adapter (here ``echo`` → GenericAdapter) only sees
        promise completion when the engine elects to capture stdout, which
        in turn requires either logging or the explicit opt-in.  Skipping
        the buffer is the whole point of the gating, so
        ``state.promise_completed`` legitimately stays False here.
        """
        config = make_config(tmp_path, max_iterations=3)
        state = make_state()
        emitter = NullEmitter()
        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout=None,
        )

        run_loop(config, state, emitter)

        assert mock_execute_agent.call_count == 3
        assert state.completed == 3
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is False
        assert [
            call.kwargs["on_output_line"] for call in mock_execute_agent.call_args_list
        ] == [None, None, None]
        assert [
            call.kwargs["capture_result_text"]
            for call in mock_execute_agent.call_args_list
        ] == [True, True, True]
        # Generic adapter requires full stdout, but the user didn't opt in
        # and no log dir is set — capture should stay off to avoid
        # buffering verbose agent output.
        assert [
            call.kwargs["capture_stdout"] for call in mock_execute_agent.call_args_list
        ] == [False, False, False]

    @patch("ralphify.engine.execute_agent")
    def test_capture_stdout_off_for_streaming_adapter_without_logging(
        self, mock_execute_agent, tmp_path
    ):
        """Claude exposes ``result_text`` directly; the engine must not
        force-buffer the full stdout transcript even when the user opts
        into ``stop_on_completion_signal``."""
        config = make_config(
            tmp_path,
            agent="claude",
            max_iterations=1,
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            result_text="<promise>RALPH_PROMISE_COMPLETE</promise>",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_args.kwargs["capture_stdout"] is False
        assert state.promise_completed is True

    @patch("ralphify.engine.execute_agent")
    def test_capture_stdout_on_for_blocking_adapter_with_opt_in(
        self, mock_execute_agent, tmp_path
    ):
        """Generic / Copilot adapters need the full stdout buffer to
        scan for the promise tag — engine must opt in when the user
        opts into completion signalling."""
        config = make_config(
            tmp_path,
            max_iterations=1,
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="<promise>RALPH_PROMISE_COMPLETE</promise>\n",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_args.kwargs["capture_stdout"] is True
        assert state.promise_completed is True

    @patch("ralphify.engine.execute_agent")
    def test_capture_stdout_on_when_log_dir_set(self, mock_execute_agent, tmp_path):
        """Logging always needs the buffer regardless of completion signal."""
        log_dir = tmp_path / "logs"
        config = make_config(tmp_path, max_iterations=1, log_dir=log_dir)
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="anything\n",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_args.kwargs["capture_stdout"] is True

    @patch("ralphify.engine.execute_agent")
    def test_tagged_promise_stops_early_when_enabled(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(
            tmp_path,
            max_iterations=5,
            stop_on_completion_signal=True,
        )
        state = make_state()
        emitter = QueueEmitter()
        emitter.wants_agent_output_lines = lambda: True
        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="<promise>RALPH_PROMISE_COMPLETE</promise>\n",
        )

        run_loop(config, state, emitter)

        mock_execute_agent.assert_called_once()
        assert mock_execute_agent.call_args.kwargs["capture_result_text"] is True
        assert state.iteration == 1
        assert state.completed == 1
        assert state.failed == 0
        assert state.total == 1
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is True

        events = drain_events(emitter)
        completed_events = events_of_type(events, EventType.ITERATION_COMPLETED)
        assert len(completed_events) == 1
        stop_event = events_of_type(events, EventType.RUN_STOPPED)[0]
        assert stop_event.data["reason"] == "completed"
        assert stop_event.data["total"] == 1
        assert stop_event.data["completed"] == 1
        assert stop_event.data["failed"] == 0
        assert stop_event.data["timed_out_count"] == 0

    @patch("ralphify.engine.execute_agent")
    def test_custom_promise_text_matches_inner_tag_text(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(
            tmp_path,
            max_iterations=4,
            completion_signal="CUSTOM_DONE",
            stop_on_completion_signal=True,
        )
        state = make_state()
        emitter = QueueEmitter()
        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="<promise>CUSTOM_DONE</promise>\n",
        )

        run_loop(config, state, emitter)

        mock_execute_agent.assert_called_once()
        assert state.iteration == 1
        assert state.completed == 1
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is True

        events = drain_events(emitter)
        stop_event = events_of_type(events, EventType.RUN_STOPPED)[0]
        assert stop_event.data["reason"] == "completed"
        assert stop_event.data["total"] == 1
        assert stop_event.data["completed"] == 1

    @patch("ralphify.engine.execute_agent")
    def test_promise_tag_normalizes_inner_whitespace_before_matching(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(
            tmp_path,
            max_iterations=4,
            completion_signal="CUSTOM DONE",
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="<promise>\n  CUSTOM\tDONE  \n</promise>\n",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_count == 1
        assert state.iteration == 1
        assert state.completed == 1
        assert state.failed == 0
        assert state.total == 1
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is True

    @patch("ralphify.engine.execute_agent")
    def test_untagged_raw_text_does_not_match_completion_signal(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(
            tmp_path,
            max_iterations=3,
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            result_text="done RALPH_PROMISE_COMPLETE without promise tags",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_count == 3
        assert state.completed == 3
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is False

    @patch("ralphify.engine.execute_agent")
    def test_different_tagged_promise_text_does_not_match(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(
            tmp_path,
            max_iterations=3,
            completion_signal="CUSTOM_DONE",
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            result_text="<promise>CUSTOM_DONE_NOW</promise>",
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_count == 3
        assert state.completed == 3
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is False

    @patch("ralphify.engine.execute_agent")
    def test_structured_agents_ignore_raw_stdout_for_promise_detection(
        self, mock_execute_agent, tmp_path
    ):
        """ClaudeAdapter only looks at ``result`` events — embedded
        promise tags inside ``status`` or ``assistant`` JSON messages
        must not trigger early completion."""
        config = make_config(
            tmp_path,
            agent="claude",
            max_iterations=2,
            stop_on_completion_signal=True,
        )
        state = make_state()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            result_text="done without promise tag",
            captured_stdout='{"type":"status","message":"<promise>RALPH_PROMISE_COMPLETE</promise>"}\n',
        )

        run_loop(config, state, NullEmitter())

        assert mock_execute_agent.call_count == 2
        assert state.completed == 2
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert state.promise_completed is False

    @patch("ralphify.engine.execute_agent")
    def test_blocking_captured_stdout_is_echoed_when_peek_is_off(
        self, mock_execute_agent, tmp_path
    ):
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        emitter = QueueEmitter()

        mock_execute_agent.return_value = AgentResult(
            returncode=0,
            elapsed=0.01,
            captured_stdout="plain blocking output\n",
        )

        run_loop(config, state, emitter)

        completed_event = events_of_type(
            drain_events(emitter), EventType.ITERATION_COMPLETED
        )[0]
        assert completed_event.data["echo_stdout"] == "plain blocking output\n"


class TestRunLoopDefaults:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_runs_without_emitter(self, mock_run, tmp_path):
        """run_loop works when called without an explicit emitter (uses NullEmitter)."""
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()

        run_loop(config, state)

        assert state.completed == 1
        assert state.status == RunStatus.COMPLETED


class TestRunLoopEvents:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_events_emitted_in_order(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = drain_events(q)
        types = event_types(events)
        assert types[0] == EventType.RUN_STARTED
        assert types[-1] == EventType.RUN_STOPPED
        # Verify lifecycle ordering within the iteration
        assert types.index(EventType.ITERATION_STARTED) < types.index(
            EventType.PROMPT_ASSEMBLED
        )
        assert types.index(EventType.PROMPT_ASSEMBLED) < types.index(
            EventType.ITERATION_COMPLETED
        )
        assert types.index(EventType.ITERATION_COMPLETED) < types.index(
            EventType.RUN_STOPPED
        )

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_failure_event_emitted(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = drain_events(q)
        assert EventType.ITERATION_FAILED in event_types(events)

    @patch(MOCK_SUBPROCESS, side_effect=timeout_proc)
    def test_timeout_event_emitted(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1, timeout=5)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = drain_events(q)
        assert EventType.ITERATION_TIMED_OUT in event_types(events)

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_all_events_have_run_id(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        for event in drain_events(q):
            assert event.run_id == "test-run-001"


class TestRunStateControls:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_stop_request(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=100)
        state = make_state()

        def stop_after_first(*args, **kwargs):
            state.request_stop()
            return ok_proc(*args, **kwargs)

        mock_run.side_effect = stop_after_first

        run_loop(config, state, NullEmitter())

        assert mock_run.call_count == 1
        assert state.status == RunStatus.STOPPED

    @patch(MOCK_SUBPROCESS)
    def test_keyboard_interrupt_sets_stopped(self, mock_run, tmp_path):
        mock_run.side_effect = KeyboardInterrupt
        config = make_config(tmp_path, max_iterations=5)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.status == RunStatus.STOPPED
        events = drain_events(q)
        stop_event = events_of_type(events, EventType.RUN_STOPPED)[0]
        assert stop_event.data["reason"] == "user_requested"

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_pause_and_resume(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=3)
        state = make_state()

        call_count = 0

        def track_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                state.request_pause()

                def resume_later():
                    time.sleep(0.1)
                    state.request_resume()

                threading.Thread(target=resume_later, daemon=True).start()
            return ok_proc(*args, **kwargs)

        mock_run.side_effect = track_calls

        run_loop(config, state, NullEmitter())

        assert state.completed == 3
        assert state.status == RunStatus.COMPLETED

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_stop_while_paused(self, mock_run, tmp_path):
        config = make_config(tmp_path, max_iterations=100)
        state = make_state()

        def pause_then_stop(*args, **kwargs):
            state.request_pause()

            def stop_later():
                time.sleep(0.1)
                state.request_stop()

            threading.Thread(target=stop_later, daemon=True).start()
            return ok_proc(*args, **kwargs)

        mock_run.side_effect = pause_then_stop

        run_loop(config, state, NullEmitter())

        assert state.status == RunStatus.STOPPED
        assert mock_run.call_count == 1


class TestRalphArgs:
    @patch(MOCK_SUBPROCESS)
    def test_args_resolved_in_prompt(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc()
        config = make_config(
            tmp_path,
            "---\nargs:\n  - dir\n  - focus\n---\nResearch {{ args.dir }} focus: {{ args.focus }}",
            max_iterations=1,
            args={"dir": "./src", "focus": "perf"},
            credit=False,
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.return_value.stdin.write.call_args.args[0]
        assert call_input == "Research ./src focus: perf"

    @patch(MOCK_SUBPROCESS)
    def test_empty_args_clears_placeholders(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc()
        config = make_config(
            tmp_path,
            "Before {{ args.opt }} after",
            max_iterations=1,
            args={},
            credit=False,
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.return_value.stdin.write.call_args.args[0]
        assert call_input == "Before  after"


class TestCommandExecution:
    @patch(MOCK_SUBPROCESS)
    @patch(MOCK_RUN_COMMAND)
    def test_commands_output_injected(self, mock_run_cmd, mock_agent, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="test output\n")
        mock_agent.return_value = ok_proc()

        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: tests\n    run: uv run pytest\n---\n"
            "Results:\n\n{{ commands.tests }}",
            max_iterations=1,
            commands=[Command(name="tests", run="uv run pytest")],
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_agent.return_value.stdin.write.call_args.args[0]
        assert "test output" in call_input
        assert "{{ commands.tests }}" not in call_input

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    @patch(MOCK_RUN_COMMAND)
    def test_multiple_commands_all_executed(self, mock_run_cmd, mock_agent, tmp_path):
        """All commands in the list are executed and their outputs collected."""

        call_count = 0

        def per_command(**kwargs):
            nonlocal call_count
            call_count += 1
            name = kwargs.get("command", "")
            return ok_run_result(output=f"output-{name}")

        mock_run_cmd.side_effect = per_command

        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: tests\n    run: pytest\n"
            "  - name: lint\n    run: ruff check\n---\n"
            "{{ commands.tests }}\n{{ commands.lint }}",
            max_iterations=1,
            commands=[
                Command(name="tests", run="pytest"),
                Command(name="lint", run="ruff check"),
            ],
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        assert mock_run_cmd.call_count == 2

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    @patch(MOCK_RUN_COMMAND)
    def test_dotslash_command_uses_ralph_dir_as_cwd(
        self, mock_run_cmd, mock_agent, tmp_path
    ):
        """Commands starting with ./ run relative to the ralph directory."""
        mock_run_cmd.return_value = ok_run_result(output="ok")

        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: local\n    run: ./check.sh\n---\n"
            "{{ commands.local }}",
            max_iterations=1,
            commands=[Command(name="local", run="./check.sh")],
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        passed_cwd = mock_run_cmd.call_args.kwargs["cwd"]
        assert passed_cwd == config.ralph_dir

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    @patch(MOCK_RUN_COMMAND)
    def test_regular_command_uses_project_root_as_cwd(
        self, mock_run_cmd, mock_agent, tmp_path
    ):
        """Commands without ./ prefix run from the project root."""
        mock_run_cmd.return_value = ok_run_result(output="ok")

        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: tests\n    run: uv run pytest\n---\n"
            "{{ commands.tests }}",
            max_iterations=1,
            commands=[Command(name="tests", run="uv run pytest")],
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        passed_cwd = mock_run_cmd.call_args.kwargs["cwd"]
        assert passed_cwd == config.project_root

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    @patch(MOCK_RUN_COMMAND)
    def test_command_timeout_passed_through(self, mock_run_cmd, mock_agent, tmp_path):
        """Command timeout from frontmatter is forwarded to run_command."""
        mock_run_cmd.return_value = ok_run_result(output="ok")

        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: slow\n    run: sleep 1\n    timeout: 300\n---\n"
            "{{ commands.slow }}",
            max_iterations=1,
            commands=[Command(name="slow", run="sleep 1", timeout=300)],
        )
        state = make_state()
        run_loop(config, state, NullEmitter())

        passed_timeout = mock_run_cmd.call_args.kwargs["timeout"]
        assert passed_timeout == 300


class TestAgentCommandParsing:
    """Tests for malformed agent command handling in the engine."""

    def test_malformed_agent_command_raises_value_error(self, tmp_path):
        """shlex.split on an agent with unmatched quotes produces a clear error."""
        config = make_config(tmp_path, max_iterations=1, agent="echo 'unterminated")
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.status == RunStatus.FAILED
        events = drain_events(q)
        log_events = events_of_type(events, EventType.LOG_MESSAGE)
        assert any(
            "Invalid agent command syntax" in e.data["message"] for e in log_events
        )

    @patch(MOCK_SUBPROCESS)
    def test_agent_not_found_raises_file_not_found_error(self, mock_run, tmp_path):
        """FileNotFoundError from the agent subprocess is re-raised with a helpful message."""
        mock_run.side_effect = FileNotFoundError(
            "No such file or directory: 'nonexistent'"
        )
        config = make_config(tmp_path, max_iterations=1, agent="nonexistent")
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.status == RunStatus.FAILED
        events = drain_events(q)
        log_events = events_of_type(events, EventType.LOG_MESSAGE)
        assert any("Agent command not found" in e.data["message"] for e in log_events)


class TestRunLoopCrashHandling:
    """Tests for the broad exception handler in run_loop (engine.py lines 269-276)."""

    @patch(MOCK_SUBPROCESS)
    def test_unexpected_exception_sets_failed_status(self, mock_run, tmp_path):
        mock_run.side_effect = RuntimeError("disk full")
        config = make_config(tmp_path, max_iterations=5)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert state.status == RunStatus.FAILED

    @patch(MOCK_SUBPROCESS)
    def test_unexpected_exception_emits_log_and_stop_events(self, mock_run, tmp_path):
        mock_run.side_effect = RuntimeError("disk full")
        config = make_config(tmp_path, max_iterations=5)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = drain_events(q)
        types = event_types(events)
        assert EventType.LOG_MESSAGE in types
        assert EventType.RUN_STOPPED in types

        log_event = events_of_type(events, EventType.LOG_MESSAGE)[0]
        assert log_event.data["level"] == "error"
        assert "disk full" in log_event.data["message"]
        assert "traceback" in log_event.data

        stop_event = events_of_type(events, EventType.RUN_STOPPED)[0]
        assert stop_event.data["reason"] == "error"

    @patch(MOCK_SUBPROCESS)
    def test_unexpected_exception_only_runs_one_iteration(self, mock_run, tmp_path):
        mock_run.side_effect = RuntimeError("boom")
        config = make_config(tmp_path, max_iterations=10)
        state = make_state()

        run_loop(config, state, NullEmitter())

        assert mock_run.call_count == 1
        assert state.iteration == 1

    @patch("ralphify.engine.parse_frontmatter")
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_crash_in_prompt_assembly_handled(self, mock_run, mock_parse, tmp_path):
        mock_parse.side_effect = ValueError("corrupt YAML")
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.status == RunStatus.FAILED
        events = drain_events(q)
        log_events = events_of_type(events, EventType.LOG_MESSAGE)
        assert any("corrupt YAML" in e.data["message"] for e in log_events)


class TestDelayIfNeeded:
    def test_no_delay_when_zero(self, tmp_path):
        config = make_config(tmp_path, delay=0, max_iterations=5)
        state = make_state()
        state.iteration = 1
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        start = time.monotonic()
        _delay_if_needed(config, state, emit)
        elapsed = time.monotonic() - start

        assert elapsed < 0.1
        assert drain_events(q) == []

    def test_delay_sleeps_between_iterations(self, tmp_path):
        config = make_config(tmp_path, delay=0.15, max_iterations=5)
        state = make_state()
        state.iteration = 1
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        start = time.monotonic()
        _delay_if_needed(config, state, emit)
        elapsed = time.monotonic() - start

        assert elapsed >= 0.1
        events = drain_events(q)
        assert len(events) == 1
        assert events[0].type == EventType.LOG_MESSAGE
        assert "Waiting" in events[0].data["message"]

    def test_delay_message_uses_format_duration(self, tmp_path):
        """Delay log message should use format_duration for consistency with
        the rest of the UI — e.g. '2m 0s' instead of raw '120s'."""
        config = make_config(tmp_path, delay=120, max_iterations=5)
        state = make_state()
        state.iteration = 1
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        # Request stop immediately so we don't actually wait 120s
        state.request_stop()
        _delay_if_needed(config, state, emit)

        events = drain_events(q)
        assert len(events) == 1
        msg = events[0].data["message"]
        assert "2m 0s" in msg, (
            f"Expected formatted duration '2m 0s' in message, got: {msg!r}"
        )

    def test_no_delay_on_last_iteration(self, tmp_path):
        config = make_config(tmp_path, delay=0.5, max_iterations=3)
        state = make_state()
        state.iteration = 3  # last iteration
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        start = time.monotonic()
        _delay_if_needed(config, state, emit)
        elapsed = time.monotonic() - start

        assert elapsed < 0.1
        assert drain_events(q) == []

    def test_delay_with_unlimited_iterations(self, tmp_path):
        config = make_config(tmp_path, delay=0.15, max_iterations=None)
        state = make_state()
        state.iteration = 100
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        start = time.monotonic()
        _delay_if_needed(config, state, emit)
        elapsed = time.monotonic() - start

        assert elapsed >= 0.1

    def test_delay_exits_early_on_stop_request(self, tmp_path):
        """Stop requests during delay should be respected, not blocked
        for the full delay duration."""
        config = make_config(tmp_path, delay=5.0, max_iterations=None)
        state = make_state()
        state.iteration = 1
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        # Request stop from another thread after a short interval
        def stop_soon():
            time.sleep(0.1)
            state.request_stop()

        threading.Thread(target=stop_soon, daemon=True).start()

        start = time.monotonic()
        _delay_if_needed(config, state, emit)
        elapsed = time.monotonic() - start

        # Should exit well before the full 5s delay
        assert elapsed < 2.0


class TestHandleControlSignals:
    """Unit tests for _handle_control_signals — stop and pause logic."""

    def test_returns_true_when_no_signals(self):
        state = make_state()
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        result = _handle_control_signals(state, emit)

        assert result is True
        assert state.status == RunStatus.PENDING

    def test_returns_false_when_stop_requested(self):
        state = make_state()
        state.request_stop()
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        result = _handle_control_signals(state, emit)

        assert result is False
        assert state.status == RunStatus.STOPPED

    def test_paused_then_resumed_returns_true(self):
        state = make_state()
        state.request_pause()
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        def resume_soon():
            time.sleep(0.05)
            state.request_resume()

        threading.Thread(target=resume_soon, daemon=True).start()

        result = _handle_control_signals(state, emit)

        assert result is True
        events = drain_events(q)
        types = event_types(events)
        assert EventType.RUN_PAUSED in types
        assert EventType.RUN_RESUMED in types

    def test_paused_then_stop_returns_false(self):
        state = make_state()
        state.request_pause()
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        def stop_soon():
            time.sleep(0.05)
            state.request_stop()

        threading.Thread(target=stop_soon, daemon=True).start()

        result = _handle_control_signals(state, emit)

        assert result is False
        assert state.status == RunStatus.STOPPED
        events = drain_events(q)
        types = event_types(events)
        assert EventType.RUN_PAUSED in types
        assert EventType.RUN_RESUMED not in types

    def test_stop_detected_during_pause_poll_interval(self):
        """Stop flag set without resume event exercises the polling-loop guard.

        Normally request_stop() sets both the flag and the resume event, so
        wait_for_unpause unblocks immediately.  This test sets only the flag
        to cover the guard inside the polling loop (engine.py _wait_for_resume)
        that checks stop_requested after each poll timeout.
        """
        state = make_state()
        state.request_pause()
        q = QueueEmitter()
        emit = BoundEmitter(q, state.run_id)

        def set_stop_flag():
            time.sleep(0.01)
            state._stop_event.set()

        threading.Thread(target=set_stop_flag, daemon=True).start()

        result = _handle_control_signals(state, emit)

        assert result is False
        assert state.status == RunStatus.STOPPED


class TestRunCommands:
    """Unit tests for _run_commands — command execution and cwd resolution."""

    @patch(MOCK_RUN_COMMAND)
    def test_returns_name_to_output_mapping(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="test output")
        commands = [Command(name="tests", run="pytest")]

        result = _run_commands(
            commands, ralph_dir=tmp_path / "ralph", project_root=tmp_path, user_args={}
        )

        assert result == {"tests": "test output"}

    @patch(MOCK_RUN_COMMAND)
    def test_multiple_commands(self, mock_run_cmd, tmp_path):
        call_count = 0

        def per_command(**kwargs):
            nonlocal call_count
            call_count += 1
            return ok_run_result(output=f"out-{call_count}")

        mock_run_cmd.side_effect = per_command
        commands = [
            Command(name="a", run="cmd-a"),
            Command(name="b", run="cmd-b"),
        ]

        result = _run_commands(
            commands, ralph_dir=tmp_path / "ralph", project_root=tmp_path, user_args={}
        )

        assert len(result) == 2
        assert result["a"] == "out-1"
        assert result["b"] == "out-2"

    @patch(MOCK_RUN_COMMAND)
    def test_dotslash_uses_ralph_dir(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="ok")
        ralph_dir = tmp_path / "my-ralph"
        commands = [Command(name="local", run="./check.sh")]

        _run_commands(
            commands, ralph_dir=ralph_dir, project_root=tmp_path, user_args={}
        )

        assert mock_run_cmd.call_args.kwargs["cwd"] == ralph_dir

    @patch(MOCK_RUN_COMMAND)
    def test_regular_command_uses_project_root(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="ok")
        ralph_dir = tmp_path / "my-ralph"
        commands = [Command(name="tests", run="pytest")]

        _run_commands(
            commands, ralph_dir=ralph_dir, project_root=tmp_path, user_args={}
        )

        assert mock_run_cmd.call_args.kwargs["cwd"] == tmp_path

    @patch(MOCK_RUN_COMMAND)
    def test_timeout_passed_to_run_command(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="ok")
        commands = [Command(name="slow", run="sleep 1", timeout=300)]

        _run_commands(commands, ralph_dir=tmp_path, project_root=tmp_path, user_args={})

        assert mock_run_cmd.call_args.kwargs["timeout"] == 300

    def test_empty_commands_returns_empty_dict(self, tmp_path):
        result = _run_commands(
            [], ralph_dir=tmp_path, project_root=tmp_path, user_args={}
        )

        assert result == {}

    @patch(MOCK_RUN_COMMAND)
    def test_resolves_args_in_command_run_string(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="issue content")
        commands = [
            Command(name="issue", run="gh issue view {{ args.issue }} --json title")
        ]

        _run_commands(
            commands,
            ralph_dir=tmp_path,
            project_root=tmp_path,
            user_args={"issue": "42"},
        )

        assert (
            mock_run_cmd.call_args.kwargs["command"] == "gh issue view 42 --json title"
        )

    @patch(MOCK_RUN_COMMAND)
    def test_dotslash_detection_after_args_resolution(self, mock_run_cmd, tmp_path):
        mock_run_cmd.return_value = ok_run_result(output="ok")
        ralph_dir = tmp_path / "my-ralph"
        commands = [Command(name="check", run="./{{ args.script }}")]

        _run_commands(
            commands,
            ralph_dir=ralph_dir,
            project_root=tmp_path,
            user_args={"script": "check.sh"},
        )

        assert mock_run_cmd.call_args.kwargs["cwd"] == ralph_dir
        assert mock_run_cmd.call_args.kwargs["command"] == "./check.sh"

    @patch(MOCK_RUN_COMMAND)
    def test_arg_values_with_spaces_are_shell_quoted_in_commands(
        self, mock_run_cmd, tmp_path
    ):
        """Arg values containing spaces must be shell-quoted when substituted
        into command run strings so shlex.split treats them as single tokens."""
        mock_run_cmd.return_value = ok_run_result(output="found it")
        commands = [Command(name="search", run="grep {{ args.pattern }} src/")]

        _run_commands(
            commands,
            ralph_dir=tmp_path,
            project_root=tmp_path,
            user_args={"pattern": "hello world"},
        )

        resolved_cmd = mock_run_cmd.call_args.kwargs["command"]
        # The value must be quoted so shlex.split produces a single token
        import shlex

        tokens = shlex.split(resolved_cmd)
        assert tokens == ["grep", "hello world", "src/"]

    @patch(MOCK_RUN_COMMAND)
    def test_dotslash_detected_after_leading_whitespace_from_empty_arg(
        self, mock_run_cmd, tmp_path
    ):
        """When an optional arg placeholder before ./ resolves to empty,
        the leading whitespace must not prevent ./  detection for cwd."""
        mock_run_cmd.return_value = ok_run_result(output="ok")
        ralph_dir = tmp_path / "my-ralph"
        commands = [Command(name="check", run="{{ args.flag }} ./check.sh")]

        _run_commands(
            commands, ralph_dir=ralph_dir, project_root=tmp_path, user_args={}
        )

        assert mock_run_cmd.call_args.kwargs["cwd"] == ralph_dir

    @patch(MOCK_RUN_COMMAND)
    def test_timed_out_command_output_includes_notice(self, mock_run_cmd, tmp_path):
        """When a command times out, the output injected into the prompt
        should include a notice so the agent knows the data is incomplete."""
        mock_run_cmd.return_value = RunResult(
            returncode=None,
            output="partial output",
            timed_out=True,
        )
        commands = [Command(name="slow", run="sleep 100", timeout=5)]

        result = _run_commands(
            commands, ralph_dir=tmp_path, project_root=tmp_path, user_args={}
        )

        assert "partial output" in result["slow"]
        assert "timed out" in result["slow"].lower()

    @patch(MOCK_RUN_COMMAND)
    def test_timed_out_command_uses_formatted_duration(self, mock_run_cmd, tmp_path):
        """The timeout notice injected into command output should use
        format_duration() for consistency with the rest of the UI — e.g.
        '2m 0s' instead of raw '120s'."""
        mock_run_cmd.return_value = RunResult(
            returncode=None,
            output="partial",
            timed_out=True,
        )
        commands = [Command(name="slow", run="sleep 200", timeout=120)]

        result = _run_commands(
            commands, ralph_dir=tmp_path, project_root=tmp_path, user_args={}
        )

        assert "2m 0s" in result["slow"]

    @patch(MOCK_RUN_COMMAND, side_effect=FileNotFoundError("no-such-binary"))
    def test_command_not_found_raises_with_context(self, mock_run_cmd, tmp_path):
        commands = [Command(name="missing", run="no-such-binary --flag")]

        with pytest.raises(
            FileNotFoundError, match="Command 'missing' binary not found"
        ):
            _run_commands(
                commands, ralph_dir=tmp_path, project_root=tmp_path, user_args={}
            )

    @patch(MOCK_RUN_COMMAND, side_effect=ValueError("No closing quotation"))
    def test_command_invalid_syntax_raises_with_context(self, mock_run_cmd, tmp_path):
        """ValueError from run_command (e.g. malformed quotes) is re-raised
        with the command name so the user knows which command failed."""
        commands = [Command(name="broken", run="echo 'unterminated")]

        with pytest.raises(ValueError, match="Command 'broken' has invalid syntax"):
            _run_commands(
                commands, ralph_dir=tmp_path, project_root=tmp_path, user_args={}
            )


class TestAssemblePrompt:
    """Unit tests for _assemble_prompt — reading and resolving the prompt template."""

    def test_reads_prompt_from_ralph_file(self, tmp_path):
        config = make_config(tmp_path, "simple prompt", max_iterations=1, credit=False)
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "simple prompt"

    def test_resolves_command_placeholders(self, tmp_path):
        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: tests\n    run: pytest\n---\n"
            "Results: {{ commands.tests }}",
            max_iterations=1,
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {"tests": "all passed"})

        assert result == "Results: all passed"

    def test_resolves_args_placeholders(self, tmp_path):
        config = make_config(
            tmp_path,
            "---\nagent: echo\nargs:\n  - dir\n---\nSearch {{ args.dir }}",
            max_iterations=1,
            args={"dir": "./src"},
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "Search ./src"

    def test_clears_unresolved_placeholders(self, tmp_path):
        config = make_config(
            tmp_path,
            "Before {{ args.missing }} after",
            max_iterations=1,
            args={},
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "Before  after"

    def test_strips_html_comments(self, tmp_path):
        config = make_config(
            tmp_path, "Before <!-- hidden --> after", max_iterations=1, credit=False
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "Before  after"

    def test_credit_instruction_appended_by_default(self, tmp_path):
        config = make_config(tmp_path, "simple prompt", max_iterations=1)
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result.startswith("simple prompt")
        assert "Co-authored-by: Ralphify <noreply@ralphify.co>" in result

    def test_credit_false_omits_instruction(self, tmp_path):
        config = make_config(tmp_path, "simple prompt", max_iterations=1, credit=False)
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "simple prompt"

    def test_arg_values_not_resolved_as_command_placeholders(self, tmp_path):
        """Arg values containing {{ commands.X }} must appear literally,
        not be re-processed as command placeholders."""
        config = make_config(
            tmp_path,
            "---\nagent: echo\ncommands:\n  - name: tests\n    run: pytest\n"
            "args:\n  - filter\n---\n"
            "Filter: {{ args.filter }}\nTests: {{ commands.tests }}",
            max_iterations=1,
            args={"filter": "{{ commands.tests }}"},
            commands=[Command(name="tests", run="pytest")],
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {"tests": "5 passed"})

        assert "Filter: {{ commands.tests }}" in result
        assert "Tests: 5 passed" in result

    def test_resolves_ralph_placeholders(self, tmp_path):
        config = make_config(
            tmp_path,
            "Name: {{ ralph.name }}, Iter: {{ ralph.iteration }}, Max: {{ ralph.max_iterations }}",
            max_iterations=5,
            credit=False,
        )
        state = make_state()
        state.iteration = 3

        result = _assemble_prompt(config, state, {})

        assert result == "Name: my-ralph, Iter: 3, Max: 5"

    def test_ralph_max_iterations_empty_when_unlimited(self, tmp_path):
        config = make_config(
            tmp_path,
            "Max: {{ ralph.max_iterations }}",
            max_iterations=None,
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "Max: "

    def test_ralph_name_is_ralph_dir_name(self, tmp_path):
        config = make_config(
            tmp_path,
            "Name: {{ ralph.name }}",
            max_iterations=1,
            credit=False,
        )
        state = make_state()
        state.iteration = 1

        result = _assemble_prompt(config, state, {})

        assert result == "Name: my-ralph"


class TestCreditInLoop:
    @patch(MOCK_SUBPROCESS)
    def test_credit_instruction_in_agent_input(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc()
        config = make_config(tmp_path, "do work", max_iterations=1)
        state = make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.return_value.stdin.write.call_args.args[0]
        assert "Co-authored-by: Ralphify <noreply@ralphify.co>" in call_input

    @patch(MOCK_SUBPROCESS)
    def test_credit_false_no_trailer_in_agent_input(self, mock_run, tmp_path):
        mock_run.return_value = ok_proc()
        config = make_config(tmp_path, "do work", max_iterations=1, credit=False)
        state = make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.return_value.stdin.write.call_args.args[0]
        assert "Co-authored-by" not in call_input


class TestEchoCoordination:
    @patch(MOCK_SUBPROCESS)
    def test_no_double_print_with_log_dir_and_peek(self, mock_run, tmp_path):
        """When --log-dir is set and peek is on, agent output lines are
        rendered inside the transient Live display — they must NOT also
        be echoed as permanent output at iteration end."""
        mock_run.return_value = ok_proc(
            stdout_text="alpha\nbeta\ngamma\n",
        )
        console = Console(record=True, width=120)
        emitter = ConsoleEmitter(console)
        emitter.toggle_peek()  # force peek on

        log_dir = tmp_path / "logs"
        config = make_config(tmp_path, max_iterations=1, log_dir=log_dir)
        state = make_state()

        run_loop(config, state, emitter)

        # Lines were shown inside the transient Live display (not permanent
        # console output).  The important invariant: they must not ALSO be
        # echoed at iteration end (which would be double-printing).
        output = console.export_text()
        assert output.count("alpha") == 0
        assert output.count("beta") == 0
        assert output.count("gamma") == 0

    @patch(MOCK_SUBPROCESS)
    def test_echo_shown_when_peek_off_and_log_dir_set(self, mock_run, tmp_path):
        """When --log-dir is set and peek is off, captured output is echoed
        via the iteration-ended event so the user still sees it."""
        mock_run.return_value = ok_proc(
            stdout_text="hello\nworld\n",
        )
        console = Console(record=True, width=120)
        emitter = ConsoleEmitter(console)
        # peek is off by default for recording consoles

        log_dir = tmp_path / "logs"
        config = make_config(tmp_path, max_iterations=1, log_dir=log_dir)
        state = make_state()

        run_loop(config, state, emitter)

        output = console.export_text()
        assert "hello" in output
        assert "world" in output


class TestAgentOutputLineFiltering:
    """Tests for AGENT_OUTPUT_LINE event filtering (medium-01)."""

    @patch(MOCK_SUBPROCESS)
    def test_agent_output_line_not_emitted_when_peek_off(self, mock_run, tmp_path):
        """When peek is off, no AGENT_OUTPUT_LINE events are emitted."""
        mock_run.return_value = ok_proc(stdout_text="line1\nline2\nline3\n")
        q = QueueEmitter()
        config = make_config(tmp_path, max_iterations=1)
        state = make_state()

        run_loop(config, state, q)

        events = drain_events(q)
        output_events = events_of_type(events, EventType.AGENT_OUTPUT_LINE)
        assert output_events == []

    @patch(MOCK_SUBPROCESS)
    def test_agent_output_line_emitted_when_peek_toggled_mid_iteration(
        self, mock_run, tmp_path
    ):
        """Start with peek off, toggle on before agent runs — subsequent
        lines appear as AGENT_OUTPUT_LINE events rendered inside the
        transient Live display.  Requires log_dir so the callback path
        is taken (without log_dir the inherit path gives
        on_output_line=None and no mid-iteration toggle is possible)."""
        console = Console(record=True, width=120)
        emitter = ConsoleEmitter(console)
        # peek starts off for recording consoles

        original_proc = ok_proc(stdout_text="first\nsecond\nthird\n")

        def popen_with_toggle(*args, **kwargs):
            # Toggle peek on before the process runs — simulates user
            # pressing 'p' early in the iteration.
            emitter.toggle_peek()
            return original_proc

        mock_run.side_effect = popen_with_toggle

        log_dir = tmp_path / "logs"
        config = make_config(tmp_path, max_iterations=1, log_dir=log_dir)
        state = make_state()

        run_loop(config, state, emitter)

        # Lines are rendered inside the transient Live display (not
        # permanent console output) so they don't appear in export_text.
        # The important invariant: they must not also be echoed at
        # iteration end (which would be double-printing).
        output = console.export_text()
        assert output.count("first") == 0
        assert output.count("second") == 0
        assert output.count("third") == 0
