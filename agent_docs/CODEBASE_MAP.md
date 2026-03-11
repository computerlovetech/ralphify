# Codebase Map

Quick orientation guide for AI coding agents working in this project.

## What this project is

Ralphify is a CLI tool (`ralph`) that runs AI coding agents in autonomous loops. It reads a prompt file, pipes it to an agent command (e.g. `claude -p`), waits for it to finish, then repeats. Each iteration gets a fresh context window. Progress is tracked through git commits.

The core loop is simple. The complexity lives in **prompt assembly** — resolving contexts, instructions, and check failures into the prompt before each iteration.

## Directory structure

```
src/ralphify/           # All source code
├── __init__.py         # Version detection + app entry point
├── cli.py              # CLI commands (init, run, status, new) — this is the main file
├── checks.py           # Discover and run validation checks, format failures
├── contexts.py         # Discover and run dynamic data contexts, resolve into prompt
├── instructions.py     # Discover and resolve static text instructions
├── resolver.py         # Template placeholder resolution (shared by contexts + instructions)
├── detector.py         # Auto-detect project type from manifest files
├── _runner.py          # Execute shell commands with timeout and capture output
├── _frontmatter.py     # Parse YAML frontmatter from markdown primitives, discover primitives
└── _output.py          # Combine/truncate stdout+stderr

tests/                  # Pytest tests — one test file per module
docs/                   # MkDocs site (Material theme) — user-facing documentation
.github/workflows/
├── docs.yml            # Deploy docs to GitHub Pages on push to main
└── publish.yml         # Publish to PyPI on release (with test gate)
```

## Architecture: how the pieces connect

The main loop lives in `cli.py:run()` (line ~344). Here's the flow:

```
ralph run
  │
  ├── Load config from ralph.toml
  ├── Discover checks, contexts, instructions from .ralph/
  │
  └── Loop:
       ├── Read PROMPT.md
       ├── Run contexts → resolve_contexts() replaces {{ contexts.* }} placeholders
       ├── Run instructions → resolve_instructions() replaces {{ instructions.* }} placeholders
       ├── Append check failures from previous iteration (if any)
       ├── Pipe assembled prompt to agent command via subprocess
       ├── Run checks → format failures for next iteration
       └── Repeat
```

### The three primitives

All three follow the same pattern: a directory under `.ralph/` with a marker markdown file containing YAML frontmatter.

| Primitive | Marker file | Runs | Injects into prompt |
|---|---|---|---|
| Check | `CHECK.md` | After iteration | Failures appended to next prompt |
| Context | `CONTEXT.md` | Before iteration | Output replaces `{{ contexts.name }}` |
| Instruction | `INSTRUCTION.md` | Before iteration | Content replaces `{{ instructions.name }}` |

Discovery is handled by `_frontmatter.py:discover_primitives()` which scans `.ralph/{kind}/*/` for marker files.

### Placeholder resolution

Both contexts and instructions use the same resolver (`resolver.py:resolve_placeholders()`):
- `{{ contexts.git-log }}` — named placement for a specific primitive
- `{{ contexts }}` — bulk placement for all remaining primitives
- No placeholders at all — everything appended to the end of the prompt

## Key files to understand first

1. **`cli.py`** — The heart of the project. All commands, the main loop, templates for scaffolded files. If you're changing behavior, it's probably here.
2. **`_frontmatter.py`** — The primitive discovery system. Understanding `discover_primitives()` and `parse_frontmatter()` is essential for working on checks/contexts/instructions.
3. **`resolver.py`** — Template placeholder logic shared by contexts and instructions. Small file but critical — changes here affect both.

## Traps and gotchas

### If you change the primitive marker filenames...
The marker file names (`CHECK.md`, `CONTEXT.md`, `INSTRUCTION.md`) are hardcoded in each module's `discover_*()` function AND in the scaffold templates in `cli.py`. You must update both.

### If you change frontmatter fields...
Frontmatter parsing is in `_frontmatter.py:parse_frontmatter()` but the field names are consumed in each module's `discover_*()` function. The `timeout` and `enabled` fields get special type coercion in `parse_frontmatter()` — adding a new typed field requires updating the coercion logic there.

### If you add a new CLI command...
Add it in `cli.py`. The CLI uses Typer. The `new` subcommand group uses `app.add_typer()`. Update `docs/cli.md` to document the new command.

### If you add a new primitive type...
You need to:
1. Create a new module (like `checks.py`) with dataclass, discover, run, and resolve functions
2. Add a scaffold template in `cli.py` and a `new` subcommand
3. Wire it into the `run()` loop in `cli.py`
4. Add tests
5. Update `docs/primitives.md`

### Output truncation
`_output.py:truncate_output()` caps output at 5000 chars. This affects check failure output injected into prompts. If agents complain about missing error details, this is why.

### The `run.*` script convention
Checks and contexts can use either a `command` in frontmatter or a `run.*` script file in the primitive directory. If both exist, the script wins. This is handled by `_frontmatter.py:find_run_script()`.

## Testing

```bash
uv run pytest           # Run all tests
uv run pytest -x        # Stop on first failure
```

Tests are in `tests/` with one file per module. They use temporary directories and don't require any external services.

## Documentation

```bash
uv run mkdocs serve     # Local preview at http://127.0.0.1:8000
uv run mkdocs build --strict   # Build and check for warnings
```

Docs auto-deploy to GitHub Pages on push to main (via `.github/workflows/docs.yml`). The site lives at `https://kasperjunge.github.io/ralphify/`.

## Dependencies

Minimal by design:
- **typer** — CLI framework
- **rich** — Terminal formatting (used via typer's console)
- No other runtime dependencies

Dev dependencies: pytest, mkdocs, mkdocs-material.
