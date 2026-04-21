# `_console_emitter.py` coverage

Valid at: 52e0272

## Recent changes

- 52e0272 — inlined the `msg = raw.get("message", {})` local in
  `_IterationPanel._apply_assistant`.  The alias was read exactly once on
  the next line as `msg.get("usage")`.  Collapsing to
  `usage = raw.get("message", {}).get("usage")` matches the chained-get
  style already used by `_iter_content_blocks` two functions above
  (`raw.get("message", {}).get("content", [])`), and the same
  inline-alias pattern as 497c028 (`agent`) and fc5e1cb (`total_in`).
  No other reference to `msg` exists in the function — verified by grep.
- b19625e — dropped the `new_offset` alias in `_FullscreenPeek.scroll_down`.
  The local was assigned directly to `self._offset`, then the
  follow-mode check re-read it as `new_offset == 0` — identical to
  `self._offset == 0` after the assignment.  Sibling `scroll_up` keeps
  its local because it compares old vs new *before* assigning (needed
  to conditionally disable auto-scroll on a real move); `scroll_down`
  has no such comparison, so the alias was dead.  Same Phase 4 shape
  as ef176bf (`line_count`) and 134078d (`name_col`).
- 497c028 — inlined the `agent = data["agent"]` local in `_on_run_started`.
  The alias was read exactly once, immediately below, as the arg to
  `_is_claude_command(agent)`.  Reading `data["agent"]` directly matches
  the style established by fc5e1cb (inlined `total_in`).  `ralph_name`
  was preserved — it's used inside an f-string where `data['ralph_name']`
  would be awkward.  Same Phase 4 shape as fc5e1cb.
- ef176bf — dropped the `line_count = len(self._scroll_lines)` alias in
  `_IterationSpinner._build_footer`.  The local served dual duty as a
  predicate (`if line_count > 0`) and as the `_plural` arg, but both
  uses were on the same truthy branch.  Replaced the predicate with
  `if self._scroll_lines:` (idiomatic list truthiness) and moved the
  `len()` call inside the branch that needs it.  This matches the
  sibling `_IterationPanel._build_footer` which uses `if self._tool_count > 0:`
  inline with no local alias.  Same Phase 4 shape as 134078d.
- ad7523e — moved the `if self._structured_agent: return` short-circuit
  in `_on_agent_output_line` from inside `_console_lock` to before
  acquisition.  The flag is write-once (set in `_on_run_started` before
  any iteration events can flow) and already read lock-free in
  `_on_agent_activity` — now both structured/raw output handlers use the
  same pattern.  Bonus: avoids a lock acquisition per stdout line under
  Claude, where every line short-circuits anyway.  Added a comment
  explaining the write-once invariant so the lock-free read doesn't look
  accidental.
- bcadee1 — dropped the `if self._active_renderable is not None:` guard
  wrapping `_archive_current_iteration_unlocked("interrupted")` in
  `_on_iteration_started`.  The archive helper already no-ops when
  nothing is active (docstring: "No-op when no iteration is active"),
  so the outer guard was mechanically redundant.  Updated the
  surrounding comment to note the no-op behavior so the call's intent
  still reads as defensive.  Same shape as 5337d88 / 4ccfa9a / 8cb0d47.
- 134078d — narrowed `name_col` scope in `_IterationPanel._apply_assistant`'s
  tool_use branch.  The padded name column was computed unconditionally
  but only rendered when `arg` was truthy (the `else` branch uses raw
  `name` without padding).  Moved the pad-to-column if/else inside
  `if arg:` so the helper variable lives only where it's used.  Same
  output in both branches — only the dead formatting work is gone.
- 1d7251f — promoted the `40` fallback-terminal-height literal to a named
  module constant `_DEFAULT_CONSOLE_HEIGHT` near the other fullscreen
  constants (`_FULLSCREEN_CHROME_ROWS`, `_FULLSCREEN_MIN_VISIBLE`).  Two
  use-sites both meant "reasonable default terminal height when the
  real value isn't available": `_FullscreenPeek._console_height` (class-
  attribute default used before the first `__rich_console__` call) and
  `ConsoleEmitter._fullscreen_page_size`'s except-branch fallback.  The
  constant keeps them in lockstep.  No other bare `40`s remain in the
  module (grep confirmed).
- d34e957 — dropped redundant `f"{_plural(total, 'line')}"` wrap in
  `_FullscreenPeek._build_header`.  `_plural` already returns a str
  so the f-string just format-identity-copied it.  Same shape as the
  surrounding `header.append(literal, style=...)` calls.  No other
  `f"{_plural(...)}"` wraps remain in the module (checked with grep).
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
