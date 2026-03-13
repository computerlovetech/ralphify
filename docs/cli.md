---
description: ralph.toml configuration format, all CLI commands (init, run, status, new), and every option with defaults and examples.
---

# Configuration & CLI Reference

## `ralph.toml`

The `ralph.toml` file configures how ralphify runs your agent. It's created by `ralph init` and lives in your project root.

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | string | yes | The agent CLI executable to run |
| `args` | list of strings | no | Arguments passed to the command |
| `ralph` | string | yes | Path to a ralph file, or a [named ralph](primitives.md#ralphs) name |

The assembled prompt is piped to the agent command as **stdin**. The full command executed each iteration is:

```
<command> <args...> < assembled_prompt
```

See [Using with Different Agents](agents.md) for setup guides for other agents.

---

## CLI Commands

### `ralph`

With no subcommand, prints the banner and help text.

```bash
ralph            # Show banner and help
ralph --version  # Show version
ralph --help     # Show help
```

| Option | Short | Description |
|---|---|---|
| `--version` | `-V` | Show version and exit |
| `--install-completion` | | Install tab completion for your current shell |
| `--show-completion` | | Print the completion script (for manual setup) |
| `--help` | | Show help and exit |

### Shell completion

```bash
ralph --install-completion bash   # or zsh, fish
```

Restart your shell after installing. Use `--show-completion` to print the script for manual setup.

### `ralph init`

Initialize a project with `ralph.toml` and `RALPH.md`.

```bash
ralph init
ralph init --force   # Overwrite existing files
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--force` | `-f` | off | Overwrite existing `ralph.toml` and `RALPH.md` |

During init, ralphify detects your project type by looking for manifest files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`). The detected type is displayed but doesn't currently change the generated configuration — all project types get the same defaults.

### `ralph run`

Start the autonomous coding loop.

```bash
ralph run                          # Run forever (Ctrl+C to stop)
ralph run docs                     # Use the "docs" named ralph
ralph run -n 5                     # Run 5 iterations
ralph run -p "Fix the login bug"   # Ad-hoc prompt (no RALPH.md needed)
ralph run -f path/to/prompt.md     # Use a specific prompt file
ralph run --stop-on-error          # Stop if agent exits non-zero
ralph run --delay 10               # Wait 10s between iterations
ralph run --timeout 300            # Kill agent after 5 minutes per iteration
ralph run --log-dir ralph_logs     # Save output to log files
```

| Argument / Option | Short | Default | Description |
|---|---|---|---|
| `[RALPH_NAME]` | | none | Name of a [named ralph](primitives.md#ralphs) in `.ralphify/ralphs/` |
| `-n` | | unlimited | Max number of iterations |
| `--prompt` | `-p` | none | Ad-hoc prompt text. Overrides the ralph file |
| `--ralph-file` | `-f` | none | Path to a ralph file. Overrides `ralph.toml` |
| `--stop-on-error` | `-s` | off | Stop loop if agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds to wait between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration |
| `--log-dir` | `-l` | none | Directory for iteration log files |

Ad-hoc prompts (`-p`) still resolve context and instruction placeholders. When `-p` is provided, `RALPH.md` doesn't need to exist.

### `ralph status`

Show current configuration, validate setup, and list all discovered primitives.

```bash
ralph status
```

This command checks:

- Whether the prompt file exists
- Whether the agent command is on PATH
- All discovered checks, contexts, instructions, and named ralphs (with enabled/disabled status)

If everything is configured correctly, it prints "Ready to run." If not, it tells you exactly what's wrong.

### `ralph new`

Scaffold new primitives. Each command creates a directory under `.ralphify/` with a template file.

```bash
ralph new check <name>         # Create .ralphify/checks/<name>/CHECK.md
ralph new instruction <name>   # Create .ralphify/instructions/<name>/INSTRUCTION.md
ralph new context <name>       # Create .ralphify/contexts/<name>/CONTEXT.md
ralph new ralph <name>         # Create .ralphify/ralphs/<name>/RALPH.md
```

#### Ralph-scoped primitives

Checks, contexts, and instructions accept a `--ralph` option to create them inside a named ralph's directory. These [ralph-scoped primitives](primitives.md#ralph-scoped-primitives) only apply when running that specific ralph.

```bash
ralph new check docs-build --ralph docs        # .ralphify/ralphs/docs/checks/docs-build/CHECK.md
ralph new context doc-coverage --ralph docs     # .ralphify/ralphs/docs/contexts/doc-coverage/CONTEXT.md
ralph new instruction writing-style --ralph docs  # .ralphify/ralphs/docs/instructions/writing-style/INSTRUCTION.md
```

| Option | Description |
|---|---|
| `--ralph` | Name of a ralph in `.ralphify/ralphs/` to scope this primitive to |

The created template files include placeholder frontmatter and comments explaining how to configure each primitive. See [Primitives](primitives.md) for full details on each type.
