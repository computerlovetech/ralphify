"""CLI commands for ralphify — run and scaffold ralphs.

The ``run`` command delegates to the engine module for the core autonomous
loop.  Terminal rendering of events is handled by
:class:`~ralphify._console_emitter.ConsoleEmitter`.
"""

from __future__ import annotations

import math
import os
import shlex
import shutil
import signal
import sys
from pathlib import Path
from typing import Any, NoReturn

import typer
from rich.console import Console

from ralphify import __version__
from ralphify._console_emitter import ConsoleEmitter
from ralphify._frontmatter import (
    CMD_FIELD_NAME,
    CMD_FIELD_RUN,
    CMD_FIELD_TIMEOUT,
    CMD_NAME_RE,
    FIELD_AGENT,
    FIELD_ARGS,
    FIELD_COMMANDS,
    FIELD_CREDIT,
    RALPH_MARKER,
    VALID_NAME_CHARS_MSG,
    parse_frontmatter,
)
from ralphify._run_types import Command, DEFAULT_COMMAND_TIMEOUT, RunConfig, RunState, generate_run_id
from ralphify.engine import run_loop

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_console = Console(highlight=False)

app = typer.Typer()


def _exit_error(msg: str) -> NoReturn:
    """Print an error in red and exit with code 1."""
    _console.print(f"[red]{msg}[/red]")
    raise typer.Exit(1)


def _is_nonempty_string(value: Any) -> bool:
    """Return True if *value* is a non-empty string (after stripping whitespace)."""
    return isinstance(value, str) and bool(value.strip())


def _is_valid_timeout(value: Any) -> bool:
    """Return True if *value* is a positive finite number (not a bool)."""
    if isinstance(value, bool):  # bool is a subclass of int — reject first
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


def _validate_name(name: str, context: str) -> None:
    """Validate that *name* contains only characters valid for placeholders.

    *context* labels the kind of name for the error message (e.g.
    ``"Arg"`` or ``"Command"``).
    """
    if not CMD_NAME_RE.fullmatch(name):
        _exit_error(
            f"{context} name '{name}' contains invalid characters. "
            f"{VALID_NAME_CHARS_MSG}"
        )


BANNER = [
    ("██████╗░░█████╗░██╗░░░░░██████╗░██╗░░██╗██╗███████╗██╗░░░██╗", "#8B6CF0"),
    ("██╔══██╗██╔══██╗██║░░░░░██╔══██╗██║░░██║██║██╔════╝╚██╗░██╔╝", "#A78BF5"),
    ("██████╔╝███████║██║░░░░░██████╔╝███████║██║█████╗░░░╚████╔╝░", "#D4A0E0"),
    ("██╔══██╗██╔══██║██║░░░░░██╔═══╝░██╔══██║██║██╔══╝░░░░╚██╔╝░░", "#E8956B"),
    ("██║░░██║██║░░██║███████╗██║░░░░░██║░░██║██║██║░░░░░░░░██║░░░", "#E87B4A"),
    ("╚═╝░░╚═╝╚═╝░░╚═╝╚══════╝╚═╝░░░░░╚═╝░░╚═╝╚═╝╚═╝░░░░░░░░╚═╝░░░", "#E06030"),
]

TAGLINE = "Stop stressing over not having an agent running. Ralph is always running"

_INIT_TEMPLATE = """\
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: git-log
    run: git log --oneline -5
args:
  - focus
---

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

## Recent changes

{{ commands.git-log }}

## Focus

{{ args.focus }}

## Task

<!-- Replace this section with your task description -->

- Implement one thing per iteration
- Run tests and fix failures before committing
- Commit with a descriptive message and push
"""


