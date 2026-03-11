"""Run loop with structured event emission.

The core ``run_loop`` function is the autonomous agent loop.  It accepts
a ``RunConfig``, ``RunState``, and ``EventEmitter``, making it reusable
from both CLI and UI contexts.

Run data types (``RunStatus``, ``RunConfig``, ``RunState``) live in
``_run_types.py`` so modules that only need types don't import the engine.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple
from ralphify._events import Event, EventEmitter, EventType, NullEmitter
from ralphify._output import collect_output, format_duration
from ralphify._run_types import RunConfig, RunState, RunStatus
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


class _BoundEmitter:
    """Wraps an EventEmitter with a fixed run_id for concise emission.

    Engine-internal helper so every call site doesn't have to repeat
    ``Event(type=..., run_id=state.run_id, data={...})``.
    """

    def __init__(self, emitter: EventEmitter, run_id: str) -> None:
        self._emitter = emitter
        self._run_id = run_id

    def __call__(
        self, event_type: EventType, data: dict[str, Any] | None = None,
    ) -> None:
        self._emitter.emit(Event(
            type=event_type, run_id=self._run_id, data=data or {},
        ))


def _wait_for_resume(state: RunState, emit: _BoundEmitter) -> bool:
    """Block until the run is resumed or a stop is requested.

    Returns ``True`` if the run should continue, ``False`` if a stop was
    requested while paused.
    """
    emit(EventType.RUN_PAUSED)
    while not state.wait_for_unpause(timeout=0.25):
        if state.stop_requested:
            break
    if state.stop_requested:
        state.status = RunStatus.STOPPED
        return False
    emit(EventType.RUN_RESUMED)
    return True


def _handle_loop_transitions(
    state: RunState,
    config: RunConfig,
    primitives: EnabledPrimitives,
    emit: _BoundEmitter,
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
        if not _wait_for_resume(state, emit):
            return False, primitives

    if state.consume_reload_request():
        primitives = _discover_enabled_primitives(config.project_root)
        emit(EventType.PRIMITIVES_RELOADED, {
            "checks": len(primitives.checks),
            "contexts": len(primitives.contexts),
            "instructions": len(primitives.instructions),
        })

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


class _AgentResult(NamedTuple):
    """Result of running the agent subprocess."""

    returncode: int | None  # None means timed out
    elapsed: float
    log_file: Path | None


def _is_claude_command(cmd: list[str]) -> bool:
    """Return True if the command looks like Claude Code (supports stream-json)."""
    if not cmd:
        return False
    binary = Path(cmd[0]).name
    return binary == "claude"


def _run_agent_process_streaming(
    cmd: list[str],
    prompt: str,
    timeout: float | None,
    log_path_dir: Path | None,
    iteration: int,
    emit: _BoundEmitter,
) -> _AgentResult:
    """Run the agent subprocess with line-by-line streaming of JSON output.

    Used for agents that support ``--output-format stream-json`` (e.g. Claude
    Code).  Each JSON line is emitted as an ``AGENT_ACTIVITY`` event so the UI
    can render a live activity feed.

    Falls back gracefully if any line is not valid JSON — it is still
    collected for logging but not emitted as a structured event.

    Timeout is enforced manually between line reads (``Popen`` has no
    built-in timeout on iteration).  A ``try/finally`` ensures the child
    process is cleaned up even on unexpected errors.
    """
    stream_cmd = cmd + ["--output-format", "stream-json", "--verbose"]
    start = time.monotonic()
    deadline = (start + timeout) if timeout else None
    stdout_lines: list[str] = []
    stderr_data = ""
    returncode: int | None = None

    proc = subprocess.Popen(
        stream_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Send prompt and close stdin so the agent can start.
        proc.stdin.write(prompt)  # type: ignore[union-attr]
        proc.stdin.close()  # type: ignore[union-attr]

        for line in proc.stdout:  # type: ignore[union-attr]
            if deadline and time.monotonic() > deadline:
                proc.kill()
                proc.wait()
                break
            stdout_lines.append(line)
            stripped = line.strip()
            if stripped:
                try:
                    parsed = json.loads(stripped)
                    emit(EventType.AGENT_ACTIVITY, {"raw": parsed})
                except json.JSONDecodeError:
                    pass
            sys.stdout.write(line)
        else:
            # stdout exhausted — process should be done
            proc.wait()
            returncode = proc.returncode

        stderr_data = proc.stderr.read()  # type: ignore[union-attr]
        if stderr_data:
            sys.stderr.write(stderr_data)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    log_file: Path | None = None
    if log_path_dir:
        log_file = _write_log(log_path_dir, iteration, "".join(stdout_lines), stderr_data)

    return _AgentResult(
        returncode=returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
    )


def _run_agent_process(
    cmd: list[str],
    prompt: str,
    timeout: float | None,
    log_path_dir: Path | None,
    iteration: int,
) -> _AgentResult:
    """Run the agent subprocess, optionally write logs, and return the result.

    When *log_path_dir* is set, output is captured, written to a log file,
    then echoed to stdout/stderr so the user still sees it live.  When unset,
    output streams directly to the terminal (no capture overhead).

    Returns ``returncode=None`` when the process times out.
    Raises ``FileNotFoundError`` if the command binary does not exist.
    """
    start = time.monotonic()
    log_file: Path | None = None
    returncode: int | None = None

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            timeout=timeout,
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

    return _AgentResult(
        returncode=returncode,
        elapsed=time.monotonic() - start,
        log_file=log_file,
    )


def _execute_agent(
    prompt: str,
    config: RunConfig,
    state: RunState,
    log_path_dir: Path | None,
    emit: _BoundEmitter,
) -> int | None:
    """Run the agent subprocess and emit the result event.

    Updates ``state`` counters (completed / failed / timed_out) and returns
    the process return code, or ``None`` if the process timed out.

    When the agent command is ``claude``, uses streaming mode to emit
    ``AGENT_ACTIVITY`` events for each JSON line of output.  Other agents
    fall back to the non-streaming ``subprocess.run()`` path.
    """
    cmd = [config.command] + config.args

    try:
        if _is_claude_command(cmd):
            agent = _run_agent_process_streaming(
                cmd, prompt, config.timeout, log_path_dir, state.iteration, emit,
            )
        else:
            agent = _run_agent_process(
                cmd, prompt, config.timeout, log_path_dir, state.iteration,
            )
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Agent command not found: {config.command!r}. "
            f"Check the [agent] command in ralph.toml."
        )

    duration = format_duration(agent.elapsed)

    # All state counter updates in one place for easy auditing.
    if agent.returncode is None:
        state.timed_out += 1
        state.failed += 1
        event_type = EventType.ITERATION_TIMED_OUT
        state_detail = f"timed out after {duration}"
    elif agent.returncode == 0:
        state.completed += 1
        event_type = EventType.ITERATION_COMPLETED
        state_detail = f"completed ({duration})"
    else:
        state.failed += 1
        event_type = EventType.ITERATION_FAILED
        state_detail = f"failed with exit code {agent.returncode} ({duration})"

    emit(event_type, {
        "iteration": state.iteration,
        "returncode": agent.returncode,
        "duration": agent.elapsed,
        "duration_formatted": duration,
        "detail": state_detail,
        "log_file": str(agent.log_file) if agent.log_file else None,
    })
    return agent.returncode


def _run_checks_phase(
    enabled_checks: list[Check],
    project_root: Path,
    state: RunState,
    emit: _BoundEmitter,
) -> str:
    """Execute all checks, emit per-check and summary events.

    Returns the formatted check-failure text to feed back into the next
    iteration's prompt (empty string when all checks pass).
    """
    iteration = state.iteration

    emit(EventType.CHECKS_STARTED, {"iteration": iteration, "count": len(enabled_checks)})

    check_results = run_all_checks(enabled_checks, project_root)

    # Build per-result data once; reused for both per-check and summary events.
    results_data: list[dict] = []
    for cr in check_results:
        result = {
            "name": cr.check.name,
            "passed": cr.passed,
            "exit_code": cr.exit_code,
            "timed_out": cr.timed_out,
            "output": cr.output,
        }
        results_data.append(result)
        emit(
            EventType.CHECK_PASSED if cr.passed else EventType.CHECK_FAILED,
            {"iteration": iteration, **result},
        )

    passed = sum(1 for r in results_data if r["passed"])
    emit(EventType.CHECKS_COMPLETED, {
        "iteration": iteration,
        "passed": passed,
        "failed": len(results_data) - passed,
        "results": results_data,
    })

    return format_check_failures(check_results)


def _run_iteration(
    config: RunConfig,
    state: RunState,
    primitives: EnabledPrimitives,
    log_path_dir: Path | None,
    check_failures_text: str,
    emit: _BoundEmitter,
) -> tuple[str, bool]:
    """Execute one iteration of the agent loop.

    Runs contexts, assembles the prompt, executes the agent, and runs
    checks.  Returns ``(check_failures_text, should_continue)`` where
    *check_failures_text* is the feedback for the next iteration and
    *should_continue* is ``False`` when ``--stop-on-error`` triggers.
    """
    iteration = state.iteration

    emit(EventType.ITERATION_STARTED, {"iteration": iteration})

    # Run contexts (subprocess I/O)
    context_results: list[ContextResult] = []
    if primitives.contexts:
        context_results = run_all_contexts(
            primitives.contexts, config.project_root,
        )
        emit(EventType.CONTEXTS_RESOLVED, {"iteration": iteration, "count": len(primitives.contexts)})

    # Assemble prompt (pure text resolution)
    prompt = _assemble_prompt(
        config, primitives, context_results, check_failures_text,
    )
    emit(EventType.PROMPT_ASSEMBLED, {"iteration": iteration, "prompt_length": len(prompt)})

    returncode = _execute_agent(
        prompt, config, state, log_path_dir, emit,
    )

    if returncode != 0 and config.stop_on_error:
        emit(EventType.LOG_MESSAGE, {"message": "Stopping due to --stop-on-error.", "level": "error"})
        return check_failures_text, False

    if primitives.checks:
        check_failures_text = _run_checks_phase(
            primitives.checks, config.project_root, state, emit,
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

    emit = _BoundEmitter(emitter, state.run_id)
    state.status = RunStatus.RUNNING
    state.started_at = datetime.now(timezone.utc)

    log_path_dir: Path | None = None
    if config.log_dir:
        log_path_dir = Path(config.log_dir)
        log_path_dir.mkdir(parents=True, exist_ok=True)

    check_failures_text = ""
    primitives = _discover_enabled_primitives(config.project_root)

    emit(EventType.RUN_STARTED, {
        "checks": len(primitives.checks),
        "contexts": len(primitives.contexts),
        "instructions": len(primitives.instructions),
        "max_iterations": config.max_iterations,
        "timeout": config.timeout,
        "delay": config.delay,
        "prompt_name": config.prompt_name,
    })

    try:
        while True:
            should_continue, primitives = _handle_loop_transitions(
                state, config, primitives, emit,
            )
            if not should_continue:
                break

            state.iteration += 1
            if config.max_iterations is not None and state.iteration > config.max_iterations:
                break

            check_failures_text, should_continue = _run_iteration(
                config, state, primitives, log_path_dir, check_failures_text, emit,
            )
            if not should_continue:
                break

            # Delay between iterations
            if config.delay > 0 and (
                config.max_iterations is None or state.iteration < config.max_iterations
            ):
                emit(EventType.LOG_MESSAGE, {"message": f"Waiting {config.delay}s...", "level": "info"})
                time.sleep(config.delay)

    except KeyboardInterrupt:
        pass
    except Exception as exc:
        state.status = RunStatus.FAILED
        tb = traceback.format_exc()
        emit(EventType.LOG_MESSAGE, {
            "message": f"Run crashed: {exc}",
            "level": "error",
            "traceback": tb,
        })

    if state.status == RunStatus.RUNNING:
        state.status = RunStatus.COMPLETED

    reason = (
        "error" if state.status == RunStatus.FAILED
        else "user_requested" if state.status == RunStatus.STOPPED
        else "completed"
    )
    total = state.completed + state.failed
    emit(EventType.RUN_STOPPED, {
        "reason": reason,
        "total": total,
        "completed": state.completed,
        "failed": state.failed,
        "timed_out": state.timed_out,
    })
