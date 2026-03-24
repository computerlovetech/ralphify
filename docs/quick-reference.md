---
title: Ralph Quick Reference
description: Condensed reference for ralphify commands, RALPH.md format, placeholder syntax, and common patterns — the page you bookmark and come back to.
keywords: ralphify quick reference, RALPH.md format, placeholder syntax, commands reference, cheat sheet
---

# Quick Reference

Everything you need at a glance. Bookmark this page.

## CLI commands

```bash
ralph run my-ralph                 # Run loop forever (Ctrl+C to stop)
ralph run my-ralph/RALPH.md        # Can also pass the file path directly
ralph run my-ralph -n 5            # Run 5 iterations
ralph run my-ralph -n 1 --log-dir logs  # Single iteration with output capture
ralph run my-ralph --stop-on-error # Stop if agent exits non-zero or times out
ralph run my-ralph --delay 10      # Wait 10s between iterations
ralph run my-ralph --timeout 300   # Kill agent after 5 min per iteration
ralph run my-ralph --dir ./src     # Pass user args to the ralph

ralph init my-task                  # Scaffold a ralph from template (no AI)
ralph init                         # Scaffold in current directory

ralph new                          # AI-guided ralph creation
ralph new docs                     # AI-guided creation with name pre-filled

ralph --version                    # Show version
```

## Directory structure

```
my-ralph/
└── RALPH.md              # Prompt + configuration (required)
```

That's it. A ralph is a directory with a `RALPH.md` file.

## RALPH.md format

```markdown
---
agent: claude -p --dangerously-skip-permissions    # Required: agent command
commands:                                           # Optional: run each iteration
  - name: tests
    run: uv run pytest -x
  - name: lint
    run: uv run ruff check .
  - name: git-log
    run: git log --oneline -10
args: [dir, focus]                                  # Optional: declared user arguments
---

# Prompt body

{{ commands.git-log }}

{{ commands.tests }}

{{ commands.lint }}

Your instructions here. Use {{ args.dir }} for user arguments.
```

### Frontmatter fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | Full agent command (piped via stdin) |
| `commands` | list | no | Commands to run each iteration |
| `args` | list | no | User argument names. Letters, digits, hyphens, and underscores only. |
| `credit` | bool | no | Append co-author trailer instruction to prompt (default: `true`) |

### Command fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Identifier for `{{ commands.<name> }}`. Letters, digits, hyphens, and underscores only. |
| `run` | string | (required) | Shell command to execute (supports `{{ args.<name> }}` placeholders). Commands starting with `./` run from the ralph directory; others run from the project root. |
| `timeout` | number | `60` | Max seconds before the command is killed |

## Placeholders

### Command placeholders

```markdown
{{ commands.tests }}              # Replaced with test command output
{{ commands.git-log }}            # Replaced with git-log command output
```

- Output includes stdout + stderr regardless of exit code
- Unmatched placeholders resolve to empty string
- Must be `commands` (plural)

### User argument placeholders

```markdown
{{ args.dir }}                   # Replaced with --dir value from CLI
{{ args.focus }}                 # Replaced with --focus value from CLI
```

- Pass via `ralph run my-ralph --dir ./src --focus "perf"` or `--dir=./src` (named flags)
- Or positionally: `ralph run my-ralph ./src "perf"` (requires `args:` in frontmatter)
- Mixed: `ralph run my-ralph --focus "perf" ./src` — positional args skip names already provided via flags
- `--` ends flag parsing: `ralph run my-ralph -- --verbose ./src` treats `--verbose` as a positional value
- Missing args resolve to empty string

### Ralph placeholders

```markdown
{{ ralph.name }}               # Ralph directory name (e.g. "my-ralph")
{{ ralph.iteration }}          # Current iteration number (1-based)
{{ ralph.max_iterations }}     # Total iterations if -n was set, empty otherwise
```

- Automatically available — no frontmatter configuration needed
- Useful for progress tracking, naming logs, or adjusting behavior near the end of a run

## The loop

Each iteration:

1. Re-read `RALPH.md` from disk
2. Run all commands in order, capture output
3. Resolve `{{ commands.* }}`, `{{ args.* }}`, and `{{ ralph.* }}` placeholders
4. Pipe assembled prompt to agent via stdin
5. Wait for agent to exit
6. Repeat

## Live editing

- The prompt body is re-read from disk every iteration — edit the prompt while the loop runs (frontmatter is parsed once at startup)
- HTML comments (`<!-- ... -->`) are stripped from the prompt — use them for notes to yourself

## Common patterns

### Minimal ralph

```markdown
---
agent: claude -p --dangerously-skip-permissions
---

Read TODO.md and implement the next task. Commit when done.
```

### Self-healing with test feedback

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
---

{{ commands.tests }}

Fix failing tests before starting new work.
Read TODO.md and implement the next task.
```

### Parameterized ralph

```markdown
---
agent: claude -p --dangerously-skip-permissions
args: [dir, focus]
---

Research the codebase at {{ args.dir }}.
Focus area: {{ args.focus }}.
```

```bash
ralph run research --dir ./api --focus "error handling"
```

### Debug a single iteration

```bash
ralph run my-ralph -n 1 --log-dir ralph_logs
cat ralph_logs/001_*.log
```

### Run on a branch

```bash
git checkout -b feature && ralph run my-ralph
```
