import pytest

from ralphify.ralphs import discover_ralphs, is_ralph_name, resolve_ralph_name


class TestDiscoverRalphs:
    def test_no_ralphs_dir(self, tmp_path):
        result = discover_ralphs(tmp_path)
        assert result == []

    def test_empty_ralphs_dir(self, tmp_path):
        (tmp_path / ".ralphify" / "ralphs").mkdir(parents=True)
        result = discover_ralphs(tmp_path)
        assert result == []

    def test_single_ralph(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "improve-docs"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text(
            "---\ndescription: Improve documentation\nenabled: true\n---\nFix the docs."
        )

        result = discover_ralphs(tmp_path)
        assert len(result) == 1
        assert result[0].name == "improve-docs"
        assert result[0].description == "Improve documentation"
        assert result[0].content == "Fix the docs."
        assert result[0].enabled is True

    def test_multiple_ralphs_alphabetical(self, tmp_path):
        ralphs_dir = tmp_path / ".ralphify" / "ralphs"
        for name in ["zebra", "alpha", "middle"]:
            d = ralphs_dir / name
            d.mkdir(parents=True)
            (d / "RALPH.md").write_text(f"---\ndescription: {name}\n---\n{name} content")

        result = discover_ralphs(tmp_path)
        assert [p.name for p in result] == ["alpha", "middle", "zebra"]

    def test_disabled_ralph(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "off"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text(
            "---\nenabled: false\ndescription: Disabled\n---\nDisabled content."
        )

        result = discover_ralphs(tmp_path)
        assert result[0].enabled is False
        assert result[0].content == "Disabled content."

    def test_description_parsing(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "refactor"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text(
            "---\ndescription: Refactor messy code\n---\nDo refactoring."
        )

        result = discover_ralphs(tmp_path)
        assert result[0].description == "Refactor messy code"

    def test_default_description_empty(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "basic"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text("---\n---\nSome content.")

        result = discover_ralphs(tmp_path)
        assert result[0].description == ""

    def test_skips_dir_without_ralph_md(self, tmp_path):
        ralphs_dir = tmp_path / ".ralphify" / "ralphs"
        valid = ralphs_dir / "valid"
        valid.mkdir(parents=True)
        (valid / "RALPH.md").write_text("---\n---\nContent here.")

        invalid = ralphs_dir / "invalid"
        invalid.mkdir(parents=True)

        result = discover_ralphs(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"


class TestResolveRalphName:
    def test_found(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "improve-docs"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text("---\ndescription: Docs\n---\nFix docs.")

        result = resolve_ralph_name("improve-docs", tmp_path)
        assert result.name == "improve-docs"
        assert result.content == "Fix docs."

    def test_not_found(self, tmp_path):
        (tmp_path / ".ralphify" / "ralphs").mkdir(parents=True)
        with pytest.raises(ValueError, match="not found"):
            resolve_ralph_name("nonexistent", tmp_path)

    def test_not_found_lists_available(self, tmp_path):
        p_dir = tmp_path / ".ralphify" / "ralphs" / "existing"
        p_dir.mkdir(parents=True)
        (p_dir / "RALPH.md").write_text("---\n---\ncontent")

        with pytest.raises(ValueError, match="existing"):
            resolve_ralph_name("nonexistent", tmp_path)


class TestIsRalphName:
    def test_simple_name(self):
        assert is_ralph_name("improve-docs") is True

    def test_name_with_underscores(self):
        assert is_ralph_name("add_tests") is True

    def test_file_path(self):
        assert is_ralph_name("RALPH.md") is False

    def test_relative_path(self):
        assert is_ralph_name("ralphs/custom.md") is False

    def test_absolute_path(self):
        assert is_ralph_name("/home/user/ralph.md") is False

    def test_dotfile(self):
        assert is_ralph_name(".hidden") is False
