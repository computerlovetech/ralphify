"""Event types and emitter protocol for the run loop.

The run engine emits structured events during execution.  CLI mode renders
them to the terminal via :class:`~ralphify._console_emitter.ConsoleEmitter`.
UI mode pushes them through a ``QueueEmitter`` into the web layer.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class EventType(Enum):
    """All event types emitted by the run loop."""

    RUN_STARTED = "run_started"
    RUN_STOPPED = "run_stopped"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETED = "iteration_completed"
    ITERATION_FAILED = "iteration_failed"
    ITERATION_TIMED_OUT = "iteration_timed_out"
    CHECKS_STARTED = "checks_started"
    CHECKS_COMPLETED = "checks_completed"
    CHECK_PASSED = "check_passed"
    CHECK_FAILED = "check_failed"
    CONTEXTS_RESOLVED = "contexts_resolved"
    PROMPT_ASSEMBLED = "prompt_assembled"
    PRIMITIVES_RELOADED = "primitives_reloaded"
    SETTINGS_CHANGED = "settings_changed"
    LOG_MESSAGE = "log_message"


@dataclass
class Event:
    """A structured event emitted by the run loop."""

    type: EventType
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class EventEmitter(Protocol):
    """Protocol for objects that receive run-loop events."""

    def emit(self, event: Event) -> None: ...


class NullEmitter:
    """Discards all events (useful for testing)."""

    def emit(self, event: Event) -> None:
        pass


class QueueEmitter:
    """Pushes events into a :class:`queue.Queue` for async consumption."""

    def __init__(self, q: queue.Queue[Event] | None = None) -> None:
        self.queue: queue.Queue[Event] = q or queue.Queue()

    def emit(self, event: Event) -> None:
        self.queue.put(event)
