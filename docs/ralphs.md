---
description: How to write effective ralphs for autonomous AI coding loops. Covers ralph anatomy, placeholder usage, ralph patterns for features, bugs, and docs.
---

# Writing Your Ralph

Your `RALPH.md` is the most important file in a ralphify project. It's the only thing the agent reads each iteration — it determines what gets built, how it's validated, and whether the loop produces useful work or noise.

## How the ralph works

Each iteration, ralphify:

1. Reads `RALPH.md` from disk
2. Resolves any `{{ contexts }}` and `{{ instructions }}` placeholders
3. Appends check failure output (if any checks failed last iteration)
4. Pipes the assembled text to your agent as stdin

Because the file is re-read every iteration, you can **edit it while the loop is running**. Changes take effect on the next iteration.

## Anatomy of a good ralph

A good loop ralph has four parts:

```markdown
# Ralph

<!-- 1. ROLE: Tell the agent what it is -->
You are an autonomous coding agent running in a loop.
Each iteration starts with a fresh context.

<!-- 2. TASK: What to work on -->
Implement features from the TODO list in priority order.

<!-- 3. CONSTRAINTS: What NOT to do -->
- No placeholder code — full implementations only
- Do not skip or delete tests
- Do not modify the CI pipeline

<!-- 4. PROCESS: How to validate and finish -->
- Run `pytest` before committing
- Commit with a descriptive message
- Mark completed items in TODO.md
```

### 1. Role

Ground the agent in its situation. Mention that it's in a loop, that context is fresh each iteration, and that progress lives in git. This prevents the agent from assuming it has memory of previous work.

### 2. Task

Be specific about what to work on. Point the agent at a concrete source of truth:

- A `TODO.md` or `PLAN.md` file it can read and update
- A specific feature spec or issue number
- A directory of failing tests to fix

Vague prompts like "improve the codebase" produce vague work.

### 3. Constraints

Tell the agent what **not** to do. This is where the "signs" go — lessons learned from previous iterations where the agent did something unhelpful:

```markdown
- Never add `# type: ignore` comments
- Do not refactor existing code unless the task requires it
- Do not create new files without checking if one already exists
```

Every time the agent does something dumb, add a sign. This is the Ralph Wiggum technique in action.

### 4. Process

Define the agent's workflow for each iteration:

```markdown
After implementing a change:
1. Run `uv run pytest` and fix any failures
2. Run `uv run ruff check .` and fix any lint errors
3. Commit with a message like `feat: add X` or `fix: resolve Y`
4. Update TODO.md to mark the task complete
```

Be explicit. "Run tests" is less effective than the exact command to run.

## Using placeholders

Placeholders let you inject [contexts](primitives.md#contexts) and [instructions](primitives.md#instructions) at specific locations in your prompt.

### Named placeholders

Place a specific context or instruction exactly where you want it:

```markdown
# Ralph

Here is the current project status:
{{ contexts.git-log }}

Here are the coding standards:
{{ instructions.code-style }}

Now implement the next feature from the plan.
```

### Bulk placeholders

Place all remaining (not yet placed by name) contexts or instructions:

```markdown
# Ralph

{{ contexts.git-log }}

Work on the next task.

## Additional context
{{ contexts }}

## Rules
{{ instructions }}
```

`{{ contexts }}` places every context that wasn't already placed by a named placeholder. Same for `{{ instructions }}`.

### No placeholders

If your prompt has no placeholders at all, contexts and instructions are automatically appended to the end of the prompt.

## The check feedback loop

When you have [checks](primitives.md#checks) configured, failed check output is automatically appended to the next iteration's prompt. You don't need to add anything to your `RALPH.md` for this — it happens automatically.

The feedback looks like:

````markdown
## Check Failures

The following checks failed after the last iteration. Fix these issues:

### lint
**Exit code:** 1

```
src/app.py:42:1: F401 'os' imported but unused
```

Fix all lint errors. Do not add noqa comments.
````

This creates a self-healing loop: the agent breaks something, the check catches it, and the next iteration gets instructions to fix it.

## Ralph patterns

### Feature implementation loop

```markdown
# Ralph

You are an autonomous coding agent. Each iteration starts fresh.
Progress lives in the code and git.

Read PLAN.md for the current task list. Pick the top uncompleted
task, implement it fully, then mark it done.

Rules:
- One task per iteration
- No placeholder code — full implementations only
- Run `pytest -x` before committing
- Commit with a descriptive message
- Mark the task done in PLAN.md

{{ contexts }}
{{ instructions }}
```

### Bug fix loop

```markdown
# Ralph

You are a bug-fixing agent. Each iteration starts fresh.

Run `pytest` to find failing tests. Pick one failure, trace the
root cause, fix it, and verify the fix. Do not modify the test
unless the test itself is wrong.

- Fix one bug per iteration
- Always run the full test suite after your fix
- Commit with `fix: <description of what was broken>`
```

### Documentation loop

```markdown
# Ralph

You are a documentation agent. Each iteration starts fresh.

Read the codebase and existing docs. Find the biggest gap between
what the code can do and what the docs explain. Write or improve
one page per iteration.

- Search before creating new files
- No placeholder content — full, accurate writing only
- Verify code examples actually work
- Commit with `docs: <what you documented>`
```

## Named ralphs for task switching

If you regularly switch between different tasks — documentation, refactoring, bug fixing, test coverage — you can save each ralph as a **named ralph** instead of rewriting `RALPH.md` every time.

```bash
ralph new ralph docs        # Create .ralphify/ralphs/docs/RALPH.md
ralph new ralph refactor    # Create .ralphify/ralphs/refactor/RALPH.md
ralph new ralph add-tests   # Create .ralphify/ralphs/add-tests/RALPH.md
```

Each named ralph is a full `RALPH.md` with its own frontmatter, content, and placeholders. Run it by name:

```bash
ralph run docs           # Use the docs ralph
ralph run refactor -n 5  # Use refactor for 5 iterations
```

Named ralphs live in `.ralphify/ralphs/<name>/RALPH.md`. Add a `description` to the frontmatter so `ralph ralphs list` shows what each one does:

```markdown
---
description: Systematically increase test coverage
enabled: true
---

# Ralph

You are a test-writing agent. Each iteration starts fresh...
```

You can also attach checks, contexts, and instructions to a specific named ralph — they'll only apply when that ralph runs. See [ralph-scoped primitives](primitives.md#ralph-scoped-primitives) for details.

See [Primitives — Ralphs](primitives.md#ralphs) for the full reference.

## Tips

**Start small.** Run a few iterations with `-n 3` and review the output before letting the loop run indefinitely.

```bash
ralph run -n 3 --log-dir logs
```

**Use a plan file.** Give the agent a `PLAN.md` or `TODO.md` that it reads and updates. This provides continuity across iterations without relying on memory.

**Add signs as you go.** Watch the first few iterations. When the agent does something wrong, add a constraint to the prompt. "SLIDE DOWN, DON'T JUMP."

**Edit while running.** The prompt is re-read each iteration. You can add signs, change the task, or adjust constraints without stopping the loop.

**Log everything.** Use `--log-dir` to save each iteration's output. This lets you review what happened and tune the prompt.

```bash
ralph run --log-dir ralph_logs
```

**Use checks for guardrails.** Don't rely on the prompt alone to enforce quality. Add checks for tests, linting, and type checking — they create a feedback loop that's more reliable than instructions.

```bash
ralph new check tests
ralph new check lint
```
