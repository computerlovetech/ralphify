import subprocess
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from ralphify.cli import app, CONFIG_FILENAME, RALPH_TOML_TEMPLATE, PROMPT_TEMPLATE, _format_duration

runner = CliRunner()


def _ok(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=0)


def _fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=1)


class TestInit:
    def test_creates_config_and_prompt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / CONFIG_FILENAME).exists()
        assert (tmp_path / "PROMPT.md").exists()
        assert (tmp_path / CONFIG_FILENAME).read_text() == RALPH_TOML_TEMPLATE
        assert (tmp_path / "PROMPT.md").read_text() == PROMPT_TEMPLATE

    def test_refuses_overwrite_without_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text("existing")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert (tmp_path / CONFIG_FILENAME).read_text() == "existing"

    def test_force_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text("old")
        (tmp_path / "PROMPT.md").write_text("old")
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0
        assert (tmp_path / CONFIG_FILENAME).read_text() == RALPH_TOML_TEMPLATE
        assert (tmp_path / "PROMPT.md").read_text() == PROMPT_TEMPLATE

    def test_skips_prompt_if_exists_without_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "PROMPT.md").write_text("my custom prompt")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "PROMPT.md").read_text() == "my custom prompt"


class TestStatus:
    def test_errors_without_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_shows_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("my prompt")
        result = runner.invoke(app, ["status"])
        assert "claude" in result.output
        assert "PROMPT.md" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_ready_when_all_valid(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("my prompt")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Ready to run" in result.output

    @patch("ralphify.cli.shutil.which", return_value=None)
    def test_not_ready_when_command_missing(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("my prompt")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "not found on PATH" in result.output
        assert "Not ready" in result.output

    def test_not_ready_when_prompt_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("ralphify.cli.shutil.which", return_value=None)
    def test_reports_all_issues(self, mock_which, tmp_path, monkeypatch):
        """Reports both prompt and command issues at once."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Prompt file" in result.output
        assert "not found on PATH" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/myagent")
    def test_shows_prompt_size(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("x" * 150)
        result = runner.invoke(app, ["status"])
        assert "150 chars" in result.output


class TestRun:
    def test_errors_without_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_errors_with_missing_prompt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_runs_n_iterations(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("test prompt")

        result = runner.invoke(app, ["run", "-n", "3"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
        for call in mock_run.call_args_list:
            assert call.kwargs["input"] == "test prompt"
            assert call.kwargs["text"] is True

    @patch("ralphify.cli.subprocess.run")
    def test_reads_prompt_each_iteration(self, mock_run, tmp_path, monkeypatch):
        """Prompt file is re-read each iteration so edits take effect."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        prompt_path = tmp_path / "PROMPT.md"
        prompt_path.write_text("v1")

        call_count = 0

        def update_prompt(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                prompt_path.write_text("v2")
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = update_prompt

        result = runner.invoke(app, ["run", "-n", "2"])
        assert result.exit_code == 0
        assert mock_run.call_args_list[0].kwargs["input"] == "v1"
        assert mock_run.call_args_list[1].kwargs["input"] == "v2"

    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_custom_command_and_args(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = '[agent]\ncommand = "myagent"\nargs = ["--fast"]\nprompt = "PROMPT.md"\n'
        (tmp_path / CONFIG_FILENAME).write_text(config)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["myagent", "--fast"], input="go", text=True
        )

    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_shows_success_per_iteration(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "2"])
        assert result.exit_code == 0
        assert "Iteration 1 completed" in result.output
        assert "Iteration 2 completed" in result.output
        assert "2 succeeded" in result.output

    @patch("ralphify.cli.subprocess.run", side_effect=_fail)
    def test_continues_on_error_by_default(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "3"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
        assert "3 failed" in result.output

    @patch("ralphify.cli.subprocess.run", side_effect=_fail)
    def test_stop_on_error(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "5", "--stop-on-error"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1
        assert "Stopping due to --stop-on-error" in result.output
        assert "1 failed" in result.output

    @patch("ralphify.cli.subprocess.run")
    def test_mixed_success_and_failure(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0),
            subprocess.CompletedProcess(args=[], returncode=1),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]

        result = runner.invoke(app, ["run", "-n", "3"])
        assert result.exit_code == 0
        assert "2 succeeded" in result.output
        assert "1 failed" in result.output

    @patch("ralphify.cli.time.sleep")
    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_delay_between_iterations(self, mock_run, mock_sleep, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "3", "--delay", "5"])
        assert result.exit_code == 0
        # Delay between iterations, not after the last one
        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 5

    @patch("ralphify.cli.time.sleep")
    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_no_delay_with_single_iteration(self, mock_run, mock_sleep, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1", "--delay", "5"])
        assert result.exit_code == 0
        mock_sleep.assert_not_called()


class TestRunLogging:
    @patch("ralphify.cli.subprocess.run")
    def test_creates_log_files(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "logs"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="agent output\n", stderr=""
        )

        result = runner.invoke(app, ["run", "-n", "2", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        log_files = sorted(log_dir.iterdir())
        assert len(log_files) == 2
        assert log_files[0].name.startswith("001_")
        assert log_files[1].name.startswith("002_")

    @patch("ralphify.cli.subprocess.run")
    def test_log_file_contains_output(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "logs"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hello from agent\n", stderr="warning\n"
        )

        result = runner.invoke(app, ["run", "-n", "1", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        log_files = list(log_dir.iterdir())
        content = log_files[0].read_text()
        assert "hello from agent" in content
        assert "warning" in content

    @patch("ralphify.cli.subprocess.run")
    def test_log_dir_created_automatically(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "nested" / "log" / "dir"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="out\n", stderr=""
        )

        result = runner.invoke(app, ["run", "-n", "1", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        assert log_dir.exists()
        assert len(list(log_dir.iterdir())) == 1

    @patch("ralphify.cli.subprocess.run", side_effect=_ok)
    def test_no_log_files_without_flag(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        # No .ralph or logs directory should be created
        assert not (tmp_path / ".ralph").exists()
        assert not (tmp_path / "logs").exists()

    @patch("ralphify.cli.subprocess.run")
    def test_log_shows_path_in_status(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "logs"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="out\n", stderr=""
        )

        result = runner.invoke(app, ["run", "-n", "1", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        assert "001_" in result.output
        assert ".log" in result.output

    @patch("ralphify.cli.subprocess.run")
    def test_log_uses_capture_output(self, mock_run, tmp_path, monkeypatch):
        """When logging, subprocess.run is called with capture_output=True."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "logs"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        runner.invoke(app, ["run", "-n", "1", "--log-dir", str(log_dir)])
        assert mock_run.call_args.kwargs["capture_output"] is True


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
