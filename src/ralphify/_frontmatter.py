"""Parse YAML frontmatter from primitive markdown files and discover primitives.

All three primitive types (checks, contexts, instructions) store their
configuration in markdown files with ``---``-delimited frontmatter.
This module provides the shared parsing and directory-scanning logic.

HTML comments in the body are stripped so users can leave notes that
don't leak into the assembled prompt.
"""

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple


# Single source of truth for well-known filenames.
# Every module that needs a marker or config name should import from here.
CHECK_MARKER = "CHECK.md"
CONTEXT_MARKER = "CONTEXT.md"
INSTRUCTION_MARKER = "INSTRUCTION.md"
PROMPT_MARKER = "PROMPT.md"
CONFIG_FILENAME = "ralph.toml"

# Pre-compiled pattern to strip HTML comments from body text.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Type coercion for known frontmatter fields.
# To add a new typed field, add an entry here — no other changes needed.
_FIELD_COERCIONS: dict[str, Callable[[str], object]] = {
    "timeout": int,
    "enabled": lambda v: v.lower() in ("true", "yes", "1"),
}


def _parse_kv_lines(lines: list[str]) -> dict:
    """Parse flat ``key: value`` lines with type coercion for known fields."""
    result: dict = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        coerce = _FIELD_COERCIONS.get(key)
        result[key] = coerce(value) if coerce else value
    return result


def _extract_frontmatter_block(text: str) -> tuple[list[str], str]:
    """Split text into frontmatter lines and body at ``---`` delimiters.

    Returns ``([], text)`` when no valid frontmatter block is found.
    """
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if start is None:
                start = i
            else:
                fm_lines = lines[start + 1 : i]
                body = "\n".join(lines[i + 1 :]).strip()
                return fm_lines, body
    return [], text


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a markdown file with optional YAML-like frontmatter.

    Frontmatter is delimited by ``---`` lines.  Only flat ``key: value``
    pairs are supported.  The ``timeout`` field is coerced to ``int``
    and ``enabled`` to ``bool``.  HTML comments are stripped from the
    body so they don't leak into the assembled prompt.

    Returns ``(frontmatter_dict, body_text)``.
    """
    if text.strip().startswith("---"):
        fm_lines, body = _extract_frontmatter_block(text)
        frontmatter = _parse_kv_lines(fm_lines)
    else:
        frontmatter, body = {}, text

    body = _HTML_COMMENT_RE.sub("", body).strip()
    return frontmatter, body


def serialize_frontmatter(frontmatter: dict, body: str) -> str:
    """Serialize frontmatter and body back to a markdown string.

    This is the inverse of :func:`parse_frontmatter`.  If *frontmatter*
    is empty the body is returned as-is (no ``---`` delimiters).
    """
    parts: list[str] = []
    if frontmatter:
        parts.append("---")
        for key, value in frontmatter.items():
            parts.append(f"{key}: {value}")
        parts.append("---")
        parts.append("")
    parts.append(body)
    return "\n".join(parts)


def find_run_script(directory: Path) -> Path | None:
    """Find the first ``run.*`` script in a primitive directory.

    Returns the first match in sorted order (e.g. ``run.py`` before
    ``run.sh``), or ``None`` if no ``run.*`` file exists.
    """
    for f in sorted(directory.iterdir()):
        if f.name.startswith("run.") and f.is_file():
            return f
    return None


class PrimitiveEntry(NamedTuple):
    """A discovered primitive's directory, parsed frontmatter, and body text."""

    path: Path
    frontmatter: dict
    body: str


def discover_primitives(
    root: Path, kind: str, marker: str
) -> Iterator[PrimitiveEntry]:
    """Yield a :class:`PrimitiveEntry` for each primitive found.

    Scans ``root/.ralph/{kind}/`` for subdirectories containing a
    *marker* file (e.g. ``CHECK.md``), parses its frontmatter, and
    yields results in alphabetical order.
    """
    primitives_dir = root / ".ralph" / kind
    if not primitives_dir.is_dir():
        return

    for entry in sorted(primitives_dir.iterdir()):
        if not entry.is_dir():
            continue

        marker_file = entry / marker
        if not marker_file.exists():
            continue

        text = marker_file.read_text()
        frontmatter, body = parse_frontmatter(text)
        yield PrimitiveEntry(entry, frontmatter, body)
