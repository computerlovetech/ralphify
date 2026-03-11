---
description: How to install, launch, and use the ralphify web dashboard to manage runs, browse prompts, edit primitives, and review history.
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

| Option    | Default       | Description              |
|-----------|---------------|--------------------------|
| `--port`  | `8765`        | Port to serve the UI on  |
| `--host`  | `127.0.0.1`   | Host to bind to          |

To expose the dashboard on your network:

```bash
ralph ui --host 0.0.0.0 --port 9000
```

## Dashboard tabs

The dashboard has four tabs. **Prompts** is the default landing page.

### Prompts

The Prompts tab shows every named prompt discovered in `.ralph/prompts/` as a
card grid. Each card displays:

- **Name** and **description** (from the prompt's frontmatter)
- A **content preview** of the prompt body
- An **Edit** button that opens an inline editor
- A **Run** button that opens the New Run modal with that prompt pre-selected

Use this tab to quickly browse your prompts, start a run from a specific one,
or create new prompts without leaving the browser.

### Timeline

Select a run in the sidebar to see its iterations as they complete:

- Pass/fail status with color-coded badges
- Agent output (truncated to 5,000 characters, same as the CLI)
- Check results with individual pass/fail/timeout indicators
- Duration and return codes

Each check gets a **sparkline bar** showing its pass/fail history across
iterations. Green means pass, red means fail, yellow means timeout — useful for
spotting flaky checks or regressions at a glance.

Events stream over WebSocket, so the page updates without refreshing.

### Configure

The Configure tab lists all checks, contexts, and instructions in your project.
You can:

- View the frontmatter and body of each primitive
- Toggle primitives on and off with enable/disable badges
- Create new primitives
- Edit existing ones
- Delete primitives you no longer need

Changes are written directly to the `.ralph/` directory on disk.

### History

Shows all past runs organized by status — completed, stopped, and failed. Each
run displays its pass rate and iteration count. Click any run to jump to the
Timeline view and see its full iteration details.

## Starting a run

Click **New Run** in the sidebar to open the run modal. It lets you:

- **Pick a named prompt** — cards show every prompt discovered in `.ralph/prompts/`
- **Enter an ad-hoc prompt** — toggle to ad-hoc mode and type a one-off task
- **Configure settings** — expand the settings panel to set max iterations, delay between iterations, timeout, and stop-on-error

Once a run starts, you can **pause**, **resume**, or **stop** it from the
sidebar or the controls bar above the Timeline.

## Editing while a run is active

The dashboard lets you edit primitives via the Configure tab while a run is in progress, but not all changes take effect immediately:

| What you change | When it takes effect |
|---|---|
| `PROMPT.md` content | Next iteration — the prompt is re-read from disk every iteration |
| Context command output | Next iteration — context commands re-run every iteration |
| Check/context/instruction config (frontmatter, body, enable/disable) | After restart — primitive configurations are loaded once when a run starts |
| New or deleted primitives | After restart — primitive discovery happens once at run start |

To apply primitive configuration changes to a running run, **stop** the run and **start a new one**. The new run will discover the updated primitives from disk.

!!! tip "Prompt edits are always live"
    The most common adjustment — adding a constraint or changing the task in your prompt — takes effect on the very next iteration without restarting. This is the primary way to steer the agent in real time.

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

## REST API

The dashboard exposes a REST API you can use directly:

| Method | Endpoint                                              | Description                    |
|--------|-------------------------------------------------------|--------------------------------|
| POST   | `/api/runs`                                           | Create and start a new run     |
| GET    | `/api/runs`                                           | List all runs                  |
| GET    | `/api/runs/{run_id}`                                  | Get run details and iterations |
| POST   | `/api/runs/{run_id}/pause`                            | Pause a running run            |
| POST   | `/api/runs/{run_id}/resume`                           | Resume a paused run            |
| POST   | `/api/runs/{run_id}/stop`                             | Stop a run                     |
| PATCH  | `/api/runs/{run_id}/settings`                         | Update runtime settings        |
| GET    | `/api/projects/{project_dir}/primitives`              | List all primitives            |
| GET    | `/api/projects/{project_dir}/primitives/{kind}/{name}`| Get a specific primitive       |
| PUT    | `/api/projects/{project_dir}/primitives/{kind}/{name}`| Update a primitive             |
| POST   | `/api/projects/{project_dir}/primitives/{kind}`       | Create a new primitive         |
| DELETE | `/api/projects/{project_dir}/primitives/{kind}/{name}`| Delete a primitive             |

Connect to `/ws` for live event streaming via WebSocket.
