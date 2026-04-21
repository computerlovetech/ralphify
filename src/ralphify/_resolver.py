"""Template placeholder resolution for commands and args.

Only named placeholders are supported:

``{{ kind.name }}`` inserts a specific value's content.

Items not referenced by a named placeholder are excluded from the
prompt.  This forces explicit placement and avoids accidental data dumps.
"""

from __future__ import annotations

import re

from ralphify._frontmatter import NAME_RE, FIELD_ARGS, FIELD_COMMANDS, FIELD_RALPH

_NAME = NAME_RE.pattern  # inlined for readability inside verbose regexes

# Pattern matching ``{{ args.<name> }}`` placeholders — used by resolve_args
# to resolve arg placeholders in command run strings independently of commands.
_ARGS_RE = re.compile(
    rf"""
    \{{\{{              # opening literal {{{{
    \s*                 # optional whitespace
    {FIELD_ARGS}        # "args"
    \.                  # dot separator
    ({_NAME})           # capture: placeholder name
    \s*                 # optional whitespace
    \}}\}}              # closing literal }}}}
    """,
    re.VERBOSE,
)


def resolve_args(prompt: str, user_args: dict[str, str]) -> str:
    """Replace ``{{ args.name }}`` placeholders with user-supplied values.

    Unknown names (and all placeholders when *user_args* is empty) resolve
    to the empty string, so stray ``{{ args.* }}`` never leak into the
    assembled prompt.
    """

    def _replace(match: re.Match) -> str:
        return user_args.get(match.group(1), "")

    return _ARGS_RE.sub(_replace, prompt)


# Single pattern matching all placeholder kinds for single-pass resolution.
_ALL_RE = re.compile(
    rf"""
    \{{\{{              # opening literal {{{{
    \s*                 # optional whitespace
    (                   # group 1: placeholder kind
        {FIELD_COMMANDS}
      | {FIELD_ARGS}
      | {FIELD_RALPH}
    )
    \.                  # dot separator
    ({_NAME})           # group 2: placeholder name
    \s*                 # optional whitespace
    \}}\}}              # closing literal }}}}
    """,
    re.VERBOSE,
)


def resolve_all(
    prompt: str,
    command_outputs: dict[str, str],
    user_args: dict[str, str],
    ralph_context: dict[str, str] | None = None,
) -> str:
    """Resolve all placeholders in a single pass to prevent cross-contamination.

    Resolves ``{{ commands.name }}``, ``{{ args.name }}``, and
    ``{{ ralph.name }}`` in a single pass so values inserted by one
    kind of placeholder are not re-processed as the other kind.
    """
    lookups: dict[str, dict[str, str]] = {
        FIELD_COMMANDS: command_outputs,
        FIELD_ARGS: user_args,
        FIELD_RALPH: ralph_context or {},
    }

    def _replace(match: re.Match) -> str:
        kind = match.group(1)
        name = match.group(2)
        return lookups[kind].get(name, "")

    return _ALL_RE.sub(_replace, prompt)
