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

_console = Console(highlight=False)
rprint = _console.print

from ralphify import __version__
from ralphify.checks import discover_checks, run_all_checks, format_check_failures
from ralphify.detector import detect_project

app = typer.Typer()

new_app = typer.Typer(help="Scaffold new ralph primitives.")
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
    "#FFD90F",  # Simpsons yellow
    "#FFD90F",
    "#D4D86A",  # transition
    "#7EBFA0",  # transition
    "#4DC8D9",  # Ralph's teal shirt
    "#4DC8D9",
]


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
    _print_banner()
    if ctx.invoked_subcommand is None:
        raise typer.Exit()

CONFIG_FILENAME = "ralph.toml"

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
        rprint(f"[yellow]PROMPT.md already exists. Use --force to overwrite.[/yellow]")
    else:
        prompt_path.write_text(PROMPT_TEMPLATE)
        rprint(f"[green]Created PROMPT.md[/green]")

    rprint(f"\nDetected project type: [bold]{project_type}[/bold]")
    rprint("Edit PROMPT.md to customize your agent's behavior.")


@new_app.command()
def check(
    name: str = typer.Argument(help="Name of the new check."),
) -> None:
    """Create a new check scaffold."""
    check_dir = Path(".ralph") / "checks" / name
    check_md = check_dir / "CHECK.md"

    if check_md.exists():
        rprint(f"[red]Check '{name}' already exists at {check_md}[/red]")
        raise typer.Exit(1)

    check_dir.mkdir(parents=True, exist_ok=True)
    check_md.write_text(CHECK_MD_TEMPLATE)
    rprint(f"[green]Created {check_md}[/green]")


@app.command()
def status() -> None:
    """Show current configuration and validate setup."""
    config_path = Path(CONFIG_FILENAME)

    if not config_path.exists():
        rprint(f"[red]✗ {CONFIG_FILENAME} not found. Run 'ralph init' first.[/red]")
        raise typer.Exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

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
    if checks:
        rprint(f"\n[bold]Checks:[/bold]  {len(checks)} found")
        for check in checks:
            cmd_display = str(check.script.name) if check.script else check.command or "?"
            icon = "[green]✓[/green]" if check.enabled else "[dim]○[/dim]"
            rprint(f"  {icon} {check.name:<18} {cmd_display}")
    else:
        rprint(f"\n[bold]Checks:[/bold]  [dim]none[/dim]")

    if issues:
        rprint(f"\n[red]Not ready.[/red] Fix the issues above before running.")
        raise typer.Exit(1)
    else:
        rprint(f"\n[green]Ready to run.[/green]")


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


def _print_check_summary(results: list) -> None:
    """Print a summary line for check results."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    timed = sum(1 for r in results if r.timed_out)

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
    stop_on_error: bool = typer.Option(False, "--stop-on-error", "-s", help="Stop if the agent exits with non-zero."),
    delay: float = typer.Option(0, "--delay", "-d", help="Seconds to wait between iterations."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", "-l", help="Save iteration output to log files in this directory."),
    timeout: Optional[float] = typer.Option(None, "--timeout", "-t", help="Max seconds per iteration. Kill agent if exceeded."),
) -> None:
    """Run the autonomous coding loop."""
    config_path = Path(CONFIG_FILENAME)

    if not config_path.exists():
        rprint(f"[red]{CONFIG_FILENAME} not found. Run 'ralph init' first.[/red]")
        raise typer.Exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    agent = config["agent"]
    command = agent["command"]
    args = agent.get("args", [])
    prompt_file = agent["prompt"]

    prompt_path = Path(prompt_file)
    if not prompt_path.exists():
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
    checks = discover_checks()
    if checks:
        enabled = [c for c in checks if c.enabled]
        rprint(f"[dim]Checks: {len(enabled)} enabled[/dim]")

    try:
        iteration = 0
        while True:
            iteration += 1
            if n is not None and iteration > n:
                break

            rprint(f"\n[bold blue]── Iteration {iteration} ──[/bold blue]")
            prompt = prompt_path.read_text()
            if check_failures_text:
                prompt = prompt + "\n\n" + check_failures_text

            start = time.monotonic()
            iteration_timed_out = False

            try:
                if log_path_dir:
                    result = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=timeout)
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    log_file = log_path_dir / f"{iteration:03d}_{timestamp}.log"
                    output = ""
                    if result.stdout:
                        output += result.stdout
                    if result.stderr:
                        output += result.stderr
                    log_file.write_text(output)
                    # Replay to terminal
                    if result.stdout:
                        sys.stdout.write(result.stdout)
                    if result.stderr:
                        sys.stderr.write(result.stderr)
                else:
                    result = subprocess.run(cmd, input=prompt, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as e:
                iteration_timed_out = True
                elapsed = time.monotonic() - start
                duration = _format_duration(elapsed)
                timed_out += 1
                failed += 1
                status_msg = f"[yellow]⏱ Iteration {iteration} timed out after {duration}"
                if log_path_dir:
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    log_file = log_path_dir / f"{iteration:03d}_{timestamp}.log"
                    output = ""
                    if e.stdout:
                        output += e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
                    if e.stderr:
                        output += e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
                    log_file.write_text(output)
                    status_msg += f" → {log_file}"
                status_msg += "[/yellow]"
                rprint(status_msg)
                if stop_on_error:
                    rprint("[red]Stopping due to --stop-on-error.[/red]")
                    break

            if not iteration_timed_out:
                elapsed = time.monotonic() - start
                duration = _format_duration(elapsed)

                if result.returncode == 0:
                    completed += 1
                    status_msg = f"[green]✓ Iteration {iteration} completed ({duration})"
                    if log_path_dir:
                        status_msg += f" → {log_file}"
                    status_msg += "[/green]"
                    rprint(status_msg)
                else:
                    failed += 1
                    status_msg = f"[red]✗ Iteration {iteration} failed with exit code {result.returncode} ({duration})"
                    if log_path_dir:
                        status_msg += f" → {log_file}"
                    status_msg += "[/red]"
                    rprint(status_msg)
                    if stop_on_error:
                        rprint("[red]Stopping due to --stop-on-error.[/red]")
                        break

            if checks:
                enabled_checks = [c for c in checks if c.enabled]
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
