---
description: Habits and patterns for productive autonomous coding loops. Covers plan files, cost control, check ordering, failure instructions, and when to intervene.
---

# Best Practices

You've set up ralphify, the loop is running, and the agent is producing work. Now what? This page covers how experienced users think about autonomous coding loops — the habits and patterns that separate productive loops from noisy ones.

## Start small, then scale

Never start with `ralph run` (infinite iterations) on a new setup. Start with a single iteration:

```bash
ralph run -n 1 --log-dir ralph_logs
```

Read the log. Did the agent:

- Pick a reasonable task?
- Produce working code?
- Commit with a useful message?

If yes, try 3 iterations. Review those logs too. Only scale up once you're confident the loop is consistently productive.

```bash
ralph run -n 3 --log-dir ralph_logs    # verify the loop is working
ralph run -n 10 --log-dir ralph_logs   # short batch
ralph run --log-dir ralph_logs         # let it run (Ctrl+C to stop)
```

This avoids burning API credits on a misconfigured loop.

## Write a plan file

The single biggest factor in loop quality is giving the agent a clear, ordered list of work. Without one, the agent guesses what to do — and guesses are unreliable.

Create a `PLAN.md` or `TODO.md` in your project root:

```markdown
# Plan

## Done
- [x] Set up project structure
- [x] Add user model with validation

## To do
- [ ] Add REST endpoint for creating users
- [ ] Add REST endpoint for listing users
- [ ] Add input validation middleware
- [ ] Write integration tests for user endpoints
```

Then reference it in your prompt:

```markdown
Read PLAN.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.
```

**Why this works:** The agent starts each iteration by reading the plan file. It sees what's done (from previous iterations' commits) and what's next. The plan file acts as shared memory between iterations, even though the agent has no memory of its own.

**Tip:** Keep tasks small and concrete. "Add user authentication" is too vague. "Add a /login endpoint that accepts email and password and returns a JWT" gives the agent everything it needs.

## Add signs, not essays

When the agent does something unhelpful, add a short, specific constraint to the prompt. This is the Ralph Wiggum technique — you're posting signs, not writing policy documents.

**Bad:** Writing a paragraph about code quality standards.

**Good:**

```markdown
- Do NOT create utility files — put helpers in the module that uses them
- Do NOT refactor code that isn't related to the current task
- Run `uv run pytest -x` BEFORE committing, not after
```

Each sign should be:

- **Specific** — reference exact commands, file patterns, or behaviors
- **Negative** — "do NOT" is clearer than "try to avoid"
- **Observable** — you should be able to tell from a git diff whether the agent followed the rule

Signs accumulate over time. That's fine — the agent reads them every iteration. After 10 iterations, your prompt might have 15 signs. That's a well-tuned prompt.

## Use checks for hard rules, the prompt for soft rules

**Checks** enforce rules automatically — if the check fails, the agent gets the failure output and must fix it. Use checks for objective, machine-verifiable rules:

- Tests must pass (`uv run pytest -x`)
- Code must lint cleanly (`uv run ruff check .`)
- Types must check (`npx tsc --noEmit`)
- Docs must build (`uv run mkdocs build --strict`)

**The prompt** is for rules that can't be machine-checked — coding style preferences, architectural decisions, commit message conventions. The agent might not always follow these perfectly, but they influence behavior.

**Rule of thumb:** If you can write a command that returns exit code 0 or 1, make it a check. If it's a judgment call, put it in the prompt.

## One task per iteration

Prompts that ask the agent to "implement the feature and also update the docs and fix the linting" in one iteration tend to produce incomplete work. The agent's context window is finite, and multi-task prompts lead to shortcuts.

Instead, design your plan file with one task per line and tell the agent to do one per iteration:

```markdown
## Rules
- One task per iteration — do it fully, then commit and stop
- Do NOT combine multiple tasks into one iteration
```

This keeps iterations short, commits atomic, and makes it easy to revert individual changes if something goes wrong.

## Structure your checks from fast to strict

If you have multiple checks, order them by speed. Ralphify runs checks alphabetically by name, so use naming to control order:

```
.ralph/checks/
├── 01-lint/          # Fast — runs in seconds
│   └── CHECK.md
├── 02-typecheck/     # Medium — runs in 10-30s
│   └── CHECK.md
└── 03-tests/         # Slowest — may take minutes
    └── CHECK.md
```

Why this matters: if the lint check fails, the agent fixes lint issues in the next iteration. If tests also failed, those failures still get reported. But on the next iteration, lint will pass quickly and the agent can focus on the test failures. This creates an efficient feedback cascade.

