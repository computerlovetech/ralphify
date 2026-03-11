"""CLI commands for ralphify — init, run, status, and scaffold new primitives.

This is the main module.  The ``run`` command delegates to the engine module
for the core autonomous loop.  It provides a ``ConsoleEmitter`` that renders
events to the terminal, reproducing the original terminal output exactly.
"""

import shutil
import tomllib
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ralphify import __version__
from ralphify._events import Event, EventType
from ralphify.checks import discover_checks
from ralphify.contexts import discover_contexts
from ralphify.engine import RunConfig, RunState, _format_duration, run_loop
from ralphify.instructions import discover_instructions
from ralphify.detector import detect_project

_console = Console(highlight=False)
rprint = _console.print

app = typer.Typer()

new_app = typer.Typer(help="Scaffold new ralph primitives.", invoke_without_command=True)
app.add_typer(new_app, name="new")


@new_app.callback()
def new_callback(ctx: typer.Context) -> None:
    """Scaffold new ralph primitives."""
    if ctx.invoked_subcommand is None:
        rprint(ctx.get_help())
        raise typer.Exit()

BANNER_LINES = [
    "██████╗░░█████╗░██╗░░░░░██████╗░██╗░░██╗██╗███████╗██╗░░░██╗",
    "██╔══██╗██╔══██╗██║░░░░░██╔══██╗██║░░██║██║██╔════╝╚██╗░██╔╝",
    "██████╔╝███████║██║░░░░░██████╔╝███████║██║█████╗░░░╚████╔╝░",
    "██╔══██╗██╔══██║██║░░░░░██╔═══╝░██╔══██║██║██╔══╝░░░░╚██╔╝░░",
    "██║░░██║██║░░██║███████╗██║░░░░░██║░░██║██║██║░░░░░░░░██║░░░",
    "╚═╝░░╚═╝╚═╝░░╚═╝╚══════╝╚═╝░░░░░╚═╝░░╚═╝╚═╝╚═╝░░░░░░░░╚═╝░░░",
]

TAGLINE = "Harness toolkit for autonomous AI coding loops"


BANNER_COLORS = [
    "#8B6CF0",  # light violet
    "#A78BF5",  # soft violet
    "#D4A0E0",  # pink-violet transition
    "#E8956B",  # warm transition
    "#E87B4A",  # orange accent
    "#E06030",  # deep orange
]


def _print_primitives_section(label: str, items: list, detail_fn) -> None:
    """Print a status section for discovered primitives."""
    if items:
        rprint(f"\n[bold]{label}:[/bold]  {len(items)} found")
        for item in items:
            icon = "[green]✓[/green]" if item.enabled else "[dim]○[/dim]"
            rprint(f"  {icon} {item.name:<18} {detail_fn(item)}")
    else:
        rprint(f"\n[bold]{label}:[/bold]  [dim]none[/dim]")


def _print_banner() -> None:
    width = shutil.get_terminal_size().columns
    art_width = max(len(line) for line in BANNER_LINES)
    pad = max(0, (width - art_width) // 2)
    prefix = " " * pad

    rprint()
    for line, color in zip(BANNER_LINES, BANNER_COLORS):
        rprint(f"[bold {color}]{prefix}{line}[/bold {color}]")
    rprint()
    rprint(f"[italic #A78BF5]{TAGLINE:^{width}}[/italic #A78BF5]")
    rprint(f"{'':^{width}}")
    help_text = "Run 'ralph --help' for usage information"
    rprint(f"[dim]{help_text:^{width}}[/dim]")
    star_text = "⭐ Star us on GitHub: https://github.com/computerlovetech/ralphify"
    rprint(f"[dim]{star_text:^{width}}[/dim]")
    rprint()


def _version_callback(value: bool) -> None:
    if value:
        rprint(f"ralphify {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", callback=_version_callback, is_eager=True),
) -> None:
    """Harness toolkit for autonomous AI coding loops."""
    if ctx.invoked_subcommand is None:
        _print_banner()
        rprint(ctx.get_help())
        raise typer.Exit()

