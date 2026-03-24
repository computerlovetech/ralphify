---
title: Ralphify Codebase Map
description: Architecture overview and module map for contributors and AI coding agents working on ralphify.
keywords: ralphify architecture, codebase map, module overview, engine, CLI, resolver, agent subprocess
---

# Codebase Map

Quick orientation guide for anyone working on this codebase — human contributors and AI coding agents alike.

## What this project is

Ralphify is a CLI tool (`ralph`) that runs AI coding agents in autonomous loops. It reads a RALPH.md file from a ralph directory, runs commands, assembles a prompt with the output, pipes it to an agent command via stdin, waits for it to finish, then repeats. Each iteration gets a fresh context window. Progress is tracked through git commits.

The core loop is simple. The complexity lives in **prompt assembly** — running commands and resolving placeholders into the prompt before each iteration.

## Directory structure

```
src/ralphify/           # All source code
├── __init__.py         # Version detection + app entry point
├── cli.py              # CLI commands (run, new, init) — delegates to engine for the loop
├── engine.py           # Core run loop orchestration with structured event emission
├── manager.py          # Multi-run orchestration (concurrent runs via threads)
├── _resolver.py        # Template placeholder resolution ({{ commands.* }}, {{ args.* }}, {{ ralph.* }})
├── _agent.py           # Run agent subprocesses (streaming + blocking modes, log writing)
├── _run_types.py       # RunConfig, RunState, RunStatus, Command — shared data types
├── _runner.py          # Execute shell commands with timeout and capture output
├── _frontmatter.py     # Parse YAML frontmatter from RALPH.md, marker constants
├── _skills.py          # Skill installation and agent detection for `ralph new`
├── _console_emitter.py # Rich console renderer for run-loop events (ConsoleEmitter)
├── _events.py          # Event types, emitter protocol, and BoundEmitter convenience wrapper
├── _output.py          # ProcessResult base class, combine stdout+stderr, format durations
└── skills/             # Bundled skill definitions (installed into agent skill dirs)
    └── new-ralph/      # AI-guided ralph creation skill for `ralph new`

tests/                  # Pytest tests — one test file per module
docs/                   # MkDocs site (Material theme) — user-facing documentation
docs/contributing/      # Contributor documentation (this section)
.github/workflows/
├── test.yml            # Run tests on push to main and PRs (Python 3.11–3.13)
├── docs.yml            # Deploy docs to GitHub Pages on push to main
└── publish.yml         # Publish to PyPI on release (with test gate)
```

## Architecture: how the pieces connect

The CLI entry point is `cli.py:run()`, which parses options, reads the ralph directory path, and delegates to `engine.py:run_loop()` for the actual iteration cycle. The engine emits structured events via an `EventEmitter`, making the same loop reusable from both the CLI and any external orchestration layer (such as `manager.py`).

```
ralph run my-ralph
  │
  ├── cli.py:run() — parse options, print banner
  │   ├── Read RALPH.md from the given directory
  │   ├── Parse frontmatter (agent, commands, args)
  │   └── Build RunConfig and call engine.run_loop()
  │
  └── engine.py:run_loop(config, state, emitter)
       └── Loop:
            ├── Re-read RALPH.md from disk
            ├── Run commands → capture output
            ├── Resolve {{ commands.* }} and {{ args.* }} placeholders
            ├── Pipe assembled prompt to agent command via subprocess
            ├── Emit iteration events (started, completed, failed, timed_out)
            ├── Handle pause/resume/stop requests via RunState
            └── Repeat
```

### Placeholder resolution

The resolver (`_resolver.py`) handles `{{ commands.<name> }}` and `{{ args.<name> }}` placeholders. Two functions:

- **`resolve_all()`** — resolves both placeholder kinds in a **single pass** so that a value inserted by one kind (e.g., an arg value containing `{{ commands.foo }}`) is never re-processed as the other kind. Used by the engine for final prompt assembly.
- **`resolve_args()`** — resolves only `{{ args.<name> }}` placeholders. Used by the engine to expand arg references inside command `run` strings before executing them.

Unmatched placeholders resolve to empty string in both functions.

### Event system

The run loop communicates via structured events (`_events.py`). Each event has a type (`EventType` enum), run ID, typed data payload, and UTC timestamp.

Event data uses TypedDict classes — one per event type — rather than free-form dicts. The key types:

- **`RunStartedData`** / **`RunStoppedData`** — run lifecycle (stop reason is a `StopReason` literal: `"completed"`, `"error"`, `"user_requested"`)
- **`IterationStartedData`** / **`IterationEndedData`** — per-iteration data (return code, duration, log path)
- **`CommandsStartedData`** / **`CommandsCompletedData`** — command execution bookends
- **`PromptAssembledData`** — prompt length after placeholder resolution
- **`AgentActivityData`** — streaming agent output
- **`LogMessageData`** — info/error messages with optional traceback

All payload types are unioned as `EventData`.

Emitter implementations:

