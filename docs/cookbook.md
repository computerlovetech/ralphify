---
description: Copy-pasteable ralphify setups for Python, TypeScript, bug fixing, documentation, test coverage, and GitHub Actions CI.
---

# Cookbook

Copy-pasteable setups for common use cases. Each recipe includes the prompt, checks, and contexts you need.

All recipes use the same `ralph.toml` (created by `ralph init`):

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```

---

## Python library development

Ship features from a plan file, with test and lint guardrails.

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

**`.ralphify/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -10
timeout: 10
enabled: true
---
## Recent commits
```

```bash
ralph init
ralph new check tests
ralph new check lint
ralph new context git-log
# Edit each file to match above, create PLAN.md, then:
ralph run -n 3 --log-dir ralph_logs
```

---

## Test-driven bug fixing

Point the agent at a failing test suite and let it fix bugs one at a time.

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

**`.ralphify/contexts/test-status/CONTEXT.md`**

```markdown
---
command: uv run pytest --tb=line -q
timeout: 60
enabled: true
---
## Current test status
```

```bash
ralph init
ralph new check tests
ralph new context test-status
# Edit files to match, then:
ralph run --stop-on-error --log-dir ralph_logs
```

---

## Documentation writing

Improve project documentation one page at a time.

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

```bash
ralph init
ralph new check docs-build
ralph new context git-log
```

---

## Node.js / TypeScript project

**`RALPH.md`** — same structure as Python, with different commands:

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

**Checks:**

```markdown
# .ralphify/checks/tests/CHECK.md
---
command: npm test
timeout: 120
enabled: true
---
Fix all failing tests. Do not skip tests with `.skip` or delete them.
```

```markdown
# .ralphify/checks/typecheck/CHECK.md
---
command: npx tsc --noEmit
timeout: 60
enabled: true
---
Fix all type errors. Do not use `// @ts-ignore` or `as any`.
```

```markdown
# .ralphify/checks/lint/CHECK.md
---
command: npx eslint .
timeout: 60
enabled: true
---
Fix all lint errors. Do not disable rules with eslint-disable comments.
```

!!! tip "Other languages"
    The same pattern works for Rust (`cargo test`, `cargo clippy`), Go (`go test ./...`, `go vet ./...`), or any language with a test runner and linter. Just swap the commands.

---

## Increase test coverage

Uses script-based checks and contexts to track and enforce coverage.

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
- Run the full test suite before committing to check for regressions
- Commit with `test: add tests for <module name>`
- Skip modules that already have 90%+ coverage
```

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

**`.ralphify/checks/coverage-threshold/run.sh`** (script-based — needs shell features):

```bash
#!/bin/bash
set -e
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

**`.ralphify/checks/coverage-threshold/CHECK.md`**

```markdown
---
timeout: 120
enabled: true
---
Coverage has dropped below the minimum threshold. Check which tests
are missing and add them. Do not lower the threshold.
```

**`.ralphify/contexts/coverage/run.sh`**:

```bash
#!/bin/bash
uv run pytest --cov=src --cov-report=term-missing -q 2>/dev/null || true
```

**`.ralphify/contexts/coverage/CONTEXT.md`**

```markdown
---
timeout: 60
enabled: true
---
## Current test coverage
```

Make scripts executable: `chmod +x .ralphify/checks/coverage-threshold/run.sh .ralphify/contexts/coverage/run.sh`

---

## Running in GitHub Actions

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

Store `ANTHROPIC_API_KEY` as a repository secret. Use `-n` and `--stop-on-error` to keep runs bounded.

For safer workflows, create a PR instead of pushing directly — replace the "Push changes" step with:

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
