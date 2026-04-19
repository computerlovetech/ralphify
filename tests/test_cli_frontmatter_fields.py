"""Tests for the new max_turns / max_turns_grace frontmatter fields."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from helpers import MOCK_WHICH
from ralphify.cli import (
    _build_run_config,
    _validate_max_turns,
    _validate_max_turns_grace,
)


class TestValidateMaxTurns:
    def test_absent_returns_none(self) -> None:
        assert _validate_max_turns(None) is None

    def test_positive_int_passes(self) -> None:
        assert _validate_max_turns(5) == 5

    def test_zero_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns(0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns(-1)

    def test_bool_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns(True)

    def test_string_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns("5")

    def test_float_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns(5.0)


class TestValidateMaxTurnsGrace:
    def test_absent_defaults_to_two(self) -> None:
        assert _validate_max_turns_grace(None, max_turns=None) == 2

    def test_absent_with_cap_defaults_to_two(self) -> None:
        assert _validate_max_turns_grace(None, max_turns=10) == 2

    def test_zero_allowed(self) -> None:
        assert _validate_max_turns_grace(0, max_turns=10) == 0

    def test_negative_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns_grace(-1, max_turns=10)

    def test_bool_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns_grace(True, max_turns=10)

    def test_float_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns_grace(1.5, max_turns=10)

    def test_grace_equal_to_cap_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns_grace(10, max_turns=10)

    def test_grace_above_cap_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_max_turns_grace(11, max_turns=10)

    def test_grace_below_cap_allowed(self) -> None:
        assert _validate_max_turns_grace(3, max_turns=10) == 3

    def test_grace_without_cap_any_non_negative_allowed(self) -> None:
        # No cap means no upper bound on grace; the value is still retained.
        assert _validate_max_turns_grace(99, max_turns=None) == 99


@patch(MOCK_WHICH, return_value="/usr/bin/claude")
class TestBuildRunConfigTurnCapFields:
    def _write_ralph(self, tmp_path: Path, body: str) -> Path:
        ralph = tmp_path / "RALPH.md"
        ralph.write_text(body, encoding="utf-8")
        return ralph

    def test_defaults_when_absent(self, _mock_which, tmp_path: Path) -> None:
        self._write_ralph(
            tmp_path,
            "---\nagent: claude -p\n---\nhello\n",
        )
        config = _build_run_config(
            ralph_path=str(tmp_path),
            max_iterations=1,
            stop_on_error=False,
            delay=0,
            log_dir=None,
            timeout=None,
        )
        assert config.max_turns is None
        assert config.max_turns_grace == 2

    def test_values_threaded_through(self, _mock_which, tmp_path: Path) -> None:
        self._write_ralph(
            tmp_path,
            "---\nagent: claude -p\nmax_turns: 20\nmax_turns_grace: 5\n---\nhello\n",
        )
        config = _build_run_config(
            ralph_path=str(tmp_path),
            max_iterations=1,
            stop_on_error=False,
            delay=0,
            log_dir=None,
            timeout=None,
        )
        assert config.max_turns == 20
        assert config.max_turns_grace == 5

    def test_invalid_max_turns_exits(self, _mock_which, tmp_path: Path) -> None:
        self._write_ralph(
            tmp_path,
            "---\nagent: claude -p\nmax_turns: 0\n---\nhello\n",
        )
        with pytest.raises(typer.Exit):
            _build_run_config(
                ralph_path=str(tmp_path),
                max_iterations=1,
                stop_on_error=False,
                delay=0,
                log_dir=None,
                timeout=None,
            )

    def test_grace_at_or_above_cap_exits(self, _mock_which, tmp_path: Path) -> None:
        self._write_ralph(
            tmp_path,
            "---\nagent: claude -p\nmax_turns: 5\nmax_turns_grace: 5\n---\nhello\n",
        )
        with pytest.raises(typer.Exit):
            _build_run_config(
                ralph_path=str(tmp_path),
                max_iterations=1,
                stop_on_error=False,
                delay=0,
                log_dir=None,
                timeout=None,
            )
