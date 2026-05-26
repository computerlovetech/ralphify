"""Tests for the wind-down shim invoked by Claude/Codex hook configs."""

from __future__ import annotations

import json

from ralphify import _wind_down_shim as shim


def test_emits_claude_payload_when_threshold_reached(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("8")
    rc = shim.main(["prog", str(counter), "10", "2", shim.CLAUDE])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    msg = payload["hookSpecificOutput"]["additionalContext"]
    assert "8 of 10" in msg
    assert "Wrap up" in msg


def test_emits_codex_payload_when_threshold_reached(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("5")
    rc = shim.main(["prog", str(counter), "6", "1", shim.CODEX])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert "systemMessage" in payload
    assert "5 of 6" in payload["systemMessage"]


def test_no_output_when_below_threshold(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("3")
    rc = shim.main(["prog", str(counter), "10", "2", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_threshold_clamped_to_zero_fires_at_count_zero(tmp_path, capsys) -> None:
    """grace > cap clamps threshold to 0; count == 0 satisfies the >= check."""
    counter = tmp_path / "turncount"
    counter.write_text("0")
    rc = shim.main(["prog", str(counter), "3", "5", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out != ""


def test_missing_counter_treated_as_zero(tmp_path, capsys) -> None:
    rc = shim.main(["prog", str(tmp_path / "missing"), "10", "2", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_unknown_agent_is_noop(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("99")
    rc = shim.main(["prog", str(counter), "10", "2", "copilot"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_too_few_args_is_noop(capsys) -> None:
    rc = shim.main(["prog", "only", "two"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_non_integer_cap_is_noop(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("5")
    rc = shim.main(["prog", str(counter), "not-a-number", "2", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_corrupt_counter_treated_as_zero(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("not-a-number\n")
    rc = shim.main(["prog", str(counter), "10", "2", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_blank_counter_treated_as_zero(tmp_path, capsys) -> None:
    counter = tmp_path / "turncount"
    counter.write_text("")
    rc = shim.main(["prog", str(counter), "10", "2", shim.CLAUDE])
    assert rc == 0
    assert capsys.readouterr().out == ""
