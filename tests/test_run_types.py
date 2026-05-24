"""Tests for run configuration and state data types."""

import threading
from pathlib import Path

import pytest

from ralphify._frontmatter import RALPH_MARKER
from ralphify._run_types import (
    DEFAULT_COMMAND_TIMEOUT,
    RUN_ID_LENGTH,
    Command,
    RunConfig,
    RunResult,
    RunState,
    RunStatus,
    generate_run_id,
)


class TestGenerateRunId:
    def test_length(self):
        run_id = generate_run_id()
        assert len(run_id) == RUN_ID_LENGTH

    def test_hex_characters(self):
        run_id = generate_run_id()
        assert all(c in "0123456789abcdef" for c in run_id)

    def test_unique(self):
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100


class TestCommand:
    def test_default_timeout(self):
        cmd = Command(name="test", run="echo hi")
        assert cmd.timeout == DEFAULT_COMMAND_TIMEOUT

    def test_custom_timeout(self):
        cmd = Command(name="slow", run="sleep 10", timeout=300)
        assert cmd.timeout == 300


class TestRunConfig:
    def test_default_project_root_is_dot(self, tmp_path):
        config = RunConfig(
            agent="echo",
            ralph_dir=tmp_path,
            ralph_file=tmp_path / RALPH_MARKER,
        )
        assert config.project_root == Path(".")

    def test_defaults(self, tmp_path):
        config = RunConfig(
            agent="echo",
            ralph_dir=tmp_path,
            ralph_file=tmp_path / RALPH_MARKER,
        )
        assert config.commands == []
        assert config.args == {}
        assert config.max_iterations is None
        assert config.delay == 0
        assert config.timeout is None
        assert config.stop_on_error is False
        assert config.log_dir is None
        assert config.credit is True
        assert config.prompt is None

    def test_prompt_body_instead_of_ralph_file(self, tmp_path):
        config = RunConfig(
            agent="echo",
            ralph_dir=tmp_path,
            prompt="do work",
        )
        assert config.prompt == "do work"
        assert config.ralph_file is None

    def test_requires_prompt_or_ralph_file(self, tmp_path):
        with pytest.raises(ValueError, match="exactly one of `prompt` or `ralph_file`"):
            RunConfig(agent="echo", ralph_dir=tmp_path)

    def test_rejects_both_prompt_and_ralph_file(self, tmp_path):
        with pytest.raises(ValueError, match="exactly one of `prompt` or `ralph_file`"):
            RunConfig(
                agent="echo",
                ralph_dir=tmp_path,
                ralph_file=tmp_path / RALPH_MARKER,
                prompt="do work",
            )


class TestRunResult:
    def test_holds_status_and_counts(self):
        result = RunResult(
            run_id="r1",
            status=RunStatus.COMPLETED,
            total=3,
            completed=2,
            failed=1,
            timed_out_count=0,
        )
        assert result.run_id == "r1"
        assert result.status == RunStatus.COMPLETED
        assert result.total == 3
        assert result.completed == 2
        assert result.failed == 1
        assert result.timed_out_count == 0

    def test_is_frozen(self):
        result = RunResult(
            run_id="r1",
            status=RunStatus.COMPLETED,
            total=1,
            completed=1,
            failed=0,
            timed_out_count=0,
        )
        with pytest.raises(AttributeError):
            result.completed = 5  # type: ignore[misc]


class TestRunState:
    def test_initial_state(self):
        state = RunState(run_id="r1")
        assert state.status == RunStatus.PENDING
        assert state.iteration == 0
        assert state.completed == 0
        assert state.failed == 0
        assert state.timed_out_count == 0
        assert state.started_at is None

    def test_total_is_completed_plus_failed(self):
        state = RunState(run_id="r1")
        state.mark_completed()
        state.mark_completed()
        state.mark_failed()
        assert state.total == 3

    def test_mark_timed_out_increments_both_timed_out_count_and_failed(self):
        state = RunState(run_id="r1")
        state.mark_timed_out()
        assert state.timed_out_count == 1
        assert state.failed == 1
        assert state.completed == 0

    def test_not_paused_initially(self):
        state = RunState(run_id="r1")
        assert not state.paused

    def test_not_stop_requested_initially(self):
        state = RunState(run_id="r1")
        assert not state.stop_requested

    def test_request_pause_and_resume(self):
        state = RunState(run_id="r1")
        state.status = RunStatus.RUNNING

        state.request_pause()
        assert state.paused
        assert state.status == RunStatus.PAUSED

        state.request_resume()
        assert not state.paused
        assert state.status == RunStatus.RUNNING

    def test_request_stop_unblocks_pause(self):
        state = RunState(run_id="r1")
        state.request_pause()
        assert state.paused

        state.request_stop()
        assert state.stop_requested
        # Stop sets the resume event so wait_for_unpause unblocks
        assert not state.paused

    def test_wait_for_unpause_returns_immediately_when_not_paused(self):
        state = RunState(run_id="r1")
        assert state.wait_for_unpause(timeout=0.01) is True

    def test_wait_for_unpause_blocks_until_resumed(self):
        state = RunState(run_id="r1")
        state.request_pause()

        resumed = threading.Event()

        def resume_later():
            state.request_resume()
            resumed.set()

        timer = threading.Timer(0.05, resume_later)
        timer.start()

        result = state.wait_for_unpause(timeout=1.0)
        assert result is True
        resumed.wait(timeout=1.0)

    def test_wait_for_unpause_times_out(self):
        state = RunState(run_id="r1")
        state.request_pause()
        result = state.wait_for_unpause(timeout=0.01)
        assert result is False

    def test_wait_for_stop_returns_immediately_when_stopped(self):
        state = RunState(run_id="r1")
        state.request_stop()
        assert state.wait_for_stop(timeout=0.01) is True

    def test_wait_for_stop_times_out_when_not_stopped(self):
        state = RunState(run_id="r1")
        assert state.wait_for_stop(timeout=0.01) is False

    def test_wait_for_stop_unblocks_on_stop_request(self):
        state = RunState(run_id="r1")
        stopped = threading.Event()

        def stop_later():
            state.request_stop()
            stopped.set()

        timer = threading.Timer(0.05, stop_later)
        timer.start()

        result = state.wait_for_stop(timeout=1.0)
        assert result is True
        stopped.wait(timeout=1.0)


class TestRunStatus:
    @pytest.mark.parametrize(
        "status,value",
        [
            (RunStatus.PENDING, "pending"),
            (RunStatus.RUNNING, "running"),
            (RunStatus.PAUSED, "paused"),
            (RunStatus.STOPPED, "stopped"),
            (RunStatus.COMPLETED, "completed"),
            (RunStatus.FAILED, "failed"),
        ],
    )
    def test_enum_values(self, status, value):
        assert status.value == value

    @pytest.mark.parametrize(
        "status,expected_reason",
        [
            (RunStatus.COMPLETED, "completed"),
            (RunStatus.FAILED, "error"),
            (RunStatus.STOPPED, "user_requested"),
        ],
    )
    def test_reason_for_terminal_statuses(self, status, expected_reason):
        assert status.reason == expected_reason

    @pytest.mark.parametrize(
        "status", [RunStatus.PENDING, RunStatus.RUNNING, RunStatus.PAUSED]
    )
    def test_reason_raises_for_non_terminal_statuses(self, status):
        with pytest.raises(ValueError, match="not a terminal status"):
            status.reason
