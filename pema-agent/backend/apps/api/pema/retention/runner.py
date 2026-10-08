"""The retention job: delete expired data of the installation's clinic, in small batches, safely (new module,
no TS source).

Single tenant: one installation is one clinic, so there is no loop over clinics and no clinic argument; one
run is one ``scope``. Scope ``agent`` is what the worker may do (``agent.*`` rows and the image
files of the local volume, role ``agent_worker``); scope ``clinic`` is what the API process may do
(``clinic.*`` rows, role ``be_app``). Neither process gets a wider right than it had: see
``pema.retention.policy``.

Properties the tests pin down:

* **Only the installation's rows.** Every statement carries ``clinic_id = :clinic_id`` (the installation
  id, ``get_installation_clinic_id``); there is no row level security any more.
* **Small batches, bounded run.** ``batch_size`` rows per statement, at most ``MAX_BATCHES_PER_GROUP``
  batches per group per run; a group that hits the cap is reported as ``capped`` and the next run continues.
* **Idempotent.** A second run finds nothing more to delete; a crash between batches loses nothing but time.
* **Safe with two runners.** A session-level advisory lock per scope (one for the installation), taken with
  ``pg_try_advisory_lock`` on a connection of its own: the second runner does not wait, it reports
  ``skipped_locked``. (Rows are also picked with ``FOR UPDATE SKIP LOCKED``, so even without the lock two
  batches could never delete the same row twice.)
* **Dry run.** Counts what a real run would delete (``SELECT count(*)``), deletes nothing, writes no audit
  row, removes no file.
* **One audit row per real run and scope**, through ``clinic_agent.record_retention_run``: counters only, no
  PII. ``clinic.audit_log`` itself is never purged.
* **A failing group does not stop the others**; it is logged (no PII: the group name) and
  listed in ``ScopeReport.failed``.

"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.core.sql_util import affected_rows
from pema.retention import rules
from pema.retention.policy import RetentionPolicy, Scope
from pema.shared.logger import create_logger

log = create_logger("retention")

MAX_BATCHES_PER_GROUP = 1000
LOCK_NAMESPACE = 0x50454D41
"""First key of the advisory locks (``"PEMA"``); the scope is added so the two scopes never wait for each
other."""
LOCK_INSTALLATION_KEY = 0
"""Second key of the advisory locks: fixed, there is one clinic per installation (it used to be a hash of the
clinic id)."""
_SCOPE_ORDER = (Scope.AGENT, Scope.CLINIC)


class RunStatus(StrEnum):
    DONE = "done"
    SKIPPED_LOCKED = "skipped_locked"


@dataclass
class ScopeReport:
    """What one ``scope`` run did (or, in a dry run, would do)."""

    clinic_id: UUID
    scope: Scope
    dry_run: bool
    status: RunStatus = RunStatus.DONE
    counts: dict[str, int] = field(default_factory=dict[str, int])
    """Rows (or files) deleted per group; in a dry run, the number that WOULD be deleted."""
    capped: list[str] = field(default_factory=list[str])
    """Groups that hit the per-run batch cap; the next run continues."""
    disabled: list[str] = field(default_factory=list[str])
    """Groups kept forever by configuration (0 days, or no media volume)."""
    failed: list[str] = field(default_factory=list[str])

    def add(self, group: str, n: int) -> None:
        self.counts[group] = self.counts.get(group, 0) + n


@dataclass
class _Ctx:
    clinic_id: UUID
    policy: RetentionPolicy
    now: datetime
    report: ScopeReport

    @property
    def dry_run(self) -> bool:
        return self.report.dry_run

    def cutoff(self, days: int) -> datetime:
        return self.now - timedelta(days=days)


def lock_keys(scope: Scope) -> tuple[int, int]:
    """The two int4 keys of the advisory lock of ``scope`` (one lock per scope for the installation)."""
    return LOCK_NAMESPACE + _SCOPE_ORDER.index(scope), LOCK_INSTALLATION_KEY


class RetentionRunner:
    def __init__(
        self,
        db: ClinicDatabase,
        policy: RetentionPolicy | Callable[[], RetentionPolicy],
        *,
        scopes: Iterable[Scope] = (Scope.CLINIC,),
        now: Callable[[], datetime] | None = None,
        max_batches: int = MAX_BATCHES_PER_GROUP,
    ) -> None:
        self._db = db
        self._policy: Callable[[], RetentionPolicy] = (
            policy if callable(policy) else lambda: policy  # a static policy
        )
        wanted = frozenset(scopes)
        self._scopes = tuple(s for s in _SCOPE_ORDER if s in wanted)
        self._now: Callable[[], datetime] = now or (lambda: datetime.now(UTC))
        self._max_batches = max_batches

    @property
    def scopes(self) -> tuple[Scope, ...]:
        return self._scopes

    # ------------------------------------------------------------------------------------------ entry points
    async def run_all(self, *, dry_run: bool = False) -> list[ScopeReport]:
        """Every scope of this runner for the clinic of the installation (the periodic pass)."""
        reports: list[ScopeReport] = []
        for scope in self._scopes:
            try:
                reports.append(await self.run_scope(scope, dry_run=dry_run))
            except Exception as err:
                log.error("retention run failed", err=err, scope=scope.value)
                clinic_id = self._db.installation_clinic_id or UUID(int=0)
                reports.append(ScopeReport(clinic_id, scope, dry_run, failed=["run"]))
        return reports

    async def run_scope(self, scope: Scope, *, dry_run: bool = False) -> ScopeReport:
        clinic_id = await get_installation_clinic_id(self._db)
        report = ScopeReport(clinic_id, scope, dry_run)
        async with self._advisory_lock(scope) as acquired:
            if not acquired:
                report.status = RunStatus.SKIPPED_LOCKED
                log.info("retention skipped: another runner holds the lock", scope=scope.value)
                return report
            ctx = _Ctx(clinic_id, self._policy(), self._now(), report)
            started = time.monotonic()
            await self._run_clinic(ctx)
            if not dry_run:
                await self._audit(ctx)
            log.info(
                "retention dry run" if dry_run else "retention run",
                scope=scope.value,
                counts=report.counts,
                capped=report.capped,
                failed=report.failed,
                ms=round((time.monotonic() - started) * 1000),
            )
        return report

    # -------------------------------------------------------------------------------------------- scopes
    async def _run_clinic(self, ctx: _Ctx) -> None:
        p = ctx.policy
        for rule in rules.CLINIC_RULES:
            await self._step(ctx, rule.group, rule.days(p), self._rule(rule))
        await self._step(ctx, "link_attempts", p.link_attempt_days, self._link_attempts)

    async def _step(
        self,
        ctx: _Ctx,
        group: str,
        days: int,
        work: Callable[[_Ctx, str, datetime], Awaitable[None]],
    ) -> None:
        if days <= 0:
            ctx.report.disabled.append(group)
            return
        try:
            await work(ctx, group, ctx.cutoff(days))
        except Exception as err:
            log.error("retention group failed", err=err, group=group)
            ctx.report.failed.append(group)

    # ----------------------------------------------------------------------------------------------- groups
    def _rule(self, rule: rules.DeleteRule) -> Callable[[_Ctx, str, datetime], Awaitable[None]]:
        async def work(ctx: _Ctx, group: str, cutoff: datetime) -> None:
            params: dict[str, Any] = {"clinic_id": ctx.clinic_id, "cutoff": cutoff}
            if ctx.dry_run:
                async with self._db.session() as session:
                    ctx.report.add(
                        group, int((await session.execute(rules.count_sql(rule), params)).scalar() or 0)
                    )
                return
            statement = rules.delete_batch_sql(rule)
            await self._in_batches(
                ctx,
                group,
                lambda: self._delete_batch(statement, params, ctx.policy.batch_size),
            )

        return work

    async def _delete_batch(self, statement: Any, params: dict[str, Any], batch_size: int) -> int:
        async with self._db.session() as session:
            return affected_rows(await session.execute(statement, {**params, "batch": batch_size}))

    async def _in_batches(self, ctx: _Ctx, group: str, batch: Callable[[], Awaitable[int]]) -> None:
        """Run ``batch`` until it deletes fewer rows than ``batch_size`` (nothing left) or the cap is hit."""
        for _ in range(self._max_batches):
            n = await batch()
            ctx.report.add(group, n)
            if n < ctx.policy.batch_size:
                return
        ctx.report.capped.append(group)

    async def _link_attempts(self, ctx: _Ctx, group: str, cutoff: datetime) -> None:
        params: dict[str, Any] = {"cutoff": cutoff, "dry_run": ctx.dry_run}
        if ctx.dry_run:
            async with self._db.session() as session:
                ctx.report.add(
                    group,
                    int(
                        (await session.execute(rules.PURGE_LINK_ATTEMPTS, {**params, "batch": 1})).scalar()
                        or 0
                    ),
                )
            return

        async def batch() -> int:
            async with self._db.session() as session:
                value = (
                    await session.execute(
                        rules.PURGE_LINK_ATTEMPTS, {**params, "batch": ctx.policy.batch_size}
                    )
                ).scalar()
            return int(value or 0)

        await self._in_batches(ctx, group, batch)

    # ---------------------------------------------------------------------------------------------- audit
    async def _audit(self, ctx: _Ctx) -> None:
        """ONE summary row: the counters of the run, nothing else (the database function refuses text)."""
        counters = {
            **ctx.report.counts,
            "capped_groups": len(ctx.report.capped),
            "failed_groups": len(ctx.report.failed),
        }
        try:
            async with self._db.session() as session:
                await session.execute(
                    rules.AUDIT_RUN, {"scope": ctx.report.scope.value, "counts": json.dumps(counters)}
                )
        except Exception as err:
            log.error("retention audit row failed", err=err)
            ctx.report.failed.append("audit")

    # ---------------------------------------------------------------------------------------------- lock
    @asynccontextmanager
    async def _advisory_lock(self, scope: Scope) -> AsyncGenerator[bool]:
        """Session-level advisory lock of ``scope`` (the whole installation) on a connection of its own
        (autocommit, so it never sits ``idle in transaction``). ``False`` means another runner holds it; the
        caller must not run."""
        first, second = lock_keys(scope)
        keys = {"a": first, "b": second}
        conn = await self._db.engine.connect()
        try:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            acquired = bool((await conn.execute(text("SELECT pg_try_advisory_lock(:a, :b)"), keys)).scalar())
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        await conn.execute(text("SELECT pg_advisory_unlock(:a, :b)"), keys)
                    except Exception:
                        # Closing the connection releases a session lock; do not hand it back to the pool
                        # held.
                        await conn.invalidate()
        finally:
            await conn.close()
