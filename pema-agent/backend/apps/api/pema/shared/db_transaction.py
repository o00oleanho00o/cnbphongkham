# ported from: src/shared/db-transaction.ts
"""Run work inside ONE database transaction.

Forced deviation (SQLite -> Postgres, sync -> async): the original hand-wrote ``BEGIN IMMEDIATE ...
COMMIT`` because ``node:sqlite`` has no ``db.transaction()``, and had to forbid async callbacks (COMMIT ran
synchronously right after the callback). With SQLAlchemy async the callback IS awaited, so the
``NotPromise`` type trick disappears; the invariants that remain are the original ones:

* a failing ``work`` rolls back and the ORIGINAL error is re-raised, whether or not the rollback
  itself succeeds. The caller needs to know WHY ``work`` failed, not why ROLLBACK failed, so an error
  during rollback is swallowed;
* nested transactions are not supported: the caller must not open this inside another open one. Use
  ``AsyncSession.begin_nested()`` (a SAVEPOINT) explicitly when that is really needed.

Postgres replaces the single-process invariants of the original ("claim a job", "count a cap") with
atomic SQL (``UPDATE ... RETURNING`` / ``INSERT ... ON CONFLICT``) and Redis locks; this helper is for
multi-statement work that must commit together.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Protocol


class TransactionalSession(Protocol):
    """The part of ``AsyncSession`` this helper uses (so tests need no database)."""

    async def begin(self) -> object: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


async def in_transaction[T](session: TransactionalSession, work: Callable[[], Awaitable[T]]) -> T:
    """``trongGiaoDich``: BEGIN, run ``work``, COMMIT; on error ROLLBACK and re-raise the original."""
    await session.begin()
    try:
        result = await work()
        await session.commit()
    except BaseException:
        with contextlib.suppress(Exception):  # keep the original error (see docstring)
            await session.rollback()
        raise
    return result
