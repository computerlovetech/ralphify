<p align="center">
  <img src="cli-graphic.png" alt="ralphify" />
</p>

<p align="center">
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/v/ralphify?color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/pyversions/ralphify" alt="Python versions"></a>
  <a href="https://github.com/computerlovetech/ralphify/blob/main/LICENSE"><img src="https://img.shields.io/github/license/computerlovetech/ralphify" alt="License"></a>
  <a href="https://ralphify.co/docs/"><img src="https://img.shields.io/badge/docs-ralphify.co%2Fdocs-blue" alt="Documentation"></a>
</p>

**Ralphify is the runtime for loop engineering.**

*Loop engineering* — designing autonomous agent loops instead of prompting turn by turn — is becoming how people get real work out of coding agents. You write a loop once and let it drive the agent for hours, one commit at a time.

**[Ralph loops](https://ralphloops.io/) is the open, standard format for writing one.** A ralph loop is a portable directory — a prompt, the commands to run between iterations, and any files the agent needs — with one required file: `RALPH.md`. Because the format is a standard, a loop is portable: write it once, commit the directory, and anyone can run it.

**Ralphify is the runtime that runs it.**

```
grow-coverage/
├── RALPH.md               # the loop definition (required)
└── check-coverage.sh      # a command that runs each iteration
```

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: coverage
    run: ./check-coverage.sh
---

Each iteration, write tests for one untested module, then stop.

## Current coverage

{{ commands.coverage }}
```

```bash
ralph run grow-coverage     # loops until Ctrl+C
```

That's loop engineering in three lines: a prompt, a command for live data, and the runtime. Each iteration starts with a **fresh context window** and **current data** — ralphify runs the commands, fills in the `{{ placeholders }}`, pipes the prompt to your agent, and loops. Walk away, come back to a pile of commits.

*Works with any agent CLI. Swap `claude -p` for Codex, Pi, or your own — just change the `agent` field.*

## Install

```bash
uv tool install ralphify
```

This gives you the `ralph` command.

---

## What you do with ralphify

Working with ralphify comes down to a few things — write a ralph, feed it live data, run the loop, steer it while it runs, and share it. That's the whole tool.

### Write a ralph

A ralph is a *directory* containing a `RALPH.md` file — that file is the only requirement, and its shape is defined by the open [ralph loops format](https://ralphloops.io/). Scaffold one:

```bash
ralph scaffold my-ralph
```

`RALPH.md` is YAML frontmatter + a markdown prompt. The only required field is `agent`:

```markdown
---
agent: claude -p --dangerously-skip-permissions
---

Read TODO.md, pick the top unfinished task, implement it fully, commit, then stop.
One task per iteration. No placeholder code.
```

The format has three frontmatter fields — `agent`, `commands` (live data, see below), and `args` (user arguments that parameterize the loop). `args` lets one ralph be reused with different inputs:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
args:
  - focus
---

Refactor the code under {{ args.focus }}. Keep tests green.

{{ commands.tests }}
```

```bash
ralph run my-ralph --focus src/auth     # {{ args.focus }} → src/auth
```

### Feed it live data

`commands` run before each iteration. Their output replaces `{{ commands.<name> }}` in the prompt, so the agent always sees the current state — test results, coverage, git log, lint output:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
---

## Test results

{{ commands.tests }}

If tests are failing, fix them before starting new work.
```

When the agent breaks a test, the next iteration sees the failure and fixes it. That's the self-healing feedback loop.

### Run the loop

```bash
ralph run my-ralph           # loops until Ctrl+C
ralph run my-ralph -n 5      # run 5 iterations then stop
```

Each iteration: run commands → assemble the prompt → pipe it to the agent → repeat with fresh context.

### Steer it while it runs

The prompt body is re-read from disk every iteration. Edit `RALPH.md` while the loop runs and the agent follows your new rules on the next cycle. When it does something dumb, add a sign:

```markdown
## Rules

- Do NOT delete failing tests — fix the underlying code instead.
```

### Share a ralph

This is what the standard format buys you. Because a ralph is just a directory in the open [ralph loops format](https://ralphloops.io/), it's portable — and anyone with ralphify can run it. Commit it to git, push it, and your loop engineering becomes someone else's starting point:

```bash
git clone https://github.com/owner/repo   # grab a shared ralph
ralph run grow-coverage                   # run it by name
```

---

## Why loop engineering works

Instead of prompting an agent turn by turn, you write the loop once and let it drive the agent for you. A single agent run can fix a bug or write a function. The leverage of a ralph loop is **sustained, autonomous work** — running for hours, one commit at a time, while you do something else.

- **Fresh context every iteration.** No context-window bloat. The agent starts clean and reads the current state of the codebase.
- **Commands as feedback.** Live data feeds back into the prompt each loop, so the agent self-corrects.
- **Steer with a text file.** Edit the prompt mid-run to redirect a running agent.
- **Progress lives in git.** Every iteration commits. `git log` shows what happened; `git reset` rolls it back.

Read the original writeup: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/).

## Documentation

Full docs at **[ralphify.co/docs](https://ralphify.co/docs/)** — getting started, the loop lifecycle, CLI reference, and cookbook. The format spec lives at **[ralphloops.io](https://ralphloops.io/)**.

## Requirements

- Python 3.11+
- An agent CLI that accepts piped input ([Claude Code](https://docs.anthropic.com/en/docs/claude-code), Codex, Pi, or your own)

## License

MIT
