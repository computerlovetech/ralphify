---
description: Full reference for ralphify's four primitives — checks (post-iteration validation), contexts (dynamic data injection), instructions (reusable prompt rules), and ralphs (named task-focused ralphs).
---

# Primitives

Primitives are reusable building blocks that extend your loop. They live in the `.ralphify/` directory and are automatically discovered by ralphify.

There are four kinds:

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

This creates `.ralphify/checks/my-tests/CHECK.md`:

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
.ralphify/checks/my-tests/
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

This creates `.ralphify/contexts/git-log/CONTEXT.md`:

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
.ralphify/contexts/project-info/
├── CONTEXT.md
└── run.sh
```

If both a `command` and a `run.*` script exist, the script takes precedence. Scripts and commands always run with the **project root** as the working directory.

This is useful for contexts that need more complex logic than a single shell command — for example, querying an API, combining multiple data sources, or running a Python script that formats output.

### Placement in the prompt

By default, all context output is appended to the end of the prompt. To control where it appears, use placeholders in your `RALPH.md`:

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

Instructions inject **static text** into the prompt. Use them for reusable rules, style guides, or constraints that you want to add or remove without editing the ralph file.

### Creating an instruction

```bash
ralph new instruction code-style
```

This creates `.ralphify/instructions/code-style/INSTRUCTION.md`:

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

## Ralphs

Ralphs are **reusable, named ralph files** that let you switch between different tasks without editing your root `RALPH.md`. Instead of maintaining one ralph and rewriting it each time you change focus, you create named ralphs and select the one you want at run time.

### When to use named ralphs

Named ralphs are useful when you have multiple recurring tasks for the same project:

- A `docs` ralph for documentation improvements
- A `refactor` ralph for cleaning up code
- A `add-tests` ralph for increasing test coverage
- A `bug-fix` ralph for systematic bug fixing

Each ralph can have its own placeholders, constraints, and workflow — tailored to that specific job.

### Creating a ralph

```bash
ralph new ralph docs
```

This creates `.ralphify/ralphs/docs/RALPH.md`:

```markdown
---
description: Describe what this ralph does
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

# Ralph

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
| `description` | string | `""` | Short description shown in `ralph status` |
| `enabled` | bool | `true` | Set to `false` to hide without deleting |

### Running a named ralph

Pass the ralph name as the first argument to `ralph run`:

```bash
ralph run docs           # Use the "docs" ralph
ralph run refactor -n 5  # Use "refactor" for 5 iterations
```

You can also set a default ralph in `ralph.toml`:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "docs"   # Name of a ralph in .ralphify/ralphs/
```

When `ralph` is set to a name (no `/` or `.` in the value), ralphify looks for `.ralphify/ralphs/<name>/RALPH.md` first, then falls back to treating it as a file path.

### Listing ralphs

Use `ralph status` to see all discovered ralphs with their enabled status and descriptions.

### Priority chain

When you run `ralph run`, the prompt is resolved in this order (first match wins):

1. **`-p` flag** — inline ad-hoc prompt text
2. **Positional argument** — `ralph run <name>` looks up `.ralphify/ralphs/<name>/RALPH.md`
3. **`--prompt-file` / `-f` flag** — explicit path to a prompt file
4. **`ralph.toml` `ralph` field** — can be a name or a file path
5. **Fallback** — `RALPH.md` in the project root

Named ralphs support all the same features as the root `RALPH.md`: context and instruction placeholders resolve as normal, and check failures are appended after each iteration.

Named ralphs also support [ralph-scoped primitives](#ralph-scoped-primitives) — checks, contexts, and instructions that only apply when running that specific ralph.

## Ralph-scoped primitives

When you use [named ralphs](#ralphs), you can attach checks, contexts, and instructions **to a specific ralph**. These ralph-scoped primitives live inside the ralph's directory and are merged with your global primitives when that ralph runs.

### Why use them

Different tasks need different validation. A documentation ralph might need a `mkdocs build` check but not a `cargo test` check. A refactoring ralph might need stricter lint rules. Ralph-scoped primitives let you customize the loop per task without cluttering the global `.ralphify/` directory.

### Creating ralph-scoped primitives

Use the `--ralph` flag with `ralph new` to scaffold a primitive inside a named ralph's directory:

```bash
ralph new check docs-build --ralph docs
ralph new context doc-coverage --ralph docs
ralph new instruction writing-style --ralph docs
```

This creates the primitive inside `.ralphify/ralphs/docs/` instead of the global `.ralphify/` directory.

### Directory structure

Place primitive directories inside the named ralph's directory, using the same `checks/`, `contexts/`, `instructions/` layout:

```
.ralphify/ralphs/docs/
├── RALPH.md
├── checks/
│   └── docs-build/
│       └── CHECK.md          ← only runs with the "docs" ralph
├── contexts/
│   └── doc-coverage/
│       └── CONTEXT.md        ← only injected with the "docs" ralph
└── instructions/
    └── writing-style/
        └── INSTRUCTION.md    ← only included with the "docs" ralph
