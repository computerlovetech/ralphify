"""Multi-run orchestration for the UI layer.

Wraps run engine threads and provides a registry for managing concurrent runs.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from ralphify._events import Event, EventEmitter, QueueEmitter
from ralphify.engine import RunConfig, RunState, run_loop


@dataclass
class ManagedRun:
    """A run wrapped with its thread and event queue."""

    config: RunConfig
    state: RunState
    emitter: QueueEmitter
    thread: threading.Thread | None = None
    _extra_emitters: list[EventEmitter] = field(default_factory=list)

    def add_listener(self, emitter: EventEmitter) -> None:
        """Register an additional emitter to receive events from this run."""
        self._extra_emitters.append(emitter)


class _FanoutEmitter:
    """Emits to multiple emitters."""

    def __init__(self, emitters: list[EventEmitter]) -> None:
        self._emitters = emitters

    def emit(self, event: Event) -> None:
        for e in self._emitters:
            e.emit(event)


class RunManager:
    """Registry of runs. Thread-safe."""

    def __init__(self) -> None:
        self._runs: dict[str, ManagedRun] = {}
        self._lock = threading.Lock()

    def create_run(self, config: RunConfig) -> ManagedRun:
        """Create a new run from *config* and register it.

        Assigns a unique run ID and returns the :class:`ManagedRun`.
        The run is not started — call :meth:`start_run` to begin execution.
        """
        run_id = uuid.uuid4().hex[:12]
        state = RunState(run_id=run_id)
        emitter = QueueEmitter()
        managed = ManagedRun(config=config, state=state, emitter=emitter)
        with self._lock:
            self._runs[run_id] = managed
        return managed

    def start_run(self, run_id: str) -> None:
        """Start the run loop in a daemon thread.

        The thread calls :func:`engine.run_loop` with a fanout emitter
        that broadcasts events to the run's queue and any extra listeners.
        """
        with self._lock:
            managed = self._runs[run_id]
        all_emitters: list[EventEmitter] = [managed.emitter] + managed._extra_emitters
        fanout = _FanoutEmitter(all_emitters)
        thread = threading.Thread(
            target=run_loop,
            args=(managed.config, managed.state, fanout),
            daemon=True,
            name=f"run-{run_id}",
        )
        managed.thread = thread
        thread.start()

    def stop_run(self, run_id: str) -> None:
        """Signal the run to stop after the current iteration finishes."""
        with self._lock:
            managed = self._runs[run_id]
        managed.state.request_stop()

    def pause_run(self, run_id: str) -> None:
        """Pause the run between iterations until :meth:`resume_run` is called."""
        with self._lock:
            managed = self._runs[run_id]
        managed.state.request_pause()

    def resume_run(self, run_id: str) -> None:
        """Resume a paused run."""
        with self._lock:
            managed = self._runs[run_id]
        managed.state.request_resume()

    def list_runs(self) -> list[ManagedRun]:
        """Return a snapshot of all registered runs."""
        with self._lock:
            return list(self._runs.values())

    def get_run(self, run_id: str) -> ManagedRun | None:
        """Look up a run by ID, returning ``None`` if not found."""
        with self._lock:
            return self._runs.get(run_id)
