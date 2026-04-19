---
title: How to Run Claude Code, Aider, or Codex in an Autonomous Loop
description: Set up Claude Code, Aider, Codex CLI, or any AI coding agent to run autonomously in a loop with ralphify. Copy-pasteable configs, wrapper scripts, and a comparison table.
keywords: run claude code in loop, aider autonomous mode, codex cli automation, AI coding agent loop, autonomous claude code, aider loop setup, run AI agent automatically, pipe prompt to coding agent, claude code non-interactive, aider no-interactive mode, codex exec stdin, automate AI coding agent
---

# Using with Different Agents

!!! tldr "TL;DR"
    Set the `agent` field in your RALPH.md to any CLI that reads a prompt from stdin and exits when done. **Claude Code** (`claude -p --dangerously-skip-permissions`) is the default with the deepest integration. **Aider** needs a `bash -c` wrapper to pass stdin as `--message`. **Codex CLI** works natively with `codex exec`. For anything else, write a short wrapper script.

Ralphify works with **any CLI that reads a prompt from stdin and exits when done**. Claude Code is the default, but you can use any tool that follows this contract.

This page shows how to configure the [`agent` frontmatter field](quick-reference.md#frontmatter-fields) in your RALPH.md for popular agents and how to write your own wrapper.

## Agent comparison

| Agent | Stdin support | Streaming | Wrapper needed |
|---|---|---|---|
| [Claude Code](#claude-code) | Native (`-p`) | Yes — real-time activity tracking | No |
| [Aider](#aider) | Via bash wrapper | No | Yes (`bash -c`) |
| [Codex CLI](#codex-cli) | Native (`exec`) | No | No |
| [Custom](#custom-wrapper-script) | You implement it | No | Yes (script) |

If you're not sure which to pick: **start with Claude Code.** It has the deepest integration, the best autonomous coding capabilities, and is the default.

## What ralphify needs from an agent

Every iteration, ralphify runs your agent like this:

```bash
echo "<assembled prompt>" | <agent command>
```

Your agent must:

1. **Read a prompt from stdin** — the full assembled prompt is piped in
2. **Do work in the current directory** — edit files, run commands, make commits
3. **Exit cleanly** — exit code `0` means the agent process succeeded; non-zero means failure
4. **Optionally emit a completion signal** — set `completion_signal` in frontmatter (default inner text: `RALPH_PROMISE_COMPLETE`) if you want the agent to print an explicit `<promise>...</promise>` marker

Normal exit codes still indicate process success or failure. They do **not** trigger promise completion by themselves.

Ralphify only stops early on promise completion when both of these are true:

- `stop_on_completion_signal: true`
- the matching `<promise>...</promise>` tag is detected in agent output or captured result text

`completion_signal` is the inner promise text. For example, `completion_signal: COMPLETE` means the agent must output `<promise>COMPLETE</promise>`.

Ralphify still keeps its own command/prompt loop architecture. Only the promise tag format and matching align with Ralph-Wiggum.

Minimal example:

```markdown
---
agent: claude -p --dangerously-skip-permissions
completion_signal: COMPLETE
stop_on_completion_signal: true
---

Implement the next todo. When the work is fully complete, print
<promise>COMPLETE</promise> and exit.
```

That's it. No API required — just stdin in, output out, process exits.

## Claude Code

The default and recommended agent.

```markdown
---
agent: claude -p --dangerously-skip-permissions
---
```

| Flag | Purpose |
|---|---|
| `-p` | Non-interactive mode — reads prompt from stdin, prints output, exits |
| `--dangerously-skip-permissions` | Skips approval prompts so the agent can work autonomously |

Install Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
```

!!! info "Why `--dangerously-skip-permissions`?"
    Without this flag, Claude Code pauses to ask for approval before editing files, running commands, or making commits. In an autonomous loop, nobody is there to approve — so the agent would hang forever. [Commands](how-it-works.md#2-run-commands-and-capture-output) in your RALPH.md act as your guardrails instead.

### Automatic streaming mode

When ralphify detects that the agent command starts with `claude`, it automatically adds `--output-format stream-json --verbose` to the command. You don't need to add these flags yourself.

This enables ralphify to:

- Parse Claude Code's structured JSON output line by line
- Track agent activity in real time
- Extract the final result text from the agent's response

## Aider

[Aider](https://aider.chat) is an AI pair-programming tool that works with multiple LLM providers.

```markdown
---
agent: bash -c 'aider --yes-always --no-auto-commits --message "$(cat -)"'
---
```

| Flag | Purpose |
|---|---|
| `--yes-always` | Auto-approve all changes (no interactive prompts) |
| `--no-auto-commits` | Let your prompt control when commits happen |
| `--message "..."` | Pass the prompt as a message instead of stdin |

!!! note "Why the bash wrapper?"
    Aider doesn't natively read prompts from stdin. The `bash -c` wrapper reads stdin with `cat -` and passes it as a `--message` argument.

### Aider with a specific model

```markdown
---
agent: bash -c 'aider --yes-always --no-auto-commits --model claude-sonnet-4-6 --message "$(cat -)"'
---
```

## Codex CLI

[OpenAI Codex CLI](https://github.com/openai/codex) supports non-interactive use natively via its `exec` subcommand.

```markdown
---
agent: codex exec --sandbox danger-full-access -
---
```

| Flag | Purpose |
|---|---|
| `exec` | Non-interactive mode — designed for piped/scripted use |
| `--sandbox danger-full-access` | Full filesystem access for autonomous operation |
| `-` | Read prompt from stdin |

## Custom wrapper script

For full control, write a wrapper script that reads stdin and calls your agent however it needs to be called.

**`ralph-agent.sh`**

```bash
#!/bin/bash
set -e

# Read the prompt from stdin
PROMPT=$(cat -)

# Call your agent however it works
my-custom-agent --input "$PROMPT" --auto-approve
```

```bash
chmod +x ralph-agent.sh
```

**`my-ralph/RALPH.md`**

```markdown
---
agent: ./ralph-agent.sh
---

Your prompt here.
```

## Testing your setup

Verify the agent works outside of ralphify first. The command depends on which agent you're using:

=== "Claude Code"

    ```bash
    echo "Say hello and nothing else" | claude -p --dangerously-skip-permissions
    ```

    ```text
    Hello!
    ```

=== "Aider"

    ```bash
    echo "Say hello and nothing else" | bash -c 'aider --yes-always --no-auto-commits --message "$(cat -)"'
    ```

=== "Codex CLI"

    ```bash
    echo "Say hello and nothing else" | codex exec --sandbox danger-full-access -
    ```

If the agent prints a response and exits, your setup is working. If it hangs or errors, fix the agent installation before continuing.

Then test through ralphify with a single iteration using [`ralph run`](cli.md#ralph-run):

```bash
ralph run my-ralph -n 1 --log-dir ralph_logs
```

!!! tip "Non-Claude-Code agents"
    Disable auto-commits if your prompt handles commits — most agents have this feature, and it conflicts with prompt-driven commit instructions. Use [`--timeout`](cli.md#ralph-run) as a safety net in case the agent enters an unexpected interactive mode.

## How agent output works

Ralphify streams agent output line-by-line in both execution modes. In an interactive terminal, output streams live to the console by default — press `p` to silence it and `p` again to resume. See [Peeking at live agent output](cli.md#peeking-at-live-agent-output) for details.

When [`--log-dir`](cli.md#ralph-run) is set, output is captured to a log file and also echoed after each iteration completes. Live peek still works the same way in that mode.

### Streaming mode (Claude Code)

When the agent command starts with `claude`, ralphify parses the agent's structured JSON output line by line. This enables additional features beyond live output:

- **Activity tracking** — the terminal shows what the agent is doing (tool calls, reasoning) in real time
- **Result text extraction** — the agent's final response is captured separately
- **Verbose logging** — with `--log-dir`, logs include the agent's internal tool calls and reasoning

### Blocking mode (all other agents)

For non-Claude agents, ralphify spawns the process and drains stdout and stderr through background reader threads. You see the agent's plain text output line by line as it's produced.

Both modes support all ralphify features (commands, timeouts, iteration tracking, live peek). The difference is that Claude Code gets structured activity tracking on top of the raw output.

## Adapting other tools

Many AI coding tools don't read from stdin directly but can be adapted with a bash wrapper. The pattern is:

```bash
bash -c '<tool> <auto-approve-flag> --message "$(cat -)"'
```

The `cat -` reads the piped prompt from stdin and passes it as a command-line argument. This works for any tool that accepts a prompt via a flag (like `--message`, `--input`, `--prompt`).

If the tool has no way to accept a prompt non-interactively, a [custom wrapper script](#custom-wrapper-script) is the escape hatch — you can use the prompt text however the tool needs it.

## Next steps

- [Getting Started](getting-started.md) — set up your first loop with the agent you just configured
- [Troubleshooting](troubleshooting.md) — when the agent hangs, produces no output, or exits unexpectedly
