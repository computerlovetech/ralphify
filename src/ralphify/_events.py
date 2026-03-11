"""Event types and emitter protocol for the run loop.

The run engine emits structured events during execution so that different
frontends can observe progress without coupling to the engine internals.

- **CLI mode** renders events to the terminal via
  :class:`~ralphify._console_emitter.ConsoleEmitter`.
- **UI mode** pushes events through a :class:`QueueEmitter` into the
  FastAPI web layer, which broadcasts them over WebSocket.
- **Tests** use :class:`NullEmitter` to silently discard events.

To add a new event type, add a member to :class:`EventType` and handle it
in both :class:`~ralphify._console_emitter.ConsoleEmitter` (terminal
rendering) and the UI event consumer (WebSocket broadcast).
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class EventType(Enum):
    """All event types emitted by the run loop.

    Events fall into four groups:

    **Run lifecycle** — emitted once per run start/stop/pause/resume:
    ``RUN_STARTED``, ``RUN_STOPPED``, ``RUN_PAUSED``, ``RUN_RESUMED``.

    **Iteration lifecycle** — emitted once per iteration:
    ``ITERATION_STARTED``, ``ITERATION_COMPLETED``, ``ITERATION_FAILED``,
    ``ITERATION_TIMED_OUT``.

    **Checks** — emitted during the post-iteration validation phase:
    ``CHECKS_STARTED``, ``CHECK_PASSED``, ``CHECK_FAILED``,
    ``CHECKS_COMPLETED``.

    **Prompt assembly** — emitted during prompt construction:
    ``CONTEXTS_RESOLVED``, ``PROMPT_ASSEMBLED``.

    Each member's value is the wire-format string used in WebSocket messages
    and :meth:`Event.to_dict` serialization.
    """

    # ── Run lifecycle ───────────────────────────────────────────
    # Data: checks/contexts/instructions (int counts), max_iterations,
    #       timeout, delay, prompt_name
    RUN_STARTED = "run_started"
    # Data: reason ("completed" | "user_requested" | "error"),
    #       total, completed, failed, timed_out
    RUN_STOPPED = "run_stopped"
    # Data: (none)
    RUN_PAUSED = "run_paused"
    # Data: (none)
    RUN_RESUMED = "run_resumed"

    # ── Iteration lifecycle ─────────────────────────────────────
    # Data: iteration (int)
    ITERATION_STARTED = "iteration_started"
    # Data: iteration, returncode, duration (seconds), duration_formatted,
    #       detail, log_file
    ITERATION_COMPLETED = "iteration_completed"
    # Data: same as ITERATION_COMPLETED
    ITERATION_FAILED = "iteration_failed"
    # Data: same as ITERATION_COMPLETED (returncode is None)
    ITERATION_TIMED_OUT = "iteration_timed_out"

    # ── Checks ──────────────────────────────────────────────────
    # Data: iteration, count (int)
    CHECKS_STARTED = "checks_started"
    # Data: iteration, passed, failed, results (list of per-check dicts)
    CHECKS_COMPLETED = "checks_completed"
    # Data: iteration, name, passed (True), exit_code, timed_out
    CHECK_PASSED = "check_passed"
    # Data: iteration, name, passed (False), exit_code, timed_out
    CHECK_FAILED = "check_failed"

    # ── Prompt assembly ─────────────────────────────────────────
    # Data: iteration, count (int — number of contexts resolved)
    CONTEXTS_RESOLVED = "contexts_resolved"
    # Data: iteration, prompt_length (int)
    PROMPT_ASSEMBLED = "prompt_assembled"

    # ── Other ───────────────────────────────────────────────────
    # Data: checks, contexts, instructions (int counts)
    PRIMITIVES_RELOADED = "primitives_reloaded"
    # Reserved for future use
    SETTINGS_CHANGED = "settings_changed"
    # Data: message, level ("info" | "error"), traceback (optional)
    LOG_MESSAGE = "log_message"


@dataclass
class Event:
    """A structured event emitted by the run loop.

    Every event carries a *type* (:class:`EventType`), the *run_id* of the
    run that produced it, an arbitrary *data* dict, and a UTC *timestamp*.
    Use :meth:`to_dict` to serialize for JSON transport (e.g. WebSocket).
    """

    type: EventType
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize this event to a JSON-compatible dict.

        The ``type`` field is converted to its string value and
        ``timestamp`` to an ISO 8601 string, making the result safe
        for ``json.dumps``.
        """
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


@runtime_checkable
class EventEmitter(Protocol):
    """Protocol for objects that receive run-loop events.

    Implement this single-method protocol to observe run-loop progress.
    The engine calls :meth:`emit` synchronously from the loop thread, so
    implementations must not block for extended periods.
    """

    def emit(self, event: Event) -> None:
        """Handle a single event from the run loop."""
        ...


class NullEmitter:
    """Discards all events.  Used in tests to run the engine without output."""

    def emit(self, event: Event) -> None:
        """No-op — silently discard the event."""


class QueueEmitter:
    """Pushes events into a :class:`queue.Queue` for async consumption.

    Used by the UI layer: the engine thread pushes events into the queue,
    and an async FastAPI task drains it for WebSocket broadcast.
    """

    def __init__(self, q: queue.Queue[Event] | None = None) -> None:
        """Create an emitter backed by *q*, or a new unbounded queue."""
        self.queue: queue.Queue[Event] = q or queue.Queue()

    def emit(self, event: Event) -> None:
        """Enqueue *event* for later consumption."""
        self.queue.put(event)


class FanoutEmitter:
    """Broadcasts events to multiple emitters.

    Used by :class:`~ralphify.manager.RunManager` to send each event to
    both a :class:`QueueEmitter` (for WebSocket broadcast) and a
    persistence layer (for SQLite storage) simultaneously.
    """

    def __init__(self, emitters: list[EventEmitter]) -> None:
        """Create a fanout that delegates to each emitter in *emitters*."""
        self._emitters = emitters

    def emit(self, event: Event) -> None:
        """Forward *event* to every registered emitter in order."""
        for e in self._emitters:
            e.emit(event)
