"""Installs the real objects into the FastAPI app (package G, no TS source).

One function, ``wire_api``, sets everything the routers look for: ``app.state`` entries, dependency overrides
and the tools-admin services. Every seam is documented in the docstring of the router that reads it; this file
only fills them from the ``Runtime`` and from B1's session (``auth_bridge``).

``ApiLifecycle`` starts and stops the API-side background work: the bot accounts of this process (send-only or
listening, see ``intake``), the personal accounts behind the bridge when the flag is on, the batcher recovery,
the KB availability snapshot, the settings refresh loop and the CRM rule runner. The runner lives HERE and not
in the worker because the rule store reads ``clinic.*`` and only ``be_app`` may (CONTRACTS decision 7). The
retention run of scope ``clinic`` (messages of closed conversations, expired sessions and link codes) lives
here
for the same reason; the worker runs scope ``agent`` (``pema.retention``).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request

from pema.api import dashboard_auth
from pema.api.mcp_route_guards import McpAdminContext, get_mcp_admin_context
from pema.api.routers import admin_crm_rules, admin_model, admin_usage
from pema.api.routers.admin_stores import AdminStores
from pema.api.routers.admin_tools import ToolsAdminServices, install_tools_admin_services
from pema.channels.zalo_personal.audit_writer import SqlAuditSink
from pema.clinic.actions import appointment_events
from pema.clinic.crm_rules.admin import SqlCrmRuleAdminService
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.composition.adapters import StaticChannelCapabilities
from pema.composition.auth_bridge import (
    clinic_of,
    current_staff_context,
    require_permission,
    resolve_staff_context,
)
from pema.composition.intake import BotStack, PersonalStack
from pema.composition.outbound import RegistryOutboundDelivery, install_identity_queue
from pema.composition.runtime import Runtime
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.agent_trace_store import PgTraceReader
from pema.core.db import get_installation_clinic_id
from pema.middleware.thread_run_chain import ThreadRef
from pema.policy.identity_admin import PolicyAdminService
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner
from pema.retention.schedule import start_retention_loop
from pema.scheduler.admin_service import ScheduleAdminService
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.common import JsonObject
from pema_contracts.installation import installation_clinic_id
from pema_contracts.roles import ActorType, Permission

log = create_logger("composition.api")

CRM_NUDGE_SETTLE_S = 2.0
"""After an appointment changed, wait this long before the rules run, so a burst (a morning of check-ins)
becomes one run."""


def _audit_context(clinic_id: UUID) -> ActionContext:
    """The signed-in staff member of the request when there is one, else the system."""
    staff = current_staff_context()
    if staff is not None and staff.clinic_id == clinic_id:
        return staff
    return ActionContext(clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.UI)


def wire_api(app: FastAPI, rt: Runtime, bot: BotStack, personal: PersonalStack) -> None:
    audit_sink = SqlAuditSink(rt.db)

    async def audit_row(
        clinic_id: UUID, action: str, entity_type: str, entity_id: str, details: JsonObject
    ) -> None:
        await audit_sink.record(_audit_context(clinic_id), action, entity_type, entity_id, dict(details))

    async def cancel_pending_batch(clinic_id: UUID, account_id: str, thread_id: str) -> int:
        return await bot.batcher.huy_batch_cua_thread(ThreadRef(clinic_id, account_id, thread_id).key)

    state = app.state
    state.runtime = rt
    state.clinic_db = rt.db
    state.live = rt.live
    identity_queue = install_identity_queue(rt.db, rt.redis_client)
    state.outbound_delivery = RegistryOutboundDelivery(
        rt.accounts, rt.channels, rt.conversation, identity_queue
    )
    state.admin_stores = AdminStores(
        agents=rt.agents,
        accounts=rt.accounts,
        conversation=rt.conversation,
        cancel_pending_batch=cancel_pending_batch,
        audit=audit_row,
    )
    state.knowledge_store = rt.knowledge
    state.schedule_admin = ScheduleAdminService(rt.scheduler_deps, rt.scheduler)
    state.zalo_bot_webhook = bot.webhook
    state.bot_account_admin = bot.admin
    state.staff_context_resolver = resolve_staff_context
    state.c2_services = personal.services
    state.policy_admin = PolicyAdminService(db=rt.db, accounts=rt.accounts)
    state.bot_stack = bot
    state.personal_stack = personal

    # B2: the rule admin service and the session of B1
    rules_admin = SqlCrmRuleAdminService(rt.db)
    app.dependency_overrides[admin_crm_rules.get_action_context] = dashboard_auth.action_context
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: rules_admin

    # D1: model settings and usage (the permission is checked by ``StaffSessionMiddleware``)
    async def clinic_id_of_request(request: Request) -> UUID:
        return clinic_of(request)

    async def model_audit(request: Request) -> admin_model.AuditSink:
        clinic_id = clinic_of(request)

        async def write(action: str, fields: object) -> None:
            names = sorted(str(f) for f in fields) if isinstance(fields, (list, tuple, set)) else []  # type: ignore[arg-type]
            await audit_sink.record(
                _audit_context(clinic_id), action, "runtime_settings", None, {"fields": names}
            )

        return write

    app.dependency_overrides[admin_model.provide_clinic_id] = clinic_id_of_request
    app.dependency_overrides[admin_model.provide_audit] = model_audit
    app.dependency_overrides[admin_usage.provide_clinic_id] = clinic_id_of_request
    app.dependency_overrides[admin_usage.provide_accounts] = lambda: rt.accounts
    app.dependency_overrides[admin_usage.provide_usage] = lambda: rt.conversation
    traces = PgTraceReader(rt.db)
    app.dependency_overrides[admin_usage.provide_traces] = lambda: traces
    app.dependency_overrides[admin_usage.provide_channels] = lambda: rt.channels
    log_dir = rt.settings.log_dir
    enabled = rt.settings.log_file_enabled
    app.dependency_overrides[admin_usage.provide_log_source] = lambda: admin_usage.LogSource(
        log_dir=Path(log_dir), enabled=enabled
    )

    # D5: MCP admin context
    async def mcp_context(request: Request) -> McpAdminContext:
        require_permission(request, Permission.ADMIN_MCP)
        return McpAdminContext(
            clinic_id=clinic_of(request),
            servers=rt.mcp.servers,
            bindings=rt.mcp.bindings,
            manager=rt.mcp.manager,
        )

    app.dependency_overrides[get_mcp_admin_context] = mcp_context

    # D4: tools admin
    install_tools_admin_services(
        ToolsAdminServices(
            registry=rt.tool_registry,
            accounts=rt.accounts,
            agents=rt.agents,
            channels=StaticChannelCapabilities(),
            clinic_id=installation_clinic_id,
        )
    )


class ApiLifecycle:
    """Start and stop of the API-side background work."""

    def __init__(self, app: FastAPI, rt: Runtime, bot: BotStack, personal: PersonalStack) -> None:
        self._app = app
        self._rt = rt
        self._bot = bot
        self._personal = personal
        self._crm_task: asyncio.Task[None] | None = None
        self._crm_wake = asyncio.Event()
        self._retention_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        rt = self._rt
        # Settings of the clinic first: the tuning provider reads this snapshot, so the accounts and the
        # batcher below already see the overrides saved on the dashboard. ``verify=True``: a
        # ``PEMA_CLINIC_ID`` that is not the clinic of this database stops the start-up.
        await rt.snapshot.refresh(await get_installation_clinic_id(rt.db, verify=True))
        rt.snapshot.start_refresh_loop()
        rt.kb_availability.start()
        rt.live.hub.start()
        recovered = await self._bot.batcher.recover()
        log.info("batcher recovered", batches=recovered)
        started = await self._bot.manager.start_all()
        log.info("bot accounts started", running=started)
        if rt.settings.zalo_personal_enabled:
            await self._personal.manager.start_all_accounts()
        interval = rt.settings.crm_runner_interval_seconds
        if interval > 0:
            appointment_events.install_listener(lambda _change: self._crm_wake.set())
            self._crm_task = asyncio.get_running_loop().create_task(self._crm_loop(interval))
        self._retention_task = start_retention_loop(
            RetentionRunner(
                rt.db,
                lambda: policy_from_settings(rt.settings, get_tuning_int),
                scopes=(Scope.CLINIC,),
            ),
            interval_seconds=rt.settings.retention_interval_seconds,
        )

    async def _crm_loop(self, interval_s: int) -> None:
        runner = CrmRulesRunner(SqlCrmRuleStore(self._rt.db), self._rt.scheduler)
        while True:
            try:
                report = await runner.run_clinic(await self._rt.clinic_id())
                log.info("crm rules ran", tasks=report.tasks_created, jobs=report.jobs_created)
            except Exception as err:
                log.error("crm rules run failed", err=err)
            # Package U, step U2: a changed appointment (missed, arrived, cancelled) wakes the loop early.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._crm_wake.wait(), timeout=interval_s)
            if self._crm_wake.is_set():
                await asyncio.sleep(CRM_NUDGE_SETTLE_S)
                self._crm_wake.clear()

    async def stop(self) -> None:
        appointment_events.install_listener(None)
        crm, self._crm_task = self._crm_task, None
        if crm is not None:
            crm.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await crm
        retention, self._retention_task = self._retention_task, None
        if retention is not None:
            retention.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await retention
        await self._bot.manager.stop_all()
        if self._rt.settings.zalo_personal_enabled:
            await self._personal.manager.stop_all_accounts()
        await self._personal.bridge.aclose()
        await self._rt.close()
        install_tools_admin_services(None)
