---
title: Lifecycle Hooks
description: Subscribe to ralphify iteration boundaries, tool-use events, and turn-cap signals via shell commands declared in RALPH.md frontmatter or Python AgentHook implementations.
keywords: ralphify hooks, shell hooks, agent lifecycle hooks, on_tool_use, on_iteration_completed, on_turn_capped, RALPH.md hooks field
---

# Lifecycle Hooks

Hooks let you react to ralphify iteration boundaries, tool-use events, and turn-cap signals without modifying the engine. Two flavors exist:

- **Shell hooks** — declared in `RALPH.md` frontmatter under the `hooks:` field. Each entry is a `{event, run}` pair; ralphify pipes the event payload as JSON to the command's stdin. No Python required.
- **Python hooks** — classes implementing the `AgentHook` Protocol. Pass them via `RunConfig(hooks=[...])` to `run_loop`. Useful when embedding ralphify in a larger application.

This page covers both.

## Available events

| Event | Fires when | Payload fields |
|---|---|---|
| `on_iteration_started` | Right before commands run for an iteration | `iteration` |
| `on_commands_completed` | After all commands finish, before prompt assembly | `iteration`, `outputs` (`{name: stdout}`) |
| `on_prompt_assembled` | After placeholder resolution, before agent spawn | `iteration`, `prompt` |
| `on_tool_use` | Each time the adapter parses a `tool_use` event | `iteration`, `tool_name`, `count` |
| `on_turn_approaching_limit` | When `count >= max_turns - max_turns_grace` | `iteration`, `count`, `max_turns` |
| `on_turn_capped` | When `count >= max_turns` and the agent is about to be terminated | `iteration`, `count` |
| `on_iteration_completed` | After the iteration's `AgentResult` is finalized | `iteration`, `result` (dict form) |
| `on_completion_signal` | When the adapter detects a `<promise>...</promise>` tag | `iteration`, `signal` |

Event names are validated when frontmatter loads — unknown names raise a clear error.

The `on_tool_use`, `on_turn_approaching_limit`, and `on_turn_capped` events only fire for adapters that count tool uses (`counts_what == "tool_use"` — Claude, Codex, Copilot, opencode). Adapters like Crush that emit no structured events never produce these callbacks.

## Shell hooks (RALPH.md)

Add a `hooks:` list to your frontmatter. Each entry is parsed with `shlex.split` (no shell metacharacters); the event payload is JSON-encoded and written to the command's stdin.

```markdown
---
agent: claude -p --dangerously-skip-permissions
max_turns: 20
hooks:
  - event: on_iteration_started
    run: ./scripts/notify-start.sh
  - event: on_turn_approaching_limit
    run: ./scripts/page-oncall.sh
  - event: on_iteration_completed
    run: ./scripts/log-result.py
---
```

A minimal `notify-start.sh`:

```bash
#!/bin/bash
payload=$(cat -)
echo "iteration starting: $payload" >> ralph_events.log
```

The payload for `on_iteration_started` is `{"iteration": 3}`.

### Failure handling

- Hook stdout is captured to the run log.
- A non-zero exit code is logged but does **not** abort the run — hooks are observers, not gatekeepers.
- One misbehaving hook does not poison the others. Each hook is invoked independently with per-call exception isolation.

### Multiple hooks for one event

You can register multiple hooks for the same event. They run in declaration order:

```markdown
---
hooks:
  - event: on_iteration_completed
    run: ./scripts/save-metrics.sh
  - event: on_iteration_completed
    run: ./scripts/notify-slack.sh
---
```

## Python hooks (`AgentHook` Protocol)

For tighter integration, implement the `AgentHook` Protocol directly. All methods are keyword-only so future field additions stay backward compatible.

```python
from ralphify import RunConfig, RunState, run_loop
from ralphify.hooks import NoOpAgentHook


class MetricsHook(NoOpAgentHook):
    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None:
        print(f"iter {iteration}: {tool_name} (#{count})")

    def on_turn_capped(self, *, iteration: int, count: int) -> None:
        print(f"iter {iteration}: capped at {count} turns")


config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("."),
    ralph_file=Path("RALPH.md"),
    hooks=[MetricsHook()],
)
run_loop(config, RunState(run_id="my-run"))
```

`NoOpAgentHook` provides empty implementations of every method so you only override the ones you care about. Pass any number of hooks via `RunConfig(hooks=[...])`; ralphify wraps them in a `CombinedAgentHook` that fans events with exception isolation.

## When to use which

- **Shell hooks** when the action is a small script, lives in your repo, and benefits from the agent's own exit-code semantics.
- **Python hooks** when you're embedding ralphify, need access to the live `RunState`, or want type-safe payloads.

Both run in the same process as the engine. Long-running hook code blocks the loop, so keep heavy work asynchronous (fire-and-forget background scripts, queues, etc.).

## Soft wind-down vs. hooks

Don't confuse the `on_turn_approaching_limit` hook (yours, observer-only) with the per-CLI soft wind-down message injected directly into Claude or Codex (theirs, in-band). The wind-down message is a hint to the agent so it has time to hand off cleanly; your hook fires alongside it so external systems can observe the same threshold.

## See also

- [Quick Reference — frontmatter fields](quick-reference.md#frontmatter-fields)
- [Using with Different Agents](agents.md)
