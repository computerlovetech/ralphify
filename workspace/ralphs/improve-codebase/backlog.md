# Backlog

Ordered roughly by phase, then by expected payoff. Add items freely; remove
only when they land in a commit.

## Phase 1 — dead code

- Audit `_console_emitter.py` for unused private helpers / constants (grep
  each `_foo` name for other references inside the module and tests).
- Audit `_agent.py` for parallel streaming/blocking helpers that reference
  the same constants but define their own copies.  (cb61477 — extracted
  `_call_safely` for the 3× best-effort observer-callback pattern; no
  remaining obvious dup after that pass.  Streaming's `_readline_pump` and
  blocking's `_pump_stream` look similar but do genuinely different work:
  the queue-based pump feeds a main-thread loop that parses JSON, while
  the list-based pump does its callback work inline on its own thread.)
- Check `cli.py` validators for unreachable error branches after recent
  TypedDict refactors.
- Confirm every `from typing import ...` import in `src/ralphify/` is used.
  (Checked 4ccfa9a — all six modules import only what they use.)
- vulture 60% flags that were verified as live: `clear_scroll`,
  `_SinglePanelNavigator`, `_stop_live`, `serialize_frontmatter`,
  `to_dict`, `_atexit_hook`, RunManager public methods — all used in tests,
  docs, or scripts/.  TypedDict field "unused" warnings are spurious.
- Consider inlining `_validate_name` into `_check_unique_name` in `cli.py`
  (the former has exactly one caller).  Tradeoff: the split doc-strings
  document the two concerns (format vs uniqueness) cleanly.
- `_is_claude_command` (`_console_emitter.py`) and `_supports_stream_json`
  (`_agent.py`) both check `Path(parts[0]).stem == CLAUDE_BINARY` but on
  different inputs (string vs list).  Consolidating would cross module
  boundaries for modest payoff — revisit only if a third caller appears.

## Phase 2 — duplication

- Look for repeated `console.print(...)` formatting patterns in
  `_console_emitter.py`.
- Look for repeated dict/TypedDict key access patterns in the event handlers.
- The fullscreen-Live teardown (`self._fullscreen_live.stop(); = None`)
  appears in `_stop_live_unlocked` and `_teardown_fullscreen_unlocked` —
  only two call sites and each is adjacent to other state mutations, so
  extracting right now would just add indirection. Revisit if a third
  caller appears.
- The `try: fn(); except Exception: pass` pattern appears in
  `_print_or_defer_unlocked`, `_flush_deferred_unlocked` (loop body),
  and around `handle_key`'s body.  Could extract a tiny `_safe_call`
  but each site is one line; not worth the indirection unless a fourth
  appears.
- `_IterationPanel._build_footer` and `_IterationSpinner._build_footer`
  both create `summary = Text(no_wrap=True, overflow="ellipsis")` then
  branch on count > 0 vs "waiting…".  Two subclasses only — already
  noted in coverage as not-worth-extracting.
- (01f2f1c — dropped `_FullscreenPeek._reset_view` which had the same body
  as `scroll_to_bottom`.)  No other near-duplicate scroll helpers spotted
  in that class; `scroll_up` / `scroll_down` / `scroll_to_top` each touch
  `_auto_scroll` under different conditions.  (b19625e — dropped the
  `new_offset` alias in `scroll_down`; `scroll_up` keeps its local
  because it compares old vs new before the assignment.)

## Phase 3 — magic values

Essentially drained.  Latest full scan (at 134078d): every bare integer
≥ 10 across `src/ralphify/` already resolves to a named constant, and
the handful of remaining single-site `2`s are flagged below with
"only if a second site appears".

- Scan each module's numeric literals (especially timeouts, widths, retry
  counts) and promote to module constants when reused.  (1d7251f —
  promoted `40` → `_DEFAULT_CONSOLE_HEIGHT` for the two fallback-height
  sites in `_console_emitter.py`.)
- `_console_emitter.py:_fullscreen_page_size` uses a bare `2` as the
  "page overlap lines" magic — only one site, but could be named
  `_PAGE_OVERLAP` for symmetry with `_FULLSCREEN_CHROME_ROWS` if a
  second page-size helper ever appears.
- `_keypress.py` has `_POLL_INTERVAL`, `_WIN_POLL_INTERVAL`,
  `_THREAD_JOIN_TIMEOUT` already at module top.  No obvious leftover
  literals worth promoting.

## Phase 4 — complex conditionals & long functions

- (134078d — narrowed `name_col` scope in `_IterationPanel._apply_assistant`
  so the padded name column is only computed on the branch that renders
  it.)
- (d0060b3 — exposed `_LivePanelBase.outcome` as a public property and
  switched `_FullscreenPeek._build_header`'s `source._outcome` read to
  go through it.  Mirror of ef9a178's `iteration_id` cleanup.)  Two
  private-attr cross-class reads remain — both of `source._scroll_lines`
  in `_FullscreenPeek._max_offset` and `__rich_console__`.  Those touch a
  mutable list the class itself appends to, so a read-only property
  would hide the mutation asymmetry; defer unless a clearer abstraction
  emerges (e.g., a "get a snapshot of visible lines" helper).
- `_IterationPanel._apply_assistant` still juggles three block types
  (`thinking` / `text` / `tool_use`) in one ~50-line method.  Splitting
  into `_render_thinking_block` / `_render_text_block` / `_render_tool_use_block`
  would shorten the outer loop but each helper is short enough that the
  indirection may not pay off — revisit only if a fourth block type lands.
- `cli.py:_parse_user_args` is 55 lines of token-by-token iteration with
  two nested branches and a while-loop that skips already-filled declared
  names.  Could be split into `_consume_flag` / `_consume_positional`
  helpers without changing any error message.  Medium payoff, medium
  churn — land only once behavior is fully pinned by tests (which it is).

## Notes / ideas to triage

- `scripts/tui_dev/` has its own fixtures; out of scope unless it blocks a
  src/ralphify/ change.
- `_IterationPanel._cache_read_tokens` is captured from usage but never
  read in production — only the regression test
  `test_format_tokens_does_not_double_count_cached_input` reads it.  The
  capture protects against a hypothetical future display, so not strictly
  dead, but worth revisiting when token rendering changes.
