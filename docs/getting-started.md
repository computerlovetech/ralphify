---
title: How to Set Up an Autonomous AI Coding Agent Loop — Ralphify Tutorial
description: Install ralphify, create your first ralph, add test commands for self-healing feedback, and run an autonomous AI coding loop — step-by-step in 10 minutes.
keywords: set up autonomous AI coding agent, install ralphify, AI coding loop tutorial, self-healing coding agent, run AI agent in loop, automate coding agent prompts, ralph loop setup, claude code autonomous
---

# Getting Started

!!! tldr "TL;DR"
    `uv tool install ralphify` → `ralph scaffold my-ralph` → edit the RALPH.md → `ralph run my-ralph -n 1 --log-dir ralph_logs` to test → add a `commands` entry for your test suite → `ralph run my-ralph` to loop. The agent sees fresh test output each iteration and fixes what it breaks.

This tutorial walks through setting up ralphify, creating a ralph with commands, and running a productive autonomous loop. By the end, you'll have a self-healing coding loop that validates its own work.

## Prerequisites

- **Python 3.11+**
- **An AI coding agent CLI** — this tutorial uses [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install it with `npm install -g @anthropic-ai/claude-code`. Ralphify also works with [other agents](agents.md).
- **A project with a test suite** (we'll use this for the feedback loop)

## Step 1: Install ralphify

```bash
uv tool install ralphify
```

??? note "Alternative install methods"
    ```bash
    pip install ralphify   # pip works too
    pipx install ralphify  # or pipx
    ```

Verify it's working:

```bash
ralph --version
```

```text
ralphify 0.3.0
```

## Step 2: Create a ralph

The fastest way to scaffold a ralph is `ralph scaffold`:

```bash
ralph scaffold my-ralph
```

```text
Created my-ralph/RALPH.md
Edit the file, then run: ralph run my-ralph
Optional early exit: uncomment completion_signal + stop_on_completion_signal and emit <promise>COMPLETE</promise>.
```

This creates `my-ralph/RALPH.md` with a ready-to-customize template including an example command, arg, prompt, and a commented promise-completion example. If you want the loop to stop before its iteration budget, uncomment `completion_signal` and `stop_on_completion_signal`, then tell the agent to emit the matching `<promise>...</promise>` tag when it is done. Edit the task section, [test it](#step-3-do-a-test-run), then follow [Step 4](#step-4-add-a-test-command) to add a test command — test feedback is what makes the loop self-healing.

Or create the file manually as shown below.

!!! tip "Installing an existing ralph?"
    Use [agr](https://github.com/computerlovetech/agr) to install shared ralphs from GitHub:

    ```bash
    agr add owner/repo
    ```

    This installs to `.agents/ralphs/` so you can run it by name with `ralph run <name>`.

### Manual setup

Create a ralph directory and `RALPH.md` with the agent field — this is the only required frontmatter:

```markdown
---
agent: claude -p --dangerously-skip-permissions
---

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

Read TODO.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Run `uv run pytest -x` before committing
- Commit with a descriptive message like `feat: add X` or `fix: resolve Y`
- Mark the completed task in TODO.md
```

!!! info "What does `--dangerously-skip-permissions` do?"
    Claude Code normally asks for your approval before running shell commands, editing files, or making git commits. The `--dangerously-skip-permissions` flag disables these interactive prompts so the agent can work autonomously without waiting for input. The `-p` flag enables non-interactive ("print") mode, which reads the prompt from stdin instead of opening a chat session.

## Step 3: Do a test run

Run a single iteration to verify your setup works:

```bash
ralph run my-ralph -n 1 --log-dir ralph_logs
```

This runs a single iteration and saves the output to `ralph_logs/`. Review the log to see what the agent did:

```bash
ls ralph_logs/
```

```text
001_20250115-142301.log
```

```bash
cat ralph_logs/001_*.log
```

!!! tip "Add `ralph_logs/` to `.gitignore`"
    Log files are useful for debugging but shouldn't be committed:

    ```bash
    echo "ralph_logs/" >> .gitignore
    ```

If the agent produced useful work, you're ready to add test feedback.

!!! info "Something not working?"
    If the agent errored or didn't do anything useful, check [Troubleshooting](troubleshooting.md) for common issues — agent hangs, missing commands, and frontmatter mistakes are all covered there.

## Step 4: Add a test command

Commands run each iteration and their output is injected into the prompt via `{{ commands.<name> }}` placeholders. Add a test command and its placeholder:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
---

# Prompt

## Test results

{{ commands.tests }}

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

Read TODO.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

If tests are failing, fix them before starting new work.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Commit with a descriptive message like `feat: add X` or `fix: resolve Y`
- Mark the completed task in TODO.md
```

The `tests` command runs `uv run pytest -x` each iteration. Its output replaces `{{ commands.tests }}` in the prompt, so the agent always sees the current test results. If tests fail, the agent fixes them — that's the self-healing loop.

## Step 5: Add more commands

Add a lint command and a git log for context:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
  - name: lint
    run: uv run ruff check .
  - name: git-log
    run: git log --oneline -10
---

# Prompt

## Recent commits

{{ commands.git-log }}

## Test results

{{ commands.tests }}

## Lint results

{{ commands.lint }}

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

Read TODO.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

If tests or lint are failing, fix them before starting new work.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Commit with a descriptive message like `feat: add X` or `fix: resolve Y`
- Mark the completed task in TODO.md
```

## Step 6: Run the loop

Start with a few iterations to verify everything works:

```bash
ralph run my-ralph -n 3 --log-dir ralph_logs
```

Add `--stop-on-error` to stop the loop if the agent exits non-zero or times out — useful when you're still tuning the prompt and don't want to waste iterations:

```bash
ralph run my-ralph -n 3 --log-dir ralph_logs --stop-on-error
```

Watch the output. Each iteration runs the commands, assembles the prompt with the command output, and pipes it to the agent:

```text
▶ Running: my-ralph
  3 commands · max 3 iterations

── Iteration 1 ──
  Commands: 3 ran
✓ Iteration 1 completed (45.2s)
  → ralph_logs/001_20250115-142301.log

── Iteration 2 ──
  Commands: 3 ran
✗ Iteration 2 failed with exit code 1 (23.1s)
  → ralph_logs/002_20250115-142512.log

── Iteration 3 ──
  Commands: 3 ran
✓ Iteration 3 completed (38.5s)
  → ralph_logs/003_20250115-142812.log

──────────────────────
Done: 3 iterations — 2 succeeded, 1 failed
```

The agent's output streams live to your terminal between the iteration markers — you can watch it work in real time. Press `p` to silence the stream if you prefer a quieter loop, and `p` again to resume.

If the agent breaks a test, the next iteration sees the failure output via `{{ commands.tests }}` and fixes it automatically.

!!! tip "Optional: stop when the task is fully complete"
    Add these frontmatter fields if you want the loop to stop on an explicit completion marker:

    ```yaml
    completion_signal: COMPLETE
    stop_on_completion_signal: true
    ```

    `completion_signal` is the inner promise text. With `completion_signal: COMPLETE`, the agent must emit `<promise>COMPLETE</promise>`. If you omit it, the default promise tag is `<promise>RALPH_PROMISE_COMPLETE</promise>`. The loop only exits early when `stop_on_completion_signal` is enabled and that tag is detected in agent output or captured result text. Exit code `0` still only means the agent process succeeded.

Once you're confident the loop works, drop the `-n 3` to let it run indefinitely. Press `Ctrl+C` to stop.

## Step 7: Steer while it runs

The prompt body is re-read from disk every iteration. You can edit `RALPH.md` while the loop is running and the agent follows your changes on the next cycle.

When the agent does something you don't want, add a rule:

```markdown
## Rules

- Do NOT delete failing tests — fix the underlying code instead
```

When you want to shift focus, change the task:

```markdown
Read TODO.md and focus only on the API module.
```

This is the most powerful part of ralph loops — you're steering a running agent with a text file.

!!! warning "Frontmatter changes need a restart"
    Only the **prompt body** is re-read each iteration. Frontmatter is parsed once at startup. If you add a new command, change the agent, or change completion settings, stop the loop with `Ctrl+C` and restart it.

## Next steps

- [Cookbook](cookbook.md) — copy-pasteable setups for coding, docs, research, and more
- [How it Works](how-it-works.md) — what happens inside each iteration
- [Troubleshooting](troubleshooting.md) — when things don't work as expected
- [CLI Reference](cli.md) — all commands and options
