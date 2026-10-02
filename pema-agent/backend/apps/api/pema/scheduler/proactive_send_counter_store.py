# ported from: src/scheduler/proactive-send-counter-store.ts
"""CRUD of ``agent.proactive_send_counters``: counts the PROACTIVE messages already sent per (scope, local
day), durable across restarts. One store per table, like ``scheduled_job_store`` and ``job_run_log_store``.

NOT counted from ``job_runs``: that table is pruned to ``SCHEDULER_RUN_LOG_KEEP`` rows PER JOB every time a
run opens, so a dense job (``every 5 minutes`` = 288 runs a day) loses its morning ``ok`` rows within hours -
recounting would drop back to 0 in the middle of the day, even worse than an in-memory counter.

Forced deviations: the SQLite key ``(account_id, thread_id, day_key)`` becomes ``(clinic_id, scope_key,
day_key)``: ``scope_key`` is chosen by the policy profile (``account:thread`` in ``staff_assistant``,
``patient:account`` in ``patient_channel``, see ``PolicyHooks.proactive_cap``). ``try_reserve_slot`` and
``try_reserve_cap_notice`` are the atomic heart: ONE ``INSERT ... ON CONFLICT DO UPDATE ... WHERE ...
RETURNING`` (Postgres row lock on the conflicting row), which is exactly what SQLite's single writer gave for
free. Two workers racing for the last slot cannot both win.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.scheduler.session_scope import use_session


@dataclass(frozen=True)
class ProactiveCounter:
    count: int
    notice_sent: bool


class ProactiveSendCounterStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_proactive_counter(
        self, clinic_id: UUID, scope_key: str, day_key: str, *, session: AsyncSession | None = None
    ) -> ProactiveCounter:
        async with use_session(self._db, clinic_id, session) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT count, notice_sent FROM agent.proactive_send_counters "
                        "WHERE clinic_id = :clinic_id AND scope_key = :scope_key AND day_key = :day_key"
                    ),
                    {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key},
                )
            ).first()
        return ProactiveCounter(0, False) if row is None else ProactiveCounter(int(row[0]), bool(row[1]))

    async def add_proactive_send_count(
        self,
        clinic_id: UUID,
        scope_key: str,
        day_key: str,
        amount: int,
        keep_since_day_key: str | None = None,
    ) -> None:
        """Add ``amount`` MESSAGES (not "runs") to the counter of the day - creates the row if missing.
        ``amount`` must be the number of messages REALLY sent (``reply.sent_parts``): ``send_reply_in_parts``
        can cut one long answer into several messages.

        Prunes on the same beat as the write (like prune-on-write in the history store): deletes rows older
        than ``keep_since_day_key`` so the table does not bloat - the cap only needs to know TODAY."""
        if amount <= 0:
            return
        async with self._db.session() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO agent.proactive_send_counters AS c (clinic_id, scope_key, day_key, count)
                    VALUES (:clinic_id, :scope_key, :day_key, :amount)
                    ON CONFLICT (clinic_id, scope_key, day_key) DO UPDATE
                       SET count = c.count + EXCLUDED.count, updated_at = now()"""
                ),
                {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key, "amount": amount},
            )
            if keep_since_day_key:
                await s.execute(
                    text(
                        "DELETE FROM agent.proactive_send_counters "
                        "WHERE clinic_id = :clinic_id AND day_key < :keep"
                    ),
                    {"clinic_id": clinic_id, "keep": keep_since_day_key},
                )

    async def mark_proactive_cap_notice_sent(self, clinic_id: UUID, scope_key: str, day_key: str) -> None:
        """Mark the cap as ALREADY announced, once per day per scope - call only AFTER the notice was really
        sent."""
        async with self._db.session() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO agent.proactive_send_counters AS c (clinic_id, scope_key, day_key,
                    notice_sent)
                    VALUES (:clinic_id, :scope_key, :day_key, true)
                    ON CONFLICT (clinic_id, scope_key, day_key) DO UPDATE SET notice_sent = true"""
                ),
                {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key},
            )

    async def try_reserve_proactive_slot(
        self, clinic_id: UUID, scope_key: str, day_key: str, max_per_day: int
    ) -> bool:
        """Take EXACTLY 1 slot ATOMICALLY - one conditional upsert (``count < max``), not a read-then-write in
        2 steps. Blocks the race between 2 jobs of the SAME scope that become due together: split in 2 steps
        both could read the old ``count`` before the other wrote, but Postgres locks the conflicting row for
        this one statement so only 1 of the 2 gets the last slot.

        A row that NEVER existed (the first job of the day for this scope) always wins whatever ``max`` is:
        the INSERT branch writes ``count=1`` directly (the WHERE only applies to the UPDATE branch of the
        upsert), and ``max >= 1`` always holds (the bound of ``SCHEDULER_MAX_PROACTIVE_PER_DAY``). A policy
        that returns ``max_per_day <= 0`` ("never proactive") is answered here WITHOUT touching the table.

        Returns ``True`` if won (1 ALREADY ADDED to count), ``False`` if the cap is full (nothing touched).
        Call ``add_proactive_send_count`` afterwards to add the REST when the real ``sent_parts`` > 1, or
        ``refund_proactive_slot`` if in the end nothing could be sent."""
        if max_per_day <= 0:
            return False
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text(
                        """
                        INSERT INTO agent.proactive_send_counters AS c (clinic_id, scope_key, day_key, count)
                        VALUES (:clinic_id, :scope_key, :day_key, 1)
                        ON CONFLICT (clinic_id, scope_key, day_key) DO UPDATE
                           SET count = c.count + 1, updated_at = now()
                         WHERE c.count < :max
                        RETURNING c.count"""
                    ),
                    {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key, "max": max_per_day},
                )
            ).first()
        return row is not None

    async def refund_proactive_slot(self, clinic_id: UUID, scope_key: str, day_key: str) -> None:
        """Give back EXACTLY 1 slot taken by ``try_reserve_proactive_slot`` that in the end could not send
        anything. Floored at 0 - never negative."""
        async with self._db.session() as s:
            await s.execute(
                text(
                    """
                    UPDATE agent.proactive_send_counters
                       SET count = GREATEST(0, count - 1), updated_at = now()
                     WHERE clinic_id = :clinic_id AND scope_key = :scope_key AND day_key = :day_key"""
                ),
                {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key},
            )

    async def try_reserve_cap_notice(self, clinic_id: UUID, scope_key: str, day_key: str) -> bool:
        """Take the RIGHT to send the cap notice ATOMICALLY - one conditional upsert (``notice_sent =
        false``). Blocks the race between N jobs of the same scope blocked in the same tick: each would read
        ``notice_sent=false`` BEFORE another finished sending (the send path waits ``SCHEDULER_SEND_GAP_MS``,
        usually 20s) and think it was the first to hit the cap - N jobs became N identical notices, 20 seconds
        apart, exactly when the bot is trying to say "I will go quiet".

        Returns ``True`` if won (``notice_sent=true`` written NOW, BEFORE the real send), ``False`` if someone
        won first (or it was really sent earlier). On a failed send call ``revert_cap_notice`` to hand the
        right back to a later job/tick."""
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text(
                        """
                        INSERT INTO agent.proactive_send_counters AS c (clinic_id, scope_key, day_key,
                        notice_sent)
                        VALUES (:clinic_id, :scope_key, :day_key, true)
                        ON CONFLICT (clinic_id, scope_key, day_key) DO UPDATE
                           SET notice_sent = true, updated_at = now()
                         WHERE c.notice_sent = false
                        RETURNING 1"""
                    ),
                    {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key},
                )
            ).first()
        return row is not None

    async def revert_cap_notice(self, clinic_id: UUID, scope_key: str, day_key: str) -> None:
        """Hand back the right to announce the cap, taken by ``try_reserve_cap_notice`` but the send failed -
        a later job/tick still has a chance to retry."""
        async with self._db.session() as s:
            await s.execute(
                text(
                    """
                    UPDATE agent.proactive_send_counters SET notice_sent = false, updated_at = now()
                     WHERE clinic_id = :clinic_id AND scope_key = :scope_key AND day_key = :day_key"""
                ),
                {"clinic_id": clinic_id, "scope_key": scope_key, "day_key": day_key},
            )

    async def reset_all_proactive_counters(self, clinic_id: UUID) -> None:
        """Tests only - wipe the clinic's counters so each case starts from 0."""
        async with self._db.session() as s:
            await s.execute(
                text("DELETE FROM agent.proactive_send_counters WHERE clinic_id = :clinic_id"),
                {"clinic_id": clinic_id},
            )
