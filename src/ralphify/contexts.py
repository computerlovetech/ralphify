"""Discover and run dynamic data contexts injected before each iteration.

Contexts live in ``.ralphify/contexts/<name>/`` and provide fresh data to the
prompt each loop — for example recent git history or current test status.
A context can run a command/script, provide static text, or both.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._discovery import discover_local_primitives, discover_primitives, find_run_script
from ralphify._frontmatter import CONTEXT_MARKER
from ralphify._output import truncate_output
from ralphify._runner import run_command
from ralphify.resolver import resolve_placeholders


_DEFAULT_TIMEOUT = 30

@dataclass
class Context:
    """A dynamic data context discovered from ``.ralphify/contexts/<name>/CONTEXT.md``.

    A context may have a *command* or *script* (whose stdout is captured),
    *static_content* (the body text from CONTEXT.md), or both.  When both
    are present the static content appears first, followed by the command output.
    """

    name: str
    path: Path
    command: str | None = None
    script: Path | None = None
    timeout: int = _DEFAULT_TIMEOUT
    enabled: bool = True
    static_content: str = ""


@dataclass
class ContextResult:
    """Outcome of running a single :class:`Context`.

    *output* contains the command's stdout (empty string for static-only
    contexts).  *success* is ``True`` when the command exits with code 0
    or when no command was configured.
    """

    context: Context
    output: str
    success: bool
    timed_out: bool = False


def _context_from_entry(prim) -> Context:
    """Convert a :class:`PrimitiveEntry` to a :class:`Context`."""
    return Context(
        name=prim.path.name,
        path=prim.path,
        command=prim.frontmatter.get("command"),
        script=find_run_script(prim.path),
        timeout=prim.frontmatter.get("timeout", _DEFAULT_TIMEOUT),
        enabled=prim.frontmatter.get("enabled", True),
        static_content=prim.body,
    )


def discover_contexts(root: Path = Path(".")) -> list[Context]:
    """Scan ``.ralphify/contexts/`` for subdirectories containing a ``CONTEXT.md``.

    Returns all discovered contexts (both enabled and disabled) sorted
    alphabetically by name.  The caller is responsible for filtering by
    ``enabled`` before execution.
    """
    return [_context_from_entry(prim) for prim in discover_primitives(root, "contexts", CONTEXT_MARKER)]


def discover_contexts_local(prompt_dir: Path) -> list[Context]:
    """Scan ``prompt_dir/contexts/`` for prompt-scoped contexts.

    Same construction logic as :func:`discover_contexts` but reads from
    a prompt directory instead of the global ``.ralphify/contexts/``.
    """
    return [_context_from_entry(prim) for prim in discover_local_primitives(prompt_dir, "contexts", CONTEXT_MARKER)]


def run_context(context: Context, project_root: Path) -> ContextResult:
    """Run a single context and return the result.

    Static-only contexts (no script or command) return immediately with
    ``success=True`` and empty output.  The static content is combined
    with command output later during prompt resolution.
    """
    if not context.script and not context.command:
        # Static-only context, no command to run
        return ContextResult(context=context, output="", success=True)

    r = run_command(
        script=context.script,
        command=context.command,
        cwd=project_root,
        timeout=context.timeout,
    )
    return ContextResult(
        context=context,
        output=r.output,
        success=r.success,
        timed_out=r.timed_out,
    )


def run_all_contexts(contexts: list[Context], project_root: Path) -> list[ContextResult]:
    """Run every context sequentially and return all results.

    Each context's command (or script) executes with *project_root* as the
    working directory.  Static-only contexts return immediately.  Results
    are passed to :func:`resolve_contexts` for prompt injection.
    """
    return [run_context(ctx, project_root) for ctx in contexts]


def resolve_contexts(prompt: str, results: list[ContextResult]) -> str:
    """Replace context placeholders in a prompt string.

    Each context result is rendered by combining its static content (if any)
    with its truncated command output, then injected into the prompt via
    :func:`resolve_placeholders`.

    Callers are responsible for passing only the results they want
    resolved (the engine pre-filters via ``_discover_enabled_primitives``).

    - {{ contexts.<name> }} → specific context content
    - {{ contexts }} → all contexts not already placed
    - If no placeholders found → append all at end
    """
    available: dict[str, str] = {}
    for r in results:
        parts = []
        if r.context.static_content:
            parts.append(r.context.static_content)
        output = truncate_output(r.output)
        if output.strip():
            parts.append(output.strip())
        rendered = "\n".join(parts)
        if rendered:
            available[r.context.name] = rendered

    return resolve_placeholders(prompt, available, "contexts")
