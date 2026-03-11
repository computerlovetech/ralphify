"""Discover and run dynamic data contexts injected before each iteration.

Contexts live in ``.ralph/contexts/<name>/`` and provide fresh data to the
prompt each loop — for example recent git history or current test status.
A context can run a command/script, provide static text, or both.
"""

from dataclasses import dataclass
from pathlib import Path

from ralphify._frontmatter import discover_primitives, find_run_script
from ralphify._output import truncate_output
from ralphify._runner import run_command
from ralphify.resolver import resolve_placeholders


@dataclass
class Context:
    """A dynamic data context discovered from ``.ralph/contexts/<name>/CONTEXT.md``.

    A context may have a *command* or *script* (whose stdout is captured),
    *static_content* (the body text from CONTEXT.md), or both.  When both
    are present the static content appears first, followed by the command output.
    """

    name: str
    path: Path
    command: str | None = None
    script: Path | None = None
    timeout: int = 30
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


def discover_contexts(root: Path = Path(".")) -> list[Context]:
    """Discover contexts in root/.ralph/contexts/ directories."""
    contexts = []
    for entry, frontmatter, body in discover_primitives(root, "contexts", "CONTEXT.md"):
        contexts.append(
            Context(
                name=entry.name,
                path=entry,
                command=frontmatter.get("command"),
                script=find_run_script(entry),
                timeout=frontmatter.get("timeout", 30),
                enabled=frontmatter.get("enabled", True),
                static_content=body,
            )
        )

    return contexts


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
    """Run all contexts and return results."""
    return [run_context(ctx, project_root) for ctx in contexts]


def _render_context(result: ContextResult) -> str:
    """Render a single context result into text for prompt injection."""
    parts = []

    if result.context.static_content:
        parts.append(result.context.static_content)

    output = truncate_output(result.output)

    if output.strip():
        parts.append(output.strip())

    return "\n".join(parts)


def resolve_contexts(prompt: str, results: list[ContextResult]) -> str:
    """Replace context placeholders in a prompt string.

    - {{ contexts.<name> }} → specific context content
    - {{ contexts }} → all enabled contexts not already placed
    - If no placeholders found → append all at end
    """
    available: dict[str, str] = {}
    for r in results:
        if not r.context.enabled:
            continue
        rendered = _render_context(r)
        if rendered:
            available[r.context.name] = rendered

    return resolve_placeholders(prompt, available, "contexts")
