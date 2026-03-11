"""Pydantic models for the REST API."""
from __future__ import annotations
from pydantic import BaseModel


class RunCreate(BaseModel):
    command: str | None = None
    args: list[str] | None = None
    prompt_file: str = "PROMPT.md"
    prompt_text: str | None = None
    prompt_name: str | None = None
    max_iterations: int | None = None
    delay: float = 0
    timeout: float | None = None
    stop_on_error: bool = False
    log_dir: str | None = None
    project_dir: str = "."


class RunSettingsUpdate(BaseModel):
    max_iterations: int | None = None
    delay: float | None = None
    timeout: float | None = None
    stop_on_error: bool | None = None


class RunResponse(BaseModel):
    run_id: str
    status: str
    iteration: int
    completed: int
    failed: int
    timed_out: int
    prompt_name: str | None = None


class IterationResponse(BaseModel):
    iteration: int
    returncode: int | None = None
    duration: float | None = None
    detail: str | None = None


class CheckResultResponse(BaseModel):
    name: str
    passed: bool
    exit_code: int
    timed_out: bool = False


class PrimitiveResponse(BaseModel):
    kind: str
    name: str
    enabled: bool
    content: str
    frontmatter: dict


class PrimitiveUpdate(BaseModel):
    content: str
    frontmatter: dict | None = None
