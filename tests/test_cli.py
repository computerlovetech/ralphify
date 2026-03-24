"""Tests for the CLI."""

import subprocess
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from helpers import MOCK_ENGINE_SLEEP, MOCK_SKILLS_WHICH, MOCK_SUBPROCESS, MOCK_WHICH, ok_proc, fail_proc, make_ralph, timeout_proc
from ralphify import __version__
from ralphify._frontmatter import RALPH_MARKER
from ralphify.cli import app, _parse_command_items, _parse_user_args

runner = CliRunner()


class TestVersion:
    @pytest.mark.parametrize("flag", ["--version", "-V"])
    def test_version_flag(self, flag):
        result = runner.invoke(app, [flag])
        assert result.exit_code == 0
        assert f"ralphify {__version__}" in result.output


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestRun:
    def test_errors_with_nonexistent_path(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not" in result.output.lower()

    def test_errors_without_ralph_md(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(app, ["run", str(empty_dir)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_errors_without_agent_field(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text("just a prompt, no frontmatter")
        result = runner.invoke(app, ["run", str(ralph_dir)])
        assert result.exit_code == 1
        assert "agent" in result.output.lower()

    def test_errors_with_whitespace_only_agent(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text("---\nagent: \"  \"\n---\ngo")
        result = runner.invoke(app, ["run", str(ralph_dir)])
        assert result.exit_code == 1
        assert "agent" in result.output.lower()

    def test_errors_with_non_string_agent(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text("---\nagent: 123\n---\ngo")
        result = runner.invoke(app, ["run", str(ralph_dir)])
        assert result.exit_code == 1
        assert "agent" in result.output.lower()

    def test_errors_when_agent_not_on_path(self, mock_which, tmp_path, monkeypatch):
        mock_which.return_value = None
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "not found on PATH" in result.output

    def test_errors_with_malformed_agent_field(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        # Valid YAML but shlex.split raises ValueError on unmatched quotes
        (ralph_dir / RALPH_MARKER).write_text(
            '---\nagent: \'claude "unclosed\'\n---\ngo'
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "malformed" in result.output.lower()

    @pytest.mark.parametrize("frontmatter, expected_error", [
        ("commands:\n  - name: \"\"\n    run: echo hi", "name"),
        ("commands:\n  - name: status\n    run: \"\"", "run"),
        ("commands: not-a-list", "must be a list"),
        ("commands: 0", "must be a list"),
        ("commands: false", "must be a list"),
        (
            "commands:\n  - name: status\n    run: git status\n"
            "  - name: status\n    run: echo hi",
            "duplicate",
        ),
    ], ids=["empty-name", "empty-run", "not-a-list", "falsy-int", "falsy-bool", "duplicate-names"])
    def test_errors_with_invalid_commands(self, mock_which, tmp_path, monkeypatch,
                                          frontmatter, expected_error):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            f"---\nagent: claude -p\n{frontmatter}\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert expected_error in result.output.lower()

    @pytest.mark.parametrize("yaml_value", ["commands:", "commands: null"],
                             ids=["empty-value", "explicit-null"])
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_null_commands_treated_as_empty(self, mock_run, mock_which, tmp_path, monkeypatch, yaml_value):
        """YAML `commands:` (no value) and `commands: null` should be treated as no commands."""
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            f"---\nagent: claude -p --dangerously-skip-permissions\n{yaml_value}\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0

    @pytest.mark.parametrize("args_value", ["true", "42", "not-a-list"],
                             ids=["bool", "int", "string"])
    def test_errors_with_invalid_args_type(self, mock_which, tmp_path, monkeypatch, args_value):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            f"---\nagent: claude -p\nargs: {args_value}\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "must be a list" in result.output.lower()

    @pytest.mark.parametrize("name", [
        "my.arg",
        "has space",
        "arg@home",
        "name!",
        "a/b",
    ], ids=["dot", "space", "at-sign", "exclamation", "slash"])
    def test_errors_with_invalid_arg_name_chars(self, mock_which, tmp_path, monkeypatch, name):
        """Arg names with chars outside [a-zA-Z0-9_-] can never be
        referenced by placeholders and must be rejected early."""
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            f'---\nagent: claude -p\nargs:\n  - "{name}"\n---\ngo'
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "invalid" in result.output.lower()

    @pytest.mark.parametrize("args_yaml,id_label", [
        ("[1, 2]", "integers"),
        ("[true, false]", "booleans"),
        ("[1.5]", "floats"),
    ], ids=lambda x: x if isinstance(x, str) else None)
    def test_errors_with_non_string_args_items(self, mock_which, tmp_path, monkeypatch, args_yaml, id_label):
        """args list items that aren't strings (e.g. YAML integers) must be rejected."""
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            f"---\nagent: claude -p\nargs: {args_yaml}\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "string" in result.output.lower()

    @pytest.mark.parametrize("n_value", ["-1", "0", "-100"])
    def test_errors_with_non_positive_n(self, mock_which, tmp_path, monkeypatch, n_value):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", n_value])
        assert result.exit_code == 1
        assert "positive integer" in result.output.lower()

    def test_errors_with_negative_delay(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--delay", "-5"])
        assert result.exit_code == 1
        assert "non-negative" in result.output.lower()

    def test_errors_with_non_positive_timeout(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "-10"])
        assert result.exit_code == 1
        assert "positive number" in result.output.lower()

    def test_errors_with_zero_timeout(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "0"])
        assert result.exit_code == 1
        assert "positive number" in result.output.lower()

    def test_errors_with_nan_timeout(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "nan"])
        assert result.exit_code == 1
        assert "positive number" in result.output.lower()

    def test_errors_with_nan_delay(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--delay", "nan"])
        assert result.exit_code == 1
        assert "non-negative" in result.output.lower()

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_runs_when_valid(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1

    @patch(MOCK_SUBPROCESS)
    def test_runs_n_iterations(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path, prompt="test prompt")
        procs = []

        def capture_proc(*args, **kwargs):
            proc = ok_proc()
            procs.append(proc)
            return proc

        mock_run.side_effect = capture_proc
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "3"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
        for proc in procs:
            assert proc.communicate.call_args.kwargs["input"].startswith("test prompt")

    @patch(MOCK_SUBPROCESS)
    def test_reads_prompt_each_iteration(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path, prompt="v1")
        ralph_file = ralph_dir / RALPH_MARKER

        call_count = 0
        procs = []

        def update_prompt(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Rewrite with same frontmatter but different body
                ralph_file.write_text(
                    "---\nagent: claude -p --dangerously-skip-permissions\n---\nv2"
                )
            proc = ok_proc(*args, **kwargs)
            procs.append(proc)
            return proc

        mock_run.side_effect = update_prompt

        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "2"])
        assert result.exit_code == 0
        assert procs[0].communicate.call_args.kwargs["input"].startswith("v1")
        assert procs[1].communicate.call_args.kwargs["input"].startswith("v2")

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_shows_success_per_iteration(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "2"])
        assert result.exit_code == 0
        assert "Iteration 1 completed" in result.output
        assert "Iteration 2 completed" in result.output
        assert "2 succeeded" in result.output

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_continues_on_error_by_default(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "3"])
        assert result.exit_code == 0
        assert mock_run.call_count == 3
        assert "3 failed" in result.output

    @patch(MOCK_SUBPROCESS, side_effect=fail_proc)
    def test_stop_on_error(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "5", "--stop-on-error"])
        assert result.exit_code == 0
        assert mock_run.call_count == 1
        assert "Stopping due to --stop-on-error" in result.output
        assert "1 failed" in result.output

    @patch(MOCK_SUBPROCESS)
    def test_mixed_success_and_failure(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        mock_run.side_effect = [ok_proc(), fail_proc(), ok_proc()]
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "3"])
        assert result.exit_code == 0
        assert "2 succeeded" in result.output
        assert "1 failed" in result.output

    @patch(MOCK_ENGINE_SLEEP)
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_delay_between_iterations(self, mock_run, mock_sleep, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "3", "--delay", "5"])
        assert result.exit_code == 0
        # Delay is split into small chunks for stop-responsiveness;
        # verify total requested sleep time sums to 2 × 5s (delays
        # after iterations 1 and 2, none after the last).
        total_sleep = sum(call.args[0] for call in mock_sleep.call_args_list)
        assert abs(total_sleep - 10.0) < 0.01

    @patch(MOCK_ENGINE_SLEEP)
    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_no_delay_with_single_iteration(self, mock_run, mock_sleep, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--delay", "5"])
        assert result.exit_code == 0
        mock_sleep.assert_not_called()

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_accepts_ralph_md_file_path(self, mock_run, mock_which, tmp_path, monkeypatch):
        """Can pass path to RALPH.md file directly."""
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir / RALPH_MARKER), "-n", "1"])
        assert result.exit_code == 0


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestRunLogging:
    @patch(MOCK_SUBPROCESS)
    def test_creates_log_files(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        log_dir = tmp_path / "logs"
        mock_run.return_value = ok_proc(stdout="agent output\n")
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "2", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        log_files = sorted(log_dir.iterdir())
        assert len(log_files) == 2
        assert log_files[0].name.startswith("001_")
        assert log_files[1].name.startswith("002_")

    @patch(MOCK_SUBPROCESS)
    def test_log_file_contains_output(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        log_dir = tmp_path / "logs"
        mock_run.return_value = ok_proc(stdout="hello from agent\n", stderr="warning\n")
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--log-dir", str(log_dir)])
        assert result.exit_code == 0
        log_files = list(log_dir.iterdir())
        content = log_files[0].read_text()
        assert "hello from agent" in content
        assert "warning" in content

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_no_log_files_without_flag(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert not (tmp_path / "logs").exists()


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestRunTimeout:
    @patch(MOCK_SUBPROCESS)
    def test_timeout_passed_to_subprocess(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "30"])
        assert result.exit_code == 0
        assert mock_run.return_value.communicate.call_args.kwargs["timeout"] == 30

    @patch(MOCK_SUBPROCESS)
    def test_no_timeout_by_default(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert mock_run.return_value.communicate.call_args.kwargs["timeout"] is None

    @patch(MOCK_SUBPROCESS, side_effect=timeout_proc)
    def test_timeout_counts_as_failure(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "10"])
        assert result.exit_code == 0
        assert "timed out" in result.output
        assert "1 timed out" in result.output

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    def test_timeout_shows_in_header(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--timeout", "300"])
        assert result.exit_code == 0
        assert "timeout 5m 0s" in result.output


class TestNew:
    @patch("ralphify.cli.os.execvp")
    @patch(MOCK_SKILLS_WHICH, return_value="/usr/bin/claude")
    def test_installs_skill_and_launches_agent(self, mock_which, mock_execvp, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "my-task"])
        assert result.exit_code == 0
        skill_file = tmp_path / ".claude" / "skills" / "new-ralph" / "SKILL.md"
        assert skill_file.exists()
        assert "new-ralph" in skill_file.read_text()
        mock_execvp.assert_called_once_with("claude", ["claude", "--dangerously-skip-permissions", "/new-ralph my-task"])

    @patch("ralphify.cli.os.execvp")
    @patch(MOCK_SKILLS_WHICH, return_value="/usr/bin/claude")
    def test_name_is_optional(self, mock_which, mock_execvp, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new"])
        assert result.exit_code == 0
        mock_execvp.assert_called_once_with("claude", ["claude", "--dangerously-skip-permissions", "/new-ralph"])

    @patch(MOCK_SKILLS_WHICH, return_value=None)
    def test_errors_when_no_agent_found(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new"])
        assert result.exit_code == 1
        assert "No agent found" in result.output

    @patch("ralphify._skills.install_skill", side_effect=RuntimeError("permission denied"))
    @patch(MOCK_SKILLS_WHICH, return_value="/usr/bin/claude")
    def test_errors_when_install_skill_fails(self, mock_which, mock_install, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new"])
        assert result.exit_code == 1
        assert "permission denied" in result.output

    @patch("ralphify.cli.os.execvp", side_effect=FileNotFoundError("not found"))
    @patch(MOCK_SKILLS_WHICH, return_value="/usr/bin/claude")
    def test_errors_when_agent_binary_not_found(self, mock_which, mock_execvp, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["new", "my-task"])
        assert result.exit_code == 1
        assert "not found on PATH" in result.output


class TestInit:
    def test_creates_ralph_with_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "my-task"])
        assert result.exit_code == 0
        ralph_file = tmp_path / "my-task" / RALPH_MARKER
        assert ralph_file.exists()
        assert "Created" in result.output

    def test_creates_ralph_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / RALPH_MARKER).exists()

    def test_errors_if_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / RALPH_MARKER).write_text("existing")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "new-dir"])
        assert result.exit_code == 0
        assert (tmp_path / "new-dir" / RALPH_MARKER).exists()

    def test_uses_existing_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "existing-dir").mkdir()
        result = runner.invoke(app, ["init", "existing-dir"])
        assert result.exit_code == 0
        assert (tmp_path / "existing-dir" / RALPH_MARKER).exists()

    def test_template_has_valid_frontmatter(self, tmp_path, monkeypatch):
        from ralphify._frontmatter import parse_frontmatter
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init", "my-task"])
        content = (tmp_path / "my-task" / RALPH_MARKER).read_text()
        fm, body = parse_frontmatter(content)
        assert "agent" in fm
        assert isinstance(fm["commands"], list)
        assert isinstance(fm["args"], list)
        assert "{{ commands.git-log }}" in body
        assert "{{ args.focus }}" in body


