import re
import shlex
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    path: Path
    command: str | None
    script: Path | None
    timeout: int = 60
    enabled: bool = True
    failure_instruction: str = ""


@dataclass
class CheckResult:
    check: Check
    passed: bool
    exit_code: int
    output: str
    timed_out: bool = False


def parse_check_md(text: str) -> tuple[dict, str]:
    """Parse a CHECK.md file with optional YAML-like frontmatter.

    Frontmatter is delimited by --- lines. Only flat key: value pairs
    are supported. Returns (frontmatter_dict, body_text).
    """
    frontmatter: dict = {}
    body = text

    stripped = text.strip()
    if stripped.startswith("---"):
        lines = text.split("\n")
        # Find the opening ---
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if start is None:
                    start = i
                else:
                    # Found closing ---
                    fm_lines = lines[start + 1 : i]
                    body = "\n".join(lines[i + 1 :]).strip()
                    for fm_line in fm_lines:
                        fm_line = fm_line.strip()
                        if not fm_line or fm_line.startswith("#"):
                            continue
                        if ":" not in fm_line:
                            continue
                        key, _, value = fm_line.partition(":")
                        key = key.strip()
                        value = value.strip()
                        # Type coercion
                        if key == "timeout":
                            frontmatter[key] = int(value)
                        elif key == "enabled":
                            frontmatter[key] = value.lower() in ("true", "yes", "1")
                        else:
                            frontmatter[key] = value
                    break

    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    return frontmatter, body


def discover_checks(root: Path = Path(".")) -> list[Check]:
    """Discover checks in root/.ralph/checks/ directories."""
    checks_dir = root / ".ralph" / "checks"
    if not checks_dir.is_dir():
        return []

    checks = []
    for entry in sorted(checks_dir.iterdir()):
        if not entry.is_dir():
            continue

        check_md = entry / "CHECK.md"
        if not check_md.exists():
            continue

        text = check_md.read_text()
        frontmatter, body = parse_check_md(text)

        # Look for run.* executable
        script = None
        for f in sorted(entry.iterdir()):
            if f.name.startswith("run.") and f.is_file():
                script = f
                break

        command = frontmatter.get("command")

        if not script and not command:
            warnings.warn(f"Check '{entry.name}' has neither a run.* script nor a command — skipping")
            continue

        checks.append(
            Check(
                name=entry.name,
                path=entry,
                command=command,
                script=script,
                timeout=frontmatter.get("timeout", 60),
                enabled=frontmatter.get("enabled", True),
                failure_instruction=body,
            )
        )

    return checks


def run_check(check: Check, project_root: Path) -> CheckResult:
    """Run a single check and return the result."""
    if check.script:
        cmd = [str(check.script)]
    else:
        cmd = shlex.split(check.command)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=check.timeout,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr

        return CheckResult(
            check=check,
            passed=result.returncode == 0,
            exit_code=result.returncode,
            output=output,
        )
    except subprocess.TimeoutExpired as e:
        output = ""
        if e.stdout:
            output += e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
        if e.stderr:
            output += e.stderr if isinstance(e.stderr, str) else e.stderr.decode()

        return CheckResult(
            check=check,
            passed=False,
            exit_code=-1,
            output=output,
            timed_out=True,
        )


def run_all_checks(checks: list[Check], project_root: Path) -> list[CheckResult]:
    """Run all checks and return results."""
    return [run_check(check, project_root) for check in checks]


MAX_OUTPUT_LEN = 5000


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

        output = r.output
        if len(output) > MAX_OUTPUT_LEN:
            output = output[:MAX_OUTPUT_LEN] + "\n... (truncated)"

        if output.strip():
            parts.append(f"\n```\n{output.strip()}\n```\n")

        if r.check.failure_instruction:
            parts.append(r.check.failure_instruction)
            parts.append("")

    return "\n".join(parts)
