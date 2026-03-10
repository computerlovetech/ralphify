import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ralphify._frontmatter import MAX_OUTPUT_LEN, parse_frontmatter
from ralphify._output import collect_output
from ralphify.resolver import resolve_placeholders


@dataclass
class Context:
    name: str
    path: Path
    command: str | None = None
    script: Path | None = None
    timeout: int = 30
    enabled: bool = True
    static_content: str = ""


@dataclass
class ContextResult:
    context: Context
    output: str
    success: bool
    timed_out: bool = False


_NAMED_PATTERN = re.compile(r"\{\{\s*contexts\.([a-zA-Z0-9_-]+)\s*\}\}")
_BULK_PATTERN = re.compile(r"\{\{\s*contexts\s*\}\}")


def discover_contexts(root: Path = Path(".")) -> list[Context]:
    """Discover contexts in root/.ralph/contexts/ directories."""
    contexts_dir = root / ".ralph" / "contexts"
    if not contexts_dir.is_dir():
        return []

    contexts = []
    for entry in sorted(contexts_dir.iterdir()):
        if not entry.is_dir():
            continue

        context_md = entry / "CONTEXT.md"
        if not context_md.exists():
            continue

        text = context_md.read_text()
        frontmatter, body = parse_frontmatter(text)

        # Look for run.* executable
        script = None
        for f in sorted(entry.iterdir()):
            if f.name.startswith("run.") and f.is_file():
                script = f
                break

        contexts.append(
            Context(
                name=entry.name,
                path=entry,
                command=frontmatter.get("command"),
                script=script,
                timeout=frontmatter.get("timeout", 30),
                enabled=frontmatter.get("enabled", True),
                static_content=body,
            )
        )

    return contexts


def run_context(context: Context, project_root: Path) -> ContextResult:
    """Run a single context command and return the result."""
    if context.script:
        cmd = [str(context.script)]
    elif context.command:
        cmd = shlex.split(context.command)
    else:
        # Static-only context, no command to run
        return ContextResult(context=context, output="", success=True)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=context.timeout,
        )
        return ContextResult(
            context=context,
            output=collect_output(result.stdout, result.stderr),
            success=result.returncode == 0,
        )
    except subprocess.TimeoutExpired as e:
        return ContextResult(
            context=context,
            output=collect_output(e.stdout, e.stderr),
            success=False,
            timed_out=True,
        )


def run_all_contexts(contexts: list[Context], project_root: Path) -> list[ContextResult]:
    """Run all contexts and return results."""
    return [run_context(ctx, project_root) for ctx in contexts]


def _render_context(result: ContextResult) -> str:
    """Render a single context result into text for prompt injection."""
    parts = []

    if result.context.static_content:
        parts.append(result.context.static_content)

    output = result.output
    if len(output) > MAX_OUTPUT_LEN:
        output = output[:MAX_OUTPUT_LEN] + "\n... (truncated)"

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

    return resolve_placeholders(prompt, available, _NAMED_PATTERN, _BULK_PATTERN)
