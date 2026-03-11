# Contributing

Ralphify is open source (MIT) and welcomes contributions. This page covers everything you need to set up a development environment, run tests, and submit changes.

## Development setup

Clone the repository and install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/computerlovetech/ralphify.git
cd ralphify
uv sync
```

This installs all runtime and dev dependencies (pytest, mkdocs, mkdocs-material) into a local virtual environment.

Verify the setup by running the CLI from source:

```bash
uv run ralph --version
```

## Running tests

The test suite uses pytest with one test file per source module:

```bash
uv run pytest           # Run all tests
uv run pytest -x        # Stop on first failure
uv run pytest -v        # Verbose output
```

Tests use temporary directories and have no external dependencies — no API keys, no network access, no Docker.

### Test structure

```
tests/
├── test_cli.py           # CLI commands (init, run, status, new)
├── test_checks.py        # Check discovery and execution
├── test_contexts.py      # Context discovery and injection
├── test_instructions.py  # Instruction discovery and resolution
├── test_runner.py        # Command execution with timeout
├── test_detector.py      # Project type detection
└── test_output.py        # Output combining and truncation
```

When adding a new feature, add tests in the corresponding file. If you're adding a new module, create a matching `test_<module>.py` file.

## Working on documentation

The docs site uses [MkDocs](https://www.mkdocs.org/) with the [Material](https://squidfunk.github.io/mkdocs-material/) theme.

### Local preview

```bash
uv run mkdocs serve
```

This starts a local server at `http://127.0.0.1:8000` with live reload — edits to docs files appear instantly in the browser.

### Build check

```bash
uv run mkdocs build --strict
```

The `--strict` flag treats warnings as errors. The CI pipeline uses this flag, so make sure your changes build cleanly before submitting.

### Docs structure

```
docs/
├── index.md              # Landing page
├── why-ralphify.md       # Design philosophy and comparison to alternatives
├── getting-started.md    # Step-by-step tutorial
├── how-it-works.md       # Iteration lifecycle and prompt assembly
├── prompts.md            # Prompt writing guide
├── best-practices.md     # Habits and patterns for productive loops
├── agents.md             # Setup guides for different agents
├── cookbook.md            # Complete copy-pasteable setups
├── quick-reference.md    # Single-page lookup of all commands and syntax
├── primitives.md         # Checks, contexts, instructions reference
├── cli.md                # Configuration and CLI reference
├── faq.md                # Common questions
├── troubleshooting.md    # Debugging guide
├── contributing.md       # This page
├── changelog.md          # Version history
└── assets/               # Images
```

Navigation is configured in `mkdocs.yml`. If you add a new page, add it to the `nav` section there.

## Project architecture

All source code lives in `src/ralphify/`. Here's how the pieces fit together:

```
src/ralphify/
├── __init__.py         # Version detection + entry point
├── cli.py              # All CLI commands and the main loop
├── checks.py           # Check discovery, execution, failure formatting
├── contexts.py         # Context discovery, execution, prompt injection
├── instructions.py     # Instruction discovery and prompt injection
├── resolver.py         # Shared template placeholder resolution
├── detector.py         # Project type auto-detection
├── _runner.py          # Shell command execution with timeout
├── _frontmatter.py     # YAML frontmatter parsing and primitive discovery
└── _output.py          # Output combining and truncation
```

**Key entry points:**

- **`cli.py`** is the main file. The `run()` function (the core loop) lives here, along with all CLI commands and scaffold templates.
- **`_frontmatter.py`** handles primitive discovery — scanning `.ralph/` directories for marker files and parsing their frontmatter.
- **`resolver.py`** handles template placeholder resolution (`{{ contexts.name }}`, `{{ instructions }}`), shared by both contexts and instructions.

### How the loop works

```
ralph run
  ├── Load config from ralph.toml
  ├── Discover checks, contexts, instructions from .ralph/
  └── Loop:
       ├── Read PROMPT.md from disk
       ├── Run context commands → resolve {{ contexts.* }} placeholders
       ├── Resolve {{ instructions.* }} placeholders
       ├── Append check failures from previous iteration
       ├── Pipe assembled prompt to agent via subprocess stdin
       ├── Run checks → store failures for next iteration
       └── Repeat
```

### Things to know before making changes

**Primitive marker filenames** (`CHECK.md`, `CONTEXT.md`, `INSTRUCTION.md`) are hardcoded in each module's `discover_*()` function AND in the scaffold templates in `cli.py`. If you change one, update both.

**Frontmatter field types** — the `timeout` and `enabled` fields get special type coercion in `_frontmatter.py:parse_frontmatter()`. Adding a new typed field requires updating the coercion logic there.

**Placeholder resolution** — both contexts and instructions use the same `resolver.py:resolve_placeholders()` function. Changes here affect both.

**Output truncation** — `_output.py:truncate_output()` caps check and context output at 5,000 characters. This is intentional to prevent context window bloat.

## Submitting changes

1. **Fork and branch** — create a feature branch from `main`:

    ```bash
    git checkout -b my-feature
    ```

2. **Make your changes** — keep commits focused and atomic.

3. **Run tests** — make sure all tests pass:

    ```bash
    uv run pytest
    ```

4. **Check the docs** — if you changed anything in `docs/` or `mkdocs.yml`:

    ```bash
    uv run mkdocs build --strict
    ```

5. **Open a pull request** against `main` with a clear description of what you changed and why.

### Commit messages

The project uses descriptive commit messages that explain the user benefit:

```
docs: explain X for users who want to Y
feat: add X so users can Y
fix: resolve X that caused Y
```

Look at `git log --oneline` for examples of the style.

## Dependencies

Ralphify is minimal by design:

- **Runtime:** `typer` (CLI framework) and `rich` (terminal formatting) — nothing else
- **Dev:** `pytest`, `mkdocs`, `mkdocs-material`

Think carefully before adding a new dependency. If it can be done with the standard library, prefer that.

## Release process

Releases are published to PyPI automatically when a GitHub release is created:

1. Update the version in `pyproject.toml`
2. Create a GitHub release with a tag matching the version (e.g. `v0.1.4`)
3. The `publish.yml` workflow runs tests, builds the package, verifies the version matches the tag, and publishes to PyPI

Docs deploy automatically to GitHub Pages on every push to `main` that changes files in `docs/` or `mkdocs.yml`.
