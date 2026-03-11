"""Tests for the extracted run engine."""

import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

from ralphify._events import Event, EventType, NullEmitter, QueueEmitter
from ralphify.engine import RunConfig, RunState, RunStatus, _format_duration, run_loop

_MOCK_SUBPROCESS = "ralphify.engine.subprocess.run"


def _make_config(tmp_path, **overrides):
    """Create a RunConfig pointing at a temp directory with PROMPT.md."""
    prompt_path = tmp_path / "PROMPT.md"
    if not prompt_path.exists():
        prompt_path.write_text("test prompt")
    defaults = dict(
        command="echo",
        args=[],
        prompt_file=str(prompt_path),
        max_iterations=1,
        project_root=tmp_path,
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


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
        (tmp_path / "PROMPT.md").write_text("test prompt")
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


class TestFormatDuration:
    def test_seconds(self):
        assert _format_duration(5.3) == "5.3s"
        assert _format_duration(0.1) == "0.1s"
        assert _format_duration(59.9) == "59.9s"

    def test_minutes(self):
        assert _format_duration(60) == "1m 0s"
        assert _format_duration(90.5) == "1m 30s"
        assert _format_duration(3599) == "59m 59s"

    def test_hours(self):
        assert _format_duration(3600) == "1h 0m"
        assert _format_duration(5400) == "1h 30m"
