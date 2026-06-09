# Troubleshooting

Quick checklist before digging in:

1. `ralph run my-ralph -n 1` — validates setup, shows clear errors.
2. Test the agent standalone: `echo "Say hello" | claude -p`.
3. `--log-dir ralph_logs` to capture output, then read the log.
4. Commands don't support shell features (pipes, `&&`) — use a wrapper script.

## Setup

- **"is not a directory, RALPH.md file, or installed ralph"** — the path
  doesn't resolve. `ralph run` accepts a directory containing `RALPH.md`, a
  direct `RALPH.md` path, or an installed ralph name in `.agents/ralphs/`.
- **"Missing or empty 'agent' field"** — add `agent: claude -p
  --dangerously-skip-permissions` to the frontmatter.
- **"Agent command 'claude' not found on PATH"** — the agent CLI isn't
  installed / on PATH. Verify with `claude --version`.

## Loop behavior

- **Agent hangs / no output** — run the agent directly (`echo "Say hello" |
  claude -p`). If it hangs there, it's the agent CLI. If it works standalone,
  add `--timeout 300` to kill stalled iterations.
- **Agent exits non-zero every iteration** — capture with `-n 1 --log-dir
  ralph_logs` and read the log. Common causes: missing agent auth, a prompt
  asking for a failing command, or a prompt too large for the context window.
- **Agent runs but doesn't commit** — ralphify doesn't commit for the agent.
  Add explicit commit instructions to the prompt and ensure the agent has git
  permission (`--dangerously-skip-permissions` for Claude Code).
- **Loop runs too fast / no useful work** — the prompt is too vague or has no
  concrete task source. Tell the agent it's in a loop with no memory; point it
  at `TODO.md`, `PLAN.md`, or failing tests.
- **Output not streaming** — press `p` to toggle live peek. Streaming is off in
  non-TTY environments (piped/CI) by design; use `--log-dir`. If bursty, set
  `PYTHONUNBUFFERED=1`.

## Frontmatter errors

- **"Invalid YAML in frontmatter"** — missing colon, bad indentation, or an
  unquoted special char (`:`, `#`, `{`, `[`). Quote risky values.
- **"Frontmatter must be a YAML mapping"** — use `key: value` pairs, not a bare
  string or list.
- **"Each command must have 'name' and 'run' fields"** — both required,
  non-empty strings.
- **"Malformed 'agent' field"** — usually an unmatched quote in `agent`.
- **"'credit' must be true or false"** — only YAML booleans, not `"yes"`/`0`.
- **"... name contains invalid characters"** — command/arg names: letters,
  digits, hyphens, underscores only.
- **"Duplicate arg name" / "Duplicate command name"** — names must be unique.
- **"'commands' must be a list" / "'args' must be a list of strings"** — use
  list syntax (`args: [focus]`; `commands:` as a list of `{name, run}`). Quote
  `args` items that look like numbers/booleans.
- **"Command '...' has invalid timeout"** — `timeout` must be a positive number.

## Argument errors

- **"Positional argument '...' requires args declared in frontmatter"** — add
  an `args` field, or use `--name value` flag syntax (works without declaration).
- **"Too many positional arguments"** — more positional values than `args`
  declares.
- **"Flag '--...' requires a value"** — a `--name` flag passed without a value.

## Command errors

- **"Command '...' has invalid syntax"** — malformed shell syntax in `run`,
  usually an unmatched quote. Use a script for complex quoting.
- **"Command '...' binary not found"** — not installed / on PATH. If it's in a
  virtualenv, prefix with `uv run`.
- **Pipes/redirections not working** — `run` is `shlex`-split and run directly;
  `|`, `2>&1`, `&&`, `$VAR` won't work. Wrap in a `.sh` script.
- **Output truncated** — the command hit its 60s timeout. Raise `timeout: 300`
  or speed up the command.
- **Command output missing from prompt** — check the placeholder name matches
  the command `name` exactly, that the command produces output, and that you
  used `commands` (plural).

## Common questions

- **Run multiple loops in parallel?** Yes — on **separate branches** to avoid
  git conflicts. For programmatic control, use the Python `RunManager`.
- **What to commit?** `RALPH.md` and helper `*.sh` scripts. Gitignore
  `ralph_logs/`.
- **Edit RALPH.md while running?** Yes — the body is re-read each iteration;
  frontmatter needs a restart.
- **Disable the co-author credit?** Set `credit: false` in frontmatter.

If it's not here: `ralph run my-ralph -n 1` to validate, `--log-dir` to
capture, or file an issue at github.com/computerlovetech/ralphify/issues.
