"""Rich console renderer for run-loop events.

The ``ConsoleEmitter`` translates structured :class:`Event` objects into
Rich-formatted terminal output.
"""

from __future__ import annotations

import shlex
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.markup import escape as escape_markup
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ralphify._events import (
    LOG_ERROR,
    STOP_COMPLETED,
    AgentActivityData,
    AgentOutputLineData,
    CommandsCompletedData,
    Event,
    EventType,
    IterationEndedData,
    IterationStartedData,
    LogMessageData,
    RunStartedData,
    RunStoppedData,
)
from ralphify import _brand
from ralphify._output import format_count, format_duration
from ralphify.adapters import select_adapter

_ICON_SUCCESS = "✓"
_ICON_FAILURE = "✗"
_ICON_TIMEOUT = "⏱"
_ICON_ARROW = "→"
_ICON_DASH = "—"
_ICON_PLAY = "▶"

# Horizontal rule used to visually bracket the run summary at the bottom.
_RULE_HEAVY = "──────────────────────"

_LIVE_REFRESH_RATE = 8  # Hz — how often the spinner redraws

# Scroll-line buffer limits for the Live renderable.  Lines beyond
# _MAX_SCROLL_LINES are dropped from memory; only the most recent
# _MAX_VISIBLE_SCROLL are rendered inside the compact Live region.
# The full buffer is exposed in the fullscreen peek view (shift+P) so
# users can scroll back through earlier activity within an iteration.
_MAX_SCROLL_LINES = 5000
_MAX_VISIBLE_SCROLL = 10

# Home directory used by ``_shorten_path`` to collapse $HOME → ~ in
# tool argument display.  Captured once at import time so a missing
# $HOME doesn't slow down every render.
try:
    _HOME = str(Path.home())
except (RuntimeError, OSError):
    _HOME = ""

# The key that toggles live peek of agent output.  Used here for status
# messages and imported by cli.py for the keypress handler.
PEEK_TOGGLE_KEY = "p"

# Shift+P enters full-screen peek mode — a scrollable view of the entire
# activity buffer that takes over the terminal using Rich's alt-screen.
FULLSCREEN_PEEK_KEY = "P"

# In fullscreen, [ / ] move between iterations (older / newer).  Completed
# iterations stay in a bounded ring buffer so the user can scroll back
# through earlier iterations' activity without leaving fullscreen.
PREV_ITERATION_KEY = "["
NEXT_ITERATION_KEY = "]"

# How many completed iterations to keep around for fullscreen browsing.
# Each panel can buffer up to ``_MAX_SCROLL_LINES`` Text objects so the
# upper bound on memory is roughly N × 5000 lines of formatted markup.
_MAX_HISTORY_ITERATIONS = 20

# Peek status messages shown when peek is toggled or at run startup.
_PEEK_ON_MSG_STRUCTURED = (
    f"[dim]live activity on — press {PEEK_TOGGLE_KEY} to hide, "
    f"shift+{PEEK_TOGGLE_KEY} for full view[/]"
)
_PEEK_ON_MSG_RAW = (
    f"[dim]live output on — press {PEEK_TOGGLE_KEY} to hide, "
    f"shift+{PEEK_TOGGLE_KEY} for full view[/]"
)
_PEEK_OFF_MSG = (
    f"[dim]peek off — press {PEEK_TOGGLE_KEY} to toggle, "
    f"shift+{PEEK_TOGGLE_KEY} for full view[/]"
)

# ── Adapter-driven structured-output detection ────────────────────────


def _agent_renders_structured_peek(agent: str) -> bool:
    """Return True if *agent*'s adapter feeds the structured peek panel.

    Drives the ``ConsoleEmitter`` choice between :class:`_IterationPanel`
    (structured) and :class:`_IterationSpinner` (raw).  Delegates to
    :func:`select_adapter` so adding a new CLI with peek-panel support
    requires no edits here.
    """
    try:
        cmd = shlex.split(agent)
    except ValueError:
        return False
    return select_adapter(cmd).renders_structured_peek


# ── Tool argument abbreviation ────────────────────────────────────────

_TRUNCATE_DEFAULT = 80
_TRUNCATE_PATH_DEFAULT = 48
# Tool error snippets get more room than generic text so the failure
# reason remains readable in the activity feed.
_TRUNCATE_TOOL_ERROR = 100


def _truncate(text: str, maxlen: int = _TRUNCATE_DEFAULT) -> str:
    if len(text) <= maxlen:
        return text
    return text[: maxlen - 1] + "…"


def _shorten_path(path: str, max_len: int = _TRUNCATE_PATH_DEFAULT) -> str:
    """Make a file path readable in the activity feed.

    Collapses $HOME → ``~`` and, when still too long, drops middle path
    segments so the parent + filename remain visible (the parts a reader
    actually scans for).  Pure paths shorter than ``max_len`` are
    returned unchanged.
    """
    if _HOME and path.startswith(_HOME + "/"):
        path = "~" + path[len(_HOME) :]
    elif _HOME and path == _HOME:
        return "~"
    if len(path) <= max_len:
        return path
    # Path is still too long: keep the leading anchor and the trailing
    # parent/file segments, drop the middle.
    parts = path.split("/")
    if len(parts) <= 3:
        return "…" + path[-(max_len - 1) :]
    head = parts[0]
    tail = "/".join(parts[-2:])
    candidate = f"{head}/…/{tail}"
    if len(candidate) <= max_len:
        return candidate
    return "…/" + tail[-(max_len - 2) :]


def _format_params(tool_input: dict[str, Any], keys: list[str]) -> str:
    """Format specified tool parameters as ``key: value`` pairs."""
    parts = []
    for key in keys:
        val = tool_input.get(key)
        if val is not None:
            parts.append(f"{key}: {val}")
    return " · ".join(parts) if parts else ""


def _extract_file_path(i: dict[str, Any]) -> str:
    return _shorten_path(i.get("file_path", ""))


def _extract_key(key: str) -> Callable[[dict[str, Any]], str]:
    """Factory for extractors that pull a single key from tool input."""
    return lambda i: i.get(key, "")


def _extract_params(*keys: str) -> Callable[[dict[str, Any]], str]:
    """Factory for extractors that format multiple keys as ``key: value`` pairs."""
    key_list = list(keys)
    return lambda i: _format_params(i, key_list)


# ── Helpers ───────────────────────────────────────────────────────────


def _plural(count: int, word: str) -> str:
    """Return *count* followed by *word*, pluralised when count is not 1."""
    return f"{count} {word}{'s' if count != 1 else ''}"


