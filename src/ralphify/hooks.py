"""User-subscribable agent lifecycle hook protocol.

Hooks let downstream consumers (milknado orchestration, user shell
scripts declared in ``RALPH.md``) react to iteration boundaries,
tool-use events, and turn-cap signals without coupling to the engine
internals.

The :class:`AgentHook` Protocol defines keyword-only ``on_*`` callbacks.
:class:`CombinedAgentHook` fans events out across a list of hooks with
per-hook exception isolation — a single misbehaving hook script cannot
take down the run.  :class:`ShellAgentHook` is the concrete hook that
backs the ``hooks:`` frontmatter field: it invokes a shell command with
the event payload as JSON on stdin.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from typing import Any, Protocol, runtime_checkable


_log = logging.getLogger(__name__)


HOOK_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "on_iteration_started",
        "on_commands_completed",
        "on_prompt_assembled",
        "on_tool_use",
        "on_turn_approaching_limit",
        "on_turn_capped",
        "on_iteration_completed",
        "on_completion_signal",
    }
)
"""Valid event names for the ``hooks:`` frontmatter field.

Kept as a frozenset so :mod:`ralphify._frontmatter` can validate user
configuration without importing :class:`AgentHook` directly.
"""


@runtime_checkable
class AgentHook(Protocol):
    """Receive structured notifications at iteration boundaries.

    All methods accept keyword arguments only so adding new fields in
    future versions stays backward compatible for implementers.  Hooks
    MUST NOT raise — the fanout catches exceptions, but hooks that fail
    silently are hard to debug.  Log and continue.
    """

    def on_iteration_started(self, *, iteration: int) -> None: ...

    def on_commands_completed(
        self, *, iteration: int, outputs: dict[str, str]
    ) -> None: ...

    def on_prompt_assembled(self, *, iteration: int, prompt: str) -> None: ...

    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None: ...

    def on_turn_approaching_limit(
        self, *, iteration: int, count: int, max_turns: int
    ) -> None: ...

    def on_turn_capped(self, *, iteration: int, count: int) -> None: ...

    def on_iteration_completed(
        self, *, iteration: int, result: dict[str, Any]
    ) -> None: ...

    def on_completion_signal(self, *, iteration: int, signal: str) -> None: ...


class NoOpAgentHook:
    """Default :class:`AgentHook` that discards every event silently.

    Useful as a base class for hooks that only care about a subset of
    events — override the methods you need, inherit the rest.
    """

    def on_iteration_started(self, *, iteration: int) -> None:
        pass

    def on_commands_completed(self, *, iteration: int, outputs: dict[str, str]) -> None:
        pass

    def on_prompt_assembled(self, *, iteration: int, prompt: str) -> None:
        pass

    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None:
        pass

    def on_turn_approaching_limit(
        self, *, iteration: int, count: int, max_turns: int
    ) -> None:
        pass

    def on_turn_capped(self, *, iteration: int, count: int) -> None:
        pass

    def on_iteration_completed(self, *, iteration: int, result: dict[str, Any]) -> None:
        pass

    def on_completion_signal(self, *, iteration: int, signal: str) -> None:
        pass


class CombinedAgentHook:
    """Fan each callback across a list of hooks with exception isolation.

    One misbehaving hook cannot poison the others: exceptions are logged
    at warning level and the fanout continues.
    """

    def __init__(self, hooks: list[AgentHook]) -> None:
        self._hooks = hooks

    def _fanout(self, event_name: str, **kwargs: Any) -> None:
        for hook in self._hooks:
            method = getattr(hook, event_name, None)
            if method is None:
                continue
            try:
                method(**kwargs)
            except Exception as exc:
                _log.warning(
                    "hook %r raised in %s: %s",
                    getattr(hook, "__class__", type(hook)).__name__,
                    event_name,
                    exc,
                )

    def on_iteration_started(self, *, iteration: int) -> None:
        self._fanout("on_iteration_started", iteration=iteration)

    def on_commands_completed(self, *, iteration: int, outputs: dict[str, str]) -> None:
        self._fanout("on_commands_completed", iteration=iteration, outputs=outputs)

    def on_prompt_assembled(self, *, iteration: int, prompt: str) -> None:
        self._fanout("on_prompt_assembled", iteration=iteration, prompt=prompt)

    def on_tool_use(self, *, iteration: int, tool_name: str, count: int) -> None:
        self._fanout(
            "on_tool_use",
            iteration=iteration,
            tool_name=tool_name,
            count=count,
        )

    def on_turn_approaching_limit(
        self, *, iteration: int, count: int, max_turns: int
    ) -> None:
        self._fanout(
            "on_turn_approaching_limit",
            iteration=iteration,
            count=count,
            max_turns=max_turns,
        )

    def on_turn_capped(self, *, iteration: int, count: int) -> None:
        self._fanout("on_turn_capped", iteration=iteration, count=count)

    def on_iteration_completed(self, *, iteration: int, result: dict[str, Any]) -> None:
        self._fanout("on_iteration_completed", iteration=iteration, result=result)

    def on_completion_signal(self, *, iteration: int, signal: str) -> None:
        self._fanout("on_completion_signal", iteration=iteration, signal=signal)


class ShellAgentHook(NoOpAgentHook):
    """Invoke a shell command for one lifecycle event.

    The event payload is serialized to JSON and written to the command's
    stdin.  Stdout is captured to the log; a non-zero exit is logged but
    does NOT abort the run (per FR-9).  The command is parsed with
    :func:`shlex.split` — no shell metacharacter expansion.
    """

    def __init__(self, event: str, command: str) -> None:
        if event not in HOOK_EVENT_NAMES:
            raise ValueError(
                f"unknown hook event {event!r}; "
                f"expected one of {sorted(HOOK_EVENT_NAMES)}"
            )
        self._event = event
        self._command = command
        setattr(self, event, self._invoke)

    def _invoke(self, **payload: Any) -> None:
        try:
            data = json.dumps(payload, default=str)
        except (TypeError, ValueError) as exc:
            _log.warning("hook %r: failed to serialize payload: %s", self._event, exc)
            return
        try:
            proc = subprocess.run(
                shlex.split(self._command),
                input=data,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _log.warning(
                "hook %r: command %r failed to start: %s",
                self._event,
                self._command,
                exc,
            )
            return
        if proc.returncode != 0:
            _log.warning(
                "hook %r: command %r exited %d (stderr=%r)",
                self._event,
                self._command,
                proc.returncode,
                proc.stderr[:200],
            )
        if proc.stdout:
            _log.info("hook %r stdout: %s", self._event, proc.stdout[:500])


__all__ = [
    "AgentHook",
    "CombinedAgentHook",
    "HOOK_EVENT_NAMES",
    "NoOpAgentHook",
    "ShellAgentHook",
]
