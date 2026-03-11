"""Discover and resolve named prompts from ``.ralph/prompts/<name>/PROMPT.md``.

Prompts are reusable task-focused prompt files that users can switch between
(e.g. ``improve-docs``, ``refactor``, ``add-tests``).  They follow the same
``.ralph/<kind>/<name>/MARKER.md`` convention as other primitives.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._discovery import discover_primitives
from ralphify._frontmatter import PROMPT_MARKER


@dataclass
class Prompt:
    """A named prompt discovered from ``.ralph/prompts/<name>/PROMPT.md``.

    Named prompts let users keep multiple task-focused prompts (e.g.
    ``docs``, ``refactor``, ``add-tests``) and switch between them with
    ``ralph run <name>`` instead of editing the root ``PROMPT.md``.

    The *content* is the body text below the YAML frontmatter — this is the
    full prompt that gets piped to the agent.  Context and instruction
    placeholders (``{{ contexts }}``, ``{{ instructions }}``) resolve the
    same way as in a root ``PROMPT.md``.
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
    """Look up a named prompt by its directory name and return the ``Prompt``.

    Called by the CLI when the user passes a positional prompt name
    (``ralph run docs``) or when ``ralph.toml``'s ``prompt`` field contains
    a name.  The match is exact — ``name`` must equal one of the directory
    names under ``.ralph/prompts/``.

    Raises ``ValueError`` with a message listing available prompts if no
    match is found.  The CLI catches this and prints a user-friendly error.
    """
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
    """Return ``True`` if *value* looks like a prompt name rather than a file path.

    A prompt name is a bare identifier (e.g. ``"docs"``) with no ``/`` path
    separators and no ``.`` file extension.  This heuristic lets
    ``ralph.toml``'s ``prompt`` field accept either a name (``"docs"``) or a
    file path (``"PROMPT.md"``, ``"prompts/custom.md"``) and route to the
    correct resolution logic in :func:`resolve_prompt_source`.
    """
    return "/" not in value and "." not in value


def resolve_prompt_source(
    *,
    prompt_name: str | None,
    prompt_file: str | None,
    toml_prompt: str,
) -> tuple[str, str | None]:
    """Resolve which prompt file to use, returning ``(file_path, prompt_name)``.

    Priority chain: positional name > --prompt-file > ralph.toml.
    The ``toml_prompt`` value from ``ralph.toml`` may be either a file path or
    a named prompt — names are tried first, falling back to a literal path.

    Only called when no inline ``-p/--prompt`` text was provided — inline
    text bypasses file resolution entirely (see :func:`~ralphify.cli.run`).

    Raises ``ValueError`` if a named prompt lookup fails.
    """
    if prompt_name:
        found = resolve_prompt_name(prompt_name)
        return str(found.path / PROMPT_MARKER), found.name

    if prompt_file:
        return prompt_file, None

    # Fall back to ralph.toml agent.prompt — could be a name or a path
    if is_prompt_name(toml_prompt):
        try:
            found = resolve_prompt_name(toml_prompt)
            return str(found.path / PROMPT_MARKER), found.name
        except ValueError:
            return toml_prompt, None

    return toml_prompt, None
