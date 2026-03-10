import subprocess
from pathlib import Path
from unittest.mock import patch

from ralphify.checks import (
    Check,
    CheckResult,
    discover_checks,
    format_check_failures,
    parse_check_md,
    run_check,
    run_all_checks,
    MAX_OUTPUT_LEN,
)


class TestParseCheckMd:
    def test_basic_frontmatter(self):
        text = "---\ncommand: ruff check .\ndescription: Lint check\n---\nFix lint errors."
        fm, body = parse_check_md(text)
        assert fm["command"] == "ruff check ."
        assert fm["description"] == "Lint check"
        assert body == "Fix lint errors."

    def test_strips_html_comments(self):
        text = "---\ncommand: echo hi\n---\n<!-- comment -->Keep this."
        fm, body = parse_check_md(text)
        assert body == "Keep this."

    def test_strips_multiline_html_comments(self):
        text = "---\ncommand: echo hi\n---\n<!--\nmultiline\ncomment\n-->Keep this."
        fm, body = parse_check_md(text)
        assert body == "Keep this."

    def test_body_only_html_comment_becomes_empty(self):
        text = "---\ncommand: echo hi\n---\n<!-- only a comment -->"
        fm, body = parse_check_md(text)
        assert body == ""

    def test_multiple_html_comments_stripped(self):
        text = "---\ncommand: echo hi\n---\n<!-- first -->Keep<!-- second --> this."
        fm, body = parse_check_md(text)
        assert body == "Keep this."

    def test_no_frontmatter(self):
        text = "Just a body with instructions."
        fm, body = parse_check_md(text)
        assert fm == {}
        assert body == "Just a body with instructions."

    def test_timeout_coerced_to_int(self):
        text = "---\ntimeout: 30\n---\nbody"
        fm, body = parse_check_md(text)
        assert fm["timeout"] == 30
        assert isinstance(fm["timeout"], int)

    def test_enabled_coerced_to_bool(self):
        for val, expected in [("true", True), ("True", True), ("yes", True), ("1", True),
                               ("false", False), ("no", False), ("0", False)]:
            text = f"---\nenabled: {val}\n---\n"
            fm, _ = parse_check_md(text)
            assert fm["enabled"] is expected, f"enabled: {val} should be {expected}"

    def test_empty_body(self):
        text = "---\ncommand: echo hi\n---\n"
        fm, body = parse_check_md(text)
        assert fm["command"] == "echo hi"
        assert body == ""

    def test_multiline_body(self):
        text = "---\ncommand: test\n---\nLine 1\nLine 2\nLine 3"
        fm, body = parse_check_md(text)
        assert "Line 1" in body
        assert "Line 3" in body

    def test_skips_comments_in_frontmatter(self):
        text = "---\n# this is a comment\ncommand: echo hi\n---\nbody"
        fm, body = parse_check_md(text)
        assert fm == {"command": "echo hi"}

    def test_skips_blank_lines_in_frontmatter(self):
        text = "---\ncommand: echo hi\n\ndescription: test\n---\nbody"
        fm, body = parse_check_md(text)
        assert fm["command"] == "echo hi"
        assert fm["description"] == "test"

    def test_value_with_colons(self):
        text = "---\ncommand: echo foo:bar:baz\n---\n"
        fm, _ = parse_check_md(text)
        assert fm["command"] == "echo foo:bar:baz"


