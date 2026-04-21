# Iterations

One line per iteration: `<sha> <summary>`.

59b0e34 refactor: inline `_fullscreen_page_size()` into the space/b lambdas in `_handle_fullscreen_key` — the `page` local was computed unconditionally in the non-exit branch but only consumed by the page-down (" ") and page-up ("b") action lambdas.  j/k/g/G/[/] now skip the call entirely; space/b still compute it exactly once per keypress, now at action-invocation time under the same lock.  Same Phase 4 "narrow the scope of a one-branch local" shape as 134078d / ef176bf / b19625e.

52e0272 refactor: inline `msg` alias in `_apply_assistant` — the `msg = raw.get("message", {})` local was read exactly once on the next line as `msg.get("usage")`.  Collapsing into `raw.get("message", {}).get("usage")` matches the chained-get style already used by `_iter_content_blocks` (which independently does `raw.get("message", {}).get("content", [])`) and the inline-alias pattern from 497c028 / fc5e1cb.

b19625e refactor: drop `new_offset` alias in `_FullscreenPeek.scroll_down` — the local was assigned to `self._offset` and then re-read only as `new_offset == 0`, which is identical to `self._offset == 0` after the assignment.  Sibling `scroll_up` needs its local because it compares old vs new before the assignment; `scroll_down` has no such comparison, so the alias was dead.  Same shape as ef176bf and 134078d.

497c028 refactor: inline `agent` alias in `_on_run_started` — the local served a single use as the arg to `_is_claude_command(...)`.  Reading `data["agent"]` directly matches the sibling style from fc5e1cb (`total_in` inline).  Preserved `ralph_name` — it's used inside an f-string on line 1247 where the alias still helps readability.

ef176bf refactor: drop `line_count` alias in `_IterationSpinner._build_footer` — local was computed unconditionally but only used on the truthy branch (both as predicate `> 0` and as `_plural` arg).  Inlined the truthy check on `self._scroll_lines` and moved the `len()` call inside the branch that uses it.  Matches the style of sibling `_IterationPanel._build_footer` which uses `if self._tool_count > 0:` with no local alias.  Same Phase 4 shape as 134078d's `name_col` narrowing.

d8d5592 refactor: gate `"".join(stdout/stderr_lines)` in `_run_agent_streaming` on `log_dir is not None` — the joined strings were only consumed by `_write_log` and the `captured_*` AgentResult fields, both of which discarded the result when log_dir was None.  Mirrors the already-lazy idiom in `_run_agent_blocking` and drops the duplicated `... if log_dir is not None else None` ternary on each AgentResult field.
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
