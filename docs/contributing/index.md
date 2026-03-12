---
description: Set up a ralphify development environment, run tests, understand the architecture, and submit pull requests.
---

# Contributing

Ralphify is open source (MIT) and welcomes contributions. This page covers everything you need to set up a development environment, run tests, and submit changes.

For architecture details and codebase orientation, see the [Codebase Map](codebase-map.md).

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
├── conftest.py            # Shared fixtures (disables streaming path for all tests)
├── test_checks.py         # Check discovery and execution
├── test_cli.py            # CLI commands (init, run, status, new, ralphs)
├── test_contexts.py       # Context discovery and injection
├── test_detector.py       # Project type detection
├── test_discovery.py      # Primitive directory scanning (discover_local_primitives)
├── test_engine.py         # Core run loop and RunState/RunConfig
├── test_instructions.py   # Instruction discovery and resolution
├── test_manager.py        # Multi-run orchestration
├── test_output.py         # Output combining and truncation
├── test_persistence.py    # UI persistence layer (SQLite)
├── test_ralphs.py         # Named ralph discovery and resolution
├── test_resolver.py       # Template placeholder resolution (named, bulk, implicit)
├── test_runner.py         # Command execution with timeout
└── ...
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
├── ralphs.md             # Ralph writing guide
├── best-practices.md     # Habits and patterns for productive loops
├── agents.md             # Setup guides for different agents
├── cookbook.md            # Complete copy-pasteable setups
├── quick-reference.md    # Single-page lookup of all commands and syntax
├── primitives.md         # Checks, contexts, instructions reference
├── cli.md                # Configuration and CLI reference
├── faq.md                # Common questions
├── troubleshooting.md    # Debugging guide
├── contributing/         # Contributor docs (this section)
│   ├── index.md          # This page
│   └── codebase-map.md   # Architecture and module guide
├── changelog.md          # Version history
└── assets/               # Images
```

Navigation is configured in `mkdocs.yml`. If you add a new page, add it to the `nav` section there.

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
