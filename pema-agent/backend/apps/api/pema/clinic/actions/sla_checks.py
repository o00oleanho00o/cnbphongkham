"""Durable "look at this routing request again at T" (package O, step O3). New module, no zalo-agent original.

Package M's routing asks ``SlaScheduler.schedule_check(SlaCheck)`` after it notified a candidate; when the
time
comes somebody must call ``RoutingService.on_sla_expired(request_id, idx)``. These functions are the storage
of that promise (``clinic.sla_check``):

* ``schedule``: insert, deduplicated by ``dedupe_key`` (a repeat of the same check changes nothing);
* ``claim_due``: pending checks that are due, taken with ``FOR UPDATE SKIP LOCKED`` and a lease;
* ``finish``: ``done`` after the handler ran; on a failure the check stays ``pending`` for a later retry
  (``attempts`` + 1, ``retry_at``) and becomes ``failed`` after ``MAX_ATTEMPTS``. "Never ran" is never turned
  into "ran": a check is ``done`` only after its handler returned.

No permission and no audit row: this is plumbing of the system actor (the routing round itself is audited by
package M); the rows carry ids and numbers only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase

MAX_ATTEMPTS = 5
LEASE_S = 120
RETRY_BASE_S = 30


@dataclass(frozen=True)
class DueCheck:
    id: UUID
    request_id: UUID
    idx: int
    due_at: datetime
    attempts: int


_INSERT_SQL = text("""
    INSERT INTO clinic.sla_check (clinic_id, request_id, idx, due_at, dedupe_key)
    VALUES (:clinic_id, :request_id, :idx, :due_at, :dedupe_key)
    ON CONFLICT (clinic_id, dedupe_key) DO NOTHING""")


async def schedule(
    db: ClinicDatabase, clinic_id: UUID, *, request_id: UUID, idx: int, due_at: datetime, dedupe_key: str
) -> None:
    async with db.session() as session:
        await session.execute(
            _INSERT_SQL,
            {
                "clinic_id": clinic_id,
                "request_id": request_id,
                "idx": idx,
                "due_at": due_at,
                "dedupe_key": dedupe_key,
            },
        )


_CLAIM_SQL = text("""
    UPDATE clinic.sla_check c SET lease_until = :until
     WHERE c.clinic_id = :clinic_id AND c.id IN (
        SELECT id FROM clinic.sla_check
         WHERE clinic_id = :clinic_id AND state = 'pending' AND due_at <= :now
           AND (lease_until IS NULL OR lease_until < :now)
         ORDER BY due_at LIMIT :limit FOR UPDATE SKIP LOCKED)
 RETURNING c.id, c.request_id, c.idx, c.due_at, c.attempts""")


async def claim_due(
    db: ClinicDatabase, clinic_id: UUID, now: datetime, *, limit: int = 20, lease_s: int = LEASE_S
) -> list[DueCheck]:
    async with db.session() as session:
        rows = (
            await session.execute(
                _CLAIM_SQL,
                {
                    "clinic_id": clinic_id,
                    "now": now,
                    "until": now + timedelta(seconds=lease_s),
                    "limit": limit,
                },
            )
        ).all()
    return [
        DueCheck(id=row.id, request_id=row.request_id, idx=row.idx, due_at=row.due_at, attempts=row.attempts)
        for row in rows
    ]


_DONE_SQL = text(
    "UPDATE clinic.sla_check SET state = 'done', lease_until = NULL WHERE clinic_id = :c AND id = :i"
)
_RETRY_SQL = text("""
    UPDATE clinic.sla_check
       SET state = :state, attempts = attempts + 1, lease_until = NULL, due_at = :due_at
     WHERE clinic_id = :c AND id = :i""")


async def finish(db: ClinicDatabase, clinic_id: UUID, check: DueCheck, *, ok: bool, now: datetime) -> bool:
    """Record the end of one run. Returns ``True`` when the check is finished (done, or given up), ``False``
    when it stays pending for another try."""
    async with db.session() as session:
        if ok:
            await session.execute(_DONE_SQL, {"c": clinic_id, "i": check.id})
            return True
        attempts = check.attempts + 1
        gave_up = attempts >= MAX_ATTEMPTS
        await session.execute(
            _RETRY_SQL,
            {
                "c": clinic_id,
                "i": check.id,
                "state": "failed" if gave_up else "pending",
                "due_at": now + timedelta(seconds=RETRY_BASE_S * (2 ** (attempts - 1))),
            },
        )
        return gave_up
