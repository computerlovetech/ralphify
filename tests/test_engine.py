"""Tests for the extracted run engine."""

import subprocess
import threading
import time
from dataclasses import replace
from unittest.mock import patch

from ralphify._events import EventType, NullEmitter, QueueEmitter
from ralphify._run_types import RunConfig, RunState, RunStatus
from ralphify.engine import _merge_primitives, _resolve_prompt_dir, run_loop

_MOCK_SUBPROCESS = "ralphify._agent.subprocess.run"


def _make_config(tmp_path, **overrides):
    """Create a RunConfig pointing at a temp directory with RALPH.md."""
    prompt_path = tmp_path / "RALPH.md"
    if not prompt_path.exists():
        prompt_path.write_text("test prompt")
    config = RunConfig(
        command="echo",
        args=[],
        prompt_file=str(prompt_path),
        max_iterations=1,
        project_root=tmp_path,
    )
    return replace(config, **overrides) if overrides else config


def _make_state():
    return RunState(run_id="test-run-001")


def _ok(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=0)


def _fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=1)


class TestRunLoop:
    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_single_iteration(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=1)
        state = _make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        assert state.completed == 1
        assert state.failed == 0
        assert state.status == RunStatus.COMPLETED
        assert mock_run.call_count == 1

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_multiple_iterations(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=3)
        state = _make_state()

        run_loop(config, state, NullEmitter())

        assert state.completed == 3
        assert mock_run.call_count == 3

    @patch(_MOCK_SUBPROCESS, side_effect=_fail)
    def test_failed_iterations_counted(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=2)
        state = _make_state()

        run_loop(config, state, NullEmitter())

        assert state.completed == 0
        assert state.failed == 2

    @patch(_MOCK_SUBPROCESS, side_effect=_fail)
    def test_stop_on_error(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=5, stop_on_error=True)
        state = _make_state()

        run_loop(config, state, NullEmitter())

        assert mock_run.call_count == 1
        assert state.failed == 1

    @patch(_MOCK_SUBPROCESS)
    def test_timeout_counted(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=5)
        config = _make_config(tmp_path, max_iterations=1, timeout=5)
        state = _make_state()

        run_loop(config, state, NullEmitter())

        assert state.timed_out == 1
        assert state.failed == 1

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_prompt_text_overrides_file(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=1, prompt_text="ad-hoc")
        state = _make_state()

        run_loop(config, state, NullEmitter())

        assert mock_run.call_args.kwargs["input"] == "ad-hoc"

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_log_dir_creates_files(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="output\n", stderr=""
        )
        log_dir = tmp_path / "logs"
        config = _make_config(tmp_path, max_iterations=2, log_dir=str(log_dir))
        state = _make_state()

        run_loop(config, state, NullEmitter())

        log_files = sorted(log_dir.iterdir())
        assert len(log_files) == 2
        assert log_files[0].name.startswith("001_")
        assert log_files[1].name.startswith("002_")


class TestRunLoopEvents:
    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_events_emitted_in_order(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=1)
        state = _make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = []
        while not q.queue.empty():
            events.append(q.queue.get())

        types = [e.type for e in events]
        assert types[0] == EventType.RUN_STARTED
        assert EventType.ITERATION_STARTED in types
        assert EventType.PROMPT_ASSEMBLED in types
        assert EventType.ITERATION_COMPLETED in types
        assert types[-1] == EventType.RUN_STOPPED

    @patch(_MOCK_SUBPROCESS, side_effect=_fail)
    def test_failure_event_emitted(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=1)
        state = _make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = []
        while not q.queue.empty():
            events.append(q.queue.get())

        types = [e.type for e in events]
        assert EventType.ITERATION_FAILED in types

    @patch(_MOCK_SUBPROCESS)
    def test_timeout_event_emitted(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=5)
        config = _make_config(tmp_path, max_iterations=1, timeout=5)
        state = _make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        events = []
        while not q.queue.empty():
            events.append(q.queue.get())

        types = [e.type for e in events]
        assert EventType.ITERATION_TIMED_OUT in types

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_all_events_have_run_id(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=1)
        state = _make_state()
        q = QueueEmitter()

        run_loop(config, state, q)

        while not q.queue.empty():
            event = q.queue.get()
            assert event.run_id == "test-run-001"


