"""Composition root of the CRM application (branch feat/agent-v2). New module, no TS source.

The agent layer (agent engine, Zalo channels, scheduler, MCP, policy profiles, care agent, notifications) was
removed from this branch so a new agent service can be written from scratch. What is left is the clinic
platform: authentication, the CRM, the Inbox, live updates and the staff guide. This module builds the few
objects those need and runs their background loops inside the API process:

* the database (``be_app``) and a Redis client for live updates (pub/sub);
* the CRM rules runner (staff tasks only; it no longer schedules messages);
* the retention run of scope ``clinic``.

The agent service never reaches this database; of the API it reaches only ``/agent-gateway``, through
crm-signer, and it hears of changes through the ``agent-events`` worker (.claude/rules/agent-crm-boundary.md,
L2).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import FastAPI

from pema.api import dashboard_auth
from pema.api.routers import admin_crm_rules
from pema.clinic.actions import agent_events, appointment_events
from pema.clinic.crm_rules.admin import SqlCrmRuleAdminService
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.composition.agent_events_worker import AgentEventWorker
from pema.config.env import Settings
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.live.publisher import install_live_publisher, installed_live_publisher
from pema.live.services import LiveServices, build_redis_live_services
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner
from pema.retention.schedule import start_retention_loop
from pema.shared.logger import create_logger
from pema_contracts.installation import installation_clinic_id

log = create_logger("composition.app")

REDIS_SOCKET_TIMEOUT_S = 5.0
CRM_NUDGE_SETTLE_S = 2.0
"""After an appointment changed, wait this long before the rules run, so a burst (a morning of check-ins)
becomes one run."""


def make_redis_client(url: str) -> Any:
    from redis.asyncio import Redis  # local import: only the processes that use Redis load it

    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        url, decode_responses=True, socket_timeout=REDIS_SOCKET_TIMEOUT_S, health_check_interval=30
    )


@dataclass
class AppRuntime:
    settings: Settings
    db: ClinicDatabase
    redis_client: Any
    live: LiveServices

    async def clinic_id(self) -> UUID:
        return await get_installation_clinic_id(self.db)

    async def close(self) -> None:
        if installed_live_publisher() is self.live.publisher:
            install_live_publisher(None)
        await self.live.aclose()
        await self.redis_client.aclose()
        await self.db.dispose()


def build_app_runtime(
    settings: Settings,
    *,
    db: ClinicDatabase | None = None,
    redis_url: str | None = None,
    install_globals: bool = True,
) -> AppRuntime:
    """``db`` / ``redis_url`` are for the integration tests; production passes none."""
    database = db or ClinicDatabase(settings.database_url)
    redis_client = make_redis_client(redis_url or settings.redis_url)
    live = build_redis_live_services(redis_client, installation_clinic_id)
    if install_globals:
        install_live_publisher(live.publisher)
    return AppRuntime(
        settings=settings,
        db=database,
        redis_client=redis_client,
        live=live,
    )


def wire_app(app: FastAPI, rt: AppRuntime) -> None:
    """Fill the ``app.state`` entries and dependency overrides the routers look for."""
    state = app.state
    state.runtime = rt
    state.clinic_db = rt.db
    state.live = rt.live
    rules_admin = SqlCrmRuleAdminService(rt.db)
    app.dependency_overrides[admin_crm_rules.get_action_context] = dashboard_auth.action_context
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: rules_admin


class AppLifecycle:
    """Start and stop of the background work of the API process."""

    def __init__(self, rt: AppRuntime) -> None:
        self._rt = rt
        self._tasks: list[asyncio.Task[None]] = []
        self._crm_wake = asyncio.Event()
        self._stop = asyncio.Event()

    async def start(self) -> None:
        rt = self._rt
        # ``verify=True``: a ``PEMA_CLINIC_ID`` that is not the clinic of this database stops the start-up.
        await get_installation_clinic_id(rt.db, verify=True)
        rt.live.hub.start()
        loop = asyncio.get_running_loop()
        interval = rt.settings.crm_runner_interval_seconds
        if interval > 0:
            appointment_events.install_listener(lambda _change: self._crm_wake.set())
            self._tasks.append(loop.create_task(self._crm_loop(interval), name="crm-rules"))
        events_url = (rt.settings.agent_events_url or "").strip()
        if events_url:
            worker = AgentEventWorker(rt.db, events_url)
            agent_events.set_waker(worker.wake)
            self._tasks.append(loop.create_task(worker.run(), name="agent-events"))
        retention = start_retention_loop(
            RetentionRunner(
                rt.db,
                lambda: policy_from_settings(rt.settings),
                scopes=(Scope.CLINIC,),
            ),
            interval_seconds=rt.settings.retention_interval_seconds,
        )
        if retention is not None:
            self._tasks.append(retention)

    async def _crm_loop(self, interval_s: int) -> None:
        runner = CrmRulesRunner(SqlCrmRuleStore(self._rt.db))
        while not self._stop.is_set():
            try:
                report = await runner.run_clinic(await self._rt.clinic_id())
                log.info("crm rules ran", tasks=report.tasks_created)
            except Exception as err:
                log.error("crm rules run failed", err=err)
            # A changed appointment (missed, arrived, cancelled) wakes the loop early.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._crm_wake.wait(), timeout=interval_s)
            if self._crm_wake.is_set():
                await asyncio.sleep(CRM_NUDGE_SETTLE_S)
                self._crm_wake.clear()

    async def stop(self) -> None:
        appointment_events.install_listener(None)
        agent_events.set_waker(None)
        self._stop.set()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._rt.close()
