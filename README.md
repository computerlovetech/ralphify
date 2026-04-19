<p align="center">
  <img src="cli-graphic.png" alt="ralphify" />
</p>

<p align="center">
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/v/ralphify?color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ralphify/"><img src="https://img.shields.io/pypi/pyversions/ralphify" alt="Python versions"></a>
  <a href="https://github.com/computerlovetech/ralphify/blob/main/LICENSE"><img src="https://img.shields.io/github/license/computerlovetech/ralphify" alt="License"></a>
  <a href="https://ralphify.co/docs/"><img src="https://img.shields.io/badge/docs-ralphify.co%2Fdocs-blue" alt="Documentation"></a>
</p>

**A ralph is a directory that defines an autonomous agent loop.** It bundles a prompt, commands, and any files your agent needs. Ralphify is the CLI runtime that executes them.

```
grow-coverage/
├── RALPH.md               # the prompt (only required file)
├── check-coverage.sh      # command that runs each iteration
└── testing-conventions.md  # context for the agent
```

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: coverage
    run: ./check-coverage.sh
---

You are an autonomous coding agent working in a loop.
Each iteration, write tests for one untested module, then stop.

Follow the conventions in testing-conventions.md.

## Current coverage

{{ commands.coverage }}
```

```bash
ralph run grow-coverage     # loops until Ctrl+C
```

That's it. One directory. One command. The agent loops — running commands, building a fresh prompt with the latest output, and piping it to your agent. Every iteration starts with clean context and current data.

*Works with any agent CLI. Swap `claude -p` for Codex, Aider, or your own — just change the `agent` field.*

## Why loops

A single agent run can fix a bug or write a function. But the real leverage is **sustained, autonomous work** — campaigns that run for hours, chipping away at a goal one commit at a time while you do something else.

Ralph loops give you:

- **Incremental progress in small chunks.** Each iteration does one thing, tests it, and commits. Small changes are easier to review and safer to ship.
- **Fresh context every iteration.** No context window bloat. The agent starts clean each loop and sees the current state of the codebase — including everything it changed last iteration.
- **Continuous work toward a goal.** The loop keeps running until you hit Ctrl+C or it reaches the iteration limit. Walk away, come back to a pile of commits.
- **No micromanagement.** Define the goal once in the prompt, tune with commands that feed live data back in. The agent figures out what to do next.
- **The prompt is a tuning knob.** When the agent does something dumb, add a rule. Like putting up a sign: "SLIDE DOWN, DON'T JUMP."

### What people build ralphs for

| Ralph | What it does |
|---|---|
| **grow-coverage** | Write tests for untested modules, one per iteration, until coverage hits the target |
| **security-audit** | Hunt for vulnerabilities — scan, find, fix, verify, repeat |
| **clear-backlog** | Work through a TODO list or issue tracker, one task per loop |
| **promise-completion** | Work until a target is done, then emit a promise tag so the loop stops early |
| **write-docs** | Generate documentation for undocumented modules, one at a time |
| **improve-codebase** | Find and fix code smells, refactor patterns, modernize APIs |
| **migrate** | Incrementally migrate files from one framework or pattern to another |
| **research** | Deep-dive into a topic — gather sources, synthesize, and build a knowledge base |
| **bug-hunter** | Run the test suite, find edge cases, write regression tests |
| **perf-sweep** | Profile, find bottlenecks, optimize, benchmark, repeat |

The ralph format is intentionally simple — if you've written a skill file or a GitHub Action, you already know how it works. YAML frontmatter for config, markdown body for the prompt, `{{ commands.name }}` placeholders for live data.

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

Scaffold a ralph and start experimenting:

```bash
ralph scaffold my-ralph
```

The scaffolded `RALPH.md` includes the normal command/arg template plus a commented promise-completion path you can enable if the agent should stop early by emitting a matching `<promise>...</promise>` tag.

For a committed example, see [`examples/promise-completion/RALPH.md`](examples/promise-completion/RALPH.md) — it shows a loop that exits early once the requested target is complete.

Edit `my-ralph/RALPH.md`, then run it:

```bash
ralph run my-ralph           # loops until Ctrl+C
ralph run my-ralph -n 5      # run 5 iterations then stop
# from a repo checkout:
ralph run examples/promise-completion -n 10 --target "stabilize the failing auth tests"
```

### What `ralph run` does

Each iteration:
1. **Runs commands** — executes all commands in the ralph, captures output
2. **Builds prompt** — reads the RALPH.md body, replaces `{{ commands.<name> }}` placeholders with fresh output
3. **Pipes to agent** — runs the agent command with the assembled prompt on stdin
4. **Repeats** — goes back to step 1 with updated data

### What it looks like

```
$ ralph run grow-coverage -n 3

▶ Running: grow-coverage
  1 command · max 3 iterations

── Iteration 1 ──
  Commands: 1 ran
✓ Iteration 1 completed (52.3s)

── Iteration 2 ──
  Commands: 1 ran
✗ Iteration 2 failed with exit code 1 (23.1s)

── Iteration 3 ──
  Commands: 1 ran
✓ Iteration 3 completed (41.7s)

──────────────────────
Done: 3 iterations — 2 succeeded, 1 failed
```

## The ralph format

A **ralph** is a directory containing a `RALPH.md` file. Everything the ralph needs lives in that directory — scripts, reference docs, test data, whatever the agent might need.

```
my-ralph/
├── RALPH.md              # the prompt (required)
├── check-coverage.sh     # script (optional)
├── style-guide.md        # reference doc (optional)
└── test-data.json        # any supporting file (optional)
```

**RALPH.md** has YAML frontmatter for configuration and a markdown body that becomes the prompt:

| Frontmatter field | Required | Description |
|---|---|---|
| `agent` | Yes | The agent command to run |
| `commands` | No | List of commands (name + run) whose output fills `{{ commands.<name> }}` placeholders |
| `args` | No | Declared argument names for `{{ args.<name> }}` placeholders |
| `credit` | No | Append co-author trailer instruction to prompt (default: `true`) |

**Commands** run before each iteration. Their output replaces `{{ commands.<name> }}` placeholders in the prompt. Use them for test results, coverage reports, git history, lint output — anything that changes between iterations.

## The technique

The Ralph Wiggum technique works because:

- **One thing per loop.** The agent picks the most important task, implements it, tests it, and commits. Then the next iteration starts fresh.
- **Fresh context every time.** No context window bloat. Each loop starts clean and reads the current state of the codebase.
- **Progress lives in git.** Code, commits, and a plan file are the only state that persists between iterations. If something goes wrong, `git reset --hard` and run more loops.

Read the full writeup: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/)

## Share ralphs

Use [agr](https://github.com/computerlovetech/agr) to install shared ralphs from GitHub:

```bash
agr add owner/repo/grow-coverage   # install a ralph from GitHub
ralph run grow-coverage            # run it by name
```

Ralphs installed by agr go to `.agents/ralphs/` and are automatically discovered by `ralph run`.

## Documentation

Full documentation at **[ralphify.co/docs](https://ralphify.co/docs/)** — getting started tutorial, format spec, cookbook, CLI reference, and troubleshooting.

## Requirements

- Python 3.11+
- An agent CLI that accepts piped input ([Claude Code](https://docs.anthropic.com/en/docs/claude-code), Codex, Aider, or your own)

## License

MIT
