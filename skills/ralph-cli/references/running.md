# Running the loop — `ralph run`

```bash
ralph run my-ralph                  # run forever (Ctrl+C to stop)
ralph run my-ralph -n 5             # run 5 iterations
ralph run my-ralph -s               # stop on agent error/timeout
ralph run my-ralph -d 10            # 10s delay between iterations
ralph run my-ralph -t 300           # kill agent after 300s/iteration
ralph run my-ralph -l ralph_logs    # save iteration output to log files
```

| Arg / Option | Short | Default | Description |
|---|---|---|---|
| `PATH` | | required | Ralph directory with `RALPH.md`, a direct `RALPH.md` path, or an installed ralph name in `.agents/ralphs/` |
| `-n` | | unlimited | Max iterations |
| `--stop-on-error` | `-s` | off | Stop if the agent exits non-zero or times out |
| `--delay` | `-d` | `0` | Seconds between iterations |
| `--timeout` | `-t` | none | Max seconds per iteration (kills the agent if exceeded) |
| `--log-dir` | `-l` | none | Directory for per-iteration log files |

The top-level CLI also has `ralph --version` / `-V`, `ralph --help`, and
`ralph --install-completion <bash|zsh|fish>` for shell completion.

## Validate first

Run **one iteration** before any long run:

```bash
ralph run my-ralph -n 1 --log-dir ralph_logs
```

This validates the path, frontmatter, agent availability, and command syntax,
and captures the full output for inspection — far cheaper than discovering a
broken prompt 20 iterations deep.

## Stopping the loop

| Action | Behavior |
|---|---|
| `Ctrl+C` (first) | Finish the current iteration gracefully, then stop |
| `Ctrl+C` (second) | Force-kill the agent process and exit immediately |

The loop also stops when all `-n` iterations finish, or when `--stop-on-error`
is set and an iteration fails/times out.

## Live peek

In an interactive terminal the agent's stdout/stderr stream live by default
(off automatically when piped/redirected/CI, so `ralph run … | cat` is clean).

| Key | Action |
|---|---|
| `p` | Toggle the live peek stream on/off |
| shift+`P` | Enter full-screen scrollable peek |
| `j` / `k` | (in full-screen) scroll down / up one line |
| `space` / `b` | page down / up |
| `g` / `G` | jump to top / bottom (bottom re-enables follow) |
| `[` / `]` | previous / next iteration |
| `q` or `P` | exit back to compact view |

Real-time activity tracking works with line-buffered agents (Claude Code,
Codex, Pi). Full-screen TUI/curses agents aren't supported — ralphify pipes
their stdio, so they detect a non-TTY and fall back to plain output. If output
arrives in bursts, set `PYTHONUNBUFFERED=1` in the launch environment.

## User-argument grammar

```bash
# Named flags work with or without args declared in frontmatter
ralph run research --dir ./my-project --focus "performance"
ralph run research --dir=./my-project --focus="performance"

# Positional args require args: [dir, focus] in frontmatter
ralph run research ./my-project "performance"

# Mixed — positional values skip names already given via flags
ralph run research --focus "performance" ./my-project

# -- ends flag parsing; everything after is positional
ralph run research -- --verbose ./src
```

Use `--` when a positional value starts with `--`. Missing args → empty string.
Reference values with `{{ args.<name> }}` in the body or in command `run` strings.
