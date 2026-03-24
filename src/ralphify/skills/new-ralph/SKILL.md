---
name: new-ralph
description: Create a new ralph from a plain-English description of what you want to automate
argument-hint: "[name]"
disable-model-invocation: true
---

You are helping the user create a new **ralph** — a reusable automation for autonomous AI coding loops powered by ralphify. The user does NOT need to know how ralphify works internally. Your job is to translate their plain description into a working ralph setup.

## What you need from the user

Ask the user to **describe what they want to automate** in plain language. For example:
- "I want to write tests for my Python project until I hit 90% coverage"
- "I want to refactor all my JavaScript files to TypeScript"
- "I want to fix linting errors across the codebase"

If `$ARGUMENTS` was provided, use it as the ralph name. Otherwise, derive a short kebab-case name from their description.

Ask **only what you need** to build a good setup:
- What does "done" look like for one cycle of work?
- What language/tools/framework is the project using?
- Any conventions or constraints to follow?

Do NOT ask the user about commands, frontmatter, or other ralphify internals. Figure those out yourself based on their description.

## How ralphs work (internal reference — do not expose to user)

A ralph is a directory containing a `RALPH.md` file. The directory is a self-contained unit — everything the ralph needs lives there.

```
my-ralph/
├── RALPH.md              # the prompt (required)
├── check-coverage.sh     # script (optional, used by commands)
├── style-guide.md        # reference doc (optional)
└── test-data.json        # any supporting file (optional)
```

### RALPH.md format

```yaml
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest
  - name: git-log
    run: git log --oneline -10
  - name: coverage
    run: ./check-coverage.sh
args:
  - module
---

You are a senior engineer working on this project.

## Recent changes

{{ commands.git-log }}

## Test results

{{ commands.tests }}

If any tests are failing above, fix them before continuing.

## Coverage

{{ commands.coverage }}

## Task

...
```

#### Frontmatter fields

| Field | Required | Description |
|-------|----------|-------------|
| `agent` | Yes | The agent command to run (full command string) |
| `commands` | No | List of commands to run each iteration |
| `commands[].name` | Yes | Identifier, used in `{{ commands.<name> }}` placeholders. Letters, digits, hyphens, and underscores only. Must be unique. |
| `commands[].run` | Yes | Command to execute. Paths starting with `./` are relative to the ralph directory. |
| `commands[].timeout` | No | Max seconds before the command is killed (default: 60) |
| `args` | No | Declared argument names for positional CLI args. Letters, digits, hyphens, and underscores only. Must be unique. |
| `credit` | No | Append co-author trailer instruction (default: `true`). Set to `false` to disable. |

#### Body

The body is the prompt. It supports three placeholder types:
- `{{ commands.<name> }}` — replaced with command output each iteration
- `{{ args.<name> }}` — replaced with CLI arguments
- `{{ ralph.<name> }}` — replaced with runtime metadata (`name`, `iteration`, `max_iterations`)

HTML comments (`<!-- ... -->`) are automatically stripped before the prompt is assembled. They never reach the agent. Use them for notes about why rules exist or TODOs for prompt maintenance.

### Commands

A command is a name and something to run. The framework executes it, captures stdout/stderr, and makes the output available via `{{ commands.<name> }}`.

- **Paths starting with `./` run relative to the ralph directory.** `run: ./check-coverage.sh` runs `my-ralph/check-coverage.sh`.
- **Other commands run from the project root.** `run: uv run pytest` runs in the working directory where `ralph run` was invoked.
- **Output is always captured** regardless of exit code.
- **No shell features by default.** Commands are parsed with `shlex.split()`. For pipes, redirects, `&&` — use a script.
- **`{{ args.<name> }}` placeholders work in `run` strings.** Example: `run: gh issue view {{ args.issue }}` resolves before execution.

### User arguments

Ralphs can accept CLI arguments, making them reusable:

- **Named flags**: `ralph run my-ralph --dir ./src --focus "perf"` or `--dir=./src` → `{{ args.dir }}`, `{{ args.focus }}`
- **Positional args**: `ralph run my-ralph ./src "perf"` — requires `args: [dir, focus]` in frontmatter
- Missing args resolve to empty string

## Your workflow

1. **Understand the task.** Get a plain-English description. Ask short clarifying questions if needed — no more than 2-3.

2. **Design the ralph.** Based on the description, decide:
   - What prompt to write
   - What commands the agent needs (tests, lint, git log, coverage, etc.)
   - Whether user arguments would make the ralph more reusable
   - What supporting scripts or files are needed

3. **Create everything:**
   - A directory for the ralph
   - `RALPH.md` with frontmatter (agent, commands) and a clear, specific prompt. Follow these patterns:
     - Start with role and loop awareness: "You are an autonomous X agent running in a loop."
     - Include: "Each iteration starts with a fresh context. Your progress lives in the code and git."
     - Use `{{ commands.<name> }}` placeholders to show command output in context
     - Be specific about what one iteration of work looks like
     - Include rules as a bulleted list
     - End with commit conventions
   - Any supporting scripts (remember `chmod +x`)

4. **Present a summary** to the user:
   - Show the file tree of what you created
   - Briefly explain what the ralph will do in each iteration
   - Mention what commands will run and what they validate
   - Suggest running: `ralph run <name> -n 1`