class TestRunStateControls:
    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_stop_request(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=100)
        state = _make_state()

        # Request stop before starting (will stop at first iteration boundary)
        def stop_after_first(*args, **kwargs):
            state.request_stop()
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = stop_after_first

        run_loop(config, state, NullEmitter())

        assert mock_run.call_count == 1
        assert state.status == RunStatus.STOPPED

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_pause_and_resume(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=3)
        state = _make_state()

        call_count = 0

        def track_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Pause after first iteration, resume shortly after
                state.request_pause()

                def resume_later():
                    time.sleep(0.1)
                    state.request_resume()

                threading.Thread(target=resume_later, daemon=True).start()
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = track_calls

        run_loop(config, state, NullEmitter())

        assert state.completed == 3
        assert state.status == RunStatus.COMPLETED

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_reload_rediscovers_primitives(self, mock_run, tmp_path):
        (tmp_path / "RALPH.md").write_text("test prompt")
        config = _make_config(tmp_path, max_iterations=2)
        state = _make_state()
        q = QueueEmitter()

        call_count = 0

        def request_reload_on_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                state.request_reload()
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = request_reload_on_first

        run_loop(config, state, q)

        events = []
        while not q.queue.empty():
            events.append(q.queue.get())

        types = [e.type for e in events]
        assert EventType.PRIMITIVES_RELOADED in types

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_stop_while_paused(self, mock_run, tmp_path):
        config = _make_config(tmp_path, max_iterations=100)
        state = _make_state()

        def pause_then_stop(*args, **kwargs):
            state.request_pause()

            def stop_later():
                time.sleep(0.1)
                state.request_stop()

            threading.Thread(target=stop_later, daemon=True).start()
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = pause_then_stop

        run_loop(config, state, NullEmitter())

        assert state.status == RunStatus.STOPPED
        assert mock_run.call_count == 1


class TestPromptLocalPrimitives:
    """Tests for prompt-scoped primitive discovery and merge logic."""

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_prompt_local_primitives_merged(self, mock_run, tmp_path):
        """Both global and local primitives are discovered."""
        # Global instruction
        gi = tmp_path / ".ralphify" / "instructions" / "global-style"
        gi.mkdir(parents=True)
        (gi / "INSTRUCTION.md").write_text("---\n---\nGlobal style.")

        # Named prompt
        prompt_dir = tmp_path / ".ralphify" / "ralphs" / "ui"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "RALPH.md").write_text("---\n---\nBuild the UI.")

        # Local instruction
        li = prompt_dir / "instructions" / "focus"
        li.mkdir(parents=True)
        (li / "INSTRUCTION.md").write_text("---\n---\nFocus on components.")

        config = _make_config(
            tmp_path,
            prompt_file=str(prompt_dir / "RALPH.md"),
            prompt_name="ui",
            max_iterations=1,
        )
        state = _make_state()
        run_loop(config, state, NullEmitter())

        # Agent should have been called with both instructions resolved
        call_input = mock_run.call_args.kwargs["input"]
        assert "Global style." in call_input
        assert "Focus on components." in call_input

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_prompt_local_overrides_global(self, mock_run, tmp_path):
        """A prompt-local primitive with the same name replaces the global one."""
        # Global instruction
        gi = tmp_path / ".ralphify" / "instructions" / "style"
        gi.mkdir(parents=True)
        (gi / "INSTRUCTION.md").write_text("---\n---\nGlobal style rules.")

        # Named prompt
        prompt_dir = tmp_path / ".ralphify" / "ralphs" / "ui"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "RALPH.md").write_text("---\n---\nBuild the UI.")

        # Local instruction with SAME name
        li = prompt_dir / "instructions" / "style"
        li.mkdir(parents=True)
        (li / "INSTRUCTION.md").write_text("---\n---\nLocal style rules.")

        config = _make_config(
            tmp_path,
            prompt_file=str(prompt_dir / "RALPH.md"),
            prompt_name="ui",
            max_iterations=1,
        )
        state = _make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.call_args.kwargs["input"]
        assert "Local style rules." in call_input
        assert "Global style rules." not in call_input

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_adhoc_prompt_only_globals(self, mock_run, tmp_path):
        """Ad-hoc prompt text (-p) should not trigger local discovery."""
        # Global instruction
        gi = tmp_path / ".ralphify" / "instructions" / "style"
        gi.mkdir(parents=True)
        (gi / "INSTRUCTION.md").write_text("---\n---\nGlobal style.")

        config = _make_config(
            tmp_path,
            prompt_text="ad-hoc prompt",
            prompt_name=None,
            max_iterations=1,
        )
        state = _make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.call_args.kwargs["input"]
        assert "Global style." in call_input

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_disabled_local_suppresses_global(self, mock_run, tmp_path):
        """A disabled local primitive with the same name hides the global one."""
        # Global instruction (enabled)
        gi = tmp_path / ".ralphify" / "instructions" / "style"
        gi.mkdir(parents=True)
        (gi / "INSTRUCTION.md").write_text("---\n---\nGlobal style.")

        # Named prompt
        prompt_dir = tmp_path / ".ralphify" / "ralphs" / "ui"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "RALPH.md").write_text("---\n---\nBuild the UI.")

        # Local instruction: same name, disabled
        li = prompt_dir / "instructions" / "style"
        li.mkdir(parents=True)
        (li / "INSTRUCTION.md").write_text("---\nenabled: false\n---\nLocal style.")

        config = _make_config(
            tmp_path,
            prompt_file=str(prompt_dir / "RALPH.md"),
            prompt_name="ui",
            max_iterations=1,
        )
        state = _make_state()
        run_loop(config, state, NullEmitter())

        call_input = mock_run.call_args.kwargs["input"]
        assert "Global style." not in call_input
        assert "Local style." not in call_input

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_reload_rediscovers_local(self, mock_run, tmp_path):
        """Reload should re-discover prompt-local primitives."""
        # Named prompt
        prompt_dir = tmp_path / ".ralphify" / "ralphs" / "ui"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "RALPH.md").write_text("---\n---\nBuild the UI.")

        config = _make_config(
            tmp_path,
            prompt_file=str(prompt_dir / "RALPH.md"),
            prompt_name="ui",
            max_iterations=2,
        )
        state = _make_state()
        q = QueueEmitter()

        call_count = 0

        def add_local_on_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Add a local instruction and request reload
                li = prompt_dir / "instructions" / "new-focus"
                li.mkdir(parents=True)
                (li / "INSTRUCTION.md").write_text("---\n---\nNew focus.")
                state.request_reload()
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = add_local_on_first

        run_loop(config, state, q)

        events = []
        while not q.queue.empty():
            events.append(q.queue.get())

        types = [e.type for e in events]
        assert EventType.PRIMITIVES_RELOADED in types

        # Second call should include the new instruction
        second_call_input = mock_run.call_args.kwargs["input"]
        assert "New focus." in second_call_input


