---
description: Configure ralphify with Claude Code, Aider, Codex CLI, or any custom agent. Includes setup guides, compatibility checklist, and wrapper script examples.
---

# Using with Different Agents

Ralphify works with **any CLI that reads a prompt from stdin and exits when done**. Claude Code is the default, but you can swap in any tool that follows this contract.

This page shows how to configure ralphify for popular agents and how to write your own wrapper.

## What ralphify needs from an agent

Every iteration, ralphify runs your agent like this:

```
echo "<assembled prompt>" | <command> <args...>
```

Your agent must:

1. **Read a prompt from stdin** — the full assembled prompt (with contexts, instructions, and any check failures) is piped in
2. **Do work in the current directory** — edit files, run commands, make commits
3. **Exit when done** — exit code 0 means success, non-zero means failure

That's it. No special protocol, no API — just stdin in, work done, process exits.

## Claude Code

The default configuration. Claude Code's `-p` flag reads from stdin and runs non-interactively.

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
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
    Without this flag, Claude Code pauses to ask for approval before editing files, running commands, or making commits. In an autonomous loop, nobody is there to approve — so the agent would hang forever. Checks act as your guardrails instead.

### Automatic streaming mode

When ralphify detects that the agent command is `claude`, it automatically adds `--output-format stream-json --verbose` to the command. You don't need to add these flags yourself — they're injected at runtime.

This enables ralphify to:

- Parse Claude Code's structured JSON output line by line
- Track agent activity in real time
- Extract the final result text from the agent's response

The flags are appended to whatever `args` you configure in `ralph.toml`, so the actual command executed each iteration is:

```
claude -p --dangerously-skip-permissions --output-format stream-json --verbose
```

This is transparent — your logs and terminal output work the same way. If you're debugging and want to see exactly what Claude Code receives, the `--verbose` flag means the agent's internal tool calls and reasoning are included in the log files when using `--log-dir`.

## Aider

[Aider](https://aider.chat) is an AI pair-programming tool that works with multiple LLM providers. It supports a message flag that accepts the prompt directly.

```toml
[agent]
command = "bash"
args = ["-c", "aider --yes-always --no-auto-commits --message \"$(cat -)\""]
ralph = "RALPH.md"
```

| Flag | Purpose |
|---|---|
| `--yes-always` | Auto-approve all changes (no interactive prompts) |
| `--no-auto-commits` | Let your prompt control when commits happen |
| `--message "..."` | Pass the prompt as a message instead of stdin |

!!! note "Why the bash wrapper?"
    Aider doesn't natively read prompts from stdin. The `bash -c` wrapper reads stdin with `cat -` and passes it as a `--message` argument. This is a common pattern for adapting tools that don't support piped input directly.

### Aider with a specific model

```toml
[agent]
command = "bash"
args = ["-c", "aider --yes-always --no-auto-commits --model claude-sonnet-4-6 --message \"$(cat -)\""]
ralph = "RALPH.md"
```

## Codex CLI

[OpenAI Codex CLI](https://github.com/openai/codex) can be configured to run non-interactively.

```toml
[agent]
command = "bash"
args = ["-c", "codex --approval-mode full-auto \"$(cat -)\""]
ralph = "RALPH.md"
```

| Flag | Purpose |
|---|---|
| `--approval-mode full-auto` | Skip all approval prompts for autonomous operation |

## Custom wrapper script

For full control, write a wrapper script that reads stdin and calls your agent however it needs to be called.

**`ralph-agent.sh`**

```bash
#!/bin/bash
set -e

# Read the prompt from stdin
PROMPT=$(cat -)

# Call your agent however it works
# Examples:
#   curl an API, save response, apply changes
#   call a local LLM with the prompt
#   pipe to any tool that accepts text input

my-custom-agent --input "$PROMPT" --auto-approve
```

```bash
chmod +x ralph-agent.sh
```

**`ralph.toml`**

```toml
[agent]
command = "./ralph-agent.sh"
args = []
ralph = "RALPH.md"
```

## Testing your setup

Verify the agent works outside of ralphify first:

```bash
echo "Say hello" | <your-command> <your-args>
```

Then test through ralphify with a single iteration:

```bash
ralph run -n 1 --log-dir ralph_logs
```

!!! tip "Non-Claude-Code agents"
    Disable auto-commits if your prompt handles commits — most agents have this feature, and it conflicts with prompt-driven commit instructions. Use `--timeout` as a safety net in case the agent enters an unexpected interactive mode.
