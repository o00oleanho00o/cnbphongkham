"""The checks every graph of the harness passes when it is built: a case's (``agentcore.cases``) and a turn's
(``agentcore.turns``). Ids are unique and valid, edges name real nodes, a counter has a cap and is a field of
the state, a node has at most one error edge and it has no condition, and an edge that goes back (to a node
listed at or before its source) carries a counter, so no loop runs forever (rule H3)."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any, Final, Protocol

NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")


class _Edge(Protocol):
    @property
    def src(self) -> str: ...

    @property
    def dst(self) -> str: ...

    @property
    def when(self) -> Any: ...

    @property
    def counter(self) -> str | None: ...

    @property
    def on(self) -> str: ...


def check_graph(
    where: str,
    order: Sequence[str],
    start: str,
    edges: Sequence[_Edge],
    counters: Mapping[str, int],
    fields: Collection[str],
) -> None:
    """Raises ``ValueError`` naming ``where`` (``case follow_up``) at the first rule broken. ``order`` is the
    node ids as declared; ``fields`` the state's field names."""
    if not order or len(set(order)) != len(order):
        raise ValueError(f"{where}: node ids must be present and unique")
    bad_ids = [i for i in order if not NAME.fullmatch(i)]
    if bad_ids:
        raise ValueError(f"{where}: invalid node id(s) {', '.join(bad_ids)}")
    if start not in order:
        raise ValueError(f"{where}: start node {start} is not a node")
    unknown = [name for name in counters if name not in fields]
    if unknown:
        raise ValueError(f"{where}: counter(s) not in the state: {', '.join(unknown)}")
    failing = [e.src for e in edges if e.on == "error"]
    if len(set(failing)) != len(failing):
        raise ValueError(f"{where}: one error edge per node at most")
    for edge in edges:
        at = f"{where}, edge {edge.src} -> {edge.dst}"
        if edge.on == "error" and edge.when is not None:
            raise ValueError(f"{at}: an error edge has no condition")
        if edge.src not in order or edge.dst not in order:
            raise ValueError(f"{at}: names a node that is not there")
        if edge.counter is not None and edge.counter not in counters:
            raise ValueError(f"{at}: counter {edge.counter} has no cap")
        if order.index(edge.dst) <= order.index(edge.src) and edge.counter is None:
            raise ValueError(f"{at}: goes back, so it needs a counter with a cap")
