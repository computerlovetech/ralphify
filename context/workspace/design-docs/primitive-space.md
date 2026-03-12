# Design Decision: Primitive Space

**Date:** 2026-03-12
**Status:** Decided
**Context:** Issue #4 originally planned five primitives (Check, Instruction, Context, Gate, Transform). After shipping the first three and studying real-world agent harness patterns (OpenAI's Harness Engineering, Cursor's long-running agent work), we re-evaluated whether the remaining two (Gate, Transform) are needed — and whether the existing three are the right abstraction.

---

## The foundational question

All three shipped primitives are mechanically the same thing: a directory with a marker file, optional frontmatter config, a static body, and an optional command. The output gets injected into the agent's prompt at some point in the iteration lifecycle.

The only real differences are two configuration knobs:

1. **Phase** — when does it run? (pre-iteration / post-iteration / static)
2. **Inject condition** — when does its output enter the prompt? (always / on-failure / never)

An Instruction is the degenerate case: no command, always inject static text.

This raised the question: should Ralphify have one generic primitive (a "hook") that users configure, or multiple named primitives with fixed semantics?

---

## The full primitive space

Enumerating all meaningful combinations of phase, command, and inject condition:

| # | Phase | Command | Inject | Name | Description | Verdict |
|---|-------|---------|--------|------|-------------|---------|
| 1 | pre | yes | always | **Context** | Gather info, always show agent | **Shipped** |
| 2 | pre | yes | on-failure | *(Gate)* | Pre-check, warn agent if bad state | Redundant with Context |
| 3 | pre | yes | on-success | — | Inject only if precondition passes | No real use case |
| 4 | pre | yes | never | *(Setup)* | Side-effect only: reset env, pull, clean | Not a prompt primitive |
| 5 | post | yes | always | — | Always inject post-output (e.g. coverage) | Minor variant of Check |
| 6 | post | yes | on-failure | **Check** | Validate work, inject error if fails | **Shipped** |
| 7 | post | yes | on-success | — | Inject only on success | No real use case |
| 8 | post | yes | never | *(Transform)* | Side-effect only: format, commit, deploy | Not a prompt primitive |
| 9 | — | no | always | **Instruction** | Static text, always inject | **Shipped** |

---

## Analysis of the "maybe" candidates

### #2 — Gate (pre + command + on-failure)

"Before the agent runs, check repo state, warn if broken." But a Context running `lint .` and always injecting the output achieves the same thing — the agent sees lint errors either way. The on-failure filter is a minor noise reduction, not a fundamentally different capability.

More importantly: a Gate that *blocks* execution is a dead end. The agent can't learn from it. A ralph loop should be a dynamic, self-healing loop with high-level boundaries enforced deterministically. Blocking is the opposite of that — injecting the failure so the agent can fix it (which is what Check already does) is strictly more useful.

**Decision:** Drop Gate. Use Check (post-iteration) or Context (pre-iteration, always inject) instead.

### #4 — Setup (pre + command + never)

"Reset test DB, clean build artifacts before iteration." Real need, but this doesn't touch the prompt at all. It's infrastructure, not a prompt primitive. A `pre_command` field in `ralph.toml` would be more honest than a full primitive with its own directory.

**Decision:** Drop as a primitive. If needed later, add as a simple lifecycle config in `ralph.toml`.

### #5 — Post-iteration always-inject

"Always show test coverage after iteration, not just on failure." This is a Check that also injects on success. One config flag (`inject: always`) away from the current Check — not a new primitive.

**Decision:** If demand arises, add an `inject: always` option to Check frontmatter. Not a separate primitive.

### #8 — Transform (post + command + never)

"Auto-format code, commit, deploy after iteration." Pure side-effect — doesn't inject into the prompt. Same as #4: this is lifecycle infrastructure, not a prompt primitive.

**Decision:** Drop as a primitive. If needed later, add as `post_command` in `ralph.toml`.

---

## Why named primitives over a single generic "hook"

The alternative design — one primitive type with `phase` and `inject` config — is mechanically simpler and more flexible. But Ralphify's value is the opinion, not the mechanism.

**Arguments for named primitives:**

- **Legibility.** A user scanning `.ralph/` immediately understands intent. `checks/lint` = validates my work. `contexts/git-status` = gathers info. `instructions/no-force-push` = permanent rule. With `hooks/lint`, you have to read the config.
- **Agent legibility.** An agent seeing "this is a check" immediately knows the lifecycle semantics. With a generic hook, it has to parse config to get the same understanding. The OpenAI harness engineering post found that agent legibility is the whole game.
- **Opinionated structure.** Ralphify isn't a generic hook runner — it encodes an opinion about how agent loops should work: gather context, give instructions, run the agent, check the work. The names make that opinion tangible.
- **Convention over configuration.** Named primitives mean users don't have to think about phase/inject combinations. The framework makes the right choice for each use case.

**Arguments for a single hook:**

- Simpler mental model (one concept, not three).
- More flexible for unforeseen use cases.
- Less code to maintain.

**Decision:** Keep named primitives. The semantic clarity outweighs the mechanical elegance of a single hook. Both the OpenAI (strict boundaries + predictable structure) and Cursor (right amount of structure is in the middle) posts validate this approach.

---

## Final decision

**Keep three primitives. Drop Gate and Transform from the roadmap.**

| Primitive | Phase | Inject | Purpose |
|-----------|-------|--------|---------|
| **Context** | pre-iteration | always | Gather dynamic information for the agent |
| **Instruction** | static | always | Permanent rules and constraints |
| **Check** | post-iteration | on-failure | Validate work, feed errors back into the loop |

The prompt pipeline:

```
Read PROMPT.md
  -> resolve {{ contexts }}    (dynamic, pre-iteration)
  -> resolve {{ instructions }} (static, always)
  -> append check failures      (post-iteration feedback from previous run)
  -> pipe to agent
```

If lifecycle side-effects (setup/cleanup) are needed in the future, they belong in `ralph.toml` config, not as primitives — because they don't inject into the prompt and therefore aren't part of the prompt resolution pipeline.

---

## References

- [Issue #4: Primitives roadmap](https://github.com/computerlovetech/ralphify/issues/4)
- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/) — validates strict structure, agent legibility, repository as system of record
- [Cursor: Scaling long-running autonomous coding](context/blog_posts/Scaling%20long-running%20autonomous%20coding.md) — validates "right amount of structure is in the middle", removing complexity > adding it
