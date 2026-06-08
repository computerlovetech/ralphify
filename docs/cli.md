---
title: Reference — Ralphify CLI, RALPH.md, the loop, agents & Python API
description: Complete ralphify reference — the ralph CLI commands, RALPH.md frontmatter format, how each loop iteration works, configuring different agents, troubleshooting, and the Python API.
keywords: loop engineering, ralph CLI reference, RALPH.md format, ralph run, ralph scaffold, ralph loops format, how loop engineering works, run claude code in loop, ralphify python api, ralphify troubleshooting
---

# Reference

Everything beyond [the basics](index.md#what-you-do-with-ralphify) lives here: the CLI, the `RALPH.md` format, how a loop iteration works under the hood, how to wire up different agents, troubleshooting, and the Python API.

`ralph run <path> -n 5` runs the loop. `ralph scaffold <name>` creates a ralph from a template. Pass user args as `--name value` flags. Everything is configured in a single [`RALPH.md`](#ralphmd-format) file with YAML frontmatter.

---

## CLI

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

Install shell completion with `ralph --install-completion bash` (or `zsh`, `fish`), then restart your shell.

### `ralph run`

Start the loop.

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

#### User arguments

User arguments are passed as named flags after the ralph path. Use `{{ args.<name> }}` [placeholders](#placeholders) in your RALPH.md to reference them.

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

Use `--` when a positional value starts with `--` and would otherwise be parsed as a flag. Missing args resolve to an empty string.

#### Stopping the loop

Press `Ctrl+C` to stop. Ralphify uses two-stage signal handling:

| Action | Behavior |
|---|---|
| `Ctrl+C` (first) | Finishes the current iteration gracefully, then stops the loop |
| `Ctrl+C` (second) | Force-kills the agent process and exits immediately |

The loop also stops automatically when all `-n` iterations have completed, or when `--stop-on-error` is set and the agent exits non-zero or times out.

#### Peeking at live agent output

When you run `ralph run` in an interactive terminal, the agent's stdout and stderr stream live to the console by default. Press `p` to silence the stream and `p` again to resume it. The default is off whenever the output is not a real terminal (piped, redirected, or captured in CI), so `ralph run ... | cat` is unaffected.

The compact peek panel shows the ten most recent activity lines. Press **shift+P** to enter **full-screen peek**, a scrollable view of the entire buffer:

| Key | Action |
|-----|--------|
| `j` / `k` | Scroll one line down / up |
| `space` / `b` | Page down / page up |
| `g` / `G` | Jump to the top / bottom (bottom re-enables follow mode) |
| `[` / `]` | Browse to the previous / next iteration |
| `q` or `P` | Exit back to the compact view |

Live streaming works with line-buffered agents such as Claude Code, OpenAI Codex, and Aider. Agents that repaint their own terminal UI (full-screen curses or TUI apps) are not supported — ralphify pipes their stdio, so they detect a non-TTY and fall back to plain output. If lines appear in bursts rather than as produced, set `PYTHONUNBUFFERED=1` (or the equivalent) in the environment where you launch `ralph`.

### `ralph scaffold`

Scaffold a new ralph with a ready-to-customize template.

```bash
ralph scaffold my-task      # Creates my-task/RALPH.md with a template
ralph scaffold              # Creates RALPH.md in the current directory
```

The generated template includes an example command (`git-log`), an example arg (`focus`), and a prompt body with placeholders for both. Errors if `RALPH.md` already exists at the target location. See [Getting Started](getting-started.md) for a full walkthrough.

---

## RALPH.md format

The `RALPH.md` file is the single configuration and prompt file for a ralph — the shape is defined by the open [ralph loops format](https://ralphloops.io/). It uses YAML frontmatter for settings and the body for the prompt text.

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

### Commands

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Identifier used in `{{ commands.<name> }}` placeholders. Letters, digits, hyphens, and underscores only. |
| `run` | string | (required) | Shell command to execute each iteration (supports `{{ args.<name> }}` placeholders). Commands starting with `./` run from the ralph directory; others run from the project root. |
| `timeout` | number | `60` | Max seconds before the command is killed |

Commands run in order. Output (stdout + stderr) is captured regardless of exit code.

Commands are parsed with `shlex.split()` and run directly, not through a shell — pipes (`|`), redirections (`>`), and chaining (`&&`) won't work in the `run` field. Point the `run` field at a script instead: `run: ./my-script.sh`.

### Placeholders

| Syntax | Resolves to |
|---|---|
| `{{ commands.<name> }}` | Output of the named command |
| `{{ args.<name> }}` | Value of the named user argument |
| `{{ ralph.name }}` | ralph directory name (e.g. `my-ralph`) |
| `{{ ralph.iteration }}` | Current iteration number (1-based) |
| `{{ ralph.max_iterations }}` | Total iterations if `-n` was set, empty otherwise |

`ralph.*` placeholders are automatically available — no frontmatter configuration needed. **Only commands referenced by a placeholder appear in the prompt** — an unreferenced command still runs each iteration, but its output is excluded. Unmatched placeholders resolve to an empty string.

---

## How the loop works

This is the lifecycle of one iteration — the format you write, and the runtime that runs it.

### The six steps of each iteration

1. **Re-read the prompt from disk.** The prompt body (everything below the frontmatter) is read **every iteration**, so you can edit the prompt — add rules, change the task — while the loop runs. Frontmatter (`agent`, `commands`, `args`) is parsed once at startup; restart to change it.
2. **Run commands and capture output.** Each command runs in order and captures stdout + stderr **regardless of exit code** — a `pytest -x` that exits non-zero is exactly what you want in the prompt. Commands run from the project root by default; commands starting with `./` run from the ralph directory. Each has a 60s default timeout (override with `timeout`).
3. **Resolve placeholders.** `{{ commands.<name> }}`, `{{ args.<name> }}`, and `{{ ralph.* }}` are replaced with their values. `{{ args.* }}` is resolved both in the prompt body and in command `run` strings.
4. **Assemble the final prompt.** The resolved body becomes a single text string. HTML comments (`<!-- ... -->`) are stripped — use them for notes to yourself. By default a **co-author trailer instruction** is appended asking the agent to add `Co-authored-by: Ralphify <noreply@ralphify.co>` to commits; disable with `credit: false`.
5. **Pipe the prompt to the agent** via stdin (`echo "<prompt>" | claude -p ...`). The agent works in the current directory and exits; ralphify waits. When the agent command starts with `claude`, ralphify automatically adds `--output-format stream-json --verbose` for structured streaming.
6. **Loop back with fresh context.** The next iteration starts from step 1 with a clean context window and fresh command output.

### What gets re-read vs. what stays fixed

| What | When read | Why it matters |
|---|---|---|
| Prompt body | Every iteration | Edit the prompt while the loop runs — the next iteration follows your new instructions |
| Command output | Every iteration | The agent always sees fresh data (latest git log, current test status, etc.) |
| Frontmatter (`agent`, `commands`, `args`) | Once at startup | Restart to pick up changes |
| User arguments | Once at startup | Passed via CLI flags, constant for the run |

### The self-healing feedback loop

When iteration 1 breaks a test, iteration 2's `{{ commands.tests }}` shows the failure:

```markdown
## Test results

FAILED tests/test_auth.py::test_login - AssertionError: expected 200, got 401
============================= 1 failed, 4 passed in 1.45s ====================

If tests are failing, fix them before starting new work.
```

The agent sees the failure and the instruction to fix it first. That's the self-healing loop: the agent breaks something, the command captures the failure, the agent fixes it next iteration.

---

## Using different agents

Ralphify works with **any CLI that reads a prompt from stdin and exits when done**. Every iteration, ralphify runs `echo "<assembled prompt>" | <agent command>`. Your agent must read the prompt from stdin, do work in the current directory, and exit (0 = success, non-zero = failure).

| Agent | Stdin support | Streaming | Wrapper needed |
|---|---|---|---|
| [Claude Code](#claude-code) | Native (`-p`) | Yes — real-time activity tracking | No |
| [Aider](#aider) | Via bash wrapper | No | Yes (`bash -c`) |
| [Codex CLI](#codex-cli) | Native (`exec`) | No | No |
| [Custom](#custom-wrapper-script) | You implement it | No | Yes (script) |

If you're not sure: **start with Claude Code.** It's the default and has the deepest integration.

### Claude Code

```markdown
---
agent: claude -p --dangerously-skip-permissions
---
```

`-p` enables non-interactive mode (reads prompt from stdin, prints output, exits). `--dangerously-skip-permissions` skips approval prompts so the agent works autonomously — without it, the agent would hang forever waiting for approval that nobody is there to give. Install with `npm install -g @anthropic-ai/claude-code`. When the command starts with `claude`, ralphify automatically adds `--output-format stream-json --verbose` for activity tracking and result-text extraction.

### Aider

[Aider](https://aider.chat) doesn't natively read prompts from stdin, so wrap it with `bash -c` and `cat -`:

```markdown
---
agent: bash -c 'aider --yes-always --no-auto-commits --message "$(cat -)"'
---
```

`--yes-always` auto-approves changes; `--no-auto-commits` lets your prompt control commits. Add `--model claude-sonnet-4-6` (or another) to pick a model.

### Codex CLI

[OpenAI Codex CLI](https://github.com/openai/codex) supports non-interactive use natively:

```markdown
---
agent: codex exec --sandbox danger-full-access -
---
```

`exec` is non-interactive mode, `--sandbox danger-full-access` grants full filesystem access, and `-` reads the prompt from stdin.

### Custom wrapper script

For anything else, write a script that reads stdin and calls your agent:

```bash
#!/bin/bash
set -e
PROMPT=$(cat -)
my-custom-agent --input "$PROMPT" --auto-approve
```

```markdown
---
agent: ./ralph-agent.sh
---
```

The general pattern for tools that accept a prompt via a flag is `bash -c '<tool> <auto-approve-flag> --message "$(cat -)"'`. Test any agent outside ralphify first (`echo "Say hello" | <agent command>`), then through ralphify with `ralph run my-ralph -n 1 --log-dir ralph_logs`.

---

## Examples

The [`examples/`](https://github.com/computerlovetech/ralphify/tree/main/examples) directory in the repo has real, runnable ralph loops you can copy: autonomous ML research, test coverage, bug hunting, deep research, code migration, security scanning, documentation, and continuous codebase improvement. Each is a `RALPH.md` (some with helper scripts) you can adapt by swapping the task and commands.

---

## Troubleshooting

A quick checklist before digging in:

1. Run `ralph run my-ralph -n 1` — it validates your setup and shows clear errors
2. Test the agent outside ralphify: `echo "Say hello" | claude -p`
3. Use `--log-dir ralph_logs` to capture output for debugging
4. Commands don't support shell features (pipes, `&&`) — use a wrapper script instead

### Setup

- **"is not a directory, RALPH.md file, or installed ralph"** — the path doesn't resolve to a valid ralph. `ralph run` accepts a directory containing `RALPH.md`, a direct path to a `RALPH.md` file, or the name of an installed ralph in `.agents/ralphs/`. Check the path exists.
- **"Missing or empty 'agent' field"** — add `agent: claude -p --dangerously-skip-permissions` to your frontmatter.
- **"Agent command 'claude' not found on PATH"** — the agent CLI isn't installed or isn't on your PATH. Verify with `claude --version`.

### Loop behavior

- **Agent hangs or produces no output** — run the agent directly (`echo "Say hello" | claude -p`). If it hangs there, the issue is the agent CLI. If it works standalone, add `--timeout 300` to kill stalled iterations.
- **Agent exits non-zero every iteration** — capture output with `ralph run my-ralph -n 1 --log-dir ralph_logs` and read the log. Common causes: missing agent auth, a prompt asking for a failing command, or a too-large prompt exceeding the context window.
- **Agent runs but doesn't commit** — ralphify doesn't commit for the agent. Add explicit commit instructions to your prompt and ensure the agent has git permission (`--dangerously-skip-permissions` for Claude Code).
- **Loop runs too fast / no useful work** — the prompt is likely too vague or has no concrete task source. Tell the agent it's in a loop with no memory, and point it at `TODO.md`, `PLAN.md`, or failing tests.
- **Output not streaming** — press `p` to toggle live peek (you may have silenced it). Streaming is disabled in non-TTY environments (piped/CI) by design; use `--log-dir`. If output appears in bursts, set `PYTHONUNBUFFERED=1`.

### Frontmatter errors

- **"Invalid YAML in frontmatter"** — usually a missing colon, bad indentation, or an unquoted special character (`:`, `#`, `{`, `[`). Wrap risky values in quotes.
- **"Frontmatter must be a YAML mapping"** — frontmatter must be `key: value` pairs, not a bare string or list.
- **"Each command must have 'name' and 'run' fields"** — every command needs both `name` and `run`, each a non-empty string.
- **"Malformed 'agent' field"** — usually an unmatched quote in the `agent` value.
- **"'credit' must be true or false"** — `credit` accepts only YAML booleans (`true`/`false`), not `"yes"` or `0`.
- **"... name contains invalid characters"** — command and arg names may only contain letters, digits, hyphens, and underscores.
- **"Duplicate arg name" / "Duplicate command name"** — names must be unique within a `RALPH.md`.
- **"'commands' must be a list" / "'args' must be a list of strings"** — use list syntax (`args: [focus]`; `commands:` as a list of `{name, run}` mappings). Quote `args` items that look like numbers or booleans.
- **"Command '...' has invalid timeout"** — `timeout` must be a positive number of seconds.

### Argument errors

- **"Positional argument '...' requires args declared in frontmatter"** — either add an `args` field, or use `--name value` flag syntax (which works without declaration).
- **"Too many positional arguments"** — you passed more positional values than the `args` field declares.
- **"Flag '--...' requires a value"** — a `--name` flag was passed without a value.

### Command errors

- **"Command '...' has invalid syntax"** — malformed shell syntax in `run`, usually an unmatched quote. Point it at a script for complex quoting.
- **"Command '...' binary not found"** — the binary isn't installed or on PATH. If it's in a virtualenv, prefix with `uv run`.
- **Pipes or redirections not working** — `run` is parsed with `shlex` and run directly, so `|`, `2>&1`, `&&`, and `$VAR` won't work. Wrap them in a `.sh` script and point the command at it.
- **Output looks truncated** — the command hit its 60s timeout. Increase it (`timeout: 300`) or speed up the command.
- **Command output missing from prompt** — check the placeholder name matches the command `name` exactly, that the command produces output, and that you used `commands` (plural).

### Common questions

- **Run multiple loops in parallel?** Yes, on **separate branches** to avoid git conflicts (`git checkout -b feature-a && ralph run ...`). For programmatic control, use the Python [`RunManager`](#concurrent-runs-with-runmanager).
- **What to commit?** Commit `RALPH.md` and any helper `*.sh` scripts. Add `ralph_logs/` to `.gitignore`.
- **Edit RALPH.md while running?** Yes — the prompt body is re-read each iteration. Frontmatter needs a restart.
- **Disable the co-author credit?** Set `credit: false` in frontmatter.

If your problem isn't here, run `ralph run my-ralph -n 1` to validate, capture a run with `--log-dir`, or file an issue at [github.com/computerlovetech/ralphify](https://github.com/computerlovetech/ralphify/issues).

---

## Python API

All public API is available from the top-level `ralphify` package. It runs the same loop as the CLI, so everything you can do with `ralph run` you can do from Python.

```python
from pathlib import Path
from ralphify import run_loop, RunConfig, RunState

config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("my-ralph"),
    ralph_file=Path("my-ralph/RALPH.md"),
    commands=[],
    max_iterations=3,
)
state = RunState(run_id="my-run")
run_loop(config, state)
```

### `run_loop(config, state, emitter=None)`

The main loop. Reads `RALPH.md`, runs commands, assembles prompts, pipes them to the agent, and repeats. **Blocks until the loop finishes.**

| Parameter | Type | Description |
|---|---|---|
| `config` | `RunConfig` | All settings for the run |
| `state` | `RunState` | Observable state — counters, status, control methods |
| `emitter` | `EventEmitter \| None` | Event listener. `None` uses `NullEmitter` (silent) |

### `RunConfig`

All settings for a single run. Fields match the [CLI options](#ralph-run).

| Field | Type | Default | Description |
|---|---|---|---|
| `agent` | `str` | — | Full agent command string |
| `ralph_dir` | `Path` | — | Path to the ralph directory |
| `ralph_file` | `Path` | — | Path to the RALPH.md file |
| `commands` | `list[Command]` | `[]` | Commands to run each iteration |
| `args` | `dict[str, str]` | `{}` | User argument values |
| `max_iterations` | `int \| None` | `None` | Max iterations (`None` = unlimited) |
| `delay` | `float` | `0` | Seconds to wait between iterations |
| `timeout` | `float \| None` | `None` | Max seconds per iteration |
| `stop_on_error` | `bool` | `False` | Stop loop if agent exits non-zero or times out |
| `log_dir` | `Path \| None` | `None` | Directory for iteration log files |
| `credit` | `bool` | `True` | Append co-author trailer instruction to prompt |
| `project_root` | `Path` | `Path(".")` | Project root directory |

`RunConfig` is mutable — change fields mid-run and the loop picks them up at the next iteration boundary.

### `Command`

```python
from ralphify import Command

cmd = Command(name="tests", run="uv run pytest -x")
cmd_slow = Command(name="integration", run="uv run pytest tests/integration", timeout=300)
```

`name` and `run` are required; `timeout` defaults to `60` seconds.

### `RunState`

Observable state for a running loop. Thread-safe control methods let you stop, pause, and resume from another thread.

| Property | Type | Description |
|---|---|---|
| `run_id` | `str` | Unique identifier for this run |
| `status` | `RunStatus` | Current lifecycle status |
| `iteration` | `int` | Current iteration number (starts at 0) |
| `completed` | `int` | Number of successful iterations |
| `failed` | `int` | Number of failed iterations (includes timed out) |
| `timed_out_count` | `int` | Number of timed-out iterations (subset of `failed`) |
| `total` | `int` | `completed + failed` |
| `started_at` | `datetime \| None` | When the run started |
| `paused` | `bool` | Whether the run is currently paused |
| `stop_requested` | `bool` | Whether a stop has been requested |

`timed_out_count` is a **subset** of `failed`, so `completed + failed == total`. Control methods: `state.request_stop()`, `state.request_pause()`, `state.request_resume()`.

### `RunStatus`

`PENDING`, `RUNNING`, `PAUSED`, `STOPPED`, `COMPLETED`, `FAILED`. `FAILED` means stopped by `--stop-on-error` after a failed/timed-out iteration, or crashed with an unhandled exception.

### `StopReason`

A `Literal` used in the `RUN_STOPPED` event's `reason` field: `"completed"`, `"error"`, or `"user_requested"`.

### Event system

The loop emits structured events at each step. Implement the `EventEmitter` protocol (a single `emit(event)` method) to listen.

```python
from pathlib import Path
from ralphify import Event, EventType, RunConfig, RunState, run_loop


class MyEmitter:
    def emit(self, event: Event) -> None:
        if event.type == EventType.ITERATION_COMPLETED:
            print(f"Iteration {event.data['iteration']} done in {event.data['duration_formatted']}")


config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("my-ralph"),
    ralph_file=Path("my-ralph/RALPH.md"),
    commands=[],
    max_iterations=3,
)
run_loop(config, RunState(run_id="observed-run"), emitter=MyEmitter())
```

Each `Event` carries `type` (`EventType`), `run_id`, `data` (dict), and `timestamp`. Use `event.to_dict()` to serialize.

#### `EventType` reference

| Group | Event | Data fields |
|---|---|---|
| Run | `RUN_STARTED` | `ralph_name`, `commands`, `max_iterations`, `timeout`, `delay` |
| Run | `RUN_STOPPED` | `reason` (`StopReason`), `total`, `completed`, `failed`, `timed_out_count` |
| Run | `RUN_PAUSED` / `RUN_RESUMED` | — |
| Iteration | `ITERATION_STARTED` | `iteration` |
| Iteration | `ITERATION_COMPLETED` | `iteration`, `returncode`, `duration`, `duration_formatted`, `detail`, `log_file`, `result_text` |
| Iteration | `ITERATION_FAILED` | same as `ITERATION_COMPLETED` |
| Iteration | `ITERATION_TIMED_OUT` | same (`returncode` is `None`) |
| Commands | `COMMANDS_STARTED` / `COMMANDS_COMPLETED` | `iteration`, `count` |
| Prompt | `PROMPT_ASSEMBLED` | `iteration`, `prompt_length` |
| Agent | `AGENT_ACTIVITY` | `iteration`, `raw` (one stream-json line; Claude Code only) |
| Agent | `AGENT_OUTPUT_LINE` | `iteration`, `line`, `stream` (`"stdout"`/`"stderr"`; all agents) |
| Other | `LOG_MESSAGE` | `message`, `level`, `traceback` (optional) |

#### Built-in emitters

| Emitter | Description |
|---|---|
| `NullEmitter` | Discards all events. Default when no emitter is passed. |
| `QueueEmitter` | Pushes events into a `queue.Queue` for async consumption. |
| `FanoutEmitter` | Broadcasts each event to multiple emitters. |
| `BoundEmitter` | Wraps any emitter with a fixed `run_id`; has `log_info`, `log_error`, and `agent_output_line` convenience methods. |

```python
from ralphify import QueueEmitter, FanoutEmitter, BoundEmitter

q_emitter = QueueEmitter()
run_loop(config, state, emitter=q_emitter)
while not q_emitter.queue.empty():
    print(q_emitter.queue.get().to_dict())

fanout = FanoutEmitter([q_emitter, MyEmitter()])
bound = BoundEmitter(q_emitter, run_id="my-run")
bound(EventType.ITERATION_STARTED, {"iteration": 1})
```

### Concurrent runs with `RunManager`

`RunManager` is a thread-safe registry for launching and controlling multiple loops concurrently. Each run gets its own daemon thread and event queue.

```python
from pathlib import Path
from ralphify import RunManager, RunConfig, Command

manager = RunManager()
config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("docs-ralph"),
    ralph_file=Path("docs-ralph/RALPH.md"),
    commands=[Command(name="build", run="mkdocs build --strict")],
    max_iterations=5,
)
run = manager.create_run(config)
manager.start_run(run.state.run_id)

for r in manager.list_runs():
    print(f"{r.state.run_id}: {r.state.status.value} — {r.state.completed} done")

manager.pause_run(run.state.run_id)
manager.resume_run(run.state.run_id)
manager.stop_run(run.state.run_id)
```

Each run is wrapped in a `ManagedRun` bundling `config`, `state`, and a `QueueEmitter`. Register extra listeners **before** `start_run()` with `run.add_listener(listener)` — events are then broadcast to both the queue and your listeners via a `FanoutEmitter`.

`RunManager` methods: `create_run(config)`, `start_run(run_id)`, `stop_run(run_id)`, `pause_run(run_id)`, `resume_run(run_id)`, `list_runs()`, `get_run(run_id)`.
