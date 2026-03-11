---
description: Install ralphify, set up your first autonomous coding loop with checks and contexts, and run a self-healing AI agent in 10 minutes.
---

# Getting Started

This tutorial walks through setting up ralphify on a project, adding checks and contexts, and running a productive autonomous loop. By the end, you'll have a self-healing coding loop that validates its own work.

## Prerequisites

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (or any agent CLI that accepts piped input)
- A project with a test suite (we'll use this for the feedback loop)

## Step 1: Install ralphify

=== "uv (recommended)"

    ```bash
    uv tool install ralphify
    ```

=== "pipx"

    ```bash
    pipx install ralphify
    ```

=== "pip"

    ```bash
    pip install ralphify
    ```

Verify it's working:

```bash
ralph --version
```

## Step 2: Initialize your project

Navigate to your project and run:

```bash
ralph init
```

This creates two files:

**`ralph.toml`** — configuration for the loop:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
```

!!! info "What does `--dangerously-skip-permissions` do?"
    Claude Code normally asks for your approval before running shell commands, editing files, or making git commits. The `--dangerously-skip-permissions` flag disables these interactive prompts so the agent can work autonomously without waiting for input. The `-p` flag enables non-interactive ("print") mode, which reads the prompt from stdin instead of opening a chat session.

    This is safe to use when ralphify is the only thing running the agent, because **checks** act as your guardrails — they validate the agent's work after each iteration and feed failures back for the agent to fix.

**`PROMPT.md`** — the prompt that gets piped to the agent each iteration. The default is a generic starting point — you'll customize it next.

## Step 3: Write your prompt

Replace the contents of `PROMPT.md` with a prompt tailored to your project. Here's an example for a Python project with a TODO list:

```markdown
# Prompt

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

!!! tip "Be specific"
    The more specific your prompt, the better the results. "Run tests" is less effective than the exact command `uv run pytest -x`. Point the agent at a concrete file like `TODO.md` rather than saying "find something to work on."

## Step 4: Do a test run

Before setting up checks and contexts, verify the basic loop works:

```bash
ralph run -n 1 --log-dir ralph_logs
```

This runs a single iteration and saves the output to `ralph_logs/`. Review the log to see what the agent did:

```bash
ls ralph_logs/
cat ralph_logs/001_*.log
```

!!! tip "Add `ralph_logs/` to `.gitignore`"
    Log files are useful for debugging but shouldn't be committed. Add them to your `.gitignore`:

    ```bash
    echo "ralph_logs/" >> .gitignore
    ```

If the agent produced useful work, you're ready to add guardrails.

## Step 5: Add a test check

Checks run **after** each iteration to validate the agent's work. If a check fails, its output is fed into the next iteration so the agent can fix the problem.

Create a check that runs your test suite:

```bash
ralph new check tests
```

This creates `.ralph/checks/tests/CHECK.md`. Edit it:

```markdown
---
command: uv run pytest -x
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip or delete tests.
Do not add `# type: ignore` or `# noqa` comments.
```

The text below the frontmatter is the **failure instruction** — it gets included in the prompt when the check fails, telling the agent how to handle the failure.

## Step 6: Add a lint check

Add a second check for linting:

```bash
ralph new check lint
```

Edit `.ralph/checks/lint/CHECK.md`:

```markdown
---
command: uv run ruff check .
timeout: 60
enabled: true
---
Fix all lint errors. Do not suppress warnings with noqa comments.
```

## Step 7: Add a context

Contexts inject dynamic data into the prompt before each iteration. A useful default is recent git history — it helps the agent understand what's already been done.

```bash
ralph new context git-log
```

Edit `.ralph/contexts/git-log/CONTEXT.md`:

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

The command runs each iteration and its output is appended to the prompt. The body text ("## Recent commits") appears above the command output as a label.

### Place the context in your prompt

By default, context output is appended to the end of the prompt. You can control placement with a placeholder in `PROMPT.md`:

```markdown
# Prompt

{{ contexts.git-log }}

You are an autonomous coding agent running in a loop...
```

Or use `{{ contexts }}` to place all contexts at once:

```markdown
{{ contexts }}

You are an autonomous coding agent...
```

## Step 8: Verify your setup

Check that everything is configured correctly:

```bash
ralph status
```

You should see output like:

```
Configuration
  Command: claude -p --dangerously-skip-permissions
  Prompt:  PROMPT.md

✓ Prompt file exists (342 chars)
✓ Command 'claude' found on PATH

Checks:  2 found
  ✓ lint               uv run ruff check .
  ✓ tests              uv run pytest -x

Contexts:  1 found
  ✓ git-log            git log --oneline -10

Instructions:  none

Ready to run.
```

## Step 9: Run the loop

Start with a few iterations to verify things work as expected:

```bash
ralph run -n 3 --log-dir ralph_logs
```

Watch the output. After each iteration, you'll see check results:

```
── Iteration 1 ──
✓ Iteration 1 completed (45.2s) → ralph_logs/001_20250115-142301.log
  Checks: 2 passed
    ✓ lint
    ✓ tests
```

If a check fails, the next iteration automatically gets the failure details:

```
── Iteration 2 ──
✗ Iteration 2 failed with exit code 1 (23.1s)
  Checks: 1 passed, 1 failed
    ✓ lint
    ✗ tests (exit 1)

── Iteration 3 ──
```

The agent in iteration 3 receives the test failure output and the failure instruction ("Fix all failing tests..."), so it can fix the problem.

## Step 10: Add signs while running

The prompt is re-read every iteration. If you see the agent doing something unhelpful, **edit `PROMPT.md` while the loop is running** — add a constraint:

```markdown
## Rules

- One task per iteration
- No placeholder code
- Run tests before committing
- Do NOT refactor existing code unless the task requires it   ← new sign
- Do NOT create new utility files                             ← new sign
```

This is the Ralph Wiggum technique: when the agent does something dumb, you put up a sign. The next iteration reads the updated prompt and follows the new rules.

## Step 11: Let it run

Once you're confident the loop is producing good work, let it run indefinitely:

```bash
ralph run --log-dir ralph_logs
```

Press `Ctrl+C` to stop at any time. You'll see a summary:

```
Done: 12 iteration(s) — 10 succeeded, 2 failed
```

## Your project structure

After setup, your project should look something like this:

```
your-project/
├── ralph.toml              # Loop configuration
├── PROMPT.md               # The prompt (edit anytime)
├── TODO.md                 # Task list the agent reads
├── .ralph/
│   ├── checks/
│   │   ├── tests/
│   │   │   └── CHECK.md    # Runs pytest after each iteration
│   │   └── lint/
│   │       └── CHECK.md    # Runs ruff after each iteration
│   └── contexts/
│       └── git-log/
│           └── CONTEXT.md  # Injects recent git history
├── ralph_logs/             # Iteration output logs
│   ├── 001_20250115-142301.log
│   ├── 002_20250115-142412.log
│   └── ...
└── src/                    # Your project code
```

## Next steps

- [How It Works](how-it-works.md) — understand the iteration lifecycle, prompt assembly, and feedback loop
- [Writing Your Prompt](prompts.md) — prompt anatomy, patterns, and tips for getting better results
- [Best Practices](best-practices.md) — habits and patterns for getting the most out of your loops
- [Cookbook](cookbook.md) — complete example setups for Python, TypeScript, bug fixing, and docs
- [Primitives](primitives.md) — full reference for checks, contexts, and instructions
- [Configuration & CLI](cli.md) — `ralph.toml` format, all commands, and options
