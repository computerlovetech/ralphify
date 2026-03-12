"""Ralphify — a minimal harness for running autonomous AI coding loops.

Exposes the ``ralph`` CLI entry point, the package version, and the
public library API for programmatic use.

Quick start::

    from ralphify import run_loop, RunConfig, RunState, QueueEmitter

    config = RunConfig(command="claude", args=["-p"], prompt_file="RALPH.md")
    state = RunState(run_id="my-run")
    emitter = QueueEmitter()
    run_loop(config, state, emitter)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ralphify")
except PackageNotFoundError:
    __version__ = "0.0.0"

from ralphify.cli import app
from ralphify.engine import run_loop
from ralphify._run_types import RunConfig, RunState, RunStatus
from ralphify._events import (
    Event,
    EventEmitter,
    EventType,
    FanoutEmitter,
    NullEmitter,
    QueueEmitter,
)
from ralphify.manager import ManagedRun, RunManager
from ralphify.checks import discover_checks, run_all_checks
from ralphify.contexts import discover_contexts, run_all_contexts
from ralphify.instructions import discover_instructions
from ralphify.ralphs import discover_ralphs, resolve_ralph_name


def main():
    """Entry point for the ``ralph`` CLI (called by the console script)."""
    app()

__all__ = [
    # Version
    "__version__",
    # Engine
    "run_loop",
    # Run types
    "RunConfig",
    "RunState",
    "RunStatus",
    # Events
    "Event",
    "EventEmitter",
    "EventType",
    "FanoutEmitter",
    "NullEmitter",
    "QueueEmitter",
    # Manager
    "ManagedRun",
    "RunManager",
    # Primitives
    "discover_checks",
    "run_all_checks",
    "discover_contexts",
    "run_all_contexts",
    "discover_instructions",
    "discover_ralphs",
    "resolve_ralph_name",
]
