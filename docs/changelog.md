---
description: Ralphify release history — new features, bug fixes, and breaking changes across all versions.
---

# Changelog

All notable changes to ralphify are documented here.

## 0.1.7 — Unreleased

Renamed "prompt" to "ralph" everywhere, simplified the CLI, and added a spinner during iterations.

### Breaking changes

- **Renamed `.ralph/` directory to `.ralphify/`** — if you have an existing `.ralph/` directory, rename it to `.ralphify/`. All primitive discovery, `ralph new`, and `ralph status` now use the new path.
- **Renamed "prompt" primitive to "ralph"** — `PROMPT.md` marker files are now `RALPH.md`. The `--prompt` flag on `ralph new` is now `--ralph`. Named prompts in `.ralph/prompts/` are now named ralphs in `.ralphify/ralphs/`.
- **Removed `ralph ralphs` and `ralph ui` subcommands** — `ralph new <name>` is now shorthand for `ralph new ralph <name>`. The `ui` subcommand was removed (the web dashboard is not yet available).

### Added

- **Spinner with elapsed time** — iterations now show a live spinner with elapsed seconds instead of a blank wait, so you can see the agent is still working.

### Fixed

- Agent result message is now displayed in CLI output after each iteration.
- Raw Claude Code `stream-json` output no longer leaks to the terminal during iterations.
- Web dashboard page now clearly marked as "Coming Soon" to prevent users from trying non-existent commands.

### Improved

- Extracted shared scanning logic in `_discovery.py` to reduce duplication across primitive types.
- Added `PrimitiveEntry` type annotations for better code clarity.
- Moved `merge_by_name` to `_discovery.py` and deduplicated checks discovery logic.
- Updated codebase map and contributing docs to match the renamed source structure.

### Migration guide

If you're upgrading from 0.1.6:

1. **Rename the directory**: `mv .ralph .ralphify`
2. **Rename marker files**: If you had custom `PROMPT.md` files in named prompts, rename them to `RALPH.md`
3. **Update `ralph.toml`**: The `ralph` field still works the same way — it can be a file path or a named ralph name
4. **Update scripts**: If you had scripts referencing `ralph ralphs` or `ralph ui`, remove those calls

---

## 0.1.6 — 2026-03-12

Named ralphs, ralph-scoped primitives, live agent activity streaming, and a redesigned dashboard with persistent history.

### Added

