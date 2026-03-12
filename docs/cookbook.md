---
description: Copy-pasteable ralphify setups for Python, TypeScript, Rust, Go, bug fixing, documentation, GitHub Actions CI, and more.
---

# Cookbook

Complete, copy-pasteable setups for common use cases. Each example includes the full configuration — `ralph.toml`, `RALPH.md`, checks, and contexts — so you can get a productive loop running quickly.

## Python library development

Ship features from a plan file, with test and lint guardrails.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.git-log }}

Read PLAN.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Run `uv run pytest -x` before committing
- Commit with a descriptive message like `feat: add X` or `fix: resolve Y`
- Mark the completed task in PLAN.md

{{ instructions }}
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: uv run pytest -x
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip or delete tests.
Do not add `# type: ignore` or `# noqa` comments.
```

**`.ralphify/checks/lint/CHECK.md`**

```markdown
---
command: uv run ruff check .
timeout: 60
enabled: true
---
Fix all lint errors. Do not suppress warnings with noqa comments.
```

### Context

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check tests
ralph new check lint
ralph new context git-log
```

Then edit each file to match the contents above, create a `PLAN.md` with your tasks, and run:

```bash
ralph run -n 3 --log-dir ralph_logs
```

---

## Test-driven bug fixing

Point the agent at a failing test suite and let it fix bugs one at a time.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are a bug-fixing agent running in a loop. Each iteration starts
with a fresh context. Your progress lives in the code and git.

{{ contexts.test-status }}

Run `uv run pytest` to see failing tests. Pick one failure, trace
the root cause in the source code, fix it, and verify the fix passes.

## Rules

- Fix one bug per iteration
- Do NOT modify the test unless the test itself is wrong
- Do NOT add `# type: ignore` or `# noqa` comments
- Always run the full test suite after your fix to check for regressions
- Commit with `fix: <description of what was broken and why>`
- If all tests pass, do nothing and exit cleanly
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: uv run pytest
timeout: 180
enabled: true
---
A test is still failing after your fix. Run `pytest -x` to find the
first failure, read the full traceback, and fix the root cause.
Do not modify tests unless they are incorrect.
```

### Context

**`.ralphify/contexts/test-status/CONTEXT.md`**

```markdown
---
command: uv run pytest --tb=line -q
timeout: 60
enabled: true
---
## Current test status
```

This context gives the agent a snapshot of which tests are failing before it starts, so it can pick the most important one without running the full suite first. Ralphify automatically truncates output to 5,000 characters, so you don't need to limit it yourself.

!!! note "Need pipes or redirections?"
    Commands are parsed with `shlex` and run directly — not through a shell. If you need pipes (`|`), redirections (`2>&1`), or other shell features, use a [`run.sh` script](primitives.md#using-a-script-instead-of-a-command) instead.

### Setup commands

```bash
ralph init
ralph new check tests
ralph new context test-status
```

Edit files to match, then run:

```bash
ralph run --stop-on-error --log-dir ralph_logs
```

!!! tip "Use `--stop-on-error` for bug fixing"
    When all tests pass, the agent exits cleanly (exit code 0). When there's nothing left to fix, `--stop-on-error` isn't strictly needed — but it prevents wasted iterations if the agent itself errors out.

---

## Documentation writing

Improve project documentation one page at a time. This is the pattern ralphify uses on its own docs.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous documentation agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.git-log }}

Read the codebase and existing docs. Identify the biggest gap between
what the code can do and what the docs explain. Write or improve one
page per iteration.

## Rules

- Do one meaningful documentation improvement per iteration
- Search before creating anything new
- No placeholder content — full, accurate, useful writing only
- Verify any code examples actually run before committing
- Commit with a descriptive message like `docs: explain X for users who want to Y`
```

### Checks

**`.ralphify/checks/docs-build/CHECK.md`**

```markdown
---
command: uv run mkdocs build --strict
timeout: 60
enabled: true
---
The docs build failed. Fix any warnings or errors in the markdown files.
Check for broken cross-links, missing pages in mkdocs.yml nav, and
invalid admonition syntax.
```

