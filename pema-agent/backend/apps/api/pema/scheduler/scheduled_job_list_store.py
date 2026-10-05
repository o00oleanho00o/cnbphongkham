# ported from: src/scheduler/scheduled-job-list-store.ts
"""Read jobs for the DASHBOARD - list BY ACCOUNT (every thread), unlike ``list_jobs_for_thread``
(``scheduled_job_store``) which always needs both the account id and the thread id because that is the scope
of the TOOL (a conversation only sees the jobs of that very conversation). The dashboard is the admin screen
(staff with a session, no notion of "each thread has a different owner") so it needs a MERGED view of every
thread of one account, or every account of the clinic (``account_id`` None) - the pattern of ``list_threads``
of the thread store used by the Sessions page.

Forced deviation: the original used an empty ``accountId`` string for "all accounts"; here it is ``None``.
The clinic filter is an explicit ``clinic_id`` predicate (the installation id).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase
from pema.scheduler.scheduled_job_record import JOB_COLUMNS, row_to_job
from pema_contracts.scheduler import ScheduledJob


class ScheduledJobListStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def list_jobs_for_account(self, clinic_id: UUID, account_id: str | None) -> list[ScheduledJob]:
        """``account_id=None`` (or empty) = every account (the dashboard shows the mixed view by default)."""
        async with self._db.session() as s:
            if account_id:
                rows = (
                    (
                        await s.execute(
                            text(
                                f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                                "WHERE clinic_id = :clinic_id AND account_id = :account_id "
                                "ORDER BY created_at DESC, id"
                            ),
                            {"clinic_id": clinic_id, "account_id": account_id},
                        )
                    )
                    .mappings()
                    .all()
                )
            else:
                rows = (
                    (
                        await s.execute(
                            text(
                                f"SELECT {JOB_COLUMNS} FROM agent.jobs "  # noqa: S608 - constant column list
                                "WHERE clinic_id = :clinic_id ORDER BY created_at DESC, id"
                            ),
                            {"clinic_id": clinic_id},
                        )
                    )
                    .mappings()
                    .all()
                )
        return [row_to_job(r) for r in rows]
