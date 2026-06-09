# Using different agents

Ralphify works with **any CLI that reads a prompt from stdin and exits when
done**. Every iteration it runs `echo "<assembled prompt>" | <agent command>`.
Your agent must read the prompt from stdin, do work in the current directory,
and exit (0 = success, non-zero = failure).

| Agent | Stdin support | Streaming | Wrapper needed |
|---|---|---|---|
| Claude Code | Native (`-p`) | Yes — real-time activity tracking | No |
| Codex CLI | Native (`exec`) | No | No |
| Pi | Native (`-p`) | No | No |
| Custom | You implement it | No | Yes (script) |

If unsure, **start with Claude Code** — it's the default and has the deepest
integration.

## Claude Code

```markdown
agent: claude -p --dangerously-skip-permissions
```

`-p` = non-interactive (read prompt from stdin, print, exit).
`--dangerously-skip-permissions` skips approval prompts so the agent works
autonomously — without it the agent hangs forever waiting for an approval
nobody is there to give. Install: `npm install -g @anthropic-ai/claude-code`.
When the command starts with `claude`, ralphify auto-adds
`--output-format stream-json --verbose` for activity tracking and result-text
extraction.

## Codex CLI

```markdown
agent: codex exec --sandbox danger-full-access -
```

`exec` is non-interactive mode, `--sandbox danger-full-access` grants full
filesystem access, `-` reads the prompt from stdin.

## Pi

[Pi](https://pi.dev) is a minimal coding-agent CLI. Print mode reads the piped
prompt from stdin natively, so no wrapper is needed:

```markdown
agent: pi -p -a
```

`-p` is print mode (non-interactive: read piped stdin as the prompt, print the
response, exit). `-a` (`--approve`) trusts the project-local Pi config and
extensions for the run so the loop runs unattended. Install with `npm install
-g --ignore-scripts @earendil-works/pi-coding-agent` or
`curl -fsSL https://pi.dev/install.sh | sh`.

## Custom wrapper script

For anything else, write a script that reads stdin and calls your agent:

```bash
#!/bin/bash
set -e
PROMPT=$(cat -)
my-custom-agent --input "$PROMPT" --auto-approve
```

```markdown
agent: ./ralph-agent.sh
```

General pattern for tools that take a prompt via a flag:
`bash -c '<tool> <auto-approve-flag> --message "$(cat -)"'`.

**Test any agent outside ralphify first** (`echo "Say hello" | <agent
command>`), then through ralphify with `ralph run my-ralph -n 1 --log-dir
ralph_logs`. The auto-approve / skip-permissions flag is mandatory for every
agent — an unattended loop can't answer interactive prompts.
