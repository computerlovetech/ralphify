"""Discover primitive directories under ``.ralphify/<kind>/``.

Scans the conventional directory structure for primitive marker files
(``CHECK.md``, ``CONTEXT.md``, etc.), parses their frontmatter, and
yields :class:`PrimitiveEntry` results.  Also locates ``run.*`` scripts
inside primitive directories.

Parsing of the marker files themselves is delegated to
:func:`~ralphify._frontmatter.parse_frontmatter`.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from ralphify._frontmatter import PRIMITIVES_DIR, parse_frontmatter


class PrimitiveEntry(NamedTuple):
    """A discovered primitive's directory, parsed frontmatter, and body text."""

    path: Path
    frontmatter: dict
    body: str


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
) -> Iterator[PrimitiveEntry]:
    """Yield a :class:`PrimitiveEntry` for each primitive found.

    Scans ``root/.ralphify/{kind}/`` for subdirectories containing a
    *marker* file (e.g. ``CHECK.md``), parses its frontmatter, and
    yields results in alphabetical order.
    """
    primitives_dir = root / PRIMITIVES_DIR / kind
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


def discover_local_primitives(
    base_dir: Path, kind: str, marker: str
) -> Iterator[PrimitiveEntry]:
    """Yield ralph-scoped primitives from ``base_dir/{kind}/``.

    Like :func:`discover_primitives` but scans a ralph directory
    directly (e.g. ``.ralphify/ralphs/ui/checks/``) instead of the
    global ``.ralphify/{kind}/`` path.  Results are in alphabetical order.
    """
    primitives_dir = base_dir / kind
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