### Context

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check docs-build
ralph new context git-log
```

---

## Node.js / TypeScript project

Feature development in a TypeScript project with type checking and test guardrails.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.git-log }}

Read TODO.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Run `npm test` before committing
- Run `npx tsc --noEmit` to check types before committing
- Commit with a descriptive message
- Mark the completed task in TODO.md

{{ instructions }}
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: npm test
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip tests with `.skip` or delete them.
```

**`.ralphify/checks/typecheck/CHECK.md`**

```markdown
---
command: npx tsc --noEmit
timeout: 60
enabled: true
---
Fix all type errors. Do not use `// @ts-ignore` or `as any`.
```

**`.ralphify/checks/lint/CHECK.md`**

```markdown
---
command: npx eslint .
timeout: 60
enabled: true
---
Fix all lint errors. Do not disable rules with eslint-disable comments.
```

### Context

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check tests
ralph new check typecheck
ralph new check lint
ralph new context git-log
```

---

## Rust project

Feature development in a Rust project with cargo tests and clippy linting.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.git-log }}

Read PLAN.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Run `cargo test` before committing
- Run `cargo clippy` and fix all warnings before committing
- Commit with a descriptive message

{{ instructions }}
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: cargo test
timeout: 180
enabled: true
---
Fix all failing tests. Do not ignore or delete tests.
Do not add `#[ignore]` attributes to skip tests.
```

**`.ralphify/checks/clippy/CHECK.md`**

```markdown
---
command: cargo clippy -- -D warnings
timeout: 60
enabled: true
---
Fix all clippy warnings. Do not suppress warnings with `#[allow(...)]`
unless there is a genuine reason documented in a comment.
```

**`.ralphify/checks/fmt/CHECK.md`**

```markdown
---
command: cargo fmt --check
timeout: 30
enabled: true
---
Run `cargo fmt` to fix formatting. Do not manually adjust formatting.
```

### Context

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check tests
ralph new check clippy
ralph new check fmt
ralph new context git-log
```

Edit each file to match the contents above, create a `PLAN.md` with your tasks, and run:

```bash
ralph run -n 3 --log-dir ralph_logs
```

---

## Go project

Feature development in a Go project with tests, vet, and staticcheck.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.git-log }}

Read PLAN.md for the current task list. Pick the top uncompleted task,
implement it fully, then mark it done.

## Rules

- One task per iteration
- No placeholder code — full, working implementations only
- Run `go test ./...` before committing
- Run `go vet ./...` and fix all issues before committing
- Commit with a descriptive message

{{ instructions }}
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: go test ./...
timeout: 180
enabled: true
---
Fix all failing tests. Do not skip tests with `t.Skip()` or delete them.
```

**`.ralphify/checks/vet/CHECK.md`**

```markdown
---
command: go vet ./...
timeout: 60
enabled: true
---
Fix all issues reported by `go vet`. These are likely bugs, not style issues.
```

### Context

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check tests
ralph new check vet
ralph new context git-log
```

Edit each file to match, create a `PLAN.md` with your tasks, and run:

```bash
ralph run -n 3 --log-dir ralph_logs
```

