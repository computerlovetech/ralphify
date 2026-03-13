"""Tests for discover_local_primitives in _discovery.py."""

from ralphify._discovery import discover_local_primitives


class TestDiscoverLocalPrimitivesBasic:
    def test_finds_primitives_at_ralph_dir(self, tmp_path):
        checks_dir = tmp_path / "checks" / "lint"
        checks_dir.mkdir(parents=True)
        (checks_dir / "CHECK.md").write_text("---\ncommand: ruff check .\n---\nFix lint.")

        results = list(discover_local_primitives(tmp_path, "checks", "CHECK.md"))
        assert len(results) == 1
        assert results[0].path == checks_dir
        assert results[0].frontmatter["command"] == "ruff check ."
        assert results[0].body == "Fix lint."

    def test_empty_dir_returns_nothing(self, tmp_path):
        (tmp_path / "checks").mkdir()
        results = list(discover_local_primitives(tmp_path, "checks", "CHECK.md"))
        assert results == []

    def test_missing_dir_returns_nothing(self, tmp_path):
        results = list(discover_local_primitives(tmp_path, "checks", "CHECK.md"))
        assert results == []

    def test_alphabetical_ordering(self, tmp_path):
        for name in ["zebra", "alpha", "middle"]:
            d = tmp_path / "instructions" / name
            d.mkdir(parents=True)
            (d / "INSTRUCTION.md").write_text(f"---\n---\n{name} content")

        results = list(discover_local_primitives(tmp_path, "instructions", "INSTRUCTION.md"))
        assert [r.path.name for r in results] == ["alpha", "middle", "zebra"]

    def test_skips_dirs_without_marker(self, tmp_path):
        valid = tmp_path / "contexts" / "valid"
        valid.mkdir(parents=True)
        (valid / "CONTEXT.md").write_text("---\ncommand: echo ok\n---\n")

        invalid = tmp_path / "contexts" / "invalid"
        invalid.mkdir(parents=True)
        # No CONTEXT.md

        results = list(discover_local_primitives(tmp_path, "contexts", "CONTEXT.md"))
        assert len(results) == 1
        assert results[0].path.name == "valid"

    def test_skips_files_in_kind_dir(self, tmp_path):
        checks_dir = tmp_path / "checks"
        checks_dir.mkdir(parents=True)
        (checks_dir / "not-a-dir.md").write_text("content")

        results = list(discover_local_primitives(tmp_path, "checks", "CHECK.md"))
        assert results == []
