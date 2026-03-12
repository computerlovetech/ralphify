"""Shared pytest fixtures for ralphify tests."""

import pytest


@pytest.fixture(autouse=True)
def _disable_streaming(monkeypatch):
    """Disable the Popen-based streaming path in all tests.

    Tests mock ``subprocess.run`` to avoid real process execution.  The
    streaming code path uses ``subprocess.Popen`` instead, which would
    bypass those mocks.  Forcing ``_is_claude_command`` to return ``False``
    ensures all tests go through the ``subprocess.run`` path.
    """
    monkeypatch.setattr("ralphify._agent._is_claude_command", lambda cmd: False)
