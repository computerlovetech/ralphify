# Iterations

One line per iteration: `<sha> <summary>`.

5337d88 refactor: drop redundant empty-dict guard in `_format_categories` — `" · ".join([])` already returns `""`
8cb0d47 refactor: drop redundant `max(total - visible, 1)` guard in `_scrollbar_metrics` — early return makes `total - visible ≥ 1`
cb61477 refactor: extract `_call_safely` helper — dedupes 3× best-effort callback guards in `_agent.py`
4ccfa9a refactor: drop redundant `if parts else ""` in `_format_params` (empty join already returns "")
3e9627b refactor: extract `_stop_compact_live_unlocked` to dedupe compact-Live teardown across 3 call sites
0900aad refactor: drop redundant `_iteration_order` list — dict insertion order suffices
