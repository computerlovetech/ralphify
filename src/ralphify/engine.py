"""Extracted run loop with structured event emission.

The core ``run_loop`` function is the autonomous agent loop previously
inlined in ``cli.py:run()``.  It accepts a ``RunConfig``, ``RunState``,
and ``EventEmitter``, making it reusable from both CLI and UI contexts.
"""

from __future__ import annotations

import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from ralphify._events import Event, EventEmitter, EventType, NullEmitter
from ralphify._output import collect_output
from ralphify.checks import (
    discover_checks,
    format_check_failures,
    run_all_checks,
)
from ralphify.contexts import discover_contexts, resolve_contexts, run_all_contexts
from ralphify._frontmatter import parse_frontmatter
from ralphify.instructions import discover_instructions, resolve_instructions


class RunStatus(Enum):
    """Lifecycle status of a run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RunConfig:
    """All settings for a single run.  Mutable — fields can change mid-run."""

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
    """Observable, thread-safe state for a run.

    Control methods use :class:`threading.Event` objects so the run loop
    can react at iteration boundaries without busy-waiting.
    """

    run_id: str
    status: RunStatus = RunStatus.PENDING
    iteration: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0

    _stop_requested: bool = False
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _reload_requested: bool = False

    def __post_init__(self) -> None:
        # Start un-paused
        self._pause_event.set()

    def request_stop(self) -> None:
        self._stop_requested = True
        # Unpause so the loop can exit
        self._pause_event.set()

    def request_pause(self) -> None:
        self.status = RunStatus.PAUSED
        self._pause_event.clear()

    def request_resume(self) -> None:
        self.status = RunStatus.RUNNING
        self._pause_event.set()

    def request_reload(self) -> None:
        self._reload_requested = True


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def _write_log(
    log_path_dir: Path,
    iteration: int,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> Path:
    """Write iteration output to a timestamped log file and return the path."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_path_dir / f"{iteration:03d}_{timestamp}.log"
    log_file.write_text(collect_output(stdout, stderr))
    return log_file


