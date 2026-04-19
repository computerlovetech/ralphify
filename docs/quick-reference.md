---
title: "RALPH.md Syntax and CLI Cheat Sheet — Ralphify Quick Reference"
description: "Cheat sheet for ralphify — RALPH.md frontmatter format, CLI flags for ralph run/scaffold, placeholder syntax for commands and args, and common loop patterns you can copy-paste."
keywords: RALPH.md format, RALPH.md frontmatter syntax, ralph run CLI flags, ralphify cheat sheet, AI coding agent loop syntax, ralph commands placeholder, ralph args placeholder, ralph scaffold, autonomous agent loop reference, ralphify quick reference
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

ralph scaffold my-task              # Scaffold a ralph from template
ralph scaffold                     # Scaffold in current directory

ralph --version                    # Show version
```

Full flag descriptions and examples → [CLI reference](cli.md)

## Directory structure

```text
my-ralph/
└── RALPH.md              # Prompt + configuration (required)
```

That's it. A ralph is a directory with a `RALPH.md` file. See [Getting Started](getting-started.md) to create your first one.

## RALPH.md format

```markdown
---
agent: claude -p --dangerously-skip-permissions # (1)!
commands: # (2)!
  - name: tests
    run: uv run pytest -x
  - name: lint
    run: uv run ruff check .
  - name: git-log
    run: git log --oneline -10
args: [dir, focus] # (3)!
---

# Prompt body  <!-- (4) -->

{{ commands.git-log }} <!-- (5) -->

{{ commands.tests }}

{{ commands.lint }}

Your instructions here. Use {{ args.dir }} for user arguments. <!-- (6) -->
```

1. **Required.** The full shell command to pipe the prompt to. `-p` enables non-interactive mode, `--dangerously-skip-permissions` lets the agent work autonomously.
2. **Optional.** Each command runs every iteration and its output fills the matching `{{ commands.<name> }}` placeholder.
3. **Optional.** Declares positional argument names. Named flags (`--dir`, `--focus`) work without this — `args` is only needed for positional usage.
4. Everything below the `---` frontmatter is the prompt body. It's re-read from disk every iteration, so you can edit it while the loop runs.
5. Replaced with the command's stdout + stderr. Only commands with a matching placeholder appear in the assembled prompt.
6. Replaced with the `--dir` value from the CLI. Missing args resolve to an empty string.

### Frontmatter fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | Full agent command (piped via stdin). See [agent configuration](agents.md) for supported agents. |
| `commands` | list | no | Commands to run each iteration |
| `args` | list | no | User argument names. Letters, digits, hyphens, and underscores only. |
| `credit` | bool | no | Append co-author trailer instruction to prompt (default: `true`) |
| `completion_signal` | string | no | Inner text for the completion promise tag. `COMPLETE` means the agent must emit `<promise>COMPLETE</promise>` (default inner text: `RALPH_PROMISE_COMPLETE`) |
| `stop_on_completion_signal` | bool | no | Stop the loop early when the matching `<promise>...</promise>` tag is detected (default: `false`) |

### Command fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Identifier for `{{ commands.<name> }}`. Letters, digits, hyphens, and underscores only. |
| `run` | string | (required) | Shell command to execute (supports `{{ args.<name> }}` placeholders). Commands starting with `./` run from the ralph directory; others run from the project root. |
| `timeout` | number | `60` | Max seconds before the command is killed |

!!! warning "No shell features in commands"
    Commands are run directly, not through a shell — pipes (`|`), redirections (`>`), and chaining (`&&`) won't work in the `run` field. Use a script instead: `run: ./my-script.sh` (scripts starting with `./` run from the ralph directory).

## Placeholders

### Command placeholders

```markdown
{{ commands.tests }} <!-- (1) -->
{{ commands.git-log }} <!-- (2) -->
```

1. Replaced with the `tests` command's stdout + stderr, regardless of exit code.
2. Replaced with the `git-log` command's output. Only commands referenced by a placeholder appear in the assembled prompt — unreferenced commands still run but their output is excluded.

- Unmatched placeholders resolve to empty string
- Must be `commands` (plural)

For details on placeholder resolution, see [How it Works](how-it-works.md#3-resolve-placeholders-with-command-output).

### User argument placeholders

```markdown
{{ args.dir }} <!-- (1) -->
{{ args.focus }} <!-- (2) -->
```

1. Replaced with the `--dir` value from the CLI. Missing args resolve to empty string.
2. Replaced with the `--focus` value from the CLI.

- Pass via `ralph run my-ralph --dir ./src --focus "perf"` or `--dir=./src` (named flags)
- Or positionally: `ralph run my-ralph ./src "perf"` (requires `args:` in frontmatter)
- Mixed: `ralph run my-ralph --focus "perf" ./src` — positional args skip names already provided via flags
- `--` ends flag parsing: `ralph run my-ralph -- --verbose ./src` treats `--verbose` as a positional value
- See [CLI reference → User arguments](cli.md#user-arguments) for full details on flag and positional parsing

### ralph placeholders

```markdown
{{ ralph.name }} <!-- (1) -->
{{ ralph.iteration }} <!-- (2) -->
{{ ralph.max_iterations }} <!-- (3) -->
```

1. Ralph directory name (e.g. `my-ralph`).
2. Current iteration number (1-based).
3. Total iterations if `-n` was set, empty otherwise.

- Automatically available — no frontmatter configuration needed
- Useful for progress tracking, naming logs, or adjusting behavior near the end of a run
- See [How it Works](how-it-works.md) for more on the loop lifecycle

## The loop

Each iteration:

1. Re-read `RALPH.md` from disk
2. Run all commands in order, capture output
3. Resolve `{{ commands.* }}`, `{{ args.* }}`, and `{{ ralph.* }}` placeholders
4. Pipe assembled prompt to agent via stdin
5. Wait for agent to exit
6. Repeat

### Stopping the loop

| Action | What happens |
|---|---|
| `Ctrl+C` (once) | Finishes the current iteration gracefully, then stops |
| `Ctrl+C` (twice) | Force-kills the agent process and exits immediately |
| `p` | Toggle live peek of the agent's stdout (on by default in an interactive terminal — press to silence, press again to resume) |
| `P` (shift+p) | Open full-screen peek — scroll the entire activity buffer. `j/k` line, `space/b` page, `g/G` top/bottom, `q` or `P` exits |
| `-n` limit reached | Stops after the specified number of iterations |
| `--stop-on-error` | Stops if agent exits non-zero or times out |
| matching `<promise>...</promise>` tag detected | Stops early only when `stop_on_completion_signal: true` and the configured promise tag is found in agent output/result |

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

More patterns and real-world examples → [Cookbook](cookbook.md)

## Next steps

- [Getting Started](getting-started.md) — set up your first ralph end-to-end
- [How it Works](how-it-works.md) — what happens inside each iteration
- [Cookbook](cookbook.md) — copy-pasteable ralphs for common tasks
- [Troubleshooting](troubleshooting.md) — common issues and how to fix them