def _format_summary(
    total: int, completed: int, failed: int, timed_out_count: int
) -> str:
    """Build a plain-text run summary string from iteration counters.

    ``timed_out_count`` is a subset of ``failed`` — non-timeout failures
    and timeouts are shown as separate categories for clarity.
    """
    non_timeout_failures = failed - timed_out_count
    parts = [f"{completed} succeeded"]
    if non_timeout_failures:
        parts.append(f"{non_timeout_failures} failed")
    if timed_out_count:
        parts.append(f"{timed_out_count} timed out")
    detail = ", ".join(parts)
    return f"{_plural(total, 'iteration')} {_ICON_DASH} {detail}"


def _format_run_info(
    timeout: float | None, command_count: int, max_iterations: int | None
) -> str:
    """Build a plain-text run info string from configuration values.

    Returns an empty string when no information is available.  Used by
    :meth:`ConsoleEmitter._on_run_started` to show the config summary
    beneath the "Running:" header.
    """
    parts: list[str] = []
    if timeout is not None and timeout > 0:
        parts.append(f"timeout {format_duration(timeout)}")
    if command_count > 0:
        parts.append(_plural(command_count, "command"))
    if max_iterations is not None:
        parts.append(f"max {_plural(max_iterations, 'iteration')}")
    return " · ".join(parts)


# ── Tool registry ───────────────────────────────────────────────────
#
# Single source of truth for tool display config in the activity feed.
# Each entry defines the color (applied to the tool name), the category
# bucket (shown in the footer counter), and an optional argument
# extractor (picks the most relevant arg for the scroll line).
#
# Color intent: blue=read/search, orange=mutate, green=execute,
# lavender=web, violet=delegate, purple=meta.


@dataclass(slots=True)
class _ToolConfig:
    """Visual and extraction config for a known tool."""

    color: str
    category: str
    extract_arg: Callable[[dict[str, Any]], str] | None = None


_TOOL_REGISTRY: dict[str, _ToolConfig] = {
    "Read": _ToolConfig(_brand.BLUE, "read", _extract_file_path),
    "Glob": _ToolConfig(_brand.BLUE, "glob", _extract_key("pattern")),
    "Grep": _ToolConfig(_brand.BLUE, "grep", _extract_key("pattern")),
    "Edit": _ToolConfig(_brand.ORANGE, "edit", _extract_file_path),
    "MultiEdit": _ToolConfig(_brand.ORANGE, "edit", _extract_file_path),
    "Write": _ToolConfig(_brand.ORANGE, "write", _extract_file_path),
    "Bash": _ToolConfig(_brand.GREEN, "bash", _extract_key("command")),
    "BashOutput": _ToolConfig(_brand.GREEN, "bash"),
    "WebFetch": _ToolConfig(_brand.LAVENDER, "web", _extract_key("url")),
    "WebSearch": _ToolConfig(_brand.LAVENDER, "web", _extract_key("query")),
    "Task": _ToolConfig(
        _brand.VIOLET, "task", _extract_params("description", "prompt")
    ),
    "Agent": _ToolConfig(
        _brand.VIOLET, "agent", _extract_params("description", "prompt")
    ),
    "ToolSearch": _ToolConfig(
        _brand.BLUE, "other", _extract_params("query", "max_results")
    ),
    "TodoWrite": _ToolConfig(
        _brand.PURPLE, "todo", lambda i: f"{len(i.get('todos', []))} todos"
    ),
}

_DEFAULT_TOOL_STYLE: tuple[str, str] = ("white", "other")

# Width reserved for the colored tool name column in the activity feed.
# Most common tools (Read/Edit/Bash/Grep) are 4 chars; longer ones like
# TodoWrite/WebFetch overflow gracefully into the argument column.
_TOOL_NAME_COL = 9


def _tool_display(name: str, tool_input: dict[str, Any]) -> tuple[str, str, str]:
    """Return ``(color, category, arg)`` for a tool call in one registry lookup.

    Unknown tools fall back to :data:`_DEFAULT_TOOL_STYLE` and a
    sorted-keys arg.  Known tools without an ``extract_arg`` (e.g.
    ``BashOutput``) also fall back to sorted keys so every tool call
    gets *something* useful in its scroll line.
    """
    cfg = _TOOL_REGISTRY.get(name)
    if cfg is None:
        color, category = _DEFAULT_TOOL_STYLE
        extractor = None
    else:
        color, category = cfg.color, cfg.category
        extractor = cfg.extract_arg
    if extractor is not None:
        arg = extractor(tool_input)
    else:
        arg = ", ".join(sorted(tool_input.keys()))
    return color, category, arg


