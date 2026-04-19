"""Run loop with structured event emission.

The core ``run_loop`` function is the autonomous agent loop.  It accepts
a ``RunConfig``, ``RunState``, and ``EventEmitter``, making it reusable
from both CLI and UI contexts.

The loop: run commands → assemble prompt → pipe to agent → repeat.
"""

from __future__ import annotations

import shlex
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ralphify._agent import execute_agent
from ralphify._events import (
    AgentActivityData,
    BoundEmitter,
    CommandsCompletedData,
    CommandsStartedData,
    EventEmitter,
    EventType,
    IterationEndedData,
    IterationStartedData,
    NullEmitter,
    OutputStream,
    PromptAssembledData,
    RunStartedData,
    RunStoppedData,
)
from ralphify._frontmatter import (
    FIELD_AGENT,
    FIELD_COMMANDS,
    RALPH_MARKER,
    parse_frontmatter,
)
from ralphify._output import format_duration
from ralphify._run_types import (
    Command,
    RunConfig,
    RunState,
    RunStatus,
)
from ralphify._resolver import resolve_all, resolve_args
from ralphify._runner import run_command
from ralphify.adapters import select_adapter


_PAUSE_POLL_INTERVAL = 0.25  # seconds between pause/resume checks
_RELATIVE_CMD_PREFIX = "./"  # commands starting with this run from the ralph directory


def _field_hint(field_name: str) -> str:
    return f"Check the '{field_name}' field in your {RALPH_MARKER} frontmatter."


_CREDIT_INSTRUCTION = (
    "\n\n---\n\n"
    "IMPORTANT: When you make any git commits, include the following trailer "
    "at the end of your commit message:\n\n"
    "Co-authored-by: Ralphify <noreply@ralphify.co>"
)


def _wait_for_resume(state: RunState, emit: BoundEmitter) -> bool:
    """Block until the run is resumed or a stop is requested."""
    emit(EventType.RUN_PAUSED)
    while not state.wait_for_unpause(timeout=_PAUSE_POLL_INTERVAL):
        if state.stop_requested:
            break
    if state.stop_requested:
        state.status = RunStatus.STOPPED
        return False
    emit(EventType.RUN_RESUMED)
    return True


def _handle_control_signals(state: RunState, emit: BoundEmitter) -> bool:
    """Handle stop and pause requests at the top of each iteration."""
    if state.stop_requested:
        state.status = RunStatus.STOPPED
        return False
    if state.paused:
        if not _wait_for_resume(state, emit):
            return False
    return True


def _run_commands(
    commands: list[Command],
    ralph_dir: Path,
    project_root: Path,
    user_args: dict[str, str],
) -> dict[str, str]:
    """Execute all commands and return a dict of name→output.

    Commands with paths starting with ``./`` run relative to the ralph
    directory.  Other commands run from the project root.
    """
    results: dict[str, str] = {}
    quoted_args = {k: shlex.quote(v) for k, v in user_args.items()}
    for cmd in commands:
        run_str = resolve_args(cmd.run, quoted_args)
        if run_str.lstrip().startswith(_RELATIVE_CMD_PREFIX):
            cwd = ralph_dir
        else:
            cwd = project_root
        try:
            result = run_command(
                command=run_str,
                cwd=cwd,
                timeout=cmd.timeout,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Command '{cmd.name}' binary not found: {run_str!r}. "
                f"{_field_hint(FIELD_COMMANDS)}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                f"Command '{cmd.name}' has invalid syntax: {run_str!r}. "
                f"{_field_hint(FIELD_COMMANDS)}"
            ) from exc
        output = result.output
        if result.timed_out:
            output += f"\n\n[Command '{cmd.name}' timed out after {format_duration(cmd.timeout)} — output may be incomplete]"
        results[cmd.name] = output
    return results


def _build_ralph_context(config: RunConfig, state: RunState) -> dict[str, str]:
    """Build the context dict for ``{{ ralph.X }}`` placeholders."""
    ctx: dict[str, str] = {
        "name": config.ralph_dir.name,
        "iteration": str(state.iteration),
    }
    if config.max_iterations is not None:
        ctx["max_iterations"] = str(config.max_iterations)
    return ctx


