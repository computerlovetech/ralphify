"""REST endpoints for run lifecycle management."""
from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ralphify._frontmatter import CONFIG_FILENAME, PROMPT_MARKER
from ralphify._run_types import RunConfig
from ralphify.manager import ManagedRun, RunManager
from ralphify.prompts import resolve_prompt_name
from ralphify.ui.models import RunCreate, RunResponse, RunSettingsUpdate

def _load_agent_config(project_dir: str) -> dict:
    """Read ``[agent]`` from ralph.toml so the UI never hard-codes command/args."""
    config_path = Path(project_dir) / CONFIG_FILENAME
    if not config_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"{CONFIG_FILENAME} not found in project directory.",
        )
    with open(config_path, "rb") as f:
        toml_cfg = tomllib.load(f)
    agent = toml_cfg.get("agent", {})
    return {"command": agent.get("command", "claude"), "args": agent.get("args", [])}


router = APIRouter()


def _get_manager(request: Request) -> RunManager:
    """Extract the RunManager from app state (set during lifespan startup)."""
    mgr: RunManager | None = getattr(request.app.state, "manager", None)
    if mgr is None:
        raise RuntimeError("RunManager not initialised")
    return mgr


def _get_run_or_404(mgr: RunManager, run_id: str) -> ManagedRun:
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return managed


def _run_response(managed: ManagedRun) -> RunResponse:
    started_at = None
    if managed.state.started_at is not None:
        started_at = managed.state.started_at.isoformat()
    return RunResponse(
        run_id=managed.state.run_id,
        status=managed.state.status.value,
        iteration=managed.state.iteration,
        completed=managed.state.completed,
        failed=managed.state.failed,
        timed_out=managed.state.timed_out,
        prompt_name=managed.config.prompt_name,
        started_at=started_at,
        max_iterations=managed.config.max_iterations,
        delay=managed.config.delay,
        timeout=managed.config.timeout,
        stop_on_error=managed.config.stop_on_error,
    )


@router.post("/runs", response_model=RunResponse)
async def create_run(body: RunCreate, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Create and start a new run."""

    # Default command/args from ralph.toml when not provided by the client.
    command = body.command
    args = body.args if body.args is not None else []
    if command is None:
        agent_cfg = _load_agent_config(body.project_dir)
        command = agent_cfg["command"]
        if body.args is None:
            args = agent_cfg["args"]

    prompt_file = body.prompt_file
    resolved_name: str | None = None
    if body.prompt_name:
        root = Path(body.project_dir)
        try:
            found = resolve_prompt_name(body.prompt_name, root)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        prompt_file = str(found.path / PROMPT_MARKER)
        resolved_name = found.name
    config = RunConfig(
        command=command,
        args=args,
        prompt_file=prompt_file,
        prompt_text=body.prompt_text,
        prompt_name=resolved_name,
        max_iterations=body.max_iterations,
        delay=body.delay,
        timeout=body.timeout,
        stop_on_error=body.stop_on_error,
        log_dir=body.log_dir,
        project_root=Path(body.project_dir),
    )
    managed = mgr.create_run(config)
    mgr.start_run(managed.state.run_id)
    return _run_response(managed)


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(mgr: RunManager = Depends(_get_manager)) -> list[RunResponse]:
    """List all runs."""
    return [_run_response(m) for m in mgr.list_runs()]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Get details for a single run."""
    return _run_response(_get_run_or_404(mgr, run_id))


@router.post("/runs/{run_id}/pause", response_model=RunResponse)
async def pause_run(run_id: str, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Pause a running run."""
    managed = _get_run_or_404(mgr, run_id)
    mgr.pause_run(run_id)
    return _run_response(managed)


@router.post("/runs/{run_id}/resume", response_model=RunResponse)
async def resume_run(run_id: str, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Resume a paused run."""
    managed = _get_run_or_404(mgr, run_id)
    mgr.resume_run(run_id)
    return _run_response(managed)


@router.post("/runs/{run_id}/stop", response_model=RunResponse)
async def stop_run(run_id: str, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Stop a run."""
    managed = _get_run_or_404(mgr, run_id)
    mgr.stop_run(run_id)
    return _run_response(managed)


@router.patch("/runs/{run_id}/settings", response_model=RunResponse)
async def update_settings(run_id: str, body: RunSettingsUpdate, mgr: RunManager = Depends(_get_manager)) -> RunResponse:
    """Update run configuration mid-run."""
    managed = _get_run_or_404(mgr, run_id)

    if body.max_iterations is not None:
        managed.config.max_iterations = body.max_iterations
    if body.delay is not None:
        managed.config.delay = body.delay
    if body.timeout is not None:
        managed.config.timeout = body.timeout
    if body.stop_on_error is not None:
        managed.config.stop_on_error = body.stop_on_error

    return _run_response(managed)
