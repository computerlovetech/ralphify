# `_console_emitter.py` coverage

Valid at: 3e9627b

## Recent changes

- 3e9627b — extracted `_stop_compact_live_unlocked` helper to dedupe the
  `if self._live is not None: self._live.stop(); self._live = None` pattern
  across `_stop_live_unlocked`, `enter_fullscreen`, and `_on_iteration_ended`.
- 4ccfa9a — dropped `if parts else ""` branch in `_format_params`.
  `" · ".join([])` returns `""`, so the guard was dead.

## Verified live (grepped, confirmed used)

Private helpers and constants that look unused but are legitimately used:

- `_ICON_SUCCESS`, `_ICON_FAILURE`, `_ICON_TIMEOUT`, `_ICON_ARROW`,
  `_ICON_DASH`, `_ICON_PLAY` — all referenced in handler print strings.
- `clear_scroll` — used by test_console_emitter tests.
- `_SinglePanelNavigator` — used by tests and `scripts/tui_dev/snapshot.py`.
- `_stop_live` (the locked wrapper) — used only in tests for cleanup
  between test cases.  Production code uses `_stop_live_unlocked` inside
  an existing lock.
- `_format_params`, `_extract_file_path`, `_extract_key`, `_extract_params`
  — all referenced in the `_TOOL_REGISTRY` table (`"Read"`, `"Glob"`,
  `"Grep"`, `"Edit"`, `"Write"`, `"Bash"`, `"WebFetch"`, `"WebSearch"`, etc.).

## Potential future wins (not yet taken)

- `_IterationPanel._build_footer` and `_IterationSpinner._build_footer` both
  start with `Text(no_wrap=True, overflow="ellipsis")` and use
  `_footer_grid(summary)` — the `Text(...)` construction repeats, but only
  twice.  Not worth extracting unless a third subclass appears.
- `panel_for` / `is_live` share the guard
  `self._current_iteration == iteration_id and self._active_renderable is not None`.
  Two call sites; extracting would be premature.
