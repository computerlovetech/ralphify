---
title: "CLI Reference: Run AI Coding Agents in Autonomous Loops"
description: "Complete CLI reference for the ralph command — run autonomous AI coding loops, scaffold new agent prompts, and configure RALPH.md frontmatter options."
keywords: run AI agent in loop CLI, autonomous coding agent command line, ralph run command, ralph scaffold, RALPH.md frontmatter format, AI coding loop options, agent timeout iterations, user arguments CLI, ralphify CLI reference
---

# CLI Reference

!!! tldr "TL;DR"
    **`ralph run <path> -n 5`** runs the loop. **`ralph scaffold <name>`** creates a ralph from a template. Pass user args as `--name value` flags. Everything is configured in a single [`RALPH.md`](#ralphmd-format) file with YAML frontmatter.

## `ralph`

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

---

## `ralph run`

Start the [autonomous coding loop](how-it-works.md).

```bash
ralph run my-ralph                         # Run forever (Ctrl+C to stop)
ralph run my-ralph -n 5                    # Run 5 iterations
ralph run my-ralph --stop-on-error         # Stop if agent exits non-zero or times out
ralph run my-ralph --delay 10              # Wait 10s between iterations
ralph run my-ralph --timeout 300           # Kill agent after 5 minutes per iteration
ralph run my-ralph --log-dir ralph_logs    # Save output to log files
ralph run my-ralph --dir ./src             # Pass user args to the ralph
```

| Argument / Option | Short | Default | Description |
|---|---|---|---|
| `PATH` | | (required) | Path to a ralph directory containing `RALPH.md`, a direct path to a `RALPH.md` file, or the name of an installed ralph in `.agents/ralphs/` |
| `-n` | | unlimited | Max number of iterations |
| `--stop-on-error` | `-s` | off | Stop loop if agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds to wait between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration |
| `--log-dir` | `-l` | none | Directory for iteration log files |

### User arguments

User arguments are passed as named flags after the ralph path. Use `{{ args.<name> }}` [placeholders](how-it-works.md#3-resolve-placeholders-with-command-output) in your RALPH.md to reference them.

Named flags (`--name value`) work without any frontmatter declaration. The `args` field is only required when you want to pass **positional** arguments — it tells ralphify which names to map them to:

```markdown
---
agent: claude -p --dangerously-skip-permissions
args: [dir, focus]
---

Research the codebase at {{ args.dir }}.
Focus area: {{ args.focus }}
```

```bash
# Named flags (work with or without args declared in frontmatter)
ralph run research --dir ./my-project --focus "performance"

# Equals syntax works too
ralph run research --dir=./my-project --focus="performance"

# Positional args (requires args: [dir, focus] in frontmatter)
ralph run research ./my-project "performance"

# Mixed — positional args skip names already provided via flags
ralph run research --focus "performance" ./my-project
# dir="./my-project", focus="performance"

# -- ends flag parsing — everything after is positional
ralph run research -- --verbose ./src
# dir="--verbose", focus="./src"
```

Use `--` when a positional value starts with `--` and would otherwise be parsed as a flag.

Missing args resolve to an empty string.

### Stopping the loop

Press `Ctrl+C` to stop the loop. Ralphify uses two-stage signal handling:

| Action | Behavior |
|---|---|
| `Ctrl+C` (first) | Finishes the current iteration gracefully, then stops the loop |
| `Ctrl+C` (second) | Force-kills the agent process and exits immediately |

The first press lets the agent complete its current work (e.g. finish a commit). If you don't want to wait, press `Ctrl+C` again to terminate immediately.

The loop also stops automatically when:

- All `-n` iterations have completed
- `--stop-on-error` is set and the agent exits non-zero or times out
- `stop_on_completion_signal: true` is set in frontmatter and the matching `<promise>...</promise>` tag is detected in agent output or captured result text

### Peeking at live agent output

When you run `ralph run` in an interactive terminal, the agent's stdout and stderr stream live to the console by default. Press `p` to silence the stream (useful for quieter loops) and press `p` again to resume it. The default is off whenever the output is not a real terminal (piped, redirected, or captured in CI), so `ralph run ... | cat` is unaffected.

The compact peek panel shows the ten most recent activity lines to keep the terminal tidy. When you need to see earlier activity from the current iteration, press **shift+P** to enter **full-screen peek** — a scrollable view of the entire buffer that takes over the terminal on the alt screen.

Inside full-screen peek:

| Key | Action |
|-----|--------|
| `j` / `k` | Scroll one line down / up |
| `space` / `b` | Page down / page up |
| `g` / `G` | Jump to the top / bottom (bottom re-enables follow mode) |
| `q` or `P` | Exit back to the compact view |

Activity keeps streaming into the buffer while you scroll, so follow mode (`G` or scrolling back to the bottom) catches up to the tail. The full-screen view exits automatically when the iteration ends, returning you to the normal terminal.

Live streaming works with line-buffered agents such as Claude Code, OpenAI Codex, Aider, and any other process that writes one line at a time. For Claude running in stream-json mode you'll see the raw JSON events; for other agents you'll see the agent's plain output. Agents that repaint their own terminal UI (full-screen curses or TUI apps) are not supported — ralphify pipes their stdio, so they detect a non-TTY and fall back to plain output.

When `--log-dir` is set, output is captured to the log file and also echoed after each iteration completes; live peek still works the same way in that mode.

Some runtimes block-buffer their stdout when it is piped, which can make lines appear in bursts rather than as they are produced. If you notice stuttering, set `PYTHONUNBUFFERED=1` (or the equivalent for your agent) in the environment where you launch `ralph`.

---

## `ralph scaffold`

Scaffold a new ralph with a ready-to-customize template.

```bash
ralph scaffold my-task      # Creates my-task/RALPH.md with a generic template
ralph scaffold              # Creates RALPH.md in the current directory
```

| Argument | Default | Description |
|---|---|---|
| `[NAME]` | none | Directory name. If omitted, creates RALPH.md in the current directory |

The generated template includes an example command (`git-log`), an example arg (`focus`), a prompt body with placeholders for both, and commented `completion_signal` / `stop_on_completion_signal` lines showing the promise-completion path. Uncomment them if you want the agent to stop early by emitting a matching `<promise>...</promise>` tag. Then run [`ralph run`](#ralph-run). See [Getting Started](getting-started.md) for a full walkthrough.

Errors if `RALPH.md` already exists at the target location.

---

## RALPH.md format

The `RALPH.md` file is the single configuration and prompt file for a ralph. It uses YAML frontmatter for settings and the body for the prompt text.

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
  - name: git-log
    run: git log --oneline -10
args: [dir, focus]
---

# Prompt body

{{ commands.tests }}

{{ commands.git-log }}

Your instructions here. Reference args with {{ args.dir }}.
```

### Frontmatter fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | The full agent command to pipe the prompt to |
| `commands` | list | no | Commands to run each iteration (each has `name` and `run`) |
| `args` | list of strings | no | Declared argument names for user arguments. Letters, digits, hyphens, and underscores only. |
| `credit` | bool | no | Append co-author trailer instruction to prompt (default: `true`) |
| `completion_signal` | string | no | Inner text for the completion promise tag. `COMPLETE` means the agent must emit `<promise>COMPLETE</promise>` (default inner text: `RALPH_PROMISE_COMPLETE`) |
| `stop_on_completion_signal` | bool | no | Stop the loop early when the matching `<promise>...</promise>` tag is detected (default: `false`) |

Exit code `0` still only means the agent process succeeded. Ralphify keeps its own loop architecture; only the promise tag format and matching align with Ralph-Wiggum.

### Commands

Each command has these fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Identifier used in `{{ commands.<name> }}` placeholders. Letters, digits, hyphens, and underscores only. |
| `run` | string | (required) | Shell command to execute each iteration (supports `{{ args.<name> }}` placeholders). Commands starting with `./` run from the ralph directory; others run from the project root. |
| `timeout` | number | `60` | Max seconds before the command is killed |

Commands run in order. Output (stdout + stderr) is captured regardless of exit code. Commands are parsed with `shlex.split()` — no shell features (pipes, redirections, `&&`). For shell features, point the `run` field at a script. See the [Cookbook](cookbook.md) for real-world command patterns.

If a command exceeds its timeout, the process is killed and the captured output up to that point is used.

### Placeholders

| Syntax | Resolves to |
|---|---|
| `{{ commands.<name> }}` | Output of the named command |
| `{{ args.<name> }}` | Value of the named user argument |
| `{{ ralph.name }}` | ralph directory name (e.g. `my-ralph`) |
| `{{ ralph.iteration }}` | Current iteration number (1-based) |
| `{{ ralph.max_iterations }}` | Total iterations if `-n` was set, empty otherwise |

`ralph.*` placeholders are automatically available — no frontmatter configuration needed.

Unmatched placeholders resolve to an empty string.

---

## Next steps

- [How it Works](how-it-works.md) — what happens inside each iteration
- [Quick Reference](quick-reference.md) — condensed cheat sheet for daily use
- [Python API](api.md) — run loops programmatically instead of via the CLI
