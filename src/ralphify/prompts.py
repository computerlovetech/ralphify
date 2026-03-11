"""Discover and resolve named prompts from ``.ralph/prompts/<name>/PROMPT.md``.

Prompts are reusable task-focused prompt files that users can switch between
(e.g. ``improve-docs``, ``refactor``, ``add-tests``).  They follow the same
``.ralph/<kind>/<name>/MARKER.md`` convention as other primitives.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._frontmatter import PROMPT_MARKER, discover_primitives


@dataclass
class Prompt:
    """A named prompt discovered from ``.ralph/prompts/<name>/PROMPT.md``.

    The *content* is the body text below the frontmatter.
    """

    name: str
    path: Path
    description: str = ""
    enabled: bool = True
    content: str = ""


def discover_prompts(root: Path = Path(".")) -> list[Prompt]:
    """Scan ``.ralph/prompts/`` for subdirectories containing ``PROMPT.md``.

    Returns all discovered prompts (both enabled and disabled) sorted
    alphabetically by name.  Used by ``ralph prompts list`` and the
    dashboard's Configure tab.
    """
    return [
        Prompt(
            name=prim.path.name,
            path=prim.path,
            description=prim.frontmatter.get("description", ""),
            enabled=prim.frontmatter.get("enabled", True),
            content=prim.body,
        )
        for prim in discover_primitives(root, "prompts", PROMPT_MARKER)
    ]


def resolve_prompt_name(name: str, root: Path = Path(".")) -> Prompt:
    """Look up a prompt by name.  Raises ``ValueError`` if not found."""
    prompts = discover_prompts(root)
    for prompt in prompts:
        if prompt.name == name:
            return prompt
    available = [p.name for p in prompts]
    msg = f"Prompt '{name}' not found."
    if available:
        msg += f" Available: {', '.join(available)}"
    raise ValueError(msg)


def is_prompt_name(value: str) -> bool:
    """Return True if *value* looks like a prompt name (no ``/`` or file extension)."""
    return "/" not in value and "." not in value
