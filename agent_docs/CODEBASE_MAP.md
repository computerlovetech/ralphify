# Codebase Map

Quick orientation guide for AI coding agents working in this project.

## What this project is

Ralphify is a CLI tool (`ralph`) that runs AI coding agents in autonomous loops. It reads a prompt file, pipes it to an agent command (e.g. `claude -p`), waits for it to finish, then repeats. Each iteration gets a fresh context window. Progress is tracked through git commits.

The core loop is simple. The complexity lives in **prompt assembly** — resolving contexts, instructions, and check failures into the prompt before each iteration.

## Directory structure

```
src/ralphify/           # All source code
├── __init__.py         # Version detection + app entry point
├── cli.py              # CLI commands (init, run, status, new, prompts) — delegates to engine for the loop
├── engine.py           # Core run loop with structured event emission (extracted from cli.py)
├── manager.py          # Multi-run orchestration for the UI layer (concurrent runs via threads)
├── checks.py           # Discover and run validation checks, format failures
├── contexts.py         # Discover and run dynamic data contexts, resolve into prompt
├── instructions.py     # Discover and resolve static text instructions
├── prompts.py          # Named prompt discovery and resolution
├── resolver.py         # Template placeholder resolution (shared by contexts + instructions)
├── detector.py         # Auto-detect project type from manifest files
├── _runner.py          # Execute shell commands with timeout and capture output
├── _frontmatter.py     # Parse YAML frontmatter from markdown primitives, discover primitives
├── _events.py          # Event types and emitter protocol (NullEmitter, QueueEmitter)
├── _output.py          # Combine/truncate stdout+stderr
└── ui/                 # Web UI layer (optional — not part of the core CLI)
    ├── app.py          # FastAPI application setup
    ├── api/            # REST API endpoints
    ├── models.py       # Pydantic models for API
    ├── persistence.py  # SQLite persistence via aiosqlite
    ├── frontend/       # Frontend assets (HTML, JS, CSS)
    └── static/         # Static files served by the UI

tests/                  # Pytest tests — one test file per module
docs/                   # MkDocs site (Material theme) — user-facing documentation
agent_docs/             # Documentation for AI coding agents
.github/workflows/
├── test.yml            # Run tests on push to main and PRs (Python 3.11–3.13)
├── docs.yml            # Deploy docs to GitHub Pages on push to main
└── publish.yml         # Publish to PyPI on release (with test gate)
```

## Architecture: how the pieces connect

The CLI entry point is `cli.py:run()` (line ~433), which parses options, resolves the prompt via the priority chain, and delegates to `engine.py:run_loop()` for the actual iteration cycle. The engine emits structured events via an `EventEmitter`, making the same loop reusable from both CLI and web UI contexts.

```
ralph run
  │
  ├── cli.py:run() — parse options, resolve prompt, print banner
  │   ├── Load config from ralph.toml
  │   ├── Resolve prompt via priority chain (--prompt > name > --prompt-file > toml > root)
  │   └── Build RunConfig and call engine.run_loop()
  │
  └── engine.py:run_loop(config, state, emitter)
       ├── Discover checks, contexts, instructions from .ralph/
       └── Loop:
            ├── Read PROMPT.md (or use ad-hoc text)
            ├── Run contexts → resolve {{ contexts.* }} placeholders
            ├── Resolve {{ instructions.* }} placeholders
            ├── Append check failures from previous iteration (if any)
            ├── Pipe assembled prompt to agent command via subprocess
            ├── Emit iteration events (started, completed, failed, timed_out)
            ├── Run checks → emit check events → format failures for next iteration
            ├── Handle pause/resume/stop/reload requests via RunState
            └── Repeat
```

### The four primitives

All four follow the same pattern: a directory under `.ralph/` with a marker markdown file containing YAML frontmatter.

| Primitive | Marker file | Runs | Injects into prompt |
|---|---|---|---|
| Check | `CHECK.md` | After iteration | Failures appended to next prompt |
| Context | `CONTEXT.md` | Before iteration | Output replaces `{{ contexts.name }}` |
| Instruction | `INSTRUCTION.md` | Before iteration | Content replaces `{{ instructions.name }}` |
| Prompt | `PROMPT.md` | At run start | Replaces root PROMPT.md when selected by name |

Discovery is handled by `_frontmatter.py:discover_primitives()` which scans `.ralph/{kind}/*/` for marker files.

### Placeholder resolution

Both contexts and instructions use the same resolver (`resolver.py:resolve_placeholders()`):
- `{{ contexts.git-log }}` — named placement for a specific primitive
- `{{ contexts }}` — bulk placement for all remaining primitives
- No placeholders at all — everything appended to the end of the prompt

