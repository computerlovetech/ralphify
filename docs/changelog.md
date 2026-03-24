---
title: Ralphify Changelog
description: Ralphify release history — new features, bug fixes, and breaking changes across all versions.
keywords: ralphify changelog, release history, new features, version updates, breaking changes
---

# Changelog

All notable changes to ralphify are documented here.

## 0.2.5 — 2026-03-22

### Added

- **Ralph placeholders** — ralphs can now access runtime metadata via `{{ ralph.name }}` (ralph directory name), `{{ ralph.iteration }}` (current iteration, 1-based), and `{{ ralph.max_iterations }}` (total iterations if `-n` was set, empty otherwise). No frontmatter configuration needed.

---

## 0.2.4 — 2026-03-22

### Fixed

- **Placeholder cross-contamination between args and commands** — when an arg value contained text like `{{ commands.tests }}`, the sequential resolution would re-process it as a command placeholder, injecting unrelated output. Placeholders are now resolved in a single pass so inserted values are never re-scanned.
- **Helpful error when command binary is not found** — when a `commands` entry references a binary that isn't installed (e.g. `run: mypy src/`), the error now identifies which command failed and points to the `commands` field. Previously this surfaced as a generic crash with no context.
- **Timed-out agent output not echoed when logging enabled** — when using `--log-dir` and the agent timed out, partial output was written to the log file but silently swallowed from the terminal. Both completion and timeout paths now echo consistently.
- **`--` separator not ending flag parsing in user args** — `ralph run my-ralph -- --verbose ./src` now correctly treats `--verbose` as a positional value instead of parsing it as a flag.
- **Command output garbled when stdout lacked trailing newline** — when a command's stdout didn't end with a newline and stderr was non-empty, the two streams were concatenated directly (e.g. `"test passedwarning: dep"`), producing garbled output in log files and `{{ commands.* }}` placeholder values.
- **Indented `---` in YAML block scalars mistaken for closing frontmatter delimiter** — the frontmatter parser used `line.strip()` to detect the closing `---`, which caused indented `---` inside YAML block scalars (e.g. `notes: |` with `  ---` content) to be treated as the end of the frontmatter. Now only `---` at column 0 is recognized as the closing delimiter.
- **Indented opening `---` delimiter accepted inconsistently** — the opening frontmatter delimiter check used `strip()` which accepted leading whitespace (e.g. `  ---`), while the closing delimiter required column 0. Both delimiters now require `---` at column 0 per the YAML frontmatter spec.
- **Arg values with spaces breaking command execution** — when `{{ args.name }}` placeholders were substituted into command `run` strings, values containing spaces (e.g. `"hello world"`) were split into separate tokens by `shlex.split`, causing the wrong command to execute. Arg values are now shell-quoted before substitution so they are always treated as single tokens.
- **Helpful error when command has invalid syntax** — when a command's `run` string has malformed shell syntax (e.g. unmatched quotes), the error now identifies which command failed and points to the `commands` field. Previously this surfaced as a bare `ValueError` like "No closing quotation" with no context.
- **Empty arg values breaking `./` working directory detection** — when an `{{ args.name }}` placeholder resolved to an empty string, the substitution could introduce leading whitespace that prevented the `./` prefix from being detected, causing the command to run from the project root instead of the ralph directory.
- **Windows `.cmd`/`.exe` extension breaking streaming mode detection** — on Windows, `claude` is installed as `claude.cmd` or `claude.exe`. The streaming mode check compared the full filename (including extension) against `"claude"`, so it never matched. Ralphify now compares the stem only, enabling real-time activity tracking on Windows.

### Improved

- **`BoundEmitter` convenience methods** — `log_info(message)` and `log_error(message, traceback=...)` let Python API users emit log events without constructing `Event` objects manually.
- **Extracted `ProcessResult` base class** — `RunResult` and `AgentResult` now share a common base with consistent `success` / `timed_out` semantics, reducing duplication in `_runner.py` and `_agent.py`.
- **Code quality** — extracted CLI validation helpers, renamed `resolver.py` to `_resolver.py` to match private module convention, deduplicated output echoing and timeout/blocking paths in `_agent.py`, extracted `ensure_str` helper for consistent bytes-to-string decoding.

