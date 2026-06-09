# Python API

Everything is importable from the top-level `ralphify` package. It runs the
same loop as the CLI, so anything `ralph run` does, you can do from Python.

```python
from pathlib import Path
from ralphify import run_loop, RunConfig, RunState

config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("my-ralph"),
    ralph_file=Path("my-ralph/RALPH.md"),
    commands=[],
    max_iterations=3,
)
run_loop(config, RunState(run_id="my-run"))
```

## `run_loop(config, state, emitter=None)`

The main loop. Reads `RALPH.md`, runs commands, assembles prompts, pipes them to
the agent, repeats. **Blocks until the loop finishes.**

| Param | Type | Description |
|---|---|---|
| `config` | `RunConfig` | All settings for the run |
| `state` | `RunState` | Observable state — counters, status, control methods |
| `emitter` | `EventEmitter \| None` | Event listener; `None` = `NullEmitter` (silent) |

## `RunConfig`

Fields mirror the CLI options. Mutable — change a field mid-run and the loop
picks it up at the next iteration boundary.

| Field | Type | Default | Description |
|---|---|---|---|
| `agent` | `str` | — | Full agent command string |
| `ralph_dir` | `Path` | — | Ralph directory |
| `ralph_file` | `Path` | — | The RALPH.md file |
| `commands` | `list[Command]` | `[]` | Commands run each iteration |
| `args` | `dict[str, str]` | `{}` | User argument values |
| `max_iterations` | `int \| None` | `None` | Max iterations (`None` = unlimited) |
| `delay` | `float` | `0` | Seconds between iterations |
| `timeout` | `float \| None` | `None` | Max seconds per iteration |
| `stop_on_error` | `bool` | `False` | Stop if agent exits non-zero/times out |
| `log_dir` | `Path \| None` | `None` | Directory for iteration log files |
| `credit` | `bool` | `True` | Append co-author trailer instruction |
| `project_root` | `Path` | `Path(".")` | Project root directory |

## `Command`

```python
from ralphify import Command
Command(name="tests", run="uv run pytest -x")
Command(name="integration", run="uv run pytest tests/integration", timeout=300)
```

`name` and `run` required; `timeout` defaults to 60s.

## `RunState`

Observable state for a running loop; thread-safe control methods.

| Property | Type | Description |
|---|---|---|
| `run_id` | `str` | Unique run id |
| `status` | `RunStatus` | Lifecycle status |
| `iteration` | `int` | Current iteration (starts at 0) |
| `completed` | `int` | Successful iterations |
| `failed` | `int` | Failed iterations (includes timed out) |
| `timed_out_count` | `int` | Timed-out iterations (subset of `failed`) |
| `total` | `int` | `completed + failed` |
| `started_at` | `datetime \| None` | Start time |
| `paused` | `bool` | Currently paused |
| `stop_requested` | `bool` | Stop requested |

Control: `state.request_stop()`, `request_pause()`, `request_resume()`.

`RunStatus`: `PENDING`, `RUNNING`, `PAUSED`, `STOPPED`, `COMPLETED`, `FAILED`.
`FAILED` = stopped by `--stop-on-error` after a failure/timeout, or crashed.

`StopReason` (in `RUN_STOPPED.reason`): `"completed"`, `"error"`,
`"user_requested"`.

## Event system

The loop emits structured events at each step. Implement the `EventEmitter`
protocol (a single `emit(event)` method) to listen.

```python
from ralphify import Event, EventType, RunConfig, RunState, run_loop

class MyEmitter:
    def emit(self, event: Event) -> None:
        if event.type == EventType.ITERATION_COMPLETED:
            print(f"Iter {event.data['iteration']} in {event.data['duration_formatted']}")

run_loop(config, RunState(run_id="observed"), emitter=MyEmitter())
```

Each `Event` carries `type` (`EventType`), `run_id`, `data` (dict), and
`timestamp`. `event.to_dict()` serializes it.

### `EventType` reference

| Group | Event | Data fields |
|---|---|---|
| Run | `RUN_STARTED` | `ralph_name`, `commands`, `max_iterations`, `timeout`, `delay` |
| Run | `RUN_STOPPED` | `reason`, `total`, `completed`, `failed`, `timed_out_count` |
| Run | `RUN_PAUSED` / `RUN_RESUMED` | — |
| Iteration | `ITERATION_STARTED` | `iteration` |
| Iteration | `ITERATION_COMPLETED` | `iteration`, `returncode`, `duration`, `duration_formatted`, `detail`, `log_file`, `result_text` |
| Iteration | `ITERATION_FAILED` | same as completed |
| Iteration | `ITERATION_TIMED_OUT` | same (`returncode` is `None`) |
| Commands | `COMMANDS_STARTED` / `COMMANDS_COMPLETED` | `iteration`, `count` |
| Prompt | `PROMPT_ASSEMBLED` | `iteration`, `prompt_length` |
| Agent | `AGENT_ACTIVITY` | `iteration`, `raw` (one stream-json line; Claude Code only) |
| Agent | `AGENT_OUTPUT_LINE` | `iteration`, `line`, `stream` (all agents) |
| Other | `LOG_MESSAGE` | `message`, `level`, `traceback` (optional) |

### Built-in emitters

| Emitter | Description |
|---|---|
| `NullEmitter` | Discards all events (default) |
| `QueueEmitter` | Pushes events into a `queue.Queue` |
| `FanoutEmitter` | Broadcasts each event to multiple emitters |
| `BoundEmitter` | Wraps an emitter with a fixed `run_id`; has `log_info`, `log_error`, `agent_output_line` |

## Concurrent runs with `RunManager`

Thread-safe registry for launching and controlling multiple loops. Each run
gets its own daemon thread and event queue.

```python
from pathlib import Path
from ralphify import RunManager, RunConfig, Command

manager = RunManager()
config = RunConfig(
    agent="claude -p --dangerously-skip-permissions",
    ralph_dir=Path("docs-ralph"),
    ralph_file=Path("docs-ralph/RALPH.md"),
    commands=[Command(name="build", run="mkdocs build --strict")],
    max_iterations=5,
)
run = manager.create_run(config)
manager.start_run(run.state.run_id)

for r in manager.list_runs():
    print(f"{r.state.run_id}: {r.state.status.value} — {r.state.completed} done")

manager.pause_run(run.state.run_id)
manager.resume_run(run.state.run_id)
manager.stop_run(run.state.run_id)
```

Each run is a `ManagedRun` bundling `config`, `state`, and a `QueueEmitter`.
Register extra listeners **before** `start_run()` with
`run.add_listener(listener)` — events broadcast to both the queue and your
listeners via a `FanoutEmitter`.

Methods: `create_run(config)`, `start_run(id)`, `stop_run(id)`, `pause_run(id)`,
`resume_run(id)`, `list_runs()`, `get_run(id)`.
