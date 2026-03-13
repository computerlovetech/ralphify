"""Discover and run validation checks after each loop iteration.

Checks are scripts or commands in ``.ralphify/checks/<name>/`` that validate
the agent's work (tests, linters, type checkers).  When a check fails its
output and failure instruction are formatted for injection into the next
iteration's prompt, creating a self-healing feedback loop.
"""

import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ralphify._discovery import PrimitiveEntry, discover_enabled, discover_local_primitives, discover_primitives, find_run_script
from ralphify._frontmatter import CHECK_MARKER
from ralphify._output import truncate_output
from ralphify._runner import run_command


_DEFAULT_TIMEOUT = 60

@dataclass
class Check:
    """A validation check discovered from ``.ralphify/checks/<name>/CHECK.md``.

    Either *command* or *script* must be set.  If both exist, *script* wins.
    The *failure_instruction* (body text from CHECK.md) is appended to the
    prompt when the check fails, guiding the agent toward a fix.
    """

    name: str
    path: Path
    command: str | None
    script: Path | None
    timeout: int = _DEFAULT_TIMEOUT
    enabled: bool = True
    failure_instruction: str = ""


@dataclass
class CheckResult:
    """Outcome of running a single :class:`Check`.

    *passed* is ``True`` when the command exits with code 0.
    *exit_code* is ``-1`` when the check timed out.
    """

    check: Check
    passed: bool
    exit_code: int
    output: str
    timed_out: bool = False

    def to_event_data(self) -> dict:
        """Serialize to a dict for event emission.

        This is the single source of truth for how check results appear
        in engine events.  Both per-check and summary events use this.
        """
        return {
            "name": self.check.name,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "output": self.output,
        }


def _check_from_entry(prim: PrimitiveEntry) -> Check | None:
    """Convert a :class:`PrimitiveEntry` to a :class:`Check`, or ``None`` if invalid."""
    script = find_run_script(prim.path)
    command = prim.frontmatter.get("command")

    if not script and not command:
        warnings.warn(f"Check '{prim.path.name}' has neither a run.* script nor a command — skipping")
        return None

    return Check(
        name=prim.path.name,
        path=prim.path,
        command=command,
        script=script,
        timeout=prim.frontmatter.get("timeout", _DEFAULT_TIMEOUT),
        enabled=prim.frontmatter.get("enabled", True),
        failure_instruction=prim.body,
    )


def _checks_from_entries(entries: Iterable[PrimitiveEntry]) -> list[Check]:
    """Convert primitive entries to Checks, skipping entries without a command or script."""
    return [c for c in map(_check_from_entry, entries) if c is not None]


def discover_checks(root: Path = Path(".")) -> list[Check]:
    """Scan ``.ralphify/checks/`` for subdirectories containing a ``CHECK.md``.

    Checks without both a ``run.*`` script and a ``command`` in frontmatter
    are skipped with a warning.  Defaults: ``timeout=_DEFAULT_TIMEOUT``, ``enabled=True``.
    """
    return _checks_from_entries(discover_primitives(root, "checks", CHECK_MARKER))


def discover_checks_local(ralph_dir: Path) -> list[Check]:
    """Scan ``ralph_dir/checks/`` for ralph-scoped checks.

    Same construction logic as :func:`discover_checks` but reads from
    a ralph directory instead of the global ``.ralphify/checks/``.
    """
    return _checks_from_entries(discover_local_primitives(ralph_dir, "checks", CHECK_MARKER))


def discover_enabled_checks(root: Path, ralph_dir: Path | None = None) -> list[Check]:
    """Discover checks, merge local overrides, and return only enabled ones.

    Convenience wrapper over :func:`~ralphify._discovery.discover_enabled`
    so callers don't need to wire up the discover/discover_local callables.
    """
    return discover_enabled(root, ralph_dir, discover_checks, discover_checks_local)


def run_check(check: Check, project_root: Path) -> CheckResult:
    """Run a single check and return the result.

    The check's script or command executes with *project_root* as the
    working directory.  On timeout, ``exit_code`` is ``-1`` and
    ``timed_out`` is ``True``.
    """
    r = run_command(
        script=check.script,
        command=check.command,
        cwd=project_root,
        timeout=check.timeout,
    )
    return CheckResult(
        check=check,
        passed=r.success,
        exit_code=r.exit_code,
        output=r.output,
        timed_out=r.timed_out,
    )


def run_all_checks(checks: list[Check], project_root: Path) -> list[CheckResult]:
    """Run every check sequentially and return all results.

    Checks execute in the order given (the engine sorts alphabetically by
    name).  Failures do not short-circuit — all checks run regardless so
    the agent receives the complete picture of what's broken.

    The engine passes the results to :func:`format_check_failures`, which
    formats them as markdown for injection into the next iteration's prompt.
    This is what drives the self-healing feedback loop.
    """
    return [run_check(check, project_root) for check in checks]


def format_check_failures(results: list[CheckResult]) -> str:
    """Format check failures as markdown for injection into the next prompt.

    Returns empty string if all checks passed.
    """
    failures = [r for r in results if not r.passed]
    if not failures:
        return ""

    parts = ["## Check Failures\n"]
    parts.append("The following checks failed after the last iteration. Fix these issues:\n")

    for r in failures:
        parts.append(f"### {r.check.name}")
        if r.timed_out:
            parts.append(f"**Timed out** after {r.check.timeout}s")
        else:
            parts.append(f"**Exit code:** {r.exit_code}")

        output = truncate_output(r.output)

        if output.strip():
            parts.append(f"\n```\n{output.strip()}\n```\n")

        if r.check.failure_instruction:
            parts.append(r.check.failure_instruction)
            parts.append("")

    return "\n".join(parts)