def _assemble_prompt(
    config: RunConfig,
    state: RunState,
    command_outputs: dict[str, str],
) -> str:
    """Build the full prompt for one iteration.

    Reads the RALPH.md body, resolves user args, command output, and
    context placeholders.
    """
    raw = config.ralph_file.read_text(encoding="utf-8")
    _, prompt = parse_frontmatter(raw)
    ralph_context = _build_ralph_context(config, state)
    prompt = resolve_all(prompt, command_outputs, config.args, ralph_context)
    if config.credit:
        prompt += _CREDIT_INSTRUCTION
    return prompt


def _run_agent_phase(
    prompt: str,
    config: RunConfig,
    state: RunState,
    emit: BoundEmitter,
) -> tuple[bool, bool]:
    """Run the agent subprocess, update state counters, and emit the result event.

    Returns ``(agent_succeeded, stop_for_completion_signal)``.
    """
    try:
        cmd = shlex.split(config.agent)
    except ValueError as exc:
        raise ValueError(
            f"Invalid agent command syntax: {config.agent!r}. {_field_hint(FIELD_AGENT)}"
        ) from exc

    adapter = select_adapter(cmd)
    completion_signal = config.completion_signal

    def _on_output_line(line: str, stream: OutputStream) -> None:
        if emit.wants_agent_output_lines():
            emit.agent_output_line(line, stream, state.iteration)

    if emit.wants_agent_output_lines() or config.log_dir is not None:
        on_output_line = _on_output_line
    else:
        on_output_line = None

    # Capture full stdout only when somebody downstream actually needs the
    # bytes — log writing, or promise detection for adapters that cannot
    # work from ``agent.result_text`` alone.  Without this gate every
    # iteration would buffer the entire transcript even for verbose
    # streaming agents, regressing memory vs the prior tail-scan path.
    capture_stdout_for_promise = (
        config.stop_on_completion_signal and adapter.requires_full_stdout_for_completion
    )
    capture_stdout = config.log_dir is not None or capture_stdout_for_promise

    try:

        def on_activity(data: dict[str, Any]) -> None:
            emit(
                EventType.AGENT_ACTIVITY,
                AgentActivityData(raw=data, iteration=state.iteration),
            )

        agent = execute_agent(
            cmd,
            prompt,
            timeout=config.timeout,
            log_dir=config.log_dir,
            iteration=state.iteration,
            adapter=adapter,
            on_activity=on_activity,
            on_output_line=on_output_line,
            capture_result_text=True,
            capture_stdout=capture_stdout,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Agent command not found: {config.agent!r}. {_field_hint(FIELD_AGENT)}"
        ) from exc

    duration = format_duration(agent.elapsed)
    promise_completed = agent.success and adapter.extract_completion_signal(
        result_text=agent.result_text,
        stdout=agent.captured_stdout,
        user_signal=completion_signal,
    )
    if promise_completed:
        state.promise_completed = True

    if agent.timed_out:
        state.mark_timed_out()
        event_type = EventType.ITERATION_TIMED_OUT
        state_detail = f"timed out after {duration}"
    elif agent.success:
        state.mark_completed()
        event_type = EventType.ITERATION_COMPLETED
        if promise_completed:
            state_detail = (
                "completed via promise tag "
                f"<promise>{completion_signal}</promise> ({duration})"
            )
        else:
            state_detail = f"completed ({duration})"
    else:
        state.mark_failed()
        event_type = EventType.ITERATION_FAILED
        state_detail = f"failed with exit code {agent.returncode} ({duration})"

    ended_data = IterationEndedData(
        iteration=state.iteration,
        returncode=agent.returncode,
        duration=agent.elapsed,
        duration_formatted=duration,
        detail=state_detail,
        log_file=str(agent.log_file) if agent.log_file else None,
        result_text=agent.result_text,
    )
    if not emit.wants_agent_output_lines():
        # When peek was off, echo any captured raw output after the spinner
        # stops so blocking agents do not appear silent. Structured agents
        # already surface their parsed result_text, so avoid echoing raw JSON
        # unless we explicitly captured logs.
        if config.log_dir is not None:
            ended_data["echo_stdout"] = agent.captured_stdout
            ended_data["echo_stderr"] = agent.captured_stderr
        elif agent.result_text is None and agent.captured_stdout is not None:
            ended_data["echo_stdout"] = agent.captured_stdout

    emit(event_type, ended_data)
    return agent.success, promise_completed and config.stop_on_completion_signal


