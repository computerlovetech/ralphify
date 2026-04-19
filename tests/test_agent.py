"""Tests for the _agent module — subprocess execution, log writing, and stream parsing."""

import io
import itertools
import os
import signal
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from helpers import MOCK_SUBPROCESS, fail_proc, make_mock_popen, ok_proc, timeout_proc

from ralphify._agent import (
    AgentResult,
    _kill_process_group,
    _pump_stream,
    _read_agent_stream,
    _run_agent_blocking,
    _run_agent_streaming,
    _write_log,
    execute_agent,
)
from ralphify.adapters import select_adapter
from ralphify.adapters.claude import ClaudeAdapter


class TestWriteLog:
    def test_creates_log_file(self, tmp_path):
        log_file = _write_log(tmp_path, 1, "stdout output", "stderr output")

        assert log_file.exists()
        assert log_file.parent == tmp_path
        content = log_file.read_text()
        assert "stdout output" in content
        assert "stderr output" in content

    def test_log_filename_format(self, tmp_path):
        log_file = _write_log(tmp_path, 5, "out", "")

        assert log_file.name.startswith("005_")
        assert log_file.suffix == ".log"

    def test_none_outputs(self, tmp_path):
        log_file = _write_log(tmp_path, 1, None, None)

        assert log_file.exists()
        assert log_file.read_text() == ""

    def test_bytes_outputs(self, tmp_path):
        log_file = _write_log(tmp_path, 1, b"binary out\n", b"binary err\n")

        content = log_file.read_text()
        assert "binary out" in content
        assert "binary err" in content

    def test_iteration_zero_padding(self, tmp_path):
        log_file = _write_log(tmp_path, 42, "out", "")
        assert log_file.name.startswith("042_")


class TestReadAgentStream:
    def test_collects_all_lines(self):
        stream = io.StringIO("line1\nline2\nline3\n")
        result = _read_agent_stream(stream, deadline=None, on_activity=None)

        assert len(result.stdout_lines) == 3
        assert result.timed_out is False

    def test_parses_json_lines(self):
        activities = []
        stream = io.StringIO('{"type": "status", "msg": "ok"}\n')
        _read_agent_stream(stream, deadline=None, on_activity=activities.append)

        assert len(activities) == 1
        assert activities[0]["type"] == "status"

    def test_captures_result_text(self):
        stream = io.StringIO('{"type": "result", "result": "All done"}\n')
        result = _read_agent_stream(stream, deadline=None, on_activity=None)

        assert result.result_text == "All done"

    def test_ignores_non_json_lines(self):
        activities = []
        stream = io.StringIO("not json\n")
        result = _read_agent_stream(
            stream, deadline=None, on_activity=activities.append
        )

        assert len(result.stdout_lines) == 1
        assert len(activities) == 0

    @pytest.mark.parametrize(
        "line", ["42\n", '"hello"\n', "[1,2,3]\n", "true\n", "null\n"]
    )
    def test_ignores_valid_json_non_object_lines(self, line):
        """Valid JSON that is not a JSON object (e.g. number, string, array)
        should be silently skipped, not crash with AttributeError."""
        activities = []
        stream = io.StringIO(line)
        result = _read_agent_stream(
            stream, deadline=None, on_activity=activities.append
        )

        assert len(result.stdout_lines) == 1
        assert len(activities) == 0
        assert result.result_text is None

    def test_skips_empty_lines(self):
        activities = []
        stream = io.StringIO("\n\n")
        result = _read_agent_stream(
            stream, deadline=None, on_activity=activities.append
        )

        assert len(result.stdout_lines) == 2
        assert len(activities) == 0

    def test_timeout_returns_early(self):
        stream = io.StringIO("line1\nline2\n")
        # Deadline already in the past — the reader thread may or may not
        # have queued lines yet, but timed_out must be True.
        result = _read_agent_stream(stream, deadline=0.001, on_activity=None)

        assert result.timed_out is True

    def test_timeout_preserves_already_read_lines(self):
        """When timeout fires after the reader thread has queued lines,
        those lines must still appear in stdout_lines ��� the non-blocking
        drain on an expired deadline must not silently discard them."""
        r_fd, w_fd = os.pipe()
        reader = os.fdopen(r_fd, "r")
        writer = os.fdopen(w_fd, "w")
        try:
            writer.write("line1\nline2\n")
            writer.flush()
            # Don't close writer — stream stays open so reader blocks on
            # readline after the two lines, and the deadline fires.
            deadline = time.monotonic() + 0.5
            result = _read_agent_stream(reader, deadline=deadline, on_activity=None)

            assert result.timed_out is True
            assert len(result.stdout_lines) >= 1
            assert result.stdout_lines[0] == "line1\n"
        finally:
            writer.close()
            reader.close()

    def test_timeout_still_processes_last_line(self):
        """When timeout fires on a line containing a result event, the result
        text must still be extracted — the deadline check should not skip
        processing of the already-read line."""
        r_fd, w_fd = os.pipe()
        reader = os.fdopen(r_fd, "r")
        writer = os.fdopen(w_fd, "w")
        try:
            writer.write('{"type": "result", "result": "Done"}\n')
            writer.flush()
            deadline = time.monotonic() + 0.5
            result = _read_agent_stream(reader, deadline=deadline, on_activity=None)

            assert result.timed_out is True
            assert result.result_text == "Done"
        finally:
            writer.close()
            reader.close()

    def test_timeout_still_calls_on_activity_for_last_line(self):
        """When timeout fires on a line, on_activity must still be called
        for that line so the last event is not silently swallowed."""
        r_fd, w_fd = os.pipe()
        reader = os.fdopen(r_fd, "r")
        writer = os.fdopen(w_fd, "w")
        try:
            activities = []
            writer.write('{"type": "status", "msg": "working"}\n')
            writer.flush()
            deadline = time.monotonic() + 0.5
            result = _read_agent_stream(
                reader, deadline=deadline, on_activity=activities.append
            )

            assert result.timed_out is True
            assert len(activities) == 1
            assert activities[0]["type"] == "status"
        finally:
            writer.close()
            reader.close()

    def test_result_type_without_result_field_ignored(self):
        stream = io.StringIO('{"type": "result"}\n')
        result = _read_agent_stream(stream, deadline=None, on_activity=None)

        assert result.result_text is None

    def test_non_string_result_field_ignored(self):
        stream = io.StringIO('{"type": "result", "result": 42}\n')
        result = _read_agent_stream(stream, deadline=None, on_activity=None)

        assert result.result_text is None

    def test_last_result_wins(self):
        stream = io.StringIO(
            '{"type": "result", "result": "first"}\n'
            '{"type": "result", "result": "second"}\n'
        )
        result = _read_agent_stream(stream, deadline=None, on_activity=None)

        assert result.result_text == "second"

    def test_continues_when_on_output_line_raises(self):
        """A raising on_output_line callback must not crash the stream reader.

        This mirrors _pump_stream's behavior where callback exceptions are
        caught per-line so that draining continues.  Without this guard, a
        transient rendering error in the console emitter would kill the
        entire streaming run."""
        call_count = 0

        def raising_callback(line, stream):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")

        stream = io.StringIO("line1\nline2\nline3\n")
        result = _read_agent_stream(
            stream, deadline=None, on_activity=None, on_output_line=raising_callback
        )

        assert len(result.stdout_lines) == 3
        assert call_count == 3
        assert result.timed_out is False

    def test_continues_when_on_activity_raises(self):
        """A raising on_activity callback must not crash the stream reader."""
        call_count = 0

        def raising_activity(data):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")

        stream = io.StringIO(
            '{"type": "status", "msg": "a"}\n{"type": "status", "msg": "b"}\n'
        )
        result = _read_agent_stream(stream, deadline=None, on_activity=raising_activity)

        assert len(result.stdout_lines) == 2
        assert call_count == 2
        assert result.timed_out is False


