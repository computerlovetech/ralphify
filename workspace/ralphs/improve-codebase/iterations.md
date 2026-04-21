# Iterations

One line per iteration: `<sha> <summary>`.

ad7523e refactor: move `_structured_agent` short-circuit out of `_console_lock` in `_on_agent_output_line` — flag is write-once (set in `_on_run_started`), matches `_on_agent_activity`'s pattern, avoids lock acquisition per stdout line under Claude
bcadee1 refactor: drop redundant `_active_renderable` guard in `_on_iteration_started` — archive call already no-ops when nothing is active
134078d refactor: narrow `name_col` scope into `if arg:` in `_apply_assistant` — padded variant was computed but unused when arg falsy
1d7251f refactor: promote 40-line fallback height to `_DEFAULT_CONSOLE_HEIGHT` — two sites used the literal 40 for "default terminal height when unknown"
6227863 refactor: drop redundant empty-user_args branch in `resolve_args` — callable path already yields "" for every match when dict is empty
d34e957 refactor: drop redundant f-string wrap around `_plural(total, 'line')` in fullscreen header
fc5e1cb refactor: inline `total_in` alias in `_format_tokens` — direct read of `self._input_tokens` clarifies intent
3838006 refactor: defer `panel_for` guard to `is_live` to dedupe identical condition
01f2f1c refactor: drop `_reset_view` in `_FullscreenPeek` — identical body to `scroll_to_bottom`
ef9a178 refactor: replace `_fullscreen_view._iteration_id` cross-class private access with public `iteration_id` property
c4469a1 refactor: extract `_step_iteration` to dedupe prev/next iteration browsing in `_FullscreenPeek`
5337d88 refactor: drop redundant empty-dict guard in `_format_categories` — `" · ".join([])` already returns `""`
8cb0d47 refactor: drop redundant `max(total - visible, 1)` guard in `_scrollbar_metrics` — early return makes `total - visible ≥ 1`
cb61477 refactor: extract `_call_safely` helper — dedupes 3× best-effort callback guards in `_agent.py`
4ccfa9a refactor: drop redundant `if parts else ""` in `_format_params` (empty join already returns "")
3e9627b refactor: extract `_stop_compact_live_unlocked` to dedupe compact-Live teardown across 3 call sites
0900aad refactor: drop redundant `_iteration_order` list — dict insertion order suffices
