"""CLI commands for ralphify — init, run, status, and scaffold new primitives.

This is the main module.  The ``run`` command delegates to the engine module
for the core autonomous loop.  Terminal rendering of events is handled by
:class:`~ralphify._console_emitter.ConsoleEmitter`.
"""

import shutil
import sys
import tomllib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer
from rich.console import Console

from ralphify import __version__
from ralphify._console_emitter import ConsoleEmitter
from ralphify._discovery import Primitive
from ralphify._frontmatter import CHECK_MARKER, CONFIG_FILENAME, CONTEXT_MARKER, INSTRUCTION_MARKER, PRIMITIVES_DIR, RALPH_MARKER
from ralphify.checks import discover_checks
from ralphify.contexts import discover_contexts
from ralphify._run_types import RunConfig, RunState
from ralphify.engine import run_loop
from ralphify.instructions import discover_instructions
from ralphify.ralphs import discover_ralphs, resolve_ralph_source
from ralphify.detector import detect_project
from ralphify._templates import (
    CHECK_MD_TEMPLATE,
    CONTEXT_MD_TEMPLATE,
    INSTRUCTION_MD_TEMPLATE,
    RALPH_MD_TEMPLATE,
    ROOT_RALPH_TEMPLATE,
    RALPH_TOML_TEMPLATE,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_console = Console(highlight=False)
rprint = _console.print

app = typer.Typer()


class _DefaultRalphGroup(typer.core.TyperGroup):
    """Click group that routes unknown subcommands to ``ralph`` creation."""

    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands:
            args = ["ralph"] + list(args)
        return super().resolve_command(ctx, args)


new_app = typer.Typer(help="Scaffold new ralph primitives.", cls=_DefaultRalphGroup)
app.add_typer(new_app, name="new")

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


_P = TypeVar("_P", bound=Primitive)


def _print_primitives_section(label: str, items: list[_P], detail_fn: Callable[[_P], str]) -> None:
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

def _load_config() -> dict:
    """Load and return the ralph.toml config, exiting if not found."""
    config_path = Path(CONFIG_FILENAME)
    if not config_path.exists():
        rprint(f"[red]{CONFIG_FILENAME} not found. Run 'ralph init' first.[/red]")
        raise typer.Exit(1)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files."),
) -> None:
    """Initialize ralph config and prompt template."""
    config_path = Path(CONFIG_FILENAME)
    prompt_path = Path("RALPH.md")

    project_type = detect_project()

    if config_path.exists() and not force:
        rprint(f"[yellow]{CONFIG_FILENAME} already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(1)

    config_path.write_text(RALPH_TOML_TEMPLATE)
    rprint(f"[green]Created {CONFIG_FILENAME}[/green]")

    if prompt_path.exists() and not force:
        rprint("[yellow]RALPH.md already exists. Use --force to overwrite.[/yellow]")
    else:
        prompt_path.write_text(ROOT_RALPH_TEMPLATE)
        rprint("[green]Created RALPH.md[/green]")

    rprint(f"\nDetected project type: [bold]{project_type}[/bold]")
    rprint("Edit RALPH.md to customize your agent's behavior.")


def _scaffold_primitive(
    kind: str, name: str, filename: str, template: str,
    ralph: str | None = None,
) -> None:
    """Create a new ralph primitive directory and template file.

    When *ralph* is set, the primitive is created under
    ``.ralphify/ralphs/{ralph}/{kind}/{name}/`` instead of the global
    ``.ralphify/{kind}/{name}/``.
    """
    if ralph:
        prim_dir = Path(PRIMITIVES_DIR) / "ralphs" / ralph / kind / name
    else:
        prim_dir = Path(PRIMITIVES_DIR) / kind / name
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
    ralph: str | None = typer.Option(None, "--ralph", help="Scope check to a named ralph."),
) -> None:
    """Create a new check. Checks are scripts that run after each iteration to validate the agent's work (e.g. tests, linters)."""
    _scaffold_primitive("checks", name, CHECK_MARKER, CHECK_MD_TEMPLATE, ralph=ralph)


@new_app.command()
def instruction(
    name: str = typer.Argument(help="Name of the new instruction."),
    ralph: str | None = typer.Option(None, "--ralph", help="Scope instruction to a named ralph."),
) -> None:
    """Create a new instruction. Instructions are template-based prompts injected into the agent's context each iteration."""
    _scaffold_primitive("instructions", name, INSTRUCTION_MARKER, INSTRUCTION_MD_TEMPLATE, ralph=ralph)


