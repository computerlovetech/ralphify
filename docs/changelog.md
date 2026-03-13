---
description: Ralphify release history — new features, bug fixes, and breaking changes across all versions.
---

# Changelog

All notable changes to ralphify are documented here.

## 0.1.7 — Unreleased

Simplified the CLI, added a spinner during iterations, and removed the experimental web dashboard to focus on the CLI experience.

### Breaking changes

- **Removed `ralph ui` subcommand and web dashboard** — the experimental web dashboard introduced in 0.1.6 has been removed. The dashboard depended on FastAPI, React, and SQLite, adding significant complexity for a feature that wasn't ready for production use. All dashboard-related API endpoints, persistent history, and WebSocket streaming have been removed. The core agent streaming (Claude Code auto-detection with `--output-format stream-json`) remains — it's used by the CLI for live activity tracking.
- **Removed `ralph ralphs` subcommand** — `ralph new <name>` is now shorthand for `ralph new ralph <name>`.

### Added

- **Spinner with elapsed time** — iterations now show a live spinner with elapsed seconds instead of a blank wait, so you can see the agent is still working.

### Fixed

- Agent result message is now displayed in CLI output after each iteration.
- Raw Claude Code `stream-json` output no longer leaks to the terminal during iterations.

### Improved

- Introduced `Primitive` protocol in `_discovery.py` so all four primitive types (`Check`, `Context`, `Instruction`, `Ralph`) share a typed interface for discovery, filtering, merging, and display.
- Added generic `_discover_and_filter_enabled()` in the engine, replacing per-type boilerplate with a single code path bounded by the `Primitive` protocol.
- Moved check result serialization into `CheckResult.to_event_data()` so event data formatting has a single source of truth.
- Added missing event data fields (`result_text`, `detail`, `duration_formatted`) to API docs so library users see what the engine actually emits.
- Extracted shared scanning logic in `_discovery.py` to reduce duplication across primitive types.
- Moved `merge_by_name` to `_discovery.py` and deduplicated checks discovery logic.
- Updated codebase map and contributing docs to match the current architecture.

---

## 0.1.6 — 2026-03-12

Named ralphs, ralph-scoped primitives, and live agent activity streaming.

### Added

- **Named ralphs** — save reusable, task-focused ralphs in `.ralphify/ralphs/<name>/RALPH.md` and switch between them with `ralph run <name>`. Create with `ralph new ralph <name>`. The `ralph` field in `ralph.toml` also accepts a ralph name.
- **`--ralph` flag on `ralph new`** — scope checks, contexts, and instructions to a named ralph with `ralph new check <name> --ralph <ralph>`. Creates the primitive inside `.ralphify/ralphs/<ralph>/` so it only applies when running that ralph.
- **`--ralph-file` / `-f` flag** — point `ralph run` at any prompt file by path, overriding `ralph.toml`.
- **Live agent activity streaming** — when the agent command is Claude Code, the engine auto-detects it and uses `--output-format stream-json` with `subprocess.Popen` for line-by-line streaming. Other agents continue to use the standard `subprocess.run()` path.
- **Codebase migration cookbook recipe** — step-by-step guide for automating JavaScript-to-TypeScript migrations, with adaptation tips for Python 2→3, CommonJS→ESM, and more.
- **Contributor docs** — new `docs/contributing/` section with a codebase map, replacing the old `agent_docs/` directory.

### Added (experimental — removed in 0.1.7)

The following features were part of an experimental web dashboard that was removed in 0.1.7. They are listed here for historical completeness.

- Web dashboard with Runs, Configure, and History tabs
- Dashboard API endpoints for runs, iterations, and activity replay
- Persistent run history in SQLite (`~/.ralphify/ui.db`)
- WebSocket-based live event streaming to the dashboard
- Ralph management UI (browse, create, edit, delete named ralphs)
- Keyboard shortcuts in dashboard editors (Cmd+S / Ctrl+S to save)

### Fixed

- `RUN_STOPPED` event now emits exactly once with the correct stop reason (`completed` vs `user_requested`) for user-requested stops.
- Windows compatibility fix for Unicode characters in terminal output (contributed by [@mikkel-kaj](https://github.com/mikkel-kaj)).

### Improved

- CI now validates the docs build on pull requests, catching broken documentation before merge.

### Internal

- Extracted `ConsoleEmitter` from `cli.py` into dedicated `_console_emitter.py` module.
- Extracted scaffold templates from `cli.py` into `_templates.py`.
- Centralized primitive marker filenames and primitives directory name into constants in `_frontmatter.py`.
- Major engine refactoring: extracted helper functions, reduced parameter counts, replaced untyped tuples with `NamedTuple`, and encapsulated `RunState` threading internals.
- Event types use `EventType` enums instead of raw strings.
- `FanoutEmitter` moved to `_events` module alongside other emitter implementations.
- Event serialization moved into `Event.to_dict()` method.

---

## 0.1.5 — 2026-03-11

Dashboard UI polish (experimental — dashboard removed in 0.1.7).

!!! note "Dashboard removed"
    All features in this release were part of the experimental web dashboard, which was removed in 0.1.7. This entry is kept for historical completeness.

### Added

- Redesigned New Run modal with card-based ralph picker and collapsible settings panel.
- Ralph card grid for selecting named ralphs with descriptions.
- Ad-hoc prompt mode toggle in the New Run modal.

### Improved

- Dashboard CSS overhaul for consistent styling.

---

## 0.1.4 — 2026-03-11

Ad-hoc prompts, better discoverability, and expanded cookbook recipes.

### Added

- **Ad-hoc prompts** — `ralph run -p "Fix the login bug"` passes a prompt directly on the command line, bypassing `RALPH.md` entirely. Useful for quick one-off tasks. Placeholders (contexts and instructions) resolve as normal.
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

- **Checks** — post-iteration validation scripts in `.ralphify/checks/`. When a check fails, its output is fed into the next iteration so the agent can fix its own mistakes. Supports both `command` in frontmatter and `run.*` scripts.
- **Contexts** — dynamic data injection in `.ralphify/contexts/`. Run a command before each iteration and inject its output into the prompt via `{{ contexts.name }}` placeholders. Static-only contexts (no command) are also supported.
- **Instructions** — reusable prompt rules in `.ralphify/instructions/`. Toggle coding standards, commit conventions, or safety constraints on and off without editing `RALPH.md`. Use `{{ instructions }}` or `{{ instructions.name }}` in the prompt.
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

- `ralph init` — create `ralph.toml` and `RALPH.md` in your project
- `ralph run` — the core autonomous loop: read prompt, pipe to agent, repeat
- Iteration tracking with exit codes and duration
- `--stop-on-error` / `-s` — halt the loop if the agent exits non-zero
- `-n` — limit the number of iterations
- `--delay` / `-d` — wait between iterations
- Auto-detection of project type (Python, Node.js, Rust, Go) during `ralph init`
- Test suite for CLI and project detector
