---
description: Use ralphify as a Python library — run loops programmatically, listen to events, and discover primitives without the CLI.
---

# Python API

Ralphify can be used as a Python library. This is useful when you want to embed the loop in a larger automation pipeline, react to events programmatically, or script runs with more control than the CLI provides.

All public API is available from the top-level `ralphify` package.

## Quick start

```python
from ralphify import run_loop, RunConfig, RunState

config = RunConfig(
    command="claude",
    args=["-p", "--dangerously-skip-permissions"],
    ralph_file="RALPH.md",
    max_iterations=3,
)
state = RunState(run_id="my-run")
run_loop(config, state)
```

This runs the same loop as `ralph run -n 3`. When the loop finishes, `state` contains the results.

## `run_loop(config, state, emitter=None)`

The main loop. Discovers primitives, assembles prompts, pipes them to the agent, runs checks, and repeats. Blocks until the loop finishes.

| Parameter | Type | Description |
|---|---|---|
| `config` | `RunConfig` | All settings for the run |
| `state` | `RunState` | Observable state — counters, status, control methods |
| `emitter` | `EventEmitter | None` | Event listener. `None` uses `NullEmitter` (silent) |

## `RunConfig`

Fields match the CLI options:

```python
config = RunConfig(
    command="claude",
    args=["-p", "--dangerously-skip-permissions"],
    ralph_file="RALPH.md",
    prompt_text=None,       # Ad-hoc prompt (overrides ralph_file)
    ralph_name=None,        # Named ralph from .ralphify/ralphs/
    max_iterations=10,
    delay=2.0,
    timeout=300,
    stop_on_error=True,
    log_dir="ralph_logs",
    project_root=Path("."),
)
```

`RunConfig` is mutable — you can change fields mid-run, and the loop picks up changes at the next iteration boundary.

## `RunState`

Observable state for a running loop:

```python
state = RunState(run_id="my-run")
run_loop(config, state)

print(state.status)      # RunStatus.COMPLETED
print(state.completed)   # 4
print(state.failed)      # 1
print(state.total)       # 5
```

### Control methods

Thread-safe methods for controlling the loop from another thread:

```python
state.request_stop()      # Stop after current iteration
state.request_pause()     # Pause between iterations
state.request_resume()    # Resume a paused loop
state.request_reload()    # Re-discover primitives before next iteration
```

## Event system

The loop emits structured events. Implement the `EventEmitter` protocol (a single `emit(event)` method) to listen:

```python
from ralphify import Event, EventType, RunConfig, RunState, run_loop


class MyEmitter:
    def emit(self, event: Event) -> None:
        if event.type == EventType.ITERATION_COMPLETED:
            print(f"Iteration {event.data['iteration']} completed")
        elif event.type == EventType.CHECK_FAILED:
            print(f"  Check '{event.data['name']}' failed")


config = RunConfig(command="claude", args=["-p"], ralph_file="RALPH.md", max_iterations=3)
state = RunState(run_id="observed-run")
run_loop(config, state, emitter=MyEmitter())
```

Each `Event` has `type` (`EventType`), `run_id`, `data` (dict), and `timestamp`. Use `event.to_dict()` to serialize.

Built-in emitters: `NullEmitter` (silent), `QueueEmitter` (pushes to a `queue.Queue`), `FanoutEmitter` (broadcasts to multiple emitters).

## Primitive discovery

Discover checks, contexts, instructions, and ralphs without running the loop:

```python
from pathlib import Path
from ralphify import discover_checks, discover_contexts, discover_instructions, discover_ralphs

root = Path(".")

for check in discover_checks(root):
    print(f"Check: {check.name}, command: {check.command}, enabled: {check.enabled}")

for ctx in discover_contexts(root):
    print(f"Context: {ctx.name}, command: {ctx.command}")
```

Run discovered primitives directly:

```python
from ralphify import run_all_checks, run_all_contexts

enabled_checks = [c for c in discover_checks(root) if c.enabled]
results = run_all_checks(enabled_checks, root)
for r in results:
    print(f"  {r.check.name}: {'PASS' if r.passed else 'FAIL'}")
```
