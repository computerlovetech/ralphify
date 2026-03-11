# FAQ

Common questions about ralphify. For setup problems and error messages, see [Troubleshooting](troubleshooting.md).

## General

### What is the Ralph Wiggum technique?

It's named after the Simpsons character who bumbles through situations but eventually gets things done. The idea: put an AI coding agent in a loop, let it make one change per iteration, and add "signs" to the prompt when it does something wrong — like posting "SLIDE DOWN, DON'T JUMP" next to a slide. The agent doesn't need to remember past mistakes because the signs are always there in the prompt.

Read the original essay: [Ralph Wiggum as a "software engineer"](https://ghuntley.com/ralph/)

### Does ralphify work with agents other than Claude Code?

Yes. Ralphify works with any CLI that reads a prompt from **stdin** and exits when done. Change the `command` and `args` in `ralph.toml`:

```toml
# Example: custom wrapper script
[agent]
command = "bash"
args = ["-c", "cat - | my-agent-wrapper --non-interactive"]
prompt = "PROMPT.md"
```

Claude Code is the default because its `-p` flag is designed for exactly this use case — reading a prompt from stdin and running non-interactively. See [Using with Different Agents](agents.md) for setup guides for Aider, Codex CLI, and custom wrappers.

### Does this cost money?

Ralphify itself is free and open source (MIT license). But the AI agent it runs will use API credits or a subscription. Each iteration is one agent session, so costs scale with the number of iterations and the amount of work per iteration.

**Tips to control costs:**

- Start with `ralph run -n 3` to test before running indefinitely
- Use `--timeout` to kill runaway iterations
- Write focused prompts that keep iterations short and targeted

### What are the requirements?

- Python 3.11+
- An AI coding agent CLI that accepts piped input (e.g. [Claude Code](https://docs.anthropic.com/en/docs/claude-code))
- A git repository (recommended but not strictly required)

### Can I use this in CI/CD?

Yes. Ralphify is a standard CLI tool that runs anywhere Python 3.11+ is available:

```bash
pip install ralphify
ralph run -n 5 --stop-on-error --timeout 300 --log-dir artifacts/ralph-logs
```

Make sure the agent CLI is installed and authenticated in your CI environment. Use `-n` and `--stop-on-error` to keep runs bounded.

See [Running in GitHub Actions](cookbook.md#running-in-github-actions) for a complete workflow you can copy into your repo.

## Usage

### Can I edit the prompt while the loop is running?

Yes — this is a core feature. `PROMPT.md` is re-read from disk at the start of every iteration. Edit it, save, and the next iteration uses the updated version. This is the main way to steer the agent in real time.

### Can I add or change checks/contexts/instructions while running?

No. Primitives (checks, contexts, instructions) are discovered and loaded once when `ralph run` starts. If you add a new check, modify a check's command, change an instruction's text, or toggle a primitive's `enabled` flag, you need to stop the loop (`Ctrl+C`) and restart it.

The exception is **context commands** — their output is always fresh because the command re-runs each iteration. But the command itself, timeout, and static content are fixed at startup.

See [What's fresh and what's fixed](how-it-works.md#whats-fresh-and-whats-fixed) for the full breakdown.

### What happens if the agent doesn't commit?

Nothing breaks — ralphify doesn't require or enforce commits. But uncommitted changes accumulate and may confuse the agent in later iterations (it might redo work or create conflicts). Best practice is to include explicit commit instructions in your prompt.

### How many iterations should I run?

Start small with `-n 3` or `-n 5` to verify the agent is producing useful work. Review the output, tune the prompt, then gradually increase. There's no universal "right" number — it depends on the size of your task and how reliable the loop is.

### Does `--stop-on-error` stop on timeouts too?

Yes. `--stop-on-error` stops the loop when the agent exits with a non-zero code **or** when an iteration times out (if `--timeout` is set).

### What if a check always fails?

This usually means the check command itself doesn't work, not that the agent is failing. Run the command manually to verify:

```bash
# See what's configured
cat .ralph/checks/my-check/CHECK.md

# Run the command directly
uv run pytest -x  # or whatever the command is
```

If it fails outside of ralphify, fix the underlying issue first. If it only fails after the agent runs, make the failure instruction more specific about how to fix it.

### Can I run multiple loops in parallel?

Yes, but they should work on **separate branches** to avoid git conflicts:

```bash
# Terminal 1
git checkout -b feature-a && ralph run

# Terminal 2
git checkout -b feature-b && ralph run
```

Each loop operates independently with its own prompt and checks.

### How do I limit API costs?

| Strategy | How |
|---|---|
| Cap iterations | `ralph run -n 10` |
| Kill stuck runs | `ralph run --timeout 300` |
| Stop on failure | `ralph run --stop-on-error` |
| Write focused prompts | One clear task per iteration, not "improve everything" |
| Review before scaling | Always start with `-n 3` and check the logs |

## Configuration

### What files should I commit?

Ralphify creates several files and directories. Here's what belongs in version control and what doesn't:

| File / directory | Commit? | Why |
|---|---|---|
| `ralph.toml` | **Yes** | Loop configuration — shared across your team |
| `PROMPT.md` | **Yes** | The prompt is the core of your loop |
| `.ralph/` | **Yes** | Checks, contexts, and instructions — project config your team should share |
| `ralph_logs/` | **No** | Iteration output logs — large, machine-specific, regenerated every run |

Add `ralph_logs/` to your `.gitignore`:

```bash
echo "ralph_logs/" >> .gitignore
```

### Should I commit the `.ralph/` directory?

Yes. It contains your checks, contexts, and instructions — this is project configuration that your team should share:

```bash
git add .ralph/
git commit -m "chore: add ralph checks and contexts"
```

### What's the difference between instructions and just writing rules in PROMPT.md?

Instructions are **modular** — you can enable, disable, or swap them without editing the prompt. This is useful when:

- Multiple prompts share the same coding standards
- You want to temporarily disable a rule without deleting it
- Team members maintain different instruction sets

If you have one prompt with a few simple rules, writing them directly in `PROMPT.md` is simpler and easier to maintain.

### Can I use a different prompt file name?

Yes. Change the `prompt` field in `ralph.toml`:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "my-custom-prompt.md"
```

The file can be named anything and placed anywhere relative to the project root.

### What's the difference between a check `command` and a `run.*` script?

A `command` in the CHECK.md frontmatter is a single shell command. A `run.*` script (e.g. `run.sh`, `run.py`) in the check directory is an executable file that can contain multi-step logic.

Use a **command** for simple, one-line validations:

```yaml
command: uv run pytest -x
```

Use a **script** when you need setup/teardown, multiple steps, or conditional logic:

```bash
#!/bin/bash
# .ralph/checks/integration/run.sh
set -e
docker compose up -d
pytest tests/integration/
docker compose down
```

If both exist, the script takes precedence. See [Primitives](primitives.md#using-a-script-instead-of-a-command) for details.
