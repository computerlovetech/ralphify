"""Parse promise completion tags emitted by agents."""

from __future__ import annotations

import re

_PROMISE_TAG_RE = re.compile(r"<promise>(.*?)</promise>", re.DOTALL)


def _normalize_promise_text(text: str) -> str:
    """Collapse internal whitespace so config and tag payloads compare consistently."""
    return " ".join(text.split())


def parse_promise_tags(text: str | None) -> list[str]:
    """Return normalized inner text from all well-formed promise tags in *text*."""
    if not text:
        return []
    return [
        _normalize_promise_text(match.group(1))
        for match in _PROMISE_TAG_RE.finditer(text)
    ]


def has_promise_completion(text: str | None, completion_signal: str) -> bool:
    """Return True when *text* contains a matching promise completion tag."""
    return _normalize_promise_text(completion_signal) in parse_promise_tags(text)
