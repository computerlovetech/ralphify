---
description: Architecture overview and module map for contributors and AI coding agents working on ralphify.
---

# Codebase Map

Quick orientation guide for anyone working on this codebase — human contributors and AI coding agents alike.

## What this project is

Ralphify is a CLI tool (`ralph`) that runs AI coding agents in autonomous loops. It reads a prompt file, pipes it to an agent command (e.g. `claude -p`), waits for it to finish, then repeats. Each iteration gets a fresh context window. Progress is tracked through git commits.

The core loop is simple. The complexity lives in **prompt assembly** — resolving contexts, instructions, and check failures into the prompt before each iteration.

## Directory structure

```
src/ralphify/           # All source code
├── __init__.py         # Version detection + app entry point
├── cli.py              # CLI commands (init, run, status, new) — delegates to engine for the loop
├── engine.py           # Core run loop orchestration with structured event emission
├── manager.py          # Multi-run orchestration (concurrent runs via threads)
├── checks.py           # Discover and run validation checks, format failures
├── contexts.py         # Discover and run dynamic data contexts, resolve into prompt
├── instructions.py     # Discover and resolve static text instructions
├── ralphs.py           # Named ralph discovery and resolution (resolve_ralph_source)
├── resolver.py         # Template placeholder resolution (shared by contexts + instructions)
├── detector.py         # Auto-detect project type from manifest files
├── _agent.py           # Run agent subprocesses (streaming + blocking modes, log writing)
├── _run_types.py       # RunConfig, RunState, RunStatus — shared data types for the engine
├── _runner.py          # Execute shell commands with timeout and capture output (checks/contexts)
├── _frontmatter.py     # Parse YAML frontmatter from markdown primitives, marker/config constants
├── _discovery.py       # Primitive protocol, directory scanning, merge_by_name, find_run_script
├── _templates.py       # Scaffold templates for init and new commands
├── _console_emitter.py # Rich console renderer for run-loop events (ConsoleEmitter)
├── _events.py          # Event types and emitter protocol (NullEmitter, QueueEmitter, FanoutEmitter)
└── _output.py          # Combine/truncate stdout+stderr

tests/                  # Pytest tests — one test file per module
docs/                   # MkDocs site (Material theme) — user-facing documentation
docs/contributing/      # Contributor documentation (this section)
.github/workflows/
├── test.yml            # Run tests on push to main and PRs (Python 3.11–3.13)
├── docs.yml            # Deploy docs to GitHub Pages on push to main
└── publish.yml         # Publish to PyPI on release (with test gate)
```

## Architecture: how the pieces connect

The CLI entry point is `cli.py:run()`, which parses options, resolves the prompt source via `ralphs.py:resolve_ralph_source()`, and delegates to `engine.py:run_loop()` for the actual iteration cycle. The engine emits structured events via an `EventEmitter`, making the same loop reusable from both the CLI and any external orchestration layer (such as `manager.py`).

```
ralph run
  │
  ├── cli.py:run() — parse options, print banner
  │   ├── Load config from ralph.toml
  │   ├── Resolve prompt via ralphs.resolve_ralph_source() (--prompt > name > --ralph-file > toml > root)
  │   └── Build RunConfig and call engine.run_loop()
  │
  └── engine.py:run_loop(config, state, emitter)
       ├── Discover checks, contexts, instructions from .ralphify/
       └── Loop:
            ├── Read RALPH.md (or use ad-hoc text)
            ├── Run contexts → resolve {{ contexts.* }} placeholders
            ├── Resolve {{ instructions.* }} placeholders
            ├── Append check failures from previous iteration (if any)
            ├── Pipe assembled prompt to agent command via subprocess
            ├── Emit iteration events (started, completed, failed, timed_out)
            ├── Run checks → emit check events → format failures for next iteration
            ├── Handle pause/resume/stop/reload requests via RunState
            └── Repeat
```

### The four primitives and the `Primitive` protocol

All four primitive types follow the same pattern: a directory under `.ralphify/` with a marker markdown file containing YAML frontmatter. Each type's dataclass (`Check`, `Context`, `Instruction`, `Ralph`) satisfies the `Primitive` protocol defined in `_discovery.py`, which requires `name` and `enabled` properties. This enables type-safe generic functions for discovery, filtering, merging, and display — the engine's `_discover_and_filter_enabled()` helper uses the protocol to handle all four types through a single code path.

| Primitive | Marker file | Runs | Injects into prompt |
|---|---|---|---|
| Check | `CHECK.md` | After iteration | Failures appended to next prompt |
| Context | `CONTEXT.md` | Before iteration | Output replaces `{{ contexts.name }}` |
| Instruction | `INSTRUCTION.md` | Before iteration | Content replaces `{{ instructions.name }}` |
| Ralph | `RALPH.md` | At run start | Replaces root RALPH.md when selected by name |

Discovery is handled by `_discovery.py:discover_primitives()` which scans `.ralphify/{kind}/*/` for marker files. The engine groups enabled primitives into an `EnabledPrimitives` NamedTuple for clean parameter passing.

