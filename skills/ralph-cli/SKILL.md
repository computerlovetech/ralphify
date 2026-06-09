---
name: ralph-cli
description: >
  Build, run, and debug autonomous AI coding loops with the ralph CLI from
  ralphify (https://ralphify.co). Use whenever the user mentions ralphify,
  ralph, RALPH.md, "ralph loop", "loop engineering", `ralph run`, `ralph
  scaffold`, or asks to: set up an autonomous agent loop, run a coding agent
  (Claude Code, Codex, …) repeatedly with fresh context, write or fix a
  RALPH.md frontmatter/prompt, wire commands and {{ placeholders }} into a
  loop, choose or configure an agent for a loop, run loops concurrently.
---

# ralph CLI

Ralphify is the open-source framework for **loop engineering**: running an AI
coding agent in an autonomous loop, piping it a prompt, capturing fresh dynamic
data each iteration, and repeating with a clean context window. The CLI is
`ralph`. This skill helps you operate it on the user's behalf — scaffold
ralphs, write and fix `RALPH.md`, run loops, pick agents, and reach for the
Python API when programmatic control is needed.

## When to use

Use this skill when the user wants to:

- Scaffold a new ralph (`ralph scaffold my-task`).
- Run an autonomous loop (`ralph run my-ralph -n 5`).
- Write or fix a `RALPH.md` — frontmatter (`agent`, `commands`, `args`),
  the prompt body, or `{{ placeholders }}`.
- Wire a command's output into the prompt, or pass user arguments.
- Pick or configure an agent (Claude Code, Codex CLI, custom wrapper).
- Debug a loop that hangs, fails every iteration, or doesn't commit.
- Run loops concurrently, or drive the loop from Python (`run_loop`,
  `RunConfig`, `RunManager`, the event system).
- Or whenever a `RALPH.md` is present and the user is doing loop-harness work.

Do NOT use this skill for:

- Installing/sharing/syncing *skills* across tools — that's the `agr` CLI
  (`agr-cli` skill). Note ralphify ships ralphs as an agr resource type, so
  `agr add user/repo/ralph` installs a ralph into `.agents/ralphs/`; the
  install/sync mechanics belong to `agr-cli`, the authoring and running of the
  ralph itself belong here.

## Prerequisites

Verify ralph is installed:

```bash
ralph --version
```

If missing, the standard install is `uv tool install ralphify` (or `pipx
install ralphify`). **Don't install without checking with the user first** —
they may prefer a pinned version. The CLI is `ralph`; the PyPI package is
`ralphify`.

The loop also needs an **agent CLI** installed and authenticated (Claude Code,
Codex, Pi, …). Claude Code is the default and best-supported: `npm install
-g @anthropic-ai/claude-code`.

## Mental model — read first

- A **ralph** is just a directory containing a `RALPH.md` file. No project
  config, no special directories. The shape follows the open
  [ralph loops format](https://ralphloops.io/).
- **`RALPH.md`** = YAML frontmatter (settings) + body (the prompt). Frontmatter
  fields: `agent` (required), `commands`, `args`, `credit`.
- **The loop**, each iteration: run `commands` → assemble the prompt (resolve
  `{{ placeholders }}`) → pipe it to the `agent` via stdin → agent works and
  exits → repeat with a **fresh context window**.
- **Fresh context every iteration** is the whole point. The agent has no memory
  between iterations; the prompt + live command output *are* its memory. Point
  it at durable state on disk (`TODO.md`, `PLAN.md`, failing tests, git log).
- **The self-healing loop**: a command like `pytest` captures failures into the
  next iteration's prompt, so the agent sees what it broke and fixes it.
- The **prompt body is re-read every iteration** (edit it live); frontmatter is
  read once at startup (restart to change `agent`/`commands`/`args`).

For the full per-iteration lifecycle: [references/the-loop.md](references/the-loop.md).

## Workflows

### 1. Scaffold a new ralph

```bash
ralph scaffold my-task     # creates my-task/RALPH.md from a template
ralph scaffold             # creates RALPH.md in the current directory
```

The template ships an example command (`git-log`), an example arg (`focus`),
and a body using both. Errors if `RALPH.md` already exists. Then edit the
frontmatter and body for the real task — see
[references/writing-ralphs.md](references/writing-ralphs.md).

### 2. Run the loop

```bash
ralph run my-ralph                  # run forever (Ctrl+C to stop)
ralph run my-ralph -n 5             # run 5 iterations
ralph run my-ralph -s               # --stop-on-error: stop if agent exits non-zero/times out
ralph run my-ralph -d 10            # --delay 10s between iterations
ralph run my-ralph -t 300           # --timeout: kill agent after 300s/iteration
ralph run my-ralph -l ralph_logs    # --log-dir: save iteration output to files
ralph run my-ralph --focus auth     # pass a user arg → {{ args.focus }}
```

`PATH` may be a directory with a `RALPH.md`, a direct path to a `RALPH.md`, or
the name of an installed ralph in `.agents/ralphs/`.

**Always validate a new or edited ralph with `ralph run my-ralph -n 1` first** —
one iteration surfaces setup/frontmatter/agent errors clearly before you commit
to a long run. Add `--log-dir ralph_logs` to capture output for inspection.

Stopping: first `Ctrl+C` finishes the current iteration then stops; a second
`Ctrl+C` force-kills the agent. Full options and the live-peek keys (`p`, shift+`P`):
[references/running.md](references/running.md).

### 3. Write / fix a RALPH.md

The single source of truth. Minimal valid example:

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
args: [focus]
---

# Your task

{{ commands.tests }}

If tests are failing, fix them before new work. Focus area: {{ args.focus }}.
You are in a loop with no memory — track progress in TODO.md.
```

Key rules (full guide: [references/writing-ralphs.md](references/writing-ralphs.md)):

- Only commands **referenced by a placeholder** appear in the prompt (an
  unreferenced command still runs, but its output is dropped).
- `run` is parsed with `shlex.split()` and run **directly, not via a shell** —
  no pipes, `>`, `&&`, or `$VAR`. Point it at a `.sh` script instead.
- Commands starting with `./` run from the ralph directory; others run from the
  project root. Default per-command `timeout` is 60s.
- Placeholders: `{{ commands.<name> }}`, `{{ args.<name> }}`, and the automatic
  `{{ ralph.name }}` / `{{ ralph.iteration }}` / `{{ ralph.max_iterations }}`.
- Named flags (`--focus value`) work without declaring `args`. Declaring
  `args: [...]` is only needed to accept **positional** arguments.

### 4. Pick / configure an agent

Ralphify works with any CLI that **reads a prompt from stdin and exits when
done**. If unsure, start with Claude Code.

```markdown
agent: claude -p --dangerously-skip-permissions          # Claude Code (default, best support)
agent: codex exec --sandbox danger-full-access -          # OpenAI Codex CLI
agent: pi -p -a                                           # Pi (pi.dev) — native stdin, no wrapper
agent: ./ralph-agent.sh                                    # custom wrapper script
```

`--dangerously-skip-permissions` (Claude) / auto-approve flags are required —
without them the agent hangs waiting for approval nobody is there to give.
Details and the custom-wrapper pattern: [references/agents.md](references/agents.md).

### 5. Debug a loop

Checklist before digging in:

1. `ralph run my-ralph -n 1` — validates setup, shows clear errors.
2. Test the agent standalone: `echo "Say hello" | claude -p`.
3. `--log-dir ralph_logs` to capture output, then read the log.
4. Remember commands don't support shell features — use a script.

Common failure-cause map and frontmatter/arg/command error messages:
[references/troubleshooting.md](references/troubleshooting.md).

### 6. Drive the loop from Python

For concurrent runs, custom event handling, or embedding in another tool, use
the `ralphify` package: `run_loop(config, state, emitter)`, `RunConfig`,
`Command`, `RunState`, and `RunManager` for concurrency.

```python
from pathlib import Path
from ralphify import run_loop, RunConfig, RunState, Command

config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("my-ralph"),
    ralph_file=Path("my-ralph/RALPH.md"),
    commands=[Command(name="tests", run="uv run pytest -x")],
    max_iterations=3,
)
run_loop(config, RunState(run_id="my-run"))
```

Full API surface (events, emitters, `RunManager`):
[references/python-api.md](references/python-api.md).

## Boundaries

- **Always validate with `ralph run ... -n 1` before a long run**, and before
  recommending a ralph the user will leave running unattended.
- **Long autonomous runs do real work** (edit files, commit, run commands).
  Run them on a **dedicated branch** — never on `main` — and confirm scope with
  the user before kicking off an unbounded (`ralph run` with no `-n`) loop.
- **Run concurrent loops on separate branches** to avoid git conflicts.
- **Ralphify doesn't commit for the agent.** If the user wants commits, the
  *prompt* must instruct it, and the agent must have git permission.
- **Don't add `ralph_logs/`** (or other generated output) to git — gitignore
  it. Commit `RALPH.md` and any helper `*.sh` scripts.
- **Don't push or `git tag`** as part of these workflows; let the user push.

## References

- [writing-ralphs.md](references/writing-ralphs.md) — RALPH.md frontmatter, commands, placeholders, prompt-writing patterns
- [running.md](references/running.md) — `ralph run` options, stopping, live peek, user arguments
- [the-loop.md](references/the-loop.md) — the six steps of an iteration, what's re-read vs fixed, the self-healing loop
- [agents.md](references/agents.md) — Claude Code, Codex, custom wrappers
- [troubleshooting.md](references/troubleshooting.md) — failure causes and all error messages
- [python-api.md](references/python-api.md) — `run_loop`, `RunConfig`, `Command`, `RunState`, events, `RunManager`

Canonical docs: https://ralphify.co/docs/ — or run `ralph <command> --help`.