---

## 0.2.3 — 2026-03-21

### Added

- **Co-authored-by credit trailer** — every prompt now includes an instruction telling the agent to add `Co-authored-by: Ralphify <noreply@ralphify.co>` to commit messages. On by default; opt out with `credit: false` in RALPH.md frontmatter.

### Improved

- **Typed event payloads** — replaced `dict[str, Any]` event data with TypedDict classes throughout the engine and console emitter for stronger type safety.
- **Code quality** — standardized imports, extracted constants, simplified TypedDicts with `NotRequired`.

---

## 0.2.2 — 2026-03-21

### Added

- **`ralph init` command** — scaffold a new ralph with a ready-to-customize template, no AI agent required. Run `ralph init my-task` to create a directory with a `RALPH.md` that includes example commands, args, and placeholders. A faster alternative to the AI-guided `ralph new`.
- **`ralphify-cowork` skill** — a Claude Cowork skill that lets non-technical users set up and run autonomous loops from plain English. Handles installation, ralph creation, running, and tweaking — no coding knowledge needed. Install it in Cowork from `skills/ralphify-cowork/`.

---

## 0.2.1 — 2026-03-21

### Fixed

- **`{{ args.* }}` placeholders now resolved in command `run` strings** — previously, arg placeholders were only resolved in the prompt body. Commands like `run: gh issue view {{ args.issue }}` would fail because `shlex.split` tokenized the raw placeholder into multiple arguments. Args are now resolved before command execution.

---

## 0.2.0 — 2026-03-21

The v2 rewrite. Ralphify is now simpler: a ralph is a directory with a `RALPH.md` file. No more `ralph.toml`, no more `.ralphify/` directory, no more `ralph init`. Everything lives in one file.

### Breaking changes

- **Removed `ralph.toml`** — the agent command is now in the `agent` field of RALPH.md frontmatter. No separate configuration file.
- **Removed `ralph init`** — create a ralph directory with a `RALPH.md` file manually, or use `ralph new`.
- **Removed `.ralphify/` directory** — no more checks, contexts, or named ralphs as separate primitives. Everything is defined in RALPH.md.
- **Removed checks and contexts** — replaced by `commands` in RALPH.md frontmatter. Commands run each iteration and their output is available via `{{ commands.<name> }}` placeholders.
- **`ralph run` requires a path** — `ralph run my-ralph` instead of `ralph run` with optional name. The argument is a path to a directory containing RALPH.md.
- **Placeholder syntax changed** — `{{ contexts.<name> }}` is now `{{ commands.<name> }}`. The `{{ args.<name> }}` syntax is unchanged.
- **User arguments** — pass named flags to your ralph: `ralph run my-ralph --dir ./src`.

### Added

- **`commands` frontmatter field** — define commands that run each iteration directly in RALPH.md. Each command has a `name` and `run` field.
- **Single-file configuration** — the `agent` field, commands, args, and prompt all live in one RALPH.md file.

### Fixed

- **Guard against double-starting a run** — `RunManager` now prevents the same run from being started twice.
- **Eliminate TOCTOU race in RunManager** — `start_run` is now atomic to prevent race conditions in concurrent runs.
- **UTF-8 encoding for all subprocess calls** — prevents encoding errors on systems with non-UTF-8 defaults.
- **Stricter input validation** — reject whitespace-only agent fields, command names, command `run` values, and command strings. Validate negative delay, non-positive `max_iterations`, and timeout values. Validate `commands` field type and reject duplicate command names. Validate command `timeout` field in frontmatter.
- **Clear command placeholders when no commands exist** — matches the existing behavior for args placeholders.
- **Error handling for `os.execvp` in `ralph new`** — graceful error instead of unhandled exception when the agent binary is not found.

### Improved

