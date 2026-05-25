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

| Agent | Prompt delivery | Streaming | Wrapper needed |
|---|---|---|---|
| [Claude Code](#claude-code) | Stdin (`-p`) | Yes — real-time activity tracking | No |
| [opencode](#opencode) | Positional arg (`run "<prompt>"`) | Yes — tool-use tracking | No |
| [Aider](#aider) | Via bash wrapper | No | Yes (`bash -c`) |
| [Codex CLI](#codex-cli) | Stdin (`exec`) | No | No |
| [Crush](#crush) | Stdin (`run`) | No | No |
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

## opencode

[opencode](https://opencode.ai) takes the prompt as a **positional argument** to its `run` subcommand rather than on stdin. Ralphify has a first-class adapter for it — no `bash -c` wrapper needed.

```markdown
---
agent: opencode run --agent build
---
```

| Flag | Purpose |
|---|---|
| `run` | Non-interactive mode — runs one prompt and exits |
| `--agent build` | Selects an agent profile permissive enough to edit files autonomously (see the caveat below) |

When ralphify detects that the agent command's binary is `opencode`, it automatically:

- Adds `--format json` so opencode emits a parseable event stream.
- Appends the assembled prompt as the final positional argument (no stdin, no shell — quotes, `$(...)`, and newlines in the prompt are passed through safely as a single argument).
- Parses the JSON stream to track tool use in real time.

!!! warning "opencode refuses writes by default"
    opencode's built-in agents start with restrictive `ask`/`deny` permission presets ([anomalyco/opencode #10411](https://github.com/anomalyco/opencode/issues/10411), [#13851](https://github.com/anomalyco/opencode/issues/13851)). An unconfigured `opencode run` will stall waiting for approval or refuse to edit files — there is no one to approve in an autonomous loop.

    This is opencode-side configuration, not something ralphify can override. Before looping, set up an agent profile (or permission config) that allows the edits and commands your prompt needs — the opencode analogue of Claude Code's `--dangerously-skip-permissions`. See [opencode's permissions docs](https://opencode.ai/docs/permissions/) for the `--agent` profile and permission settings.

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

## Crush

[Charm Crush](https://github.com/charmbracelet/crush) is TUI-first but supports non-interactive use via its `run` subcommand, which reads the prompt from stdin. Ralphify has a first-class adapter for it — no `bash -c` wrapper needed.

```markdown
---
agent: crush run
---
```

| Flag | Purpose |
|---|---|
| `run` | Non-interactive mode — runs one prompt from stdin and exits |

When ralphify detects that the agent command's binary is `crush`, it automatically adds `--quiet` to hide the progress spinner. `crush run` auto-approves every permission request for the duration of the invocation, so no `--yolo`-style flag is needed to run autonomously.

!!! info "Configure a provider first"
    `crush run` exits with "no providers configured" if no model provider is set up. Configure one non-interactively before looping — e.g. export `ANTHROPIC_API_KEY` (or another provider's key) or commit a `crush.json`. Run `crush` once interactively if you prefer the guided setup.

!!! warning "No structured output — turn capping unavailable"
    Crush emits plain text only (no JSON/streaming-event mode), so ralphify runs it in [blocking mode](#blocking-mode-all-other-agents) and cannot count tool calls or enforce `max_turns` for it. Completion still works via the [`<promise>` tag](#what-ralphify-needs-from-an-agent) scanned from stdout. Use [`--timeout`](cli.md#ralph-run) as the safety net instead of a turn cap.

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