```

### How merging works

When you run `ralph run docs`, ralphify discovers both global and ralph-scoped primitives, then merges them:

1. **Global primitives** from `.ralphify/checks/`, `.ralphify/contexts/`, `.ralphify/instructions/` are loaded first
2. **Ralph-scoped primitives** from `.ralphify/ralphs/docs/checks/`, etc. are loaded next
3. If a local primitive has the **same name** as a global one, the **local version wins**
4. Enabled filtering happens **after** the merge — a disabled local primitive can suppress a global one

This means you can:

- **Add** ralph-specific primitives that only run for that ralph
- **Override** a global primitive by creating a local one with the same name
- **Suppress** a global primitive by creating a disabled local one with the same name

### Example: override a global check

Say you have a global test check:

```
.ralphify/checks/tests/CHECK.md     ← command: pytest
```

For your `docs` ralph, you want to skip full tests and only validate the docs build. Create a local override:

```
.ralphify/ralphs/docs/checks/tests/CHECK.md
```

```markdown
---
enabled: false
---
```

This disables the global `tests` check when running the `docs` ralph, because the local primitive with the same name (`tests`) takes precedence.

Then add a ralph-specific check:

```
.ralphify/ralphs/docs/checks/docs-build/CHECK.md
```

```markdown
---
command: mkdocs build --strict
timeout: 60
---
Fix any MkDocs build warnings or errors.
```

Now `ralph run docs` runs only the `docs-build` check (plus any other global checks not overridden).

### With ad-hoc prompts

Ralph-scoped primitives only apply when running a named ralph. Ad-hoc prompts (`ralph run -p "..."`) use global primitives only, since there is no ralph directory to scan.

## Behavior notes

Important runtime behaviors that affect how you design and organize your primitives.

### Execution order

Primitives are discovered and executed in **alphabetical order by directory name**. This applies to checks, contexts, and instructions alike.

If execution order matters — for example, you want a fast lint check to run before a slow test suite — use number prefixes:

```
.ralphify/checks/
├── 01-lint/          ← runs first (fast feedback)
│   └── CHECK.md
├── 02-typecheck/     ← runs second
│   └── CHECK.md
└── 03-tests/         ← runs last (slowest)
    └── CHECK.md
```

All checks run regardless of whether earlier checks pass or fail — there is no short-circuiting.

### Naming

A primitive's name is its **directory name**, not a field in frontmatter. The name `tests` comes from the directory `.ralphify/checks/tests/`, not from anything inside `CHECK.md`. This name is used in:

- `ralph status` output
- Check failure headings in the prompt
- Placeholder references like `{{ contexts.git-log }}`

### Frontmatter format

Frontmatter uses a simplified `key: value` format — **not full YAML**. Each line is one field:

```markdown
---
command: uv run pytest -x
timeout: 120
enabled: true
---
```

Limitations:

- No nested structures, lists, or multi-line values
- Lines starting with `#` are treated as comments and ignored
- Only `timeout` (coerced to int) and `enabled` (coerced to bool) have type coercion — all other fields are strings
- Values for `enabled` are truthy if they match `true`, `yes`, or `1` (case-insensitive)

### Context command failures

Context output is injected into the prompt **regardless of the command's exit code**. Even if a context command exits non-zero, its stdout and stderr are still captured and included. This is intentional — commands like `pytest --tb=line -q` often exit non-zero (because tests are failing) but produce exactly the output you want the agent to see.

If a context command produces no output at all, only its static content (the body below the frontmatter) is injected. If it has neither output nor static content, it contributes nothing to the prompt.

### Disabled primitives

Setting `enabled: false` in frontmatter skips the primitive during execution but does **not** hide it. Disabled primitives still appear in `ralph status` (marked with a different indicator) and are still discovered — they're just filtered out before running. This makes it easy to toggle primitives on and off without deleting directories.

## Directory structure

```
.ralphify/
├── checks/                          ← global checks (all ralphs)
│   ├── lint/
│   │   └── CHECK.md
│   └── tests/
│       ├── CHECK.md
│       └── run.sh
├── contexts/                        ← global contexts
│   └── git-log/
│       └── CONTEXT.md
├── instructions/                    ← global instructions
│   └── code-style/
│       └── INSTRUCTION.md
└── ralphs/
    ├── docs/
    │   ├── RALPH.md
    │   ├── checks/                  ← ralph-scoped (docs only)
    │   │   └── docs-build/
    │   │       └── CHECK.md
    │   └── instructions/
    │       └── writing-style/
    │           └── INSTRUCTION.md
    └── refactor/
        └── RALPH.md
```

## Viewing your primitives

Use `ralph status` to see all discovered primitives and whether they're enabled:

```bash
ralph status
```
