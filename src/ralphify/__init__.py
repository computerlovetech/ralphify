"""Ralphify — a minimal harness for running autonomous AI coding loops.

Exposes the ``ralph`` CLI entry point, the package version, and the
public library API for programmatic use.

Quick start::

    from ralphify import run_loop, RunConfig, RunState, Command

    config = RunConfig(
        agent="claude -p --dangerously-skip-permissions",
        ralph_dir=Path("."),
        ralph_file=Path("RALPH.md"),
    )
    state = RunState(run_id="my-run")
    run_loop(config, state)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ralphify")
except PackageNotFoundError:
    __version__ = "0.0.0"

from ralphify.engine import run_loop
from ralphify._run_types import (
    Command,
    RunConfig,
    RunResult,
    RunState,
    RunStatus,
)
from ralphify._events import (
    AgentActivityData,
    AgentOutputLineData,
    BoundEmitter,
    CommandsCompletedData,
    CommandsStartedData,
    Event,
    EventData,
    EventEmitter,
    EventType,
    FanoutEmitter,
    IterationEndedData,
    IterationStartedData,
    LogMessageData,
    NullEmitter,
    PromptAssembledData,
    QueueEmitter,
    RunStartedData,
    RunStoppedData,
    StopReason,
    ToolUseData,
    TurnApproachingLimitData,
    TurnCappedData,
)
from ralphify.manager import ManagedRun, RunManager


def main() -> None:
    """Entry point for the ``ralph`` CLI (called by the console script)."""
    try:
        from ralphify.cli import app
    except ModuleNotFoundError as exc:
        # Only a genuinely-absent CLI dependency gets the install hint; any
        # other missing module is a real bug inside ralphify.cli, so re-raise
        # it rather than masking it behind the [cli]-extra message.
        if exc.name in {"rich", "typer"}:
            raise SystemExit(
                "The `ralph` CLI requires the [cli] extra: pip install 'ralphify[cli]'"
            ) from exc
        raise

    app()


__all__ = [
    "__version__",
    "run_loop",
    "BoundEmitter",
    "Command",
    "RunConfig",
    "RunResult",
    "RunState",
    "RunStatus",
    "Event",
    "EventData",
    "EventEmitter",
    "EventType",
    "FanoutEmitter",
    "NullEmitter",
    "QueueEmitter",
    "StopReason",
    "ManagedRun",
    "RunManager",
    # Typed event payloads
    "AgentActivityData",
    "AgentOutputLineData",
    "CommandsCompletedData",
    "CommandsStartedData",
    "IterationEndedData",
    "IterationStartedData",
    "LogMessageData",
    "PromptAssembledData",
    "RunStartedData",
    "RunStoppedData",
    "ToolUseData",
    "TurnApproachingLimitData",
    "TurnCappedData",
]
