---
title: How Autonomous AI Coding Loops Work — The Ralph Loop Lifecycle
description: Step-by-step breakdown of what happens inside each ralph loop iteration — command execution, prompt assembly, agent piping, and the self-healing feedback cycle that auto-fixes broken code.
keywords: autonomous coding loop lifecycle, how AI coding agents work, self-healing code loop, AI agent feedback cycle, prompt assembly pipeline, ralph loop architecture, agentic coding workflow
---

# How the ralph loop works

!!! tldr "TL;DR"
    Each iteration: re-read `RALPH.md` from disk → run commands → replace `{{ placeholders }}` with output → pipe the assembled prompt to the agent → agent works and exits → repeat. The prompt body is re-read every iteration (so you can edit it live), but frontmatter is parsed once at startup. Failed commands still capture output — that's what makes the loop self-healing.

What happens inside each iteration of an autonomous coding loop? This page breaks down the lifecycle — from command execution to prompt assembly to agent piping — so you can write better prompts, debug unexpected behavior, and understand the self-healing feedback cycle.

## The six steps of each iteration

Every iteration follows the same sequence. Here's what happens at each step.

### 1. Re-read the prompt from disk

The prompt body (everything below the frontmatter) is read from disk **every iteration**. This means you can edit the prompt text — add rules, change the task, adjust constraints — while the loop is running. Changes take effect on the next cycle.

Frontmatter settings are parsed once at startup. To change them, restart the loop.

### 2. Run commands and capture output

Each command defined in the `commands` frontmatter runs in order and captures its output (stdout + stderr). Commands run from the **project root** by default. Commands starting with `./` run relative to the **ralph directory** instead — useful for scripts bundled alongside your `RALPH.md`.

Command output is captured **regardless of exit code** — a command like `pytest -x` exits non-zero when tests fail, but its output is exactly what you want in the prompt.

Each command has a default timeout of 60 seconds. If a command takes longer, the process is killed and the output captured so far is used. Override this with the `timeout` field for slow commands (e.g., a large test suite):

```yaml
commands:
  - name: tests
    run: uv run pytest -x
    timeout: 300  # 5 minutes
```

### 3. Resolve placeholders with command output

Each `{{ commands.<name> }}` placeholder in the prompt body is replaced with the corresponding command's output. **Only commands referenced by a placeholder appear in the prompt** — if you define a command but don't use `{{ commands.<name> }}` for it, the command still runs every iteration but its output is excluded. This forces you to place data deliberately rather than accidentally dumping everything into the prompt.

Placeholders for `{{ args.<name> }}` are replaced with user argument values from the CLI — both in the prompt body and in command `run` strings.

`{{ ralph.* }}` placeholders provide runtime metadata — no frontmatter configuration needed:

- `{{ ralph.name }}` — the ralph's directory name (e.g. `my-ralph`)
- `{{ ralph.iteration }}` — current iteration number (1-based)
- `{{ ralph.max_iterations }}` — total iterations if `-n` was set, empty otherwise

These are useful for iteration-aware prompts — for example, telling the agent to wrap up on the last iteration, or including the ralph name in commit messages.

Unmatched placeholders resolve to an empty string — you won't see raw `{{ }}` text in the assembled prompt.

### 4. Assemble the final prompt

The prompt body (everything below the YAML frontmatter in `RALPH.md`) with all placeholders resolved becomes the fully assembled prompt — a single text string ready for the agent.

HTML comments (`<!-- ... -->`) are stripped during assembly — they never reach the agent. Use them for notes to yourself, like why a rule exists or what to change next.

By default, ralphify appends a **co-author trailer instruction** to the end of the prompt, asking the agent to include `Co-authored-by: Ralphify <noreply@ralphify.co>` in its commit messages. This gives visibility into which commits were produced by a ralph loop. To disable it, set `credit: false` in the frontmatter.

### 5. Pipe the prompt to the AI agent

The assembled prompt is piped to the agent command via stdin:

```bash
echo "<assembled prompt>" | claude -p --dangerously-skip-permissions
```

