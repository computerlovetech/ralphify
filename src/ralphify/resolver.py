"""Template placeholder resolution shared by contexts and instructions.

Handles three placement strategies:

1. **Named** — ``{{ kind.name }}`` inserts a specific primitive's content.
2. **Bulk** — ``{{ kind }}`` inserts all remaining primitives (alphabetically).
3. **Implicit** — when no placeholders exist, all content is appended to the end.
"""

import re


def resolve_placeholders(
    prompt: str,
    available: dict[str, str],
    kind: str,
) -> str:
    """Replace template placeholders in a prompt string.

    *kind* is the placeholder category (e.g. "contexts" or "instructions").

    - Named placeholders (e.g. {{ kind.name }}) -> specific content
    - Bulk placeholder (e.g. {{ kind }}) -> all not already placed
    - No placeholders found -> append all at end
    """
    if not available:
        return prompt

    named_pattern = re.compile(r"\{\{\s*" + re.escape(kind) + r"\.([a-zA-Z0-9_-]+)\s*\}\}")
    bulk_pattern = re.compile(r"\{\{\s*" + re.escape(kind) + r"\s*\}\}")

    has_named = bool(named_pattern.search(prompt))
    placed: set[str] = set()

    def _replace_named(match: re.Match) -> str:
        name = match.group(1)
        if name in available:
            placed.add(name)
            return available[name]
        return ""

    result = named_pattern.sub(_replace_named, prompt)

    remaining = [content for name, content in sorted(available.items()) if name not in placed]
    bulk_text = "\n\n".join(remaining)

    if bulk_pattern.search(result):
        result = bulk_pattern.sub(bulk_text, result)
    elif not has_named:
        # No placeholders found at all -> append
        if bulk_text:
            result = result + "\n\n" + bulk_text

    return result
