"""Test harness for the D2 admin routers (not a route module; no zalo-agent source).

Builds the REAL API router (``build_api_router``) on a bare FastAPI app with the real error handlers, wires
``app.state.admin_stores`` to the Postgres stores of a ``ClinicEnv`` and plays package B1's auth layer with
a tiny middleware: the headers ``x-test-clinic`` and ``x-test-permissions`` become
``request.state.clinic_id`` / ``request.state.permissions``. No header = not signed in. The cancel-batch
hook and the audit sink record what they receive so a test can assert on them.

Lives next to the routers (not under ``tests/``) because the test directories are imported in ``importlib``
mode and cannot share modules; nothing in production imports it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, Request, Response

from pema.api.errors import install_error_handlers
from pema.api.router import build_api_router
from pema.api.routers.admin_stores import AdminStores
from pema.config.account_store import AccountStoreImpl
from pema.config.agent_store import AgentStoreImpl
from pema.conversation.media_store import MediaStore
from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.store import PostgresConversationStore
from pema_contracts.common import JsonObject
from pema_contracts.roles import Permission

API = "/api/v1/admin"
ADMIN_AGENTS = Permission.ADMIN_AGENTS.value
ADMIN_AGENTS_AND_POLICY = f"{Permission.ADMIN_AGENTS.value},{Permission.ADMIN_POLICY.value}"


class Harness:
    """What a route test needs: the client, the clinic, the stores and the recorded side effects."""

    def __init__(self, env: ClinicEnv, app: FastAPI, client: httpx.AsyncClient, stores: AdminStores) -> None:
        self.env = env
        self.app = app
        self.client = client
        self.stores = stores
        self.cancelled: list[tuple[UUID, str, str]] = []
        self.audits: list[tuple[str, str, str, JsonObject]] = []

    def headers(self, permissions: str | None = ADMIN_AGENTS) -> dict[str, str]:
        out = {"x-test-clinic": str(self.env.clinic_id)}
        if permissions is not None:
            out["x-test-permissions"] = permissions
        return out


@asynccontextmanager
async def open_harness(env: ClinicEnv, media_root: Path) -> AsyncGenerator[Harness]:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(build_api_router())

    async def fake_auth(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        clinic = request.headers.get("x-test-clinic")
        if clinic:
            request.state.clinic_id = UUID(clinic)
        permissions = request.headers.get("x-test-permissions")
        if permissions is not None:
            request.state.permissions = frozenset(p for p in permissions.split(",") if p)
        return await call_next(request)

    app.middleware("http")(fake_auth)

    stores = AdminStores(
        agents=AgentStoreImpl(env.db),
        accounts=AccountStoreImpl(env.db),
        conversation=PostgresConversationStore(env.db, MediaStore(media_root)),
    )
    app.state.admin_stores = stores

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        harness = Harness(env, app, client, stores)

        async def cancel(clinic_id: UUID, account_id: str, thread_id: str) -> int:
            harness.cancelled.append((clinic_id, account_id, thread_id))
            return 2

        async def audit(
            clinic_id: UUID, action: str, entity_type: str, entity_id: str, details: JsonObject
        ) -> None:
            harness.audits.append((action, entity_type, entity_id, details))

        stores.cancel_pending_batch = cancel
        stores.audit = audit
        yield harness
