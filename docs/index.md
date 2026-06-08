---
title: Ralphify — the runtime for loop engineering
description: Ralphify is the runtime for loop engineering. Ralph loops (ralphloops.io) is the open, standard format for writing an autonomous agent loop; ralphify is the runtime that runs it.
keywords: loop engineering, ralphify, ralph loops, ralph loops format, RALPH.md, ralphloops.io, agent loop runtime, autonomous agent loop
hide:
  - toc
---

<p align="center">
  <img src="assets/cli-banner.png" alt="Ralphify CLI banner" style="max-width: 500px;" />
</p>

<p align="center" style="font-size: 1.3em; margin-top: -0.5em;">
<strong>Ralphify is the runtime for loop engineering.</strong>
</p>

*Loop engineering* — designing autonomous agent loops instead of prompting turn by turn — is becoming how people get real work out of coding agents. You write a loop once and let it drive the agent for hours, one commit at a time.

**[Ralph loops](https://ralphloops.io/) is the open, standard format for writing one.** A ralph loop is a portable directory — a prompt, the commands to run between iterations, and any files the agent needs — whose one required file is `RALPH.md`. Because the format is a standard, a loop is portable: write it once, commit the directory, and anyone with ralphify can run it.

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

Each iteration starts with a **fresh context window** and **current data** — ralphify runs the commands, fills in the `{{ placeholders }}`, pipes the prompt to your agent, and loops.

*Works with any agent CLI. Swap `claude -p` for Codex, Aider, or your own — just change the `agent` field.*

[Get Started](getting-started.md){ .md-button .md-button--primary }
[The ralph loops format](https://ralphloops.io/){ .md-button }

---

## What is loop engineering?

**Loop engineering is the practice of designing autonomous agent loops** — instead of steering a coding agent turn by turn, you engineer a loop that drives it for you. A loop has three parts: a **prompt** (what the agent should do each pass), **commands** that pull in live data (test results, coverage, git log), and a **runtime** that assembles the prompt, runs the agent, and repeats with fresh context.

Loop engineering is becoming how people get sustained, autonomous work out of coding agents — hours of progress, one commit at a time. It rests on two pieces:

- **[Ralph loops](https://ralphloops.io/) — the format.** An open, standard way to write a loop as a portable directory (`RALPH.md`). Because it's a standard, loops are shareable and reusable across people and projects.
- **Ralphify — the runtime.** The `ralph` CLI that runs a loop: run commands → assemble the prompt → pipe it to your agent → loop.

Write the loop once in the standard format, and ralphify runs it for as long as you want.

---

## Install

```bash
uv tool install ralphify
```

---

## What you do with ralphify

Working with ralphify comes down to a few things — write a ralph, feed it live data, run the loop, steer it while it runs, and share it. That's the whole tool.

<div class="grid cards" markdown>

-   :material-file-document-edit-outline:{ .lg .middle } **Write a ralph**

    ---

    Scaffold a directory with a `RALPH.md` — YAML frontmatter for config, a markdown body for the prompt. The only required field is `agent`; add `args` to parameterize the loop with `{{ args.<name> }}`.

    ```bash
    ralph scaffold my-ralph
    ```

    [Getting Started →](getting-started.md)

-   :material-database-arrow-down-outline:{ .lg .middle } **Feed it live data**

    ---

    `commands` run each iteration; their output fills `{{ commands.<name> }}` in the prompt. The agent always sees current test results, coverage, and git log — a self-healing feedback loop.

    [How it works →](cli.md#how-the-loop-works)

-   :material-play-circle-outline:{ .lg .middle } **Run the loop**

    ---

    `ralph run` assembles the prompt, pipes it to your agent, and repeats with fresh context. Loop until `Ctrl+C` or cap it with `-n`.

    ```bash
    ralph run my-ralph -n 5
    ```

    [CLI reference →](cli.md)

-   :material-pencil-outline:{ .lg .middle } **Steer it while it runs**

    ---

    The prompt is re-read every iteration. Edit `RALPH.md` mid-run and the agent follows your new rules next cycle. When it does something dumb, add a sign.

    [Getting Started →](getting-started.md#step-7-steer-while-it-runs)

-   :material-share-variant-outline:{ .lg .middle } **Share a ralph**

    ---

    This is what the standard format buys you. A ralph is a portable directory in the open [ralph loops format](https://ralphloops.io/) — commit it, push it, and anyone with ralphify can run it.

    ```bash
    git clone https://github.com/owner/repo
    ralph run my-ralph
    ```

</div>

---

## Why loop engineering works

A single agent run fixes a bug or writes a function. The leverage of loop engineering is **sustained, autonomous work** — a ralph loop runs for hours, one commit at a time, while you do something else.

- **Fresh context, no decay.** Each iteration starts with a clean context window. The agent reads the current state of the codebase every loop — no conversation bloat, no degradation.
- **Commands as feedback.** Command output feeds into the prompt each iteration. When tests fail, the agent sees the failure and fixes it next cycle.
- **Steer with a text file.** Edit `RALPH.md` while the loop runs to redirect a running agent.
- **Progress lives in git.** Every iteration commits. `git log` shows what happened; `git reset` rolls it back.

---

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or [any agent CLI](cli.md#using-different-agents) that accepts piped input)

---

## Next steps

- **[Getting Started](getting-started.md)** — from install to a running loop in 10 minutes
- **[Reference](cli.md)** — the CLI, RALPH.md format, how the loop works, agents, troubleshooting, and the Python API
- **[The ralph loops format](https://ralphloops.io/)** — the open, standard spec ralphify implements
