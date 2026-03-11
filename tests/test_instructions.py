from pathlib import Path

from ralphify.instructions import Instruction, discover_instructions, resolve_instructions


class TestDiscoverInstructions:
    def test_no_instructions_dir(self, tmp_path):
        result = discover_instructions(tmp_path)
        assert result == []

    def test_empty_instructions_dir(self, tmp_path):
        (tmp_path / ".ralph" / "instructions").mkdir(parents=True)
        result = discover_instructions(tmp_path)
        assert result == []

    def test_single_instruction(self, tmp_path):
        inst_dir = tmp_path / ".ralph" / "instructions" / "coding-style"
        inst_dir.mkdir(parents=True)
        (inst_dir / "INSTRUCTION.md").write_text(
            "---\nenabled: true\n---\nAlways use type hints."
        )

        result = discover_instructions(tmp_path)
        assert len(result) == 1
        assert result[0].name == "coding-style"
        assert result[0].content == "Always use type hints."
        assert result[0].enabled is True

    def test_alphabetical_ordering(self, tmp_path):
        instructions_dir = tmp_path / ".ralph" / "instructions"
        for name in ["zebra", "alpha", "middle"]:
            d = instructions_dir / name
            d.mkdir(parents=True)
            (d / "INSTRUCTION.md").write_text(f"---\n---\n{name} content")

        result = discover_instructions(tmp_path)
        assert [i.name for i in result] == ["alpha", "middle", "zebra"]

    def test_skips_dir_without_instruction_md(self, tmp_path):
        instructions_dir = tmp_path / ".ralph" / "instructions"
        valid = instructions_dir / "valid"
        valid.mkdir(parents=True)
        (valid / "INSTRUCTION.md").write_text("---\n---\nContent here.")

        invalid = instructions_dir / "invalid"
        invalid.mkdir(parents=True)
        # No INSTRUCTION.md

        result = discover_instructions(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_files_in_instructions_dir(self, tmp_path):
        instructions_dir = tmp_path / ".ralph" / "instructions"
        instructions_dir.mkdir(parents=True)
        (instructions_dir / "not-a-dir.md").write_text("content")

        result = discover_instructions(tmp_path)
        assert result == []

    def test_default_enabled_true(self, tmp_path):
        inst_dir = tmp_path / ".ralph" / "instructions" / "basic"
        inst_dir.mkdir(parents=True)
        (inst_dir / "INSTRUCTION.md").write_text("---\n---\nSome content.")

        result = discover_instructions(tmp_path)
        assert result[0].enabled is True

    def test_disabled_instruction(self, tmp_path):
        inst_dir = tmp_path / ".ralph" / "instructions" / "off"
        inst_dir.mkdir(parents=True)
        (inst_dir / "INSTRUCTION.md").write_text(
            "---\nenabled: false\n---\nDisabled content."
        )

        result = discover_instructions(tmp_path)
        assert result[0].enabled is False
        assert result[0].content == "Disabled content."

    def test_strips_html_comments(self, tmp_path):
        inst_dir = tmp_path / ".ralph" / "instructions" / "commented"
        inst_dir.mkdir(parents=True)
        (inst_dir / "INSTRUCTION.md").write_text(
            "---\n---\n<!-- remove this -->Keep this."
        )

        result = discover_instructions(tmp_path)
        assert result[0].content == "Keep this."


class TestResolveInstructions:
    def _make_instructions(self, *items):
        """Helper: items are (name, content) or (name, content, enabled) tuples."""
        result = []
        for item in items:
            if len(item) == 2:
                name, content = item
                enabled = True
            else:
                name, content, enabled = item
            result.append(
                Instruction(name=name, path=Path(f"/fake/{name}"), enabled=enabled, content=content)
            )
        return result

    def test_no_instructions_returns_prompt_unchanged(self):
        prompt = "Do the thing."
        assert resolve_instructions(prompt, []) == prompt

    def test_no_placeholders_appends_at_end(self):
        instructions = self._make_instructions(("style", "Use black formatting."))
        result = resolve_instructions("Base prompt.", instructions)
        assert result == "Base prompt.\n\nUse black formatting."

    def test_named_placeholder_replaced(self):
        instructions = self._make_instructions(("style", "Use black."))
        prompt = "Do work.\n\n{{ instructions.style }}\n\nDone."
        result = resolve_instructions(prompt, instructions)
        assert "Use black." in result
        assert "{{ instructions.style }}" not in result

    def test_bulk_placeholder_injects_all(self):
        instructions = self._make_instructions(
            ("alpha", "Alpha content."),
            ("beta", "Beta content."),
        )
        prompt = "Start.\n\n{{ instructions }}\n\nEnd."
        result = resolve_instructions(prompt, instructions)
        assert "Alpha content." in result
        assert "Beta content." in result
        assert "{{ instructions }}" not in result

    def test_named_excludes_from_bulk(self):
        instructions = self._make_instructions(
            ("alpha", "Alpha content."),
            ("beta", "Beta content."),
        )
        prompt = "{{ instructions.alpha }}\n\n{{ instructions }}"
        result = resolve_instructions(prompt, instructions)
        assert result.count("Alpha content.") == 1
        assert "Beta content." in result

    def test_multiple_named_placeholders(self):
        instructions = self._make_instructions(
            ("foo", "Foo text."),
            ("bar", "Bar text."),
        )
        prompt = "A: {{ instructions.foo }}\nB: {{ instructions.bar }}"
        result = resolve_instructions(prompt, instructions)
        assert "A: Foo text." in result
        assert "B: Bar text." in result

    def test_unknown_name_resolves_to_empty(self):
        instructions = self._make_instructions(("real", "Real content."))
        prompt = "{{ instructions.nonexistent }}"
        result = resolve_instructions(prompt, instructions)
        assert result == ""

    def test_whitespace_in_placeholder(self):
        instructions = self._make_instructions(("foo", "Foo text."))
        prompt = "{{  instructions.foo  }}"
        result = resolve_instructions(prompt, instructions)
        assert result == "Foo text."

    def test_bulk_placeholder_with_backslash_sequences(self):
        """Content with regex-like backslash sequences must not crash re.sub."""
        instructions = self._make_instructions(
            ("regex", r"Use \d+ to match numbers and \1 for backreferences."),
        )
        prompt = "Start.\n\n{{ instructions }}\n\nEnd."
        result = resolve_instructions(prompt, instructions)
        assert r"\d+" in result
        assert r"\1" in result
