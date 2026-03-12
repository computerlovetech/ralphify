"""Scaffold templates for ``ralph init`` and ``ralph new`` commands."""

RALPH_TOML_TEMPLATE = """\
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
"""

CHECK_MD_TEMPLATE = """\
---
command: ruff check .
timeout: 60
enabled: true
---
<!--
Optional instructions for the agent when this check fails.
Appended to the prompt alongside the command output.

Example: "Fix all lint errors. Do not add noqa comments."
-->
"""

INSTRUCTION_MD_TEMPLATE = """\
---
enabled: true
---
<!--
Write your instruction content below.
This text will be injected into RALPH.md every iteration.

Use {{ instructions.<name> }} in RALPH.md to place this specifically,
or {{ instructions }} to inject all enabled instructions.
-->
"""

CONTEXT_MD_TEMPLATE = """\
---
command: git log --oneline -10
timeout: 30
enabled: true
---
<!--
Optional static text injected above the command output.
The command runs each iteration and its stdout is appended.

Use {{ contexts.<name> }} in RALPH.md to place this specifically,
or {{ contexts }} to inject all enabled contexts.
-->
"""

RALPH_MD_TEMPLATE = """\
---
description: Describe what this ralph does
enabled: true
---

Your prompt content here.
"""

ROOT_RALPH_TEMPLATE = """\
# Prompt

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

- Implement one thing per iteration
- Search before creating anything new
- No placeholder code — full implementations only
- Run tests and fix failures before committing
- Commit with a descriptive message

<!-- Add your project-specific instructions below -->
"""
