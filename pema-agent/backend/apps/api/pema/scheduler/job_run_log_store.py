# ported from: src/scheduler/job-run-log-store.ts
"""The ledger of WHAT HAPPENED at each run of a scheduled job (table ``agent.job_runs``).

Unlike ``jobs.last_status`` (which only tells the LAST run): a job that failed 5 times and ran fine the 6th
looks perfectly healthy without a separate log that tells every run - the exact reason Hermes split
``executions.py`` from ``jobs.py``. ``turn_id`` links to ``agent.usage`` for ``kind='agent'`` jobs, one click
to the Trace page when you need to know why a job answered wrong.

Forced deviations: Postgres + async; ``agent.job_runs`` has a real foreign key to ``agent.jobs`` with
``ON DELETE CASCADE`` (the original had a plain TEXT ``job_id`` and deleted the history by hand); two
columns added by migration ``s_0004`` for several workers: ``worker_id`` and ``heartbeat_at`` (a ``running``
row proves its worker is alive by refreshing the heartbeat, see ``interrupt_stale_runs``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import ClinicDatabase
from pema.scheduler.session_scope import use_session
from pema_contracts.scheduler import JobRunRecord, JobRunStatus

__all__ = ["FinishRunParams", "JobRunLogStore", "JobRunRecord", "JobRunStatus"]


@dataclass(frozen=True)
class FinishRunParams:
    status: JobRunStatus
    """Never ``running``: that is the state of an OPEN run."""
    detail: str = ""
    delivered_chars: int = 0
    turn_id: int | None = None


class JobRunLogStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def open_run(
        self,
        clinic_id: UUID,
        job_id: str,
        keep: int | None = None,
        *,
        worker_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> int:
        """Open 1 run (status='running') and get its id AT ONCE - before the job really runs.

        Keeps the ``keep`` most recent runs of each job - the same prune pattern as the history store and the
        memory store (cleaned right after the write, no separate cron). Done in ``open_run`` and not
        ``finish_run`` because ``open_run`` already has ``job_id`` - ``finish_run`` only receives the run id,
        looking up the job id would cost one more SELECT at every close."""
        keep_rows = keep if keep is not None else get_tuning_int("SCHEDULER_RUN_LOG_KEEP")
        async with use_session(self._db, clinic_id, session) as s:
            run_id = (
                await s.execute(
                    text(
                        "INSERT INTO agent.job_runs (clinic_id, job_id, status, worker_id) "
                        "VALUES (:clinic_id, :job_id, 'running', :worker_id) RETURNING id"
                    ),
                    {"clinic_id": clinic_id, "job_id": job_id, "worker_id": worker_id},
                )
            ).scalar_one()
            await s.execute(
                text(
                    """
                    DELETE FROM agent.job_runs
                     WHERE clinic_id = :clinic_id AND job_id = :job_id
                       AND id <= (SELECT id FROM agent.job_runs
                                   WHERE clinic_id = :clinic_id AND job_id = :job_id
                                   ORDER BY id DESC LIMIT 1 OFFSET :keep)"""
                ),
                {"clinic_id": clinic_id, "job_id": job_id, "keep": keep_rows},
            )
        return int(run_id)

    async def finish_run(
        self,
        clinic_id: UUID,
        run_id: int,
        params: FinishRunParams,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Close a run opened by ``open_run`` - also called on error (``detail`` is the error message)."""
        async with use_session(self._db, clinic_id, session) as s:
            await s.execute(
                text(
                    """
                    UPDATE agent.job_runs
                       SET status = :status, detail = :detail, delivered_chars = :delivered_chars,
                           turn_id = :turn_id, finished_at = now()
                     WHERE clinic_id = :clinic_id AND id = :id"""
                ),
                {
                    "clinic_id": clinic_id,
                    "id": run_id,
                    "status": params.status.value,
                    "detail": params.detail,
                    "delivered_chars": params.delivered_chars,
                    "turn_id": params.turn_id,
                },
            )

    async def list_runs(
        self, clinic_id: UUID, job_id: str, limit: int = 50, *, session: AsyncSession | None = None
    ) -> list[JobRunRecord]:
        """Run history of 1 job, newest first - for the history drawer of the dashboard."""
        async with use_session(self._db, clinic_id, session) as s:
            rows = (
                (
                    await s.execute(
                        text(
                            "SELECT id, job_id, turn_id, status, detail, delivered_chars, started_at, finished_at "  # noqa: E501
                            "FROM agent.job_runs WHERE clinic_id = :clinic_id AND job_id = :job_id "
                            "ORDER BY id DESC LIMIT :limit"
                        ),
                        {"clinic_id": clinic_id, "job_id": job_id, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return [
            JobRunRecord(
                id=r["id"],
                job_id=r["job_id"],
                turn_id=r["turn_id"],
                status=JobRunStatus(r["status"]),
                detail=r["detail"],
                delivered_chars=r["delivered_chars"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
            )
            for r in rows
        ]

    async def has_running_run(
        self, clinic_id: UUID, job_id: str, *, session: AsyncSession | None = None
    ) -> bool:
        """The job still has 1 run NOT CLOSED (status='running') - used to block "Run now" (the admin route)
        from colliding with a REAL dispatch in progress (a ``kind='agent'`` job can run longer than
        ``SCHEDULER_TICK_MS``). The same lesson as the header of this file: ``jobs.last_status`` is not
        enough, only the run log tells whether it is running."""
        async with use_session(self._db, clinic_id, session) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT 1 FROM agent.job_runs WHERE clinic_id = :clinic_id AND job_id = :job_id "
                        "AND status = 'running' LIMIT 1"
                    ),
                    {"clinic_id": clinic_id, "job_id": job_id},
                )
            ).first()
        return row is not None

    async def heartbeat(self, clinic_id: UUID, run_id: int) -> None:
        """Prove the worker of a ``running`` row is still alive (see ``interrupt_stale_runs``)."""
        async with self._db.session(clinic_id) as s:
            await s.execute(
                text(
                    "UPDATE agent.job_runs SET heartbeat_at = now() "
                    "WHERE clinic_id = :clinic_id AND id = :id AND status = 'running'"
                ),
                {"clinic_id": clinic_id, "id": run_id},
            )

    async def interrupt_stale_runs(
        self, clinic_id: UUID, stale_after_seconds: float, *, session: AsyncSession | None = None
    ) -> int:
        """Boot / periodic recovery: every row still ``running`` whose heartbeat is older than the stale
        window belongs to a worker that was killed mid-run -> ``interrupted``.

        The original did this for EVERY running row at boot because it was one process (no need to prove it by
        pid like Hermes, where 2 processes gateway/CLI fought over jobs.json). With several workers a live one
        may be in the middle of a long agent turn, so the heartbeat decides. Returns how many rows changed."""
        async with use_session(self._db, clinic_id, session) as s:
            result = await s.execute(
                text(
                    """
                    UPDATE agent.job_runs
                       SET status = 'interrupted', finished_at = now()
                     WHERE clinic_id = :clinic_id AND status = 'running'
                       AND heartbeat_at < now() - make_interval(secs => :stale)"""
                ),
                {"clinic_id": clinic_id, "stale": stale_after_seconds},
            )
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def last_started_at(self, clinic_id: UUID, job_id: str) -> datetime | None:
        """Start of the most recent run of the job, or ``None`` (diagnostics for the admin API)."""
        async with self._db.session(clinic_id) as s:
            value = (
                await s.execute(
                    text(
                        "SELECT started_at FROM agent.job_runs WHERE clinic_id = :clinic_id AND job_id = :job_id "  # noqa: E501
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"clinic_id": clinic_id, "job_id": job_id},
                )
            ).scalar()
        return value if isinstance(value, datetime) else None
