"""Multi-run orchestration for concurrent ralph loops.

Wraps run engine threads and provides a thread-safe registry for launching,
controlling, and inspecting multiple runs from external code.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from ralphify._events import EventEmitter, FanoutEmitter, QueueEmitter
from ralphify._run_types import (
    RunConfig,
    RunResult,
    RunState,
    RunStatus,
    generate_run_id,
)
from ralphify.engine import run_loop


_TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED}
)


@dataclass(slots=True)
class ManagedRun:
    """A run bundled with its background thread and event queue.

    Created by :meth:`RunManager.create_run`.  Use ``state`` to inspect
    progress or call control methods (stop, pause, resume), and drain
    ``emitter.queue`` to consume events.  Register extra listeners with
    :meth:`add_listener` *before* calling :meth:`RunManager.start_run`.
    """

    config: RunConfig
    state: RunState
    emitter: QueueEmitter
    thread: threading.Thread | None = None
    _extra_emitters: list[EventEmitter] = field(default_factory=list)

    def add_listener(self, emitter: EventEmitter) -> None:
        """Register an additional emitter to receive events from this run."""
        self._extra_emitters.append(emitter)

    def build_emitter(self) -> EventEmitter:
        """Build the composite emitter for this run.

        Returns a :class:`FanoutEmitter` when extra listeners are registered,
        or the queue emitter directly when there are none.  This keeps the
        emitter composition logic inside ``ManagedRun`` so callers don't need
        to reach into private fields.
        """
        if self._extra_emitters:
            return FanoutEmitter([self.emitter, *self._extra_emitters])
        return self.emitter


class RunManager:
    """Thread-safe registry for managing concurrent background runs.

    Use this instead of calling :func:`run_loop` directly when you need to
    launch multiple runs, control them from another thread (e.g. a web
    server), or list/inspect all active runs.  Each run gets its own daemon
    thread and event queue.
    """

    def __init__(self) -> None:
        self._runs: dict[str, ManagedRun] = {}
        self._lock = threading.Lock()
        # Notified once whenever any run thread exits, so waiters can wake
        # and re-check terminal status without polling.
        self._done = threading.Condition()

    def _lookup(self, run_id: str) -> ManagedRun:
        """Look up a run by ID. Caller must hold ``_lock``."""
        try:
            return self._runs[run_id]
        except KeyError:
            raise KeyError(f"No run with ID '{run_id}'") from None

    def _require_run(self, run_id: str) -> ManagedRun:
        """Look up a run by ID under the lock. Raises ``KeyError`` if missing."""
        with self._lock:
            return self._lookup(run_id)

    def create_run(self, config: RunConfig) -> ManagedRun:
        """Create a new run from *config* and register it.

        Assigns a unique run ID and returns the :class:`ManagedRun`.
        The run is not started — call :meth:`start_run` to begin execution.
        """
        run_id = generate_run_id()
        state = RunState(run_id=run_id)
        emitter = QueueEmitter()
        managed = ManagedRun(config=config, state=state, emitter=emitter)
        with self._lock:
            self._runs[run_id] = managed
        return managed

    def start_run(self, run_id: str) -> None:
        """Start the run loop in a daemon thread.

        The thread calls :func:`engine.run_loop` with the emitter built
        by :meth:`ManagedRun.build_emitter`, which fans out to the queue
        and any extra listeners.

        The entire operation runs under the registry lock so that
        concurrent calls cannot race on the same run.

        Raises ``KeyError`` if the run ID is not registered.
        """
        with self._lock:
            managed = self._lookup(run_id)
            if managed.thread is not None:
                raise RuntimeError(f"Run '{run_id}' has already been started")
            emitter = managed.build_emitter()
            config = managed.config
            state = managed.state

            def target() -> None:
                try:
                    run_loop(config, state, emitter)
                finally:
                    with self._done:
                        self._done.notify_all()

            thread = threading.Thread(
                target=target,
                daemon=True,
                name=f"run-{run_id}",
            )
            managed.thread = thread
            thread.start()

    def stop_run(self, run_id: str) -> None:
        """Signal the run to stop after the current iteration finishes."""
        self._require_run(run_id).state.request_stop()

    def pause_run(self, run_id: str) -> None:
        """Pause the run between iterations until :meth:`resume_run` is called."""
        self._require_run(run_id).state.request_pause()

    def resume_run(self, run_id: str) -> None:
        """Resume a paused run."""
        self._require_run(run_id).state.request_resume()

    def list_runs(self) -> list[ManagedRun]:
        """Return a snapshot of all registered runs."""
        with self._lock:
            return list(self._runs.values())

    def get_run(self, run_id: str) -> ManagedRun | None:
        """Look up a run by ID, returning ``None`` if not found."""
        with self._lock:
            return self._runs.get(run_id)

    def _finished_ids(self, run_ids: Sequence[str]) -> list[str]:
        """Return the subset of *run_ids* whose status is terminal."""
        with self._lock:
            return [
                run_id
                for run_id in run_ids
                if run_id in self._runs
                and self._runs[run_id].state.status in _TERMINAL_STATUSES
            ]

    def wait_for_any(
        self, run_ids: Sequence[str], timeout: float | None = None
    ) -> list[str]:
        """Block until at least one of *run_ids* reaches a terminal status.

        Returns the finished run IDs.  Returns ``[]`` if *timeout* elapses
        before any finish.  Unknown IDs are ignored (never reported as
        finished); when *run_ids* is empty or none are registered, returns
        ``[]`` immediately rather than blocking forever (nothing can wake it).
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            if not any(run_id in self._runs for run_id in run_ids):
                return []
        with self._done:
            while True:
                finished = self._finished_ids(run_ids)
                if finished:
                    return finished
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return []
                self._done.wait(timeout=remaining)

    def wait_for_all(
        self, run_ids: Sequence[str], timeout: float | None = None
    ) -> bool:
        """Block until every run in *run_ids* finishes or *timeout* elapses.

        Returns ``True`` iff all finished.  Unknown IDs can never finish, so
        if any ID in *run_ids* is not registered this returns ``False``
        immediately rather than blocking forever.  An empty *run_ids* is
        vacuously satisfied and returns ``True``.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        target = set(run_ids)
        with self._lock:
            if not all(run_id in self._runs for run_id in run_ids):
                return False
        with self._done:
            while True:
                if set(self._finished_ids(run_ids)) >= target:
                    return True
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                self._done.wait(timeout=remaining)

    def get_result(self, run_id: str) -> RunResult:
        """Snapshot the run's status and iteration counts.

        Returns current counts regardless of terminal state — wait first
        (e.g. via :meth:`wait_for_all`) for a final result.  Raises
        ``KeyError`` if the run ID is unknown.
        """
        state = self._require_run(run_id).state
        return RunResult(
            run_id=state.run_id,
            status=state.status,
            total=state.total,
            completed=state.completed,
            failed=state.failed,
            timed_out_count=state.timed_out_count,
        )

    def shutdown(self, timeout: float | None = None) -> bool:
        """Request stop on every run and join its thread.

        Returns ``True`` iff all live threads joined within *timeout*.
        With ``timeout=None`` this blocks until every run thread exits.
        """
        with self._lock:
            runs = list(self._runs.values())
        for managed in runs:
            managed.state.request_stop()

        deadline = None if timeout is None else time.monotonic() + timeout
        all_joined = True
        for managed in runs:
            thread = managed.thread
            if thread is None:
                continue
            remaining = None
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():
                all_joined = False
        return all_joined
