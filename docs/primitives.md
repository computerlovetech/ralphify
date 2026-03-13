---
description: Full reference for ralphify's four primitives — checks (post-iteration validation), contexts (dynamic data injection), instructions (reusable prompt rules), and ralphs (named task-focused ralphs).
---

# Primitives

Primitives are reusable building blocks that extend your loop. They live in the `.ralphify/` directory and are automatically discovered by ralphify.

| Primitive | Purpose | Runs when |
|---|---|---|
| [Checks](#checks) | Validate the agent's work (tests, linters) | After each iteration |
| [Contexts](#contexts) | Inject dynamic data into the prompt | Before each iteration |
| [Instructions](#instructions) | Inject static text into the prompt | Before each iteration |
| [Ralphs](#ralphs) | Reusable task-focused ralphs you can switch between | At run start |

## Checks

Checks run **after** each iteration to validate what the agent did. If a check fails, its output (and optional failure instructions) are appended to the next iteration's prompt so the agent can fix the problem.

### Creating a check

```bash
ralph new check my-tests
```

Edit `.ralphify/checks/my-tests/CHECK.md`:

```markdown
---
command: pytest -x
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip or delete tests.
```

The body text below the frontmatter is the **failure instruction** — it gets included in the prompt alongside the check output when the check fails.

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Command to run (see [command parsing](#command-parsing) below) |
| `timeout` | int | `60` | Max seconds before the check is killed |
| `enabled` | bool | `true` | Set to `false` to skip without deleting |

A check must have either a `command` in its frontmatter or an executable `run.*` script in its directory. Checks that have neither are skipped with a warning.

### Command parsing

Commands are split with Python's `shlex.split()` and executed **directly** — not through a shell. This means:

- Simple commands work: `uv run pytest -x`, `npm test`, `ruff check .`
- Shell features like pipes (`|`), redirections (`>`), chaining (`&&`), and variable expansion (`$VAR`) do **not** work

If you need shell features, use a script instead.

### Using a script instead of a command

Place an executable script named `run.*` (e.g. `run.sh`, `run.py`) in the check directory. If both a `command` and a `run.*` script exist, the script takes precedence. Scripts run with the **project root** as the working directory.

### How check failures appear in the prompt

When a check fails, ralphify appends this to the next iteration's prompt:

````markdown
## Check Failures

The following checks failed after the last iteration. Fix these issues:

### my-tests
**Exit code:** 1

```
FAILED tests/test_foo.py::test_bar - AssertionError
```

Fix all failing tests. Do not skip or delete tests.
````

## Contexts

Contexts inject **dynamic data** into the prompt before each iteration — recent git history, test status, file listings, etc.

### Creating a context

```bash
ralph new context git-log
```

Edit `.ralphify/contexts/git-log/CONTEXT.md`:

```markdown
---
command: git log --oneline -10
timeout: 30
enabled: true
---
## Recent commits
```

The command runs each iteration and its stdout is injected into the prompt. The body text appears above the command output as a label. A context can also be purely static (no command) — just omit the `command` field.

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Command whose stdout is captured |
| `timeout` | int | `30` | Max seconds before the command is killed |
| `enabled` | bool | `true` | Set to `false` to skip without deleting |

Scripts work the same way as checks — place a `run.*` script in the context directory.

Context output is injected **regardless of the command's exit code**. Commands like `pytest --tb=line -q` exit non-zero but produce exactly the output you want.

### Placement in the prompt

By default, all context output is appended to the end of the prompt. Control placement with placeholders in your `RALPH.md`:

```markdown
{{ contexts.git-log }}

Work on the next task.

{{ contexts }}
```

- `{{ contexts.git-log }}` — places that specific context here
- `{{ contexts }}` — places all remaining contexts (those not already placed by name)
- If no placeholders are found, all context output is appended to the end

## Instructions

Instructions inject **static text** into the prompt — reusable rules, style guides, or constraints you can toggle without editing the ralph file.

### Creating an instruction

```bash
ralph new instruction code-style
```

Edit `.ralphify/instructions/code-style/INSTRUCTION.md`:

```markdown
---
enabled: true
---
Always use type hints on function signatures.
Keep functions under 30 lines.
Never use print() for logging — use the logging module.
```

Instructions with no body text are silently excluded, even when `enabled: true`.

### Placement in the prompt

Same rules as contexts: `{{ instructions.code-style }}` for specific placement, `{{ instructions }}` for all remaining, or appended to the end if no placeholders.

## Ralphs

Named ralphs let you switch between different tasks without editing your root `RALPH.md`. Create a `docs` ralph, a `refactor` ralph, and a `bug-fix` ralph — select the one you need at run time.

### Creating a ralph

```bash
ralph new ralph docs
```

Edit `.ralphify/ralphs/docs/RALPH.md`:

```markdown
---
description: Improve project documentation
enabled: true
---

You are a documentation agent. Each iteration starts fresh.

Read the codebase and existing docs. Find the biggest gap and improve one page per iteration.

{{ contexts }}
{{ instructions }}
```

### Running a named ralph

```bash
ralph run docs           # Use the "docs" ralph
ralph run refactor -n 5  # Use "refactor" for 5 iterations
```

You can also set a default in `ralph.toml`:

```toml
[agent]
ralph = "docs"   # Name of a ralph in .ralphify/ralphs/
```

### Priority chain

When resolving the prompt (first match wins):

1. `-p` flag — inline ad-hoc prompt text
2. Positional argument — `ralph run <name>` looks up `.ralphify/ralphs/<name>/RALPH.md`
3. `--ralph-file` / `-f` flag — explicit path to a prompt file
4. `ralph.toml` `ralph` field — can be a name or a file path
5. Fallback — `RALPH.md` in the project root

## Ralph-scoped primitives

Named ralphs can have their own checks, contexts, and instructions that only apply when running that ralph. Create them with the `--ralph` flag:

```bash
ralph new check docs-build --ralph docs
ralph new context doc-coverage --ralph docs
```

These live inside the ralph's directory:

```
.ralphify/ralphs/docs/
├── RALPH.md
├── checks/docs-build/CHECK.md
└── contexts/doc-coverage/CONTEXT.md
```

When you run `ralph run docs`, global primitives and ralph-scoped primitives are merged. If a local primitive has the same name as a global one, the local version wins. A disabled local primitive suppresses a global one with the same name.

## Behavior notes

### Execution order

Primitives run in **alphabetical order by directory name**. To control order, use number prefixes: `01-lint/`, `02-typecheck/`, `03-tests/`. All checks run regardless of whether earlier checks pass or fail.

### What's re-read vs. fixed at startup

| What | When loaded | Editable while running? |
|---|---|---|
| `RALPH.md` | Every iteration | Yes |
| Context command output | Every iteration | Yes |
| Primitive config (checks, contexts, instructions) | Startup only | No — restart the loop |

`RALPH.md` is the primary way to steer the agent in real time.