### Event system

The run loop communicates via structured events (`_events.py`). Each event has a type (`EventType` enum), run ID, data dict, and UTC timestamp.

- **`EventEmitter`** — protocol that any listener implements (just an `emit(event)` method)
- **`NullEmitter`** — discards events (used in tests)
- **`QueueEmitter`** — pushes events into a `queue.Queue` for async consumption (used by the UI)

The CLI uses a `ConsoleEmitter` (defined in `cli.py`) that renders events to the terminal with Rich formatting.

### Multi-run management (UI layer)

`manager.py:RunManager` orchestrates concurrent runs for the web UI:
- Creates runs with unique IDs and wraps them in `ManagedRun` (config + state + emitter + thread)
- Starts each run in a daemon thread via `engine.run_loop()`
- Supports pause/resume/stop per run via `RunState` thread-safe control methods
- Uses `_FanoutEmitter` to broadcast events to multiple listeners (e.g., queue + persistence)

## Key files to understand first

1. **`engine.py`** — The core run loop. Understands `RunConfig`, `RunState`, and `EventEmitter`. This is where iteration logic lives.
2. **`cli.py`** — All CLI commands, scaffold templates, and the `ConsoleEmitter`. Delegates to `engine.run_loop()` for the actual loop.
3. **`_frontmatter.py`** — The primitive discovery system. Understanding `discover_primitives()` and `parse_frontmatter()` is essential for working on checks/contexts/instructions/prompts.
4. **`resolver.py`** — Template placeholder logic shared by contexts and instructions. Small file but critical — changes here affect both.

## Traps and gotchas

### If you change the primitive marker filenames...
The marker file names (`CHECK.md`, `CONTEXT.md`, `INSTRUCTION.md`, `PROMPT.md`) are hardcoded in each module's `discover_*()` function AND in the scaffold templates in `cli.py`. You must update both.

### If you change frontmatter fields...
Frontmatter parsing is in `_frontmatter.py:parse_frontmatter()` but the field names are consumed in each module's `discover_*()` function. The `timeout` and `enabled` fields get special type coercion in `parse_frontmatter()` — adding a new typed field requires updating the coercion logic there.

### If you add a new CLI command...
Add it in `cli.py`. The CLI uses Typer. The `new` subcommand group uses `app.add_typer()`. Update `docs/cli.md` to document the new command.

### If you add a new primitive type...
You need to:
1. Create a new module (like `prompts.py`) with dataclass, discover, and resolve functions
2. Add a scaffold template in `cli.py` and a `new` subcommand
3. Wire it into `engine.py:run_loop()` if it affects the iteration cycle
4. Add tests
5. Update `docs/primitives.md`

### If you change the event system...
Events are defined in `_events.py:EventType`. The `ConsoleEmitter` in `cli.py` renders them to the terminal. The UI layer consumes them via `QueueEmitter`. Adding a new event type requires handling it in both places.

### Output truncation
`_output.py:truncate_output()` caps output at 5000 chars. This affects check failure output injected into prompts. If agents complain about missing error details, this is why.

### The `run.*` script convention
Checks and contexts can use either a `command` in frontmatter or a `run.*` script file in the primitive directory. If both exist, the script wins. This is handled by `_frontmatter.py:find_run_script()`.

## Testing

```bash
uv run pytest           # Run all tests
uv run pytest -x        # Stop on first failure
```

Tests are in `tests/` with one file per module:

```
tests/
├── test_cli.py           # CLI commands (init, run, status, new, prompts)
├── test_engine.py        # Core run loop and RunState/RunConfig
├── test_manager.py       # Multi-run orchestration
├── test_checks.py        # Check discovery and execution
├── test_contexts.py      # Context discovery and injection
├── test_instructions.py  # Instruction discovery and resolution
├── test_prompts.py       # Named prompt discovery and resolution
├── test_runner.py        # Command execution with timeout
├── test_detector.py      # Project type detection
├── test_output.py        # Output combining and truncation
└── test_persistence.py   # UI persistence layer (SQLite)
```

All tests use temporary directories and don't require any external services.

## Documentation

```bash
uv run mkdocs serve     # Local preview at http://127.0.0.1:8000
uv run mkdocs build --strict   # Build and check for warnings
```

Docs auto-deploy to GitHub Pages on push to main (via `.github/workflows/docs.yml`). The site lives at `https://computerlovetech.github.io/ralphify/`.

## Dependencies

Minimal by design:
- **typer** — CLI framework
- **rich** — Terminal formatting (used via typer's console)
- No other runtime dependencies

Dev dependencies: pytest, mkdocs, mkdocs-material.

Optional UI dependencies: fastapi, uvicorn, aiosqlite, websockets.
