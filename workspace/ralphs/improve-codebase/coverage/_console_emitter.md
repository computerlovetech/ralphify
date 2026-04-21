# `_console_emitter.py` coverage

Valid at: fc5e1cb

## Recent changes

- fc5e1cb — inlined `total_in = self._input_tokens` alias in
  `_IterationPanel._format_tokens`.  The rename hinted at a "total
  input" aggregate that no longer exists (cache-read tokens are
  intentionally excluded from ctx); reading `self._input_tokens`
  directly matches what the value actually is.  Matches the existing
  style in the sibling `if self._output_tokens > 0` branch.
- 3838006 — rewrote `ConsoleEmitter.panel_for` to call `self.is_live(...)`
  for its guard instead of re-stating the
  `cur_iter == id and active is not None` expression.  Same behavior;
  one source of truth for "this is the active iteration" check.  Type
  checker is happy: returning `self._active_renderable` (typed
  `_LivePanelBase | None`) matches the declared return type even though
  the runtime invariant guarantees non-None whenever `is_live` is True.
- 01f2f1c — dropped `_FullscreenPeek._reset_view`.  Its body
  (`self._offset = 0; self._auto_scroll = True`) was byte-for-byte identical
  to `scroll_to_bottom`.  The two call sites in `_step_iteration` now call
  `scroll_to_bottom()` directly; the "snap to newest line + follow" intent
  moved into a docstring on the surviving method.  No other scroll-reset
  duplication remains.
- ef9a178 — replaced the single cross-class `_fullscreen_view._iteration_id`
  access in `_archive_current_iteration_unlocked` with the public
  `iteration_id` property on `_FullscreenPeek`.  No behavior change —
  `_FullscreenPeek` already exposes this via an `@property` (line 739-741);
  the private-attribute shortcut was an oversight from earlier iterations.
  Now `_iteration_id` is only read from within `_FullscreenPeek` itself.
- c4469a1 — extracted `_FullscreenPeek._step_iteration(direction)` from
  `prev_iteration` / `next_iteration`.  The two methods were 12-line
  mirror images differing only in step direction (-1 vs +1) and
  eviction-fallback (`ids[0]` vs `ids[-1]`).  Combined boundary check
  uses `0 <= new_idx < len(ids)` which collapses both `idx == 0` (prev)
  and `idx >= len(ids) - 1` (next) into one expression.
- 5337d88 — dropped `if not self._tool_categories: return ""` early
  return in `_IterationPanel._format_categories`.  Empty dict yields an
  empty list comprehension which `" · ".join` turns into `""`, so the
  guard was dead — same shape as 4ccfa9a's `_format_params` cleanup.
  No other empty-collection-then-join pattern remains in the module
  (`_format_tokens` builds its `parts` list with conditional appends, so
  it has no comprehension to short-circuit).
- 8cb0d47 — dropped the `max(total - visible, 1)` guard in
  `_scrollbar_metrics`.  The early return `if total <= visible` already
  guarantees `total - visible ≥ 1`, so the `max(..., 1)` floor was dead
  defensive code.  Inlined the subtraction directly into the `frac`
  calculation and added a comment noting the invariant.
- 0900aad — dropped `_iteration_order` list; `_iteration_history` dict
  preserves insertion order by itself.  Archive now pops-then-inserts to
  move existing entries to the end; eviction iterates the dict
  (oldest-first); `enter_fullscreen` uses `next(reversed(...))` for the
  most recent finished iteration.  Updated the single direct-field
  reference in `tests/test_console_emitter.py`.
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
