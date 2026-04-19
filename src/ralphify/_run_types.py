"""Data types for run configuration and state.

These are the core types shared across the engine, CLI, manager, and UI
modules.  They are intentionally separate from ``engine.py`` so modules
that only need the types don't pull in the engine's execution logic.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from ralphify._events import STOP_COMPLETED, STOP_ERROR, STOP_USER_REQUESTED, StopReason


DEFAULT_COMMAND_TIMEOUT: float = 60
"""Default timeout in seconds for commands defined in RALPH.md frontmatter."""

DEFAULT_COMPLETION_SIGNAL = "RALPH_PROMISE_COMPLETE"
"""Default inner ``<promise>...</promise>`` text that marks promise completion."""

RUN_ID_LENGTH: int = 12
"""Number of hex characters used for generated run IDs."""


def generate_run_id() -> str:
    """Generate a short hex run ID from a random UUID."""
    return uuid.uuid4().hex[:RUN_ID_LENGTH]


class RunStatus(Enum):
    """Lifecycle status of a run.

    Transitions follow a simple path: ``PENDING`` → ``RUNNING`` →
    terminal (``COMPLETED``, ``STOPPED``, or ``FAILED``).  A running loop
    may also be ``PAUSED`` and later resumed back to ``RUNNING``.
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def reason(self) -> StopReason:
        """Return the reason string for terminal statuses.

        Used in ``RUN_STOPPED`` event data.  Only valid for terminal
        statuses (``COMPLETED``, ``FAILED``, ``STOPPED``).

        Raises :class:`ValueError` for non-terminal statuses.
        """
        reason = _STATUS_REASONS.get(self)
        if reason is None:
            raise ValueError(f"{self.name} is not a terminal status")
        return reason


# Maps terminal run statuses to the reason string emitted in RUN_STOPPED events.
_STATUS_REASONS: dict[RunStatus, StopReason] = {
    RunStatus.COMPLETED: STOP_COMPLETED,
    RunStatus.FAILED: STOP_ERROR,
    RunStatus.STOPPED: STOP_USER_REQUESTED,
}


@dataclass(slots=True)
class Command:
    """A named command from RALPH.md frontmatter."""

    name: str
    run: str
    timeout: float = DEFAULT_COMMAND_TIMEOUT


@dataclass(slots=True)
class RunConfig:
    """All settings for a single run.

    Mutable by design: the engine reads fields at each iteration boundary,
    so you can change ``max_iterations``, ``delay``, or ``timeout`` while
    the loop is running and the new values take effect on the next cycle.
    """

    agent: str
    ralph_dir: Path
    ralph_file: Path
    commands: list[Command] = field(default_factory=list)
    args: dict[str, str] = field(default_factory=dict)
    max_iterations: int | None = None
    delay: float = 0
    timeout: float | None = None
    stop_on_error: bool = False
    log_dir: Path | None = None
    project_root: Path = field(default=Path("."))
    credit: bool = True
    # Inner text expected inside ``<promise>...</promise>``.
    completion_signal: str = DEFAULT_COMPLETION_SIGNAL
    # Stop the run when the configured promise payload is observed.
    stop_on_completion_signal: bool = False
    # Per-iteration tool-use cap; None disables the cap.
    max_turns: int | None = None
    # Soft wind-down fires at ``max_turns - max_turns_grace``.
    max_turns_grace: int = 2


@dataclass(slots=True)
class RunState:
    """Observable state for a run.

    Control methods (:meth:`request_stop`, :meth:`request_pause`,
    :meth:`request_resume`) use :class:`threading.Event` so the run loop
    can react at iteration boundaries without busy-waiting.

    **Counter invariant**: ``timed_out_count`` is a *subset* of ``failed``,
    not an independent category.  A timed-out iteration increments both
    ``timed_out_count`` and ``failed``.  Therefore
    ``completed + failed == total iterations`` (use :attr:`total`).
    """

    run_id: str
    status: RunStatus = RunStatus.PENDING
    iteration: int = 0
    completed: int = 0
    failed: int = 0
    timed_out_count: int = 0
    started_at: datetime | None = None
    promise_completed: bool = False

    _stop_event: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )
    _resume_event: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )

    @property
    def total(self) -> int:
        """Total iterations run (``completed + failed``)."""
        return self.completed + self.failed

    def __post_init__(self) -> None:
        self._resume_event.set()

    def request_stop(self) -> None:
        self._stop_event.set()
        self._resume_event.set()

    def request_pause(self) -> None:
        self.status = RunStatus.PAUSED
        self._resume_event.clear()

    def request_resume(self) -> None:
        self.status = RunStatus.RUNNING
        self._resume_event.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def wait_for_stop(self, timeout: float | None = None) -> bool:
        """Block until a stop is requested or timeout. Returns True if stopped."""
        return self._stop_event.wait(timeout=timeout)

    @property
    def paused(self) -> bool:
        return not self._resume_event.is_set()

    def wait_for_unpause(self, timeout: float | None = None) -> bool:
        """Block until unpaused or timeout. Returns True if unpaused."""
        return self._resume_event.wait(timeout=timeout)

    def mark_completed(self) -> None:
        self.completed += 1

    def mark_failed(self) -> None:
        self.failed += 1

    def mark_timed_out(self) -> None:
        """Record a timed-out iteration (also counts as failed)."""
        self.timed_out_count += 1
        self.mark_failed()