CONFIG_FILENAME = "ralph.toml"


def _load_config() -> dict:
    """Load and return the ralph.toml config, exiting if not found."""
    config_path = Path(CONFIG_FILENAME)
    if not config_path.exists():
        rprint(f"[red]{CONFIG_FILENAME} not found. Run 'ralph init' first.[/red]")
        raise typer.Exit(1)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


RALPH_TOML_TEMPLATE = """\
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
"""

CHECK_MD_TEMPLATE = """\
---
command: ruff check .
timeout: 60
enabled: true
---
<!--
Optional instructions for the agent when this check fails.
Appended to the prompt alongside the command output.

Example: "Fix all lint errors. Do not add noqa comments."
-->
"""

INSTRUCTION_MD_TEMPLATE = """\
---
enabled: true
---
<!--
Write your instruction content below.
This text will be injected into PROMPT.md every iteration.

Use {{ instructions.<name> }} in PROMPT.md to place this specifically,
or {{ instructions }} to inject all enabled instructions.
-->
"""

CONTEXT_MD_TEMPLATE = """\
---
command: git log --oneline -10
timeout: 30
enabled: true
---
<!--
Optional static text injected above the command output.
The command runs each iteration and its stdout is appended.

Use {{ contexts.<name> }} in PROMPT.md to place this specifically,
or {{ contexts }} to inject all enabled contexts.
-->
"""

