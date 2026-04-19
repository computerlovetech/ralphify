---
title: Ralphify — a runtime for the ralph format
description: Ralphify is the runtime for the ralph format — a skill-like spec for autonomous agent loops. A ralph is a directory with a RALPH.md file. Ralphify runs it.
keywords: ralphify, ralph format, RALPH.md, autonomous agent loop, agent runtime, harness engineering, skill-like format, ralph spec
hide:
  - toc
---

<p align="center">
  <img src="assets/cli-banner.png" alt="Ralphify CLI banner" style="max-width: 500px;" />
</p>

<p align="center" style="font-size: 1.3em; margin-top: -0.5em;">
<strong>A ralph is a directory that defines an autonomous agent loop. Ralphify runs it.</strong>
</p>

A **ralph** is a directory with a `RALPH.md` file — a skill-like format that bundles a prompt, the commands to run between iterations, and any files the agent needs. **Ralphify** is the CLI runtime that executes them.

See [The Ralph Format](blog/posts/the-ralph-standard.md) for the full spec.

```
grow-coverage/
├── RALPH.md               # the loop definition (required)
├── check-coverage.sh      # command that runs each iteration
└── testing-conventions.md # context for the agent
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

One directory. One command. Each iteration starts with fresh context and current data — ralphify runs the commands, fills in `{{ placeholders }}`, pipes the prompt to your agent, and loops.

*Works with any agent CLI. Swap `claude -p` for Codex, Aider, or your own — just change the `agent` field.*

[Get Started](getting-started.md){ .md-button .md-button--primary }
[Read the Format Spec](blog/posts/the-ralph-standard.md){ .md-button }

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

## Scaffold a ralph and run it

```bash
ralph scaffold my-ralph
```

This creates a directory with a `RALPH.md` template. Edit it, then run:

```bash
ralph run my-ralph         # loop until Ctrl+C
ralph run my-ralph -n 3    # run 3 iterations
```

Edit `RALPH.md` while the loop is running — changes take effect on the next iteration.

## Or install one with agr

Ralphs are just directories, so you can share them via any git repo. Install a pre-built ralph from GitHub with [agr](https://github.com/computerlovetech/agr):

```bash
agr add owner/repo/my-ralph     # install a ralph from GitHub
ralph run my-ralph              # run it by name
```

agr installs ralphs to `.agents/ralphs/` so they're automatically discovered by `ralph run`.

---

## Why a format

Everyone writing ralph loops ends up with the same scaffolding: a markdown prompt, a few shell commands that surface state between iterations, a while-loop that ties them together. Turning that into a format makes ralphs **shareable**, **versionable**, and **installable** — the same way skills made inner-loop workflows shareable.

Ralphs are to the outer loop what [skills](https://agentskills.io/) are to the inner loop. A skill guides an agent inside a session. A ralph defines what runs *between* sessions.

<div class="grid cards" markdown>

-   :material-refresh:{ .lg .middle } **Fresh context, no decay**

    ---

    Each iteration starts with a clean context window. No conversation bloat, no hallucinated memories, no degradation over time. The agent reads the current state of the codebase every loop.

-   :material-shield-check-outline:{ .lg .middle } **Commands as feedback**

    ---

    Commands run each iteration and their output feeds into the prompt. When tests fail, the agent sees the failure output and fixes it in the next iteration — a self-healing feedback loop.

-   :material-pencil-outline:{ .lg .middle } **Steer while it runs**

    ---

    The prompt is re-read every iteration. Edit `RALPH.md` while the loop runs and the agent follows your new rules on the next cycle. When it does something dumb, add a sign.

-   :material-git:{ .lg .middle } **Progress lives in git**

    ---

    Every iteration commits to git. If something goes wrong, `git log` shows exactly what happened and `git reset` rolls it back. No opaque internal state to debug or lose.

</div>

---

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or [any agent CLI](agents.md) that accepts piped input)

---

## Next steps

- **[The Ralph Format](blog/posts/the-ralph-standard.md)** — the full spec
- **[Getting Started](getting-started.md)** — from install to a running loop in 10 minutes
- **[How it Works](how-it-works.md)** — what happens inside each iteration
- **[Cookbook](cookbook.md)** — copy-pasteable ralphs for coding, docs, research, and more
- **[Python API](api.md)** — embed the loop in your own automation