class TestExecuteAgentBlocking:
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_success(self, mock_popen):
        result = execute_agent(
            ["echo"], "prompt", timeout=None, log_dir=None, iteration=1
        )

        assert result.returncode == 0
        assert result.timed_out is False
        assert result.log_file is None
        assert result.elapsed >= 0

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_failure(self, mock_popen):
        result = execute_agent(
            ["echo"], "prompt", timeout=None, log_dir=None, iteration=1
        )

        assert result.returncode == 1
        assert result.timed_out is False

    @patch(MOCK_SUBPROCESS, side_effect=timeout_proc)
    def test_timeout(self, mock_popen):
        result = execute_agent(["echo"], "prompt", timeout=5, log_dir=None, iteration=1)

        assert result.returncode is None
        assert result.timed_out is True

    @patch(MOCK_SUBPROCESS, side_effect=timeout_proc)
    def test_returncode_is_none_on_blocking_timeout(self, mock_popen):
        """Blocking path returns returncode=None on timeout, matching the
        ProcessResult contract and the streaming path's behavior."""
        result = _run_agent_blocking(
            ["echo"], "prompt", timeout=5, log_dir=None, iteration=1
        )

        assert result.returncode is None
        assert result.timed_out is True

    @patch(MOCK_SUBPROCESS)
    def test_writes_log_on_success(self, mock_popen, tmp_path):
        mock_popen.return_value = ok_proc(stdout_text="agent output\n")
        result = execute_agent(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=tmp_path,
            iteration=3,
        )

        assert result.log_file is not None
        assert result.log_file.exists()
        assert result.log_file.name.startswith("003_")
        assert "agent output" in result.log_file.read_text()

    @patch(MOCK_SUBPROCESS)
    def test_writes_log_on_timeout(self, mock_popen, tmp_path):
        mock_popen.return_value = timeout_proc(stdout_text="partial", stderr_text="err")
        result = execute_agent(
            ["echo"],
            "prompt",
            timeout=5,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.log_file is not None
        assert result.log_file.exists()

    @patch(MOCK_SUBPROCESS)
    def test_timeout_captures_partial_output(self, mock_popen, tmp_path):
        """When logging is enabled and the agent times out, partial output
        is captured on the AgentResult for the engine to echo."""
        mock_popen.return_value = timeout_proc(
            stdout_text="partial stdout", stderr_text="partial stderr"
        )
        result = execute_agent(
            ["echo"],
            "prompt",
            timeout=5,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.captured_stdout == "partial stdout"
        assert result.captured_stderr == "partial stderr"

    @patch(MOCK_SUBPROCESS)
    def test_capture_result_text_does_not_buffer_blocking_output_without_log_dir(
        self, mock_popen
    ):
        mock_popen.return_value = ok_proc(
            stdout_text="<promise>done</promise>\n",
            stderr_text="some stderr\n",
        )
        result = _run_agent_blocking(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            capture_result_text=True,
        )

        assert result.captured_stdout is None
        assert result.captured_stderr is None
        assert result.result_text is None

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs.get("stdin") == subprocess.PIPE
        assert call_kwargs.get("stdout") == subprocess.PIPE
        assert call_kwargs.get("stderr") is None

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_no_log_when_dir_not_set(self, mock_popen):
        result = execute_agent(
            ["echo"], "prompt", timeout=None, log_dir=None, iteration=1
        )

        assert result.log_file is None

    @patch(MOCK_SUBPROCESS)
    def test_file_not_found_propagates(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("not found")

        with pytest.raises(FileNotFoundError):
            execute_agent(
                ["nonexistent"],
                "prompt",
                timeout=None,
                log_dir=None,
                iteration=1,
            )


class TestAgentResult:
    def test_defaults(self):
        result = AgentResult(returncode=0, elapsed=1.0, log_file=None)
        assert result.result_text is None
        assert result.timed_out is False

    def test_timed_out(self):
        result = AgentResult(
            returncode=None, elapsed=5.0, log_file=None, timed_out=True
        )
        assert result.timed_out is True
        assert result.returncode is None

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            (AgentResult(returncode=0, elapsed=1.0, log_file=None), True),
            (AgentResult(returncode=1, elapsed=1.0, log_file=None), False),
            (
                AgentResult(
                    returncode=None, elapsed=5.0, log_file=None, timed_out=True
                ),
                False,
            ),
        ],
        ids=["zero-exit", "nonzero-exit", "timed-out"],
    )
    def test_success(self, result, expected):
        assert result.success is expected


class TestExecuteAgentDispatch:
    """Tests for execute_agent routing to streaming vs blocking mode."""

    @patch(MOCK_SUBPROCESS)
    def test_dispatches_to_streaming_for_claude(self, mock_popen, monkeypatch):
        """execute_agent uses the streaming path when the adapter renders
        structured output."""
        claude_adapter = select_adapter(["claude"])
        assert isinstance(claude_adapter, ClaudeAdapter)
        monkeypatch.setattr(claude_adapter, "supports_streaming", True)
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "result", "result": "done"}\n',
            returncode=0,
        )
        result = execute_agent(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        assert result.returncode == 0
        assert result.result_text == "done"
        mock_popen.assert_called_once()

    def test_execute_agent_passes_capture_result_text_to_streaming_helper(
        self, monkeypatch
    ):
        on_activity = MagicMock()
        on_output_line = MagicMock()
        fake_streaming = MagicMock(return_value=AgentResult(returncode=0, elapsed=0.01))

        claude_adapter = select_adapter(["claude"])
        assert isinstance(claude_adapter, ClaudeAdapter)
        monkeypatch.setattr(claude_adapter, "supports_streaming", True)
        monkeypatch.setattr("ralphify._agent._run_agent_streaming", fake_streaming)

        execute_agent(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            on_activity=on_activity,
            on_output_line=on_output_line,
            capture_result_text=True,
        )

        fake_streaming.assert_called_once_with(
            claude_adapter.build_command(["claude", "-p"]),
            "prompt",
            None,
            None,
            1,
            on_activity=on_activity,
            on_output_line=on_output_line,
            capture_result_text=True,
            capture_stdout=False,
        )

    def test_execute_agent_passes_capture_result_text_to_blocking_helper(
        self, monkeypatch
    ):
        on_output_line = MagicMock()
        fake_blocking = MagicMock(return_value=AgentResult(returncode=0, elapsed=0.01))

        # The autouse conftest fixture already forces every adapter's
        # supports_streaming flag to False, so ``echo`` falls into the
        # blocking path through the GenericAdapter fallback.
        monkeypatch.setattr("ralphify._agent._run_agent_blocking", fake_blocking)

        execute_agent(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            on_output_line=on_output_line,
            capture_result_text=True,
        )

        fake_blocking.assert_called_once_with(
            ["echo"],
            "prompt",
            None,
            None,
            1,
            on_output_line=on_output_line,
            capture_result_text=True,
            capture_stdout=False,
        )


class TestExecuteAgentStreaming:
    """Tests for the streaming execution path (_run_agent_streaming)."""

    @patch(MOCK_SUBPROCESS)
    def test_streaming_result_event_populates_result_text(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "result", "result": "early done"}\n',
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=10,
            log_dir=None,
            iteration=1,
        )
        assert result.result_text == "early done"
        assert result.returncode == 0
        assert result.timed_out is False

    @patch(MOCK_SUBPROCESS)
    def test_blocking_result_event_populates_result_text_when_captured(
        self, mock_popen, tmp_path
    ):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "result", "result": "early done"}\n',
            returncode=0,
        )
        result = _run_agent_blocking(
            ["claude", "-p"],
            "prompt",
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.result_text == "early done"
        assert result.returncode == 0
        assert result.timed_out is False

    @patch(MOCK_SUBPROCESS)
    def test_result_text_absent_when_no_result_event(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines="status: working\n",
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=10,
            log_dir=None,
            iteration=1,
        )
        assert result.result_text is None
        assert result.returncode == 0
        assert result.timed_out is False

    @patch(MOCK_SUBPROCESS)
    def test_last_result_event_wins(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "result", "result": "first"}\n{"type": "result", "result": "second"}\n',
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=10,
            log_dir=None,
            iteration=1,
        )
        assert result.result_text == "second"
        assert result.returncode == 0
        assert result.timed_out is False

    @patch(MOCK_SUBPROCESS)
    def test_success(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "status", "msg": "working"}\n',
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        assert result.returncode == 0
        assert result.timed_out is False
        assert result.elapsed >= 0

    @patch(MOCK_SUBPROCESS)
    def test_failure(self, mock_popen):
        mock_popen.return_value = make_mock_popen(returncode=1)
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        assert result.returncode == 1
        assert result.timed_out is False
        assert result.success is False

    @patch(MOCK_SUBPROCESS)
    def test_captures_result_text(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "result", "result": "All tests passed"}\n',
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        assert result.result_text == "All tests passed"

    @patch(MOCK_SUBPROCESS)
    def test_sends_prompt_to_stdin(self, mock_popen):
        proc = make_mock_popen(returncode=0)
        mock_popen.return_value = proc
        _run_agent_streaming(
            ["claude", "-p"],
            "my prompt text",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        proc.stdin.write.assert_called_once_with("my prompt text")
        proc.stdin.close.assert_called_once()

    @patch(MOCK_SUBPROCESS)
    def test_passes_cmd_verbatim_to_popen(self, mock_popen):
        """_run_agent_streaming no longer appends its own flags — the caller
        (via ``adapter.build_command``) owns CLI flags now."""
        mock_popen.return_value = make_mock_popen(returncode=0)
        _run_agent_streaming(
            ["claude", "-p", "--output-format", "stream-json", "--verbose"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd == [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
        ]

    @patch(MOCK_SUBPROCESS)
    def test_writes_log_on_success(self, mock_popen, tmp_path):
        mock_popen.return_value = make_mock_popen(
            stdout_lines="agent output\n",
            stderr_text="some stderr\n",
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=tmp_path,
            iteration=3,
        )

        assert result.log_file is not None
        assert result.log_file.exists()
        assert result.log_file.name.startswith("003_")
        content = result.log_file.read_text()
        assert "agent output" in content
        assert "some stderr" in content

    @patch(MOCK_SUBPROCESS)
    def test_captured_output_set_when_logging(self, mock_popen, tmp_path):
        """When log_dir is set, captured_stdout and captured_stderr
        must be populated so the engine can echo them via the event system
        — matching the blocking path's behavior."""
        mock_popen.return_value = make_mock_popen(
            stdout_lines="agent output\n",
            stderr_text="some stderr\n",
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.captured_stdout == "agent output\n"
        assert result.captured_stderr == "some stderr\n"

    @patch(MOCK_SUBPROCESS)
    def test_capture_result_text_does_not_buffer_stream_output_without_log_dir(
        self, mock_popen
    ):
        mock_popen.return_value = make_mock_popen(
            stdout_lines="<promise>done</promise>\n",
            stderr_text="some stderr\n",
            returncode=0,
        )
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            capture_result_text=True,
        )

        assert result.captured_stdout is None
        assert result.captured_stderr is None
        assert result.result_text is None

        call_args = mock_popen.call_args
        assert call_args.args[0] == ["claude", "-p"]
        call_kwargs = call_args[1]
        assert call_kwargs.get("stdin") == subprocess.PIPE
        assert call_kwargs.get("stdout") == subprocess.PIPE
        assert call_kwargs.get("stderr") is None

    @patch(MOCK_SUBPROCESS)
    def test_no_log_when_dir_not_set(self, mock_popen):
        mock_popen.return_value = make_mock_popen(returncode=0)
        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )

        assert result.log_file is None

    @patch(MOCK_SUBPROCESS)
    def test_on_activity_callback_invoked(self, mock_popen):
        mock_popen.return_value = make_mock_popen(
            stdout_lines='{"type": "status", "msg": "working"}\n{"type": "progress"}\n',
            returncode=0,
        )
        activities = []
        _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            on_activity=activities.append,
        )

        assert len(activities) == 2
        assert activities[0]["type"] == "status"
        assert activities[1]["type"] == "progress"

    @patch("ralphify._agent.time.monotonic")
    @patch(MOCK_SUBPROCESS)
    def test_timeout_kills_process(self, mock_popen, mock_time):
        # start=0 → deadline=5.  First loop check: remaining=5 (positive,
        # so queue.get waits up to 5 real seconds — succeeds immediately
        # because the StringIO reader fills the queue).  Post-line check
        # returns 100 → past deadline → timed_out.
        mock_time.side_effect = itertools.chain(
            [0.0, 0.0, 100.0],
            itertools.repeat(100.0),
        )
        proc = make_mock_popen(
            stdout_lines="line1\nline2\n",
            returncode=0,
        )
        proc.poll.return_value = None  # process still running when timeout fires
        mock_popen.return_value = proc

        result = _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=5,
            log_dir=None,
            iteration=1,
        )

        assert result.timed_out is True
        assert result.returncode is None