- **Extensive test coverage** — added unit tests for `_agent.py`, `_events.py`, `ConsoleEmitter`, engine internals, streaming agent execution, command cwd logic, and frontmatter edge cases.
- **Code quality** — extracted magic strings into named constants, consolidated duplicate test helpers, replaced lambda closures with `functools.partial`, and compiled module-level regexes in the resolver.

### How to upgrade from 0.1.x

1. **Move agent config into RALPH.md** — take the `command` and `args` from `ralph.toml` and combine them into the `agent` field in RALPH.md frontmatter.

2. **Convert checks and contexts to commands** — each check/context becomes a command entry:

    ```yaml
    # Before (separate files):
    # .ralphify/checks/tests/CHECK.md with command: uv run pytest -x
    # .ralphify/contexts/git-log/CONTEXT.md with command: git log --oneline -10

    # After (in RALPH.md frontmatter):
    commands:
      - name: tests
        run: uv run pytest -x
      - name: git-log
        run: git log --oneline -10
    ```

3. **Update placeholders** — change `{{ contexts.<name> }}` to `{{ commands.<name> }}`.

4. **Move RALPH.md into a directory** — create a directory for your ralph and put RALPH.md inside it.

5. **Delete old files** — remove `ralph.toml` and the `.ralphify/` directory.

6. **Update CLI usage** — `ralph run` becomes `ralph run <path>`.

---

## 0.1.12 — 2026-03-20

### Changed

- **New tagline** — updated project tagline to "Stop stressing over not having an agent running. Ralph is always running" across CLI, PyPI, and docs.

---

## 0.1.11 — 2026-03-18

### Improved

- **`ralph new` runs without permission prompts** — Claude Code is now launched with `--dangerously-skip-permissions` so the AI-guided setup flow is uninterrupted.
- **Simpler `ralph new` experience** — the skill no longer asks users about checks, contexts, or frontmatter. Just describe what you want to automate in plain English and the agent builds the ralph for you.
- **`ralph new` knows about user arguments** — the skill can now suggest `{{ args.name }}` placeholders when a ralph would benefit from being reusable across projects.

---

## 0.1.10 — 2026-03-18

### Added

- **User arguments for ralphs** — pass `--name value` flags or positional args to `ralph run` and reference them in prompts with `{{ args.name }}` placeholders. Declare positional arg names in frontmatter with `args: [dir, focus]`. Context and check scripts receive user arguments as `RALPH_ARG_<KEY>` environment variables.
- **Quick reference page** — single-page cheat sheet covering CLI commands, directory structure, frontmatter fields, placeholders, and common patterns.
- **Prompt writing guide** — best practices for writing effective RALPH.md prompts, including tips on scoping, context usage, and user arguments.
- **"How it works" page** — explains the iteration lifecycle so users understand the system model.
- **"When to use" guide** — helps users evaluate whether ralph loops fit their task.
- **Agent comparison table** — side-by-side comparison of supported agents with output behavior notes.
- **Expanded cookbook** — new recipes for Python, TypeScript, Rust, Go, bug fixing, codebase migration, and multi-ralph project setup.

### Fixed

- Malformed `ralph.toml` now shows a helpful error message instead of a raw `KeyError`.

---

## 0.1.9 — 2026-03-16

Tightened the primitive system: global primitives are now opt-in, context placeholders must be named, and primitives are re-discovered every iteration.

### Breaking changes

- **Explicit primitive dependencies required** — global checks and contexts are no longer auto-applied to all ralphs. Each ralph must declare which global primitives it uses in its frontmatter (`checks: [lint, tests]`, `contexts: [git-log]`). Unknown names produce a clear error. Ralph-local primitives still auto-apply.
- **Named placeholders only** — the bulk `{{ contexts }}` placeholder and implicit append behavior have been removed. Each context must be referenced by name (`{{ contexts.git-log }}`). Contexts not referenced by a placeholder are excluded from the prompt.
- **Removed `ralph status` command** — setup validation has been moved into `ralph run` startup, so a separate status command is no longer needed.

