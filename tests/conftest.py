"""Shared pytest fixtures for ralphify tests."""

import pytest

from ralphify.adapters import ADAPTERS


@pytest.fixture(autouse=True)
def _disable_streaming(monkeypatch):
    """Force the blocking path and raw peek on every registered adapter.

    Tests that explicitly need the Popen streaming path or structured
    peek rendering re-enable the relevant flag on the specific adapter
    they exercise.
    """
    for adapter in ADAPTERS:
        monkeypatch.setattr(adapter, "supports_streaming", False)
        monkeypatch.setattr(adapter, "renders_structured_peek", False)