class TestMergePrimitives:
    """Unit tests for _merge_primitives helper."""

    def test_local_wins_on_name_conflict(self):
        from ralphify.instructions import Instruction
        from pathlib import Path

        global_list = [
            Instruction(name="style", path=Path("/g/style"), content="Global."),
            Instruction(name="other", path=Path("/g/other"), content="Other."),
        ]
        local_list = [
            Instruction(name="style", path=Path("/l/style"), content="Local."),
        ]
        merged = _merge_primitives(global_list, local_list)
        assert len(merged) == 2
        by_name = {p.name: p for p in merged}
        assert by_name["style"].content == "Local."
        assert by_name["other"].content == "Other."

    def test_sorted_by_name(self):
        from ralphify.instructions import Instruction
        from pathlib import Path

        global_list = [
            Instruction(name="zebra", path=Path("/g/z"), content="Z."),
        ]
        local_list = [
            Instruction(name="alpha", path=Path("/l/a"), content="A."),
        ]
        merged = _merge_primitives(global_list, local_list)
        assert [p.name for p in merged] == ["alpha", "zebra"]

    def test_empty_lists(self):
        assert _merge_primitives([], []) == []


class TestResolvePromptDir:
    """Unit tests for _resolve_prompt_dir helper."""

    def test_named_prompt_returns_parent(self):
        from pathlib import Path
        config = RunConfig(
            command="echo", args=[],
            prompt_file="/project/.ralphify/ralphs/ui/RALPH.md",
            prompt_name="ui",
        )
        result = _resolve_prompt_dir(config)
        assert result == Path("/project/.ralphify/ralphs/ui")

    def test_adhoc_text_returns_none(self):
        config = RunConfig(
            command="echo", args=[],
            prompt_file="RALPH.md",
            prompt_text="ad-hoc",
            prompt_name="ui",
        )
        assert _resolve_prompt_dir(config) is None

    def test_no_prompt_name_returns_none(self):
        config = RunConfig(
            command="echo", args=[],
            prompt_file="RALPH.md",
        )
        assert _resolve_prompt_dir(config) is None
