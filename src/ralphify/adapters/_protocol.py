"""Adapter Protocol, event type, and registry.

Concrete adapter modules (:mod:`claude`, :mod:`codex`, :mod:`copilot`,
:mod:`_generic`) import from here rather than from the package
``__init__``.  The package ``__init__`` populates :data:`ADAPTERS` by
importing concrete adapters, and those adapters need the Protocol
before the ``__init__`` finishes executing — keeping the Protocol in a
leaf module makes the import graph acyclic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, NamedTuple, Protocol, runtime_checkable


AdapterEventKind = Literal["tool_use", "turn", "message", "result"]
"""Categories of events an adapter can surface from a CLI's output stream."""

CountsWhat = Literal["tool_use", "turn", "none"]
"""What an adapter counts against ``max_turns`` — tool uses, turns, or nothing."""


class AdapterEvent(NamedTuple):
    """A single structured event parsed from a CLI's output stream.

    ``kind`` is the event category; ``name`` carries a tool name for
    ``tool_use`` events (``None`` otherwise); ``raw`` is the original
    parsed JSON object so callers can inspect extra fields when needed.
    """

    kind: AdapterEventKind
    name: str | None = None
    raw: dict | None = None


@runtime_checkable
class CLIAdapter(Protocol):
    """Protocol every CLI adapter must satisfy.

    Adapters are stateless singletons: the same instance is reused for
    every iteration of every run.  Any per-iteration state lives in the
    caller (``_agent.py``) — adapters only translate.
    """

    name: str
    counts_what: CountsWhat
    supports_streaming: bool
    renders_structured_peek: bool
    supports_soft_wind_down: bool
    requires_full_stdout_for_completion: bool

    def matches(self, cmd: list[str]) -> bool:
        """Return True if this adapter handles the given agent command."""
        ...

    def build_command(self, cmd: list[str]) -> list[str]:
        """Return the command with any adapter-required flags appended.

        Idempotent: calling twice returns the same command.
        """
        ...

    def parse_event(self, line: str) -> AdapterEvent | None:
        """Parse one line of stdout into an :class:`AdapterEvent`.

        Returns ``None`` for lines that are not recognised events.
        MUST NOT raise on malformed input (per FR-8).
        """
        ...

    def extract_completion_signal(
        self,
        *,
        result_text: str | None,
        stdout: str | None,
        user_signal: str,
    ) -> bool:
        """Return True if the agent's final output contains the completion signal.

        The signal is wrapped in ``<promise>...</promise>`` markup; the
        inner text equals ``user_signal``.

        Adapters receive both the streaming-extracted *result_text* (the
        terminal assistant message, when the streaming path could parse one)
        and the full *stdout* buffer (only present when the engine chose to
        capture it).  Adapters with ``requires_full_stdout_for_completion``
        set False MUST be able to detect completion from *result_text* alone;
        engines may pass ``stdout=None`` to skip the memory cost.
        """
        ...

    def install_wind_down_hook(
        self,
        tempdir: Path,
        counter_path: Path,
        cap: int,
        grace: int,
    ) -> dict[str, str]:
        """Write hook config files into *tempdir* and return env-var overrides.

        Only called when ``supports_soft_wind_down`` is True.  Adapters that
        set the flag False may leave this unimplemented (a ``NotImplementedError``
        is acceptable and is treated as a runtime downgrade to hard-cap-only).
        """
        ...


ADAPTERS: list[CLIAdapter] = []
"""Adapter registry, populated at import time by concrete adapter modules.

Ordering matters: :func:`ralphify.adapters.select_adapter` returns the
first adapter whose ``matches`` method returns True, with
:class:`ralphify.adapters._generic.GenericAdapter` as a final catch-all.
Specific adapters go first, generic last.
"""