@new_app.command()
def context(
    name: str = typer.Argument(help="Name of the new context."),
    ralph: str | None = typer.Option(None, "--ralph", help="Scope context to a named ralph."),
) -> None:
    """Create a new context. Contexts are dynamic data sources (scripts or static text) injected before each iteration."""
    _scaffold_primitive("contexts", name, CONTEXT_MARKER, CONTEXT_MD_TEMPLATE, ralph=ralph)


@new_app.command("ralph", hidden=True)
def new_ralph(
    name: str = typer.Argument(help="Name of the new ralph."),
) -> None:
    """Create a new ralph. Ralphs are reusable task-focused prompt files you can switch between."""
    _scaffold_primitive("ralphs", name, RALPH_MARKER, RALPH_MD_TEMPLATE)


@app.command()
def status() -> None:
    """Show current configuration and validate setup."""
    config = _load_config()
    agent = config["agent"]
    command = agent["command"]
    args = agent.get("args", [])
    ralph_file = agent["ralph"]
    ralph_path = Path(ralph_file)

    rprint("[bold]Configuration[/bold]")
    rprint(f"  Command: [cyan]{command} {' '.join(args)}[/cyan]")
    rprint(f"  Ralph:   [cyan]{ralph_file}[/cyan]")

    issues = []

    if ralph_path.exists():
        size = len(ralph_path.read_text())
        rprint(f"\n[green]✓[/green] Ralph file exists ({size} chars)")
    else:
        issues.append("ralph")
        rprint(f"\n[red]✗[/red] Ralph file '{ralph_file}' not found")

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

    ralphs = discover_ralphs()
    _print_primitives_section("Ralphs", ralphs,
        lambda p: p.description or "(no description)")

    if issues:
        rprint("\n[red]Not ready.[/red] Fix the issues above before running.")
        raise typer.Exit(1)
    else:
        rprint("\n[green]Ready to run.[/green]")


@app.command()
def run(
    prompt_name: str | None = typer.Argument(None, help="Name of a ralph in .ralphify/ralphs/."),
    n: int | None = typer.Option(None, "-n", help="Max number of iterations. Infinite if not set."),
    prompt_text: str | None = typer.Option(None, "-p", "--prompt", help="Ad-hoc prompt text. Overrides the prompt file."),
    prompt_file: str | None = typer.Option(None, "--prompt-file", "-f", help="Path to prompt file. Overrides ralph.toml."),
    stop_on_error: bool = typer.Option(False, "--stop-on-error", "-s", help="Stop if the agent exits with non-zero."),
    delay: float = typer.Option(0, "--delay", "-d", help="Seconds to wait between iterations."),
    log_dir: str | None = typer.Option(None, "--log-dir", "-l", help="Save iteration output to log files in this directory."),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Max seconds per iteration. Kill agent if exceeded."),
) -> None:
    """Run the autonomous coding loop.

    Each iteration: read RALPH.md, resolve context placeholders, resolve
    instruction placeholders, append any check failures from the previous
    iteration, pipe the assembled prompt to the agent, then run checks.
    Repeat until *n* iterations or Ctrl+C.
    """
    _print_banner()
    toml_config = _load_config()
    agent = toml_config["agent"]
    command = agent["command"]
    args = agent.get("args", [])

    # Inline text (-p/--prompt) bypasses file resolution entirely.
    if prompt_text:
        prompt_file_path = agent.get("ralph", "RALPH.md")
        resolved_prompt_name: str | None = None
    else:
        if prompt_name and prompt_file:
            rprint("[red]Cannot use both a ralph name and --prompt-file.[/red]")
            raise typer.Exit(1)

        try:
            prompt_file_path, resolved_prompt_name = resolve_ralph_source(
                prompt_name=prompt_name,
                prompt_file=prompt_file,
                toml_ralph=agent.get("ralph", "RALPH.md"),
            )
        except ValueError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)

        if not Path(prompt_file_path).exists():
            rprint(f"[red]Prompt file '{prompt_file_path}' not found.[/red]")
            raise typer.Exit(1)

    if log_dir:
        rprint(f"[dim]Logging output to {log_dir}/[/dim]")

    config = RunConfig(
        command=command,
        args=args,
        prompt_file=prompt_file_path,
        prompt_text=prompt_text,
        prompt_name=resolved_prompt_name,
        max_iterations=n,
        delay=delay,
        timeout=timeout,
        stop_on_error=stop_on_error,
        log_dir=log_dir,
    )
    state = RunState(run_id=uuid.uuid4().hex[:12])
    emitter = ConsoleEmitter(_console)

    run_loop(config, state, emitter)


