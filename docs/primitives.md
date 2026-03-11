---
description: Full reference for ralphify's four primitives — checks (post-iteration validation), contexts (dynamic data injection), instructions (reusable prompt rules), and prompts (named task-focused prompts).
---

# Primitives

Primitives are reusable building blocks that extend your loop. They live in the `.ralph/` directory and are automatically discovered by ralphify.

There are four kinds:

| Primitive | Purpose | Runs when |
|---|---|---|
| [Checks](#checks) | Validate the agent's work (tests, linters) | After each iteration |
| [Contexts](#contexts) | Inject dynamic data into the prompt | Before each iteration |
| [Instructions](#instructions) | Inject static text into the prompt | Before each iteration |
| [Prompts](#prompts) | Reusable task-focused prompts you can switch between | At run start |

## Checks

Checks run **after** each iteration to validate what the agent did. If a check fails, its output (and optional failure instructions) are appended to the next iteration's prompt so the agent can fix the problem.

### Creating a check

```bash
ralph new check my-tests
```

This creates `.ralph/checks/my-tests/CHECK.md`:

```markdown
---
command: ruff check .
timeout: 60
enabled: true
---
```

Edit the frontmatter to set your validation command:

```markdown
---
command: pytest -x
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip or delete tests.
```

The body text below the frontmatter is the **failure instruction** — it gets included in the prompt alongside the check output when the check fails. Use it to tell the agent how you want failures handled.

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Command to run (see [command parsing](#command-parsing) below) |
| `timeout` | int | `60` | Max seconds before the check is killed |
| `enabled` | bool | `true` | Set to `false` to skip without deleting |

!!! warning "Checks need a command or script"
    A check must have either a `command` in its frontmatter or an executable `run.*` script in its directory. Checks that have neither are **skipped with a warning** during discovery. If `ralph status` shows fewer checks than you expect, verify each check has a command or script configured.

### Command parsing

Commands are split with Python's `shlex.split()` and executed **directly** — not through a shell. This means:

- Simple commands work as expected: `uv run pytest -x`, `npm test`, `ruff check .`
- Shell features like **pipes** (`|`), **redirections** (`2>&1`, `>`), **chaining** (`&&`, `||`), and **variable expansion** (`$VAR`) do **not** work
- Arguments with spaces need quoting: `pytest "tests/my dir/"` works correctly

If you need shell features, use a [script](#using-a-script-instead-of-a-command) instead.

### Using a script instead of a command

Instead of a `command` in frontmatter, you can place an executable script named `run.*` (e.g. `run.sh`, `run.py`) in the check directory:

```
.ralph/checks/my-tests/
├── CHECK.md
└── run.sh
```

If both a `command` and a `run.*` script exist, the script takes precedence. Scripts and commands always run with the **project root** as the working directory, not the primitive's directory.

### HTML comments are stripped

You can use HTML comments in any primitive file for internal notes — they're stripped before the content is injected into the prompt:

```markdown
---
command: pytest -x
timeout: 120
enabled: true
---
<!-- TODO: consider adding --tb=short flag -->
<!-- Agreed on this policy in sprint retro 2025-01-10 -->
Fix all failing tests. Do not skip or delete tests.
```

The agent never sees the comments. This is useful for documenting why a check exists or what you've tried.

### How check failures appear in the prompt

When a check fails, ralphify appends a section like this to the next iteration's prompt:

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

Contexts inject **dynamic data** into the prompt before each iteration. Use them to give the agent fresh information like recent git history, open issues, or file listings.

### Creating a context

```bash
ralph new context git-log
```

This creates `.ralph/contexts/git-log/CONTEXT.md`:

```markdown
---
command: git log --oneline -10
timeout: 30
enabled: true
---
```

The command runs each iteration and its stdout is injected into the prompt.

### Static content

The body below the frontmatter is **static content** that gets included above the command output:

```markdown
---
command: git log --oneline -10
timeout: 30
enabled: true
---
## Recent commits

Here are the latest commits for reference:
```

A context can also be purely static (no command) — just omit the `command` field and write the content in the body.

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Command whose stdout is captured (see [command parsing](#command-parsing)) |
| `timeout` | int | `30` | Max seconds before the command is killed |
| `enabled` | bool | `true` | Set to `false` to skip without deleting |

### Using a script instead of a command

Just like checks, you can place an executable script named `run.*` (e.g. `run.sh`, `run.py`) in the context directory instead of using a `command` in frontmatter:

```
.ralph/contexts/project-info/
├── CONTEXT.md
└── run.sh
```

If both a `command` and a `run.*` script exist, the script takes precedence. Scripts and commands always run with the **project root** as the working directory.

This is useful for contexts that need more complex logic than a single shell command — for example, querying an API, combining multiple data sources, or running a Python script that formats output.

### Placement in the prompt

By default, all context output is appended to the end of the prompt. To control where it appears, use placeholders in your `PROMPT.md`:

```markdown
# Prompt

{{ contexts.git-log }}

Work on the next task from the plan.

{{ contexts }}
```

- `{{ contexts.git-log }}` — places that specific context's output here
- `{{ contexts }}` — places all remaining contexts (those not already placed by name)
- If no placeholders are found, all context output is appended to the end

## Instructions

Instructions inject **static text** into the prompt. Use them for reusable rules, style guides, or constraints that you want to add or remove without editing the prompt file.

### Creating an instruction

```bash
ralph new instruction code-style
```

This creates `.ralph/instructions/code-style/INSTRUCTION.md`:

```markdown
---
enabled: true
---
```

Write your instruction content in the body:

```markdown
---
enabled: true
---
Always use type hints on function signatures.
Keep functions under 30 lines.
Never use print() for logging — use the logging module.
```

!!! note "Empty instructions are excluded"
    Instructions with no body text (only frontmatter) are silently excluded from prompt injection, even when `enabled: true`. If an instruction isn't appearing in your prompt, make sure it has content below the frontmatter.

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Set to `false` to skip without deleting |

### Placement in the prompt

Same rules as contexts:

- `{{ instructions.code-style }}` — places that specific instruction here
- `{{ instructions }}` — places all remaining instructions
- If no placeholders are found, all instructions are appended to the end

## Prompts

Prompts are **reusable, named prompt files** that let you switch between different tasks without editing your root `PROMPT.md`. Instead of maintaining one prompt and rewriting it each time you change focus, you create named prompts and select the one you want at run time.

### When to use named prompts

Named prompts are useful when you have multiple recurring tasks for the same project:

- A `docs` prompt for documentation improvements
- A `refactor` prompt for cleaning up code
- A `add-tests` prompt for increasing test coverage
- A `bug-fix` prompt for systematic bug fixing

Each prompt can have its own placeholders, constraints, and workflow — tailored to that specific job.

### Creating a prompt

```bash
ralph new prompt docs
```

This creates `.ralph/prompts/docs/PROMPT.md`:

```markdown
---
description: Describe what this prompt does
enabled: true
---

Your prompt content here.
```

Edit it with your task-specific prompt:

```markdown
---
description: Improve project documentation
enabled: true
---

# Prompt

You are a documentation agent. Each iteration starts fresh.

Read the codebase and existing docs. Find the biggest gap between
what the code can do and what the docs explain. Write or improve
one page per iteration.

- Search before creating new files
- No placeholder content — full, accurate writing only
- Verify code examples actually work
- Commit with `docs: <what you documented>`

{{ contexts }}
{{ instructions }}
```

### Frontmatter fields

| Field | Type | Default | Description |
|---|---|---|---|
| `description` | string | `""` | Short description shown in `ralph prompts list` |
| `enabled` | bool | `true` | Set to `false` to hide without deleting |

### Running a named prompt

Pass the prompt name as the first argument to `ralph run`:

```bash
ralph run docs           # Use the "docs" prompt
ralph run refactor -n 5  # Use "refactor" for 5 iterations
```

You can also set a default prompt in `ralph.toml`:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "docs"   # Name of a prompt in .ralph/prompts/
```

When `prompt` is set to a name (no `/` or `.` in the value), ralphify looks for `.ralph/prompts/<name>/PROMPT.md` first, then falls back to treating it as a file path.

### Listing prompts

```bash
ralph prompts list
```

This shows the root `PROMPT.md` (if it exists) plus all named prompts with their enabled status and descriptions.

### Priority chain

When you run `ralph run`, the prompt is resolved in this order (first match wins):

1. **`-p` flag** — inline ad-hoc prompt text
2. **Positional argument** — `ralph run <name>` looks up `.ralph/prompts/<name>/PROMPT.md`
3. **`--prompt-file` / `-f` flag** — explicit path to a prompt file
4. **`ralph.toml` `prompt` field** — can be a name or a file path
5. **Fallback** — `PROMPT.md` in the project root

Named prompts support all the same features as the root `PROMPT.md`: context and instruction placeholders resolve as normal, and check failures are appended after each iteration.

## Directory structure

```
.ralph/
├── checks/
│   ├── lint/
│   │   └── CHECK.md
│   └── tests/
│       ├── CHECK.md
│       └── run.sh
├── contexts/
│   └── git-log/
│       └── CONTEXT.md
├── instructions/
│   └── code-style/
│       └── INSTRUCTION.md
└── prompts/
    ├── docs/
    │   └── PROMPT.md
    └── refactor/
        └── PROMPT.md
```

## Viewing your primitives

Use `ralph status` to see all discovered primitives and whether they're enabled:

```bash
ralph status
```
