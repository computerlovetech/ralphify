"""Event types and emitter protocol for the run loop.

The run engine emits structured events during execution so that different
frontends can observe progress without coupling to the engine internals.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Literal,
    NotRequired,
    Protocol,
    TypedDict,
    cast,
    runtime_checkable,
)


LogLevel = Literal["info", "error"]
"""Valid log levels for :class:`LogMessageData` events."""

LOG_INFO: LogLevel = "info"
LOG_ERROR: LogLevel = "error"

StopReason = Literal["completed", "error", "user_requested"]
"""Valid reason strings for :class:`RunStoppedData` events."""

STOP_COMPLETED: StopReason = "completed"
STOP_ERROR: StopReason = "error"
STOP_USER_REQUESTED: StopReason = "user_requested"


class EventType(Enum):
    """All event types emitted by the run loop.

    Events fall into five groups:

    **Run lifecycle** — emitted once per run start/stop/pause/resume:
    ``RUN_STARTED``, ``RUN_STOPPED``, ``RUN_PAUSED``, ``RUN_RESUMED``.

    **Iteration lifecycle** — emitted once per iteration:
    ``ITERATION_STARTED``, ``ITERATION_COMPLETED``, ``ITERATION_FAILED``,
    ``ITERATION_TIMED_OUT``.

    **Commands** — emitted around command execution:
    ``COMMANDS_STARTED``, ``COMMANDS_COMPLETED``.

    **Prompt assembly** — emitted after the prompt is built:
    ``PROMPT_ASSEMBLED``.

    **Agent activity** — emitted during agent execution (streaming only):
    ``AGENT_ACTIVITY``.

    The ``LOG_MESSAGE`` type is used for general informational and error
    messages (e.g. delay notifications, crash reports).
    """

    # ── Run lifecycle ───────────────────────────────────────────
    RUN_STARTED = "run_started"
    RUN_STOPPED = "run_stopped"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"

    # ── Iteration lifecycle ─────────────────────────────────────
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETED = "iteration_completed"
    ITERATION_FAILED = "iteration_failed"
    ITERATION_TIMED_OUT = "iteration_timed_out"

    # ── Commands ────────────────────────────────────────────────
    COMMANDS_STARTED = "commands_started"
    COMMANDS_COMPLETED = "commands_completed"

    # ── Prompt assembly ─────────────────────────────────────────
    PROMPT_ASSEMBLED = "prompt_assembled"

    # ── Agent activity (live streaming) ─────────────────────────
    AGENT_ACTIVITY = "agent_activity"
    AGENT_OUTPUT_LINE = "agent_output_line"
    TOOL_USE = "tool_use"

    # ── Turn-cap enforcement ────────────────────────────────────
    ITERATION_TURN_APPROACHING_LIMIT = "iteration_turn_approaching_limit"
    ITERATION_TURN_CAPPED = "iteration_turn_capped"

    # ── Other ───────────────────────────────────────────────────
    LOG_MESSAGE = "log_message"


# ── Typed event data payloads ─────────────────────────────────────────


class RunStartedData(TypedDict):
    ralph_name: str
    agent: str
    commands: int
    max_iterations: int | None
    timeout: float | None
    delay: float


class RunStoppedData(TypedDict):
    reason: StopReason
    total: int
    completed: int
    failed: int
    timed_out_count: int


class IterationStartedData(TypedDict):
    iteration: int


class IterationEndedData(TypedDict):
    iteration: int
    returncode: int | None
    duration: float
    duration_formatted: str
    detail: str
    log_file: str | None
    result_text: str | None
    echo_stdout: NotRequired[str | None]
    echo_stderr: NotRequired[str | None]


class CommandsStartedData(TypedDict):
    iteration: int
    count: int


class CommandsCompletedData(TypedDict):
    iteration: int
    count: int


class PromptAssembledData(TypedDict):
    iteration: int
    prompt_length: int


class AgentActivityData(TypedDict):
    raw: dict[str, Any]
    iteration: int


OutputStream = Literal["stdout", "stderr"]
"""Which standard stream an :class:`AgentOutputLineData` event came from."""


class AgentOutputLineData(TypedDict):
    line: str
    stream: OutputStream
    iteration: int


class ToolUseData(TypedDict):
    iteration: int
    tool_name: str
    count: int


class TurnApproachingLimitData(TypedDict):
    iteration: int
    count: int
    max_turns: int


class TurnCappedData(TypedDict):
    iteration: int
    count: int


class LogMessageData(TypedDict):
    message: str
    level: LogLevel
    traceback: NotRequired[str]


EventData = (
    RunStartedData
    | RunStoppedData
    | IterationStartedData
    | IterationEndedData
    | CommandsStartedData
    | CommandsCompletedData
    | PromptAssembledData
    | AgentActivityData
    | AgentOutputLineData
    | ToolUseData
    | TurnApproachingLimitData
    | TurnCappedData
    | LogMessageData
)
"""Union of all typed event data payloads."""


@dataclass(slots=True)
class Event:
    """A structured event emitted by the run loop."""

    type: EventType
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize this event to a JSON-compatible dict."""
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