PROMPT_TEMPLATE = """\
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

- Implement one thing per iteration
- Search before creating anything new
- No placeholder code — full implementations only
- Run tests and fix failures before committing
- Commit with a descriptive message

<!-- Add your project-specific instructions below -->
"""


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files."),
) -> None:
    """Initialize ralph config and prompt template."""
    config_path = Path(CONFIG_FILENAME)
    prompt_path = Path("PROMPT.md")

    project_type = detect_project()

    if config_path.exists() and not force:
        rprint(f"[yellow]{CONFIG_FILENAME} already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(1)

    config_path.write_text(RALPH_TOML_TEMPLATE)
    rprint(f"[green]Created {CONFIG_FILENAME}[/green]")

    if prompt_path.exists() and not force:
        rprint("[yellow]PROMPT.md already exists. Use --force to overwrite.[/yellow]")
    else:
        prompt_path.write_text(PROMPT_TEMPLATE)
        rprint("[green]Created PROMPT.md[/green]")

    rprint(f"\nDetected project type: [bold]{project_type}[/bold]")
    rprint("Edit PROMPT.md to customize your agent's behavior.")


def _scaffold_primitive(kind: str, name: str, filename: str, template: str) -> None:
    """Create a new ralph primitive directory and template file."""
    prim_dir = Path(".ralph") / kind / name
    prim_file = prim_dir / filename
    label = filename.split(".")[0].capitalize()
    if prim_file.exists():
        rprint(f"[red]{label} '{name}' already exists at {prim_file}[/red]")
        raise typer.Exit(1)
    prim_dir.mkdir(parents=True, exist_ok=True)
    prim_file.write_text(template)
    rprint(f"[green]Created {prim_file}[/green]")


@new_app.command()
def check(
    name: str = typer.Argument(help="Name of the new check."),
) -> None:
    """Create a new check. Checks are scripts that run after each iteration to validate the agent's work (e.g. tests, linters)."""
    _scaffold_primitive("checks", name, "CHECK.md", CHECK_MD_TEMPLATE)


@new_app.command()
def instruction(
    name: str = typer.Argument(help="Name of the new instruction."),
) -> None:
    """Create a new instruction. Instructions are template-based prompts injected into the agent's context each iteration."""
    _scaffold_primitive("instructions", name, "INSTRUCTION.md", INSTRUCTION_MD_TEMPLATE)


@new_app.command()
def context(
    name: str = typer.Argument(help="Name of the new context."),
) -> None:
    """Create a new context. Contexts are dynamic data sources (scripts or static text) injected before each iteration."""
    _scaffold_primitive("contexts", name, "CONTEXT.md", CONTEXT_MD_TEMPLATE)


@app.command()
def status() -> None:
    """Show current configuration and validate setup."""
    config = _load_config()
    agent = config["agent"]
    command = agent["command"]
    args = agent.get("args", [])
    prompt_file = agent["prompt"]
    prompt_path = Path(prompt_file)

    rprint("[bold]Configuration[/bold]")
    rprint(f"  Command: [cyan]{command} {' '.join(args)}[/cyan]")
    rprint(f"  Prompt:  [cyan]{prompt_file}[/cyan]")

    issues = []

    if prompt_path.exists():
        size = len(prompt_path.read_text())
        rprint(f"\n[green]✓[/green] Prompt file exists ({size} chars)")
    else:
        issues.append("prompt")
        rprint(f"\n[red]✗[/red] Prompt file '{prompt_file}' not found")

    if shutil.which(command):
        rprint(f"[green]✓[/green] Command '{command}' found on PATH")
    else:
        issues.append("command")
        rprint(f"[red]✗[/red] Command '{command}' not found on PATH")

    checks = discover_checks()
    _print_primitives_section("Checks", checks,
        lambda c: str(c.script.name) if c.script else c.command or "?")

    contexts = discover_contexts()
    _print_primitives_section("Contexts", contexts,
        lambda c: str(c.script.name) if c.script else c.command or "(static)")

    instructions = discover_instructions()
    _print_primitives_section("Instructions", instructions,
        lambda i: (i.content[:50] + "...") if len(i.content) > 50 else i.content)

    if issues:
        rprint("\n[red]Not ready.[/red] Fix the issues above before running.")
        raise typer.Exit(1)
    else:
        rprint("\n[green]Ready to run.[/green]")


class ConsoleEmitter:
    """Renders engine events to the Rich console, reproducing original CLI output."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._rprint = console.print

    def emit(self, event: Event) -> None:
        d = event.data
        t = event.type

        if t == EventType.RUN_STARTED:
            if d.get("timeout"):
                self._rprint(f"[dim]Timeout: {_format_duration(d['timeout'])} per iteration[/dim]")
            if d.get("checks"):
                self._rprint(f"[dim]Checks: {d['checks']} enabled[/dim]")
            if d.get("contexts"):
                self._rprint(f"[dim]Contexts: {d['contexts']} enabled[/dim]")
            if d.get("instructions"):
                self._rprint(f"[dim]Instructions: {d['instructions']} enabled[/dim]")

        elif t == EventType.ITERATION_STARTED:
            self._rprint(f"\n[bold blue]── Iteration {d['iteration']} ──[/bold blue]")

        elif t in (EventType.ITERATION_COMPLETED, EventType.ITERATION_FAILED, EventType.ITERATION_TIMED_OUT):
            iteration = d["iteration"]
            returncode = d.get("returncode")
            detail = d["detail"]
            log_file = d.get("log_file")

            if returncode is None:
                color, icon = "yellow", "\u23f1"
            elif returncode == 0:
                color, icon = "green", "\u2713"
            else:
                color, icon = "red", "\u2717"

            status_msg = f"[{color}]{icon} Iteration {iteration} {detail}"
            if log_file:
                status_msg += f" \u2192 {log_file}"
            status_msg += f"[/{color}]"
            self._rprint(status_msg)

        elif t == EventType.CHECKS_COMPLETED:
            passed = d["passed"]
            failed = d["failed"]
            parts = []
            if passed:
                parts.append(f"{passed} passed")
            if failed:
                parts.append(f"{failed} failed")
            self._rprint(f"  [bold]Checks:[/bold] {', '.join(parts)}")
            for r in d["results"]:
                if r["passed"]:
                    self._rprint(f"    [green]\u2713[/green] {r['name']}")
                elif r["timed_out"]:
                    self._rprint(f"    [yellow]\u23f1[/yellow] {r['name']} (timed out)")
                else:
                    self._rprint(f"    [red]\u2717[/red] {r['name']} (exit {r['exit_code']})")

        elif t == EventType.LOG_MESSAGE:
            msg = d.get("message", "")
            if "Stopping" in msg:
                self._rprint(f"[red]{msg}[/red]")
            elif "Waiting" in msg:
                self._rprint(f"[dim]{msg}[/dim]")

        elif t == EventType.RUN_STOPPED:
            if d.get("reason") == "completed":
                total = d.get("total", 0)
                completed = d.get("completed", 0)
                failed = d.get("failed", 0)
                timed_out_count = d.get("timed_out", 0)
                summary = f"\n[green]Done: {total} iteration(s) \u2014 {completed} succeeded"
                if failed:
                    summary += f", {failed} failed"
                if timed_out_count:
                    summary += f" ({timed_out_count} timed out)"
                summary += "[/green]"
                self._rprint(summary)


@app.command()
def run(
    n: Optional[int] = typer.Option(None, "-n", help="Max number of iterations. Infinite if not set."),
    prompt_text: Optional[str] = typer.Option(None, "-p", "--prompt", help="Ad-hoc prompt text. Overrides the prompt file."),
    prompt_file: Optional[str] = typer.Option(None, "--prompt-file", "-f", help="Path to prompt file. Overrides ralph.toml."),
    stop_on_error: bool = typer.Option(False, "--stop-on-error", "-s", help="Stop if the agent exits with non-zero."),
    delay: float = typer.Option(0, "--delay", "-d", help="Seconds to wait between iterations."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", "-l", help="Save iteration output to log files in this directory."),
    timeout: Optional[float] = typer.Option(None, "--timeout", "-t", help="Max seconds per iteration. Kill agent if exceeded."),
) -> None:
    """Run the autonomous coding loop.

    Each iteration: read PROMPT.md, resolve context placeholders, resolve
    instruction placeholders, append any check failures from the previous
    iteration, pipe the assembled prompt to the agent, then run checks.
    Repeat until *n* iterations or Ctrl+C.
    """
    _print_banner()
    toml_config = _load_config()
    agent = toml_config["agent"]
    command = agent["command"]
    args = agent.get("args", [])
    prompt_file_path = prompt_file if prompt_file else agent["prompt"]

    prompt_path = Path(prompt_file_path)
    if not prompt_text and not prompt_path.exists():
        rprint(f"[red]Prompt file '{prompt_file_path}' not found.[/red]")
        raise typer.Exit(1)

    if log_dir:
        rprint(f"[dim]Logging output to {log_dir}/[/dim]")

    config = RunConfig(
        command=command,
        args=args,
        prompt_file=prompt_file_path,
        prompt_text=prompt_text,
        max_iterations=n,
        delay=delay,
        timeout=timeout,
        stop_on_error=stop_on_error,
        log_dir=log_dir,
    )
    state = RunState(run_id=uuid.uuid4().hex[:12])
    emitter = ConsoleEmitter(_console)

    run_loop(config, state, emitter)


@app.command()
def ui(
    port: int = typer.Option(8765, "--port", help="Port to serve the UI on."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to."),
) -> None:
    """Launch the web-based orchestration dashboard."""
    try:
        from ralphify.ui.app import create_app
    except ImportError:
        rprint("[red]UI deps not installed. Run: pip install ralphify[ui][/red]")
        raise typer.Exit(1)
    import uvicorn

    rprint(f"[bold]Starting Ralphify UI at http://{host}:{port}[/bold]")
    uvicorn.run(create_app(), host=host, port=port)