class TestDiscoverChecks:
    def test_no_checks_dir(self, tmp_path):
        result = discover_checks(tmp_path)
        assert result == []

    def test_empty_checks_dir(self, tmp_path):
        (tmp_path / ".ralph" / "checks").mkdir(parents=True)
        result = discover_checks(tmp_path)
        assert result == []

    def test_single_check_with_command(self, tmp_path):
        check_dir = tmp_path / ".ralph" / "checks" / "ruff-lint"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ncommand: ruff check .\n---\nFix lint errors.")

        result = discover_checks(tmp_path)
        assert len(result) == 1
        assert result[0].name == "ruff-lint"
        assert result[0].command == "ruff check ."
        assert result[0].failure_instruction == "Fix lint errors."

    def test_single_check_with_script(self, tmp_path):
        check_dir = tmp_path / ".ralph" / "checks" / "typecheck"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ndescription: Type check\n---\nFix types.")
        script = check_dir / "run.sh"
        script.write_text("#!/bin/bash\nmypy .")
        script.chmod(0o755)

        result = discover_checks(tmp_path)
        assert len(result) == 1
        assert result[0].name == "typecheck"
        assert result[0].script == script

    def test_script_takes_precedence(self, tmp_path):
        """run.* script should be found even when command is also set."""
        check_dir = tmp_path / ".ralph" / "checks" / "mycheck"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ncommand: echo fallback\n---\n")
        script = check_dir / "run.sh"
        script.write_text("#!/bin/bash\necho script")
        script.chmod(0o755)

        result = discover_checks(tmp_path)
        assert len(result) == 1
        assert result[0].script == script
        assert result[0].command == "echo fallback"

    def test_alphabetical_ordering(self, tmp_path):
        checks_dir = tmp_path / ".ralph" / "checks"
        for name in ["zcheck", "acheck", "mcheck"]:
            d = checks_dir / name
            d.mkdir(parents=True)
            (d / "CHECK.md").write_text(f"---\ncommand: echo {name}\n---\n")

        result = discover_checks(tmp_path)
        assert [c.name for c in result] == ["acheck", "mcheck", "zcheck"]

    def test_skips_dir_without_check_md(self, tmp_path):
        checks_dir = tmp_path / ".ralph" / "checks"
        valid = checks_dir / "valid"
        valid.mkdir(parents=True)
        (valid / "CHECK.md").write_text("---\ncommand: echo ok\n---\n")

        invalid = checks_dir / "invalid"
        invalid.mkdir(parents=True)
        # No CHECK.md

        result = discover_checks(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_check_without_command_or_script(self, tmp_path):
        check_dir = tmp_path / ".ralph" / "checks" / "broken"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ndescription: no command\n---\nBody.")

        with patch("ralphify.checks.warnings.warn") as mock_warn:
            result = discover_checks(tmp_path)
        assert result == []
        mock_warn.assert_called_once()

    def test_default_values(self, tmp_path):
        check_dir = tmp_path / ".ralph" / "checks" / "basic"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ncommand: echo hi\n---\n")

        result = discover_checks(tmp_path)
        assert result[0].timeout == 60
        assert result[0].enabled is True

    def test_custom_timeout_and_enabled(self, tmp_path):
        check_dir = tmp_path / ".ralph" / "checks" / "custom"
        check_dir.mkdir(parents=True)
        (check_dir / "CHECK.md").write_text("---\ncommand: echo hi\ntimeout: 120\nenabled: false\n---\n")

        result = discover_checks(tmp_path)
        assert result[0].timeout == 120
        assert result[0].enabled is False

    def test_skips_files_in_checks_dir(self, tmp_path):
        """Only directories are considered, not files."""
        checks_dir = tmp_path / ".ralph" / "checks"
        checks_dir.mkdir(parents=True)
        (checks_dir / "not-a-dir.md").write_text("---\ncommand: echo\n---\n")

        result = discover_checks(tmp_path)
        assert result == []


class TestRunCheck:
    def _make_check(self, **kwargs):
        defaults = dict(
            name="test-check",
            path=Path("/fake"),
            command="echo hello",
            script=None,
            timeout=60,
            enabled=True,
            failure_instruction="Fix it.",
        )
        defaults.update(kwargs)
        return Check(**defaults)

    @patch("ralphify.checks.subprocess.run")
    def test_passing_check(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        )
        check = self._make_check()
        result = run_check(check, Path("/project"))

        assert result.passed is True
        assert result.exit_code == 0
        assert "ok" in result.output
        assert result.timed_out is False

    @patch("ralphify.checks.subprocess.run")
    def test_failing_check(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error\n"
        )
        check = self._make_check()
        result = run_check(check, Path("/project"))

        assert result.passed is False
        assert result.exit_code == 1
        assert "error" in result.output

    @patch("ralphify.checks.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=60)
        check = self._make_check()
        result = run_check(check, Path("/project"))

        assert result.passed is False
        assert result.timed_out is True
        assert result.exit_code == -1

    @patch("ralphify.checks.subprocess.run")
    def test_uses_command_with_shlex(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        check = self._make_check(command="ruff check --fix .")
        run_check(check, Path("/project"))

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == ["ruff", "check", "--fix", "."]

    @patch("ralphify.checks.subprocess.run")
    def test_uses_script_when_set(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        script_path = Path("/checks/run.sh")
        check = self._make_check(script=script_path, command="echo fallback")
        run_check(check, Path("/project"))

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == [str(script_path)]

    @patch("ralphify.checks.subprocess.run")
    def test_cwd_is_project_root(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        check = self._make_check()
        run_check(check, Path("/my/project"))

        assert mock_run.call_args.kwargs["cwd"] == Path("/my/project")

    @patch("ralphify.checks.subprocess.run")
    def test_timeout_passed_to_subprocess(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        check = self._make_check(timeout=120)
        run_check(check, Path("/project"))

        assert mock_run.call_args.kwargs["timeout"] == 120

    @patch("ralphify.checks.subprocess.run")
    def test_combines_stdout_and_stderr(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="out\n", stderr="err\n"
        )
        check = self._make_check()
        result = run_check(check, Path("/project"))

        assert "out" in result.output
        assert "err" in result.output


class TestRunAllChecks:
    @patch("ralphify.checks.subprocess.run")
    def test_runs_all_checks(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        checks = [
            Check(name="a", path=Path("/a"), command="echo a", script=None),
            Check(name="b", path=Path("/b"), command="echo b", script=None),
        ]
        results = run_all_checks(checks, Path("/project"))
        assert len(results) == 2
        assert mock_run.call_count == 2


class TestFormatCheckFailures:
    def _make_result(self, name="test", passed=True, exit_code=0, output="",
                     timed_out=False, failure_instruction=""):
        check = Check(
            name=name,
            path=Path("/fake"),
            command="echo",
            script=None,
            failure_instruction=failure_instruction,
            timeout=60,
        )
        return CheckResult(
            check=check,
            passed=passed,
            exit_code=exit_code,
            output=output,
            timed_out=timed_out,
        )

    def test_no_failures_returns_empty(self):
        results = [self._make_result(passed=True)]
        assert format_check_failures(results) == ""

    def test_single_failure(self):
        results = [self._make_result(
            name="ruff-lint",
            passed=False,
            exit_code=1,
            output="error: unused import\n",
            failure_instruction="Fix lint errors.",
        )]
        text = format_check_failures(results)
        assert "## Check Failures" in text
        assert "ruff-lint" in text
        assert "Exit code:" in text
        assert "unused import" in text
        assert "Fix lint errors." in text

    def test_multiple_failures(self):
        results = [
            self._make_result(name="lint", passed=False, exit_code=1, output="lint err"),
            self._make_result(name="types", passed=False, exit_code=2, output="type err"),
            self._make_result(name="ok-check", passed=True),
        ]
        text = format_check_failures(results)
        assert "lint" in text
        assert "types" in text
        assert "ok-check" not in text

    def test_timed_out(self):
        results = [self._make_result(
            name="slow",
            passed=False,
            exit_code=-1,
            timed_out=True,
        )]
        text = format_check_failures(results)
        assert "Timed out" in text

    def test_output_truncation(self):
        long_output = "x" * (MAX_OUTPUT_LEN + 1000)
        results = [self._make_result(
            name="verbose",
            passed=False,
            exit_code=1,
            output=long_output,
        )]
        text = format_check_failures(results)
        assert "truncated" in text
        assert len(text) < len(long_output)

    def test_empty_output(self):
        results = [self._make_result(
            name="silent",
            passed=False,
            exit_code=1,
            output="",
            failure_instruction="Fix it.",
        )]
        text = format_check_failures(results)
        assert "silent" in text
        assert "Fix it." in text
