# Improve Codebase — Plan

Ralphify is a small, well-tested Python CLI (~4.7k LOC src, 628 tests passing,
ruff + ty clean). Recent commits have been steady refactor work targeting
`_console_emitter.py` (the biggest file at ~1.6k LOC). Continue that thread:
squeeze out duplication and complexity in the hottest files first, then fan
out to smaller polish.

## Phases

1. **Dead code / unused symbols** — private helpers with no callers, stale
   constants, dead branches. Verify with grep + tests.
2. **Duplication** — copy-pasted blocks (especially in `_console_emitter.py`
   and `_agent.py`). Extract helpers where extraction does not hurt clarity.
3. **Magic values & local constants** — stringly/numeric literals that repeat
   inside a single module; lift to a named constant near the top.
4. **Complex conditionals & long functions** — split `_console_emitter.py`
   functions that juggle many states; extract pure helpers.
5. **Naming & structure** — vague names, misplaced helpers, module-level
   imports that could collapse.
6. **Tests** — tighten unclear test names, merge duplicated fixtures.

Each iteration must preserve behavior. If an "improvement" changes observable
behavior (even by one log line), skip it and leave a note in backlog.md.

## Current phase

**Phase 3 — magic values & local constants.** Phase 1 looks exhausted: all
vulture flags (60% and above) were verified live, typing imports were all
checked used, and the cli.py / _console_emitter.py / _agent.py audits turned
up no remaining unused helpers. Move on to numeric/stringly literals that
repeat inside a single module; lift to a named constant near the top.
Phase 2 (duplication) is kept open for any near-duplicate block spotted in
passing — see backlog.

## Priorities (tailored to this repo)

- The largest module is `_console_emitter.py`; every iteration there should
  leave the module smaller *or* clearer, never both-at-once.
- `_agent.py` has two execution paths (streaming / blocking) that historically
  drift apart — watch for duplication.
- Constants like `_MAX_VISIBLE_SCROLL`, `_MAX_SCROLL_LINES`,
  `_SIGTERM_GRACE_PERIOD` live where they're used. Don't centralize them
  unless two modules need the same value.
- Do not churn public API: `src/ralphify/__init__.py` re-exports, CLI
  commands, and event payload types.
- Do not change docs wording in this ralph; that's for other ralphs.

## Out of scope

- New features or behavior changes
- Dependency upgrades
- Docs content (beyond fixing stale contributor notes encountered in passing)
- Release tooling
