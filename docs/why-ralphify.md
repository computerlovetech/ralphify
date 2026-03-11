---
description: Why use ralphify over a raw shell loop or other autonomous coding frameworks. Covers the self-healing feedback loop, design principles, and when ralphify is the right fit.
---

# Why Ralphify?

You've used an AI coding agent. You've seen it produce useful work in a single prompt. But what happens when you want it to do *sustained* work — shipping features from a backlog, fixing bugs across a test suite, or writing documentation for an entire codebase?

You put it in a loop. And that's where things get interesting.

## The problem

The raw loop is simple:

```bash
while :; do cat PROMPT.md | claude -p; done
```

This works — until it doesn't. Common failure modes:

- **The agent breaks something and doesn't notice.** No tests ran, no linter checked. The next iteration builds on broken code.
- **The agent goes in circles.** It does something, undoes it, redoes it — because there's no feedback signal telling it what's wrong.
- **The agent does random work.** Without structure, it picks whatever seems interesting instead of what you need.
- **A stuck iteration burns credits forever.** No timeout, no iteration cap, no way to stop gracefully.
- **You can't debug what happened.** No logs, no iteration tracking, no summary of what passed or failed.

You can fix each of these with shell scripting. Timeout with `timeout`, log with `tee`, run tests with `&&`. But you end up writing a bespoke harness every time — and it's never quite right.

## What ralphify adds

Ralphify wraps the raw loop with exactly the machinery you need to make autonomous coding productive:

| Problem | Raw loop | Ralphify |
|---|---|---|
| Agent breaks things silently | No feedback | **Checks** run after each iteration; failures feed into the next prompt |
| Agent goes in circles | No correction signal | **Self-healing loop** — check output tells the agent exactly what's wrong |
| No dynamic context | Static prompt | **Contexts** inject fresh data (git log, test status) each iteration |
| No reusable rules | Edit the prompt | **Instructions** you can toggle on/off without touching the prompt |
| Stuck iterations | Runs forever | `--timeout` kills hung agents |
| No cost control | No limits | `-n` caps iterations, `--stop-on-error` halts on failure |
| No visibility | No logs | `--log-dir` saves every iteration, summary printed on exit |
| Hard to steer | Stop, edit, restart | **Edit `PROMPT.md` while running** — changes take effect next iteration |

The core insight: **an autonomous loop needs a feedback mechanism.** Without one, the agent can't self-correct. Ralphify's check system creates that feedback loop automatically.

## Compared to alternatives

### vs. a raw shell loop

A raw `while` loop gets you started fast but has no guardrails. Ralphify adds the guardrails without adding complexity. You still write a markdown prompt, you still pipe it to your agent — but now failed tests feed back into the next iteration, and you can steer the agent in real time.

**Use a raw loop when:** you're experimenting for 5 minutes and don't care about quality. **Use ralphify when:** you want the agent to produce work you'd actually merge.

### vs. interactive AI coding (chat sessions)

Interactive sessions work great for exploration and one-off tasks. But they don't scale — you're the bottleneck. Every approval prompt, every "yes, go ahead", every context window reset requires your attention.

Ralphify removes you from the loop. The agent works autonomously, checks validate the work, and you review the results when you're ready. You can run it overnight, during lunch, or in CI.

**Use interactive mode when:** you're exploring a problem or need tight control. **Use ralphify when:** you have a clear task list and want it done without babysitting.

### vs. other autonomous coding frameworks

Tools like SWE-agent and OpenDevin are research-oriented frameworks designed for benchmarks and complex multi-step reasoning. They're powerful but heavyweight — custom environments, specialized prompting, significant setup.

Ralphify takes the opposite approach: **minimal surface area, maximum composability.** It's a thin layer on top of whatever agent CLI you already use. No custom environment, no specialized prompting framework, no agent-specific protocol. Just stdin in, work done, checks run.

| | Ralphify | Research frameworks |
|---|---|---|
| Setup | `pip install ralphify && ralph init` | Docker, custom environments, configuration |
| Agent | Any CLI that reads stdin | Usually framework-specific |
| Feedback | Checks you define (tests, linters) | Built-in evaluation harness |
| Prompt | Markdown file you edit directly | Framework-managed prompt templates |
| Extensibility | Shell scripts and markdown | Python plugins, custom tools |
| Best for | Shipping real work on your codebase | Research, benchmarks, evaluation |

## Design principles

### Minimal by design

Ralphify has two runtime dependencies: `typer` and `rich`. Everything else is Python stdlib. This isn't accidental — every dependency is a risk, a version conflict, a thing that can break. The tool does one thing well and gets out of the way.

### Agent-agnostic

Ralphify doesn't know or care which AI model you're using. It works with Claude Code, Aider, Codex CLI, or any script that reads from stdin. Swap agents by changing one line in `ralph.toml`. This protects you from lock-in and lets you use the best tool for each task.

### Git-native

Progress lives in git, not in ralphify's state. There's no database, no session file, no hidden state that can get corrupted. If something goes wrong, `git log` shows you what happened and `git reset --hard` gets you back to a clean state. Every iteration is independently reviewable.

### Composable primitives

Checks, contexts, and instructions are simple building blocks. Each is a directory with a markdown file and an optional script. You can:

- Share them across projects by copying directories
- Version them in git alongside your code
- Enable and disable them without deleting anything
- Write them in any language (bash, Python, whatever `run.*` you want)

There's no plugin API to learn, no configuration language to master. It's files and commands.

### The prompt is the interface

The most important file in a ralphify project is `PROMPT.md`. It's plain markdown that you write and edit directly. No abstraction layer between you and what the agent sees. When the agent does something wrong, you edit the prompt — not a config file three levels deep.

## When ralphify is the right choice

Ralphify works best when you have:

- **A clear, decomposable task** — a backlog, a test suite to fix, docs to write, a migration to perform
- **Machine-checkable quality criteria** — tests, linters, type checkers, build scripts
- **An agent CLI you trust** — ralphify amplifies the agent's capabilities, so the agent needs to be competent on its own
- **Time you'd rather spend reviewing than typing** — the loop runs while you do other things

## When it's not

Ralphify is not the right tool when:

- **You need tight, interactive control** — use your agent's chat mode instead
- **The task can't be decomposed into iterations** — some problems need sustained, multi-step reasoning within a single context
- **There are no checkable quality criteria** — without checks, the loop has no feedback mechanism and the agent can't self-correct
- **You're evaluating AI models** — use a proper benchmarking framework instead

## Next steps

- [Getting Started](getting-started.md) — install and run your first loop in 5 minutes
- [How It Works](how-it-works.md) — understand the iteration lifecycle and self-healing feedback loop
- [Best Practices](best-practices.md) — patterns that make loops productive
