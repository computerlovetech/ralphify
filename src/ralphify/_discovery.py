"""Discover primitive directories under ``.ralphify/<kind>/``.

Scans the conventional directory structure for primitive marker files
(``CHECK.md``, ``CONTEXT.md``, etc.), parses their frontmatter, and
yields :class:`PrimitiveEntry` results.  Also locates ``run.*`` scripts
inside primitive directories.

Parsing of the marker files themselves is delegated to
:func:`~ralphify._frontmatter.parse_frontmatter`.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple, Protocol, TypeVar

from ralphify._frontmatter import PRIMITIVES_DIR, parse_frontmatter


class Primitive(Protocol):
    """Protocol for the shared interface of all primitive types.

    All primitive dataclasses (:class:`~ralphify.checks.Check`,
    :class:`~ralphify.contexts.Context`, :class:`~ralphify.instructions.Instruction`,
    :class:`~ralphify.ralphs.Ralph`) satisfy this protocol, enabling type-safe
    discovery, filtering, merging, and display.
    """

    @property
    def name(self) -> str: ...

    @property
    def enabled(self) -> bool: ...


_P = TypeVar("_P", bound=Primitive)


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


def _scan_dir(
    primitives_dir: Path, marker: str
) -> Iterator[PrimitiveEntry]:
    """Yield entries from *primitives_dir* that contain *marker*.

    Shared implementation for :func:`discover_primitives` and
    :func:`discover_local_primitives`.  Results are in alphabetical order.
    """
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


def discover_primitives(
    root: Path, kind: str, marker: str
) -> Iterator[PrimitiveEntry]:
    """Yield a :class:`PrimitiveEntry` for each primitive found.

    Scans ``root/.ralphify/{kind}/`` for subdirectories containing a
    *marker* file (e.g. ``CHECK.md``), parses its frontmatter, and
    yields results in alphabetical order.
    """
    return _scan_dir(root / PRIMITIVES_DIR / kind, marker)


def discover_local_primitives(
    base_dir: Path, kind: str, marker: str
) -> Iterator[PrimitiveEntry]:
    """Yield ralph-scoped primitives from ``base_dir/{kind}/``.

    Like :func:`discover_primitives` but scans a ralph directory
    directly (e.g. ``.ralphify/ralphs/ui/checks/``) instead of the
    global ``.ralphify/{kind}/`` path.  Results are in alphabetical order.
    """
    return _scan_dir(base_dir / kind, marker)


def merge_by_name(global_list: list[_P], local_list: list[_P]) -> list[_P]:
    """Merge global and prompt-local primitives; local wins on name conflict.

    Used by the engine to overlay prompt-scoped primitives on top of
    global ones.  Both lists must contain objects satisfying the
    :class:`Primitive` protocol.  Results are sorted alphabetically by name.
    """
    by_name = {p.name: p for p in global_list}
    for p in local_list:
        by_name[p.name] = p  # local wins
    return sorted(by_name.values(), key=lambda p: p.name)


def discover_enabled(
    root: Path,
    ralph_dir: Path | None,
    discover: Callable[[Path], list[_P]],
    discover_local: Callable[[Path], list[_P]],
) -> list[_P]:
    """Discover primitives, merge local overrides (if any), and return only enabled ones.

    Encapsulates the three-step pattern shared by all primitive types:
    discover globals → merge with ralph-scoped locals → filter to enabled.

    Used by the engine's ``_discover_enabled_primitives`` to build the
    full set of primitives for a run.
    """
    items = discover(root)
    if ralph_dir is not None:
        items = merge_by_name(items, discover_local(ralph_dir))
    return [item for item in items if item.enabled]