def _run_iteration(
    config: RunConfig,
    state: RunState,
    emit: BoundEmitter,
) -> tuple[bool, bool]:
    """Execute one iteration of the agent loop.

    Returns (should_continue, stop_for_completion_signal):
      - should_continue: True if the loop should continue, False to break
      - stop_for_completion_signal: True if a completion signal ended the run early
    """
    iteration = state.iteration

    emit(EventType.ITERATION_STARTED, IterationStartedData(iteration=iteration))

    command_outputs: dict[str, str] = {}
    if config.commands:
        emit(
            EventType.COMMANDS_STARTED,
            CommandsStartedData(iteration=iteration, count=len(config.commands)),
        )
        command_outputs = _run_commands(
            config.commands,
            config.ralph_dir,
            config.project_root,
            config.args,
        )
        emit(
            EventType.COMMANDS_COMPLETED,
            CommandsCompletedData(
                iteration=iteration,
                count=len(command_outputs),
            ),
        )

    prompt = _assemble_prompt(config, state, command_outputs)
    emit(
        EventType.PROMPT_ASSEMBLED,
        PromptAssembledData(iteration=iteration, prompt_length=len(prompt)),
    )

    agent_succeeded, stop_for_completion_signal = _run_agent_phase(
        prompt, config, state, emit
    )

    if not agent_succeeded and config.stop_on_error:
        state.status = RunStatus.FAILED
        emit.log_error("Stopping due to --stop-on-error.")
        return False, stop_for_completion_signal

    return True, stop_for_completion_signal


def _delay_if_needed(config: RunConfig, state: RunState, emit: BoundEmitter) -> None:
    """Sleep between iterations when a delay is configured.

    Uses :meth:`RunState.wait_for_stop` so that stop requests break the
    delay immediately rather than polling.
    """
    if config.delay > 0 and (
        config.max_iterations is None or state.iteration < config.max_iterations
    ):
        emit.log_info(f"Waiting {format_duration(config.delay)}...")
        state.wait_for_stop(timeout=config.delay)


def run_loop(
    config: RunConfig,
    state: RunState,
    emitter: EventEmitter | None = None,
) -> None:
    """Execute the autonomous agent loop.

    Each iteration: run commands → assemble prompt → pipe to agent → repeat.
    """
    if emitter is None:
        emitter = NullEmitter()

    emit = BoundEmitter(emitter, state.run_id)
    state.status = RunStatus.RUNNING
    state.started_at = datetime.now(timezone.utc)

    if config.log_dir:
        config.log_dir.mkdir(parents=True, exist_ok=True)

    emit(
        EventType.RUN_STARTED,
        RunStartedData(
            ralph_name=config.ralph_dir.name,
            agent=config.agent,
            commands=len(config.commands),
            max_iterations=config.max_iterations,
            timeout=config.timeout,
            delay=config.delay,
        ),
    )

    try:
        while True:
            if not _handle_control_signals(state, emit):
                break

            if (
                config.max_iterations is not None
                and state.iteration >= config.max_iterations
            ):
                break
            state.iteration += 1

            should_continue, stop_for_completion_signal = _run_iteration(
                config, state, emit
            )
            if stop_for_completion_signal:
                state.status = RunStatus.COMPLETED
                break
            if not should_continue:
                break

            _delay_if_needed(config, state, emit)

    except KeyboardInterrupt:
        state.status = RunStatus.STOPPED
    except Exception as exc:
        state.status = RunStatus.FAILED
        tb = traceback.format_exc()
        emit.log_error(f"Run crashed: {exc}", traceback=tb)

    if state.status == RunStatus.RUNNING:
        state.status = RunStatus.COMPLETED

    reason = state.status.reason
    emit(
        EventType.RUN_STOPPED,
        RunStoppedData(
            reason=reason,
            total=state.total,
            completed=state.completed,
            failed=state.failed,
            timed_out_count=state.timed_out_count,
        ),
    )
