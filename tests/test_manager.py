"""Tests for the multi-run manager."""

import threading
import time
from unittest.mock import patch

import pytest

from helpers import MOCK_SUBPROCESS, drain_events, event_types, make_config, ok_proc

from ralphify._events import EventType, FanoutEmitter, QueueEmitter
from ralphify._run_types import RUN_ID_LENGTH, RunResult, RunStatus
from ralphify.manager import ManagedRun, RunManager


def _returns_without_blocking(fn, timeout=2.0):
    """Run *fn* in a watchdog thread; fail if it doesn't return in *timeout*.

    Lets us assert the wait helpers never block on empty/unknown run_ids
    with ``timeout=None`` (the infinite-hang regression) without risking a
    hung test run if the guard is ever removed.
    """
    box = {}
    thread = threading.Thread(target=lambda: box.update(result=fn()), daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "wait helper blocked instead of returning"
    return box["result"]


class TestRunManagerCreateRun:
    def test_create_run_returns_managed_run(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)
        managed = manager.create_run(config)

        assert isinstance(managed, ManagedRun)
        assert managed.config is config
        assert managed.state.status == RunStatus.PENDING
        assert managed.thread is None
        assert isinstance(managed.emitter, QueueEmitter)

    def test_create_run_assigns_unique_ids(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)
        run1 = manager.create_run(config)
        run2 = manager.create_run(config)

        assert run1.state.run_id != run2.state.run_id

    def test_create_run_id_is_12_hex_chars(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)
        managed = manager.create_run(config)

        run_id = managed.state.run_id
        assert len(run_id) == RUN_ID_LENGTH
        assert all(c in "0123456789abcdef" for c in run_id)


class TestRunManagerStartRun:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_start_run_starts_thread(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        assert managed.thread is not None
        managed.thread.join(timeout=5)
        assert managed.state.status == RunStatus.COMPLETED

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_start_run_thread_is_daemon(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        assert managed.thread is not None
        assert managed.thread.daemon is True
        managed.thread.join(timeout=5)

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_start_run_emits_events_to_queue(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        events = drain_events(managed.emitter)
        types = event_types(events)
        assert EventType.RUN_STARTED in types
        assert EventType.RUN_STOPPED in types


class TestRunManagerStartRunGuards:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_start_run_raises_on_double_start(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)
        with pytest.raises(RuntimeError, match="already been started"):
            manager.start_run(run_id)

        assert managed.thread is not None
        managed.thread.join(timeout=5)


class TestRunManagerInvalidRunId:
    def test_start_run_raises_key_error_for_unknown_id(self):
        manager = RunManager()
        with pytest.raises(KeyError, match="No run with ID 'nonexistent'"):
            manager.start_run("nonexistent")

    def test_stop_run_raises_key_error_for_unknown_id(self):
        manager = RunManager()
        with pytest.raises(KeyError, match="No run with ID 'nonexistent'"):
            manager.stop_run("nonexistent")

    def test_pause_run_raises_key_error_for_unknown_id(self):
        manager = RunManager()
        with pytest.raises(KeyError, match="No run with ID 'nonexistent'"):
            manager.pause_run("nonexistent")

    def test_resume_run_raises_key_error_for_unknown_id(self):
        manager = RunManager()
        with pytest.raises(KeyError, match="No run with ID 'nonexistent'"):
            manager.resume_run("nonexistent")


class TestRunManagerStopRun:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_stop_run_stops_running_run(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=100, delay=0.1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)
        time.sleep(0.05)

        manager.stop_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        assert managed.state.status == RunStatus.STOPPED


class TestRunManagerPauseResume:
    @patch(MOCK_SUBPROCESS)
    def test_pause_and_resume(self, mock_run, tmp_path):
        pause_done = threading.Event()
        resume_allowed = threading.Event()
        call_count = 0

        def counting_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pause_done.set()
                resume_allowed.wait(timeout=5)
            return ok_proc(*args, **kwargs)

        mock_run.side_effect = counting_ok

        manager = RunManager()
        config = make_config(tmp_path, max_iterations=3)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        manager.start_run(run_id)

        pause_done.wait(timeout=5)
        manager.pause_run(run_id)
        assert managed.state.status == RunStatus.PAUSED

        resume_allowed.set()
        time.sleep(0.05)
        manager.resume_run(run_id)

        assert managed.thread is not None
        managed.thread.join(timeout=5)
        assert managed.state.completed == 3


class TestRunManagerListAndGet:
    def test_list_runs_returns_all_runs(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)

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
        config = make_config(tmp_path)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        result = manager.get_run(run_id)
        assert result is managed

    def test_get_run_returns_none_for_unknown_id(self):
        manager = RunManager()
        assert manager.get_run("nonexistent") is None


class TestManagedRunBuildEmitter:
    def test_build_emitter_returns_queue_emitter_without_extras(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)
        managed = manager.create_run(config)

        emitter = managed.build_emitter()
        assert emitter is managed.emitter
        assert isinstance(emitter, QueueEmitter)

    def test_build_emitter_returns_fanout_with_extras(self, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path)
        managed = manager.create_run(config)

        extra = QueueEmitter()
        managed.add_listener(extra)

        emitter = managed.build_emitter()
        assert isinstance(emitter, FanoutEmitter)


class TestRunManagerExtraListeners:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_extra_listeners_receive_events(self, mock_run, tmp_path):
        manager = RunManager()
        config = make_config(tmp_path, max_iterations=1)
        managed = manager.create_run(config)
        run_id = managed.state.run_id

        extra = QueueEmitter()
        managed.add_listener(extra)

        manager.start_run(run_id)
        assert managed.thread is not None
        managed.thread.join(timeout=5)

        primary_events = drain_events(managed.emitter)
        extra_events = drain_events(extra)

        assert len(primary_events) > 0
        assert len(extra_events) == len(primary_events)


class TestRunManagerWaitForAny:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_wait_for_any_returns_first_finisher(self, mock_run, tmp_path):
        manager = RunManager()
        # Run A finishes after one iteration; run B runs long with a delay.
        fast = manager.create_run(make_config(tmp_path, max_iterations=1))
        slow = manager.create_run(make_config(tmp_path, max_iterations=100, delay=10))

        manager.start_run(fast.state.run_id)
        manager.start_run(slow.state.run_id)

        finished = manager.wait_for_any(
            [fast.state.run_id, slow.state.run_id], timeout=5
        )

        assert fast.state.run_id in finished
        assert slow.state.run_id not in finished

        manager.shutdown(timeout=5)

    def test_wait_for_any_times_out_to_empty_list(self, tmp_path):
        manager = RunManager()
        # Never started — never finishes.
        managed = manager.create_run(make_config(tmp_path))
        assert manager.wait_for_any([managed.state.run_id], timeout=0.05) == []

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_wait_for_any_ignores_unknown_ids(self, mock_run, tmp_path):
        # Docstring contract: unknown IDs are never reported as finished,
        # only the real run that completes is returned.
        manager = RunManager()
        real = manager.create_run(make_config(tmp_path, max_iterations=1))
        manager.start_run(real.state.run_id)

        finished = manager.wait_for_any([real.state.run_id, "ghost"], timeout=5)

        assert finished == [real.state.run_id]
        assert "ghost" not in finished

    def test_wait_for_any_empty_run_ids_times_out(self):
        # No IDs can ever finish, so this can only time out to [].
        manager = RunManager()
        assert manager.wait_for_any([], timeout=0.05) == []

    def test_wait_for_any_empty_run_ids_no_timeout_returns_immediately(self):
        # Regression: empty run_ids with timeout=None must NOT block forever.
        # Nothing can ever notify the condition for an empty set, so the only
        # honest answer is an immediate [].
        manager = RunManager()
        assert _returns_without_blocking(lambda: manager.wait_for_any([])) == []

    def test_wait_for_any_all_unknown_no_timeout_returns_immediately(self):
        # Regression: all-unknown IDs with timeout=None must not hang.
        manager = RunManager()
        assert (
            _returns_without_blocking(
                lambda: manager.wait_for_any(["ghost1", "ghost2"])
            )
            == []
        )


class TestRunManagerWaitForAll:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_wait_for_all_returns_true_when_all_finish(self, mock_run, tmp_path):
        manager = RunManager()
        a = manager.create_run(make_config(tmp_path, max_iterations=1))
        b = manager.create_run(make_config(tmp_path, max_iterations=1))

        manager.start_run(a.state.run_id)
        manager.start_run(b.state.run_id)

        assert manager.wait_for_all([a.state.run_id, b.state.run_id], timeout=5) is True
        assert a.state.status == RunStatus.COMPLETED
        assert b.state.status == RunStatus.COMPLETED

    def test_wait_for_all_times_out_to_false(self, tmp_path):
        manager = RunManager()
        managed = manager.create_run(make_config(tmp_path))
        assert manager.wait_for_all([managed.state.run_id], timeout=0.05) is False

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_wait_for_all_false_when_an_id_is_unknown(self, mock_run, tmp_path):
        # Docstring contract: an unknown ID can never finish, so even when
        # the real run completes the whole set never resolves -> times out.
        manager = RunManager()
        real = manager.create_run(make_config(tmp_path, max_iterations=1))
        manager.start_run(real.state.run_id)
        manager.wait_for_all([real.state.run_id], timeout=5)  # let real finish

        assert manager.wait_for_all([real.state.run_id, "ghost"], timeout=0.05) is False

    def test_wait_for_all_empty_run_ids_is_true(self):
        # Vacuously satisfied: no runs to wait on, so all (zero) are finished.
        manager = RunManager()
        assert manager.wait_for_all([], timeout=0.05) is True

    def test_wait_for_all_unknown_id_no_timeout_returns_immediately(self):
        # Regression: an unknown ID can never finish, so wait_for_all with
        # timeout=None must return False immediately instead of blocking forever.
        manager = RunManager()
        assert (
            _returns_without_blocking(lambda: manager.wait_for_all(["ghost"])) is False
        )


class TestRunManagerGetResult:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_get_result_matches_run_state_counts(self, mock_run, tmp_path):
        manager = RunManager()
        managed = manager.create_run(make_config(tmp_path, max_iterations=3))
        run_id = managed.state.run_id

        manager.start_run(run_id)
        assert manager.wait_for_all([run_id], timeout=5) is True

        result = manager.get_result(run_id)
        state = managed.state
        assert isinstance(result, RunResult)
        assert result.run_id == run_id
        assert result.status == state.status
        assert result.total == state.total
        assert result.completed == state.completed
        assert result.failed == state.failed
        assert result.timed_out_count == state.timed_out_count
        assert result.completed == 3

    def test_get_result_raises_key_error_for_unknown_id(self):
        manager = RunManager()
        with pytest.raises(KeyError, match="No run with ID 'nope'"):
            manager.get_result("nope")

    def test_get_result_snapshots_non_terminal_run(self, tmp_path):
        # Docstring contract: returns current counts "regardless of terminal
        # state". An unstarted run is PENDING with zeroed counters.
        manager = RunManager()
        managed = manager.create_run(make_config(tmp_path, max_iterations=3))

        result = manager.get_result(managed.state.run_id)

        assert result.status == RunStatus.PENDING
        assert result.total == 0
        assert result.completed == 0
        assert result.failed == 0
        assert result.timed_out_count == 0


class TestRunManagerShutdown:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_shutdown_stops_and_joins_live_runs(self, mock_run, tmp_path):
        manager = RunManager()
        a = manager.create_run(make_config(tmp_path, max_iterations=100, delay=10))
        b = manager.create_run(make_config(tmp_path, max_iterations=100, delay=10))

        manager.start_run(a.state.run_id)
        manager.start_run(b.state.run_id)
        time.sleep(0.05)

        assert manager.shutdown(timeout=5) is True
        assert a.thread is not None and not a.thread.is_alive()
        assert b.thread is not None and not b.thread.is_alive()
        assert a.state.status == RunStatus.STOPPED
        assert b.state.status == RunStatus.STOPPED

    def test_shutdown_with_no_runs_returns_true(self):
        manager = RunManager()
        assert manager.shutdown(timeout=1) is True

    def test_shutdown_ignores_unstarted_runs(self, tmp_path):
        manager = RunManager()
        manager.create_run(make_config(tmp_path))
        # No thread to join; request_stop is harmless.
        assert manager.shutdown(timeout=1) is True
