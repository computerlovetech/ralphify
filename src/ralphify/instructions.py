"""Discover and resolve static instruction text injected into each prompt.

Instructions are reusable rules in ``.ralphify/instructions/<name>/`` that get
injected into the prompt every iteration — for example coding standards or
git conventions.  Unlike contexts, they have no command; their content is
the body text of the INSTRUCTION.md file.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._discovery import discover_local_primitives, discover_primitives
from ralphify._frontmatter import INSTRUCTION_MARKER
from ralphify.resolver import resolve_placeholders


@dataclass
class Instruction:
    """A static instruction discovered from ``.ralphify/instructions/<name>/INSTRUCTION.md``.

    The *content* is the body text below the frontmatter.  Instructions with
    empty content are silently excluded from prompt injection even if enabled.
    """

    name: str
    path: Path
    enabled: bool = True
    content: str = ""


def _instruction_from_entry(prim) -> Instruction:
    """Convert a :class:`PrimitiveEntry` to an :class:`Instruction`."""
    return Instruction(
        name=prim.path.name,
        path=prim.path,
        enabled=prim.frontmatter.get("enabled", True),
        content=prim.body,
    )


def discover_instructions(root: Path = Path(".")) -> list[Instruction]:
    """Scan ``.ralphify/instructions/`` for subdirectories containing ``INSTRUCTION.md``.

    Unlike checks and contexts, instructions have no command or script —
    just static content.  Default: ``enabled=True``.
    """
    return [_instruction_from_entry(prim) for prim in discover_primitives(root, "instructions", INSTRUCTION_MARKER)]


def discover_instructions_local(prompt_dir: Path) -> list[Instruction]:
    """Scan ``prompt_dir/instructions/`` for prompt-scoped instructions.

    Same construction logic as :func:`discover_instructions` but reads from
    a prompt directory instead of the global ``.ralphify/instructions/``.
    """
    return [_instruction_from_entry(prim) for prim in discover_local_primitives(prompt_dir, "instructions", INSTRUCTION_MARKER)]


def resolve_instructions(prompt: str, instructions: list[Instruction]) -> str:
    """Replace instruction placeholders in a prompt string.

    Callers are responsible for passing only the instructions they want
    resolved (the engine pre-filters via ``_discover_enabled_primitives``).
    Instructions with empty content are silently excluded.

    - {{ instructions.<name> }} → specific instruction content
    - {{ instructions }} → all instructions not already placed
    - If no placeholders found → append all at end
    """
    available = {i.name: i.content for i in instructions if i.content}
    return resolve_placeholders(prompt, available, "instructions")