def _print_banner() -> None:
    width = shutil.get_terminal_size().columns
    art_width = max(len(line) for line, _ in BANNER)
    pad = max(0, (width - art_width) // 2)
    prefix = " " * pad

    _console.print()
    for line, color in BANNER:
        _console.print(f"[bold {color}]{prefix}{line}[/bold {color}]")
    _console.print()
    _console.print(f"[italic #A78BF5]{TAGLINE:^{width}}[/italic #A78BF5]")
    _console.print()
    help_text = "Run 'ralph --help' for usage information"
    _console.print(f"[dim]{help_text:^{width}}[/dim]")
    star_text = "⭐ Star us on GitHub: https://github.com/computerlovetech/ralphify"
    _console.print(f"[dim]{star_text:^{width}}[/dim]")
    _console.print()


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"ralphify {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", callback=_version_callback, is_eager=True),
) -> None:
    """Stop stressing over not having an agent running. Ralph is always running."""
    if ctx.invoked_subcommand is None:
        _print_banner()
        _console.print(ctx.get_help())
        raise typer.Exit()


@app.command()
def new(
    name: str | None = typer.Argument(None, help="Name for the new ralph. If omitted, the agent will help you choose."),
) -> None:
    """Create a new ralph with AI-guided setup."""
    from ralphify._skills import build_agent_command, detect_agent, install_skill

    try:
        agent = detect_agent()
    except RuntimeError as exc:
        _exit_error(str(exc))

    try:
        install_skill("new-ralph", agent.name)
    except RuntimeError as exc:
        _exit_error(str(exc))

    cmd = build_agent_command(agent.name, "new-ralph", name)
    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError:
        _exit_error(f"Agent command '{cmd[0]}' not found on PATH.")


@app.command()
def init(
    name: str | None = typer.Argument(None, help="Directory name. If omitted, creates RALPH.md in the current directory."),
) -> None:
    """Scaffold a new ralph with a ready-to-customize template."""
    if name:
        target_dir = Path.cwd() / name
        target_dir.mkdir(exist_ok=True)
    else:
        target_dir = Path.cwd()

    ralph_file = target_dir / RALPH_MARKER
    if ralph_file.exists():
        _exit_error(f"{RALPH_MARKER} already exists at '{ralph_file}'.")

    ralph_file.write_text(_INIT_TEMPLATE, encoding="utf-8")
    rel = ralph_file.relative_to(Path.cwd())
    _console.print(f"[green]Created[/green] {rel}")
    _console.print(f"[dim]Edit the file, then run:[/dim] ralph run {name or '.'}")


def _parse_user_args(
    raw_args: list[str],
    declared_names: list[str] | None,
) -> dict[str, str]:
    """Parse extra CLI args into a dict of user arguments.

    Supports ``--name value`` (named) and positional args mapped to
    *declared_names* from frontmatter ``args: [...]``.  A bare ``--``
    token ends flag parsing — everything after it is positional.
    """
    result: dict[str, str] = {}
    positional_index = 0
    flags_ended = False
    it = iter(raw_args)
    for token in it:
        if not flags_ended and token == "--":
            flags_ended = True
            continue
        if not flags_ended and token.startswith("--"):
            rest = token[2:]
            if "=" in rest:
                name, value = rest.split("=", 1)
            else:
                name = rest
                try:
                    value = next(it)
                except StopIteration:
                    raise typer.BadParameter(f"Flag '--{name}' requires a value.") from None
            if not CMD_NAME_RE.fullmatch(name):
                raise typer.BadParameter(
                    f"Arg name '{name}' contains invalid characters. "
                    f"{VALID_NAME_CHARS_MSG}"
                )
            result[name] = value
        else:
            if not declared_names:
                raise typer.BadParameter(
                    f"Positional argument '{token}' requires args declared in {RALPH_MARKER} frontmatter. "
                    f"Use --name value syntax or add 'args: [...]' to your {RALPH_MARKER}."
                )
            # Skip declared names already provided via named flags
            while positional_index < len(declared_names) and declared_names[positional_index] in result:
                positional_index += 1
            if positional_index >= len(declared_names):
                raise typer.BadParameter(
                    f"Too many positional arguments. Expected at most {len(declared_names)} "
                    f"({', '.join(declared_names)})."
                )
            result[declared_names[positional_index]] = token
            positional_index += 1
    return result