class TestProcessGroupCleanup:
    """Process group cleanup, isolation, and _kill_process_group tests."""

    pytestmark = pytest.mark.skipif(
        sys.platform == "win32", reason="POSIX-only behavior"
    )

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_session_leader_gets_sigterm(self, mock_getpgid, mock_killpg):
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        mock_getpgid.return_value = 42

        _kill_process_group(proc)

        mock_killpg.assert_any_call(42, signal.SIGTERM)
        proc.wait.assert_called_once_with(timeout=3)

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_escalates_to_sigkill_on_timeout(self, mock_getpgid, mock_killpg):
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="agent", timeout=3)
        mock_getpgid.return_value = 42

        _kill_process_group(proc)

        mock_killpg.assert_any_call(42, signal.SIGTERM)
        mock_killpg.assert_any_call(42, signal.SIGKILL)

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_sigkill_failure_falls_back_to_proc_kill(self, mock_getpgid, mock_killpg):
        """When SIGTERM times out and SIGKILL also fails, fall back to proc.kill()."""
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="agent", timeout=3)
        mock_getpgid.return_value = 42
        # SIGTERM succeeds but SIGKILL fails (process vanished between attempts)
        mock_killpg.side_effect = [None, ProcessLookupError("No such process")]

        _kill_process_group(proc)

        mock_killpg.assert_any_call(42, signal.SIGTERM)
        mock_killpg.assert_any_call(42, signal.SIGKILL)
        proc.kill.assert_called_once()

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_not_session_leader_falls_back_to_kill(self, mock_getpgid, mock_killpg):
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        mock_getpgid.return_value = 1

        _kill_process_group(proc)

        mock_killpg.assert_not_called()
        proc.kill.assert_called_once()

    def test_already_exited_falls_back_to_kill(self):
        proc = MagicMock(pid=42, poll=MagicMock(return_value=0))

        _kill_process_group(proc)

        proc.kill.assert_called_once()

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_blocking_uses_start_new_session(self, mock_popen):
        execute_agent(["echo"], "prompt", timeout=None, log_dir=None, iteration=1)
        assert mock_popen.call_args[1].get("start_new_session") is True

    @patch(MOCK_SUBPROCESS)
    def test_streaming_uses_start_new_session(self, mock_popen):
        mock_popen.return_value = make_mock_popen(returncode=0)
        _run_agent_streaming(
            ["claude", "-p"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
        )
        assert mock_popen.call_args[1].get("start_new_session") is True

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_killpg_oserror_falls_back_to_proc_kill(self, mock_getpgid, mock_killpg):
        """When os.killpg raises OSError (e.g. process already gone), fall back to proc.kill()."""
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        mock_getpgid.return_value = 42  # session leader
        mock_killpg.side_effect = OSError("No such process")

        _kill_process_group(proc)

        mock_killpg.assert_called_once_with(42, signal.SIGTERM)
        proc.kill.assert_called_once()

    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_killpg_process_lookup_error_falls_back_to_proc_kill(
        self, mock_getpgid, mock_killpg
    ):
        """When os.killpg raises ProcessLookupError, fall back to proc.kill()."""
        proc = MagicMock(pid=42, poll=MagicMock(return_value=None))
        mock_getpgid.return_value = 42
        mock_killpg.side_effect = ProcessLookupError("No such process")

        _kill_process_group(proc)

        proc.kill.assert_called_once()

    @pytest.mark.parametrize("pid", [0, -1, None])
    @patch("ralphify._agent.os.killpg")
    @patch("ralphify._agent.os.getpgid")
    def test_kill_process_group_short_circuits_on_sentinel_pid(
        self, mock_getpgid, mock_killpg, pid
    ):
        """Non-positive or None pids must never reach os.getpgid/os.killpg."""
        proc = MagicMock(pid=pid, poll=MagicMock(return_value=None))

        _kill_process_group(proc)

        mock_getpgid.assert_not_called()
        mock_killpg.assert_not_called()
        proc.kill.assert_not_called()


class TestRunAgentStreamingPipeGuard:
    """Test the defensive RuntimeError when Popen fails to create PIPE streams."""

    @patch(MOCK_SUBPROCESS)
    def test_raises_when_stdin_is_none(self, mock_popen):
        proc = make_mock_popen(returncode=0)
        proc.stdin = None
        proc.poll.return_value = None  # process still running for finally cleanup
        mock_popen.return_value = proc

        with pytest.raises(RuntimeError, match="PIPE streams"):
            _run_agent_streaming(
                ["claude", "-p"],
                "prompt",
                timeout=None,
                log_dir=None,
                iteration=1,
            )


class TestRunAgentBlockingKeyboardInterrupt:
    """Test that KeyboardInterrupt during blocking execution kills the process and re-raises."""

    @patch(MOCK_SUBPROCESS)
    def test_keyboard_interrupt_kills_and_reraises(self, mock_popen):
        proc = MagicMock()
        proc.pid = 0  # sentinel: skip real process-group manipulation
        proc.stdin = MagicMock()
        proc.stdout = io.StringIO("")
        proc.stderr = io.StringIO("")
        # First wait() raises KeyboardInterrupt; all subsequent calls
        # return -2.  Uses itertools.chain so the exact number of wait()
        # calls made by cleanup paths can drift without breaking the test.
        proc.wait.side_effect = itertools.chain(
            [KeyboardInterrupt], itertools.repeat(-2)
        )
        # First poll() (inside _kill_process_group) sees a live process;
        # every later poll() sees it as reaped so cleanup paths don't
        # re-enter kill/wait.
        proc.poll.side_effect = itertools.chain([None], itertools.repeat(0))
        mock_popen.return_value = proc

        with pytest.raises(KeyboardInterrupt):
            execute_agent(
                ["echo"],
                "prompt",
                timeout=None,
                log_dir=None,
                iteration=1,
            )

        proc.wait.assert_called()


class TestRunAgentBlockingLineStreaming:
    """Real-subprocess tests for live line streaming via _run_agent_blocking.

    Uses tiny ``python -c`` subprocesses rather than mocks so we exercise
    the actual reader-thread path and observe lines as the process runs.
    """

    def test_on_output_line_receives_lines_in_order(self, tmp_path):
        script = "import sys; print('first'); print('second'); print('third')"
        received: list[tuple[str, str]] = []

        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt="",
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=lambda line, stream: received.append((line, stream)),
        )

        assert result.returncode == 0
        assert [line for line, _ in received] == ["first", "second", "third"]
        assert all(stream == "stdout" for _, stream in received)

        # Log file still receives the full output (behavior preserved).
        assert result.log_file is not None
        log_text = result.log_file.read_text()
        assert "first" in log_text
        assert "second" in log_text
        assert "third" in log_text

    def test_on_output_line_captures_stderr_separately(self, tmp_path):
        script = (
            "import sys; "
            "print('out-line', file=sys.stdout); "
            "print('err-line', file=sys.stderr); "
            "sys.stdout.flush(); sys.stderr.flush()"
        )
        received: list[tuple[str, str]] = []

        _run_agent_blocking(
            [sys.executable, "-u", "-c", script],
            prompt="",
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=lambda line, stream: received.append((line, stream)),
        )

        streams = {stream for _, stream in received}
        assert streams == {"stdout", "stderr"}
        lines_by_stream = {stream: line for line, stream in received}
        assert lines_by_stream["stdout"] == "out-line"
        assert lines_by_stream["stderr"] == "err-line"

    def test_stdin_prompt_delivered_to_subprocess(self, tmp_path):
        """The prompt must reach the child via stdin so real agents get it."""
        script = "import sys; sys.stdout.write(sys.stdin.read())"
        received: list[str] = []

        _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt="hello-from-prompt\n",
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=lambda line, stream: received.append(line),
        )

        assert received == ["hello-from-prompt"]

    def test_large_prompt_with_concurrent_stderr_does_not_deadlock(self, tmp_path):
        """Regression guard for the pipe-buffer deadlock.

        If the child writes a burst of stderr larger than the OS pipe
        buffer before reading its stdin, and the parent is simultaneously
        writing a stdin prompt larger than the buffer, the only way to
        avoid deadlock is for the parent to drain stderr concurrently on
        a reader thread that was started **before** the stdin write began.

        This test fails (hangs) if the reader threads are started after
        the stdin write.
        """
        script = (
            "import sys\n"
            "sys.stderr.write('y' * 200000)\n"
            "sys.stderr.flush()\n"
            "sys.stdin.read()\n"
            "sys.stdout.write('done\\n')\n"
        )
        large_prompt = "x" * 200000

        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt=large_prompt,
            timeout=15,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.returncode == 0
        assert result.timed_out is False

    def test_early_exit_with_large_prompt_does_not_crash(self, tmp_path):
        """If the agent exits without consuming its stdin, the parent's
        write will raise ``BrokenPipeError``; the blocking path must
        swallow it and still return the child's real exit code.
        """
        script = "import sys; sys.exit(0)"
        large_prompt = "x" * 200000

        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt=large_prompt,
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.returncode == 0
        assert result.timed_out is False

    def test_streaming_large_stderr_drained_concurrently(self, tmp_path):
        """Regression guard for the streaming path.

        An agent that writes substantial stderr before emitting its result
        event would previously deadlock the streaming path because stderr
        was only read after ``proc.wait()``.  With a concurrent stderr
        pump thread this finishes normally.
        """
        script = (
            "import sys\n"
            "sys.stderr.write('y' * 200000)\n"
            "sys.stderr.flush()\n"
            "sys.stdin.read()\n"
            'sys.stdout.write(\'{"type": "result", "result": "ok"}\\n\')\n'
        )

        result = _run_agent_streaming(
            [sys.executable, "-c", script],
            prompt="hi",
            timeout=15,
            log_dir=tmp_path,
            iteration=1,
        )

        assert result.returncode == 0
        assert result.timed_out is False
        assert result.result_text == "ok"

    def test_timeout_enforced_when_agent_does_not_read_stdin(self, tmp_path):
        """If the agent never reads stdin, --timeout must still fire.

        Before the writer-thread fix, proc.stdin.write(prompt) blocked on
        the main thread when the OS pipe buffer was full, and
        proc.wait(timeout=...) was never reached — so --timeout silently
        did nothing.

        Uses a prompt large enough to fill the pipe buffer (64 KB on
        Linux, ~8 KB on macOS) so the write would block if it were on
        the main thread.
        """
        # Agent that never reads stdin and sleeps for 30 seconds.
        script = "import time; time.sleep(30)"
        # Prompt larger than OS pipe buffer on any platform.
        large_prompt = "x" * 200_000

        start = time.monotonic()
        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt=large_prompt,
            timeout=2.0,
            log_dir=tmp_path,
            iteration=1,
        )
        elapsed = time.monotonic() - start

        assert result.timed_out is True
        assert result.returncode is None
        # Must complete well before the child's 30-second sleep finishes.
        assert elapsed < 15.0


