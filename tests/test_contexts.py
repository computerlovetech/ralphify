import subprocess
from pathlib import Path
from unittest.mock import patch

from ralphify._output import MAX_OUTPUT_LEN
from ralphify.contexts import (
    Context,
    ContextResult,
    discover_contexts,
    discover_contexts_local,
    resolve_contexts,
    run_context,
    run_all_contexts,
)

_MOCK_SUBPROCESS = "ralphify._runner.subprocess.run"


class TestDiscoverContexts:
    def test_no_contexts_dir(self, tmp_path):
        result = discover_contexts(tmp_path)
        assert result == []

    def test_empty_contexts_dir(self, tmp_path):
        (tmp_path / ".ralphify" / "contexts").mkdir(parents=True)
        result = discover_contexts(tmp_path)
        assert result == []

    def test_single_context_with_command(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "git-history"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text(
            "---\ncommand: git log --oneline -10\n---\nRecent commits:"
        )

        result = discover_contexts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "git-history"
        assert result[0].command == "git log --oneline -10"
        assert result[0].static_content == "Recent commits:"

    def test_static_only_context(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "project-info"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text(
            "---\nenabled: true\n---\nThis is a Python project."
        )

        result = discover_contexts(tmp_path)
        assert len(result) == 1
        assert result[0].command is None
        assert result[0].script is None
        assert result[0].static_content == "This is a Python project."

    def test_context_with_script(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "custom"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text("---\n---\nHeader:")
        script = ctx_dir / "run.sh"
        script.write_text("#!/bin/bash\necho hello")
        script.chmod(0o755)

        result = discover_contexts(tmp_path)
        assert len(result) == 1
        assert result[0].script == script

    def test_alphabetical_ordering(self, tmp_path):
        contexts_dir = tmp_path / ".ralphify" / "contexts"
        for name in ["zebra", "alpha", "middle"]:
            d = contexts_dir / name
            d.mkdir(parents=True)
            (d / "CONTEXT.md").write_text(f"---\ncommand: echo {name}\n---\n")

        result = discover_contexts(tmp_path)
        assert [c.name for c in result] == ["alpha", "middle", "zebra"]

    def test_skips_dir_without_context_md(self, tmp_path):
        contexts_dir = tmp_path / ".ralphify" / "contexts"
        valid = contexts_dir / "valid"
        valid.mkdir(parents=True)
        (valid / "CONTEXT.md").write_text("---\ncommand: echo ok\n---\n")

        invalid = contexts_dir / "invalid"
        invalid.mkdir(parents=True)
        # No CONTEXT.md

        result = discover_contexts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_files_in_contexts_dir(self, tmp_path):
        contexts_dir = tmp_path / ".ralphify" / "contexts"
        contexts_dir.mkdir(parents=True)
        (contexts_dir / "not-a-dir.md").write_text("content")

        result = discover_contexts(tmp_path)
        assert result == []

    def test_default_values(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "basic"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text("---\ncommand: echo hi\n---\n")

        result = discover_contexts(tmp_path)
        assert result[0].timeout == 30
        assert result[0].enabled is True

    def test_custom_timeout_and_enabled(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "custom"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text(
            "---\ncommand: echo hi\ntimeout: 10\nenabled: false\n---\n"
        )

        result = discover_contexts(tmp_path)
        assert result[0].timeout == 10
        assert result[0].enabled is False

    def test_disabled_context(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "off"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text(
            "---\ncommand: echo off\nenabled: false\n---\nDisabled."
        )

        result = discover_contexts(tmp_path)
        assert result[0].enabled is False
        assert result[0].static_content == "Disabled."

    def test_strips_html_comments(self, tmp_path):
        ctx_dir = tmp_path / ".ralphify" / "contexts" / "commented"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text(
            "---\ncommand: echo hi\n---\n<!-- remove this -->Keep this."
        )

        result = discover_contexts(tmp_path)
        assert result[0].static_content == "Keep this."


class TestDiscoverContextsLocal:
    def test_finds_contexts_in_prompt_dir(self, tmp_path):
        ctx_dir = tmp_path / "contexts" / "tasks"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text("---\ncommand: cat tasks.md\n---\nCurrent tasks:")

        result = discover_contexts_local(tmp_path)
        assert len(result) == 1
        assert result[0].name == "tasks"
        assert result[0].command == "cat tasks.md"
        assert result[0].static_content == "Current tasks:"

    def test_empty_prompt_dir(self, tmp_path):
        result = discover_contexts_local(tmp_path)
        assert result == []

    def test_static_only_context(self, tmp_path):
        ctx_dir = tmp_path / "contexts" / "info"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "CONTEXT.md").write_text("---\n---\nStatic info.")

        result = discover_contexts_local(tmp_path)
        assert len(result) == 1
        assert result[0].command is None
        assert result[0].static_content == "Static info."

    def test_alphabetical_ordering(self, tmp_path):
        contexts_dir = tmp_path / "contexts"
        for name in ["zebra", "alpha"]:
            d = contexts_dir / name
            d.mkdir(parents=True)
            (d / "CONTEXT.md").write_text(f"---\ncommand: echo {name}\n---\n")

        result = discover_contexts_local(tmp_path)
        assert [c.name for c in result] == ["alpha", "zebra"]


class TestRunContext:
    def _make_context(self, **kwargs: object) -> Context:
        cmd = kwargs.get("command", "echo hello")
        return Context(
            name=str(kwargs.get("name", "test-ctx")),
            path=Path(str(kwargs["path"])) if "path" in kwargs else Path("/fake"),
            command=str(cmd) if cmd is not None else None,
            script=Path(str(kwargs["script"])) if kwargs.get("script") else None,
            timeout=int(str(kwargs["timeout"])) if "timeout" in kwargs else 30,
            enabled=bool(kwargs.get("enabled", True)),
            static_content=str(kwargs.get("static_content", "")),
        )

    @patch(_MOCK_SUBPROCESS)
    def test_successful_command(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="output\n", stderr=""
        )
        ctx = self._make_context()
        result = run_context(ctx, Path("/project"))

        assert result.success is True
        assert "output" in result.output
        assert result.timed_out is False

    @patch(_MOCK_SUBPROCESS)
    def test_failing_command(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error\n"
        )
        ctx = self._make_context()
        result = run_context(ctx, Path("/project"))

        assert result.success is False
        assert "error" in result.output

    @patch(_MOCK_SUBPROCESS)
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=30)
        ctx = self._make_context()
        result = run_context(ctx, Path("/project"))

        assert result.success is False
        assert result.timed_out is True

    def test_static_only_no_subprocess(self):
        ctx = self._make_context(command=None, script=None, static_content="Static text.")
        result = run_context(ctx, Path("/project"))

        assert result.success is True
        assert result.output == ""

    @patch(_MOCK_SUBPROCESS)
    def test_uses_script_when_set(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="from script\n", stderr=""
        )
        script_path = Path("/contexts/run.sh")
        ctx = self._make_context(script=script_path, command="echo fallback")
        run_context(ctx, Path("/project"))

        call_args = mock_run.call_args
        assert call_args.args[0] == [str(script_path)]

    @patch(_MOCK_SUBPROCESS)
    def test_uses_command_with_shlex(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        ctx = self._make_context(command="git log --oneline -10")
        run_context(ctx, Path("/project"))

        call_args = mock_run.call_args
        assert call_args.args[0] == ["git", "log", "--oneline", "-10"]

    @patch(_MOCK_SUBPROCESS)
    def test_cwd_is_project_root(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        ctx = self._make_context()
        run_context(ctx, Path("/my/project"))

        assert mock_run.call_args.kwargs["cwd"] == Path("/my/project")

    @patch(_MOCK_SUBPROCESS)
    def test_timeout_passed_to_subprocess(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        ctx = self._make_context(timeout=15)
        run_context(ctx, Path("/project"))

        assert mock_run.call_args.kwargs["timeout"] == 15

    @patch(_MOCK_SUBPROCESS)
    def test_combines_stdout_and_stderr(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="out\n", stderr="err\n"
        )
        ctx = self._make_context()
        result = run_context(ctx, Path("/project"))

        assert "out" in result.output
        assert "err" in result.output


class TestRunAllContexts:
    @patch(_MOCK_SUBPROCESS)
    def test_runs_all_contexts(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        )
        contexts = [
            Context(name="a", path=Path("/a"), command="echo a"),
            Context(name="b", path=Path("/b"), command="echo b"),
        ]
        results = run_all_contexts(contexts, Path("/project"))
        assert len(results) == 2
        assert mock_run.call_count == 2


class TestContextRendering:
    """Test context rendering (static content + command output) via resolve_contexts."""

    def _make_result(self, name="test", static_content="", output="", success=True):
        ctx = Context(
            name=name,
            path=Path("/fake"),
            command="echo",
            static_content=static_content,
        )
        return ContextResult(context=ctx, output=output, success=success)

    def _render_via_resolve(self, static_content="", output=""):
        """Render a context through resolve_contexts with a named placeholder."""
        result = self._make_result(static_content=static_content, output=output)
        return resolve_contexts("{{ contexts.test }}", [result])

    def test_static_and_output(self):
        rendered = self._render_via_resolve(static_content="Header:", output="data\n")
        assert "Header:" in rendered
        assert "data" in rendered

    def test_static_only(self):
        rendered = self._render_via_resolve(static_content="Just static.", output="")
        assert rendered == "Just static."

    def test_output_only(self):
        rendered = self._render_via_resolve(static_content="", output="dynamic output\n")
        assert rendered == "dynamic output"

    def test_empty_context_not_injected(self):
        result = self._make_result(static_content="", output="")
        prompt = "Base prompt."
        rendered = resolve_contexts(prompt, [result])
        assert rendered == prompt

    def test_output_truncation(self):
        long_output = "x" * (MAX_OUTPUT_LEN + 1000)
        rendered = self._render_via_resolve(output=long_output)
        assert "truncated" in rendered
        assert len(rendered) < len(long_output)


class TestResolveContexts:
    def _make_results(self, *items):
        """Helper: items are (name, content) or (name, content, enabled) tuples.

        content is used as command output.
        """
        results = []
        for item in items:
            if len(item) == 2:
                name, output = item
                enabled = True
            else:
                name, output, enabled = item
            ctx = Context(
                name=name,
                path=Path(f"/fake/{name}"),
                command="echo",
                enabled=enabled,
            )
            results.append(ContextResult(context=ctx, output=output, success=True))
        return results

    def test_no_results_returns_prompt_unchanged(self):
        prompt = "Do the thing."
        assert resolve_contexts(prompt, []) == prompt

    def test_no_placeholders_appends_at_end(self):
        results = self._make_results(("git-log", "abc123 fix bug\n"))
        result = resolve_contexts("Base prompt.", results)
        assert result == "Base prompt.\n\nabc123 fix bug"

    def test_named_placeholder_replaced(self):
        results = self._make_results(("git-log", "abc123 fix\n"))
        prompt = "Context:\n\n{{ contexts.git-log }}\n\nDone."
        result = resolve_contexts(prompt, results)
        assert "abc123 fix" in result
        assert "{{ contexts.git-log }}" not in result

    def test_bulk_placeholder_injects_all(self):
        results = self._make_results(
            ("alpha", "Alpha output\n"),
            ("beta", "Beta output\n"),
        )
        prompt = "Start.\n\n{{ contexts }}\n\nEnd."
        result = resolve_contexts(prompt, results)
        assert "Alpha output" in result
        assert "Beta output" in result
        assert "{{ contexts }}" not in result

    def test_named_excludes_from_bulk(self):
        results = self._make_results(
            ("alpha", "Alpha output\n"),
            ("beta", "Beta output\n"),
        )
        prompt = "{{ contexts.alpha }}\n\n{{ contexts }}"
        result = resolve_contexts(prompt, results)
        assert result.count("Alpha output") == 1
        assert "Beta output" in result

    def test_multiple_named_placeholders(self):
        results = self._make_results(
            ("foo", "Foo data\n"),
            ("bar", "Bar data\n"),
        )
        prompt = "A: {{ contexts.foo }}\nB: {{ contexts.bar }}"
        result = resolve_contexts(prompt, results)
        assert "A: Foo data" in result
        assert "B: Bar data" in result

    def test_unknown_name_resolves_to_empty(self):
        results = self._make_results(("real", "Real output\n"))
        prompt = "{{ contexts.nonexistent }}"
        result = resolve_contexts(prompt, results)
        assert result == ""

    def test_whitespace_in_placeholder(self):
        results = self._make_results(("foo", "Foo data\n"))
        prompt = "{{  contexts.foo  }}"
        result = resolve_contexts(prompt, results)
        assert result == "Foo data"

    def test_static_content_included(self):
        ctx = Context(
            name="info",
            path=Path("/fake/info"),
            command="echo",
            enabled=True,
            static_content="Header:",
        )
        results = [ContextResult(context=ctx, output="dynamic\n", success=True)]
        prompt = "{{ contexts }}"
        result = resolve_contexts(prompt, results)
        assert "Header:" in result
        assert "dynamic" in result