def _validate_declared_args(raw_args: Any) -> list[str] | None:
    """Validate the ``args`` field from frontmatter and return a clean list.

    Returns ``None`` when *raw_args* is ``None`` (field absent).  Exits
    with an error when the value is malformed (wrong type, invalid names,
    or duplicates).
    """
    if raw_args is None:
        return None
    if not isinstance(raw_args, list):
        _exit_error(f"'{FIELD_ARGS}' must be a list of strings.")
    if not all(isinstance(a, str) for a in raw_args):
        _exit_error(f"'{FIELD_ARGS}' items must be strings, got non-string value.")
    seen: set[str] = set()
    for name in raw_args:
        _validate_name(name, "Arg")
        if name in seen:
            _exit_error(f"Duplicate arg name '{name}'.")
        seen.add(name)
    return raw_args


def _parse_command_items(raw_commands: list[dict[str, Any]]) -> list[Command]:
    """Validate and parse raw command dicts from frontmatter into Command objects."""
    commands: list[Command] = []
    seen_names: set[str] = set()
    for cmd_def in raw_commands:
        if not isinstance(cmd_def, dict) or CMD_FIELD_NAME not in cmd_def or CMD_FIELD_RUN not in cmd_def:
            _exit_error(f"Each command must have '{CMD_FIELD_NAME}' and '{CMD_FIELD_RUN}' fields.")
        for key in (CMD_FIELD_NAME, CMD_FIELD_RUN):
            if not _is_nonempty_string(cmd_def[key]):
                _exit_error(f"Command '{key}' must be a non-empty string.")
        cmd_name = cmd_def[CMD_FIELD_NAME]
        cmd_run = cmd_def[CMD_FIELD_RUN]
        _validate_name(cmd_name, "Command")
        if cmd_name in seen_names:
            _exit_error(f"Duplicate command name '{cmd_name}'.")
        seen_names.add(cmd_name)
        timeout = cmd_def.get(CMD_FIELD_TIMEOUT, DEFAULT_COMMAND_TIMEOUT)
        if not _is_valid_timeout(timeout):
            _exit_error(
                f"Command '{cmd_name}' has invalid timeout: {timeout!r}. "
                f"Must be a positive number."
            )
        commands.append(Command(
            name=cmd_name,
            run=cmd_run,
            timeout=timeout,
        ))
    return commands


def _validate_commands(raw_commands: Any) -> list[Command]:
    """Validate the ``commands`` field from frontmatter and return parsed Commands.

    Returns an empty list when *raw_commands* is ``None`` (field absent).
    Exits with an error when the value is malformed.
    """
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        _exit_error(f"'{FIELD_COMMANDS}' must be a list of {{name, run}} mappings.")
    return _parse_command_items(raw_commands)


def _resolve_ralph_paths(ralph_path: str) -> tuple[Path, Path]:
    """Resolve the ralph directory and RALPH.md file from a user-provided path.

    Accepts a directory containing RALPH.md or a direct path to RALPH.md.
    Returns ``(ralph_dir, ralph_file)``.  Exits with an error message when
    the path is invalid or RALPH.md is not found.
    """
    path = Path(ralph_path)
    if path.is_dir():
        ralph_dir = path
        ralph_file = path / RALPH_MARKER
    elif path.is_file() and path.name == RALPH_MARKER:
        ralph_dir = path.parent
        ralph_file = path
    else:
        _exit_error(f"'{ralph_path}' is not a directory or {RALPH_MARKER} file.")

    if not ralph_file.exists():
        _exit_error(f"{RALPH_MARKER} not found at '{ralph_file}'.")

    return ralph_dir, ralph_file


def _validate_agent(raw_agent: Any) -> str:
    """Validate the ``agent`` frontmatter field and check the binary exists.

    Returns the validated agent string.  Exits with an error when the
    value is missing, malformed, or the binary is not found on PATH.
    """
    if not _is_nonempty_string(raw_agent):
        _exit_error(f"Missing or empty '{FIELD_AGENT}' field in {RALPH_MARKER} frontmatter.")
    try:
        agent_binary = shlex.split(raw_agent)[0]
    except ValueError as exc:
        _exit_error(f"Malformed '{FIELD_AGENT}' field in {RALPH_MARKER} frontmatter: {exc}")
    if not shutil.which(agent_binary):
        _exit_error(f"Agent command '{agent_binary}' not found on PATH.")
    return raw_agent