class TestStreamingDeadlineAndBuffering:
    """Tests for deadline enforcement and line-at-a-time delivery in the
    streaming path (_read_agent_stream / _run_agent_streaming).

    Uses real subprocesses to exercise the actual I/O layer — the bugs
    these tests guard against live at the pipe-buffering and thread-scheduling
    level, where mocks would be misleading.
    """

    def test_streaming_timeout_enforced_on_silent_agent(self, tmp_path):
        """A hung agent that produces no output must still be killed by --timeout.

        Before the fix, ``for line in stdout`` blocked in readline()
        indefinitely, and the deadline check only ran between lines.  The
        queue-based approach unblocks via ``queue.get(timeout=remaining)``
        so the deadline fires even with zero output.
        """
        # Agent reads stdin then sleeps 30s, writing nothing to stdout.
        script = "import sys, time; sys.stdin.read(); time.sleep(30)"

        start = time.monotonic()
        result = _run_agent_streaming(
            [sys.executable, "-u", "-c", script],
            prompt="go",
            timeout=1.0,
            log_dir=tmp_path,
            iteration=1,
        )
        elapsed = time.monotonic() - start

        assert result.timed_out is True
        assert result.returncode is None
        # Must return well before the child's 30-second sleep.
        assert elapsed < 10.0

    def test_streaming_peek_flows_line_at_a_time(self, tmp_path):
        """Peek callbacks must fire promptly as lines arrive, not in 8KB bursts.

        A fake agent emits timestamped lines with 200ms sleeps.  Each
        ``on_output_line`` callback must fire within 500ms of the line's
        emission — if they arrived in readahead bursts the later lines
        would be delayed.
        """
        # Agent emits 5 lines at ~200ms intervals with wall-clock timestamps.
        script = (
            "import sys, time\n"
            "sys.stdin.read()\n"
            "for i in range(5):\n"
            "    print(f'{time.monotonic():.6f} line{i}', flush=True)\n"
            "    if i < 4:\n"
            "        time.sleep(0.2)\n"
        )
        receive_times: list[float] = []

        def on_line(line: str, stream: str) -> None:
            receive_times.append(time.monotonic())

        result = _run_agent_streaming(
            [sys.executable, "-u", "-c", script],
            prompt="go",
            timeout=15,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=on_line,
        )

        assert result.returncode == 0
        assert result.timed_out is False
        # Should have received all 5 lines (stdout) plus any stderr lines
        # forwarded by the stderr pump — at least 5.
        stdout_callbacks = len(receive_times)
        assert stdout_callbacks >= 5

        # Check that lines were delivered promptly.  The gap between
        # consecutive callbacks should be roughly 200ms (±300ms for
        # scheduling jitter).  If buffered in 8KB bursts, the last 4
        # lines would all arrive at once with ~0ms gaps.
        for i in range(1, min(5, stdout_callbacks)):
            gap = receive_times[i] - receive_times[i - 1]
            assert gap > 0.05, (
                f"Gap between line {i - 1} and {i} was {gap:.3f}s — "
                "lines likely arrived in a buffered burst"
            )


