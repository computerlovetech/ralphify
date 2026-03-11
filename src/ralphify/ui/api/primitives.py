"""REST endpoints for browsing and editing primitives."""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ralphify._frontmatter import (
    CHECK_MARKER,
    CONTEXT_MARKER,
    INSTRUCTION_MARKER,
    PROMPT_MARKER,
    parse_frontmatter,
    serialize_frontmatter,
)
from ralphify.checks import discover_checks
from ralphify.contexts import discover_contexts
from ralphify.instructions import discover_instructions
from ralphify.prompts import discover_prompts
from ralphify.ui.models import PrimitiveResponse, PrimitiveUpdate

router = APIRouter()

# Mapping from kind to (discover function, marker filename)
_KIND_MAP = {
    "checks": (discover_checks, CHECK_MARKER),
    "contexts": (discover_contexts, CONTEXT_MARKER),
    "instructions": (discover_instructions, INSTRUCTION_MARKER),
    "prompts": (discover_prompts, PROMPT_MARKER),
}


def _decode_project_dir(encoded: str) -> Path:
    """Decode a base64-encoded project directory path."""
    try:
        return Path(base64.urlsafe_b64decode(encoded).decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 project_dir")


def _primitive_to_response(prim, kind: str) -> PrimitiveResponse:
    """Convert a discovered primitive to a response model."""
    marker = _KIND_MAP[kind][1]
    marker_file = prim.path / marker
    if marker_file.exists():
        text = marker_file.read_text()
        fm, body = parse_frontmatter(text)
    else:
        fm, body = {}, ""
    return PrimitiveResponse(
        kind=kind,
        name=prim.name,
        enabled=prim.enabled,
        content=body,
        frontmatter=fm,
    )


@router.get(
    "/projects/{project_dir}/primitives",
    response_model=list[PrimitiveResponse],
)
async def list_primitives(project_dir: str) -> list[PrimitiveResponse]:
    """List all primitives for a project."""
    root = _decode_project_dir(project_dir)
    results: list[PrimitiveResponse] = []
    for kind, (discover_fn, _marker) in _KIND_MAP.items():
        for prim in discover_fn(root):
            results.append(_primitive_to_response(prim, kind))
    return results


@router.get(
    "/projects/{project_dir}/primitives/{kind}/{name}",
    response_model=PrimitiveResponse,
)
async def get_primitive(project_dir: str, kind: str, name: str) -> PrimitiveResponse:
    """Read a specific primitive."""
    if kind not in _KIND_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    root = _decode_project_dir(project_dir)
    discover_fn, _marker = _KIND_MAP[kind]
    for prim in discover_fn(root):
        if prim.name == name:
            return _primitive_to_response(prim, kind)
    raise HTTPException(status_code=404, detail="Primitive not found")


@router.put(
    "/projects/{project_dir}/primitives/{kind}/{name}",
    response_model=PrimitiveResponse,
)
async def update_primitive(
    project_dir: str, kind: str, name: str, body: PrimitiveUpdate
) -> PrimitiveResponse:
    """Update a primitive's content and/or frontmatter."""
    if kind not in _KIND_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    root = _decode_project_dir(project_dir)
    _discover_fn, marker = _KIND_MAP[kind]
    marker_file = root / ".ralph" / kind / name / marker
    if not marker_file.exists():
        raise HTTPException(status_code=404, detail="Primitive not found")

    marker_file.write_text(serialize_frontmatter(body.frontmatter or {}, body.content))

    # Re-read to return updated state
    text = marker_file.read_text()
    fm, content = parse_frontmatter(text)
    return PrimitiveResponse(
        kind=kind,
        name=name,
        enabled=fm.get("enabled", True),
        content=content,
        frontmatter=fm,
    )


@router.post(
    "/projects/{project_dir}/primitives/{kind}",
    response_model=PrimitiveResponse,
    status_code=201,
)
async def create_primitive(
    project_dir: str, kind: str, body: PrimitiveUpdate
) -> PrimitiveResponse:
    """Scaffold a new primitive.

    The primitive name is derived from the frontmatter 'name' field,
    which must be present.
    """
    if kind not in _KIND_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    if not body.frontmatter or "name" not in body.frontmatter:
        raise HTTPException(
            status_code=400,
            detail="frontmatter must include a 'name' field",
        )
    root = _decode_project_dir(project_dir)
    _discover_fn, marker = _KIND_MAP[kind]
    name = body.frontmatter["name"]
    prim_dir = root / ".ralph" / kind / name
    if prim_dir.exists():
        raise HTTPException(status_code=409, detail="Primitive already exists")

    prim_dir.mkdir(parents=True)
    marker_file = prim_dir / marker

    marker_file.write_text(serialize_frontmatter(body.frontmatter or {}, body.content))

    fm, content = parse_frontmatter(marker_file.read_text())
    return PrimitiveResponse(
        kind=kind,
        name=name,
        enabled=fm.get("enabled", True),
        content=content,
        frontmatter=fm,
    )


@router.delete("/projects/{project_dir}/primitives/{kind}/{name}", status_code=204)
async def delete_primitive(project_dir: str, kind: str, name: str) -> None:
    """Delete a primitive directory."""
    if kind not in _KIND_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    root = _decode_project_dir(project_dir)
    prim_dir = root / ".ralph" / kind / name
    if not prim_dir.exists():
        raise HTTPException(status_code=404, detail="Primitive not found")
    shutil.rmtree(prim_dir)
