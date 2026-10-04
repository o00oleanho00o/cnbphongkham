# ported from: src/scheduler/delivery-attempt-store.ts
"""Count the CONSECUTIVE FAILED DELIVERY ATTEMPTS of one job - the durable column ``delivery_attempts`` on
``agent.jobs`` itself (not a separate table: this is state ATTACHED to the job, not history). Durable across
restarts to honour the invariant "a reminder that never managed to be sent is never counted as run" while
still having a STOPPING POINT - without this column a send that keeps failing (a long network outage) would
repeat forever, exactly the LLM-burning loop fixed by the daily cap (``scheduled_job_cap_guard``).

Forced deviation: the original did ``UPDATE`` then ``SELECT`` (two steps, fine in one sync process); here the
increment is ONE ``UPDATE ... RETURNING``, so two concurrent failures of the same job cannot both read ``1``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.scheduler.session_scope import use_session
from pema_contracts.scheduler import MAX_DELIVERY_ATTEMPTS

__all__ = ["MAX_DELIVERY_ATTEMPTS", "DeliveryAttemptStore"]
# MAX_DELIVERY_ATTEMPTS = 3: try at most 3 times before spending the run slot + writing a real 'error' for the
# dashboard. The constant lives in ``pema_contracts.scheduler`` (the contract documents the invariant) and is
# re-exported here under the original name.


class DeliveryAttemptStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def increment_delivery_attempts(
        self, clinic_id: UUID, job_id: str, *, session: AsyncSession | None = None
    ) -> int:
        """Increase the counter and return the NEW value - call it each time a run could not send ANYTHING.
        A job that does not exist is a no-op and returns 0 (no error)."""
        async with use_session(self._db, clinic_id, session) as s:
            value = (
                await s.execute(
                    text(
                        "UPDATE agent.jobs SET delivery_attempts = delivery_attempts + 1 "
                        "WHERE clinic_id = :clinic_id AND id = :id RETURNING delivery_attempts"
                    ),
                    {"clinic_id": clinic_id, "id": job_id},
                )
            ).scalar()
        return int(value) if value is not None else 0

    async def reset_delivery_attempts(
        self, clinic_id: UUID, job_id: str, *, session: AsyncSession | None = None
    ) -> None:
        """Back to 0 - call when the job just managed to send (even a part) or just spent its run slot after
        reaching ``MAX_DELIVERY_ATTEMPTS``."""
        async with use_session(self._db, clinic_id, session) as s:
            await s.execute(
                text("UPDATE agent.jobs SET delivery_attempts = 0 WHERE clinic_id = :clinic_id AND id = :id"),
                {"clinic_id": clinic_id, "id": job_id},
            )

    async def get_delivery_attempts(self, clinic_id: UUID, job_id: str) -> int:
        """Current value (diagnostics and tests)."""
        async with self._db.session(clinic_id) as s:
            value = (
                await s.execute(
                    text(
                        "SELECT delivery_attempts FROM agent.jobs WHERE clinic_id = :clinic_id AND id = :id"
                    ),
                    {"clinic_id": clinic_id, "id": job_id},
                )
            ).scalar()
        return int(value) if value is not None else 0
