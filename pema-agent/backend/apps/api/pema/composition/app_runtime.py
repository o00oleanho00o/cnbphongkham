"""Composition root of the CRM application (branch feat/agent-v2). New module, no TS source.

The agent layer (agent engine, Zalo channels, scheduler, MCP, policy profiles, care agent, notifications) was
removed from this branch so a new agent service can be written from scratch. What is left is the clinic
platform: authentication, the CRM, the Inbox, live updates and the knowledge base. This module builds the few
objects those need and runs their background loops inside the API process:

* the database (``be_app``) and a Redis client for live updates (pub/sub and presence);
* the runtime settings snapshot (dashboard overrides of the tuning values, read by the CRM and retention);
* the knowledge base store and its ingest loop (the old worker process is gone; ``be_app`` may write
  ``agent.kb_*``), used by the staff guide and "Hỏi Pema";
* the CRM rules runner (staff tasks only; it no longer schedules messages);
* the retention run of scope ``clinic``.

A future agent service talks to the clinic through the HTTP API only; nothing here imports it.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI

from pema.api import dashboard_auth
from pema.api.routers import admin_crm_rules
from pema.clinic.actions import appointment_events
from pema.clinic.crm_rules.admin import SqlCrmRuleAdminService
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.composition.auth_bridge import resolve_staff_context
from pema.config.env import Settings
from pema.config.runtime_settings_store import (
    RuntimeSettingsSnapshot,
    SqlRuntimeSettingsStore,
    install_runtime_settings,
)
from pema.config.runtime_tuning_settings import get_tuning_int, install_tuning_provider
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.knowledge.embedding_client import EmbeddingSettings, OllamaEmbeddingClient
from pema.knowledge.kb_ingest_worker import TICK_MS, KbIngestWorker
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema.live.publisher import install_live_publisher, installed_live_publisher
from pema.live.services import LiveServices, build_redis_live_services
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner
from pema.retention.schedule import start_retention_loop
from pema.shared.logger import create_logger
from pema_contracts.installation import installation_clinic_id
from pema_contracts.knowledge import EmbeddingClient

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


def embedder_from_env() -> EmbeddingClient | None:
    config = EmbeddingSettings()
    if not config.enabled:
        log.info("embedding off: the knowledge base searches by keyword only")
        return None
    return OllamaEmbeddingClient(config)


@dataclass
class AppRuntime:
    settings: Settings
    db: ClinicDatabase
    redis_client: Any
    snapshot: RuntimeSettingsSnapshot
    knowledge: PostgresKnowledgeStore
    kb_worker: KbIngestWorker
    live: LiveServices

    async def clinic_id(self) -> UUID:
        return await get_installation_clinic_id(self.db)

    async def close(self) -> None:
        if installed_live_publisher() is self.live.publisher:
            install_live_publisher(None)
        await self.live.aclose()
        await self.snapshot.stop_refresh_loop()
        await self.redis_client.aclose()
        await self.db.dispose()


def build_app_runtime(
    settings: Settings,
    *,
    db: ClinicDatabase | None = None,
    redis_url: str | None = None,
    embedder: EmbeddingClient | Literal["env"] | None = "env",
    install_globals: bool = True,
) -> AppRuntime:
    """``db`` / ``redis_url`` / ``embedder`` are for the integration tests; production passes none."""
    database = db or ClinicDatabase(settings.database_url)
    redis_client = make_redis_client(redis_url or settings.redis_url)
    snapshot = RuntimeSettingsSnapshot(SqlRuntimeSettingsStore(database))
    if install_globals:
        install_runtime_settings(snapshot)
        install_tuning_provider(snapshot)
    chosen = embedder_from_env() if embedder == "env" else embedder
    knowledge = PostgresKnowledgeStore(database, embedder=chosen, data_dir=settings.data_dir)
    kb_worker = KbIngestWorker(database, embedder=chosen, data_dir=settings.data_dir)
    live = build_redis_live_services(redis_client, installation_clinic_id)
    if install_globals:
        install_live_publisher(live.publisher)
    return AppRuntime(
        settings=settings,
        db=database,
        redis_client=redis_client,
        snapshot=snapshot,
        knowledge=knowledge,
        kb_worker=kb_worker,
        live=live,
    )


def wire_app(app: FastAPI, rt: AppRuntime) -> None:
    """Fill the ``app.state`` entries and dependency overrides the routers look for."""
    state = app.state
    state.runtime = rt
    state.clinic_db = rt.db
    state.live = rt.live
    state.knowledge_store = rt.knowledge
    state.staff_context_resolver = resolve_staff_context
    # No channel sender until the new channel integration exists: staff messages stay queued.
    state.outbound_delivery = None
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
        await rt.snapshot.refresh(await get_installation_clinic_id(rt.db, verify=True))
        rt.snapshot.start_refresh_loop()
        rt.live.hub.start()
        loop = asyncio.get_running_loop()
        interval = rt.settings.crm_runner_interval_seconds
        if interval > 0:
            appointment_events.install_listener(lambda _change: self._crm_wake.set())
            self._tasks.append(loop.create_task(self._crm_loop(interval), name="crm-rules"))
        self._tasks.append(loop.create_task(self._kb_loop(), name="kb-ingest"))
        retention = start_retention_loop(
            RetentionRunner(
                rt.db,
                lambda: policy_from_settings(rt.settings, get_tuning_int),
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

    async def _kb_loop(self) -> None:
        """Boot sweep and first pass at once, then one pass per tick (what the old worker process did)."""
        worker = self._rt.kb_worker
        try:
            await worker.bat_dau_worker()
        except Exception as err:
            log.error("knowledge base boot pass failed", err=err)
        while not self._stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=TICK_MS / 1000)
            if self._stop.is_set():
                break
            try:
                await worker.chay_mot_vong_an_toan()
            except Exception as err:
                log.error("knowledge base pass failed", err=err)

    async def stop(self) -> None:
        appointment_events.install_listener(None)
        self._stop.set()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._rt.close()