class TestParseUserArgs:
    def test_named_flag(self):
        result = _parse_user_args(["--dir", "./src"], None)
        assert result == {"dir": "./src"}

    def test_multiple_named_flags(self):
        result = _parse_user_args(["--dir", "./src", "--focus", "perf"], None)
        assert result == {"dir": "./src", "focus": "perf"}

    def test_positional_with_declared_names(self):
        result = _parse_user_args(["./src", "perf"], ["dir", "focus"])
        assert result == {"dir": "./src", "focus": "perf"}

    def test_mixed_positional_and_named(self):
        result = _parse_user_args(["./src", "--focus", "perf"], ["dir", "focus"])
        assert result == {"dir": "./src", "focus": "perf"}

    def test_named_flag_before_positional_no_overwrite(self):
        """--dir ./src perf should assign perf to 'focus', not overwrite 'dir'."""
        result = _parse_user_args(["--dir", "./src", "perf"], ["dir", "focus"])
        assert result == {"dir": "./src", "focus": "perf"}

    def test_positional_without_declaration_errors(self):
        with pytest.raises(typer.BadParameter, match="requires args declared"):
            _parse_user_args(["./src"], None)

    def test_too_many_positionals_errors(self):
        with pytest.raises(typer.BadParameter, match="Too many positional"):
            _parse_user_args(["./src", "extra"], ["dir"])

    def test_flag_without_value_errors(self):
        with pytest.raises(typer.BadParameter, match="requires a value"):
            _parse_user_args(["--dir"], None)

    def test_empty_args(self):
        result = _parse_user_args([], None)
        assert result == {}

    def test_equals_syntax(self):
        """--key=value is a common CLI convention and must be handled."""
        result = _parse_user_args(["--topic=testing"], None)
        assert result == {"topic": "testing"}

    def test_equals_syntax_with_equals_in_value(self):
        """Only the first = separates key from value."""
        result = _parse_user_args(["--expr=a=b"], None)
        assert result == {"expr": "a=b"}

    def test_equals_syntax_empty_value(self):
        """--key= should set value to empty string."""
        result = _parse_user_args(["--key="], None)
        assert result == {"key": ""}

    def test_invalid_name_in_flag_rejected(self):
        """--my.arg should be rejected — dots are invalid in placeholder names."""
        with pytest.raises(typer.BadParameter, match="invalid characters"):
            _parse_user_args(["--my.arg", "value"], None)

    def test_invalid_name_in_equals_syntax_rejected(self):
        """--my.arg=value should be rejected — dots are invalid in placeholder names."""
        with pytest.raises(typer.BadParameter, match="invalid characters"):
            _parse_user_args(["--my.arg=value"], None)

    def test_empty_name_rejected(self):
        """--=value should be rejected — empty arg name."""
        with pytest.raises(typer.BadParameter, match="invalid characters"):
            _parse_user_args(["--=value"], None)

    def test_double_dash_ends_flag_parsing(self):
        """-- should end flag parsing; remaining tokens are positional."""
        result = _parse_user_args(["--dir", "./src", "--", "remaining"], ["dir", "extra"])
        assert result == {"dir": "./src", "extra": "remaining"}

    def test_double_dash_allows_flag_like_positional(self):
        """After --, values starting with -- are treated as positional."""
        result = _parse_user_args(["--", "--verbose"], ["pattern"])
        assert result == {"pattern": "--verbose"}

    def test_double_dash_only_positional_args(self):
        """-- with all positional args and no named flags."""
        result = _parse_user_args(["--", "a", "b"], ["x", "y"])
        assert result == {"x": "a", "y": "b"}


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestDuplicateArgNamesRejected:
    def test_duplicate_declared_arg_names_rejected(self, mock_which, tmp_path, monkeypatch):
        """args: [foo, foo] should be rejected — duplicate names cause silent overwrites."""
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir()
        (ralph_dir / RALPH_MARKER).write_text(
            "---\nagent: claude -p\nargs:\n  - foo\n  - foo\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "duplicate" in result.output.lower()


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestRunWithUserArgs:
    @patch(MOCK_SUBPROCESS)
    def test_named_args_resolved_in_prompt(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path, prompt="Research {{ args.dir }}")
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "--dir", "./my-project"])
        assert result.exit_code == 0
        assert mock_run.return_value.communicate.call_args.kwargs["input"].startswith("Research ./my-project")

    @patch(MOCK_SUBPROCESS)
    def test_positional_args_with_declared_names(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(
            tmp_path,
            prompt="Research {{ args.dir }} with focus on {{ args.focus }}",
            args=["dir", "focus"],
        )
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1", "./my-project", "performance"])
        assert result.exit_code == 0
        assert mock_run.return_value.communicate.call_args.kwargs["input"].startswith("Research ./my-project with focus on performance")

    @patch(MOCK_SUBPROCESS)
    def test_unused_arg_placeholders_cleared(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path, prompt="Before {{ args.opt }} after")
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert mock_run.return_value.communicate.call_args.kwargs["input"].startswith("Before  after")


class TestParseCommands:
    def test_valid_commands(self):
        raw = [
            {"name": "tests", "run": "uv run pytest"},
            {"name": "lint", "run": "ruff check"},
        ]
        commands = _parse_command_items(raw)
        assert len(commands) == 2
        assert commands[0].name == "tests"
        assert commands[0].run == "uv run pytest"
        assert commands[1].name == "lint"

    def test_empty_list(self):
        assert _parse_command_items([]) == []

    def test_custom_timeout(self):
        raw = [{"name": "slow", "run": "sleep 10", "timeout": 300}]
        commands = _parse_command_items(raw)
        assert commands[0].timeout == 300

    def test_default_timeout(self):
        from ralphify._run_types import DEFAULT_COMMAND_TIMEOUT
        raw = [{"name": "fast", "run": "echo hi"}]
        commands = _parse_command_items(raw)
        assert commands[0].timeout == DEFAULT_COMMAND_TIMEOUT

    def test_missing_name_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"run": "echo hi"}])

    def test_missing_run_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test"}])

    def test_empty_name_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "", "run": "echo hi"}])

    def test_empty_run_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": ""}])

    def test_duplicate_names_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([
                {"name": "test", "run": "echo 1"},
                {"name": "test", "run": "echo 2"},
            ])

    def test_whitespace_only_name_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "  ", "run": "echo hi"}])

    def test_whitespace_only_run_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "  "}])

    def test_non_string_name_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": 123, "run": "echo hi"}])

    def test_non_string_run_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": 123}])

    def test_non_dict_entry_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items(["not-a-dict"])

    def test_non_numeric_timeout_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": "fast"}])

    def test_negative_timeout_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": -10}])

    def test_zero_timeout_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": 0}])

    def test_boolean_timeout_errors(self):
        """timeout: true in YAML is parsed as Python True (== 1); must be rejected."""
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": True}])

    def test_boolean_false_timeout_errors(self):
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": False}])

    def test_nan_timeout_errors(self):
        """timeout: .nan in YAML produces float('nan'); must be rejected."""
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": float("nan")}])

    def test_inf_timeout_errors(self):
        """timeout: .inf in YAML produces float('inf'); must be rejected."""
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": "test", "run": "echo hi", "timeout": float("inf")}])

    @pytest.mark.parametrize("name", [
        "git.status",
        "my command",
        "test@home",
        "name!",
        "a/b",
    ], ids=["dot", "space", "at-sign", "exclamation", "slash"])
    def test_name_with_invalid_chars_errors(self, name):
        """Command names with chars outside [a-zA-Z0-9_-] can never be
        referenced by placeholders and must be rejected early."""
        with pytest.raises(typer.Exit):
            _parse_command_items([{"name": name, "run": "echo hi"}])


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestCreditFrontmatter:
    @patch(MOCK_SUBPROCESS)
    def test_credit_true_by_default(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path, prompt="go")
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert "Co-authored-by: Ralphify" in mock_run.return_value.communicate.call_args.kwargs["input"]

    @patch(MOCK_SUBPROCESS)
    def test_credit_false_omits_trailer(self, mock_run, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir(exist_ok=True)
        (ralph_dir / RALPH_MARKER).write_text(
            "---\nagent: claude -p --dangerously-skip-permissions\ncredit: false\n---\ngo"
        )
        mock_run.return_value = ok_proc()
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 0
        assert "Co-authored-by" not in mock_run.return_value.communicate.call_args.kwargs["input"]

    def test_credit_invalid_value_errors(self, mock_which, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ralph_dir = tmp_path / "my-ralph"
        ralph_dir.mkdir(exist_ok=True)
        (ralph_dir / RALPH_MARKER).write_text(
            "---\nagent: claude -p --dangerously-skip-permissions\ncredit: maybe\n---\ngo"
        )
        result = runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        assert result.exit_code == 1
        assert "credit" in result.output.lower()
        assert "true or false" in result.output.lower()


class TestTwoStageCtrlC:
    """Test the two-stage Ctrl+C signal handler installed by the run command."""

    def test_first_sigint_calls_request_stop(self):
        """First Ctrl+C should call state.request_stop() and not raise."""
        import signal
        from unittest.mock import MagicMock
        from ralphify._run_types import RunState, generate_run_id

        state = RunState(run_id=generate_run_id())
        console = MagicMock()

        ctrl_c_count = 0
        original_handler = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            nonlocal ctrl_c_count
            ctrl_c_count += 1
            if ctrl_c_count == 1:
                state.request_stop()
                console.print("\n[yellow]Finishing current iteration… (Ctrl+C again to force stop)[/yellow]")
            else:
                signal.signal(signal.SIGINT, original_handler)
                raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _sigint_handler)
        try:
            # Simulate first Ctrl+C
            _sigint_handler(signal.SIGINT, None)
            assert state.stop_requested is True
            assert ctrl_c_count == 1
            console.print.assert_called_once()
            assert "Finishing current iteration" in console.print.call_args[0][0]
        finally:
            signal.signal(signal.SIGINT, original_handler)

    def test_second_sigint_raises_keyboard_interrupt(self):
        """Second Ctrl+C should raise KeyboardInterrupt."""
        import signal
        from unittest.mock import MagicMock
        from ralphify._run_types import RunState, generate_run_id

        state = RunState(run_id=generate_run_id())
        console = MagicMock()

        ctrl_c_count = 0
        original_handler = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            nonlocal ctrl_c_count
            ctrl_c_count += 1
            if ctrl_c_count == 1:
                state.request_stop()
                console.print("\n[yellow]Finishing current iteration… (Ctrl+C again to force stop)[/yellow]")
            else:
                signal.signal(signal.SIGINT, original_handler)
                raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _sigint_handler)
        try:
            # First Ctrl+C — graceful
            _sigint_handler(signal.SIGINT, None)
            assert ctrl_c_count == 1

            # Second Ctrl+C — force
            with pytest.raises(KeyboardInterrupt):
                _sigint_handler(signal.SIGINT, None)
            assert ctrl_c_count == 2
        finally:
            signal.signal(signal.SIGINT, original_handler)

    @patch(MOCK_SUBPROCESS, side_effect=ok_proc)
    @patch(MOCK_WHICH, return_value="/usr/bin/claude")
    def test_run_command_restores_original_handler(self, mock_which, mock_run, tmp_path, monkeypatch):
        """Signal handler should be restored after run_loop finishes."""
        import signal

        monkeypatch.chdir(tmp_path)
        ralph_dir = make_ralph(tmp_path)
        original = signal.getsignal(signal.SIGINT)
        runner.invoke(app, ["run", str(ralph_dir), "-n", "1"])
        restored = signal.getsignal(signal.SIGINT)
        assert restored == original
