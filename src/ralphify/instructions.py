"""Discover and resolve static instruction text injected into each prompt.

Instructions are reusable rules in ``.ralph/instructions/<name>/`` that get
injected into the prompt every iteration — for example coding standards or
git conventions.  Unlike contexts, they have no command; their content is
the body text of the INSTRUCTION.md file.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._frontmatter import discover_primitives
from ralphify.resolver import resolve_placeholders


@dataclass
class Instruction:
    """A static instruction discovered from ``.ralph/instructions/<name>/INSTRUCTION.md``.

    The *content* is the body text below the frontmatter.  Instructions with
    empty content are silently excluded from prompt injection even if enabled.
    """

    name: str
    path: Path
    enabled: bool = True
    content: str = ""


def discover_instructions(root: Path = Path(".")) -> list[Instruction]:
    """Scan ``.ralph/instructions/`` for subdirectories containing ``INSTRUCTION.md``.

    Unlike checks and contexts, instructions have no command or script —
    just static content.  Default: ``enabled=True``.
    """
    return [
        Instruction(
            name=entry.name,
            path=entry,
            enabled=frontmatter.get("enabled", True),
            content=body,
        )
        for entry, frontmatter, body in discover_primitives(root, "instructions", "INSTRUCTION.md")
    ]


def resolve_instructions(prompt: str, instructions: list[Instruction]) -> str:
    """Replace instruction placeholders in a prompt string.

    - {{ instructions.<name> }} → specific instruction content
    - {{ instructions }} → all enabled instructions not already placed
    - If no placeholders found → append all at end
    """
    available = {i.name: i.content for i in instructions if i.enabled and i.content}
    return resolve_placeholders(prompt, available, "instructions")
