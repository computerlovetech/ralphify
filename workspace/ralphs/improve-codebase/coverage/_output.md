# `_output.py` coverage

Valid at: 7730dd4

## Recent changes

- 7730dd4 — narrowed `secs = total % _SECONDS_PER_MINUTE` scope in
  `format_duration`.  The local was computed unconditionally between
  the `total = int(seconds + 0.5)` / `minutes = total // 60` setup and
  the `if minutes < _MINUTES_PER_HOUR:` branch, but only consumed by
  the `f"{minutes}m {secs}s"` return on the truthy branch.  The hours
  branch (`hours = minutes // 60; mins = minutes % 60`) never touches
  `secs`, so for any duration ≥ 1h the modulo was wasted work.  Moved
  the assignment inside the if to co-locate with its only use site.
  Same Phase 4 shape as 134078d / ef176bf / 59b0e34 / b19625e.

## Layout snapshot (at 7730dd4)

- Module is 139 lines — small, mostly format helpers.
- Top: `IS_WINDOWS`, `SUBPROCESS_TEXT_KWARGS`, `SESSION_KWARGS` —
  shared subprocess kwargs imported by `_agent.py` and `_runner.py`.
- `ProcessResult` — base dataclass for `RunResult` / `AgentResult`,
  with the shared `success` property.
- Format helpers: `ensure_str`, `collect_output`, `warn`, `format_count`,
  `format_duration`.
- Module-level constants `_COUNT_THOUSANDS`, `_COUNT_MILLIONS`,
  `_SECONDS_PER_MINUTE`, `_MINUTES_PER_HOUR` are used only by the two
  `format_*` functions below them.

## Potential future wins (not yet taken)

- `format_count` repeats `f"{n / _COUNT_MILLIONS:.1f}M"` in two
  branches (the bare ≥1M return and the rounded-cross-into-M guard).
  Could lift to a `_format_millions(n)` helper, but each site is one
  line and the duplication is intentional (the rounding guard explains
  the second site).  Skip unless a third user appears.
- `collect_output`'s `text = ensure_str(stream)` local is read once on
  the next line (`parts.append(text)`).  Could inline as
  `parts.append(ensure_str(stream))` for the same alias-inline pattern
  as fc5e1cb / 497c028 / 52e0272.  Tradeoff: the local documents the
  decoded form, but `ensure_str` already names the operation.  Worth
  a Phase 4 iteration if we want symmetry with the other inlines.
- The two `format_*` functions both have a "rounded value crossed into
  next unit" guard (59.95s → "1m 0s"; 999_950 → "1.0M") with parallel
  comments referencing each other.  Already kept in lockstep — no
  refactor needed.
