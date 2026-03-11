---
description: Ralphify release history — new features, bug fixes, and breaking changes across all versions.
---

# Changelog

All notable changes to ralphify are documented here.

## Unreleased

Nothing yet.

---

## 0.1.5 — 2026-03-11

Redesigned New Run modal and polished dashboard styling.

### Added

- **Redesigned New Run modal** — the modal now features a card-based prompt picker, clearer section labels with icons, and a collapsible settings panel instead of exposing every field at once.
- **Prompt card grid** — named prompts display as selectable cards with descriptions, replacing the old chip-style buttons.
- **Ad-hoc prompt mode** — users can toggle between selecting a named prompt and typing a one-off prompt directly in the modal.

### Improved

- Dashboard CSS overhaul — new modal layout classes, better spacing, softer card styling, and consistent use of the Dusk design system.
- Simplified New Run form state — replaced single config object with focused individual state hooks for clarity.
- Updated project prompt (`PROMPT.md`) to focus on UI/design iteration with the Dusk palette and design principles.

---

## 0.1.4 — 2026-03-11

Ad-hoc prompts, better discoverability, and expanded cookbook recipes.

### Added

- **Ad-hoc prompts** — `ralph run -p "Fix the login bug"` passes a prompt directly on the command line, bypassing `PROMPT.md` entirely. Useful for quick one-off tasks. Placeholders (contexts and instructions) resolve as normal.
- **Test coverage cookbook recipe** — step-by-step setup for systematically increasing test coverage with a coverage context, threshold check, and focused prompt.
- **Rust and Go cookbook recipes** — complete copy-pasteable setups for `cargo test`/`cargo clippy`/`cargo fmt` and `go test`/`go vet` workflows.

### Improved

- Page descriptions and search plugin for better SEO — docs pages now have meta descriptions and the search separates on dots and dashes.
- `-p`/`--prompt` flag surfaced in README quickstart and CLI reference so new users discover it faster.
- Comprehensive docstrings on all public functions and classes for contributors and AI agents working in the codebase.

---

## 0.1.3 — 2026-03-10

The primitives release. Checks, contexts, and instructions turn the basic loop into a self-healing feedback system.

### Added

- **Checks** — post-iteration validation scripts in `.ralph/checks/`. When a check fails, its output is fed into the next iteration so the agent can fix its own mistakes. Supports both `command` in frontmatter and `run.*` scripts.
- **Contexts** — dynamic data injection in `.ralph/contexts/`. Run a command before each iteration and inject its output into the prompt via `{{ contexts.name }}` placeholders. Static-only contexts (no command) are also supported.
- **Instructions** — reusable prompt rules in `.ralph/instructions/`. Toggle coding standards, commit conventions, or safety constraints on and off without editing `PROMPT.md`. Use `{{ instructions }}` or `{{ instructions.name }}` in the prompt.
- `ralph new check|context|instruction <name>` scaffolding commands
- HTML comment stripping — comments in primitive markdown files are stripped before injection, so you can leave notes that don't leak into the assembled prompt
- Placeholder resolution with three strategies: named (`{{ contexts.name }}`), bulk (`{{ contexts }}`), and implicit (append to end)

### Changed

- Improved CLI help text for all commands and subcommands

### Internal

- Extracted shared modules: `_frontmatter.py`, `resolver.py`, `_runner.py`, `_output.py`

## 0.1.2 — 2026-03-09

Quality-of-life improvements for the core loop.

### Added

- `ralph status` command — validate your setup and see discovered primitives before running
- `--timeout` / `-t` option — kill agent iterations that exceed a time limit
- `--log-dir` / `-l` option — save each iteration's output to timestamped log files
- `--version` / `-V` flag
- ASCII art startup banner with Ralph Wiggum color scheme
- GitHub Actions workflow for publishing to PyPI

### Fixed

- `UnicodeEncodeError` on Windows when printing non-ASCII characters

## 0.1.0 — 2026-03-09

Initial release.

### Added

- `ralph init` — create `ralph.toml` and `PROMPT.md` in your project
- `ralph run` — the core autonomous loop: read prompt, pipe to agent, repeat
- Iteration tracking with exit codes and duration
- `--stop-on-error` / `-s` — halt the loop if the agent exits non-zero
- `-n` — limit the number of iterations
- `--delay` / `-d` — wait between iterations
- Auto-detection of project type (Python, Node.js, Rust, Go) during `ralph init`
- Test suite for CLI and project detector