@runtime_checkable
class EventEmitter(Protocol):
    """Protocol for objects that receive run-loop events."""

    def emit(self, event: Event) -> None: ...

    def wants_agent_output_lines(self) -> bool:
        """Return True if this emitter will render AGENT_OUTPUT_LINE events.

        Used by the engine to avoid per-line event allocation when no
        subscriber cares.  This is a hint — emitters may still receive
        the events if the caller chooses to send them anyway.
        """
        return False


class NullEmitter:
    """Discards all events silently."""

    def emit(self, event: Event) -> None:
        pass

    def wants_agent_output_lines(self) -> bool:
        return False


class QueueEmitter:
    """Pushes events into a :class:`queue.Queue` for async consumption."""

    def __init__(self, q: queue.Queue[Event] | None = None) -> None:
        self.queue: queue.Queue[Event] = q or queue.Queue()

    def emit(self, event: Event) -> None:
        self.queue.put(event)

    def wants_agent_output_lines(self) -> bool:
        return False


class FanoutEmitter:
    """Broadcasts events to multiple emitters."""

    def __init__(self, emitters: list[EventEmitter]) -> None:
        self._emitters = emitters

    def emit(self, event: Event) -> None:
        for e in self._emitters:
            e.emit(event)

    def wants_agent_output_lines(self) -> bool:
        return any(e.wants_agent_output_lines() for e in self._emitters)


class BoundEmitter:
    """Wraps an EventEmitter with a fixed run_id for concise emission.

    Instead of constructing :class:`Event` objects manually at every call
    site, callers create a ``BoundEmitter`` once with the run ID and then
    emit events with just the type and optional data payload.
    """

    def __init__(self, emitter: EventEmitter, run_id: str) -> None:
        self._emitter = emitter
        self._run_id = run_id

    def wants_agent_output_lines(self) -> bool:
        """Delegate to the underlying emitter (checked per-call, not cached)."""
        return self._emitter.wants_agent_output_lines()

    def __call__(
        self,
        event_type: EventType,
        data: EventData | None = None,
    ) -> None:
        self._emitter.emit(
            Event(
                type=event_type,
                run_id=self._run_id,
                data=cast(dict[str, Any], data) if data is not None else {},
            )
        )

    def log_info(self, message: str) -> None:
        """Emit a ``LOG_MESSAGE`` event at info level."""
        self(EventType.LOG_MESSAGE, LogMessageData(message=message, level=LOG_INFO))

    def agent_output_line(
        self, line: str, stream: OutputStream, iteration: int
    ) -> None:
        """Emit an ``AGENT_OUTPUT_LINE`` event with a raw line of agent output."""
        self(
            EventType.AGENT_OUTPUT_LINE,
            AgentOutputLineData(line=line, stream=stream, iteration=iteration),
        )

    def log_error(self, message: str, *, traceback: str | None = None) -> None:
        """Emit a ``LOG_MESSAGE`` event at error level."""
        data = LogMessageData(message=message, level=LOG_ERROR)
        if traceback is not None:
            data["traceback"] = traceback
        self(EventType.LOG_MESSAGE, data)
