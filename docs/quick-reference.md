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
| `ralph run <prompt-name>` | Start the loop with a [named prompt](primitives.md#prompts) |
| `ralph status` | Validate setup and list primitives |
| `ralph prompts list` | List all available prompts |
| `ralph new check <name>` | Scaffold a new check |
| `ralph new context <name>` | Scaffold a new context |
| `ralph new instruction <name>` | Scaffold a new instruction |
| `ralph new prompt <name>` | Scaffold a new named prompt |
| `ralph new check <name> --prompt <prompt>` | Scaffold a [prompt-scoped](primitives.md#prompt-scoped-primitives) check |
| `ralph ui` | Launch the [web dashboard](dashboard.md) |
| `ralph ui --port 9000` | Dashboard on a custom port |
| `ralph ui --host 0.0.0.0` | Expose dashboard on network |
| `ralph --install-completion` | Install [shell tab completion](cli.md#shell-completion) |

### `ralph run` options

| Argument / Option | Short | Default | Description |
|---|---|---|---|
| `[PROMPT_NAME]` | | none | Name of a named prompt in `.ralph/prompts/` |
| `-n` | | unlimited | Max iterations |
| `--prompt` | `-p` | none | Ad-hoc prompt text (overrides prompt file) |
| `--prompt-file` | `-f` | none | Path to a prompt file (overrides `ralph.toml`) |
| `--stop-on-error` | `-s` | off | Stop if agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration |
| `--log-dir` | `-l` | none | Directory for iteration log files |

```bash
# Common combinations
ralph run docs                              # Use the "docs" named prompt
ralph run -n 1 --log-dir ralph_logs         # Single test iteration
ralph run -n 1 -p "Fix the login bug"       # Quick one-off task
ralph run -n 5 --stop-on-error              # Short batch, stop on failure
ralph run --timeout 300 --log-dir ralph_logs # Production run with safety net
```

### Prompt source priority

When multiple prompt sources are specified, the first match wins:

| Priority | Source | Example |
|---|---|---|
| 1 | `-p` flag (inline text) | `ralph run -p "Fix the bug"` |
| 2 | Positional name | `ralph run docs` |
| 3 | `-f` flag (file path) | `ralph run -f path/to/prompt.md` |
| 4 | `ralph.toml` `prompt` field | Can be a named prompt or a file path |
| 5 | Fallback | `PROMPT.md` in the project root |

See [How It Works — Prompt assembly](how-it-works.md#prompt-assembly) for details.

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

### Prompts

Reusable task-focused prompts. Switch between tasks without editing root `PROMPT.md`.

**Location:** `.ralph/prompts/<name>/PROMPT.md`

```markdown
---
description: Improve project documentation   # Shown in `ralph prompts list`
enabled: true                                 # Set false to hide (default: true)
---
Your full prompt content here, with {{ contexts }} and {{ instructions }} as usual.
```

```bash
ralph run docs        # Run with the "docs" prompt
ralph prompts list    # See all available prompts
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
├── PROMPT.md                  # Root prompt file (re-read every iteration)
├── .ralph/
│   ├── checks/
│   │   └── <name>/CHECK.md
│   ├── contexts/
│   │   └── <name>/CONTEXT.md
│   ├── instructions/
│   │   └── <name>/INSTRUCTION.md
│   └── prompts/
│       └── <name>/PROMPT.md   # Named prompts (ralph run <name>)
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

## Dashboard keyboard shortcuts

| Shortcut | Where | Action |
|---|---|---|
| <kbd>Cmd+S</kbd> / <kbd>Ctrl+S</kbd> | Primitive editor | Save changes |
| <kbd>Cmd+S</kbd> / <kbd>Ctrl+S</kbd> | Create primitive form | Create the primitive |
| <kbd>Escape</kbd> | New Run modal | Close the modal |

See [Web Dashboard](dashboard.md#keyboard-shortcuts) for details.

---

## Prompt assembly order

Each iteration assembles the prompt in this order:

1. Read prompt (from `PROMPT.md`, or from `-p` flag if provided)
2. Run context commands and resolve `{{ contexts }}` placeholders
3. Resolve `{{ instructions }}` placeholders
4. Append check failures from previous iteration (if any)
5. Pipe result to agent as stdin
