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

## Phase 3 — magic values

- Scan each module's numeric literals (especially timeouts, widths, retry
  counts) and promote to module constants when reused.

## Notes / ideas to triage

- `scripts/tui_dev/` has its own fixtures; out of scope unless it blocks a
  src/ralphify/ change.