### Placeholder resolution

Both contexts and instructions use the same resolver (`resolver.py:resolve_placeholders()`):

- `{{ contexts.git-log }}` — named placement for a specific primitive
- `{{ contexts }}` — bulk placement for all remaining primitives
- No placeholders at all — everything appended to the end of the prompt

### Event system

The run loop communicates via structured events (`_events.py`). Each event has a type (`EventType` enum), run ID, data dict, and UTC timestamp.

- **`EventEmitter`** — protocol that any listener implements (just an `emit(event)` method)
- **`NullEmitter`** — discards events (used in tests)
- **`QueueEmitter`** — pushes events into a `queue.Queue` for async consumption (used by external orchestration layers)
- **`FanoutEmitter`** — broadcasts events to multiple emitters (used by the manager for fan-out to queue + persistence)

The CLI uses a `ConsoleEmitter` (defined in `_console_emitter.py`) that renders events to the terminal with Rich formatting.

### Multi-run management

`manager.py:RunManager` orchestrates concurrent runs, providing the building blocks for any external orchestration layer:

- Creates runs with unique IDs and wraps them in `ManagedRun` (config + state + emitter + thread)
- Starts each run in a daemon thread via `engine.run_loop()`
- Supports pause/resume/stop per run via `RunState` thread-safe control methods
- Uses `FanoutEmitter` to broadcast events to multiple listeners

## Key files to understand first

1. **`engine.py`** — The core run loop. Uses `RunConfig` and `RunState` (from `_run_types.py`) and `EventEmitter`. This is where iteration logic lives.
2. **`_run_types.py`** — `RunConfig`, `RunState`, and `RunStatus`. These are the shared data types used by the engine, CLI, and manager. Separated so modules that only need the types don't pull in execution logic.
3. **`cli.py`** — All CLI commands. Delegates to `engine.run_loop()` for the actual loop. Prompt source resolution (name vs. file path vs. inline) lives in `ralphs.py:resolve_ralph_source()`. Scaffold templates live in `_templates.py`. Terminal event rendering lives in `_console_emitter.py`.
4. **`_frontmatter.py`** + **`_discovery.py`** — Frontmatter parsing and primitive discovery. `_frontmatter.py` handles YAML parsing and defines marker constants. `_discovery.py` defines the `Primitive` protocol, scans `.ralphify/` directories, and provides `merge_by_name()` for overlaying ralph-scoped primitives on globals. Understanding both is essential for working on checks/contexts/instructions/ralphs.
5. **`resolver.py`** — Template placeholder logic shared by contexts and instructions. Small file but critical — changes here affect both.

## Traps and gotchas

### If you change the primitive marker filenames...

The marker file names (`CHECK.md`, `CONTEXT.md`, `INSTRUCTION.md`, `RALPH.md`) are defined as constants in `_frontmatter.py` (`CHECK_MARKER`, `CONTEXT_MARKER`, `INSTRUCTION_MARKER`, `RALPH_MARKER`). The primitives directory name is `PRIMITIVES_DIR`. All modules — `checks.py`, `contexts.py`, `instructions.py`, `ralphs.py`, and `cli.py` — import from there. Change the constant to rename everywhere.

### If you change frontmatter fields...

Frontmatter parsing is in `_frontmatter.py:parse_frontmatter()` but the field names are consumed in each module's `discover_*()` function. The `timeout` and `enabled` fields get special type coercion in `parse_frontmatter()` — adding a new typed field requires updating the coercion logic there.

### If you add a new CLI command...

Add it in `cli.py`. The CLI uses Typer. The `new` subcommand group uses `app.add_typer()`. Update `docs/cli.md` to document the new command.

### If you add a new primitive type...

You need to:

1. Create a new module (like `ralphs.py`) with a dataclass that satisfies the `Primitive` protocol (`name` and `enabled` properties), plus discover and resolve functions
2. Add a scaffold template in `_templates.py` and a `new` subcommand in `cli.py`
3. Wire it into `engine.py:run_loop()` — add it to `EnabledPrimitives` and use `_discover_and_filter_enabled()`
4. Add tests
5. Update `docs/primitives.md`

### If you change the event system...

Events are defined in `_events.py:EventType`. The `ConsoleEmitter` in `_console_emitter.py` renders them to the terminal. External consumers can use `QueueEmitter` or implement the `EventEmitter` protocol. Adding a new event type requires handling it in `ConsoleEmitter` and any other active emitters.

### Output truncation

`_output.py:truncate_output()` caps output at 5000 chars. This affects check failure output injected into prompts. If agents complain about missing error details, this is why.

### The `run.*` script convention

Checks and contexts can use either a `command` in frontmatter or a `run.*` script file in the primitive directory. If both exist, the script wins. This is handled by `_discovery.py:find_run_script()`.

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
- No other runtime dependencies

Dev dependencies: pytest, mkdocs, mkdocs-material.