## Monitor with git, not just logs

Log files show you what the agent *said*. Git shows you what it *did*. After a batch of iterations, review the git history:

```bash
git log --oneline -20          # what did the agent commit?
git diff HEAD~10..HEAD --stat  # what files changed?
```

Red flags to watch for:

- **Commits that undo previous commits** — the agent is going in circles. Add a sign like "Do NOT revert or undo changes from previous iterations."
- **Giant commits touching many files** — the agent is over-scoping. Add "One task per iteration. Keep changes focused."
- **No commits for several iterations** — the agent is stuck or not following commit instructions. Check the logs.
- **Commits with vague messages** — add a sign: "Commit with a descriptive message like `feat: add X` not `update code`."

## Write failure instructions that guide, not just complain

When a check fails, the failure instruction tells the agent what to do about it. Generic instructions produce generic fixes:

**Weak:**

```markdown
---
command: uv run pytest -x
timeout: 120
---
Fix the failing tests.
```

**Strong:**

```markdown
---
command: uv run pytest -x
timeout: 120
---
Fix all failing tests. Do not skip or delete tests.
Do not add `# type: ignore` or `# noqa` comments.
If a test fails because of a missing import, add the import.
If a test fails because of changed behavior, update the source code, not the test.
```

The more specific your failure instruction, the faster the agent self-corrects.

## Use contexts for orientation, not overload

Contexts give the agent fresh data each iteration. But too many contexts bloat the prompt and dilute the agent's attention.

**Good contexts:**

- Recent git history (5-10 commits) — helps the agent understand what's been done
- Current test status (short summary) — highlights what needs attention
- Project structure (static) — orients the agent in the codebase

**Avoid:**

- Dumping entire file contents into the prompt — the agent can read files itself
- Running expensive commands (API calls, full test suites) as contexts — use checks for validation
- Adding contexts "just in case" — every context competes for the agent's attention

Start with one context (git log) and add more only when you see the agent making decisions without information it should have.

## Control costs

Every iteration is an LLM API call. Costs add up.

| Strategy | How | Impact |
|---|---|---|
| Start small | `ralph run -n 3` before scaling | Prevents runaway costs on broken setups |
| Set timeouts | `--timeout 300` | Kills stuck iterations instead of burning credits |
| Write focused prompts | One clear task, specific instructions | Shorter iterations = less token usage |
| Use a plan file | Agent does one task and stops | Prevents aimless exploration |
| Review before scaling | Read logs from first 3 iterations | Catches prompt issues early |
| Stop on error | `--stop-on-error` | Prevents loops where the agent repeatedly fails |

A well-tuned loop with focused tasks typically costs less per unit of useful work than a vague prompt running indefinitely.

## Know when to intervene

The loop is running. When should you step in?

**Let it run** when:

- Iterations are producing commits that match your plan
- Check failures are being fixed in the next iteration
- The agent is making steady progress through the task list

**Intervene** (edit `PROMPT.md`) when:

- The agent repeats the same mistake across multiple iterations — add a sign
- The agent is doing work that's not in the plan — add "Only work on tasks from PLAN.md"
- The agent is over-engineering — add "Keep implementations minimal. No extra abstractions."
- Check failures aren't getting fixed — make the failure instruction more specific

**Stop the loop** (`Ctrl+C`) when:

- The plan is complete — all tasks are done
- The agent is going in circles — undoing and redoing the same changes
- You need to add, remove, or reconfigure checks/contexts/instructions (these require a restart)
- You need to manually fix something the agent can't figure out

## Common mistakes

**Vague prompts.** "Improve the project" gives the agent no clear direction. Always point it at a specific task source (plan file, failing tests, issue tracker).

**No checks.** Running without checks means the agent has no feedback when it breaks something. Always add at least a test check.

**Too many checks on day one.** Start with tests. Add linting after the first few iterations work smoothly. Add type checking after that. Each check adds a potential failure loop.

**Editing checks while the loop is running.** Checks are loaded once at startup. If you change a check's command, the loop won't pick it up until you restart. (The prompt, however, is re-read every iteration.)

**Not reading the logs.** The first 3 iterations of any new setup should be carefully reviewed. Issues caught early save hours of wasted compute later.

**Asking the agent to do too much per iteration.** An iteration that takes 5 minutes and produces one focused commit is better than an iteration that takes 20 minutes and produces a sprawling changeset.