def _iter_content_blocks(raw: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each dict block from ``raw["message"]["content"]``."""
    content = raw.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict):
            yield block


class _LivePanelBase:
    """Shared scroll-buffer state for iteration Live renderables.

    Both :class:`_IterationPanel` (Claude structured output) and
    :class:`_IterationSpinner` (raw agent output) need the same scroll
    buffer, peek visibility toggle, and body-rendering logic.  This base
    class provides all of that so neither subclass has to duplicate it.
    """

    def __init__(self) -> None:
        self._spinner = Spinner("dots", style=f"bold {_brand.PURPLE}")
        self._start = time.monotonic()
        self._scroll_lines: list[Text] = []
        self._peek_message: Text | None = None
        # Visibility flag controlled by toggle_peek.  Buffering keeps
        # happening behind the scenes regardless — toggling peek back on
        # reveals the latest state with full catch-up.
        self._peek_visible: bool = True
        # Set by ``freeze`` once the iteration ends so the elapsed timer
        # stops ticking and the panel can advertise its outcome in
        # fullscreen browsing mode.  ``None`` while the iteration is live.
        self._end: float | None = None
        self._outcome: str | None = None  # "completed" | "failed" | "timed out"

    def freeze(self, outcome: str) -> None:
        """Mark the iteration as ended and freeze its elapsed time.

        Called when the iteration finishes — the panel keeps existing in
        the history ring buffer so the user can browse it in fullscreen,
        but elapsed time should stop advancing and the outcome should be
        visible in the fullscreen header.
        """
        if self._end is None:
            self._end = time.monotonic()
        self._outcome = outcome

    # ── Scroll buffer management ─────────────────────────────────────

    def add_scroll_line(self, markup: str) -> None:
        """Append a Rich-markup scroll line to the transient buffer."""
        self._scroll_lines.append(Text.from_markup(markup))
        if len(self._scroll_lines) > _MAX_SCROLL_LINES:
            self._scroll_lines.pop(0)

    def clear_scroll(self) -> None:
        """Drop all buffered scroll lines."""
        self._scroll_lines.clear()

    def set_peek_message(self, markup: str) -> None:
        """Set a transient status message shown inside the Live region."""
        self._peek_message = Text.from_markup(markup)

    def set_peek_visible(self, visible: bool) -> None:
        """Show or hide the scroll feed without touching the buffer."""
        self._peek_visible = visible

    # ── Shared rendering ─────────────────────────────────────────────

    def _build_title(self) -> Text:
        """Title bar text: elapsed time.  Subclasses may override."""
        end = self._end if self._end is not None else time.monotonic()
        elapsed = end - self._start
        title = Text()
        title.append(" ⏱ ", style=_brand.PURPLE)
        title.append(format_duration(elapsed), style=f"bold {_brand.PURPLE}")
        title.append(" ", style="dim")
        return title

    def _build_subtitle(self) -> Text | None:
        """Subtitle text.  Returns ``None`` by default."""
        return None

    def _build_footer(self) -> Table:
        """Subclasses must override to provide the footer summary row."""
        raise NotImplementedError

    def _footer_grid(self, summary: Text) -> Table:
        """Three-column footer row: spinner | summary | peek hint."""
        hint = Text("Shift+P full screen", style="dim", no_wrap=True)
        grid = Table.grid(expand=True)
        grid.add_column(width=2, no_wrap=True)
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(no_wrap=True, justify="right")
        grid.add_row(self._spinner, summary, hint)
        return grid

    def _build_body(self) -> Group:
        """Body group: scroll lines (or peek message) + spacer + footer."""
        rows: list[Any] = []
        if self._peek_visible:
            visible = self._scroll_lines[-_MAX_VISIBLE_SCROLL:]
            for line in visible:
                line.no_wrap = True
                line.overflow = "ellipsis"
                rows.append(line)
        if not rows and self._peek_message is not None:
            rows.append(self._peek_message)
        rows.append(Text(""))  # spacer above footer
        rows.append(self._build_footer())
        return Group(*rows)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        panel = Panel(
            self._build_body(),
            box=box.ROUNDED,
            title=self._build_title(),
            title_align="left",
            subtitle=self._build_subtitle(),
            subtitle_align="right",
            border_style=_brand.PURPLE,
            padding=(0, 2),
        )
        yield panel


class _IterationPanel(_LivePanelBase):
    """Rich renderable for the live peek panel.

    Shows a bordered Rich :class:`Panel` whose title carries elapsed time
    and token counts, body holds the most recent activity rows, and
    footer holds a spinner + tool counters + model name.

    The activity feed is the centerpiece — each row shows a colored tool
    name (color-coded by intent: blue for read/search, orange for
    mutating, green for execution, lavender for web) followed by its
    primary argument (file path, pattern, command) in dim text.
    """

    def __init__(self) -> None:
        super().__init__()
        self._model: str = ""
        self._tool_count: int = 0
        self._tool_categories: dict[str, int] = {}
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._cache_read_tokens: int = 0

    # ── Stream-json processing ───────────────────────────────────────

    def apply(self, raw: dict[str, Any]) -> None:
        """Update panel state from a parsed stream-json dict.

        Each handler appends its own scroll lines to the buffer so that
        multi-line blocks (thinking, long text) can produce several rows.
        """
        event_type = raw.get("type")

        if event_type == "system" and raw.get("subtype") == "init":
            self._model = raw.get("model", "")
        elif event_type == "assistant":
            self._apply_assistant(raw)
        elif event_type == "user":
            self._apply_user(raw)
        elif event_type == "rate_limit_event":
            info = raw.get("rate_limit_info", {})
            status = info.get("status", "")
            resets = info.get("resetsAt", "")
            self.add_scroll_line(
                f"[bold {_brand.PEACH}]⚠ rate limit:[/]"
                f" [dim]{escape_markup(str(status))}"
                f", resets {escape_markup(str(resets))}[/]"
            )

    def _apply_assistant(self, raw: dict[str, Any]) -> None:
        msg = raw.get("message", {})

        # Update token counts from usage
        usage = msg.get("usage")
        if isinstance(usage, dict):
            self._input_tokens = usage.get("input_tokens", self._input_tokens)
            self._output_tokens = usage.get("output_tokens", self._output_tokens)
            self._cache_read_tokens = usage.get(
                "cache_read_input_tokens", self._cache_read_tokens
            )

        for block in _iter_content_blocks(raw):
            block_type = block.get("type")

            if block_type == "thinking":
                text = block.get("thinking", "")
                if text:
                    for tline in text.split("\n"):
                        self.add_scroll_line(f"[dim italic]{escape_markup(tline)}[/]")

            elif block_type == "text":
                text = block.get("text", "")
                if text:
                    for tline in text.split("\n"):
                        if tline.strip():
                            self.add_scroll_line(
                                f'[italic {_brand.LAVENDER}]"{escape_markup(tline)}"[/]'
                            )

            elif block_type == "tool_use":
                name = block.get("name", "?")
                tool_input = block.get("input", {})
                if not isinstance(tool_input, dict):
                    tool_input = {}

                self._tool_count += 1
                color, cat, arg = _tool_display(name, tool_input)
                self._tool_categories[cat] = self._tool_categories.get(cat, 0) + 1

                # Pad short names to a fixed column so arguments line up;
                # longer names get a guaranteed two-space gap so the arg
                # never collides with the tool label.
                if len(name) < _TOOL_NAME_COL:
                    name_col = f"{name:<{_TOOL_NAME_COL}}"
                else:
                    name_col = f"{name}  "
                if arg:
                    self.add_scroll_line(
                        f"[bold {color}]{escape_markup(name_col)}[/]"
                        f"[dim]{escape_markup(arg)}[/]"
                    )
                else:
                    self.add_scroll_line(f"[bold {color}]{escape_markup(name)}[/]")

    def _apply_user(self, raw: dict[str, Any]) -> None:
        for block in _iter_content_blocks(raw):
            if block.get("type") == "tool_result" and block.get("is_error"):
                snippet = _truncate(str(block.get("content", "")), _TRUNCATE_TOOL_ERROR)
                self.add_scroll_line(
                    f"[bold {_brand.DEEP_ORANGE}]{_ICON_FAILURE} tool error:[/]"
                    f" [dim]{escape_markup(snippet)}[/]"
                )
                return

    def _format_tokens(self) -> str:
        """Format token counts as compact ctx/out string."""
        parts: list[str] = []
        total_in = self._input_tokens
        if total_in > 0:
            parts.append(f"ctx {format_count(total_in)}")
        if self._output_tokens > 0:
            parts.append(f"out {format_count(self._output_tokens)}")
        return " · ".join(parts)

    def _format_categories(self) -> str:
        if not self._tool_categories:
            return ""
        parts = [f"{v} {k}" for k, v in self._tool_categories.items()]
        return " · ".join(parts)

    # ── Rich renderable ───────────────────────────────────────────────

    def _build_title(self) -> Text:
        """Title bar text: elapsed time + token usage."""
        title = super()._build_title()
        tokens = self._format_tokens()
        if tokens:
            title.append("  ", style="dim")
            title.append(tokens, style=f"bold {_brand.LAVENDER}")
            title.append(" ", style="dim")
        return title

    def _build_subtitle(self) -> Text | None:
        """Subtitle: model name, when known."""
        if not self._model:
            return None
        sub = Text()
        sub.append(" ", style="dim")
        sub.append(self._model, style=f"dim italic {_brand.LAVENDER}")
        sub.append(" ", style="dim")
        return sub

    def _build_footer(self) -> Table:
        """Bottom row of the panel: spinner + tool counts + peek hint."""
        summary = Text(no_wrap=True, overflow="ellipsis")
        if self._tool_count > 0:
            summary.append(
                _plural(self._tool_count, "tool"),
                style=f"bold {_brand.PURPLE}",
            )
            cats = self._format_categories()
            if cats:
                summary.append("  ·  ", style="dim")
                summary.append(cats, style="dim")
        else:
            summary.append("waiting for first tool call…", style="dim italic")
        return self._footer_grid(summary)


class _IterationSpinner(_LivePanelBase):
    """Rich renderable for non-Claude agents that emit raw stdout.

    Same panel chrome as :class:`_IterationPanel` so the visual feels
    consistent across agents — only the body content differs (raw text
    lines vs. structured tool rows).
    """

    def _build_footer(self) -> Table:
        line_count = len(self._scroll_lines)
        summary = Text(no_wrap=True, overflow="ellipsis")
        if line_count > 0:
            summary.append(
                _plural(line_count, "line"),
                style=f"bold {_brand.PURPLE}",
            )
            summary.append(" of agent output", style="dim")
        else:
            summary.append("waiting for agent output…", style="dim italic")
        return self._footer_grid(summary)


# ── Full-screen peek ─────────────────────────────────────────────────

# Chrome rows that the fullscreen peek reserves on top of its viewport:
# panel top border (1) + panel bottom border (1).  Header lives in the
# panel title and footer in the subtitle, so they cost no extra rows.
_FULLSCREEN_CHROME_ROWS = 2
_FULLSCREEN_MIN_VISIBLE = 3


@dataclass(slots=True)
class _ScrollbarMetrics:
    """Pure-data result of scrollbar geometry calculation.

    ``show`` is ``False`` when the buffer fits in the viewport and no
    scrollbar should be rendered.  ``thumb_start`` and ``thumb_size``
    are row indices within the viewport, valid only when ``show`` is
    ``True``.
    """

    show: bool
    thumb_start: int
    thumb_size: int


def _scrollbar_metrics(total: int, visible: int, offset: int) -> _ScrollbarMetrics:
    """Compute scrollbar position and size for the fullscreen peek view.

    *total* is the number of buffered lines, *visible* the viewport
    height, and *offset* how many lines are hidden below the viewport
    (0 = following the tail).

    Returns a :class:`_ScrollbarMetrics` with ``show=False`` when the
    buffer fits within the viewport.
    """
    if total <= visible:
        return _ScrollbarMetrics(show=False, thumb_start=0, thumb_size=0)
    thumb_size = max(1, visible * visible // total)
    max_off = max(total - visible, 1)
    frac = 1.0 - (offset / max_off)
    track_space = visible - thumb_size
    thumb_start = int(frac * track_space)
    return _ScrollbarMetrics(show=True, thumb_start=thumb_start, thumb_size=thumb_size)


class _IterationNavigator(Protocol):
    """Lookup interface :class:`_FullscreenPeek` uses to browse iterations.

    Implemented by :class:`ConsoleEmitter` and by :class:`_SinglePanelNavigator`
    (the latter exists for unit tests that only care about a single panel).
    """

    def iteration_ids(self) -> list[int]: ...

    def panel_for(self, iteration_id: int) -> _LivePanelBase | None: ...

    def is_live(self, iteration_id: int) -> bool: ...


class _SinglePanelNavigator:
    """Navigator wrapping one panel — used by isolated _FullscreenPeek tests.

    Production code uses :class:`ConsoleEmitter` directly as the
    navigator; this stub keeps the view testable in isolation without
    spinning up the full emitter.
    """

    def __init__(
        self, panel: _LivePanelBase, iteration_id: int = 1, live: bool = True
    ) -> None:
        self._panel = panel
        self._iteration_id = iteration_id
        self._live = live

    def iteration_ids(self) -> list[int]:
        return [self._iteration_id]

    def panel_for(self, iteration_id: int) -> _LivePanelBase | None:
        return self._panel if iteration_id == self._iteration_id else None

    def is_live(self, iteration_id: int) -> bool:
        return self._live and iteration_id == self._iteration_id


class _FullscreenPeek:
    """Scrollable alt-screen view of the activity buffer.

    Reads ``_scroll_lines`` from the iteration panel that the navigator
    returns for the currently-selected iteration id.  While the user is
    in fullscreen they can move between iterations with
    ``[`` / ``]`` — finished iterations live in the navigator's
    history ring buffer so previous activity is browsable without
    leaving fullscreen.

    The source keeps receiving agent events in the background, so when
    viewing the live iteration the view follows the tail when
    ``_auto_scroll`` is set.

    The offset is anchored to the *bottom* of the buffer: ``_offset=0``
    shows the latest lines, ``_offset=1`` hides the newest line, and so
    on up to ``len(buffer) - visible``.  This keeps "follow mode" cheap —
    auto-scroll just means "keep offset at 0".
    """

    def __init__(self, navigator: _IterationNavigator, iteration_id: int) -> None:
        self._navigator = navigator
        self._iteration_id = iteration_id
        self._offset: int = 0
        self._auto_scroll: bool = True

    @property
    def _source(self) -> _LivePanelBase | None:
        """The panel being viewed, or ``None`` if its iteration was evicted."""
        return self._navigator.panel_for(self._iteration_id)

    @property
    def iteration_id(self) -> int:
        return self._iteration_id

    def _viewport_height(self, console_height: int) -> int:
        return max(_FULLSCREEN_MIN_VISIBLE, console_height - _FULLSCREEN_CHROME_ROWS)

    def _max_offset(self, visible: int) -> int:
        source = self._source
        if source is None:
            return 0
        return max(0, len(source._scroll_lines) - visible)

    # ── Scroll commands ──────────────────────────────────────────────

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll toward older lines (offset grows)."""
        visible = self._viewport_height(self._console_height)
        new_offset = min(self._offset + lines, self._max_offset(visible))
        if new_offset != self._offset:
            self._offset = new_offset
            self._auto_scroll = False

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll toward newer lines (offset shrinks)."""
        new_offset = max(0, self._offset - lines)
        self._offset = new_offset
        if new_offset == 0:
            self._auto_scroll = True

    def scroll_to_top(self) -> None:
        visible = self._viewport_height(self._console_height)
        self._offset = self._max_offset(visible)
        self._auto_scroll = False

    def scroll_to_bottom(self) -> None:
        self._offset = 0
        self._auto_scroll = True

    # ── Iteration navigation ─────────────────────────────────────────

    def _reset_view(self) -> None:
        """Snap to bottom + follow when switching iterations."""
        self._offset = 0
        self._auto_scroll = True

    def prev_iteration(self) -> bool:
        """Move to the iteration before the current one.  Returns ``True``
        if the view changed; ``False`` when there is no older iteration."""
        ids = self._navigator.iteration_ids()
        if not ids:
            return False
        if self._iteration_id not in ids:
            # Current iteration was evicted — snap to oldest available.
            self._iteration_id = ids[0]
            self._reset_view()
            return True
        idx = ids.index(self._iteration_id)
        if idx == 0:
            return False
        self._iteration_id = ids[idx - 1]
        self._reset_view()
        return True

    def next_iteration(self) -> bool:
        """Move to the iteration after the current one.  Returns ``True``
        if the view changed; ``False`` when already on the newest."""
        ids = self._navigator.iteration_ids()
        if not ids:
            return False
        if self._iteration_id not in ids:
            self._iteration_id = ids[-1]
            self._reset_view()
            return True
        idx = ids.index(self._iteration_id)
        if idx >= len(ids) - 1:
            return False
        self._iteration_id = ids[idx + 1]
        self._reset_view()
        return True

    # ── Rendering ────────────────────────────────────────────────────

    _console_height: int = 40  # updated on every render

    def _build_header(self, total: int, visible: int) -> Text:
        header = Text(no_wrap=True, overflow="ellipsis")
        header.append(" Full peek ", style=f"bold {_brand.PURPLE}")
        ids = self._navigator.iteration_ids()
        if ids:
            try:
                pos = ids.index(self._iteration_id) + 1
            except ValueError:
                pos = 0
            header.append(
                f"· iter {self._iteration_id} ({pos} of {len(ids)})", style="dim"
            )
            if self._navigator.is_live(self._iteration_id):
                header.append("  ·  ", style="dim")
                header.append("live", style=f"italic {_brand.GREEN}")
            else:
                source = self._source
                outcome = source._outcome if source is not None else None
                if outcome:
                    header.append("  ·  ", style="dim")
                    header.append(outcome, style=f"italic {_brand.LAVENDER}")
        header.append("  ·  ", style="dim")
        header.append(f"{_plural(total, 'line')}", style="dim")
        if self._auto_scroll:
            header.append("  ·  ", style="dim")
            header.append("following", style=f"italic {_brand.GREEN}")
        else:
            start = max(0, total - self._offset - visible) + 1
            end_line = total - self._offset
            header.append("  ·  ", style="dim")
            header.append(
                f"lines {start}–{end_line}", style=f"italic {_brand.LAVENDER}"
            )
        header.append(" ", style="dim")
        return header

    def _build_footer(self) -> Text:
        hint = Text(no_wrap=True, overflow="ellipsis")
        hint.append(
            " ↑/↓ scroll · space/b page · g/G top/bottom · ",
            style="dim",
        )
        hint.append(PREV_ITERATION_KEY, style=f"bold {_brand.PURPLE}")
        hint.append("/", style="dim")
        hint.append(NEXT_ITERATION_KEY, style=f"bold {_brand.PURPLE}")
        hint.append(" iter · q/", style="dim")
        hint.append(FULLSCREEN_PEEK_KEY, style=f"bold {_brand.PURPLE}")
        hint.append(" exit ", style="dim")
        return hint

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        self._console_height = options.max_height or console.size.height
        visible = self._viewport_height(self._console_height)
        source = self._source
        lines = source._scroll_lines if source is not None else []
        total = len(lines)

        # Clamp offset whenever the buffer shrinks (edge case) or the
        # terminal was resized since the last render.
        max_off = self._max_offset(visible)
        if self._offset > max_off:
            self._offset = max_off
        if self._auto_scroll:
            self._offset = 0

        end = total - self._offset
        start = max(0, end - visible)
        window = lines[start:end]

        sb = _scrollbar_metrics(total, visible, self._offset)

        # Body is exactly `visible` rows tall: a single Table.grid that
        # always pads to the viewport height (with empty Text rows when
        # the buffer is shorter than the viewport) so the panel's height
        # never depends on how full the buffer is.
        content = Table.grid(expand=True)
        content.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        if sb.show:
            content.add_column(width=1, no_wrap=True)

        show_waiting = not window and not sb.show
        for i in range(visible):
            if show_waiting and i == 0:
                if source is None:
                    line: Text = Text(
                        "  (iteration no longer available)", style="dim italic"
                    )
                else:
                    line = Text("  (waiting for activity…)", style="dim italic")
            elif i < len(window):
                line = window[i]
                line.no_wrap = True
                line.overflow = "ellipsis"
            else:
                line = Text("")
            if sb.show:
                in_thumb = sb.thumb_start <= i < sb.thumb_start + sb.thumb_size
                bar = Text(
                    "█" if in_thumb else "│",
                    style=_brand.PURPLE if in_thumb else "dim",
                )
                content.add_row(line, bar)
            else:
                content.add_row(line)

        panel = Panel(
            content,
            box=box.ROUNDED,
            title=self._build_header(total, visible),
            title_align="left",
            subtitle=self._build_footer(),
            subtitle_align="left",
            border_style=_brand.PURPLE,
            padding=(0, 1),
            height=visible + _FULLSCREEN_CHROME_ROWS,
        )
        yield panel


def _interactive_default_peek(console: Console) -> bool:
    """Return True when live peek should be on by default.

    Peek is only useful when both (a) the console is attached to a real
    terminal (so the user can see the extra lines) and (b) stdin is a TTY
    (so the keypress listener is actually active and the user can turn
    peek back off).  Recording consoles used in tests fail check (a).
    """
    if not console.is_terminal:
        return False
    try:
        return sys.stdin.isatty()
    except (ValueError, OSError):
        return False


class ConsoleEmitter:
    """Renders engine events to the Rich console."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._live: Live | None = None
        self._peek_enabled = _interactive_default_peek(console)
        self._structured_agent: bool = False
        self._peek_broken: bool = False
        self._active_renderable: _LivePanelBase | None = None
        # Iteration number of the currently-active panel (the one
        # receiving events).  ``None`` between iterations.
        self._current_iteration: int | None = None
        # Bounded ring buffer of finished iteration panels, keyed by
        # iteration number.  Insertion order is tracked separately so
        # eviction is O(1).  Used by fullscreen peek for browsing.
        self._iteration_history: dict[int, _LivePanelBase] = {}
        self._iteration_order: list[int] = []
        # Fullscreen peek state — a second Live using Rich's alt-screen
        # that shows an iteration's full activity buffer with scroll +
        # iteration-navigation controls.  While fullscreen is active the
        # compact ``_live`` is stopped and console prints from event
        # handlers are buffered into ``_deferred_renders`` so the user
        # isn't dropped out of the alt screen on every iteration end.
        self._fullscreen_view: _FullscreenPeek | None = None
        self._fullscreen_live: Live | None = None
        self._deferred_renders: list[Callable[[], None]] = []
        # Single lock that serialises every ``_console.print`` call and
        # protects ``_peek_enabled`` mutations so that reader-thread /
        # keypress-thread writes cannot interleave with main-thread event
        # handlers while a Rich ``Live`` region is active.
        self._console_lock = threading.Lock()
        self._handlers: dict[EventType, Callable[..., None]] = {
            EventType.RUN_STARTED: self._on_run_started,
            EventType.ITERATION_STARTED: self._on_iteration_started,
            EventType.ITERATION_COMPLETED: partial(
                self._on_iteration_ended,
                color="green",
                icon=_ICON_SUCCESS,
                outcome="completed",
            ),
            EventType.ITERATION_FAILED: partial(
                self._on_iteration_ended,
                color="red",
                icon=_ICON_FAILURE,
                outcome="failed",
            ),
            EventType.ITERATION_TIMED_OUT: partial(
                self._on_iteration_ended,
                color="yellow",
                icon=_ICON_TIMEOUT,
                outcome="timed out",
            ),
            EventType.COMMANDS_COMPLETED: self._on_commands_completed,
            EventType.LOG_MESSAGE: self._on_log_message,
            EventType.RUN_STOPPED: self._on_run_stopped,
            EventType.AGENT_OUTPUT_LINE: self._on_agent_output_line,
            EventType.AGENT_ACTIVITY: self._on_agent_activity,
        }

    # ── _IterationNavigator implementation ───────────────────────────
    #
    # These three methods expose the emitter's iteration state to
    # ``_FullscreenPeek`` so it can browse forward/back across
    # completed iterations while staying inside the alt screen.

    def iteration_ids(self) -> list[int]:
        """Return all known iteration ids in ascending order.

        Combines the history ring buffer with the currently-active
        iteration (if any).  Used by ``_FullscreenPeek`` to drive
        ``[`` / ``]`` navigation.
        """
        ids = list(self._iteration_history.keys())
        if (
            self._current_iteration is not None
            and self._current_iteration not in self._iteration_history
        ):
            ids.append(self._current_iteration)
        ids.sort()
        return ids

    def panel_for(self, iteration_id: int) -> _LivePanelBase | None:
        """Look up the panel for *iteration_id* in history or active state."""
        if (
            self._current_iteration == iteration_id
            and self._active_renderable is not None
        ):
            return self._active_renderable
        return self._iteration_history.get(iteration_id)

    def is_live(self, iteration_id: int) -> bool:
        """Return True when *iteration_id* is the currently-active iteration."""
        return (
            self._current_iteration == iteration_id
            and self._active_renderable is not None
        )

    # ── Deferred-print helpers ───────────────────────────────────────

    def _print_or_defer_unlocked(self, render_fn: Callable[[], None]) -> None:
        """Print now, or queue for replay if fullscreen is active.

        While fullscreen is active the user sees the alt screen, not the
        normal terminal.  Anything event handlers want to ``print`` is
        queued and replayed when the user exits fullscreen so the
        terminal scrollback shows the full picture instead of jumping
        from "Iteration 1 started" straight to "Iteration 5 started".

        Caller must hold ``_console_lock``.
        """
        if self._fullscreen_view is not None:
            self._deferred_renders.append(render_fn)
        else:
            try:
                render_fn()
            except Exception:
                pass

    def _flush_deferred_unlocked(self) -> None:
        """Replay all queued prints onto the normal console.

        Caller must hold ``_console_lock``.
        """
        renders = self._deferred_renders
        self._deferred_renders = []
        for fn in renders:
            try:
                fn()
            except Exception:
                pass

    def _archive_current_iteration_unlocked(self, outcome: str) -> None:
        """Move the active panel into the history ring buffer.

        Freezes the panel (stops elapsed time, records outcome) and
        evicts the oldest history entry when the buffer is full.  Never
        evicts an iteration the user is currently viewing in
        fullscreen — that would yank the page out from under them.

        Caller must hold ``_console_lock``.  No-op when no iteration is
        active.
        """
        panel = self._active_renderable
        if panel is None or self._current_iteration is None:
            return
        iteration_id = self._current_iteration
        panel.freeze(outcome)
        # Record (or refresh order of) the iteration in history.
        if iteration_id in self._iteration_history:
            self._iteration_order.remove(iteration_id)
        self._iteration_history[iteration_id] = panel
        self._iteration_order.append(iteration_id)
        # Eviction: drop oldest until at or below the cap, but skip the
        # iteration the user is currently viewing in fullscreen.
        viewing = (
            self._fullscreen_view._iteration_id
            if self._fullscreen_view is not None
            else None
        )
        while len(self._iteration_order) > _MAX_HISTORY_ITERATIONS:
            candidate = next(
                (iid for iid in self._iteration_order if iid != viewing),
                None,
            )
            if candidate is None:
                # All remaining entries are the viewed iteration (impossible
                # with one viewer) — bail to avoid an infinite loop.
                break
            self._iteration_order.remove(candidate)
            self._iteration_history.pop(candidate, None)
        self._active_renderable = None
        self._current_iteration = None

    def _refresh_live_unlocked(self, renderable: _LivePanelBase) -> None:
        """Push updated state to whichever Live context is active.

        Fullscreen takes priority — when active, the compact Live has been
        stopped, so only the fullscreen Live needs a refresh.  Otherwise
        the compact Live is updated.

        Caller must hold ``_console_lock``.
        """
        if self._fullscreen_live is not None and self._fullscreen_view is not None:
            self._fullscreen_live.update(self._fullscreen_view)
        elif self._live is not None:
            self._live.update(renderable)

    def wants_agent_output_lines(self) -> bool:
        # Returns the peek state so the engine still gets a "no, drop
        # raw line events" signal when peek is off.  This lets the
        # engine package captured output for end-of-iteration echo when
        # ``--log-dir`` is set, preserving that recovery path for users
        # who keep peek off the whole run.  Persistence for structured
        # (Claude) agents goes through ``_on_agent_activity`` which is
        # always called regardless of this gate.
        return self._peek_enabled

    def _peek_status_msg(self, enabled: bool) -> str:
        """Return the peek status message for the given on/off state."""
        if not enabled:
            return _PEEK_OFF_MSG
        return _PEEK_ON_MSG_STRUCTURED if self._structured_agent else _PEEK_ON_MSG_RAW

    def toggle_peek(self) -> bool:
        """Flip live-output rendering on or off.

        Safe to call from a non-main thread (e.g. the keypress listener).
        Returns the new peek state.  Toggling never clears the scroll
        buffer — the panel keeps recording behind the scenes so toggling
        peek back on shows the latest state.
        """
        with self._console_lock:
            self._peek_enabled = not self._peek_enabled
            enabled = self._peek_enabled
            msg = self._peek_status_msg(enabled)

            renderable = self._active_renderable
            if renderable is not None:
                renderable.set_peek_visible(enabled)
                renderable.set_peek_message(msg)
                if self._live is not None:
                    self._live.update(renderable)
            else:
                self._console.print(msg)
        return enabled

    def _panel_for_event(self, iteration: int | None) -> _LivePanelBase | None:
        """Resolve the panel an incoming event should land in.

        Falls back to the active renderable when the event omits an
        ``iteration`` field or when the iteration matches the active
        one.  History panels are also addressable so late-arriving
        events for an already-archived iteration still hit the right
        buffer.
        """
        if iteration is not None:
            panel = self.panel_for(iteration)
            if panel is not None:
                return panel
        return self._active_renderable

    def _on_agent_output_line(self, data: AgentOutputLineData) -> None:
        with self._console_lock:
            # When we have structured rendering, raw lines are redundant noise.
            if self._structured_agent:
                return
            line = escape_markup(data["line"])
            target = self._panel_for_event(data["iteration"])
            if not isinstance(target, _IterationSpinner):
                return
            target.add_scroll_line(f"[white]{line}[/]")
            self._refresh_live_unlocked(target)

    def _on_agent_activity(self, data: AgentActivityData) -> None:
        """Handle structured agent activity events (Claude stream-json).

        Peek is best-effort — a failure here must never kill the run loop.
        Events are always buffered into the panel regardless of peek
        state; visibility is controlled by the panel's _peek_visible flag.
        """
        if not self._structured_agent:
            return

        with self._console_lock:
            if self._peek_broken:
                return

            try:
                target = self._panel_for_event(data["iteration"])
                if not isinstance(target, _IterationPanel):
                    return
                target.apply(data["raw"])
                self._refresh_live_unlocked(target)
            except Exception:
                self._peek_broken = True
                self._console.print(
                    "[dim]peek: live activity unavailable (continuing)[/]"
                )

    def emit(self, event: Event) -> None:
        handler = self._handlers.get(event.type)
        if handler is not None:
            handler(event.data)

    def _on_run_started(self, data: RunStartedData) -> None:
        ralph_name = data["ralph_name"]
        agent = data["agent"]
        self._structured_agent = _agent_renders_structured_peek(agent)
        with self._console_lock:
            self._console.print(
                f"\n[bold {_brand.PURPLE}]{_ICON_PLAY} Running:[/] [bold]{escape_markup(ralph_name)}[/]"
            )
            info = _format_run_info(
                data["timeout"], data["commands"], data["max_iterations"]
            )
            if info:
                self._console.print(f"  [dim]{info}[/]")
            if self._peek_enabled:
                self._console.print(self._peek_status_msg(True))

    def _create_panel_unlocked(self) -> _LivePanelBase:
        """Construct the iteration's panel/spinner without starting Live.

        Splitting panel creation from Live startup means we can buffer
        events into the panel even when fullscreen has suppressed the
        compact Live for this iteration.

        Caller must hold ``_console_lock``.
        """
        if self._structured_agent:
            renderable: _LivePanelBase = _IterationPanel()
        else:
            renderable = _IterationSpinner()
        self._active_renderable = renderable
        # Carry the current peek visibility into the new renderable so
        # an iteration that starts with peek already off doesn't flash
        # the empty scroll feed before the first event lands.
        renderable.set_peek_visible(self._peek_enabled)
        if not self._peek_enabled:
            renderable.set_peek_message(_PEEK_OFF_MSG)
        return renderable

    def _start_compact_live_unlocked(self, renderable: _LivePanelBase) -> None:
        """Start a transient compact Live for *renderable*.

        Caller must hold ``_console_lock``.
        """
        self._live = Live(
            renderable,
            console=self._console,
            transient=True,
            refresh_per_second=_LIVE_REFRESH_RATE,
        )
        self._live.start()

    def _stop_live_unlocked(self) -> None:
        """Tear down all Live regions and forget the active iteration.

        Used by ``_on_run_stopped`` and tests to fully reset the renderer
        state.  Iteration-end uses :meth:`_archive_current_iteration_unlocked`
        instead so finished iterations stay browsable.

        Caller must hold ``_console_lock``.
        """
        if self._fullscreen_live is not None:
            self._fullscreen_live.stop()
            self._fullscreen_live = None
        self._fullscreen_view = None
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._active_renderable = None
        self._current_iteration = None

    def _stop_live(self) -> None:
        with self._console_lock:
            self._stop_live_unlocked()

    # ── Fullscreen peek ──────────────────────────────────────────────

    def enter_fullscreen(self) -> bool:
        """Enter fullscreen peek mode.  Safe to call from any thread.

        Returns ``True`` if fullscreen is now active, ``False`` if the
        caller tried to enter when no iteration was running (nothing to
        show) or when already in fullscreen.

        Defaults the view to the currently-active iteration; if none is
        active (e.g. between iterations) falls back to the most recently
        finished iteration in history.
        """
        with self._console_lock:
            if self._fullscreen_view is not None:
                return True  # already active — no-op
            initial_id: int | None = self._current_iteration
            if initial_id is None and self._iteration_order:
                initial_id = self._iteration_order[-1]
            if initial_id is None or self.panel_for(initial_id) is None:
                self._console.print("[dim]Full peek: no iterations yet[/]")
                return False
            view = _FullscreenPeek(self, initial_id)
            self._fullscreen_view = view
            # Stop the compact Live before taking over the terminal so
            # the two Rich renderers don't fight for the same console.
            if self._live is not None:
                self._live.stop()
                self._live = None
            self._fullscreen_live = Live(
                view,
                console=self._console,
                screen=True,
                refresh_per_second=_LIVE_REFRESH_RATE,
                vertical_overflow="crop",
            )
            try:
                self._fullscreen_live.start()
            except Exception:
                # Alt-screen can fail in unusual terminals — clean up
                # and silently fall back to compact mode rather than
                # wedging the user.
                self._fullscreen_live = None
                self._fullscreen_view = None
                self._restart_compact_unlocked()
                return False
            return True

    def exit_fullscreen(self) -> None:
        """Exit fullscreen peek mode.  Safe to call from any thread.

        Replays any prints buffered during the fullscreen session so the
        terminal scrollback gets the iteration rules and status lines
        the user would otherwise have missed, then restarts the compact
        Live for the currently-active iteration (if any).
        """
        with self._console_lock:
            if not self._teardown_fullscreen_unlocked():
                return
            self._restart_compact_unlocked()

    def _teardown_fullscreen_unlocked(self) -> bool:
        """Stop the fullscreen Live and clear fullscreen state.

        Flushes any buffered prints so the terminal scrollback stays
        consistent.  Returns True if fullscreen was active, False if it
        was already inactive (caller can skip any follow-up steps).
        Caller must hold _console_lock.
        """
        if self._fullscreen_view is None:
            return False
        if self._fullscreen_live is not None:
            self._fullscreen_live.stop()
            self._fullscreen_live = None
        self._fullscreen_view = None
        self._flush_deferred_unlocked()
        return True

    def _restart_compact_unlocked(self) -> None:
        """Bring the compact Live back after a fullscreen exit.

        Uses the existing panel/spinner (and its accumulated buffer) if
        an iteration is still running.  No-op when the iteration has
        already ended.
        """
        source = self._active_renderable
        if source is None:
            return
        self._start_compact_live_unlocked(source)

    def _fullscreen_page_size(self) -> int:
        """Lines to jump on space/b (page down/up).

        One viewport minus a 2-line overlap so the user can keep their
        place across page jumps.
        """
        try:
            height = self._console.size.height
        except Exception:
            height = 40
        return max(1, height - _FULLSCREEN_CHROME_ROWS - 2)

    def handle_key(self, key: str) -> None:
        """Dispatch a single keypress from the KeypressListener.

        The emitter owns key routing because the keybindings differ
        between compact mode (``p`` / ``P``) and fullscreen mode (vim +
        less style navigation).  Errors are swallowed so a render bug
        never kills the listener thread.
        """
        try:
            if self._fullscreen_view is not None:
                self._handle_fullscreen_key(key)
                return
            if key == PEEK_TOGGLE_KEY:
                self.toggle_peek()
            elif key == FULLSCREEN_PEEK_KEY:
                self.enter_fullscreen()
        except Exception:
            pass

    def _handle_fullscreen_key(self, key: str) -> None:
        """Scroll + iteration navigation while fullscreen peek is active."""
        with self._console_lock:
            view = self._fullscreen_view
            if view is None:
                return  # raced with exit
            if key not in ("q", FULLSCREEN_PEEK_KEY):
                page = self._fullscreen_page_size()
                actions: dict[str, Callable[[], object]] = {
                    "j": lambda: view.scroll_down(1),
                    "k": lambda: view.scroll_up(1),
                    " ": lambda: view.scroll_down(page),
                    "b": lambda: view.scroll_up(page),
                    "g": view.scroll_to_top,
                    "G": view.scroll_to_bottom,
                    PREV_ITERATION_KEY: view.prev_iteration,
                    NEXT_ITERATION_KEY: view.next_iteration,
                }
                action = actions.get(key)
                if action is not None:
                    action()
                    if self._fullscreen_live is not None:
                        self._fullscreen_live.update(view)
                return
        # Exit path runs outside the lock to avoid re-entry.
        self.exit_fullscreen()

    def _on_iteration_started(self, data: IterationStartedData) -> None:
        iteration = data["iteration"]
        with self._console_lock:
            self._peek_broken = False
            # Defensive: if a previous iteration didn't archive (engine
            # error), evict it now so we don't leak panel state.
            if self._active_renderable is not None:
                self._archive_current_iteration_unlocked("interrupted")
            self._current_iteration = iteration
            renderable = self._create_panel_unlocked()

            def do_print() -> None:
                self._console.print()
                self._console.print(
                    Rule(
                        title=f"[bold {_brand.PURPLE}]Iteration {iteration}[/]",
                        align="left",
                        style=_brand.PURPLE,
                        characters="─",
                    )
                )

            if self._fullscreen_view is not None:
                # User is browsing fullscreen — defer the rule print
                # and don't start a competing compact Live.  The new
                # iteration becomes navigable via ``]`` immediately.
                # ``exit_fullscreen`` later restarts the compact Live
                # for whichever iteration is active at exit time.
                self._deferred_renders.append(do_print)
            else:
                do_print()
                self._start_compact_live_unlocked(renderable)

    def _echo_stream(self, text: str | None) -> None:
        """Print captured stream output, ensuring a trailing newline.

        Caller must hold ``_console_lock``.  No-ops when *text* is falsy.
        """
        if text:
            self._console.print(Text(text), end="")
            if not text.endswith("\n"):
                self._console.print()

    def _on_iteration_ended(
        self, data: IterationEndedData, color: str, icon: str, outcome: str
    ) -> None:
        iteration = data["iteration"]
        detail = data["detail"]
        log_file = data["log_file"]
        result_text = data["result_text"]
        echo_stdout = data.get("echo_stdout")
        echo_stderr = data.get("echo_stderr")
        with self._console_lock:
            # Stop the compact Live (if any) before archiving — the
            # underlying panel is preserved in history for fullscreen
            # browsing.  When fullscreen is active there is no compact
            # Live to stop; the panel was buffering events directly.
            if self._live is not None:
                self._live.stop()
                self._live = None
            self._archive_current_iteration_unlocked(outcome)

            def do_print() -> None:
                self._echo_stream(echo_stdout)
                self._echo_stream(echo_stderr)
                self._console.print(
                    f"[{color}]{icon} Iteration {iteration} {detail}[/]"
                )
                if log_file:
                    self._console.print(
                        f"  [dim]{_ICON_ARROW} {escape_markup(log_file)}[/]"
                    )
                if result_text:
                    self._console.print(Markdown(result_text))

            self._print_or_defer_unlocked(do_print)

    def _on_commands_completed(self, data: CommandsCompletedData) -> None:
        count = data["count"]
        if not count:
            return
        with self._console_lock:
            self._print_or_defer_unlocked(
                lambda: self._console.print(f"  [bold]Commands:[/] {count} ran")
            )

    def _on_log_message(self, data: LogMessageData) -> None:
        msg = escape_markup(data["message"])
        level = data["level"]
        traceback = data.get("traceback")

        def do_print() -> None:
            if level == LOG_ERROR:
                self._console.print(f"[red]{msg}[/]")
                if traceback:
                    self._console.print(f"[dim]{escape_markup(traceback)}[/]")
            else:
                self._console.print(f"[dim]{msg}[/]")

        with self._console_lock:
            self._print_or_defer_unlocked(do_print)

    def _on_run_stopped(self, data: RunStoppedData) -> None:
        with self._console_lock:
            # Tear down everything — the run is done.  If the user is
            # still inside fullscreen, exit it first and replay buffered
            # prints so the terminal scrollback shows the full history.
            self._teardown_fullscreen_unlocked()
            self._stop_live_unlocked()
            if data["reason"] != STOP_COMPLETED:
                return

            summary = _format_summary(
                data["total"],
                data["completed"],
                data["failed"],
                data["timed_out_count"],
            )
            self._console.print(f"\n[bold {_brand.BLUE}]{_RULE_HEAVY}[/]")
            self._console.print(f"[bold {_brand.GREEN}]Done:[/] {summary}")
