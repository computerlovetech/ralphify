import re
from dataclasses import dataclass
from pathlib import Path

from ralphify._frontmatter import parse_frontmatter
from ralphify.resolver import resolve_placeholders


@dataclass
class Instruction:
    name: str
    path: Path
    enabled: bool = True
    content: str = ""


_NAMED_PATTERN = re.compile(r"\{\{\s*instructions\.([a-zA-Z0-9_-]+)\s*\}\}")
_BULK_PATTERN = re.compile(r"\{\{\s*instructions\s*\}\}")


def discover_instructions(root: Path = Path(".")) -> list[Instruction]:
    """Discover instructions in root/.ralph/instructions/ directories."""
    instructions_dir = root / ".ralph" / "instructions"
    if not instructions_dir.is_dir():
        return []

    instructions = []
    for entry in sorted(instructions_dir.iterdir()):
        if not entry.is_dir():
            continue

        instruction_md = entry / "INSTRUCTION.md"
        if not instruction_md.exists():
            continue

        text = instruction_md.read_text()
        frontmatter, body = parse_frontmatter(text)

        instructions.append(
            Instruction(
                name=entry.name,
                path=entry,
                enabled=frontmatter.get("enabled", True),
                content=body,
            )
        )

    return instructions


def resolve_instructions(prompt: str, instructions: list[Instruction]) -> str:
    """Replace instruction placeholders in a prompt string.

    - {{ instructions.<name> }} → specific instruction content
    - {{ instructions }} → all enabled instructions not already placed
    - If no placeholders found → append all at end
    """
    available = {i.name: i.content for i in instructions if i.enabled and i.content}
    return resolve_placeholders(prompt, available, _NAMED_PATTERN, _BULK_PATTERN)
