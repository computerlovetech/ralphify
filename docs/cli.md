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
prompt = "PROMPT.md"
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | string | yes | The agent CLI executable to run |
| `args` | list of strings | no | Arguments passed to the command |
| `prompt` | string | yes | Path to a prompt file, or a [named prompt](primitives.md#prompts) name |

The assembled prompt is piped to the agent command as **stdin**. The full command executed each iteration is:

```
<command> <args...> < assembled_prompt
```

### Using a different agent

Ralphify works with any CLI that reads a prompt from stdin. To use a different agent, change the `command` and `args` fields:

```toml
# Claude Code (default)
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
```

```toml
# Any custom script that reads stdin
[agent]
command = "bash"
args = ["-c", "cat - | my-agent-wrapper"]
prompt = "PROMPT.md"
```

The only requirement is that the command reads the prompt from stdin and exits when done. See [Using with Different Agents](agents.md) for complete setup guides for popular agents and custom wrappers.

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
| `--help` | | Show help and exit |

### `ralph init`

Initialize a project with `ralph.toml` and `PROMPT.md`.

```bash
ralph init
ralph init --force   # Overwrite existing files
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--force` | `-f` | off | Overwrite existing `ralph.toml` and `PROMPT.md` |

During init, ralphify detects your project type by looking for manifest files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`). The detected type is displayed but doesn't currently change the generated configuration — all project types get the same defaults.

### `ralph run`

Start the autonomous coding loop.

```bash
ralph run                          # Run forever (Ctrl+C to stop)
ralph run docs                     # Use the "docs" named prompt
ralph run -n 5                     # Run 5 iterations
ralph run -p "Fix the login bug"   # Ad-hoc prompt (no PROMPT.md needed)
ralph run -f path/to/prompt.md     # Use a specific prompt file
ralph run --stop-on-error          # Stop if agent exits non-zero
ralph run --delay 10               # Wait 10s between iterations
ralph run --timeout 300            # Kill agent after 5 minutes per iteration
ralph run --log-dir ralph_logs     # Save output to log files
```

| Argument / Option | Short | Default | Description |
|---|---|---|---|
| `[PROMPT_NAME]` | | none | Name of a [named prompt](primitives.md#prompts) in `.ralph/prompts/` |
| `-n` | | unlimited | Max number of iterations |
| `--prompt` | `-p` | none | Ad-hoc prompt text. Overrides the prompt file |
| `--prompt-file` | `-f` | none | Path to a prompt file. Overrides `ralph.toml` |
| `--stop-on-error` | `-s` | off | Stop loop if agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds to wait between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration |
| `--log-dir` | `-l` | none | Directory for iteration log files |

Options can be combined:

```bash
ralph run -n 10 --timeout 300 --log-dir ralph_logs --stop-on-error
```

#### Ad-hoc prompts

Use `-p` to pass a prompt directly on the command line, bypassing the prompt file entirely:

```bash
ralph run -n 1 -p "Add type hints to all public functions in src/"
```

This is useful for quick one-off tasks where you don't want to create or edit a `PROMPT.md`. The ad-hoc prompt still supports placeholders — contexts and instructions resolve as normal:

```bash
ralph run -n 1 -p "{{ contexts.git-log }}\n\nFix the failing test."
```

When `-p` is provided, `PROMPT.md` doesn't need to exist.

### `ralph status`

Show current configuration, validate setup, and list all discovered primitives.

```bash
ralph status
```

This command checks:

- Whether the prompt file exists
- Whether the agent command is on PATH
- All discovered checks, contexts, and instructions (with enabled/disabled status)

If everything is configured correctly, it prints "Ready to run." If not, it tells you exactly what's wrong.

### `ralph prompts`

Manage named prompts.

#### `ralph prompts list`

List all available prompts — both the root `PROMPT.md` and any named prompts in `.ralph/prompts/`.

```bash
ralph prompts list
```

Output shows enabled status, name, and description for each prompt.

### `ralph ui`

Launch the web-based orchestration dashboard for managing multiple runs, watching iterations live, and editing primitives from your browser.

```bash
ralph ui                    # Default: http://127.0.0.1:8765
ralph ui --port 9000        # Custom port
ralph ui --host 0.0.0.0     # Expose on network
```

| Option | Default | Description |
|---|---|---|
| `--port` | `8765` | Port to serve the UI on |
| `--host` | `127.0.0.1` | Host to bind to |

Requires optional dependencies:

```bash
pip install ralphify[ui]    # Adds FastAPI, uvicorn, WebSocket support
```

See [Web Dashboard](dashboard.md) for a full walkthrough of the UI features and REST API.

### `ralph new`

Scaffold new primitives. Each command creates a directory under `.ralph/` with a template file.

```bash
ralph new check <name>         # Create .ralph/checks/<name>/CHECK.md
ralph new instruction <name>   # Create .ralph/instructions/<name>/INSTRUCTION.md
ralph new context <name>       # Create .ralph/contexts/<name>/CONTEXT.md
ralph new prompt <name>        # Create .ralph/prompts/<name>/PROMPT.md
```

The created template files include placeholder frontmatter and comments explaining how to configure each primitive. See [Primitives](primitives.md) for full details on each type.