- **`EventEmitter`** — protocol that any listener implements (just an `emit(event)` method)
- **`NullEmitter`** — discards events (used in tests)
- **`QueueEmitter`** — pushes events into a `queue.Queue` for async consumption
- **`FanoutEmitter`** — broadcasts events to multiple emitters
- **`BoundEmitter`** — wraps any emitter with a fixed run ID, so callers don't have to pass the ID on every emit. The engine creates one per run and threads it through all internal functions.

The CLI uses a `ConsoleEmitter` (defined in `_console_emitter.py`) that renders events to the terminal with Rich formatting.

### Multi-run management

`manager.py:RunManager` orchestrates concurrent runs:

- Creates runs with unique IDs and wraps them in `ManagedRun` (config + state + emitter + thread)
- Starts each run in a daemon thread via `engine.run_loop()`
- Supports pause/resume/stop per run via `RunState` thread-safe control methods
- Uses `FanoutEmitter` to broadcast events to multiple listeners

## Key files to understand first

1. **`engine.py`** — The core run loop. Uses `RunConfig` and `RunState` (from `_run_types.py`) and `EventEmitter`. This is where iteration logic lives.
2. **`_run_types.py`** — `RunConfig`, `RunState`, `RunStatus`, and `Command`. These are the shared data types used by the engine, CLI, and manager.
3. **`cli.py`** — All CLI commands. Validates frontmatter fields via extracted helpers (`_validate_agent`, `_validate_commands`, `_validate_credit`, `_validate_run_options`, `_validate_declared_args`), builds a `RunConfig`, and delegates to `engine.run_loop()` for the actual loop. Terminal event rendering lives in `_console_emitter.py`.
4. **`_frontmatter.py`** — YAML frontmatter parsing. Extracts `agent`, `commands`, `args` from the RALPH.md file.
5. **`_resolver.py`** — Template placeholder logic. Small file but critical.
6. **`_skills.py`** + **`skills/`** — The skill system behind `ralph new`. `_skills.py` handles agent detection, reads bundled skill definitions from `skills/`, installs them into the agent's skill directory, and builds the command to launch the agent.

## Traps and gotchas

### If you change frontmatter fields...

Frontmatter parsing is in `_frontmatter.py:parse_frontmatter()`, which returns a raw dict. Each field is then validated and coerced by a dedicated helper in `cli.py` — e.g. `_validate_agent()`, `_validate_commands()`, `_validate_credit()`. Adding a new frontmatter field means adding a new validator in `cli.py` and wiring it into `_build_run_config()`.

**Field name constants** (`FIELD_AGENT`, `FIELD_COMMANDS`, `FIELD_ARGS`, `FIELD_CREDIT`, `CMD_FIELD_NAME`, `CMD_FIELD_RUN`, `CMD_FIELD_TIMEOUT`) are centralized in `_frontmatter.py`. Always import these constants instead of hardcoding strings like `"agent"` or `"commands"` — this keeps error messages, validation, and placeholder resolution in sync when fields are renamed.

### If you add a new CLI command...

Add it in `cli.py`. The CLI uses Typer. Update `docs/cli.md` to document the new command.

### If you change the event system...

Events are defined in `_events.py:EventType`, with a corresponding TypedDict payload class for each type. Adding a new event type requires a new `EventType` member, a new TypedDict payload class, adding it to the `EventData` union, and handling it in `ConsoleEmitter` (`_console_emitter.py`).

### Credit trailer

When `credit` is `true` (the default), `engine.py:_assemble_prompt()` appends `_CREDIT_INSTRUCTION` to the prompt — a short instruction telling the agent to include a `Co-authored-by: Ralphify` trailer in git commits. Users can opt out with `credit: false` in frontmatter.

### Subprocess result types

`_output.py` defines `ProcessResult`, the base dataclass for subprocess results (provides `returncode`, `timed_out`, and a `success` property). Both `_runner.py:RunResult` (command execution) and `_agent.py:AgentResult` (agent execution) extend it. If you add a new subprocess wrapper, inherit from `ProcessResult` to get consistent success/timeout semantics. The module also provides `ensure_str()` for bytes-to-string decoding, `collect_output()` for combining stdout+stderr, and `SUBPROCESS_TEXT_KWARGS` — the shared kwargs dict used by all `subprocess.Popen` calls to ensure consistent encoding and stream handling.

### Command parsing

Commands in RALPH.md frontmatter are parsed with `shlex.split()` — no shell features. For shell features, users point the `run` field at a script.

## Testing

```bash
uv run pytest           # Run all tests
uv run pytest -x        # Stop on first failure
```

Tests are in `tests/` with one file per module. All tests use temporary directories and don't require any external services.

## Dependencies

Minimal by design:

- **typer** — CLI framework
- **rich** — Terminal formatting (used via typer's console)
- **pyyaml** — YAML frontmatter parsing in `_frontmatter.py`

Dev dependencies: pytest, mkdocs, mkdocs-material.