def run_loop(
    config: RunConfig,
    state: RunState,
    emitter: EventEmitter | None = None,
) -> None:
    """Execute the autonomous agent loop.

    This is the core loop extracted from ``cli.py:run()``.  All terminal
    output is replaced by ``emitter.emit()`` calls so the same logic can
    drive both CLI and web UIs.
    """
    if emitter is None:
        emitter = NullEmitter()

    state.status = RunStatus.RUNNING

    prompt_path = Path(config.prompt_file)
    log_path_dir: Path | None = None
    if config.log_dir:
        log_path_dir = Path(config.log_dir)
        log_path_dir.mkdir(parents=True, exist_ok=True)

    cmd = [config.command] + config.args

    check_failures_text = ""
    enabled_checks = [c for c in discover_checks(config.project_root) if c.enabled]
    contexts = discover_contexts(config.project_root)
    enabled_contexts = [c for c in contexts if c.enabled] if contexts else []
    instructions = discover_instructions(config.project_root)

    emitter.emit(Event(
        type=EventType.RUN_STARTED,
        run_id=state.run_id,
        data={
            "checks": len(enabled_checks),
            "contexts": len(enabled_contexts),
            "instructions": len([i for i in instructions if i.enabled]),
            "max_iterations": config.max_iterations,
            "timeout": config.timeout,
            "delay": config.delay,
            "prompt_name": config.prompt_name,
        },
    ))

    try:
        while True:
            # Check stop
            if state._stop_requested:
                state.status = RunStatus.STOPPED
                emitter.emit(Event(
                    type=EventType.RUN_STOPPED,
                    run_id=state.run_id,
                    data={"reason": "user_requested"},
                ))
                break

            # Check pause — block until resumed or stopped
            if not state._pause_event.is_set():
                emitter.emit(Event(
                    type=EventType.RUN_PAUSED,
                    run_id=state.run_id,
                ))
                while not state._pause_event.wait(timeout=0.25):
                    if state._stop_requested:
                        break
                if state._stop_requested:
                    state.status = RunStatus.STOPPED
                    emitter.emit(Event(
                        type=EventType.RUN_STOPPED,
                        run_id=state.run_id,
                        data={"reason": "user_requested"},
                    ))
                    break
                emitter.emit(Event(
                    type=EventType.RUN_RESUMED,
                    run_id=state.run_id,
                ))

            # Check hot-reload
            if state._reload_requested:
                state._reload_requested = False
                enabled_checks = [c for c in discover_checks(config.project_root) if c.enabled]
                contexts = discover_contexts(config.project_root)
                enabled_contexts = [c for c in contexts if c.enabled] if contexts else []
                instructions = discover_instructions(config.project_root)
                emitter.emit(Event(
                    type=EventType.PRIMITIVES_RELOADED,
                    run_id=state.run_id,
                    data={
                        "checks": len(enabled_checks),
                        "contexts": len(enabled_contexts),
                        "instructions": len([i for i in instructions if i.enabled]),
                    },
                ))

            state.iteration += 1
            iteration = state.iteration

            if config.max_iterations is not None and iteration > config.max_iterations:
                break

            emitter.emit(Event(
                type=EventType.ITERATION_STARTED,
                run_id=state.run_id,
                data={"iteration": iteration},
            ))

            # Assemble prompt
            if config.prompt_text:
                prompt = config.prompt_text
            else:
                raw = prompt_path.read_text()
                _, prompt = parse_frontmatter(raw)
            if enabled_contexts:
                context_results = run_all_contexts(enabled_contexts, config.project_root)
                prompt = resolve_contexts(prompt, context_results)
                emitter.emit(Event(
                    type=EventType.CONTEXTS_RESOLVED,
                    run_id=state.run_id,
                    data={"iteration": iteration, "count": len(enabled_contexts)},
                ))
            if instructions:
                prompt = resolve_instructions(prompt, instructions)
            if check_failures_text:
                prompt = prompt + "\n\n" + check_failures_text

            emitter.emit(Event(
                type=EventType.PROMPT_ASSEMBLED,
                run_id=state.run_id,
                data={"iteration": iteration, "prompt_length": len(prompt)},
            ))

            # Run agent
            start = time.monotonic()
            log_file: Path | None = None
            returncode: int | None = None

            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    text=True,
                    timeout=config.timeout,
                    capture_output=bool(log_path_dir),
                )
                if log_path_dir:
                    log_file = _write_log(log_path_dir, iteration, result.stdout, result.stderr)
                    if result.stdout:
                        sys.stdout.write(result.stdout)
                    if result.stderr:
                        sys.stderr.write(result.stderr)
                returncode = result.returncode
            except subprocess.TimeoutExpired as e:
                state.timed_out += 1
                state.failed += 1
                if log_path_dir:
                    log_file = _write_log(log_path_dir, iteration, e.stdout, e.stderr)

            elapsed = time.monotonic() - start
            duration = _format_duration(elapsed)

            if returncode is None:
                event_type = EventType.ITERATION_TIMED_OUT
                state_detail = f"timed out after {duration}"
            elif returncode == 0:
                state.completed += 1
                event_type = EventType.ITERATION_COMPLETED
                state_detail = f"completed ({duration})"
            else:
                state.failed += 1
                event_type = EventType.ITERATION_FAILED
                state_detail = f"failed with exit code {returncode} ({duration})"

            emitter.emit(Event(
                type=event_type,
                run_id=state.run_id,
                data={
                    "iteration": iteration,
                    "returncode": returncode,
                    "duration": elapsed,
                    "duration_formatted": duration,
                    "detail": state_detail,
                    "log_file": str(log_file) if log_file else None,
                },
            ))

            if returncode != 0 and config.stop_on_error:
                emitter.emit(Event(
                    type=EventType.LOG_MESSAGE,
                    run_id=state.run_id,
                    data={"message": "Stopping due to --stop-on-error."},
                ))
                break

            # Run checks
            if enabled_checks:
                emitter.emit(Event(
                    type=EventType.CHECKS_STARTED,
                    run_id=state.run_id,
                    data={"iteration": iteration, "count": len(enabled_checks)},
                ))

                check_results = run_all_checks(enabled_checks, config.project_root)

                for cr in check_results:
                    emitter.emit(Event(
                        type=EventType.CHECK_PASSED if cr.passed else EventType.CHECK_FAILED,
                        run_id=state.run_id,
                        data={
                            "iteration": iteration,
                            "check_name": cr.check.name,
                            "exit_code": cr.exit_code,
                            "timed_out": cr.timed_out,
                        },
                    ))

                emitter.emit(Event(
                    type=EventType.CHECKS_COMPLETED,
                    run_id=state.run_id,
                    data={
                        "iteration": iteration,
                        "passed": sum(1 for r in check_results if r.passed),
                        "failed": sum(1 for r in check_results if not r.passed),
                        "results": [
                            {
                                "name": r.check.name,
                                "passed": r.passed,
                                "exit_code": r.exit_code,
                                "timed_out": r.timed_out,
                            }
                            for r in check_results
                        ],
                    },
                ))

                check_failures_text = format_check_failures(check_results)

            # Delay
            if config.delay > 0 and (
                config.max_iterations is None or iteration < config.max_iterations
            ):
                emitter.emit(Event(
                    type=EventType.LOG_MESSAGE,
                    run_id=state.run_id,
                    data={"message": f"Waiting {config.delay}s..."},
                ))
                time.sleep(config.delay)

    except KeyboardInterrupt:
        pass

    if state.status == RunStatus.RUNNING:
        state.status = RunStatus.COMPLETED

    total = state.completed + state.failed
    emitter.emit(Event(
        type=EventType.RUN_STOPPED,
        run_id=state.run_id,
        data={
            "reason": "completed",
            "total": total,
            "completed": state.completed,
            "failed": state.failed,
            "timed_out": state.timed_out,
        },
    ))
