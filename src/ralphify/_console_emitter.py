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
from ralphify._output import format_duration

# Status icons shared by iteration and check result rendering.
_ICON_SUCCESS = "\u2713"  # ✓
_ICON_FAILURE = "\u2717"  # ✗
_ICON_TIMEOUT = "\u23f1"  # ⏱
_ICON_ARROW = "\u2192"    # →
_ICON_DASH = "\u2014"     # —


class ConsoleEmitter:
    """Renders engine events to the Rich console, reproducing original CLI output."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._rprint = console.print
        self._handlers: dict[EventType, Callable[[dict], None]] = {
            EventType.RUN_STARTED: self._on_run_started,
            EventType.ITERATION_STARTED: self._on_iteration_started,
            EventType.ITERATION_COMPLETED: self._on_iteration_ended,
            EventType.ITERATION_FAILED: self._on_iteration_ended,
            EventType.ITERATION_TIMED_OUT: self._on_iteration_ended,
            EventType.CHECKS_COMPLETED: self._on_checks_completed,
            EventType.LOG_MESSAGE: self._on_log_message,
            EventType.RUN_STOPPED: self._on_run_stopped,
        }

    def emit(self, event: Event) -> None:
        """Dispatch an engine event to the appropriate Rich renderer.

        Implements the :class:`~ralphify._events.EventEmitter` protocol.
        Only event types registered in ``_handlers`` produce terminal output;
        all others are silently ignored.
        """
        handler = self._handlers.get(event.type)
        if handler:
            handler(event.data)

    def _on_run_started(self, data: dict) -> None:
        if data.get("timeout"):
            self._rprint(f"[dim]Timeout: {format_duration(data['timeout'])} per iteration[/dim]")
        if data.get("checks"):
            self._rprint(f"[dim]Checks: {data['checks']} enabled[/dim]")
        if data.get("contexts"):
            self._rprint(f"[dim]Contexts: {data['contexts']} enabled[/dim]")
        if data.get("instructions"):
            self._rprint(f"[dim]Instructions: {data['instructions']} enabled[/dim]")

    def _on_iteration_started(self, data: dict) -> None:
        self._rprint(f"\n[bold blue]── Iteration {data['iteration']} ──[/bold blue]")

    def _on_iteration_ended(self, data: dict) -> None:
        returncode = data.get("returncode")
        if returncode is None:
            color, icon = "yellow", _ICON_TIMEOUT
        elif returncode == 0:
            color, icon = "green", _ICON_SUCCESS
        else:
            color, icon = "red", _ICON_FAILURE

        status_msg = f"[{color}]{icon} Iteration {data['iteration']} {data['detail']}"
        if data.get("log_file"):
            status_msg += f" {_ICON_ARROW} {data['log_file']}"
        status_msg += f"[/{color}]"
        self._rprint(status_msg)

    def _on_checks_completed(self, data: dict) -> None:
        parts = []
        if data["passed"]:
            parts.append(f"{data['passed']} passed")
        if data["failed"]:
            parts.append(f"{data['failed']} failed")
        self._rprint(f"  [bold]Checks:[/bold] {', '.join(parts)}")
        for r in data["results"]:
            if r["passed"]:
                self._rprint(f"    [green]{_ICON_SUCCESS}[/green] {r['name']}")
            elif r["timed_out"]:
                self._rprint(f"    [yellow]{_ICON_TIMEOUT}[/yellow] {r['name']} (timed out)")
            else:
                self._rprint(f"    [red]{_ICON_FAILURE}[/red] {r['name']} (exit {r['exit_code']})")

    def _on_log_message(self, data: dict) -> None:
        msg = data.get("message", "")
        level = data.get("level", "info")
        if level == "error":
            self._rprint(f"[red]{msg}[/red]")
            tb = data.get("traceback")
            if tb:
                self._rprint(f"[dim]{tb}[/dim]")
        else:
            self._rprint(f"[dim]{msg}[/dim]")

    def _on_run_stopped(self, data: dict) -> None:
        if data.get("reason") == "completed":
            total = data.get("total", 0)
            completed = data.get("completed", 0)
            failed = data.get("failed", 0)
            timed_out_count = data.get("timed_out", 0)
            summary = f"\n[green]Done: {total} iteration(s) {_ICON_DASH} {completed} succeeded"
            if failed:
                summary += f", {failed} failed"
            if timed_out_count:
                summary += f" ({timed_out_count} timed out)"
            summary += "[/green]"
            self._rprint(summary)

