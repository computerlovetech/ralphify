---
title: Ralph Loop Recipes
description: Copy-pasteable ralph loop setups for autonomous ML research, promise-based early exit, test coverage, code migration, security scanning, deep research, documentation, bug fixing, and codebase improvement.
keywords: ralphify cookbook, autonomous coding recipes, RALPH.md examples, promise completion, early exit agent loop, documentation loop, bug fixing loop, codebase improvement, deep research agent, code migration loop, security scanning agent, test coverage automation, autoresearch, autonomous ML research
---

# Cookbook

!!! tldr "TL;DR"
    9 copy-pasteable ralph loops: [autoresearch](#autoresearch), [codebase improvement](#codebase-improvement), [documentation](#documentation-loop), [bug hunting](#bug-hunter), [deep research](#deep-research), [code migration](#code-migration), [security scanning](#security-scan), [test coverage](#test-coverage), and [promise completion](#promise-completion). Each is a real, runnable example from the `examples/` directory.

Copy-pasteable setups for common autonomous workflows. Each recipe is a real, runnable ralph from the [`examples/`](https://github.com/computerlovetech/ralphify/tree/main/examples) directory.

All recipes use **Claude Code** as the agent. To use a different agent, swap the `agent` field — see [Using with Different Agents](agents.md).

!!! tip "User arguments in recipes"
    Many recipes accept CLI arguments like `--focus` or `--target`. These aren't built-in flags — they're **user arguments** declared in each recipe's `args` field. When you pass `--focus "test coverage"`, the value replaces `{{ args.focus }}` in the prompt. See [User Arguments](cli.md#user-arguments) for details.

---

## Run autonomous ML experiments {: #autoresearch }

An autonomous ML research loop inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch). The agent runs experiments on a training script to minimize validation loss — modifying code, training for 5 minutes, keeping improvements and reverting failures. This recipe uses helper scripts as commands to surface experiment state each iteration.

**`autoresearch/RALPH.md`**

```markdown
--8<-- "examples/autoresearch/RALPH.md"
```

??? note "Helper scripts that surface experiment state each iteration"

    **`autoresearch/show-results.sh`**

    ```bash
    --8<-- "examples/autoresearch/show-results.sh"
    ```

    **`autoresearch/show-last-run.sh`**

    ```bash
    --8<-- "examples/autoresearch/show-last-run.sh"
    ```

```bash
ralph run autoresearch --train_script train.py --prepare_script prepare.py
```

```text
▶ Running: autoresearch
  2 commands · unlimited iterations

── Iteration 1 ──
  Commands: 2 ran
✓ Iteration 1 completed (312.4s)

── Iteration 2 ──
  Commands: 2 ran
✓ Iteration 2 completed (287.1s)
```

The `train_script` and `prepare_script` args let you point the ralph at any autoresearch-style project. The agent handles everything autonomously: establishing a baseline on the first iteration, then running experiments indefinitely. Each iteration is one hypothesis tested — modify the train script, train, evaluate, keep or revert.

---

## Improve code quality continuously {: #codebase-improvement }

A loop that continuously improves code quality without changing functionality. It runs [commands](quick-reference.md#command-fields) (tests, type checking, lint) each iteration to give the agent a [self-healing feedback loop](how-it-works.md#how-broken-code-gets-fixed-automatically), then picks one improvement to make.

**`improve-codebase/RALPH.md`**

```markdown
--8<-- "examples/improve-codebase/RALPH.md"
```

```bash
ralph run improve-codebase -n 5 --focus "focus on test coverage" --log-dir ralph_logs
```

```text
▶ Running: improve-codebase
  3 commands · max 5 iterations

── Iteration 1 ──
  Commands: 3 ran
✓ Iteration 1 completed (48.2s)
  → ralph_logs/001_20250115-142301.log

── Iteration 2 ──
  Commands: 3 ran
✓ Iteration 2 completed (55.7s)
  → ralph_logs/002_20250115-143112.log
```

---

## Write and improve documentation automatically {: #documentation-loop }

A loop focused on writing and improving documentation.

**`docs/RALPH.md`**

```markdown
--8<-- "examples/docs/RALPH.md"
```

```bash
ralph run docs --focus "focus on the API reference pages" --log-dir ralph_logs
```

```text
▶ Running: docs
  1 command · unlimited iterations

── Iteration 1 ──
  Commands: 1 ran
✓ Iteration 1 completed (63.5s)
  → ralph_logs/001_20250120-091502.log
```

---

## Find and fix bugs automatically {: #bug-hunter }

A loop that discovers bugs and fixes them. The agent reads the codebase, finds a real bug (edge case, off-by-one, missing validation), writes a failing test to prove it, then fixes it.

**`bug-hunter/RALPH.md`**

```markdown
--8<-- "examples/bug-hunter/RALPH.md"
```

```bash
ralph run bug-hunter -n 5 --focus "focus on input validation" --log-dir ralph_logs
```

```text
▶ Running: bug-hunter
  1 command · max 5 iterations

── Iteration 1 ──
  Commands: 1 ran
✓ Iteration 1 completed (71.3s)
  → ralph_logs/001_20250118-103045.log
```

---

## Run structured AI research loops {: #deep-research }

A structured research loop that builds up a report over many iterations. Uses shell scripts as commands to track maturity, show the question tree, and even run an editorial review agent that gives feedback between iterations.

This is a more advanced ralph — it uses [`args`](cli.md#user-arguments) for the research topic, helper scripts (run with `./` [relative to the ralph directory](how-it-works.md#2-run-commands-and-capture-output)), and a [`timeout`](how-it-works.md#2-run-commands-and-capture-output) on the review command.

**`research/RALPH.md`**

```markdown
--8<-- "examples/research/RALPH.md"
```

??? note "Helper scripts — `show-focus.sh`, `show-questions.sh`, `review.sh`"
    The helper scripts read from the workspace files and surface key state. The `review.sh` script pipes the full workspace to a separate Claude call that acts as an editorial reviewer — giving the research agent targeted feedback each iteration.

```bash
ralph run research --workspace ai-safety --focus "current approaches to AI alignment"
```

```text
▶ Running: research
  4 commands · unlimited iterations

── Iteration 1 ──
  Commands: 4 ran
✓ Iteration 1 completed (185.6s)
```

This recipe shows several advanced patterns: commands that call scripts relative to the ralph directory (`./show-focus.sh`), a command with a `timeout`, a command that itself calls an AI agent (`review.sh` pipes to `claude -p`), and `args` used in the prompt body via [`{{ args.workspace }}` placeholders](how-it-works.md#3-resolve-placeholders-with-command-output).

---

## Migrate code patterns across a codebase {: #code-migration }

A loop for batch code transformations — migrating from one pattern to another across a codebase. The `remaining` command counts how many files still need migration, giving the agent a clear finish line. Use [`--stop-on-error`](cli.md#ralph-run) to halt the loop once all files are migrated.

**`migrate/RALPH.md`**

```markdown
--8<-- "examples/migrate/RALPH.md"
```

??? note "`count-remaining.sh` — tracks migration progress"
    The script receives the pattern as an argument (resolved from `{{ args.old_pattern }}` in the `run` field) to find files that still need migration:

    ```bash
    --8<-- "examples/migrate/count-remaining.sh"
    ```

```bash
ralph run migrate --old_pattern "from utils import legacy_helper" \
                  --new_pattern "from core.helpers import modern_helper"
```

```text
▶ Running: migrate
  1 command · unlimited iterations

── Iteration 1 ──
  Commands: 1 ran
✓ Iteration 1 completed (34.8s)
```

The `remaining` command gives the agent a shrinking counter and a list of files still needing attention, so it always knows where to focus next.

---

## Automate security scanning and fixes {: #security-scan }

An iterative security review loop. The agent runs a scanner each iteration, picks one finding, fixes it, and verifies the fix. Good for systematically hardening a codebase. Use [`-n`](cli.md#ralph-run) to limit iterations and [`--log-dir`](cli.md#ralph-run) to keep an audit trail.

**`security/RALPH.md`**

```markdown
--8<-- "examples/security/RALPH.md"
```

```bash
ralph run security -n 10 --log-dir ralph_logs
```

```text
▶ Running: security
  1 command · max 10 iterations

── Iteration 1 ──
  Commands: 1 ran
✓ Iteration 1 completed (42.9s)
  → ralph_logs/001_20250122-160830.log
```

Swap `bandit` for your scanner of choice — `semgrep`, `npm audit`, `cargo audit`, etc. The pattern works the same: scan, pick a finding, fix it, log it.

---

## Increase test coverage automatically {: #test-coverage }

A loop that systematically increases test coverage. The agent sees the current coverage percentage and a list of uncovered functions, then writes tests for one module per iteration. The coverage command output feeds into the prompt via [`{{ commands.coverage }}`](how-it-works.md#3-resolve-placeholders-with-command-output) so the agent always knows where to focus.

**`test-coverage/RALPH.md`**

```markdown
--8<-- "examples/test-coverage/RALPH.md"
```

```bash
ralph run test-coverage -n 5 --target "focus on error handling paths" --log-dir ralph_logs
```

```text
▶ Running: test-coverage
  2 commands · max 5 iterations

── Iteration 1 ──
  Commands: 2 ran
✓ Iteration 1 completed (56.1s)
  → ralph_logs/001_20250125-140210.log
```

The coverage report gives the agent a clear metric to improve and shows exactly which lines are missing, so it always knows where to focus.

---

## Stop the loop when the task is complete {: #promise-completion }

A loop that uses ralphify's promise-completion path to stop before the iteration budget. The agent keeps working until the requested target is done, then emits `<promise>COMPLETE</promise>` so the run ends immediately instead of burning the remaining iterations.

**`promise-completion/RALPH.md`**

```markdown
--8<-- "examples/promise-completion/RALPH.md"
```

```bash
ralph run promise-completion -n 10 --target "stabilize the failing auth tests"
```

```text
▶ Running: promise-completion
  3 commands · max 10 iterations

── Iteration 1 ──
  Commands: 3 ran
✓ Iteration 1 completed (51.4s)

── Iteration 2 ──
  Commands: 3 ran
✓ Iteration 2 completed via promise tag <promise>COMPLETE</promise> (43.2s)

──────────────────────
Done: 2 iterations — 2 succeeded
```

Set `completion_signal` to the inner promise text and `stop_on_completion_signal: true` to enable early exit. The agent must emit the matching `<promise>...</promise>` tag — bare text does not count.

---

## Next steps

- [CLI Reference](cli.md) — all `ralph run` options (`--timeout`, `--stop-on-error`, `--delay`, user args)
- [Troubleshooting](troubleshooting.md) — when the agent hangs, commands fail, or output looks wrong
