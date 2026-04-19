"""Pluggable CLI adapter layer.

Each supported agent CLI (Claude, Codex, Copilot, ...) implements the
:class:`CLIAdapter` protocol in its own module under this package.  The
engine dispatches on :func:`select_adapter` at run time, so adding a new
CLI means writing one file and registering it in :data:`ADAPTERS` — no
edits to the engine, emitter, or subprocess machinery.

Adapters translate the CLI's native output format to a common
:class:`AdapterEvent` stream and advertise capability flags so the core
loop can gracefully degrade when a CLI lacks structured output or hook
injection.  Process lifecycle (spawn, SIGTERM at cap, reap) stays in
``_agent.py``; adapters only observe.

The Protocol, :class:`AdapterEvent`, and :data:`ADAPTERS` live in
:mod:`_protocol` so concrete adapter modules can depend on them
without cycling through this package's ``__init__``.
"""

from __future__ import annotations

from ralphify.adapters._protocol import (
    ADAPTERS,
    AdapterEvent,
    AdapterEventKind,
    CLIAdapter,
    CountsWhat,
)


def select_adapter(cmd: list[str]) -> CLIAdapter:
    """Return the first registered adapter that claims *cmd*.

    Falls back to :class:`GenericAdapter` when nothing matches.  Never
    returns None — callers can always dispatch safely.
    """
    from ralphify.adapters._generic import GenericAdapter

    for adapter in ADAPTERS:
        if adapter.matches(cmd):
            return adapter
    return GenericAdapter()


def _register_builtin_adapters() -> None:
    """Import concrete adapter modules so their ``ADAPTERS.append`` runs.

    Keeps the registry populated without forcing callers to import every
    adapter module manually.  Imports are deferred to the bottom of this
    module (executed once at first package import) so cyclic-import risk
    is contained.
    """
    from ralphify.adapters import claude, codex, copilot  # noqa: F401


_register_builtin_adapters()


__all__ = [
    "ADAPTERS",
    "AdapterEvent",
    "AdapterEventKind",
    "CLIAdapter",
    "CountsWhat",
    "select_adapter",
]
