"""Charm Crush CLI adapter.

Crush (https://github.com/charmbracelet/crush) is TUI-first but ships a
``crush run`` subcommand for non-interactive single-prompt use:

    crush run "<prompt>"            # prompt as positional args
    echo "<prompt>" | crush run     # prompt piped on stdin

``crush run`` auto-approves every permission request for the duration of
the invocation, so it runs fully autonomously in a loop without a
``--yolo``-style flag.  A provider must be configured first (via env vars
such as ``ANTHROPIC_API_KEY`` or a ``crush.json``); otherwise ``run`` exits
with "no providers configured".

Capability matrix:

- ``counts_what = "none"`` — crush emits **plain text / markdown only**.
  There is no ``--json`` / ``--output-format`` / streaming-event mode, so
  there are no tool-use or turn events to count against ``max_turns``.
- ``supports_streaming = False`` — no parseable event stream; the adapter
  runs on the blocking path and never parses per-line events.
- ``renders_structured_peek = False`` — peek panel stays in raw-line mode.
- ``supports_soft_wind_down = False`` — crush has no hook system, so
  ``install_wind_down_hook`` raises :class:`NotImplementedError` (the
  engine downgrades this to hard-cap-only).
- ``requires_full_stdout_for_completion = True`` — with no streaming
  result event, promise detection scans the full stdout buffer.

Because crush gives ralphify no structured output, this adapter behaves
like the generic stdin adapter; its job is to claim the ``crush`` binary
stem, inject the headless ``--quiet`` flag, and provide a named home for a
future JSON-output upgrade should Crush add one.
"""

from __future__ import annotations

from pathlib import Path

from ralphify._promise import has_promise_completion
from ralphify.adapters._protocol import (
    ADAPTERS,
    AdapterEvent,
    CountsWhat,
    Invocation,
    stdin_invocation,
)


CRUSH_BINARY_STEM = "crush"
"""Binary stem (``Path(cmd[0]).stem``) that identifies the Crush CLI."""

_QUIET_FLAGS: frozenset[str] = frozenset({"--quiet", "-q"})


class CrushAdapter:
    """Runs ``crush run`` on the blocking path; crush has no structured output."""

    name: str = "crush"
    counts_what: CountsWhat = "none"
    supports_streaming: bool = False
    renders_structured_peek: bool = False
    supports_soft_wind_down: bool = False
    # crush emits no streaming result event; the full stdout buffer is the
    # only source for promise-tag scanning.
    requires_full_stdout_for_completion: bool = True

    def matches(self, cmd: list[str]) -> bool:
        if not cmd:
            return False
        return Path(cmd[0]).stem == CRUSH_BINARY_STEM

    def build_command(self, cmd: list[str]) -> list[str]:
        """Append ``--quiet`` to hide crush's spinner in non-interactive runs.

        Idempotent: skips injection when the caller already supplied
        ``--quiet`` or its ``-q`` short form. ``--quiet`` is a ``run``
        subcommand flag, so it is appended after any existing args (e.g.
        ``crush run`` -> ``crush run --quiet``).
        """
        result = list(cmd)
        if _QUIET_FLAGS.isdisjoint(result):
            result.append("--quiet")
        return result

    def deliver_prompt(self, cmd: list[str], prompt: str) -> Invocation:
        """crush reads the prompt from stdin (blocking path)."""
        return stdin_invocation(cmd, prompt)

    def parse_event(self, line: str) -> AdapterEvent | None:
        """crush has no structured event stream; nothing to parse.

        Returns ``None`` unconditionally, like the generic adapter. Never
        raises (per FR-8).
        """
        del line
        return None

    def extract_completion_signal(
        self,
        *,
        result_text: str | None,
        stdout: str | None,
        user_signal: str,
    ) -> bool:
        """Scan the full stdout for the ``<promise>{signal}</promise>`` tag.

        *result_text* is unused — crush runs on the blocking path and emits
        no streaming result event. The engine opts into
        ``requires_full_stdout_for_completion`` so *stdout* is supplied when
        promise detection is requested.
        """
        del result_text
        if stdout is None:
            return False
        return has_promise_completion(stdout, user_signal)

    def install_wind_down_hook(
        self,
        tempdir: Path,
        counter_path: Path,
        cap: int,
        grace: int,
    ) -> dict[str, str]:
        raise NotImplementedError(
            "crush has no hook system; soft wind-down is unavailable and "
            "max_turns will hard-kill without a wind-down signal."
        )


ADAPTERS.append(CrushAdapter())
