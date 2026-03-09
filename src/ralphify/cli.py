import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from ralphify.detector import detect_project

app = typer.Typer()

BANNER = """\
[bold blue] ██████   █████  ██      ██████  ██   ██ ██ ███████ ██    ██
 ██   ██ ██   ██ ██      ██   ██ ██   ██ ██ ██       ██  ██
 ██████  ███████ ██      ██████  ███████ ██ █████     ████
 ██   ██ ██   ██ ██      ██      ██   ██ ██ ██         ██
 ██   ██ ██   ██ ███████ ██      ██   ██ ██ ██         ██[/bold blue]
"""


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Harness toolkit for autonomous AI coding loops."""
    rprint(BANNER)
    if ctx.invoked_subcommand is None:
        raise typer.Exit()

CONFIG_FILENAME = "ralph.toml"

RALPH_TOML_TEMPLATE = """\
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
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


@app.command()
def run(
    n: Optional[int] = typer.Option(None, "-n", help="Max number of iterations. Infinite if not set."),
    stop_on_error: bool = typer.Option(False, "--stop-on-error", "-s", help="Stop if the agent exits with non-zero."),
    delay: float = typer.Option(0, "--delay", "-d", help="Seconds to wait between iterations."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", "-l", help="Save iteration output to log files in this directory."),
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

    cmd = [command] + args
    completed = 0
    failed = 0

    try:
        iteration = 0
        while True:
            iteration += 1
            if n is not None and iteration > n:
                break

            rprint(f"\n[bold blue]── Iteration {iteration} ──[/bold blue]")
            prompt = prompt_path.read_text()

            start = time.monotonic()

            if log_path_dir:
                result = subprocess.run(cmd, input=prompt, text=True, capture_output=True)
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
                result = subprocess.run(cmd, input=prompt, text=True)

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

            if delay > 0 and (n is None or iteration < n):
                rprint(f"[dim]Waiting {delay}s...[/dim]")
                time.sleep(delay)

    except KeyboardInterrupt:
        pass

    total = completed + failed
    summary = f"\n[green]Done: {total} iteration(s) — {completed} succeeded"
    if failed:
        summary += f", {failed} failed"
    summary += "[/green]"
    rprint(summary)
