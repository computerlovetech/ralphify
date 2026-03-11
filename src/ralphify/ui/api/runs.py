"""REST endpoints for run lifecycle management."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException  # ty: ignore[unresolved-import]

from ralphify.engine import RunConfig
from ralphify.manager import RunManager
from ralphify.prompts import resolve_prompt_name
from ralphify.ui.models import RunCreate, RunResponse, RunSettingsUpdate

router = APIRouter()

# Set at app startup by create_app()
_manager: RunManager | None = None


def _get_manager() -> RunManager:
    if _manager is None:
        raise RuntimeError("RunManager not initialised")
    return _manager


def _run_response(managed) -> RunResponse:
    return RunResponse(
        run_id=managed.state.run_id,
        status=managed.state.status.value,
        iteration=managed.state.iteration,
        completed=managed.state.completed,
        failed=managed.state.failed,
        timed_out=managed.state.timed_out,
    )


@router.post("/runs", response_model=RunResponse)
async def create_run(body: RunCreate) -> RunResponse:
    """Create and start a new run."""
    mgr = _get_manager()
    prompt_file = body.prompt_file
    resolved_name: str | None = None
    if body.prompt_name:
        root = Path(body.project_dir)
        try:
            found = resolve_prompt_name(body.prompt_name, root)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        prompt_file = str(found.path / "PROMPT.md")
        resolved_name = found.name
    config = RunConfig(
        command=body.command,
        args=body.args,
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
async def list_runs() -> list[RunResponse]:
    """List all runs."""
    mgr = _get_manager()
    return [_run_response(m) for m in mgr.list_runs()]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    """Get details for a single run."""
    mgr = _get_manager()
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_response(managed)


@router.post("/runs/{run_id}/pause", response_model=RunResponse)
async def pause_run(run_id: str) -> RunResponse:
    """Pause a running run."""
    mgr = _get_manager()
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")
    mgr.pause_run(run_id)
    return _run_response(managed)


@router.post("/runs/{run_id}/resume", response_model=RunResponse)
async def resume_run(run_id: str) -> RunResponse:
    """Resume a paused run."""
    mgr = _get_manager()
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")
    mgr.resume_run(run_id)
    return _run_response(managed)


@router.post("/runs/{run_id}/stop", response_model=RunResponse)
async def stop_run(run_id: str) -> RunResponse:
    """Stop a run."""
    mgr = _get_manager()
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")
    mgr.stop_run(run_id)
    return _run_response(managed)


@router.patch("/runs/{run_id}/settings", response_model=RunResponse)
async def update_settings(run_id: str, body: RunSettingsUpdate) -> RunResponse:
    """Update run configuration mid-run."""
    mgr = _get_manager()
    managed = mgr.get_run(run_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if body.max_iterations is not None:
        managed.config.max_iterations = body.max_iterations
    if body.delay is not None:
        managed.config.delay = body.delay
    if body.timeout is not None:
        managed.config.timeout = body.timeout
    if body.stop_on_error is not None:
        managed.config.stop_on_error = body.stop_on_error

    return _run_response(managed)
