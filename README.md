<p align="center">
  <img src="cli-graphic.png" alt="ralphify" />
</p>

<p align="center">
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/v/ralphify?color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/pyversions/ralphify" alt="Python versions"></a>
  <a href="https://github.com/computerlovetech/ralphify/blob/main/LICENSE"><img src="https://img.shields.io/github/license/computerlovetech/ralphify" alt="License"></a>
  <a href="https://computerlovetech.github.io/ralphify/"><img src="https://img.shields.io/badge/docs-computerlovetech.github.io%2Fralphify-blue" alt="Documentation"></a>
</p>

Put your AI coding agent in a `while True` loop and let it ship.

Ralphify is a minimal harness for running autonomous AI coding loops, inspired by the [Ralph Wiggum technique](https://ghuntley.com/ralph/). The idea is simple: pipe a prompt to an AI coding agent, let it do one thing, commit, and repeat. Forever. Until you hit Ctrl+C.

```
while :; do cat PROMPT.md | claude -p ; done
```

Ralphify wraps this pattern into a proper tool with config, iteration tracking, and clean shutdown.

## Install

```bash
uv tool install ralphify    # recommended
```

Or if you don't have `uv`:

```bash
pipx install ralphify       # isolated install via pipx
pip install ralphify         # plain pip (use a virtualenv or --user)
```

Any of these gives you the `ralph` command.

## Quickstart

```bash
# In your project directory
ralph init      # Creates ralph.toml + PROMPT.md
ralph run       # Starts the loop (Ctrl+C to stop)
```

That's it. Two commands.

Or skip setup entirely with an ad-hoc prompt:

```bash
ralph run -n 1 -p "Add type hints to all public functions in src/"
```

### What `ralph init` creates

**`ralph.toml`** — tells ralphify what command to run:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
```

**`PROMPT.md`** — a starter prompt template. This file IS the prompt. It gets piped directly to your agent each iteration. Edit it to fit your project.

### What `ralph run` does

Reads the prompt, pipes it to the agent, waits for it to finish, then does it again. Each iteration gets a fresh context window. Progress lives in the code and in git.

```bash
ralph run          # Run forever
ralph run -n 10    # Run 10 iterations then stop
ralph run -p "Fix the login bug"   # Ad-hoc prompt, no PROMPT.md needed
```

### What it looks like

```
$ ralph run -n 3 --log-dir ralph_logs

── Iteration 1 ──
✓ Iteration 1 completed (52.3s) → ralph_logs/001_20250115-142301.log
  Checks: 2 passed
    ✓ lint
    ✓ tests

── Iteration 2 ──
✗ Iteration 2 failed with exit code 1 (23.1s)
  Checks: 1 passed, 1 failed
    ✓ lint
    ✗ tests (exit 1)

── Iteration 3 ──
✓ Iteration 3 completed (41.7s) → ralph_logs/003_20250115-143012.log
  Checks: 2 passed
    ✓ lint
    ✓ tests

Done: 3 iteration(s) — 2 succeeded, 1 failed
```

Iteration 2 broke a test. Iteration 3 automatically received the failure output and fixed it — that's the self-healing loop in action.

## The technique

The Ralph Wiggum technique works because:

- **One thing per loop.** The agent picks the most important task, implements it, tests it, and commits. Then the next iteration starts fresh.
- **Fresh context every time.** No context window bloat. Each loop starts clean and reads the current state of the codebase.
- **Progress lives in git.** Code, commits, and a plan file are the only state that persists between iterations. If something goes wrong, `git reset --hard` and run more loops.
- **The prompt is a tuning knob.** When the agent does something dumb, you add a sign. Like telling Ralph not to jump off the slide — you add "SLIDE DOWN, DON'T JUMP" to the prompt.

Read the full writeup: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/)

## Beyond the basic loop

The simple loop works, but ralphify's real power comes from four primitives that live in the `.ralph/` directory.

### Checks — the self-healing loop

Checks validate the agent's work after each iteration. When one fails, its output automatically feeds into the next iteration so the agent can fix its own mistakes.

```bash
ralph new check tests
```

Edit `.ralph/checks/tests/CHECK.md`:

```markdown
---
command: uv run pytest -x
timeout: 120
---
Fix all failing tests. Do not skip or delete tests.
```

Now the loop self-corrects:

```
Iteration 1 → Agent adds feature → tests pass ✓ → moves on
Iteration 2 → Agent adds feature → tests fail ✗
Iteration 3 → Agent sees failure output → fixes tests → pass ✓
```

You define what "valid" means. Ralphify feeds failures back automatically.

### Contexts — dynamic data injection

Contexts inject fresh data into the prompt each iteration — git history, test status, anything a shell command can produce.

```bash
ralph new context git-log
```

Edit `.ralph/contexts/git-log/CONTEXT.md`:

```markdown
---
command: git log --oneline -10
---
## Recent commits
```

The command runs before each iteration. Use `{{ contexts.git-log }}` in your `PROMPT.md` to control where the output appears.

### Instructions — reusable rules

Instructions are static text blocks (coding standards, commit conventions) you can toggle on and off without editing the prompt.

```bash
ralph new instruction code-style
```

Drop `{{ instructions }}` into `PROMPT.md` to inject all enabled instructions.

### Prompts — named task switcher

Keep multiple prompts for different jobs and switch between them at run time:

```bash
ralph new prompt docs
ralph new prompt refactor
```

Edit `.ralph/prompts/docs/PROMPT.md` with your documentation-focused prompt, then:

```bash
ralph run docs           # Use the "docs" prompt
ralph run refactor -n 5  # Use "refactor" for 5 iterations
```

List available prompts with `ralph prompts list`.

## Web dashboard

Manage runs from your browser with `ralph ui`:

```bash
uv tool install "ralphify[ui]"   # one-time: add dashboard dependencies
ralph ui                          # opens http://127.0.0.1:8765
```

The dashboard lets you start and stop runs, browse named prompts, watch iterations stream in live, and edit checks/contexts/instructions — all without touching the terminal. See the [dashboard docs](https://computerlovetech.github.io/ralphify/dashboard/) for the full walkthrough.

## Customizing your prompt

The generated `PROMPT.md` is a starting point. A good prompt for autonomous loops typically includes:

- What to work on (specs, plan file, TODO list)
- Constraints — what NOT to do (no placeholders, no skipping tests)
- Process — how to validate and commit

The agent reads this prompt fresh every iteration, so you can edit it while the loop is running. When the agent does something dumb, add a sign to the prompt — the next iteration follows the new rules.

## Documentation

Full documentation at **[computerlovetech.github.io/ralphify](https://computerlovetech.github.io/ralphify/)** — tutorials, cookbook, prompt writing guide, and troubleshooting.

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or any agent CLI that accepts piped input)

## License

MIT
