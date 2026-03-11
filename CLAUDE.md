# CLAUDE.md

Project context for Claude Code when working on this repository.

For full architecture details, see `agent_docs/CODEBASE_MAP.md`.

## What this is

Ralphify is a CLI tool (`ralph`) that runs AI coding agents in autonomous loops. It pipes a prompt to an agent, validates work with checks, and repeats with fresh context each iteration.

## Quick commands

```bash
uv run pytest              # Run tests (required before any commit)
uv run pytest -x           # Stop on first failure
uv run mkdocs build --strict  # Build docs (must pass with zero warnings)
uv run mkdocs serve        # Preview docs at http://127.0.0.1:8000
```

## Project layout

All source code is in `src/ralphify/`. The main file is `cli.py` — it contains the CLI commands and delegates to the engine for the core loop.

Key modules:
- `cli.py` — CLI commands and the `ConsoleEmitter`
- `_templates.py` — Scaffold templates for `ralph init` and `ralph new`
- `_frontmatter.py` — Primitive discovery and YAML frontmatter parsing
- `resolver.py` — Template placeholder resolution (`{{ contexts.name }}`, `{{ instructions }}`)
- `prompts.py` — Named prompt discovery and resolution
- `checks.py`, `contexts.py`, `instructions.py` — The other three primitive types

Tests are in `tests/` with one file per module. Docs are in `docs/` using MkDocs with Material theme.

## Conventions

- **Commit messages**: `docs: explain X for users who want to Y`, `feat: add X so users can Y`, `fix: resolve X that caused Y`
- **Dependencies**: Minimal by design. Runtime deps are only `typer` and `rich`. Prefer stdlib over new deps.
- **Tests**: No external services, no API keys. All tests use temporary directories.
- **Docs**: Every user-facing feature needs a docs page. Run `mkdocs build --strict` before committing doc changes.

## Traps

- Primitive marker filenames (`CHECK.md`, `CONTEXT.md`, `INSTRUCTION.md`, `PROMPT.md`) are defined as constants in `_frontmatter.py` (`CHECK_MARKER`, `CONTEXT_MARKER`, etc.). All modules import from there — change the constant to rename everywhere.
- `timeout` and `enabled` frontmatter fields have special type coercion in `_frontmatter.py:parse_frontmatter()`. New typed fields need coercion logic added there.
- Both contexts and instructions share `resolver.py:resolve_placeholders()`. Changes affect both.
- Output is truncated to 5000 chars in `_output.py`. This is intentional.
- Commands in frontmatter run via `shlex.split()` — no shell features (pipes, redirections, `&&`). Scripts (`run.*`) are the escape hatch.
