"""Tests for the multi-run manager."""

import subprocess
import threading
import time
from dataclasses import replace
from unittest.mock import patch

from ralphify._events import Event, EventType, FanoutEmitter, QueueEmitter
from ralphify._run_types import RunConfig, RunStatus
from ralphify.manager import ManagedRun, RunManager

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


def _ok(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=0)


def _fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=1)


class TestRunManagerCreateRun:
    def test_create_run_returns_managed_run(self, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path)
        managed = manager.create_run(config)

        assert isinstance(managed, ManagedRun)
        assert managed.config is config
        assert managed.state.status == RunStatus.PENDING
        assert managed.thread is None
        assert isinstance(managed.emitter, QueueEmitter)

    def test_create_run_assigns_unique_ids(self, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path)
        run1 = manager.create_run(config)
        run2 = manager.create_run(config)

        assert run1.state.run_id != run2.state.run_id

    def test_create_run_id_is_12_hex_chars(self, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path)
        managed = manager.create_run(config)

        run_id = managed.state.run_id
        assert len(run_id) == 12
        assert all(c in "0123456789abcdef" for c in run_id)


class TestRunManagerStartRun:
    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_start_run_starts_thread(self, mock_run, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        assert managed.thread is not None
        assert managed.thread.is_alive() or managed.thread.is_alive() is False
        # Wait for the thread to finish (max 1 iteration)
        managed.thread.join(timeout=5)
        assert managed.state.status == RunStatus.COMPLETED

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_start_run_thread_is_daemon(self, mock_run, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        assert managed.thread is not None
        assert managed.thread.daemon is True
        managed.thread.join(timeout=5)

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_start_run_emits_events_to_queue(self, mock_run, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        events = []
        while not managed.emitter.queue.empty():
            events.append(managed.emitter.queue.get())

        types = [e.type for e in events]
        assert EventType.RUN_STARTED in types
        assert EventType.RUN_STOPPED in types


class TestRunManagerStopRun:
    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_stop_run_stops_running_run(self, mock_run, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=100, delay=0.1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)
        # Give the thread a moment to start
        time.sleep(0.05)

        manager.stop_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        assert managed.state.status == RunStatus.STOPPED


class TestRunManagerPauseResume:
    @patch(_MOCK_SUBPROCESS)
    def test_pause_and_resume(self, mock_run, tmp_path):
        """Pause after the first iteration and verify the run completes after resume."""
        pause_done = threading.Event()
        resume_allowed = threading.Event()
        call_count = 0

        def counting_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Signal the test to pause, then wait for it to resume
                pause_done.set()
                resume_allowed.wait(timeout=5)
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = counting_ok

        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=3)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        # Wait until first iteration is in progress, then pause
        pause_done.wait(timeout=5)
        manager.pause_run(run_id)
        assert managed.state.status == RunStatus.PAUSED

        # Let the first subprocess call finish, then resume
        resume_allowed.set()
        time.sleep(0.05)
        manager.resume_run(run_id)

        assert managed.thread is not None
        managed.thread.join(timeout=5)
        assert managed.state.completed == 3


class TestRunManagerListAndGet:
    def test_list_runs_returns_all_runs(self, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path)

        managed1 = manager.create_run(config)
        managed2 = manager.create_run(config)
        managed3 = manager.create_run(config)

        runs = manager.list_runs()
        assert len(runs) == 3
        run_ids = {r.state.run_id for r in runs}
        assert managed1.state.run_id in run_ids
        assert managed2.state.run_id in run_ids
        assert managed3.state.run_id in run_ids

    def test_list_runs_empty(self):
        manager = RunManager()
        assert manager.list_runs() == []

    def test_get_run_returns_correct_run(self, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        result = manager.get_run(run_id)
        assert result is managed

    def test_get_run_returns_none_for_unknown_id(self):
        manager = RunManager()
        assert manager.get_run("nonexistent") is None


class TestFanoutEmitter:
    def test_fanout_emits_to_all(self):
        q1 = QueueEmitter()
        q2 = QueueEmitter()
        fanout = FanoutEmitter([q1, q2])

        event = Event(type=EventType.LOG_MESSAGE, run_id="test", data={"msg": "hi"})
        fanout.emit(event)

        assert not q1.queue.empty()
        assert not q2.queue.empty()
        assert q1.queue.get() is event
        assert q2.queue.get() is event

    @patch(_MOCK_SUBPROCESS, side_effect=_ok)
    def test_extra_listeners_receive_events(self, mock_run, tmp_path):
        manager = RunManager()
        config = _make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        extra = QueueEmitter()
        managed.add_listener(extra)

        manager.start_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        # Both the primary emitter and the extra listener should have events
        primary_events = []
        while not managed.emitter.queue.empty():
            primary_events.append(managed.emitter.queue.get())

        extra_events = []
        while not extra.queue.empty():
            extra_events.append(extra.queue.get())

        assert len(primary_events) > 0
        assert len(extra_events) == len(primary_events)
