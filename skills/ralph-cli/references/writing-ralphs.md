# Writing a RALPH.md

A `RALPH.md` is the single configuration + prompt file for a ralph: YAML
frontmatter for settings, the body for the prompt text.

```markdown
---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: tests
    run: uv run pytest -x
  - name: git-log
    run: git log --oneline -10
args: [dir, focus]
---

# Prompt body

{{ commands.tests }}

{{ commands.git-log }}

Your instructions here. Reference args with {{ args.dir }}.
```

## Frontmatter fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | Full agent command the prompt is piped to (see `agents.md`) |
| `commands` | list | no | Commands run each iteration; each has `name` and `run` |
| `args` | list of strings | no | Declared user-argument names. Letters, digits, `-`, `_` only |
| `credit` | bool | no | Append co-author trailer instruction to prompt (default `true`) |

## Commands

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | required | Identifier used in `{{ commands.<name> }}`. Letters, digits, `-`, `_` only |
| `run` | string | required | Command run each iteration (supports `{{ args.<name> }}`) |
| `timeout` | number | `60` | Max seconds before the command is killed |

- Commands run **in order**, each iteration.
- Output (stdout + stderr) is captured **regardless of exit code** — a failing
  `pytest -x` is exactly what you want in the prompt.
- `run` is parsed with `shlex.split()` and run **directly, not through a
  shell**. Pipes (`|`), redirections (`>`, `2>&1`), chaining (`&&`), and shell
  variables (`$VAR`) do NOT work. Point `run` at a script instead:
  `run: ./my-script.sh`.
- Commands starting with `./` run from the **ralph directory**; all others run
  from the **project root** (current working directory of `ralph run`).

## Placeholders

| Syntax | Resolves to |
|---|---|
| `{{ commands.<name> }}` | Output of the named command |
| `{{ args.<name> }}` | Value of the named user argument |
| `{{ ralph.name }}` | Ralph directory name |
| `{{ ralph.iteration }}` | Current iteration number (1-based) |
| `{{ ralph.max_iterations }}` | Total iterations if `-n` set, else empty |

- `ralph.*` placeholders are automatic — no frontmatter needed.
- **Only commands referenced by a `{{ commands.* }}` placeholder appear in the
  prompt.** An unreferenced command still *runs* each iteration (useful for side
  effects), but its output is excluded.
- Unmatched placeholders resolve to an empty string.
- `{{ args.* }}` is resolved both in the body and inside command `run` strings.

## Prompt-writing patterns

The agent starts every iteration with **no memory** — only the assembled prompt
and fresh command output. Good prompts make that explicit and anchor the agent
to durable state:

- **State the loop contract**: "You are running in a loop with no memory of
  previous iterations. Read TODO.md to see what's left."
- **Give one concrete task source**: a `TODO.md`/`PLAN.md`, failing tests, an
  issue list, or a command whose output names the next thing to do. A vague
  prompt with no task source makes the loop spin without useful work.
- **Feed back live signal**: include `{{ commands.tests }}` (or lint, build,
  typecheck) and tell the agent to fix failures *before* new work. This is the
  self-healing loop.
- **Instruct commits explicitly** if you want them — ralphify never commits for
  the agent. "Commit each chunk of work with a descriptive message."
- **HTML comments are stripped** from the assembled prompt — use `<!-- … -->`
  for notes to yourself that the agent never sees.
- Edit the body freely while the loop runs; the next iteration picks it up.

## User arguments

Named flags (`--focus value` or `--focus=value`) work **without** any
frontmatter declaration. The `args` field is only needed to accept **positional**
arguments — it maps positions to names.

```bash
ralph run research --dir ./proj --focus performance   # named flags, no args: needed
ralph run research ./proj performance                  # positional, needs args: [dir, focus]
ralph run research -- --verbose ./src                  # -- ends flag parsing
```

Missing args resolve to an empty string. See `running.md` for the full argument
grammar.
