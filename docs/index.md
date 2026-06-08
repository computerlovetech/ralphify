---
title: Ralphify — the runtime for ralph loops
description: Ralphify runs ralph loops — an open format for autonomous agent loops (ralphloops.io). A ralph loop is a directory with a RALPH.md file. Ralphify runs it.
keywords: ralphify, ralph loops, ralph loops format, RALPH.md, ralphloops.io, agent loop runtime, autonomous agent loop
hide:
  - toc
---

<p align="center">
  <img src="assets/cli-banner.png" alt="Ralphify CLI banner" style="max-width: 500px;" />
</p>

<p align="center" style="font-size: 1.3em; margin-top: -0.5em;">
<strong>Ralphify runs ralph loops.</strong>
</p>

A **ralph loop** is a portable directory that defines an autonomous agent loop — a prompt, the commands to run between iterations, and any files the agent needs. It's a directory-based format ([ralphloops.io](https://ralphloops.io/)), like skills: a directory that must contain a `RALPH.md` file. **Ralphify** is the CLI that runs it.

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

## Install

=== "uv (recommended)"

    ```bash
    uv tool install ralphify
    ```

=== "pipx"

    ```bash
    pipx install ralphify
    ```

=== "pip"

    ```bash
    pip install ralphify
    ```

---

## The five things you do with ralphify

Everything in ralphify is one of these five jobs. That's the whole tool.

<div class="grid cards" markdown>

-   :material-file-document-edit-outline:{ .lg .middle } **1. Write a ralph**

    ---

    Scaffold a directory with a `RALPH.md` — YAML frontmatter for config, a markdown body for the prompt. The only required field is `agent`.

    ```bash
    ralph scaffold my-ralph
    ```

    [Getting Started →](getting-started.md)

-   :material-database-arrow-down-outline:{ .lg .middle } **2. Feed it live data**

    ---

    `commands` run each iteration; their output fills `{{ commands.<name> }}` in the prompt. The agent always sees current test results, coverage, and git log — a self-healing feedback loop.

    [How it works →](how-it-works.md)

-   :material-play-circle-outline:{ .lg .middle } **3. Run the loop**

    ---

    `ralph run` assembles the prompt, pipes it to your agent, and repeats with fresh context. Loop until `Ctrl+C` or cap it with `-n`.

    ```bash
    ralph run my-ralph -n 5
    ```

    [CLI reference →](cli.md)

-   :material-pencil-outline:{ .lg .middle } **4. Steer it while it runs**

    ---

    The prompt is re-read every iteration. Edit `RALPH.md` mid-run and the agent follows your new rules next cycle. When it does something dumb, add a sign.

    [Getting Started →](getting-started.md#step-7-steer-while-it-runs)

-   :material-share-variant-outline:{ .lg .middle } **5. Share and install ralphs**

    ---

    A ralph is a portable directory in the [ralph loops format](https://ralphloops.io/). Version it in git, share it, install it from GitHub with [agr](https://github.com/computerlovetech/agr).

    ```bash
    agr add owner/repo/my-ralph
    ```

</div>

---

## Why loops

A single agent run fixes a bug or writes a function. The leverage of a ralph loop is **sustained, autonomous work** — running for hours, one commit at a time, while you do something else.

- **Fresh context, no decay.** Each iteration starts with a clean context window. The agent reads the current state of the codebase every loop — no conversation bloat, no degradation.
- **Commands as feedback.** Command output feeds into the prompt each iteration. When tests fail, the agent sees the failure and fixes it next cycle.
- **Steer with a text file.** Edit `RALPH.md` while the loop runs to redirect a running agent.
- **Progress lives in git.** Every iteration commits. `git log` shows what happened; `git reset` rolls it back.

---

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or [any agent CLI](agents.md) that accepts piped input)

---

## Next steps

- **[Getting Started](getting-started.md)** — from install to a running loop in 10 minutes
- **[How it Works](how-it-works.md)** — what happens inside each iteration
- **[Cookbook](cookbook.md)** — copy-pasteable ralph loops to start from
- **[The ralph loops format](https://ralphloops.io/)** — the open spec ralphify implements
