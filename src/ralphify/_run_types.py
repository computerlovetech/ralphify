"""Data types for run configuration and state.

These are the core types shared across the engine, CLI, manager, and UI
modules.  They are intentionally separate from ``engine.py`` so modules
that only need the types don't pull in the engine's execution logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class RunStatus(Enum):
    """Lifecycle status of a run.

    Transitions follow a simple path: ``PENDING`` → ``RUNNING`` →
    terminal (``COMPLETED``, ``STOPPED``, or ``FAILED``).  A running loop
    may also be ``PAUSED`` and later resumed back to ``RUNNING``.

    Check ``state.status`` to decide what UI elements to show or whether
    it's safe to start a new run with the same resources.
    """

    PENDING = "pending"       # Created but not yet started
    RUNNING = "running"       # Loop is executing iterations
    PAUSED = "paused"         # Paused between iterations, waiting for resume
    STOPPED = "stopped"       # Stopped by user via request_stop()
    COMPLETED = "completed"   # Reached max_iterations or finished naturally
    FAILED = "failed"         # Crashed with an unhandled exception


@dataclass
class RunConfig:
    """All settings for a single run.

    Mutable by design: the engine reads fields at each iteration boundary,
    so you can change ``max_iterations``, ``delay``, or ``timeout`` while
    the loop is running and the new values take effect on the next cycle.

    For CLI usage the config is built once from ``ralph.toml`` + flags.
    For programmatic usage, construct directly and pass to :func:`run_loop`.
    """

    command: str
    args: list[str]
    prompt_file: str
    prompt_text: str | None = None
    prompt_name: str | None = None
    max_iterations: int | None = None
    delay: float = 0
    timeout: float | None = None
    stop_on_error: bool = False
    log_dir: str | None = None
    project_root: Path = field(default_factory=lambda: Path("."))


@dataclass
class RunState:
    """Observable state for a run.

    Control methods (:meth:`request_stop`, :meth:`request_pause`,
    :meth:`request_resume`) use :class:`threading.Event` so the run loop
    can react at iteration boundaries without busy-waiting.

    **Counter invariant**: ``timed_out`` is a *subset* of ``failed``, not
    an independent category.  A timed-out iteration increments both
    ``timed_out`` and ``failed``.  Therefore
    ``completed + failed == total iterations`` (use :attr:`total`).

    **Threading model**: counters (``iteration``, ``completed``, etc.) are
    written only by the engine thread and read by API threads.  Under
    CPython's GIL this is safe — readers may see a briefly stale value,
    which is acceptable for dashboard display.
    """

    run_id: str
    status: RunStatus = RunStatus.PENDING
    iteration: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0  # subset of ``failed``; see class docstring
    started_at: datetime | None = None

    _stop_requested: bool = False
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _reload_requested: bool = False

    @property
    def total(self) -> int:
        """Total iterations run (``completed + failed``).

        Because ``timed_out`` is already counted in ``failed``, the total
        is simply ``completed + failed`` — do **not** add ``timed_out``.
        """
        return self.completed + self.failed

    def __post_init__(self) -> None:
        # Start un-paused
        self._pause_event.set()

    def request_stop(self) -> None:
        """Signal the loop to stop after the current iteration."""
        self._stop_requested = True
        # Unpause so the loop can exit
        self._pause_event.set()

    def request_pause(self) -> None:
        """Pause the loop between iterations until resumed."""
        self.status = RunStatus.PAUSED
        self._pause_event.clear()

    def request_resume(self) -> None:
        """Resume a paused loop."""
        self.status = RunStatus.RUNNING
        self._pause_event.set()

    def request_reload(self) -> None:
        """Request re-discovery of primitives before the next iteration."""
        self._reload_requested = True

    @property
    def stop_requested(self) -> bool:
        """Whether a stop has been requested."""
        return self._stop_requested

    @property
    def paused(self) -> bool:
        """Whether the run is currently paused."""
        return not self._pause_event.is_set()

    def wait_for_unpause(self, timeout: float | None = None) -> bool:
        """Block until unpaused or timeout. Returns True if unpaused."""
        return self._pause_event.wait(timeout=timeout)

    def consume_reload_request(self) -> bool:
        """If a reload was requested, clear the flag and return True."""
        if self._reload_requested:
            self._reload_requested = False
            return True
        return False