class TestBlockingInheritPath:
    """Tests for the fd-inheritance path in _run_agent_blocking.

    When both ``log_dir`` and ``on_output_line`` are ``None``, the
    blocking path should inherit stdout/stderr from the parent (no PIPE,
    no reader threads) so that ``ralph run | cat`` shows output.
    """

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_no_pipe_when_no_log_no_callback(self, mock_popen):
        """Popen must NOT receive stdout/stderr=PIPE when no one needs capture."""
        result = _run_agent_blocking(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            on_output_line=None,
        )

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs.get("stdout") is None
        assert call_kwargs.get("stderr") is None
        assert result.returncode == 0
        assert result.log_file is None

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_still_pipes_when_callback_set(self, mock_popen):
        """When on_output_line is provided, stdout/stderr must be PIPE'd."""
        _run_agent_blocking(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=None,
            iteration=1,
            on_output_line=lambda line, stream: None,
        )

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs.get("stdout") == subprocess.PIPE
        assert call_kwargs.get("stderr") == subprocess.PIPE

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_still_pipes_when_log_dir_set(self, mock_popen, tmp_path):
        """When log_dir is provided, stdout/stderr must be PIPE'd."""
        _run_agent_blocking(
            ["echo"],
            "prompt",
            timeout=None,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=None,
        )

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs.get("stdout") == subprocess.PIPE
        assert call_kwargs.get("stderr") == subprocess.PIPE

    def test_inherit_path_shows_output(self, capfd):
        """Real subprocess in inherit mode: child output reaches the parent's
        stdout, verifying the ``ralph run | cat`` scenario works.

        Uses ``capfd`` (fd-level capture) rather than ``capsys`` because
        the inherit path writes to the raw file descriptor, bypassing
        Python's ``sys.stdout``.
        """
        script = "import sys; print('visible-output')"

        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt="",
            timeout=10,
            log_dir=None,
            iteration=1,
            on_output_line=None,
        )

        assert result.returncode == 0
        captured = capfd.readouterr()
        assert "visible-output" in captured.out

    def test_callback_only_does_not_buffer(self, tmp_path):
        """When on_output_line is set but log_dir is None, lines should
        be forwarded to the callback but NOT accumulated (no unbounded
        buffering).  Verified indirectly: log_file is None (no buffer to
        write) but the callback still receives lines."""
        script = "import sys; print('line1'); print('line2')"
        received: list[str] = []

        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt="",
            timeout=10,
            log_dir=None,
            iteration=1,
            on_output_line=lambda line, stream: received.append(line),
        )

        assert result.returncode == 0
        assert result.log_file is None
        assert received == ["line1", "line2"]


