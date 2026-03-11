import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ralphify import __version__
from ralphify._frontmatter import parse_frontmatter
from ralphify.checks import Check, CheckResult
from ralphify.contexts import Context, ContextResult
from ralphify.cli import app, CONFIG_FILENAME, RALPH_TOML_TEMPLATE, PROMPT_TEMPLATE
from ralphify.engine import _format_duration

runner = CliRunner()


def _ok(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=0)


def _fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=args, returncode=1)


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert f"ralphify {__version__}" in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert f"ralphify {__version__}" in result.output


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

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
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

    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_custom_command_and_args(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = '[agent]\ncommand = "myagent"\nargs = ["--fast"]\nprompt = "PROMPT.md"\n'
        (tmp_path / CONFIG_FILENAME).write_text(config)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["myagent", "--fast"], input="go", text=True, timeout=None, capture_output=False
        )

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_shows_success_per_iteration(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "2"])
        assert result.exit_code == 0
        assert "Iteration 1 completed" in result.output
        assert "Iteration 2 completed" in result.output
        assert "2 succeeded" in result.output

    @patch("ralphify.engine.subprocess.run", side_effect=_fail)
    def test_continues_on_error_by_default(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "3"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
        assert "3 failed" in result.output

    @patch("ralphify.engine.subprocess.run", side_effect=_fail)
    def test_stop_on_error(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "5", "--stop-on-error"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1
        assert "Stopping due to --stop-on-error" in result.output
        assert "1 failed" in result.output

    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.time.sleep")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
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

    @patch("ralphify.engine.time.sleep")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_no_delay_with_single_iteration(self, mock_run, mock_sleep, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1", "--delay", "5"])
        assert result.exit_code == 0
        mock_sleep.assert_not_called()


class TestRunAdHocPrompt:
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_uses_provided_prompt_text(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)

        result = runner.invoke(app, ["run", "-n", "1", "-p", "do something"])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["input"] == "do something"

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_skips_prompt_file_check(self, mock_run, tmp_path, monkeypatch):
        """Works without PROMPT.md when -p is provided."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        # No PROMPT.md created

        result = runner.invoke(app, ["run", "-n", "1", "-p", "ad-hoc prompt"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_contexts_and_instructions_resolve_with_ad_hoc_prompt(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        _setup_instruction(tmp_path, "style", content="Use black formatting.")

        result = runner.invoke(app, ["run", "-n", "1", "-p", "Base.\n\n{{ instructions }}"])
        assert result.exit_code == 0
        prompt_sent = mock_run.call_args.kwargs["input"]
        assert "Use black formatting." in prompt_sent
        assert "{{ instructions }}" not in prompt_sent


class TestRunPromptFile:
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_prompt_file_overrides_config(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("default prompt")
        (tmp_path / "alt.md").write_text("alternate prompt")

        result = runner.invoke(app, ["run", "-n", "1", "--prompt-file", "alt.md"])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["input"] == "alternate prompt"

    def test_prompt_file_missing_exits(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("default prompt")

        result = runner.invoke(app, ["run", "-n", "1", "--prompt-file", "nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_prompt_text_overrides_prompt_file(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "alt.md").write_text("alternate prompt")

        result = runner.invoke(app, ["run", "-n", "1", "-p", "inline text", "--prompt-file", "alt.md"])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["input"] == "inline text"


class TestRunLogging:
    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_no_log_files_without_flag(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        # No .ralph or logs directory should be created
        assert not (tmp_path / ".ralph").exists()
        assert not (tmp_path / "logs").exists()

    @patch("ralphify.engine.subprocess.run")
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

    @patch("ralphify.engine.subprocess.run")
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


class TestRunTimeout:
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_timeout_passed_to_subprocess(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1", "--timeout", "30"])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["timeout"] == 30

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_no_timeout_by_default(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["timeout"] is None

    @patch("ralphify.engine.subprocess.run")
    def test_timeout_counts_as_failure(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)

        result = runner.invoke(app, ["run", "-n", "1", "--timeout", "10"])
        assert result.exit_code == 0
        assert "timed out" in result.output
        assert "1 failed" in result.output
        assert "1 timed out" in result.output

    @patch("ralphify.engine.subprocess.run")
    def test_timeout_continues_by_default(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd="claude", timeout=10),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]

        result = runner.invoke(app, ["run", "-n", "2", "--timeout", "10"])
        assert result.exit_code == 0
        assert mock_run.call_count == 2
        assert "1 succeeded" in result.output
        assert "1 failed" in result.output

    @patch("ralphify.engine.subprocess.run")
    def test_timeout_stops_with_stop_on_error(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)

        result = runner.invoke(app, ["run", "-n", "3", "--timeout", "10", "--stop-on-error"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1
        assert "Stopping due to --stop-on-error" in result.output

    @patch("ralphify.engine.subprocess.run")
    def test_timeout_with_logging(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")
        log_dir = tmp_path / "logs"

        exc = subprocess.TimeoutExpired(cmd="claude", timeout=10)
        exc.stdout = b"partial output\n"
        exc.stderr = b""
        mock_run.side_effect = exc

        result = runner.invoke(app, ["run", "-n", "1", "--timeout", "10", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        log_files = list(log_dir.iterdir())
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "partial output" in content

    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_timeout_shows_in_header(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("go")

        result = runner.invoke(app, ["run", "-n", "1", "--timeout", "300"])
        assert result.exit_code == 0
        assert "5m 0s per iteration" in result.output


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


def _setup_check(tmp_path, name="ruff-lint", command="ruff check .", enabled=True,
                 body="Fix lint errors."):
    """Helper to create a check directory with CHECK.md."""
    check_dir = tmp_path / ".ralph" / "checks" / name
    check_dir.mkdir(parents=True, exist_ok=True)
    enabled_str = "true" if enabled else "false"
    (check_dir / "CHECK.md").write_text(
        f"---\ncommand: {command}\nenabled: {enabled_str}\n---\n{body}"
    )
    return check_dir


class TestStatusChecks:
    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_no_checks_dir(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "none" in result.output
        assert "Ready to run" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_found_checks(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_check(tmp_path, "ruff-lint", "ruff check .")
        _setup_check(tmp_path, "typecheck", "mypy .")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output
        assert "ruff-lint" in result.output
        assert "typecheck" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_disabled_check_display(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_check(tmp_path, "enabled-check", "echo ok", enabled=True)
        _setup_check(tmp_path, "disabled-check", "echo skip", enabled=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output


def _make_check_result(name="lint", passed=True, exit_code=0, output="ok\n",
                       timed_out=False, failure_instruction=""):
    """Helper to create a CheckResult for tests."""
    check = Check(
        name=name,
        path=Path("/fake"),
        command="echo",
        script=None,
        failure_instruction=failure_instruction,
    )
    return CheckResult(
        check=check,
        passed=passed,
        exit_code=exit_code,
        output=output,
        timed_out=timed_out,
    )


class TestRunChecks:
    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_checks_run_after_iteration(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("test prompt")
        _setup_check(tmp_path, "lint", "ruff check .")

        mock_run_checks.return_value = [_make_check_result()]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        assert mock_run_checks.call_count == 1
        assert "1 passed" in result.output

    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_failure_text_appended_to_next_prompt(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("base prompt")
        _setup_check(tmp_path, "lint", "ruff check .", body="Fix lint errors.")

        mock_run_checks.return_value = [
            _make_check_result(
                passed=False, exit_code=1, output="error: bad code\n",
                failure_instruction="Fix lint errors.",
            )
        ]

        result = runner.invoke(app, ["run", "-n", "2"])
        assert result.exit_code == 0

        # First iteration gets base prompt only
        first_call_input = mock_agent.call_args_list[0].kwargs["input"]
        assert first_call_input == "base prompt"

        # Second iteration gets check failure appended
        second_call_input = mock_agent.call_args_list[1].kwargs["input"]
        assert "base prompt" in second_call_input
        assert "Check Failures" in second_call_input
        assert "bad code" in second_call_input
        assert "Fix lint errors." in second_call_input

    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_fail)
    def test_checks_run_even_when_agent_fails(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_check(tmp_path, "lint", "ruff check .")

        mock_run_checks.return_value = [_make_check_result()]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        assert mock_run_checks.call_count == 1

    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_check_failure_does_not_trigger_stop_on_error(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_check(tmp_path, "lint", "ruff check .")

        mock_run_checks.return_value = [
            _make_check_result(passed=False, exit_code=1, output="fail\n")
        ]

        # Agent succeeds, but check fails — should NOT stop
        result = runner.invoke(app, ["run", "-n", "2", "--stop-on-error"])
        assert result.exit_code == 0
        # Both iterations should run (agent didn't fail)
        assert mock_agent.call_count == 2

    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_disabled_checks_not_run(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_check(tmp_path, "enabled", "echo ok", enabled=True)
        _setup_check(tmp_path, "disabled", "echo skip", enabled=False)

        mock_run_checks.return_value = [_make_check_result()]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        # run_all_checks is called with only enabled checks
        checks_arg = mock_run_checks.call_args.args[0]
        assert len(checks_arg) == 1
        assert checks_arg[0].name == "enabled"


class TestNewCheck:
    def test_creates_check_directory_and_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "check", "my-lint"])
        assert result.exit_code == 0
        check_md = tmp_path / ".ralph" / "checks" / "my-lint" / "CHECK.md"
        assert check_md.exists()
        content = check_md.read_text()
        assert "command:" in content
        assert "timeout:" in content
        assert "enabled:" in content

    def test_refuses_existing_check(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        check_dir = tmp_path / ".ralph" / "checks" / "my-lint"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("original content")

        result = runner.invoke(app, ["new", "check", "my-lint"])
        assert result.exit_code == 1
        assert "already exists" in result.output
        assert (check_dir / "CHECK.md").read_text() == "original content"

    def test_creates_ralph_dirs_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".ralph").exists()
        result = runner.invoke(app, ["new", "check", "fresh"])
        assert result.exit_code == 0
        assert (tmp_path / ".ralph" / "checks" / "fresh" / "CHECK.md").exists()

    def test_default_body_stripped_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "check", "empty-body"])
        assert result.exit_code == 0
        check_md = tmp_path / ".ralph" / "checks" / "empty-body" / "CHECK.md"
        _, body = parse_frontmatter(check_md.read_text())
        assert body == ""


def _setup_instruction(tmp_path, name="coding-style", enabled=True, content="Use type hints."):
    """Helper to create an instruction directory with INSTRUCTION.md."""
    inst_dir = tmp_path / ".ralph" / "instructions" / name
    inst_dir.mkdir(parents=True, exist_ok=True)
    enabled_str = "true" if enabled else "false"
    (inst_dir / "INSTRUCTION.md").write_text(
        f"---\nenabled: {enabled_str}\n---\n{content}"
    )
    return inst_dir


class TestNewInstruction:
    def test_creates_instruction_directory_and_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "instruction", "my-style"])
        assert result.exit_code == 0
        inst_md = tmp_path / ".ralph" / "instructions" / "my-style" / "INSTRUCTION.md"
        assert inst_md.exists()
        content = inst_md.read_text()
        assert "enabled:" in content

    def test_refuses_existing_instruction(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        inst_dir = tmp_path / ".ralph" / "instructions" / "my-style"
        inst_dir.mkdir(parents=True)
        (inst_dir / "INSTRUCTION.md").write_text("original content")

        result = runner.invoke(app, ["new", "instruction", "my-style"])
        assert result.exit_code == 1
        assert "already exists" in result.output
        assert (inst_dir / "INSTRUCTION.md").read_text() == "original content"

    def test_creates_ralph_dirs_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".ralph").exists()
        result = runner.invoke(app, ["new", "instruction", "fresh"])
        assert result.exit_code == 0
        assert (tmp_path / ".ralph" / "instructions" / "fresh" / "INSTRUCTION.md").exists()

    def test_default_body_stripped_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "instruction", "empty-body"])
        assert result.exit_code == 0
        inst_md = tmp_path / ".ralph" / "instructions" / "empty-body" / "INSTRUCTION.md"
        _, body = parse_frontmatter(inst_md.read_text())
        assert body == ""


class TestStatusInstructions:
    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_no_instructions_shows_none(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Instructions:" in result.output
        assert "none" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_found_instructions_shown(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_instruction(tmp_path, "coding-style", content="Use type hints.")
        _setup_instruction(tmp_path, "testing", content="Write tests first.")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output
        assert "coding-style" in result.output
        assert "testing" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_disabled_instruction_display(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_instruction(tmp_path, "enabled-inst", enabled=True)
        _setup_instruction(tmp_path, "disabled-inst", enabled=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output


class TestRunInstructions:
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_instructions_injected_into_prompt(self, mock_run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("Base prompt.\n\n{{ instructions }}")
        _setup_instruction(tmp_path, "style", content="Use black formatting.")

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        prompt_sent = mock_run.call_args.kwargs["input"]
        assert "Use black formatting." in prompt_sent
        assert "{{ instructions }}" not in prompt_sent

    @patch("ralphify.engine.run_all_checks")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_instructions_resolved_before_check_failures(self, mock_agent, mock_run_checks, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("Base.\n\n{{ instructions }}")
        _setup_instruction(tmp_path, "style", content="Use black.")
        _setup_check(tmp_path, "lint", "ruff check .", body="Fix lint.")

        mock_run_checks.return_value = [
            _make_check_result(passed=False, exit_code=1, output="err\n", failure_instruction="Fix lint.")
        ]

        result = runner.invoke(app, ["run", "-n", "2"])
        assert result.exit_code == 0

        # Second iteration: instructions resolved + check failures appended
        second_input = mock_agent.call_args_list[1].kwargs["input"]
        assert "Use black." in second_input
        assert "Check Failures" in second_input
        # Instructions should come before check failures
        inst_pos = second_input.index("Use black.")
        fail_pos = second_input.index("Check Failures")
        assert inst_pos < fail_pos


def _setup_context(tmp_path, name="git-history", command="git log --oneline -5",
                   enabled=True, body=""):
    """Helper to create a context directory with CONTEXT.md."""
    ctx_dir = tmp_path / ".ralph" / "contexts" / name
    ctx_dir.mkdir(parents=True, exist_ok=True)
    enabled_str = "true" if enabled else "false"
    parts = [f"---\nenabled: {enabled_str}"]
    if command:
        parts[0] = f"---\ncommand: {command}\nenabled: {enabled_str}"
    parts.append(f"---\n{body}")
    (ctx_dir / "CONTEXT.md").write_text("\n".join(parts))
    return ctx_dir


class TestNewContext:
    def test_creates_context_directory_and_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "context", "git-history"])
        assert result.exit_code == 0
        ctx_md = tmp_path / ".ralph" / "contexts" / "git-history" / "CONTEXT.md"
        assert ctx_md.exists()
        content = ctx_md.read_text()
        assert "command:" in content
        assert "timeout:" in content
        assert "enabled:" in content

    def test_refuses_existing_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx_dir = tmp_path / ".ralph" / "contexts" / "git-history"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text("original content")

        result = runner.invoke(app, ["new", "context", "git-history"])
        assert result.exit_code == 1
        assert "already exists" in result.output
        assert (ctx_dir / "CONTEXT.md").read_text() == "original content"

    def test_creates_ralph_dirs_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".ralph").exists()
        result = runner.invoke(app, ["new", "context", "fresh"])
        assert result.exit_code == 0
        assert (tmp_path / ".ralph" / "contexts" / "fresh" / "CONTEXT.md").exists()

    def test_default_body_stripped_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "context", "empty-body"])
        assert result.exit_code == 0
        ctx_md = tmp_path / ".ralph" / "contexts" / "empty-body" / "CONTEXT.md"
        _, body = parse_frontmatter(ctx_md.read_text())
        assert body == ""


class TestStatusContexts:
    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_no_contexts_shows_none(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Contexts:" in result.output
        assert "none" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_found_contexts_shown(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_context(tmp_path, "git-history", "git log --oneline -5")
        _setup_context(tmp_path, "coverage", "coverage report")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output
        assert "git-history" in result.output
        assert "coverage" in result.output

    @patch("ralphify.cli.shutil.which", return_value="/usr/bin/claude")
    def test_disabled_context_display(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_context(tmp_path, "enabled-ctx", "echo ok", enabled=True)
        _setup_context(tmp_path, "disabled-ctx", "echo skip", enabled=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "2 found" in result.output


class TestRunContexts:
    @patch("ralphify.engine.run_all_contexts")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_contexts_injected_into_prompt(self, mock_agent, mock_run_contexts, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("Base.\n\n{{ contexts }}")
        _setup_context(tmp_path, "git-log", "git log --oneline -5")

        ctx = Context(name="git-log", path=Path("/fake"), command="git log", enabled=True)
        mock_run_contexts.return_value = [
            ContextResult(context=ctx, output="abc123 fix bug\n", success=True)
        ]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        prompt_sent = mock_agent.call_args.kwargs["input"]
        assert "abc123 fix bug" in prompt_sent
        assert "{{ contexts }}" not in prompt_sent

    @patch("ralphify.engine.run_all_contexts")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_contexts_resolved_before_instructions(self, mock_agent, mock_run_contexts, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("Base.\n\n{{ contexts }}\n\n{{ instructions }}")
        _setup_context(tmp_path, "git-log", "git log --oneline -5")
        _setup_instruction(tmp_path, "style", content="Use black.")

        ctx = Context(name="git-log", path=Path("/fake"), command="git log", enabled=True)
        mock_run_contexts.return_value = [
            ContextResult(context=ctx, output="abc123 fix\n", success=True)
        ]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        prompt_sent = mock_agent.call_args.kwargs["input"]
        assert "abc123 fix" in prompt_sent
        assert "Use black." in prompt_sent
        # Contexts should come before instructions
        ctx_pos = prompt_sent.index("abc123 fix")
        inst_pos = prompt_sent.index("Use black.")
        assert ctx_pos < inst_pos

    @patch("ralphify.engine.run_all_contexts")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_disabled_contexts_not_run(self, mock_agent, mock_run_contexts, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("prompt")
        _setup_context(tmp_path, "enabled", "echo ok", enabled=True)
        _setup_context(tmp_path, "disabled", "echo skip", enabled=False)

        ctx = Context(name="enabled", path=Path("/fake"), command="echo ok", enabled=True)
        mock_run_contexts.return_value = [
            ContextResult(context=ctx, output="ok\n", success=True)
        ]

        result = runner.invoke(app, ["run", "-n", "1"])
        assert result.exit_code == 0
        # run_all_contexts called with only enabled contexts
        contexts_arg = mock_run_contexts.call_args.args[0]
        assert len(contexts_arg) == 1
        assert contexts_arg[0].name == "enabled"

    @patch("ralphify.engine.run_all_contexts")
    @patch("ralphify.engine.subprocess.run", side_effect=_ok)
    def test_contexts_run_each_iteration(self, mock_agent, mock_run_contexts, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / CONFIG_FILENAME).write_text(RALPH_TOML_TEMPLATE)
        (tmp_path / "PROMPT.md").write_text("{{ contexts }}")
        _setup_context(tmp_path, "info", "echo hi")

        ctx = Context(name="info", path=Path("/fake"), command="echo hi", enabled=True)
        mock_run_contexts.return_value = [
            ContextResult(context=ctx, output="hi\n", success=True)
        ]

        result = runner.invoke(app, ["run", "-n", "3"])
        assert result.exit_code == 0
        assert mock_run_contexts.call_count == 3
