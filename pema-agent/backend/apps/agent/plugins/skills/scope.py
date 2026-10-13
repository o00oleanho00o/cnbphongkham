"""Where an item applies. A scope is ``agent`` (every channel), ``plugin:<name>`` (every channel that plugin
registered, ``zalo`` for each Zalo account) or ``channel:<name>`` (one channel, one account). A channel gets
the items whose scopes match it, the broad ones first and the narrow ones last: the narrow one is the more
specific and wins when two disagree."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Final

from agentcore.channels import valid_channel_name

AGENT: Final = "agent"
PLUGIN: Final = "plugin"
CHANNEL: Final = "channel"
RANK: Final = {AGENT: 0, PLUGIN: 1, CHANNEL: 2}

PluginOf = Callable[[str], str | None]
"""The plugin a channel comes from, None for a channel no plugin registered."""


def parse(scope: str) -> tuple[str, str]:
    """``(kind, key)``; raises ``ValueError`` naming what is wrong."""
    if scope == AGENT:
        return AGENT, ""
    kind, sep, key = scope.partition(":")
    if kind not in (PLUGIN, CHANNEL) or not sep:
        raise ValueError(f"scope {scope!r}: use agent, plugin:<name> or channel:<name>")
    if not valid_channel_name(key):
        raise ValueError(f"scope {scope!r}: {key!r} is not a valid {kind} name")
    return kind, key


def clean(scopes: Iterable[str]) -> list[str]:
    """The scopes checked and without repeats, in the order given; empty stays empty (the whole agent)."""
    found: list[str] = []
    for scope in scopes:
        parse(scope)
        if scope not in found:
            found.append(scope)
    return found


def reach(scopes: Sequence[str], channel: str | None, plugin_of: PluginOf) -> int | None:
    """How specifically the scopes match a turn on ``channel``: 0 the whole agent, 1 its plugin, 2 the
    channel itself; None when none does. No scopes means the whole agent."""
    if not scopes:
        return 0
    owner = plugin_of(channel) if channel else None
    best: int | None = None
    for scope in scopes:
        kind, key = parse(scope)
        matches = (
            kind == AGENT
            or (kind == CHANNEL and key == channel)
            or (kind == PLUGIN and owner is not None and key == owner)
        )
        if matches:
            best = RANK[kind] if best is None else max(best, RANK[kind])
    return best
