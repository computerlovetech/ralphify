<p align="center">
  <img src="cli-graphic.png" alt="ralphify" />
</p>

Put your AI coding agent in a `while True` loop and let it ship.

Ralphify is a minimal harness for running autonomous AI coding loops, inspired by the [Ralph Wiggum technique](https://ghuntley.com/ralph/). The idea is simple: pipe a prompt to an AI coding agent, let it do one thing, commit, and repeat. Forever. Until you hit Ctrl+C.

```
while :; do cat PROMPT.md | claude -p ; done
```

Ralphify wraps this pattern into a proper tool with config, iteration tracking, and clean shutdown.

## Install

```bash
uv tool install ralphify
```

This gives you the `ralph` command.

## Quickstart

```bash
# In your project directory
ralph init      # Creates ralph.toml + PROMPT.md
ralph run       # Starts the loop (Ctrl+C to stop)
```

That's it. Two commands.

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
```

## The technique

The Ralph Wiggum technique works because:

- **One thing per loop.** The agent picks the most important task, implements it, tests it, and commits. Then the next iteration starts fresh.
- **Fresh context every time.** No context window bloat. Each loop starts clean and reads the current state of the codebase.
- **Progress lives in git.** Code, commits, and a plan file are the only state that persists between iterations. If something goes wrong, `git reset --hard` and run more loops.
- **The prompt is a tuning knob.** When the agent does something dumb, you add a sign. Like telling Ralph not to jump off the slide — you add "SLIDE DOWN, DON'T JUMP" to the prompt.

Read the full writeup: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/)

## Customizing your prompt

The generated `PROMPT.md` is a starting point. A good prompt for autonomous loops typically includes:

- What to work on (specs, plan file, TODO list)
- How to validate (run tests, type check, build)
- What NOT to do (no placeholders, no skipping tests)
- When to commit (after tests pass)

The agent reads this prompt fresh every iteration, so you can edit it while the loop is running.

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (or any agent CLI that accepts piped input)

## License

MIT
