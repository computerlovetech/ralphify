---
description: Single-page cheat sheet for ralphify — all CLI commands, options, placeholder syntax, primitive formats, and key defaults.
---

# Quick Reference

Everything you need to look up on one page. For detailed explanations, follow the links to the relevant guide pages.

## `ralph.toml`

```toml
[agent]
command = "claude"                                # Agent CLI executable
args = ["-p", "--dangerously-skip-permissions"]   # Arguments passed to the command
prompt = "PROMPT.md"                              # Path to the prompt file
```

The assembled prompt is piped to the agent as stdin: `<command> <args...> < assembled_prompt`

See [Configuration & CLI](cli.md#ralphtoml) for details.

---

## CLI commands

| Command | Description |
|---|---|
| `ralph init` | Create `ralph.toml` and `PROMPT.md` |
| `ralph init --force` | Overwrite existing files |
| `ralph run` | Start the loop (Ctrl+C to stop) |
| `ralph status` | Validate setup and list primitives |
| `ralph new check <name>` | Scaffold a new check |
| `ralph new context <name>` | Scaffold a new context |
| `ralph new instruction <name>` | Scaffold a new instruction |

### `ralph run` options

| Option | Short | Default | Description |
|---|---|---|---|
| `-n` | | unlimited | Max iterations |
| `--stop-on-error` | `-s` | off | Stop if agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration |
| `--log-dir` | `-l` | none | Directory for iteration log files |

```bash
# Common combinations
ralph run -n 1 --log-dir ralph_logs         # Single test iteration
ralph run -n 5 --stop-on-error              # Short batch, stop on failure
ralph run --timeout 300 --log-dir ralph_logs # Production run with safety net
```

---

## Template placeholders

Use these in `PROMPT.md` to control where contexts and instructions appear.

| Placeholder | What it does |
|---|---|
| `{{ contexts.name }}` | Insert a specific context by directory name |
| `{{ contexts }}` | Insert all remaining contexts (not already placed by name) |
| `{{ instructions.name }}` | Insert a specific instruction by directory name |
| `{{ instructions }}` | Insert all remaining instructions (not already placed by name) |

### Resolution rules

| Prompt contains | Behavior |
|---|---|
| Named only (`{{ contexts.x }}`) | Named content placed inline; **other contexts are dropped** |
| Bulk only (`{{ contexts }}`) | All enabled contexts placed at that location |
| Both named and bulk | Named placed inline, remaining go to bulk location |
| Neither | All content appended to end of prompt |

Same rules apply for `{{ instructions }}`.

!!! warning "Named-only drops remaining"
    If you use `{{ contexts.git-log }}` without `{{ contexts }}`, other contexts are silently excluded. Add `{{ contexts }}` to catch the rest.

See [Writing Your Prompt](prompts.md#using-placeholders) and [Placeholder resolution rules](how-it-works.md#placeholder-resolution-rules).

---

## Primitives

All primitives live under `.ralph/` and are discovered automatically at startup.

### Checks

Run **after** each iteration. Failures feed into the next prompt.

**Location:** `.ralph/checks/<name>/CHECK.md`

```markdown
---
command: uv run pytest -x    # Command to run (or use a run.* script)
timeout: 60                  # Seconds before kill (default: 60)
enabled: true                # Set false to skip (default: true)
---
Failure instruction text goes here — included in prompt when check fails.
```

### Contexts

Run **before** each iteration. Output injected into the prompt.

**Location:** `.ralph/contexts/<name>/CONTEXT.md`

```markdown
---
command: git log --oneline -10   # Command whose stdout is captured (optional)
timeout: 30                      # Seconds before kill (default: 30)
enabled: true                    # Set false to skip (default: true)
---
Static content appears above command output. Omit command for static-only.
```

### Instructions

Static text injected into the prompt. No commands.

**Location:** `.ralph/instructions/<name>/INSTRUCTION.md`

```markdown
---
enabled: true   # Set false to skip (default: true)
---
Instruction content goes here — injected via {{ instructions.name }} or {{ instructions }}.
```

### Script alternative

Any check or context can use an executable `run.*` script instead of a frontmatter `command`:

```
.ralph/checks/my-check/
├── CHECK.md       # Frontmatter + failure instruction
└── run.sh         # Executable script (takes precedence over command)
```

Scripts run with the **project root** as the working directory. Make them executable with `chmod +x`.

See [Primitives](primitives.md) for full details.

---

## Directory structure

```
your-project/
├── ralph.toml                 # Loop configuration
├── PROMPT.md                  # Prompt file (re-read every iteration)
├── .ralph/
│   ├── checks/
│   │   └── <name>/CHECK.md
│   ├── contexts/
│   │   └── <name>/CONTEXT.md
│   └── instructions/
│       └── <name>/INSTRUCTION.md
└── ralph_logs/                # Iteration logs (add to .gitignore)
```

---

## Key defaults

| Setting | Default |
|---|---|
| Check timeout | 60 seconds |
| Context timeout | 30 seconds |
| Output truncation | 5,000 characters per check/context |
| Iteration limit | Unlimited (Ctrl+C to stop) |
| Delay between iterations | 0 seconds |

---

## Command parsing

Frontmatter `command` values are split with `shlex` and run **directly** (no shell). This means:

- Simple commands work: `uv run pytest -x`, `npm test`
- **No** pipes (`|`), redirections (`2>&1`), chaining (`&&`), or variable expansion (`$VAR`)
- Need shell features? Use a `run.sh` script instead

---

## What's re-read vs. fixed at startup

| What | When loaded | Editable while running? |
|---|---|---|
| `PROMPT.md` | Every iteration | Yes |
| Context command output | Every iteration | Yes (commands re-run) |
| Context/instruction config | Startup only | No — restart required |
| Check config | Startup only | No — restart required |
| New/removed primitives | Startup only | No — restart required |

---

## Prompt assembly order

Each iteration assembles the prompt in this order:

1. Read `PROMPT.md` from disk
2. Run context commands and resolve `{{ contexts }}` placeholders
3. Resolve `{{ instructions }}` placeholders
4. Append check failures from previous iteration (if any)
5. Pipe result to agent as stdin
