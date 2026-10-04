# ported from: src/shared/turn-log-context.ts
"""Context of the RUNNING turn, attached to every log line produced inside it.

Why: attaching ``turn_id`` with a child logger only covers modules that hold that logger. Measured on a
real turn: 11 lines with a turn id, 3 without, because ``web-fetch-tool`` creates its own logger. The
alternative, threading ``turn_id`` through function signatures, would pollute APIs such as
``search_web(query, opts)`` that have nothing to do with a "turn".

Forced deviation: Node ``AsyncLocalStorage`` becomes ``contextvars.ContextVar``, which also survives
``await`` and tasks and keeps two interleaved turns apart. ``logger.py`` reads it in a logging filter,
so no module needs to know anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class TurnLogContext:
    account_id: str
    thread_id: str
    turn_id: int


_storage: ContextVar[TurnLogContext | None] = ContextVar("pema_turn_log_context", default=None)


async def run_in_turn_log_context[T](context: TurnLogContext, fn: Callable[[], Awaitable[T]]) -> T:
    """Run ``fn`` in the turn context; every log inside (also after an await) carries these fields."""
    token = _storage.set(context)
    try:
        return await fn()
    finally:
        _storage.reset(token)


def current_turn_log_context() -> TurnLogContext | None:
    """Current context, or ``None`` outside a turn (startup, admin API, periodic cleanup). ``None`` and
    not an empty object so the logger adds nothing to those lines."""
    return _storage.get()
