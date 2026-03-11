# Ralphify

Put your AI coding agent in a `while True` loop and let it ship.

Ralphify is a minimal harness for running autonomous AI coding loops, inspired by the [Ralph Wiggum technique](https://ghuntley.com/ralph/). It pipes a prompt to an AI coding agent, lets it do one thing, commits, and repeats — each iteration starts with a fresh context window.

## Install

```bash
uv tool install ralphify
```

This gives you the `ralph` command.

## Quickstart

```bash
ralph init      # Creates ralph.toml + PROMPT.md
ralph run       # Starts the loop (Ctrl+C to stop)
```

### What `ralph init` creates

**`ralph.toml`** — tells ralphify which agent to call:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
```

**`PROMPT.md`** — a starter prompt template. This file is the prompt. It gets piped directly to your agent each iteration. Edit it to fit your project.

### What `ralph run` does

Each iteration:

1. Reads `PROMPT.md`
2. Resolves any [contexts and instructions](primitives.md) into the prompt
3. Pipes the assembled prompt to your agent command
4. Waits for the agent to finish
5. Runs any configured [checks](primitives.md#checks) and feeds failures into the next iteration
6. Repeats

```bash
ralph run          # Run forever
ralph run -n 10    # Run 10 iterations then stop
```

## The technique

The Ralph Wiggum technique works because:

- **One thing per loop.** The agent picks the most important task, implements it, tests it, and commits. Then the next iteration starts fresh.
- **Fresh context every time.** No context window bloat. Each loop starts clean and reads the current state of the codebase.
- **Progress lives in git.** Code and commits are the only state that persists between iterations. If something goes wrong, `git reset --hard` and run more loops.
- **The prompt is a tuning knob.** When the agent does something dumb, you add a sign. Like telling Ralph not to jump off the slide — add "SLIDE DOWN, DON'T JUMP" to the prompt.

Read the full writeup: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/)

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or any agent CLI that accepts piped input)

## Next steps

- [Getting Started](getting-started.md) — step-by-step tutorial from install to a running loop with checks and contexts
- [How It Works](how-it-works.md) — the iteration lifecycle, prompt assembly, and feedback loop explained
- [Writing Your Prompt](prompts.md) — how to write prompts that produce useful work
- [Cookbook](cookbook.md) — complete, copy-pasteable setups for Python, TypeScript, bug fixing, and docs
- [Primitives](primitives.md) — add checks, contexts, and instructions to your loop
- [CLI Reference](cli.md) — all commands and options
