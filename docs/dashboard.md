---
description: How to install, launch, and use the ralphify web dashboard to manage runs, browse ralphs, edit primitives, and review history.
---

# Web Dashboard

Ralphify includes a web-based orchestration dashboard that lets you manage
multiple runs, watch iterations in real time, and edit primitives — all from
your browser.

## Install

The dashboard requires optional dependencies:

=== "uv tool (recommended)"

    If you installed ralphify with `uv tool install`, reinstall with the UI extra:

    ```bash
    uv tool install "ralphify[ui]"
    ```

=== "pipx"

    ```bash
    pipx install "ralphify[ui]"
    ```

=== "pip"

    ```bash
    pip install "ralphify[ui]"
    ```

This adds FastAPI, uvicorn, and WebSocket support.

## Launch

```bash
ralph ui
```

The dashboard opens at [http://127.0.0.1:8765](http://127.0.0.1:8765).

<figure markdown="span">
  ![Ralphify dashboard — Runs tab](assets/dashboard/runs-tab.png){ loading=lazy }
  <figcaption>The Runs tab is your starting point for launching and monitoring autonomous loops.</figcaption>
</figure>

| Option    | Default       | Description              |
|-----------|---------------|--------------------------|
| `--port`  | `8765`        | Port to serve the UI on  |
| `--host`  | `127.0.0.1`   | Host to bind to          |

To expose the dashboard on your network:

```bash
ralph ui --host 0.0.0.0 --port 9000
```

## Dashboard tabs

The dashboard has three tabs: **Runs**, **Configure**, and **History**.

### Runs

The Runs tab is the default landing page. When no runs are active, it shows an
onboarding view with three steps — Configure, Launch, Monitor — and a prominent
**+ New Run** button to get you started.

Once a run is active, select it in the sidebar to see its iterations as they
complete:

- Pass/fail status with color-coded badges
- Agent output (truncated to 5,000 characters, same as the CLI)
- Check results with individual pass/fail/timeout indicators
- Duration and return codes
- **Live agent activity stream** (Claude Code only) — see tool calls and text
  output as they happen

Each check gets a **sparkline bar** showing its pass/fail history across
iterations. Green means pass, red means fail, yellow means timeout — useful for
spotting flaky checks or regressions at a glance.

Events stream over WebSocket, so the page updates without refreshing.

### Configure

The Configure tab is your central hub for managing all primitives. The overview
shows four cards — **Ralphs**, **Checks**, **Contexts**, and **Instructions** —
each displaying how many items exist.

<figure markdown="span">
  ![Configure tab overview](assets/dashboard/configure-tab.png){ loading=lazy }
  <figcaption>The Configure overview shows all four primitive types with counts. Click any card to drill in.</figcaption>
</figure>

Click into any primitive type to see its items. Each list shows the name,
command (for checks and contexts), and enabled status:

<figure markdown="span">
  ![Checks list in Configure](assets/dashboard/configure-checks.png){ loading=lazy }
  <figcaption>Drill into Checks to see each check's command and enabled status.</figcaption>
</figure>

Click an item to open its editor, where you can:

- Edit the **description**, **command**, and **timeout** fields
- Toggle the **enabled** switch
- Edit the **content** (failure instructions for checks, static content for contexts)
- **Delete** the primitive entirely
- **Create new** primitives with the button at the top of each list

<figure markdown="span">
  ![Editing a check](assets/dashboard/check-editor.png){ loading=lazy }
  <figcaption>Click a check to edit its command, timeout, failure instruction, and enabled toggle.</figcaption>
</figure>

The Ralphs section works the same way — browse, create, edit, and delete named
ralphs without leaving the browser. Each ralph card also has a **Run** button
(visible on hover, always visible on mobile) that opens the New Run modal with
that ralph pre-selected — so you can go from browsing ralphs to launching a run
in one click. The ralph editor has a **Run this ralph** button in the header
for the same shortcut.

<figure markdown="span">
  ![Ralphs list in Configure](assets/dashboard/configure-prompts.png){ loading=lazy }
  <figcaption>Drill into Ralphs to browse and manage your named ralphs. Hover over a card to see the Run button.</figcaption>
</figure>

Changes are written directly to the `.ralphify/` directory on disk.

### History

The History tab shows all past runs — completed, stopped, and failed. Each run
displays its pass rate, iteration count, and status badge. Click any run to
review its full iteration details, including individual check results and agent
output for every iteration.

When no runs have completed yet, the tab shows an onboarding prompt with a
button to start your first run.

<figure markdown="span">
  ![History tab](assets/dashboard/history-tab.png){ loading=lazy }
  <figcaption>The History tab lists all past runs with pass rates and status badges. Click any run to drill into its iterations.</figcaption>
</figure>

## Starting a run

Click **New Run** in the sidebar to open the run modal. It lets you:

- **Pick a named ralph** — cards show every ralph discovered in `.ralphify/ralphs/`
- **Preview the ralph** — after selecting a ralph, expand the preview panel to see its full content before launching
- **Enter an ad-hoc prompt** — toggle to ad-hoc mode and type a one-off task
- **Configure settings** — expand the settings panel to set max iterations, delay between iterations, timeout, and stop-on-error

<figure markdown="span">
  ![New Run dialog](assets/dashboard/new-run-dialog.png){ loading=lazy }
  <figcaption>Pick a named ralph or write an ad-hoc one. The Settings panel is collapsed by default.</figcaption>
</figure>

<figure markdown="span">
  ![New Run with settings expanded](assets/dashboard/new-run-settings.png){ loading=lazy }
  <figcaption>Select a ralph and expand Settings to configure iterations, delay, timeout, and stop-on-error before launching.</figcaption>
</figure>

Once a run starts, you can **pause**, **resume**, or **stop** it from the
sidebar or the controls bar above the iteration view on the Runs tab.

## Live agent activity stream

When the agent command is Claude Code, the dashboard shows a real-time activity
feed inside each iteration. Instead of waiting for the iteration to finish, you
can watch the agent think, call tools, and produce output as it happens.

The activity stream appears below each iteration card on the Runs tab and shows:

- **Tool calls** — each tool invocation (Read, Edit, Bash, Grep, Write, Glob,
  etc.) appears as a color-coded badge with a summary of the input (file path,
  command, or search pattern). Click a tool call to expand and see its full
  result in a dark terminal-style panel.
- **Text output** — the agent's reasoning and responses stream in as they are
  generated.
- **Cost and token stats** — when the iteration completes, the header shows the
  total cost (USD) and token count for that iteration.

The feed auto-scrolls to follow new activity. Scroll up manually to pause
auto-scroll and review earlier output — it resumes when you scroll back to the
bottom.

!!! info "Claude Code only"
    The live activity stream requires Claude Code as the agent command. When
    Claude Code is detected, ralphify automatically adds
    `--output-format stream-json --verbose` to the agent command and streams
    each JSON line as an event. Other agents fall back to the standard
    `subprocess.run()` path — you'll still see the full output once the
    iteration completes, but not the live feed.

!!! tip "Tool result truncation"
    Long tool results are truncated to 2,000 characters in the activity stream
    to keep the UI responsive. The full output is still captured in the
    iteration log file if you use `--log-dir`.

## Adjusting settings mid-run

You don't have to stop and restart a run to change its settings. While a run is
active, click the **Run Settings** gear icon below the run overview to expand
the settings panel. From there you can adjust:

- **Max iterations** — increase or decrease the remaining iteration limit
- **Delay** — change the pause between iterations (in seconds)
- **Timeout** — change the per-iteration timeout (in seconds)
- **Stop on first error** — toggle whether the loop halts on agent failure

Make your changes and click **Apply**. A "modified" badge appears next to the
gear icon when you have unapplied changes. All settings take effect on the
**next iteration** — the currently running iteration (if any) is not
interrupted.

This is useful when you see the loop is working well and want to extend it
(raise the iteration limit), or when you notice iterations are taking too long
and want to add a timeout — all without losing the run's progress or history.

!!! tip "Settings vs. primitives"
    Run settings (iterations, delay, timeout, stop-on-error) can be changed
    mid-run and take effect immediately. Primitive configurations (checks,
    contexts, instructions) are loaded once at run start and require a restart
    to pick up changes. See [Editing while a run is active](#editing-while-a-run-is-active)
    for the full breakdown.

## Editing while a run is active

The dashboard lets you edit primitives via the Configure tab while a run is in progress, but not all changes take effect immediately:

| What you change | When it takes effect |
|---|---|
| `RALPH.md` content | Next iteration — the prompt is re-read from disk every iteration |
| Context command output | Next iteration — context commands re-run every iteration |
| Run settings (iterations, delay, timeout, stop-on-error) | Next iteration — applied via the [settings panel](#adjusting-settings-mid-run) |
| Check/context/instruction config (frontmatter, body, enable/disable) | After restart — primitive configurations are loaded once when a run starts |
| New or deleted primitives | After restart — primitive discovery happens once at run start |

To apply primitive configuration changes to a running run, **stop** the run and **start a new one**. The new run will discover the updated primitives from disk.

!!! tip "Prompt edits are always live"
    The most common adjustment — adding a constraint or changing the task in your prompt — takes effect on the very next iteration without restarting. This is the primary way to steer the agent in real time.

## Data storage

The dashboard persists run history, iterations, check results, and raw events
in a SQLite database at `~/.ralphify/ui.db`. This is what powers the History tab
and the iterations endpoint — data survives across dashboard restarts.

The database is created automatically on first launch. To reset all history,
stop the dashboard and delete the file:

```bash
rm ~/.ralphify/ui.db
```

## Architecture

The dashboard is a single-page app that talks to a FastAPI backend:

```
Browser (Preact + htm)
  ↕ WebSocket (live events)
  ↕ REST API (run management, primitives)
FastAPI (uvicorn)
  ↕ RunManager (threading)
  ↕ run_loop (engine.py)
```

- **Backend**: FastAPI serves the REST API and WebSocket endpoint. Each run
  executes in its own thread using the same `run_loop()` that powers the CLI.
- **Frontend**: A Preact app bundled with esbuild. No build step needed to use
  it — the compiled bundle ships with the package.
- **Events**: The run loop emits structured events (iteration started, check
  passed, check failed, etc.) into a queue. An async task drains the queue and
  broadcasts events to all connected WebSocket clients.

## Responsive layout

The dashboard adapts to smaller screens. On tablets and phones (below 900px
wide), the sidebar collapses into a slide-out drawer — tap the hamburger menu to
open it and the overlay to close it. Controls and spacing tighten further below
600px so the dashboard remains usable on a phone.

<figure markdown="span">
  ![Mobile dashboard view](assets/dashboard/mobile-view.png){ width="360" loading=lazy }
  <figcaption>On phones, the sidebar collapses and the layout stacks vertically.</figcaption>
</figure>

## Keyboard shortcuts

The dashboard supports keyboard shortcuts for common actions:

| Shortcut | Where | Action |
|---|---|---|
| <kbd>Cmd+S</kbd> / <kbd>Ctrl+S</kbd> | Primitive editor | Save changes to the current primitive |
| <kbd>Cmd+S</kbd> / <kbd>Ctrl+S</kbd> | Create primitive form | Create the new primitive |
| <kbd>Escape</kbd> | New Run modal | Close the modal |

The save shortcut works in both the edit and create views of the Configure tab — press <kbd>Cmd+S</kbd> (Mac) or <kbd>Ctrl+S</kbd> (Windows/Linux) instead of clicking the Save or Create button.

## REST API

The dashboard exposes a REST API you can use to script runs, manage primitives,
and build custom integrations. All examples below assume the dashboard is running
at `http://127.0.0.1:8765`.

### Runs

#### Start a new run

```bash
curl -X POST http://127.0.0.1:8765/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "project_dir": ".",
    "max_iterations": 5,
    "delay": 2,
    "timeout": 300,
    "stop_on_error": true
  }'
```

The request body accepts these fields:

| Field            | Type          | Default      | Description                                         |
|------------------|---------------|--------------|-----------------------------------------------------|
| `project_dir`    | string        | `"."`        | Path to the project directory                       |
| `prompt_file`    | string        | `"RALPH.md"` | Path to the ralph file                              |
| `prompt_text`    | string\|null  | `null`       | Inline prompt text (overrides `prompt_file`)        |
| `prompt_name`    | string\|null  | `null`       | Named ralph to use from `.ralphify/ralphs/`         |
| `command`        | string\|null  | `null`       | Agent command (reads from `ralph.toml` if omitted)  |
| `args`           | list\|null    | `null`       | Agent arguments (reads from `ralph.toml` if omitted)|
| `max_iterations` | int\|null     | `null`       | Max iterations (`null` = unlimited)                 |
| `delay`          | float         | `0`          | Seconds to wait between iterations                  |
| `timeout`        | float\|null   | `null`       | Seconds before killing a stuck iteration            |
| `stop_on_error`  | bool          | `false`      | Stop the loop if the agent exits non-zero           |
| `log_dir`        | string\|null  | `null`       | Directory to save iteration logs                    |

Response:

```json
{
  "run_id": "a1b2c3d4",
  "status": "running",
  "iteration": 0,
  "completed": 0,
  "failed": 0,
  "timed_out": 0,
  "prompt_name": null,
  "started_at": "2026-03-11T14:23:01.123456",
  "max_iterations": 5,
  "delay": 2.0,
  "timeout": 300.0,
  "stop_on_error": true
}
```

You can provide a prompt three ways — pick one:

- **`prompt_file`** — path to a markdown file (default: reads `RALPH.md`)
- **`prompt_text`** — raw prompt string passed inline
- **`prompt_name`** — name of a ralph in `.ralphify/ralphs/`

#### List all runs

```bash
curl http://127.0.0.1:8765/api/runs
```

```json
[
  {
    "run_id": "a1b2c3d4",
    "status": "running",
    "iteration": 3,
    "completed": 2,
    "failed": 1,
    "timed_out": 0,
    "prompt_name": "docs",
    "started_at": "2026-03-11T14:23:01.123456",
    "max_iterations": 5,
    "delay": 2.0,
    "timeout": 300.0,
    "stop_on_error": true
  }
]
```

#### Get run details

```bash
curl http://127.0.0.1:8765/api/runs/a1b2c3d4
```

Returns the same shape as the list response, for a single run.

#### Pause, resume, and stop

```bash
curl -X POST http://127.0.0.1:8765/api/runs/a1b2c3d4/pause
curl -X POST http://127.0.0.1:8765/api/runs/a1b2c3d4/resume
curl -X POST http://127.0.0.1:8765/api/runs/a1b2c3d4/stop
```

All three return the updated run status.

#### Update settings mid-run

Change runtime settings without restarting:

```bash
curl -X PATCH http://127.0.0.1:8765/api/runs/a1b2c3d4/settings \
  -H "Content-Type: application/json" \
  -d '{"max_iterations": 10, "delay": 5}'
```

All fields are optional — only the ones you include are updated:

| Field            | Type         | Description                           |
|------------------|--------------|---------------------------------------|
| `max_iterations` | int\|null    | New iteration limit                   |
| `delay`          | float\|null  | New delay between iterations          |
| `timeout`        | float\|null  | New timeout per iteration             |
| `stop_on_error`  | bool\|null   | Whether to stop on agent errors       |

#### Get iterations for a run

Retrieve persisted iteration data with per-check results — useful for reviewing
past runs or building custom reports.

```bash
curl http://127.0.0.1:8765/api/runs/a1b2c3d4/iterations
```

```json
[
  {
    "iteration": 1,
    "status": "success",
    "returncode": 0,
    "duration": "52.3s",
    "checks": [
      {"name": "tests", "passed": true, "exit_code": 0, "timed_out": false},
      {"name": "lint", "passed": true, "exit_code": 0, "timed_out": false}
    ]
  },
  {
    "iteration": 2,
    "status": "failure",
    "returncode": 1,
    "duration": "23.1s",
    "checks": [
      {"name": "tests", "passed": false, "exit_code": 1, "timed_out": false},
      {"name": "lint", "passed": true, "exit_code": 0, "timed_out": false}
    ]
  }
]
```

Each iteration includes:

| Field        | Type              | Description                                              |
|--------------|-------------------|----------------------------------------------------------|
| `iteration`  | int               | Iteration number (1-indexed)                             |
| `status`     | string            | `"success"`, `"failure"`, `"timeout"`, or `"running"`    |
| `returncode` | int\|null         | Agent exit code (`null` if timed out or still running)   |
| `duration`   | string\|null      | Formatted duration (e.g. `"52.3s"`)                      |
| `checks`     | array\|null       | Per-check results, or `null` if no checks ran            |

#### Get agent activity for an iteration

Retrieve the raw agent activity stream for a specific iteration — useful for
replaying what the agent did step-by-step or building custom activity UIs.
Only returns data when the agent is Claude Code (which uses streamed JSON
output).

```bash
curl http://127.0.0.1:8765/api/runs/a1b2c3d4/iterations/1/activity
```

```json
[
  {
    "type": "stream_event",
    "subtype": "content_block_start",
    "content_block": {"type": "tool_use", "name": "Read", "id": "toolu_01..."}
  },
  {
    "type": "stream_event",
    "subtype": "content_block_delta",
    "delta": {"type": "input_json_delta", "partial_json": "{\"file_path\":..."}
  },
  {
    "type": "result",
    "cost_usd": 0.042,
    "input_tokens": 12345,
    "output_tokens": 678
  }
]
```

Each item is a raw Claude Code stream-json object — the same format used by the
live [agent activity stream](#live-agent-activity-stream). The endpoint
correlates events to the iteration using timestamp ranges, so it works for both
completed and in-progress iterations.

Returns an empty array if the iteration doesn't exist or if no activity events
were recorded (e.g. when using a non-Claude-Code agent).

#### List past runs (history)

Retrieve all persisted runs from the SQLite store — these survive dashboard
restarts. This is what powers the History tab.

```bash
curl http://127.0.0.1:8765/api/history/runs
```

```json
[
  {
    "run_id": "a1b2c3d4",
    "status": "completed",
    "command": "claude",
    "prompt_file": "RALPH.md",
    "started_at": "2026-03-11T14:23:01",
    "stopped_at": "2026-03-11T14:35:12",
    "iterations": 5,
    "completed": 4,
    "failed": 1,
    "timed_out": 0
  }
]
```

Each run includes:

| Field        | Type         | Description                                    |
|--------------|--------------|------------------------------------------------|
| `run_id`     | string       | Unique run identifier                          |
| `status`     | string       | `"running"`, `"completed"`, `"stopped"`, etc.  |
| `command`    | string       | Agent command used                             |
| `prompt_file`| string       | Path to the ralph file                         |
| `started_at` | string\|null | ISO 8601 start timestamp                       |
| `stopped_at` | string\|null | ISO 8601 stop timestamp                        |
| `iterations` | int          | Total iterations executed                      |
| `completed`  | int          | Iterations that succeeded                      |
| `failed`     | int          | Iterations that failed                         |
| `timed_out`  | int          | Iterations that timed out                      |

Runs are returned newest-first. Combine with the [iterations endpoint](#get-iterations-for-a-run) to drill into a specific run's details.

### Primitives

Primitive endpoints use a base64-encoded `project_dir` in the URL path. Encode
it with:

```bash
PROJECT=$(echo -n "/path/to/project" | base64)
```

#### List all primitives

```bash
curl http://127.0.0.1:8765/api/projects/$PROJECT/primitives
```

```json
[
  {
    "kind": "checks",
    "name": "tests",
    "enabled": true,
    "content": "Fix all failing tests.",
    "frontmatter": {"command": "uv run pytest -x", "timeout": 120, "enabled": true}
  },
  {
    "kind": "contexts",
    "name": "git-log",
    "enabled": true,
    "content": "## Recent commits",
    "frontmatter": {"command": "git log --oneline -10", "timeout": 10, "enabled": true}
  }
]
```

#### Get a specific primitive

```bash
curl http://127.0.0.1:8765/api/projects/$PROJECT/primitives/checks/tests
```

#### Create a new primitive

```bash
curl -X POST http://127.0.0.1:8765/api/projects/$PROJECT/primitives/checks \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Fix all type errors.",
    "frontmatter": {
      "name": "typecheck",
      "command": "uv run mypy src/",
      "timeout": 60,
      "enabled": true
    }
  }'
```

The `name` field in `frontmatter` is required — it determines the directory name
under `.ralphify/checks/typecheck/CHECK.md`.

#### Update a primitive

```bash
curl -X PUT http://127.0.0.1:8765/api/projects/$PROJECT/primitives/checks/tests \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Fix all failing tests. Do not skip or delete tests.",
    "frontmatter": {"command": "uv run pytest -x", "timeout": 180, "enabled": true}
  }'
```

#### Delete a primitive

```bash
curl -X DELETE http://127.0.0.1:8765/api/projects/$PROJECT/primitives/checks/typecheck
```

Returns `204 No Content` on success.

#### Test a check

Run a single check immediately and get the result — useful for validating a
check command before starting a full run.

```bash
curl -X POST http://127.0.0.1:8765/api/projects/$PROJECT/primitives/checks/tests/test
```

```json
{
  "passed": true,
  "exit_code": 0,
  "output": "4 passed in 1.23s\n",
  "timed_out": false,
  "duration": 1.45
}
```

Returns `404` if the check does not exist.

### WebSocket

Connect to `/api/ws` for live event streaming:

```javascript
const ws = new WebSocket("ws://127.0.0.1:8765/api/ws");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.type, data.run_id, data.data);
};
```

Events are JSON objects with this shape:

```json
{
  "type": "iteration_started",
  "run_id": "a1b2c3d4",
  "timestamp": "2026-03-11T14:23:01.123456",
  "data": { "iteration": 1 }
}
```

You can filter events by run ID:

```javascript
ws.send(JSON.stringify({ "action": "subscribe", "run_id": "a1b2c3d4" }));
```

Send `{"action": "subscribe", "run_id": "*"}` to receive events from all runs
(this is the default on connect).

To unsubscribe from a specific run:

```javascript
ws.send(JSON.stringify({ "action": "unsubscribe", "run_id": "a1b2c3d4" }));
```

#### Event types

Every event has `type`, `run_id`, `timestamp`, and `data`. The table below lists all event types and their `data` fields.

**Run lifecycle**

| Event type | When | Data fields |
|---|---|---|
| `run_started` | Run begins | `checks`, `contexts`, `instructions` (int counts), `max_iterations`, `timeout`, `delay`, `prompt_name` |
| `run_stopped` | Run ends for any reason | `reason` (`"completed"`, `"user_requested"`, `"error"`), `total`, `completed`, `failed`, `timed_out` |
| `run_paused` | Run is paused | — |
| `run_resumed` | Run is resumed | — |

**Iteration lifecycle**

| Event type | When | Data fields |
|---|---|---|
| `iteration_started` | Iteration begins | `iteration` |
| `iteration_completed` | Agent exits with code 0 | `iteration`, `returncode`, `duration` (seconds), `duration_formatted`, `detail`, `log_file` |
| `iteration_failed` | Agent exits non-zero | `iteration`, `returncode`, `duration`, `duration_formatted`, `detail`, `log_file` |
| `iteration_timed_out` | Agent exceeds timeout | `iteration`, `returncode` (null), `duration`, `duration_formatted`, `detail`, `log_file` |

**Checks**

| Event type | When | Data fields |
|---|---|---|
| `checks_started` | Check phase begins | `iteration`, `count` |
| `check_passed` | A single check passes | `iteration`, `name`, `passed`, `exit_code`, `timed_out` |
| `check_failed` | A single check fails | `iteration`, `name`, `passed`, `exit_code`, `timed_out` |
| `checks_completed` | All checks finish | `iteration`, `passed`, `failed`, `results` (array of `{name, passed, exit_code, timed_out}`) |

**Prompt assembly**

| Event type | When | Data fields |
|---|---|---|
| `contexts_resolved` | Contexts injected into prompt | `iteration`, `count` |
| `prompt_assembled` | Full prompt built | `iteration`, `prompt_length` |

**Agent activity**

| Event type | When | Data fields |
|---|---|---|
| `agent_activity` | Each line of streamed agent output (Claude Code only) | `raw` (dict — one parsed JSON line from the agent's `stream-json` output), `iteration` (int — which iteration produced this event) |

The `raw` dict contains the original Claude Code stream event. Common shapes
include `stream_event` (with `content_block_start`, `content_block_delta`,
`content_block_stop` sub-events for tool calls and text), `user` (tool results),
and `result` (final cost/token summary). See the
[Claude Code streaming docs](https://docs.anthropic.com/en/docs/claude-code)
for the full schema.

**Other**

| Event type | When | Data fields |
|---|---|---|
| `primitives_reloaded` | Primitives re-discovered mid-run | `checks`, `contexts`, `instructions` (int counts) |
| `settings_changed` | Reserved for future use | — |
| `log_message` | General log from the engine | `message`, `level` (`"info"`, `"error"`), `traceback` (optional, present on crashes) |
