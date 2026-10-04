"""Test support of the knowledge-base route tests (``tests/api/routers``). NOT used by running code.

``KbApi`` bundles an ASGI client on a FastAPI app that holds ONLY the knowledge router, the throwaway Postgres
and the store behind it. ``build_kb_api_app`` installs a stand-in for the session authentication of
package B1:
a middleware that puts ``clinic_id`` / ``user_id`` / ``role`` / ``permissions`` into ``request.state`` from
``x-test-*`` headers, which is exactly the context ``lay_ngu_canh_kb`` expects.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response

from pema.api.deps import API_PREFIX
from pema.api.errors import install_error_handlers
from pema.api.routers import admin_kb
from pema.knowledge.kb_test_support import KbTestDatabase
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema_contracts.roles import Permission

TOAN_QUYEN = f"{Permission.KB_READ.value},{Permission.KB_MANAGE.value}"


@dataclass
class KbApi:
    client: httpx.AsyncClient
    kb_database: KbTestDatabase
    store: PostgresKnowledgeStore
    data_dir: Path
    user_id: uuid.UUID

    def headers(
        self, *, role: str = "manager", permissions: str = TOAN_QUYEN, clinic: uuid.UUID | None = None
    ) -> dict[str, str]:
        return {
            "x-test-clinic": str(clinic or self.kb_database.clinic_id),
            "x-test-user": str(self.user_id),
            "x-test-role": role,
            "x-test-perms": permissions,
        }

    @property
    def base(self) -> str:
        return f"{API_PREFIX}/admin/kb"


def build_kb_api_app(store: PostgresKnowledgeStore) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_kb.router, prefix=API_PREFIX)
    app.state.knowledge_store = store

    @app.middleware("http")
    async def gia_lap_xac_thuc(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        h = request.headers
        if "x-test-clinic" in h:
            request.state.clinic_id = uuid.UUID(h["x-test-clinic"])
            request.state.user_id = uuid.UUID(h["x-test-user"])
            request.state.role = h["x-test-role"]
            request.state.permissions = [p for p in h["x-test-perms"].split(",") if p]
        return await call_next(request)

    return app
