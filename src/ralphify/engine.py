"""Extracted run loop with structured event emission.

The core ``run_loop`` function is the autonomous agent loop previously
inlined in ``cli.py:run()``.  It accepts a ``RunConfig``, ``RunState``,
and ``EventEmitter``, making it reusable from both CLI and UI contexts.
"""

from __future__ import annotations

import subprocess
import sys
import time
import traceback
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import NamedTuple
from ralphify._events import Event, EventEmitter, EventType, NullEmitter
from ralphify._output import collect_output, format_duration
from ralphify.checks import (
    Check,
    discover_checks,
    format_check_failures,
    run_all_checks,
)
from ralphify.contexts import (
    Context,
    ContextResult,
    discover_contexts,
    resolve_contexts,
    run_all_contexts,
)
from ralphify._frontmatter import parse_frontmatter
from ralphify.instructions import Instruction, discover_instructions, resolve_instructions


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
    """Observable state for a run.

    Control methods (:meth:`request_stop`, :meth:`request_pause`,
    :meth:`request_resume`) use :class:`threading.Event` so the run loop
    can react at iteration boundaries without busy-waiting.

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
    timed_out: int = 0

    _stop_requested: bool = False
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _reload_requested: bool = False

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


class EnabledPrimitives(NamedTuple):
    """The enabled checks, contexts, and instructions for a project."""

    checks: list[Check]
    contexts: list[Context]
    instructions: list[Instruction]


def _discover_enabled_primitives(root: Path) -> EnabledPrimitives:
    """Discover all primitives and return only the enabled ones.

    This is the **single layer** responsible for enabled filtering.
    Downstream functions (``resolve_contexts``, ``resolve_instructions``,
    ``run_all_contexts``, ``run_all_checks``) trust that they receive
    only enabled primitives and do not re-filter.
    """
    return EnabledPrimitives(
        checks=[c for c in discover_checks(root) if c.enabled],
        contexts=[c for c in discover_contexts(root) if c.enabled],
        instructions=[i for i in discover_instructions(root) if i.enabled],
    )


def _wait_for_resume(state: RunState, emitter: EventEmitter) -> bool:
    """Block until the run is resumed or a stop is requested.

    Returns ``True`` if the run should continue, ``False`` if a stop was
    requested while paused.
    """
    emitter.emit(Event(
        type=EventType.RUN_PAUSED,
        run_id=state.run_id,
    ))
    while not state.wait_for_unpause(timeout=0.25):
        if state.stop_requested:
            break
    if state.stop_requested:
        state.status = RunStatus.STOPPED
        return False
    emitter.emit(Event(
        type=EventType.RUN_RESUMED,
        run_id=state.run_id,
    ))
    return True


def _handle_loop_transitions(
    state: RunState,
    config: RunConfig,
    primitives: EnabledPrimitives,
    emitter: EventEmitter,
) -> tuple[bool, EnabledPrimitives]:
    """Handle stop, pause, and reload transitions at the top of each iteration.

    Returns ``(True, primitives)`` if the loop should continue, or
    ``(False, primitives)`` if the loop should exit.  When a reload is
    consumed, the returned primitives are freshly discovered.
    """
    if state.stop_requested:
        state.status = RunStatus.STOPPED
        return False, primitives

    if state.paused:
        if not _wait_for_resume(state, emitter):
            return False, primitives

    if state.consume_reload_request():
        primitives = _discover_enabled_primitives(config.project_root)
        emitter.emit(Event(
            type=EventType.PRIMITIVES_RELOADED,
            run_id=state.run_id,
            data={
                "checks": len(primitives.checks),
                "contexts": len(primitives.contexts),
                "instructions": len(primitives.instructions),
            },
        ))

    return True, primitives


def _assemble_prompt(
    config: RunConfig,
    primitives: EnabledPrimitives,
    context_results: list[ContextResult],
    check_failures_text: str,
) -> str:
    """Build the full prompt for one iteration (pure text assembly).

    Reads the prompt source, resolves pre-computed context results and
    instructions, and appends any check-failure feedback from the previous
    iteration.  This is a pure function with no side effects — event
    emission is handled by the caller.
    """
    if config.prompt_text:
        prompt = config.prompt_text
    else:
        raw = Path(config.prompt_file).read_text()
        _, prompt = parse_frontmatter(raw)
    if context_results:
        prompt = resolve_contexts(prompt, context_results)
    if primitives.instructions:
        prompt = resolve_instructions(prompt, primitives.instructions)
    if check_failures_text:
        prompt = prompt + "\n\n" + check_failures_text
    return prompt


def _execute_agent(
    prompt: str,
    config: RunConfig,
    state: RunState,
    log_path_dir: Path | None,
    emitter: EventEmitter,
) -> int | None:
    """Run the agent subprocess and emit the result event.

    Updates ``state`` counters (completed / failed / timed_out) and returns
    the process return code, or ``None`` if the process timed out.
    """
    iteration = state.iteration
    cmd = [config.command] + config.args

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
        if log_path_dir:
            log_file = _write_log(log_path_dir, iteration, e.stdout, e.stderr)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Agent command not found: {config.command!r}. "
            f"Check the [agent] command in ralph.toml."
        )

    elapsed = time.monotonic() - start
    duration = format_duration(elapsed)

    # All state counter updates in one place for easy auditing.
    if returncode is None:
        state.timed_out += 1
        state.failed += 1
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
    return returncode


def _run_checks_phase(
    enabled_checks: list[Check],
    project_root: Path,
    state: RunState,
    emitter: EventEmitter,
) -> str:
    """Execute all checks, emit per-check and summary events.

    Returns the formatted check-failure text to feed back into the next
    iteration's prompt (empty string when all checks pass).
    """
    iteration = state.iteration

    emitter.emit(Event(
        type=EventType.CHECKS_STARTED,
        run_id=state.run_id,
        data={"iteration": iteration, "count": len(enabled_checks)},
    ))

    check_results = run_all_checks(enabled_checks, project_root)

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

    return format_check_failures(check_results)


def _run_iteration(
    config: RunConfig,
    state: RunState,
    primitives: EnabledPrimitives,
    log_path_dir: Path | None,
    check_failures_text: str,
    emitter: EventEmitter,
) -> tuple[str, bool]:
    """Execute one iteration of the agent loop.

    Runs contexts, assembles the prompt, executes the agent, and runs
    checks.  Returns ``(check_failures_text, should_continue)`` where
    *check_failures_text* is the feedback for the next iteration and
    *should_continue* is ``False`` when ``--stop-on-error`` triggers.
    """
    iteration = state.iteration

    emitter.emit(Event(
        type=EventType.ITERATION_STARTED,
        run_id=state.run_id,
        data={"iteration": iteration},
    ))

    # Run contexts (subprocess I/O)
    context_results: list[ContextResult] = []
    if primitives.contexts:
        context_results = run_all_contexts(
            primitives.contexts, config.project_root,
        )
        emitter.emit(Event(
            type=EventType.CONTEXTS_RESOLVED,
            run_id=state.run_id,
            data={"iteration": iteration, "count": len(primitives.contexts)},
        ))

    # Assemble prompt (pure text resolution)
    prompt = _assemble_prompt(
        config, primitives, context_results, check_failures_text,
    )
    emitter.emit(Event(
        type=EventType.PROMPT_ASSEMBLED,
        run_id=state.run_id,
        data={"iteration": iteration, "prompt_length": len(prompt)},
    ))

    returncode = _execute_agent(
        prompt, config, state, log_path_dir, emitter,
    )

    if returncode != 0 and config.stop_on_error:
        emitter.emit(Event(
            type=EventType.LOG_MESSAGE,
            run_id=state.run_id,
            data={"message": "Stopping due to --stop-on-error.", "level": "error"},
        ))
        return check_failures_text, False

    if primitives.checks:
        check_failures_text = _run_checks_phase(
            primitives.checks, config.project_root, state, emitter,
        )

    return check_failures_text, True


def run_loop(
    config: RunConfig,
    state: RunState,
    emitter: EventEmitter | None = None,
) -> None:
    """Execute the autonomous agent loop.

    This is the core loop extracted from ``cli.py:run()``.  All terminal
    output is replaced by ``emitter.emit()`` calls so the same logic can
    drive both CLI and web UIs.

    Orchestration only — the work of each iteration is in
    :func:`_run_iteration`.
    """
    if emitter is None:
        emitter = NullEmitter()

    state.status = RunStatus.RUNNING

    log_path_dir: Path | None = None
    if config.log_dir:
        log_path_dir = Path(config.log_dir)
        log_path_dir.mkdir(parents=True, exist_ok=True)

    check_failures_text = ""
    primitives = _discover_enabled_primitives(config.project_root)

    emitter.emit(Event(
        type=EventType.RUN_STARTED,
        run_id=state.run_id,
        data={
            "checks": len(primitives.checks),
            "contexts": len(primitives.contexts),
            "instructions": len(primitives.instructions),
            "max_iterations": config.max_iterations,
            "timeout": config.timeout,
            "delay": config.delay,
            "prompt_name": config.prompt_name,
        },
    ))

    try:
        while True:
            should_continue, primitives = _handle_loop_transitions(
                state, config, primitives, emitter,
            )
            if not should_continue:
                break

            state.iteration += 1
            if config.max_iterations is not None and state.iteration > config.max_iterations:
                break

            check_failures_text, should_continue = _run_iteration(
                config, state, primitives, log_path_dir, check_failures_text, emitter,
            )
            if not should_continue:
                break

            # Delay between iterations
            if config.delay > 0 and (
                config.max_iterations is None or state.iteration < config.max_iterations
            ):
                emitter.emit(Event(
                    type=EventType.LOG_MESSAGE,
                    run_id=state.run_id,
                    data={"message": f"Waiting {config.delay}s...", "level": "info"},
                ))
                time.sleep(config.delay)

    except KeyboardInterrupt:
        pass
    except Exception as exc:
        state.status = RunStatus.FAILED
        tb = traceback.format_exc()
        emitter.emit(Event(
            type=EventType.LOG_MESSAGE,
            run_id=state.run_id,
            data={
                "message": f"Run crashed: {exc}",
                "level": "error",
                "traceback": tb,
            },
        ))

    if state.status == RunStatus.RUNNING:
        state.status = RunStatus.COMPLETED

    reason = (
        "error" if state.status == RunStatus.FAILED
        else "user_requested" if state.status == RunStatus.STOPPED
        else "completed"
    )
    total = state.completed + state.failed
    emitter.emit(Event(
        type=EventType.RUN_STOPPED,
        run_id=state.run_id,
        data={
            "reason": reason,
            "total": total,
            "completed": state.completed,
            "failed": state.failed,
            "timed_out": state.timed_out,
        },
    ))
