# Backlog

Ordered roughly by phase, then by expected payoff. Add items freely; remove
only when they land in a commit.

## Phase 1 — dead code

- Audit `_console_emitter.py` for unused private helpers / constants (grep
  each `_foo` name for other references inside the module and tests).
- Audit `_agent.py` for parallel streaming/blocking helpers that reference
  the same constants but define their own copies.
- Check `cli.py` validators for unreachable error branches after recent
  TypedDict refactors.
- Confirm every `from typing import ...` import in `src/ralphify/` is used.

## Phase 2 — duplication

- Look for repeated `console.print(...)` formatting patterns in
  `_console_emitter.py`.
- Look for repeated dict/TypedDict key access patterns in the event handlers.

## Phase 3 — magic values

- Scan each module's numeric literals (especially timeouts, widths, retry
  counts) and promote to module constants when reused.

## Notes / ideas to triage

- `scripts/tui_dev/` has its own fixtures; out of scope unless it blocks a
  src/ralphify/ change.
