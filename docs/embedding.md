---
title: Embedding Ralphify as a Headless Engine
description: Drive ralphify from a long-lived Python process — headless import without rich/typer, in-memory prompts, concurrent run lifecycle, typed events, and a clean shutdown.
keywords: embed ralphify, headless agent loop, ralphify library, RunManager lifecycle, in-memory prompt, typed events, shutdown RunManager, concurrent AI agent runs
---

# Embedding Ralphify

!!! tldr "TL;DR"
    `import ralphify` pulls in only the engine — no `rich` or `typer`. Drive runs from your own process with `RunManager`: `create_run` → `start_run` → `wait_for_any` / `wait_for_all` → `get_result` → `shutdown`. Run prompts straight from memory with `RunConfig(prompt=...)`, and annotate event handlers with the typed payloads.

This page is for embedders driving ralphify as a library from a long-lived host process (a web server, a scheduler, another agent). For the full API reference, see the [Python API](api.md).

## Headless import — no TUI dependencies

The engine, manager, and event system are TUI-free. Install ralphify without the `[cli]` extra and the import chain pulls in neither `rich` nor `typer`:

```bash
pip install ralphify          # engine only (pyyaml)
pip install 'ralphify[cli]'   # adds the `ralph` console script (rich + typer)
```

```python
import ralphify, sys

assert "rich" not in sys.modules
assert "typer" not in sys.modules
```

The `ralph` console script stays registered either way. If it is invoked without the `[cli]` extra installed, it exits with an actionable message:

```
The `ralph` CLI requires the [cli] extra: pip install 'ralphify[cli]'
```

`pyyaml` stays a core dependency — frontmatter parsing is part of the engine, not the TUI.

## Running a prompt from memory

Embedders that already hold the prompt body in memory don't need to write a throwaway `RALPH.md`. Set `RunConfig.prompt` instead of `ralph_file`:

```python
from pathlib import Path
from ralphify import RunConfig, RunState, run_loop

config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("."),
    prompt="Fix the failing test in {{ args.target }} and commit.",
    args={"target": "tests/test_widget.py"},
    max_iterations=3,
)
run_loop(config, RunState(run_id="in-memory"))
```

`prompt` is the prompt **body** — placeholders (`{{ commands.x }}`, `{{ args.x }}`, `{{ ralph.x }}`) are still resolved, but no frontmatter is parsed from it. Set `agent`, `commands`, and `args` on `RunConfig` directly.

!!! note "Exactly one prompt source"
    `RunConfig` requires exactly one of `prompt` or `ralph_file`. Passing both or neither raises `ValueError`.

## Typed event payloads

`Event` is generic over its data payload. Annotate handlers with the concrete `TypedDict` and your type checker carries the payload type through — no `.get()` or `cast`:

```python
from ralphify import Event, EventType, IterationEndedData

def on_iteration(event: Event[IterationEndedData]) -> None:
    duration = event.data["duration_formatted"]  # statically typed str
    print(f"iteration {event.data['iteration']} took {duration}")
```

The exported payload types are `RunStartedData`, `RunStoppedData`, `IterationStartedData`, `IterationEndedData`, `CommandsStartedData`, `CommandsCompletedData`, `PromptAssembledData`, `AgentActivityData`, `AgentOutputLineData`, `ToolUseData`, `TurnApproachingLimitData`, `TurnCappedData`, and `LogMessageData`. `EventData` is the union of all of them; an emitter that handles arbitrary events receives `Event[EventData]` and narrows on `event.type`. `to_dict()` is unchanged — `TypedDict`s are plain dicts at runtime.

## Thread-safety

`RunManager` is thread-safe. Each run executes on its own daemon thread; the registry, control methods, and the wait primitives are guarded internally. You can call `start_run`, `stop_run`, `pause_run`, `resume_run`, `get_result`, and the wait methods from any thread.

`RunState` exposes the same thread-safe control methods (`request_stop`, `request_pause`, `request_resume`) — safe to call while the run thread is mid-iteration; they take effect at the next iteration boundary.

## The run lifecycle

The supported lifecycle for a managed run is **create → start → wait → result → shutdown**:

```python
from pathlib import Path
from ralphify import RunManager, RunConfig

manager = RunManager()

a = manager.create_run(RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("."), prompt="task A", max_iterations=2,
))
b = manager.create_run(RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("."), prompt="task B", max_iterations=2,
))

manager.start_run(a.state.run_id)
manager.start_run(b.state.run_id)

# Block until at least one finishes (returns the finished run IDs).
done = manager.wait_for_any([a.state.run_id, b.state.run_id], timeout=300)

# Block until all finish (returns True iff every run finished in time).
all_done = manager.wait_for_all([a.state.run_id, b.state.run_id], timeout=300)

# Snapshot the structured outcome.
result = manager.get_result(a.state.run_id)
print(result.status, result.completed, result.failed)

# Request stop on every run and join their threads.
manager.shutdown(timeout=30)
```

### Waiting for completion

| Method | Returns | Blocks until |
|---|---|---|
| `wait_for_any(run_ids, timeout=None)` | `list[str]` — the finished run IDs (`[]` on timeout) | at least one of `run_ids` reaches a terminal status |
| `wait_for_all(run_ids, timeout=None)` | `bool` — `True` iff all finished | every run in `run_ids` finishes, or `timeout` elapses |

Both are backed by an internal condition notified when any run thread exits — no polling. A terminal status is `COMPLETED`, `STOPPED`, or `FAILED`. Unknown run IDs are ignored by `wait_for_any` and can never satisfy `wait_for_all`.

### Reading the result

`get_result(run_id)` returns a frozen `RunResult` snapshot. It reports the **current** counts regardless of terminal state, so wait first (e.g. with `wait_for_all`) if you want the final outcome. It raises `KeyError` for an unknown run ID.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | The run's ID |
| `status` | `RunStatus` | Current lifecycle status |
| `total` | `int` | `completed + failed` |
| `completed` | `int` | Successful iterations |
| `failed` | `int` | Failed iterations (includes timed out) |
| `timed_out_count` | `int` | Timed-out iterations (subset of `failed`) |

### Shutting down

`shutdown(timeout=None)` requests stop on every registered run and joins each live thread. It returns `True` iff all live threads joined within `timeout`; with `timeout=None` it blocks until every run thread exits. Unstarted runs are harmless — there is no thread to join. Call it once when the host process is winding down.

## Next steps

- [**Python API**](api.md) — full reference for every public type and method
- [**How the loop works**](how-it-works.md) — the iteration cycle `run_loop` executes
