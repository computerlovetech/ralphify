"""Discover and resolve named ralphs from ``.ralphify/ralphs/<name>/RALPH.md``.

Ralphs are reusable task-focused prompt files that users can switch between
(e.g. ``improve-docs``, ``refactor``, ``add-tests``).  They follow the same
``.ralphify/<kind>/<name>/MARKER.md`` convention as other primitives.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._discovery import discover_primitives
from ralphify._frontmatter import RALPH_MARKER


@dataclass
class Ralph:
    """A named ralph discovered from ``.ralphify/ralphs/<name>/RALPH.md``.

    Named ralphs let users keep multiple task-focused prompts (e.g.
    ``docs``, ``refactor``, ``add-tests``) and switch between them with
    ``ralph run <name>`` instead of editing the root ``RALPH.md``.

    The *content* is the body text below the YAML frontmatter — this is the
    full prompt that gets piped to the agent.  Context and instruction
    placeholders (``{{ contexts }}``, ``{{ instructions }}``) resolve the
    same way as in a root ``RALPH.md``.
    """

    name: str
    path: Path
    description: str = ""
    enabled: bool = True
    content: str = ""


def discover_ralphs(root: Path = Path(".")) -> list[Ralph]:
    """Scan ``.ralphify/ralphs/`` for subdirectories containing ``RALPH.md``.

    Returns all discovered ralphs (both enabled and disabled) sorted
    alphabetically by name.  Used by ``ralph ralphs list`` and the
    dashboard's Configure tab.
    """
    return [
        Ralph(
            name=prim.path.name,
            path=prim.path,
            description=prim.frontmatter.get("description", ""),
            enabled=prim.frontmatter.get("enabled", True),
            content=prim.body,
        )
        for prim in discover_primitives(root, "ralphs", RALPH_MARKER)
    ]


def resolve_ralph_name(name: str, root: Path = Path(".")) -> Ralph:
    """Look up a named ralph by its directory name and return the ``Ralph``.

    Called by the CLI when the user passes a positional ralph name
    (``ralph run docs``) or when ``ralph.toml``'s ``ralph`` field contains
    a name.  The match is exact — ``name`` must equal one of the directory
    names under ``.ralphify/ralphs/``.

    Raises ``ValueError`` with a message listing available ralphs if no
    match is found.  The CLI catches this and prints a user-friendly error.
    """
    ralphs = discover_ralphs(root)
    for r in ralphs:
        if r.name == name:
            return r
    available = [r.name for r in ralphs]
    msg = f"Ralph '{name}' not found."
    if available:
        msg += f" Available: {', '.join(available)}"
    raise ValueError(msg)


def is_ralph_name(value: str) -> bool:
    """Return ``True`` if *value* looks like a ralph name rather than a file path.

    A ralph name is a bare identifier (e.g. ``"docs"``) with no ``/`` path
    separators and no ``.`` file extension.  This heuristic lets
    ``ralph.toml``'s ``ralph`` field accept either a name (``"docs"``) or a
    file path (``"RALPH.md"``, ``"ralphs/custom.md"``) and route to the
    correct resolution logic in :func:`resolve_ralph_source`.
    """
    return "/" not in value and "." not in value


def resolve_ralph_source(
    *,
    prompt_name: str | None,
    prompt_file: str | None,
    toml_ralph: str,
) -> tuple[str, str | None]:
    """Resolve which prompt file to use, returning ``(file_path, ralph_name)``.

    Priority chain: positional name > --prompt-file > ralph.toml.
    The ``toml_ralph`` value from ``ralph.toml`` may be either a file path or
    a named ralph — names are tried first, falling back to a literal path.

    Only called when no inline ``-p/--prompt`` text was provided — inline
    text bypasses file resolution entirely (see :func:`~ralphify.cli.run`).

    Raises ``ValueError`` if a named ralph lookup fails.
    """
    if prompt_name:
        found = resolve_ralph_name(prompt_name)
        return str(found.path / RALPH_MARKER), found.name

    if prompt_file:
        return prompt_file, None

    # Fall back to ralph.toml agent.ralph — could be a name or a path
    if is_ralph_name(toml_ralph):
        try:
            found = resolve_ralph_name(toml_ralph)
            return str(found.path / RALPH_MARKER), found.name
        except ValueError:
            return toml_ralph, None

    return toml_ralph, None