def _validate_credit(raw_credit: Any) -> bool:
    """Validate the ``credit`` frontmatter field and return the resolved value.

    Returns ``True`` when the field is absent (default behavior).
    Exits with an error when the value is not a boolean.
    """
    if raw_credit is None:
        return True
    if not isinstance(raw_credit, bool):
        _exit_error(f"'{FIELD_CREDIT}' must be true or false, got {raw_credit!r}.")
    return raw_credit


def _validate_run_options(
    max_iterations: int | None,
    delay: float,
    timeout: float | None,
) -> None:
    """Validate numeric CLI run options.

    Exits with an error when any value is out of range or non-finite.
    """
    if max_iterations is not None and max_iterations < 1:
        _exit_error(f"'-n' must be a positive integer, got {max_iterations}.")
    if not math.isfinite(delay) or delay < 0:
        _exit_error(f"'--delay' must be non-negative, got {delay}.")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        _exit_error(f"'--timeout' must be a positive number, got {timeout}.")


def _build_run_config(
    ralph_path: str,
    max_iterations: int | None,
    stop_on_error: bool,
    delay: float,
    log_dir: str | None,
    timeout: float | None,
    extra_args: list[str] | None = None,
) -> RunConfig:
    """Read RALPH.md from the given path, validate, and build a RunConfig."""
    # Validate CLI options first — cheap checks before file I/O.
    _validate_run_options(max_iterations, delay, timeout)

    ralph_dir, ralph_file = _resolve_ralph_paths(ralph_path)

    ralph_text = ralph_file.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(ralph_text)

    agent = _validate_agent(fm.get(FIELD_AGENT))
    commands = _validate_commands(fm.get(FIELD_COMMANDS))
    declared_names = _validate_declared_args(fm.get(FIELD_ARGS))
    ralph_args: dict[str, str] = {}
    if extra_args:
        ralph_args = _parse_user_args(extra_args, declared_names)

    credit = _validate_credit(fm.get(FIELD_CREDIT))

    return RunConfig(
        agent=agent,
        ralph_dir=ralph_dir.resolve(),
        ralph_file=ralph_file.resolve(),
        commands=commands,
        args=ralph_args,
        max_iterations=max_iterations,
        delay=delay,
        timeout=timeout,
        stop_on_error=stop_on_error,
        log_dir=Path(log_dir) if log_dir else None,
        project_root=Path.cwd(),
        credit=credit,
    )


@app.command(context_settings={"allow_extra_args": True, "allow_interspersed_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Path to a ralph directory or RALPH.md file."),
    n: int | None = typer.Option(None, "-n", help="Max number of iterations. Infinite if not set."),
    stop_on_error: bool = typer.Option(False, "--stop-on-error", "-s", help="Stop if the agent exits non-zero or times out."),
    delay: float = typer.Option(0, "--delay", "-d", help="Seconds to wait between iterations."),
    log_dir: str | None = typer.Option(None, "--log-dir", "-l", help="Save iteration output to log files in this directory."),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Max seconds per iteration. Kill agent if exceeded."),
) -> None:
    """Run the autonomous coding loop.

    Each iteration: run commands, assemble prompt with command output,
    pipe to agent, repeat until *n* iterations or Ctrl+C.

    Extra flags (--name value) and positional args after the path are
    passed as user arguments.  Use {{ args.name }} placeholders in
    RALPH.md to reference them.
    """
    extra = list(ctx.args)

    config = _build_run_config(
        path, n, stop_on_error, delay, log_dir, timeout,
        extra_args=extra or None,
    )

    if log_dir:
        _console.print(f"[dim]Logging output to {log_dir}/[/dim]")

    state = RunState(run_id=generate_run_id())
    emitter = ConsoleEmitter(_console)

    ctrl_c_count = 0
    original_handler = signal.getsignal(signal.SIGINT)

    def _sigint_handler(signum: int, frame: Any) -> None:
        nonlocal ctrl_c_count
        ctrl_c_count += 1
        if ctrl_c_count == 1:
            state.request_stop()
            _console.print("\n[yellow]Finishing current iteration… (Ctrl+C again to force stop)[/yellow]")
        else:
            signal.signal(signal.SIGINT, original_handler)
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)
    try:
        run_loop(config, state, emitter)
    finally:
        signal.signal(signal.SIGINT, original_handler)