### Added

- **Live re-discovery** — primitives are re-discovered every iteration, so adding or editing a check, context, or ralph on disk takes effect on the next cycle without restarting the loop.

---

## 0.1.8 — 2026-03-16

Redesigned `ralph new` with AI-guided setup, and added environment variables for scripts.

### Added

- **AI-guided `ralph new`** — `ralph new` now installs a skill into your agent (Claude Code or Codex) and launches an interactive session where the agent guides you through creating a complete ralph — prompt, checks, and contexts — via conversation. Replaces the old `ralph new check`/`ralph new context`/`ralph new ralph` scaffolding subcommands.
- **`RALPH_NAME` environment variable** — context and check scripts now receive the name of the current ralph in `RALPH_NAME`, so scripts can adapt their behavior based on which ralph is running.

---

## 0.1.7 — 2026-03-12

Simplified the CLI, added a spinner during iterations, and removed the experimental web dashboard to focus on the CLI experience.

### Breaking changes

- **Removed `ralph ui` subcommand and web dashboard** — the experimental web dashboard introduced in 0.1.6 has been removed.
- **Removed `ralph ralphs` subcommand** — `ralph new <name>` is now shorthand for `ralph new ralph <name>`.
- **Removed instructions primitive** — the `instructions` primitive type introduced in 0.1.3 has been removed. Use contexts for injecting reusable rules into prompts instead.
- **Removed ad-hoc prompts (`-p` flag)** — the `--prompt` / `-p` flag on `ralph run` has been removed.

### Added

- **Spinner with elapsed time** — iterations now show a live spinner with elapsed seconds.

### Fixed

- Agent result message is now displayed in CLI output after each iteration.
- Raw Claude Code `stream-json` output no longer leaks to the terminal during iterations.

---

## 0.1.6 — 2026-03-12

Named ralphs, ralph-scoped primitives, and live agent activity streaming.

### Added

- **Named ralphs** — save reusable, task-focused ralphs in `.ralphify/ralphs/<name>/RALPH.md` and switch between them with `ralph run <name>`.
- **Live agent activity streaming** — when the agent command is Claude Code, the engine auto-detects it and uses `--output-format stream-json` with `subprocess.Popen` for line-by-line streaming.
- **Contributor docs** — new `docs/contributing/` section with a codebase map.

### Fixed

- `RUN_STOPPED` event now emits exactly once with the correct stop reason.
- Windows compatibility fix for Unicode characters in terminal output.

---

## 0.1.5 — 2026-03-11

Dashboard UI polish (experimental — dashboard removed in 0.1.7).

---

## 0.1.4 — 2026-03-11

Ad-hoc prompts, better discoverability, and expanded cookbook recipes.

### Added

- **Ad-hoc prompts** — `ralph run -p "Fix the login bug"` passes a prompt directly on the command line.
- **Rust and Go cookbook recipes** — complete copy-pasteable setups.

---

## 0.1.3 — 2026-03-10

The primitives release. Checks, contexts, and instructions turn the basic loop into a self-healing feedback system.

### Added

- **Checks** — post-iteration validation scripts in `.ralphify/checks/`.
- **Contexts** — dynamic data injection in `.ralphify/contexts/`.
- **Instructions** — reusable prompt rules in `.ralphify/instructions/`.

---

## 0.1.2 — 2026-03-09

Quality-of-life improvements for the core loop.

### Added

- `ralph status` command
- `--timeout` / `-t` option
- `--log-dir` / `-l` option
- `--version` / `-V` flag
- ASCII art startup banner

---

## 0.1.0 — 2026-03-09

Initial release.

### Added

- `ralph init` — create `ralph.toml` and `RALPH.md` in your project
- `ralph run` — the core autonomous loop: read prompt, pipe to agent, repeat
- Iteration tracking with exit codes and duration
- `--stop-on-error` / `-s`, `-n`, `--delay` / `-d`
- Auto-detection of project type during `ralph init`
