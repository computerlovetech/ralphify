"""Tests for the adapter registry and first-match dispatch."""

from __future__ import annotations

from ralphify.adapters import ADAPTERS, CLIAdapter, select_adapter
from ralphify.adapters._generic import GenericAdapter
from ralphify.adapters.claude import ClaudeAdapter
from ralphify.adapters.codex import CodexAdapter
from ralphify.adapters.copilot import CopilotAdapter


def test_registry_contains_builtin_adapters() -> None:
    types = {type(a) for a in ADAPTERS}
    assert ClaudeAdapter in types
    assert CodexAdapter in types
    assert CopilotAdapter in types


def test_select_adapter_dispatches_by_binary_stem() -> None:
    assert isinstance(select_adapter(["claude"]), ClaudeAdapter)
    assert isinstance(select_adapter(["codex", "exec"]), CodexAdapter)
    assert isinstance(select_adapter(["copilot"]), CopilotAdapter)


def test_select_adapter_falls_back_to_generic() -> None:
    selected = select_adapter(["aider", "--model", "claude-4"])
    assert isinstance(selected, GenericAdapter)


def test_select_adapter_handles_empty_cmd() -> None:
    assert isinstance(select_adapter([]), GenericAdapter)


def test_generic_adapter_parse_never_raises() -> None:
    generic = GenericAdapter()
    assert generic.parse_event("garbage") is None
    assert generic.parse_event("") is None


def test_all_adapters_satisfy_protocol() -> None:
    """Runtime Protocol check catches shape regressions in any adapter."""
    for adapter in ADAPTERS:
        assert isinstance(adapter, CLIAdapter)
