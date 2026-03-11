"""Rich console renderer for run-loop events.

The ``ConsoleEmitter`` translates structured :class:`Event` objects into
Rich-formatted terminal output.  It is wired into the ``run`` command
in ``cli.py`` and handles the subset of event types that are meaningful
for interactive CLI sessions.
"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from ralphify._events import Event, EventType
from ralphify.engine import format_duration


class ConsoleEmitter:
    """Renders engine events to the Rich console, reproducing original CLI output."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._rprint = console.print

    def emit(self, event: Event) -> None:
        handler = self._handlers.get(event.type)
        if handler:
            handler(self, event.data)

    def _on_run_started(self, d: dict) -> None:
        if d.get("timeout"):
            self._rprint(f"[dim]Timeout: {format_duration(d['timeout'])} per iteration[/dim]")
        if d.get("checks"):
            self._rprint(f"[dim]Checks: {d['checks']} enabled[/dim]")
        if d.get("contexts"):
            self._rprint(f"[dim]Contexts: {d['contexts']} enabled[/dim]")
        if d.get("instructions"):
            self._rprint(f"[dim]Instructions: {d['instructions']} enabled[/dim]")

    def _on_iteration_started(self, d: dict) -> None:
        self._rprint(f"\n[bold blue]── Iteration {d['iteration']} ──[/bold blue]")

    def _on_iteration_ended(self, d: dict) -> None:
        returncode = d.get("returncode")
        if returncode is None:
            color, icon = "yellow", "\u23f1"
        elif returncode == 0:
            color, icon = "green", "\u2713"
        else:
            color, icon = "red", "\u2717"

        status_msg = f"[{color}]{icon} Iteration {d['iteration']} {d['detail']}"
        if d.get("log_file"):
            status_msg += f" \u2192 {d['log_file']}"
        status_msg += f"[/{color}]"
        self._rprint(status_msg)

    def _on_checks_completed(self, d: dict) -> None:
        parts = []
        if d["passed"]:
            parts.append(f"{d['passed']} passed")
        if d["failed"]:
            parts.append(f"{d['failed']} failed")
        self._rprint(f"  [bold]Checks:[/bold] {', '.join(parts)}")
        for r in d["results"]:
            if r["passed"]:
                self._rprint(f"    [green]\u2713[/green] {r['name']}")
            elif r["timed_out"]:
                self._rprint(f"    [yellow]\u23f1[/yellow] {r['name']} (timed out)")
            else:
                self._rprint(f"    [red]\u2717[/red] {r['name']} (exit {r['exit_code']})")

    def _on_log_message(self, d: dict) -> None:
        msg = d.get("message", "")
        level = d.get("level", "info")
        if level == "error":
            self._rprint(f"[red]{msg}[/red]")
        else:
            self._rprint(f"[dim]{msg}[/dim]")

    def _on_run_stopped(self, d: dict) -> None:
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

    _handlers: dict[EventType, "Callable[[ConsoleEmitter, dict], None]"] = {
        EventType.RUN_STARTED: _on_run_started,
        EventType.ITERATION_STARTED: _on_iteration_started,
        EventType.ITERATION_COMPLETED: _on_iteration_ended,
        EventType.ITERATION_FAILED: _on_iteration_ended,
        EventType.ITERATION_TIMED_OUT: _on_iteration_ended,
        EventType.CHECKS_COMPLETED: _on_checks_completed,
        EventType.LOG_MESSAGE: _on_log_message,
        EventType.RUN_STOPPED: _on_run_stopped,
    }