class TestPumpStreamExceptionHandling:
    """Tests for _pump_stream resilience against callback and I/O errors."""

    def test_continues_when_callback_raises(self):
        """A callback that raises on the first line must not prevent
        subsequent lines from being buffered."""
        script = (
            "import sys; "
            "print('line1'); print('line2'); print('line3'); "
            "sys.stdout.flush()"
        )
        call_count = 0

        def raising_callback(line, stream):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")

        result = _run_agent_blocking(
            [sys.executable, "-u", "-c", script],
            prompt="",
            timeout=10,
            log_dir=None,
            iteration=1,
            on_output_line=raising_callback,
        )

        assert result.returncode == 0
        # The callback was called for all three lines, even though
        # the first invocation raised.
        assert call_count == 3

    def test_buffers_all_lines_when_callback_raises(self, tmp_path):
        """When logging is enabled, all lines must be captured in the log
        even if the callback raises on every single line."""
        script = "import sys; print('a'); print('b'); print('c'); sys.stdout.flush()"

        def always_raises(line, stream):
            raise ValueError("always fails")

        result = _run_agent_blocking(
            [sys.executable, "-u", "-c", script],
            prompt="",
            timeout=10,
            log_dir=tmp_path,
            iteration=1,
            on_output_line=always_raises,
        )

        assert result.returncode == 0
        assert result.log_file is not None
        log_text = result.log_file.read_text()
        assert "a" in log_text
        assert "b" in log_text
        assert "c" in log_text

    def test_exits_cleanly_on_closed_stream(self):
        """When the read end of a pipe is closed, the pump thread must
        exit within a short bounded join — not hang forever."""
        import os
        import threading

        read_fd, write_fd = os.pipe()
        read_file = os.fdopen(read_fd, "r")
        write_file = os.fdopen(write_fd, "w")

        buffer: list[str] = []
        thread = threading.Thread(
            target=_pump_stream,
            args=(read_file, buffer, "stdout", None),
            daemon=True,
        )
        thread.start()

        # Write a line so the thread is actively reading, then close.
        write_file.write("hello\n")
        write_file.flush()
        write_file.close()

        # The thread must exit promptly — EOF from the closed write end.
        thread.join(timeout=5)
        assert not thread.is_alive(), (
            "_pump_stream thread did not exit after pipe closed"
        )
        assert buffer == ["hello\n"]

        read_file.close()

    def test_exits_cleanly_on_valueerror(self):
        """A stream whose readline raises ValueError (e.g. closed file)
        must not crash the thread — it should exit cleanly."""
        import threading

        class ClosedStream:
            """Fake stream that raises ValueError on readline, simulating
            a concurrent close of the underlying file descriptor."""

            def readline(self):
                raise ValueError("I/O operation on closed file")

        buffer: list[str] = []
        thread = threading.Thread(
            target=_pump_stream,
            args=(ClosedStream(), buffer, "stdout", None),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), (
            "_pump_stream thread did not exit after ValueError"
        )
        assert buffer == []

    def test_exits_cleanly_on_oserror(self):
        """A stream whose readline raises OSError must not crash the thread."""
        import threading

        class BrokenStream:
            def readline(self):
                raise OSError("stream error")

        buffer: list[str] = []
        thread = threading.Thread(
            target=_pump_stream,
            args=(BrokenStream(), buffer, "stdout", None),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "_pump_stream thread did not exit after OSError"
        assert buffer == []


class TestBoundedReaderThreadJoins:
    """Tests for bounded reader-thread joins and pipe-closing in finally blocks.

    Validates that grandchild processes holding stdout/stderr pipes cannot
    hang the CLI, and that joins always happen in the finally block.
    """

    @pytest.mark.xfail(
        reason="Grandchild pipe inheritance behaves differently on Linux CI runners",
        strict=False,
    )
    def test_grandchild_inheriting_stdout_does_not_hang(self, tmp_path):
        """Spawn an agent that forks a grandchild inheriting stdout.

        The grandchild sleeps for 30s holding the pipe open.  The parent
        agent exits after 0.1s.  Without parent-side pipe closing and
        bounded joins, _run_agent_blocking would hang forever waiting for
        the grandchild's readline to return EOF.

        The fix (close parent-side pipes → bounded join) must let
        _run_agent_blocking return well within the 5s join timeout.
        """
        # The agent spawns a grandchild that inherits stdout and sleeps,
        # then the agent itself exits quickly.
        script = (
            "import subprocess, sys, time\n"
            "subprocess.Popen(\n"
            "    [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
            ")\n"
            "print('parent-output')\n"
            "sys.stdout.flush()\n"
            "time.sleep(0.1)\n"
        )

        start = time.monotonic()
        result = _run_agent_blocking(
            [sys.executable, "-c", script],
            prompt="",
            timeout=15,
            log_dir=tmp_path,
            iteration=1,
        )
        elapsed = time.monotonic() - start

        assert result.returncode == 0
        assert result.timed_out is False
        # Must complete well within the grandchild's 30-second sleep.
        # The parent-side pipe close forces EOF; 5s join timeout is the
        # upper bound.  Allow generous headroom for CI.
        assert elapsed < 12.0, (
            f"_run_agent_blocking took {elapsed:.1f}s — likely hung on"
            " grandchild holding stdout pipe"
        )

        # The parent's output should still be captured.
        assert result.log_file is not None
        log_text = result.log_file.read_text()
        assert "parent-output" in log_text

    def test_joins_happen_in_finally(self):
        """Inject an exception after threads start but before proc.wait.

        Both reader threads must have exited by the time the exception
        propagates — proving that the finally block joined them.
        """
        import threading

        stdout_thread_ref: list[threading.Thread] = []
        stderr_thread_ref: list[threading.Thread] = []

        # Script that produces output on both streams then exits.
        script = (
            "import sys; "
            "print('out'); sys.stdout.flush(); "
            "print('err', file=sys.stderr); sys.stderr.flush()"
        )

        class InjectErrorPopen(subprocess.Popen):
            """Popen subclass whose wait() raises RuntimeError on first call.

            This simulates an unexpected exception after the process has
            been started and reader threads are running.
            """

            _first_wait = True

            def wait(self, timeout=None):
                if InjectErrorPopen._first_wait:
                    InjectErrorPopen._first_wait = False
                    raise RuntimeError("injected error")
                return super().wait(timeout=timeout)

        with pytest.raises(RuntimeError, match="injected error"):
            with patch(
                MOCK_SUBPROCESS, side_effect=lambda *a, **kw: InjectErrorPopen(*a, **kw)
            ):
                # Capture thread references by patching _start_pump_thread
                original_start_pump = __import__(
                    "ralphify._agent", fromlist=["_start_pump_thread"]
                )._start_pump_thread

                def tracking_start_pump(stream, buffer, stream_name, on_output_line):
                    t = original_start_pump(stream, buffer, stream_name, on_output_line)
                    if stream_name == "stdout":
                        stdout_thread_ref.append(t)
                    else:
                        stderr_thread_ref.append(t)
                    return t

                with patch(
                    "ralphify._agent._start_pump_thread",
                    side_effect=tracking_start_pump,
                ):
                    _run_agent_blocking(
                        [sys.executable, "-c", script],
                        prompt="",
                        timeout=10,
                        log_dir=None,
                        iteration=1,
                        on_output_line=lambda line, stream: None,
                    )

        # After the exception propagated, the finally block must have
        # joined (and the pipe close must have unblocked) both threads.
        for ref, name in [(stdout_thread_ref, "stdout"), (stderr_thread_ref, "stderr")]:
            assert len(ref) == 1, f"expected 1 {name} thread, got {len(ref)}"
            thread = ref[0]
            # Give a small grace period — the finally block's join should
            # have already completed, but allow for thread scheduling.
            thread.join(timeout=2.0)
            assert not thread.is_alive(), (
                f"{name} reader thread still alive after exception — "
                "joins are not in the finally block"
            )
