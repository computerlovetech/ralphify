from pathlib import Path

import pytest

from ralphify.prompts import Prompt, discover_prompts, is_prompt_name, resolve_prompt_name


class TestDiscoverPrompts:
    def test_no_prompts_dir(self, tmp_path):
        result = discover_prompts(tmp_path)
        assert result == []

    def test_empty_prompts_dir(self, tmp_path):
        (tmp_path / ".ralph" / "prompts").mkdir(parents=True)
        result = discover_prompts(tmp_path)
        assert result == []

    def test_single_prompt(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "improve-docs"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text(
            "---\ndescription: Improve documentation\nenabled: true\n---\nFix the docs."
        )

        result = discover_prompts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "improve-docs"
        assert result[0].description == "Improve documentation"
        assert result[0].content == "Fix the docs."
        assert result[0].enabled is True

    def test_multiple_prompts_alphabetical(self, tmp_path):
        prompts_dir = tmp_path / ".ralph" / "prompts"
        for name in ["zebra", "alpha", "middle"]:
            d = prompts_dir / name
            d.mkdir(parents=True)
            (d / "PROMPT.md").write_text(f"---\ndescription: {name}\n---\n{name} content")

        result = discover_prompts(tmp_path)
        assert [p.name for p in result] == ["alpha", "middle", "zebra"]

    def test_disabled_prompt(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "off"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text(
            "---\nenabled: false\ndescription: Disabled\n---\nDisabled content."
        )

        result = discover_prompts(tmp_path)
        assert result[0].enabled is False
        assert result[0].content == "Disabled content."

    def test_description_parsing(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "refactor"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text(
            "---\ndescription: Refactor messy code\n---\nDo refactoring."
        )

        result = discover_prompts(tmp_path)
        assert result[0].description == "Refactor messy code"

    def test_default_description_empty(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "basic"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text("---\n---\nSome content.")

        result = discover_prompts(tmp_path)
        assert result[0].description == ""

    def test_skips_dir_without_prompt_md(self, tmp_path):
        prompts_dir = tmp_path / ".ralph" / "prompts"
        valid = prompts_dir / "valid"
        valid.mkdir(parents=True)
        (valid / "PROMPT.md").write_text("---\n---\nContent here.")

        invalid = prompts_dir / "invalid"
        invalid.mkdir(parents=True)

        result = discover_prompts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"


class TestResolvePromptName:
    def test_found(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "improve-docs"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text("---\ndescription: Docs\n---\nFix docs.")

        result = resolve_prompt_name("improve-docs", tmp_path)
        assert result.name == "improve-docs"
        assert result.content == "Fix docs."

    def test_not_found(self, tmp_path):
        (tmp_path / ".ralph" / "prompts").mkdir(parents=True)
        with pytest.raises(ValueError, match="not found"):
            resolve_prompt_name("nonexistent", tmp_path)

    def test_not_found_lists_available(self, tmp_path):
        p_dir = tmp_path / ".ralph" / "prompts" / "existing"
        p_dir.mkdir(parents=True)
        (p_dir / "PROMPT.md").write_text("---\n---\ncontent")

        with pytest.raises(ValueError, match="existing"):
            resolve_prompt_name("nonexistent", tmp_path)


class TestIsPromptName:
    def test_simple_name(self):
        assert is_prompt_name("improve-docs") is True

    def test_name_with_underscores(self):
        assert is_prompt_name("add_tests") is True

    def test_file_path(self):
        assert is_prompt_name("PROMPT.md") is False

    def test_relative_path(self):
        assert is_prompt_name("prompts/custom.md") is False

    def test_absolute_path(self):
        assert is_prompt_name("/home/user/prompt.md") is False

    def test_dotfile(self):
        assert is_prompt_name(".hidden") is False