The agent reads the prompt, does work in the current directory (edits files, runs commands, makes commits), and exits. Ralphify waits for the agent process to finish.

Exit codes still mean process success or failure. Promise completion is separate: `completion_signal` is the inner promise text (default: `RALPH_PROMISE_COMPLETE`), so ralphify only stops early when `stop_on_completion_signal` is `true` and the agent emits the matching `<promise>...</promise>` tag in output or captured result text. This aligns the promise format with Ralph-Wiggum, but ralphify still uses its own command/prompt loop architecture.

When the agent command starts with `claude`, ralphify automatically adds `--output-format stream-json --verbose` to enable structured streaming. This lets ralphify track agent activity in real time — you don't need to configure this yourself.

### 6. Loop back with fresh context

The loop starts the next iteration from step 1. The RALPH.md is re-read, commands run again with fresh output, and the agent gets a new prompt reflecting the current state of the codebase.

## What gets re-read vs. what stays fixed

| What | When read | Why it matters |
|---|---|---|
| Prompt body | Every iteration | Edit the prompt while the loop runs — the next iteration follows your new instructions |
| Command output | Every iteration | The agent always sees fresh data (latest git log, current test status, etc.) |
| Frontmatter settings | Once at startup | Parsed when the loop starts. Restart to pick up changes. |
| User arguments | Once at startup | Passed via CLI flags, constant for the run |

## How broken code gets fixed automatically

Here's a concrete example. Given this `RALPH.md`:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: git-log
    run: git log --oneline -5
  - name: tests
    run: uv run pytest -x
---

# Prompt

## Recent commits

{{ commands.git-log }}

## Test results

{{ commands.tests }}

Read TODO.md and implement the next task.
If tests are failing, fix them first.
```

### Iteration 1 (tests passing)

The assembled prompt piped to the agent:

```markdown
# Prompt

## Recent commits

a1b2c3d feat: add user model
e4f5g6h fix: resolve database connection timeout
i7j8k9l docs: update API reference

## Test results

============================= 5 passed in 1.23s ==============================

Read TODO.md and implement the next task.
If tests are failing, fix them first.
```

### Iteration 2 (tests broken by iteration 1)

```markdown
# Prompt

## Recent commits

x1y2z3a feat: add login endpoint
a1b2c3d feat: add user model
e4f5g6h fix: resolve database connection timeout

## Test results

FAILED tests/test_auth.py::test_login - AssertionError: expected 200, got 401
============================= 1 failed, 4 passed in 1.45s ====================

Read TODO.md and implement the next task.
If tests are failing, fix them first.
```

The agent sees the test failure and the instruction to fix it first. This is the **self-healing feedback loop**: the agent breaks something, the command captures the failure, and the agent sees it in the next iteration.

## Command execution order and failure handling

Commands run in the order they appear in the `commands` list in the RALPH.md frontmatter. All commands run regardless of whether earlier commands fail.

```yaml
commands:
  - name: tests      # Runs first
    run: uv run pytest -x
  - name: lint       # Runs second
    run: uv run ruff check .
  - name: git-log    # Runs third
    run: git log --oneline -10
```

## How to stop the loop (Ctrl+C, limits, and errors)

The loop continues until one of these happens:

| Condition | What happens |
|---|---|
| `Ctrl+C` (first) | Gracefully finishes the current iteration, then stops the loop. The agent completes its work and the iteration result is recorded. |
| `Ctrl+C` (second) | Force-stops immediately — kills the agent process and exits. Use when you don't want to wait for the current iteration to finish. |
| `-n` limit reached | Loop stops after completing the specified number of iterations |
| `stop_on_completion_signal: true` and matching `<promise>...</promise>` tag detected | Loop stops after the current iteration |
| `--stop-on-error` and agent exits non-zero or times out | Loop stops after the current iteration |
| `--timeout` exceeded | Agent process is killed, iteration is marked as timed out, loop continues (unless `--stop-on-error`) |

## Next steps

- [Getting Started](getting-started.md) — set up your first loop
- [CLI Reference](cli.md) — all commands and options
- [Troubleshooting](troubleshooting.md) — when things don't work as expected
