# Troubleshooting

Common issues and how to fix them. If your problem isn't listed here, run `ralph status` first — it validates your setup and points out most configuration problems.

## Setup issues

### "ralph.toml not found"

You haven't initialized the project yet. Run `ralph init` in your project directory to create `ralph.toml` and `PROMPT.md`.

### "Command 'claude' not found on PATH"

The agent CLI isn't installed or isn't in your shell's PATH. Verify by running the command directly:

```bash
claude --version
```

If it's installed but not found, check that your PATH includes the directory where it's installed. Run `ralph status` to confirm — it checks whether the configured command is on PATH.

### "Not ready" from `ralph status`

`ralph status` found one or more problems. The output tells you exactly what's wrong:

- **Prompt file not found** → Create it with `ralph init`, or check that the `prompt` path in `ralph.toml` is correct
- **Command not found** → Install the agent CLI or fix the `command` in `ralph.toml`

### "PROMPT.md already exists"

`ralph init` won't overwrite existing files by default. If you want to start fresh:

```bash
ralph init --force
```

## Loop issues

### Agent produces no output or seems to hang

Try running the agent command directly to see if it works outside of ralphify:

```bash
echo "Say hello" | claude -p
```

If it hangs there too, the issue is with the agent CLI, not ralphify. If it works standalone but hangs via ralphify, try adding `--timeout` to kill stalled iterations:

```bash
ralph run --timeout 300
```

### Agent exits non-zero every iteration

Check the agent's output to understand why. Use `--log-dir` to capture output:

```bash
ralph run -n 1 --log-dir ralph_logs
cat ralph_logs/001_*.log
```

Common causes:
- The agent CLI requires authentication that hasn't been set up
- The prompt asks the agent to run a command that fails
- The agent's context window is being exceeded by a very large prompt

If you want the loop to stop on errors instead of continuing, use `--stop-on-error`:

```bash
ralph run --stop-on-error --log-dir ralph_logs
```

### Agent runs but doesn't commit

Ralphify doesn't commit for the agent — committing is the agent's responsibility. Make sure your prompt includes explicit commit instructions:

```markdown
## Process
- Run tests before committing
- Commit with a descriptive message like `feat: add X`
```

Also ensure the agent has permission to run git commands. With Claude Code, the `--dangerously-skip-permissions` flag handles this.

### Loop runs too fast / agent not doing anything useful

If iterations finish in seconds with no meaningful work, the agent may be exiting without taking action. Check the logs:

```bash
ralph run -n 1 --log-dir ralph_logs
cat ralph_logs/001_*.log
```

Common causes:
- The prompt is too vague ("improve the code" instead of "read TODO.md and implement the next task")
- There's no concrete task source (no TODO.md, PLAN.md, or failing tests to fix)
- The agent can't find what it's supposed to work on

## Check issues

### Checks always failing

Run the check command manually to see if it works:

```bash
# Look up the command in your check file
cat .ralph/checks/tests/CHECK.md

# Run it directly
uv run pytest -x
```

If the command fails manually, the issue isn't with ralphify — fix the underlying test/lint failures first.

### Check timed out

The check took longer than its configured timeout. Increase the `timeout` value in the check's frontmatter:

```markdown
---
command: uv run pytest
timeout: 300
enabled: true
---
```

The default is 60 seconds. Long test suites may need 300+ seconds.

### Script permission denied

If you're using a `run.sh` or `run.py` script instead of a frontmatter `command`, make sure it's executable:

```bash
chmod +x .ralph/checks/my-check/run.sh
```

### Check has neither command nor script

If `ralph status` warns that a check has neither a `run.*` script nor a `command`, add one of:

- A `command` field in the CHECK.md frontmatter
- An executable script named `run.sh`, `run.py`, etc. in the check directory

## Context and instruction issues

### Placeholders not resolving

If you see raw `{{ contexts.my-context }}` text in the agent's output, the placeholder name doesn't match any discovered context. Check:

1. The directory name matches: `.ralph/contexts/my-context/CONTEXT.md`
2. The placeholder uses the exact directory name: `{{ contexts.my-context }}`
3. The context is enabled (check with `ralph status`)

Same rules apply for `{{ instructions.name }}`.

### Context command failing

Run the context command manually:

```bash
# Check what command is configured
cat .ralph/contexts/git-log/CONTEXT.md

# Run it directly
git log --oneline -10
```

If the command fails, its output won't be injected. Fix the command or increase its timeout.

### Some contexts are missing from the prompt

If you use a **named placeholder** like `{{ contexts.git-log }}` but don't include a bulk `{{ contexts }}` placeholder, any other contexts are silently excluded. Add `{{ contexts }}` somewhere in your prompt to catch all remaining contexts:

```markdown
{{ contexts.git-log }}

Do the work.

{{ contexts }}
```

See [placeholder resolution rules](how-it-works.md#placeholder-resolution-rules) for full details.

## Output issues

### Output is truncated

Ralphify truncates check and context output to **5,000 characters** each. This prevents extremely long output from consuming the agent's context window. You'll see `... (truncated)` at the end of truncated output.

This is expected behavior. If you need the full output, check the log files:

```bash
ralph run --log-dir ralph_logs
cat ralph_logs/001_*.log
```

### No output visible during iteration

By default, agent output goes directly to the terminal. If you're using `--log-dir`, output is captured and then replayed — you'll still see it, but only after the iteration completes.

## Getting more help

1. Run `ralph status` to validate your full setup
2. Use `ralph run -n 1 --log-dir ralph_logs` to capture a single iteration for debugging
3. Check the [CLI Reference](cli.md) for all available options
4. File an issue at [github.com/computerlovetech/ralphify](https://github.com/computerlovetech/ralphify/issues)
