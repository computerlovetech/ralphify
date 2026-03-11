"""CLI commands for ralphify — init, run, status, and scaffold new primitives.

This is the main module.  The ``run`` command implements the core autonomous
loop: read prompt, resolve contexts and instructions, pipe to the agent,
run checks, and repeat.
"""

import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ralphify import __version__
from ralphify._output import collect_output
from ralphify.checks import CheckResult, discover_checks, run_all_checks, format_check_failures
from ralphify.contexts import discover_contexts, run_all_contexts, resolve_contexts
from ralphify.instructions import discover_instructions, resolve_instructions
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
    "#FFD90F",  # Simpsons yellow
    "#FFD90F",
    "#D4D86A",  # transition
    "#7EBFA0",  # transition
    "#4DC8D9",  # Ralph's teal shirt
    "#4DC8D9",
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
    rprint(f"[italic cyan]{TAGLINE:^{width}}[/italic cyan]")
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


def _write_log(log_path_dir: Path, iteration: int, stdout: str | bytes | None, stderr: str | bytes | None) -> Path:
    """Write iteration output to a timestamped log file and return the path."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_path_dir / f"{iteration:03d}_{timestamp}.log"
    log_file.write_text(collect_output(stdout, stderr))
    return log_file


def _print_check_summary(results: list[CheckResult]) -> None:
    """Print a summary line for check results."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    parts = []
    if passed:
        parts.append(f"{passed} passed")
    if failed:
        parts.append(f"{failed} failed")
    rprint(f"  [bold]Checks:[/bold] {', '.join(parts)}")

    for r in results:
        if r.passed:
            rprint(f"    [green]✓[/green] {r.check.name}")
        elif r.timed_out:
            rprint(f"    [yellow]⏱[/yellow] {r.check.name} (timed out)")
        else:
            rprint(f"    [red]✗[/red] {r.check.name} (exit {r.exit_code})")


@app.command()
def run(
    n: Optional[int] = typer.Option(None, "-n", help="Max number of iterations. Infinite if not set."),
    prompt_text: Optional[str] = typer.Option(None, "-p", "--prompt", help="Ad-hoc prompt text. Overrides the prompt file."),
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
    config = _load_config()
    agent = config["agent"]
    command = agent["command"]
    args = agent.get("args", [])
    prompt_file = agent["prompt"]

    prompt_path = Path(prompt_file)
    if not prompt_text and not prompt_path.exists():
        rprint(f"[red]Prompt file '{prompt_file}' not found.[/red]")
        raise typer.Exit(1)

    log_path_dir = None
    if log_dir:
        log_path_dir = Path(log_dir)
        log_path_dir.mkdir(parents=True, exist_ok=True)
        rprint(f"[dim]Logging output to {log_path_dir}/[/dim]")

    if timeout is not None:
        rprint(f"[dim]Timeout: {_format_duration(timeout)} per iteration[/dim]")

    cmd = [command] + args
    completed = 0
    failed = 0
    timed_out = 0

    check_failures_text = ""
    enabled_checks = [c for c in discover_checks() if c.enabled]
    if enabled_checks:
        rprint(f"[dim]Checks: {len(enabled_checks)} enabled[/dim]")

    contexts = discover_contexts()
    enabled_contexts = [c for c in contexts if c.enabled] if contexts else []
    if enabled_contexts:
        rprint(f"[dim]Contexts: {len(enabled_contexts)} enabled[/dim]")

    instructions = discover_instructions()
    if instructions:
        enabled_inst = [i for i in instructions if i.enabled]
        rprint(f"[dim]Instructions: {len(enabled_inst)} enabled[/dim]")

    try:
        iteration = 0
        while True:
            iteration += 1
            if n is not None and iteration > n:
                break

            rprint(f"\n[bold blue]── Iteration {iteration} ──[/bold blue]")
            prompt = prompt_text if prompt_text else prompt_path.read_text()
            if enabled_contexts:
                context_results = run_all_contexts(enabled_contexts, Path("."))
                prompt = resolve_contexts(prompt, context_results)
            if instructions:
                prompt = resolve_instructions(prompt, instructions)
            if check_failures_text:
                prompt = prompt + "\n\n" + check_failures_text

            start = time.monotonic()
            log_file = None
            returncode = None

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
                timed_out += 1
                failed += 1
                if log_path_dir:
                    log_file = _write_log(log_path_dir, iteration, e.stdout, e.stderr)

            elapsed = time.monotonic() - start
            duration = _format_duration(elapsed)

            if returncode is None:
                color, icon = "yellow", "⏱"
                detail = f"timed out after {duration}"
            elif returncode == 0:
                completed += 1
                color, icon = "green", "✓"
                detail = f"completed ({duration})"
            else:
                failed += 1
                color, icon = "red", "✗"
                detail = f"failed with exit code {returncode} ({duration})"

            status_msg = f"[{color}]{icon} Iteration {iteration} {detail}"
            if log_file:
                status_msg += f" → {log_file}"
            status_msg += f"[/{color}]"
            rprint(status_msg)

            if returncode != 0 and stop_on_error:
                rprint("[red]Stopping due to --stop-on-error.[/red]")
                break

            if enabled_checks:
                check_results = run_all_checks(enabled_checks, Path("."))
                _print_check_summary(check_results)
                check_failures_text = format_check_failures(check_results)

            if delay > 0 and (n is None or iteration < n):
                rprint(f"[dim]Waiting {delay}s...[/dim]")
                time.sleep(delay)

    except KeyboardInterrupt:
        pass

    total = completed + failed
    summary = f"\n[green]Done: {total} iteration(s) — {completed} succeeded"
    if failed:
        summary += f", {failed} failed"
    if timed_out:
        summary += f" ({timed_out} timed out)"
    summary += "[/green]"
    rprint(summary)
