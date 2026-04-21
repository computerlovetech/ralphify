# Iterations

One line per iteration: `<sha> <summary>`.

cb61477 refactor: extract `_call_safely` helper — dedupes 3× best-effort callback guards in `_agent.py`
4ccfa9a refactor: drop redundant `if parts else ""` in `_format_params` (empty join already returns "")
3e9627b refactor: extract `_stop_compact_live_unlocked` to dedupe compact-Live teardown across 3 call sites
0900aad refactor: drop redundant `_iteration_order` list — dict insertion order suffices
