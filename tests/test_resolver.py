"""Tests for ralphify._resolver — the template placeholder resolution engine."""

from ralphify._resolver import resolve_all, resolve_args


class TestResolveAll:
    """Tests for resolve_all — the single-pass resolver used by the engine."""

    def test_no_placeholders_returns_unchanged(self):
        assert resolve_all("Hello world", {}, {}) == "Hello world"

    def test_single_command(self):
        result = resolve_all("Tests:\n{{ commands.tests }}", {"tests": "5 passed"}, {})
        assert result == "Tests:\n5 passed"

    def test_multiple_commands(self):
        result = resolve_all(
            "{{ commands.a }} and {{ commands.b }}",
            {"a": "alpha", "b": "beta"}, {},
        )
        assert result == "alpha and beta"

    def test_empty_commands_clears_placeholders(self):
        result = resolve_all("Before {{ commands.tests }} after", {}, {})
        assert result == "Before  after"

    def test_unknown_command_resolves_to_empty(self):
        result = resolve_all(
            "{{ commands.known }} {{ commands.unknown }}",
            {"known": "value"}, {},
        )
        assert result == "value "

    def test_whitespace_in_command_placeholder_is_tolerated(self):
        result = resolve_all("{{  commands.name  }}", {"name": "value"}, {})
        assert result == "value"

    def test_hyphenated_command_name(self):
        result = resolve_all(
            "{{ commands.git-log }}",
            {"git-log": "commits here"}, {},
        )
        assert result == "commits here"

    def test_underscored_command_name(self):
        result = resolve_all(
            "{{ commands.test_status }}",
            {"test_status": "all green"}, {},
        )
        assert result == "all green"

    def test_regex_special_chars_in_command_content(self):
        result = resolve_all(
            "{{ commands.re }}",
            {"re": r"match \d+ and \1 groups"}, {},
        )
        assert result == r"match \d+ and \1 groups"

    def test_unreferenced_commands_not_appended(self):
        result = resolve_all(
            "Base prompt.",
            {"style": "Use black formatting."}, {},
        )
        assert result == "Base prompt."

    def test_only_referenced_commands_included(self):
        result = resolve_all(
            "{{ commands.used }}",
            {"used": "placed", "unused": "should not appear"}, {},
        )
        assert "placed" in result
        assert "should not appear" not in result

    def test_resolves_both_kinds(self):
        result = resolve_all(
            "{{ commands.tests }} and {{ args.dir }}",
            {"tests": "ok"}, {"dir": "./src"},
        )
        assert result == "ok and ./src"

    def test_arg_value_not_resolved_as_command_placeholder(self):
        """Values inserted from args must not be re-processed as command placeholders."""
        result = resolve_all(
            "Filter: {{ args.filter }}\nTests: {{ commands.tests }}",
            {"tests": "5 passed"},
            {"filter": "{{ commands.tests }}"},
        )
        assert "Filter: {{ commands.tests }}" in result
        assert "Tests: 5 passed" in result

    def test_command_output_not_resolved_as_arg_placeholder(self):
        """Values inserted from commands must not be re-processed as arg placeholders."""
        result = resolve_all(
            "Output: {{ commands.echo }}\nDir: {{ args.dir }}",
            {"echo": "{{ args.dir }}"},
            {"dir": "./src"},
        )
        assert "Output: {{ args.dir }}" in result
        assert "Dir: ./src" in result

    def test_clears_unknown_placeholders(self):
        result = resolve_all(
            "{{ commands.missing }} {{ args.missing }}",
            {"other": "val"}, {"other": "val"},
        )
        assert result == " "

    def test_empty_dicts_clear_all(self):
        result = resolve_all(
            "{{ commands.a }} {{ args.b }}",
            {}, {},
        )
        assert result == " "


class TestResolveArgs:
    """Tests for resolve_args — used individually for command run strings."""

    def test_single_arg(self):
        result = resolve_args("Research {{ args.dir }}", {"dir": "./my-project"})
        assert result == "Research ./my-project"

    def test_multiple_args(self):
        result = resolve_args(
            "{{ args.dir }} focus: {{ args.focus }}",
            {"dir": "./src", "focus": "performance"},
        )
        assert result == "./src focus: performance"

    def test_empty_args_clears_placeholders(self):
        result = resolve_args("Before {{ args.dir }} after", {})
        assert result == "Before  after"

    def test_unknown_arg_resolves_to_empty(self):
        result = resolve_args(
            "{{ args.known }} {{ args.unknown }}",
            {"known": "value"},
        )
        assert result == "value "

    def test_does_not_touch_command_placeholders(self):
        result = resolve_args(
            "{{ args.dir }} and {{ commands.tests }}",
            {"dir": "./src"},
        )
        assert result == "./src and {{ commands.tests }}"

    def test_whitespace_tolerant(self):
        result = resolve_args("{{  args.dir  }}", {"dir": "."})
        assert result == "."

    def test_hyphenated_arg_name(self):
        result = resolve_args("{{ args.my-dir }}", {"my-dir": "/tmp"})
        assert result == "/tmp"


class TestResolveRalphContext:
    """Tests for {{ ralph.X }} placeholders passed through resolve_all."""

    def test_resolves_ralph_name(self):
        result = resolve_all("Ralph: {{ ralph.name }}", {}, {}, {"name": "my-ralph"})
        assert result == "Ralph: my-ralph"

    def test_resolves_ralph_iteration(self):
        result = resolve_all("Iter: {{ ralph.iteration }}", {}, {}, {"iteration": "3"})
        assert result == "Iter: 3"

    def test_resolves_ralph_max_iterations(self):
        result = resolve_all(
            "Max: {{ ralph.max_iterations }}", {}, {}, {"max_iterations": "10"},
        )
        assert result == "Max: 10"

    def test_unknown_ralph_key_resolves_to_empty(self):
        result = resolve_all("{{ ralph.unknown }}", {}, {}, {"name": "test"})
        assert result == ""

    def test_no_ralph_context_clears_placeholders(self):
        result = resolve_all("{{ ralph.name }}", {}, {})
        assert result == ""

    def test_ralph_with_commands_and_args(self):
        result = resolve_all(
            "{{ commands.tests }} {{ args.dir }} {{ ralph.iteration }}",
            {"tests": "ok"}, {"dir": "./src"}, {"iteration": "2"},
        )
        assert result == "ok ./src 2"

    def test_ralph_value_not_resolved_as_command_placeholder(self):
        result = resolve_all(
            "Ctx: {{ ralph.name }}\nCmd: {{ commands.tests }}",
            {"tests": "5 passed"},
            {},
            {"name": "{{ commands.tests }}"},
        )
        assert "Ctx: {{ commands.tests }}" in result
        assert "Cmd: 5 passed" in result

    def test_whitespace_tolerant(self):
        result = resolve_all("{{  ralph.name  }}", {}, {}, {"name": "test"})
        assert result == "test"
