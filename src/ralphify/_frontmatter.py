"""Parse YAML frontmatter from primitive markdown files and discover primitives.

All three primitive types (checks, contexts, instructions) store their
configuration in markdown files with ``---``-delimited frontmatter.
This module provides the shared parsing and directory-scanning logic.

HTML comments in the body are stripped so users can leave notes that
don't leak into the assembled prompt.
"""

import re
from collections.abc import Iterator
from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a markdown file with optional YAML-like frontmatter.

    Frontmatter is delimited by ``---`` lines.  Only flat ``key: value``
    pairs are supported.  The ``timeout`` field is coerced to ``int``
    and ``enabled`` to ``bool``.  HTML comments are stripped from the
    body so they don't leak into the assembled prompt.

    Returns ``(frontmatter_dict, body_text)``.
    """
    frontmatter: dict = {}
    body = text

    stripped = text.strip()
    if stripped.startswith("---"):
        lines = text.split("\n")
        # Find the opening ---
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if start is None:
                    start = i
                else:
                    # Found closing ---
                    fm_lines = lines[start + 1 : i]
                    body = "\n".join(lines[i + 1 :]).strip()
                    for fm_line in fm_lines:
                        fm_line = fm_line.strip()
                        if not fm_line or fm_line.startswith("#"):
                            continue
                        if ":" not in fm_line:
                            continue
                        key, _, value = fm_line.partition(":")
                        key = key.strip()
                        value = value.strip()
                        # Type coercion
                        if key == "timeout":
                            frontmatter[key] = int(value)
                        elif key == "enabled":
                            frontmatter[key] = value.lower() in ("true", "yes", "1")
                        else:
                            frontmatter[key] = value
                    break

    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
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


def discover_primitives(
    root: Path, kind: str, marker: str
) -> Iterator[tuple[Path, dict, str]]:
    """Yield (directory, frontmatter, body) for each primitive found.

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
        yield entry, frontmatter, body