!!! tip "Adding staticcheck"
    If you use [staticcheck](https://staticcheck.dev/), add it as a third check:

    ```bash
    ralph new check staticcheck
    ```

    ```markdown
    ---
    command: staticcheck ./...
    timeout: 60
    enabled: true
    ---
    Fix all staticcheck findings. Do not suppress with `//nolint` comments.
    ```

---

## Adding instructions for coding standards

Instructions are reusable rules you can toggle on and off without editing the prompt. They're useful for enforcing coding standards across different ralphs.

**`.ralphify/instructions/code-style/INSTRUCTION.md`**

```markdown
---
enabled: true
---
## Coding standards

- Always use type hints on function signatures
- Keep functions under 30 lines — extract helpers if needed
- Use `logging` module instead of `print()` for any diagnostic output
- Prefer early returns over deeply nested conditions
- Write docstrings for all public functions and classes
```

**`.ralphify/instructions/git-conventions/INSTRUCTION.md`**

```markdown
---
enabled: true
---
## Git conventions

- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Keep commits atomic — one logical change per commit
- Write commit messages in imperative mood: "add feature" not "added feature"
```

Reference them in your prompt:

```markdown
{{ instructions }}

Now implement the next feature from the plan.
```

Or place specific ones:

```markdown
{{ instructions.code-style }}

Read PLAN.md and pick the next task.

{{ instructions.git-conventions }}
```

---

## Using a script-based check

For validation logic that's more complex than a single command, use a `run.sh` or `run.py` script instead of a frontmatter `command`.

**`.ralphify/checks/integration/CHECK.md`**

```markdown
---
timeout: 300
enabled: true
---
Integration tests failed. Check the test output above for details.
Make sure the API server is configured correctly and all endpoints
return the expected responses.
```

**`.ralphify/checks/integration/run.sh`**

```bash
#!/bin/bash
set -e

# Start a test server in the background
python -m myapp.server --port 9999 &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT

# Wait for it to be ready
sleep 2

# Run integration tests against it
pytest tests/integration/ -x --timeout=30
```

Make the script executable:

```bash
chmod +x .ralphify/checks/integration/run.sh
```

When both a `command` in frontmatter and a `run.*` script exist, the script takes precedence.

---

## Running in GitHub Actions

Run ralphify as a GitHub Actions workflow — useful for automated bug fixing, documentation generation, or scheduled code maintenance.

### Workflow

Create `.github/workflows/ralph-loop.yml`:

```yaml
name: Ralph Loop

on:
  workflow_dispatch:
    inputs:
      iterations:
        description: "Number of iterations to run"
        default: "5"
        type: string

permissions:
  contents: write

jobs:
  loop:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install tools
        run: |
          pip install ralphify
          npm install -g @anthropic-ai/claude-code

      - name: Run ralph loop
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          ralph run \
            -n ${{ inputs.iterations }} \
            --stop-on-error \
            --timeout 300 \
            --log-dir ralph-logs

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ralph-logs
          path: ralph-logs/

      - name: Push changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "chore: apply changes from ralph loop"
          git push
```

### Key settings for CI

| Setting | Why |
|---|---|
| `-n 5` | Cap iterations to control cost and runtime |
| `--stop-on-error` | Stop immediately if the agent fails instead of burning credits |
| `--timeout 300` | Kill stuck iterations after 5 minutes |
| `--log-dir ralph-logs` | Capture output so you can debug via artifacts |

### Tips for CI usage

**Store your API key as a repository secret.** Go to Settings → Secrets and variables → Actions and add `ANTHROPIC_API_KEY`. Never hardcode keys in the workflow file.

**Use `workflow_dispatch` for manual control.** This lets you choose how many iterations to run each time. You can also add a `schedule` trigger for recurring loops:

```yaml
on:
  schedule:
    - cron: "0 9 * * 1-5"  # 9 AM UTC on weekdays
  workflow_dispatch:
    inputs:
      iterations:
        default: "5"
        type: string
```

**Create a PR instead of pushing directly.** For safer workflows, open a pull request so you can review the agent's changes before merging:

```yaml
      - name: Create pull request
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BRANCH="ralph/run-$(date +%Y%m%d-%H%M%S)"
          git checkout -b "$BRANCH"
          git add -A
          git diff --staged --quiet && exit 0
          git commit -m "chore: apply changes from ralph loop"
          git push -u origin "$BRANCH"
          gh pr create \
            --title "Ralph loop: automated changes" \
            --body "Automated changes from ralph loop run." \
            --base main
```

!!! note "Adapt for your agent"
    This example uses Claude Code, but ralphify works with any CLI that reads stdin. Replace the agent install step and environment variables to match your agent. See [Using with Different Agents](agents.md) for setup guides.

---

## Increase test coverage

Systematically improve test coverage by having the agent write tests for uncovered modules, one at a time.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous test-writing agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.coverage }}

Read the coverage report above. Find the module with the lowest coverage
that has meaningful logic worth testing. Write thorough tests for that
module — cover the happy path, edge cases, and error conditions.

## Rules

- One module per iteration — write all tests for it, then move on
- Write tests that verify behavior, not implementation details
- Do NOT modify source code to make it easier to test — test it as-is
- Do NOT use mocks unless testing external dependencies (APIs, databases)
- Run the full test suite before committing to check for regressions
- Commit with `test: add tests for <module name>`
- Skip modules that already have 90%+ coverage

{{ instructions }}
```

### Checks

**`.ralphify/checks/tests/CHECK.md`**

```markdown
---
command: uv run pytest -x
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip or delete existing tests.
If a new test is failing, the test is likely wrong — fix the test,
not the source code.
```

**`.ralphify/checks/coverage-threshold/CHECK.md`**

This check ensures overall coverage doesn't decrease. Use a `run.sh` script since we need shell features (pipes, exit codes based on output):

```markdown
---
timeout: 120
enabled: true
---
Coverage has dropped below the minimum threshold. Check which tests
are missing and add them. Do not lower the threshold.
```

**`.ralphify/checks/coverage-threshold/run.sh`**

```bash
#!/bin/bash
set -e

# Run coverage and check minimum threshold (adjust percentage as needed)
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

### Context

**`.ralphify/contexts/coverage/CONTEXT.md`**

This context shows the agent which modules need tests:

```markdown
---
timeout: 60
enabled: true
---
## Current test coverage
```

**`.ralphify/contexts/coverage/run.sh`**

```bash
#!/bin/bash
# Show per-module coverage so the agent can pick the lowest-covered module
uv run pytest --cov=src --cov-report=term-missing -q 2>/dev/null || true
```

!!! note "Why `|| true`?"
    Context output is captured regardless of exit code, so `|| true` isn't strictly needed for ralphify. However, it ensures the script exits cleanly if you run it manually outside of ralphify (e.g. during debugging), and prevents errors if you later add `set -e` to the script.

### Setup commands

```bash
ralph init
ralph new check tests
ralph new check coverage-threshold
ralph new context coverage
```

Create the `run.sh` scripts:

```bash
# Coverage threshold check script
cat > .ralphify/checks/coverage-threshold/run.sh << 'EOF'
#!/bin/bash
set -e
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
EOF
chmod +x .ralphify/checks/coverage-threshold/run.sh

# Coverage context script
cat > .ralphify/contexts/coverage/run.sh << 'EOF'
#!/bin/bash
uv run pytest --cov=src --cov-report=term-missing -q 2>/dev/null || true
EOF
chmod +x .ralphify/contexts/coverage/run.sh
```

Edit the CHECK.md and CONTEXT.md files to match the contents above, then run:

```bash
ralph run -n 5 --log-dir ralph_logs
```

!!! tip "Adapt the coverage command"
    Replace `--cov=src` with the path to your source code. For Node.js, swap `pytest --cov` for `npx jest --coverage` or `npx c8 report`. The pattern works the same — the context shows what's uncovered, the check enforces a minimum threshold.

---

## Codebase migration

Automate systematic, file-by-file migrations — JavaScript to TypeScript, Python 2 to 3, CommonJS to ESM, or any codebase-wide transformation. The agent migrates one file per iteration, checks validate the result, and a context tracks progress.

This recipe shows a JavaScript-to-TypeScript migration. Adapt the commands and rules for your specific migration.

### Configuration

**`ralph.toml`**

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

**`RALPH.md`**

```markdown
# Prompt

You are an autonomous migration agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

{{ contexts.migration-status }}
{{ contexts.git-log }}

Migrate one JavaScript file to TypeScript per iteration. Pick the file
with the fewest dependencies on other unmigrated files (leaf nodes first).

## Rules

- One file per iteration — rename `.js` → `.ts` (or `.tsx`), add types, fix imports
- Do NOT use `any` — write proper types for all function signatures and variables
- Do NOT change behavior — the migration must be a pure type-layer addition
- Update import paths in other files that reference the migrated file
- Run the type checker and fix all errors before committing
- Run tests to verify nothing broke
- Commit with `refactor: migrate <filename> to TypeScript`
- If all `.js` files are migrated, do nothing and exit cleanly

{{ instructions }}
```

### Checks

**`.ralphify/checks/01-typecheck/CHECK.md`**

```markdown
---
command: npx tsc --noEmit
timeout: 120
enabled: true
---
Fix all type errors introduced by the migration. Do not use `any` or
`// @ts-ignore`. Write proper types for every function, parameter,
and return value.
```

**`.ralphify/checks/02-tests/CHECK.md`**

```markdown
---
command: npm test
timeout: 180
enabled: true
---
The migration broke a test. The file's behavior must not change during
migration — only types are added. Revert any accidental behavior changes
and fix the type errors differently.
```

**`.ralphify/checks/03-lint/CHECK.md`**

```markdown
---
command: npx eslint . --ext .ts,.tsx,.js,.jsx
timeout: 60
enabled: true
---
Fix all lint errors. Do not disable rules with eslint-disable comments.
```

### Contexts

**`.ralphify/contexts/migration-status/CONTEXT.md`**

Use a script to show which files still need migrating:

```markdown
---
timeout: 15
enabled: true
---
## Migration progress
```

**`.ralphify/contexts/migration-status/run.sh`**

```bash
#!/bin/bash
# Count remaining .js files vs .ts files in the source directory
JS_COUNT=$(find src -name '*.js' -o -name '*.jsx' | wc -l | tr -d ' ')
TS_COUNT=$(find src -name '*.ts' -o -name '*.tsx' | wc -l | tr -d ' ')
TOTAL=$((JS_COUNT + TS_COUNT))

echo "Files migrated: $TS_COUNT / $TOTAL"
echo "Remaining .js files: $JS_COUNT"
echo ""

if [ "$JS_COUNT" -gt 0 ]; then
    echo "Files still to migrate:"
    find src -name '*.js' -o -name '*.jsx' | sort
fi
```

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

### Setup commands

```bash
ralph init
ralph new check 01-typecheck
ralph new check 02-tests
ralph new check 03-lint
ralph new context migration-status
ralph new context git-log
```

Create the migration status script:

```bash
cat > .ralphify/contexts/migration-status/run.sh << 'SCRIPT'
#!/bin/bash
JS_COUNT=$(find src -name '*.js' -o -name '*.jsx' | wc -l | tr -d ' ')
TS_COUNT=$(find src -name '*.ts' -o -name '*.tsx' | wc -l | tr -d ' ')
TOTAL=$((JS_COUNT + TS_COUNT))
echo "Files migrated: $TS_COUNT / $TOTAL"
echo "Remaining .js files: $JS_COUNT"
echo ""
if [ "$JS_COUNT" -gt 0 ]; then
    echo "Files still to migrate:"
    find src -name '*.js' -o -name '*.jsx' | sort
fi
SCRIPT
chmod +x .ralphify/contexts/migration-status/run.sh
```

Edit each CHECK.md and CONTEXT.md to match the contents above, then run:

```bash
ralph run -n 3 --log-dir ralph_logs   # test with a few files first
```

Review the first 3 migrations, then scale up:

```bash
ralph run --log-dir ralph_logs --stop-on-error
```

!!! tip "Adapt for other migrations"
    This pattern works for any systematic codebase transformation:

    - **Python 2 → 3**: Replace the type checker with `python -m py_compile`, add a `pyupgrade` check, update the context to count `print` statements or other Python 2 patterns
    - **CommonJS → ESM**: Check for remaining `require()` calls, validate with a bundler build
    - **REST → GraphQL**: Track endpoints migrated vs remaining, validate with schema checks
    - **Class components → hooks**: Count class components remaining, run tests after each conversion

    The key ingredients are always the same: a context that shows what's left, checks that validate each step, and a prompt that tells the agent to do one file at a time.

---

## Static context (no command)

Contexts don't need a command — you can use them for static text that you want to inject without editing the prompt file.

**`.ralphify/contexts/architecture/CONTEXT.md`**

```markdown
---
enabled: true
---
## Project architecture

- `src/api/` — HTTP handlers and routing
- `src/core/` — Business logic, no framework dependencies
- `src/db/` — Database access layer (PostgreSQL)
- `tests/unit/` — Unit tests for core logic
- `tests/integration/` — API endpoint tests

All new features should follow this layering: handler → core → db.
Never import from `src/api/` in `src/core/`.
```

This gets injected into the prompt every iteration, giving the agent a map of the project without running any command.