- **Named ralphs** — save reusable, task-focused ralphs in `.ralphify/ralphs/<name>/RALPH.md` and switch between them with `ralph run <name>`. Create with `ralph new ralph <name>`. The `ralph` field in `ralph.toml` also accepts a ralph name.
- **`--ralph` flag on `ralph new`** — scope checks, contexts, and instructions to a named ralph with `ralph new check <name> --ralph <ralph>`. Creates the primitive inside `.ralphify/ralphs/<ralph>/` so it only applies when running that ralph.
- **`--prompt-file` / `-f` flag** — point `ralph run` at any prompt file by path, overriding `ralph.toml`.
- **Ralphs in Configure** — browse, create, edit, and delete named ralphs alongside other primitives in the Configure tab. Each ralph shows as an interactive card with description, content preview, and edit button.
- **Redesigned dashboard to three tabs** — the dashboard now uses three tabs (Runs, Configure, History). The History tab shows rich run cards with visual pass rates and status badges. The Configure tab has an overview dashboard with drill-down views and inline editors for creating, editing, and deleting ralphs, checks, contexts, and instructions.
- **Dashboard reads `ralph.toml`** — the UI reads `command` and `args` from your project's `ralph.toml` so it no longer hardcodes agent configuration.
- **Responsive dashboard** — the dashboard adapts to tablets (≤ 900px) and phones (≤ 600px) with a collapsible slide-out sidebar, tighter spacing, and adjusted modal widths.
- **Ralph preview in New Run modal** — expand a preview panel to see the full ralph content before launching a run.
- **Run buttons in Configure** — each ralph card in the Configure tab has a "Run" button (visible on hover, always on mobile) and the ralph editor has a "Run this ralph" header button. Both open the New Run modal with the ralph pre-selected, connecting the configure and run workflows.
- **Command and timeout in Configure** — the Configure tab now shows editable command and timeout fields for checks and contexts, so you can see and change what each primitive runs without leaving the browser.
- **WebSocket event type reference** — dashboard docs now include a complete table of all event types and their data fields.
- **Codebase migration cookbook recipe** — step-by-step guide for automating JavaScript-to-TypeScript migrations, with adaptation tips for Python 2→3, CommonJS→ESM, and more.
- **Contributor docs** — new `docs/contributing/` section with a codebase map, replacing the old `agent_docs/` directory.
- **Iterations API endpoint** — `GET /api/runs/{run_id}/iterations` returns persisted iteration data with per-check results, enabling History tab drill-downs and custom reporting.
- **Persistent run history** — the dashboard stores run history, iterations, and check results in a SQLite database at `~/.ralphify/ui.db` that survives across restarts.
- **Keyboard shortcuts in dashboard** — press Cmd+S / Ctrl+S to save changes in primitive editors and create forms. Escape closes the New Run modal.
- **History runs API endpoint** — `GET /api/history/runs` returns all persisted runs from the SQLite store, enabling custom history queries and reporting.
- **Live agent activity stream** — when the agent command is Claude Code, the dashboard streams tool calls, text output, and cost/token stats in real time during each iteration. The engine auto-detects Claude Code and uses `--output-format stream-json` with `subprocess.Popen` for line-by-line streaming. Other agents continue to use the standard `subprocess.run()` path. The activity feed shows color-coded tool badges (Read, Edit, Bash, Grep, etc.) with expandable results and auto-scrolling.
- **Iteration activity API endpoint** — `GET /api/runs/{run_id}/iterations/{iteration}/activity` returns raw agent activity events for a specific iteration, enabling replay of what the agent did step-by-step.

### Fixed

- `RUN_STOPPED` event now emits exactly once with the correct stop reason (`completed` vs `user_requested`) for user-requested stops.
- Windows compatibility fix for Unicode characters in terminal output (contributed by [@mikkel-kaj](https://github.com/mikkel-kaj)).
- New Run modal closes on Escape key press.
- Running runs show a pulse animation on their status badge.
- First run is auto-selected on page load.
- Crashed iteration details and history labels display correctly.

### Improved

- CI now validates the docs build on pull requests, catching broken documentation before merge.
- Dashboard ralph cards strip markdown formatting and use line-clamp for cleaner content previews.

### Internal

- Extracted `ConsoleEmitter` from `cli.py` into dedicated `_console_emitter.py` module.
- Extracted scaffold templates from `cli.py` into `_templates.py`.
- Centralized primitive marker filenames and primitives directory name into constants in `_frontmatter.py`.
- Major engine refactoring: extracted helper functions, reduced parameter counts, replaced untyped tuples with `NamedTuple`, and encapsulated `RunState` threading internals.
- Event types use `EventType` enums instead of raw strings.
- `FanoutEmitter` moved to `_events` module alongside other emitter implementations.
- Event handler dispatch uses bound methods in `ConsoleEmitter` and `Store`.
- FastAPI dependency injection replaces module-level `_manager` global.
- Event serialization moved into `Event.to_dict()` method.

---

## 0.1.5 — 2026-03-11

Redesigned New Run modal and polished dashboard styling.

### Added

- **Redesigned New Run modal** — the modal now features a card-based ralph picker, clearer section labels with icons, and a collapsible settings panel instead of exposing every field at once.
- **Ralph card grid** — named ralphs display as selectable cards with descriptions, replacing the old chip-style buttons.
- **Ad-hoc prompt mode** — users can toggle between selecting a named ralph and typing a one-off prompt directly in the modal.

### Improved

- Dashboard CSS overhaul — new modal layout classes, better spacing, softer card styling, and consistent use of the Dusk design system.
- Simplified New Run form state — replaced single config object with focused individual state hooks for clarity.
- Updated project prompt (`RALPH.md`) to focus on UI/design iteration with the Dusk palette and design principles.

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
