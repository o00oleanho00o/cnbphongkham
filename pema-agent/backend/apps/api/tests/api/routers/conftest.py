"""Fixtures of the route tests under ``tests/api/routers``.

* Package D2 (``admin_agents`` and ``admin_threads``): same database fixtures as ``tests/conversation/conftest.py``;
  ``h`` is the harness of ``pema.api.routers.admin_stores_testing`` (real router, real stores, fake auth middleware).
* Package D1: ``settings_env`` lives in ``pema.config.testing_settings``.
* Package C2: ``make_client`` builds a FastAPI app with the real router tree and the C2 services of ``build_test_rig``.
* Package D3 (knowledge base): the ``be_app`` database role - the role the API process really uses - behind a
  FastAPI app with the knowledge router only (see ``pema.api.kb_test_support``).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from pema.api.errors import install_error_handlers
from pema.api.kb_test_support import KbApi, build_kb_api_app
from pema.api.router import build_api_router
from pema.api.routers.admin_stores_testing import Harness, open_harness
from pema.channels.zalo_personal.service_testing import TestRig
from pema.config.testing_settings import settings_env
from pema.core.pg_testing import ClinicEnv, PgTestServer
from pema.core.db import ClinicDatabase
from pema.knowledge.kb_test_support import KbTestDatabase, database_url_for_tests
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PgTestServer]:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    server = PgTestServer.create(url)
    yield server
    server.drop()


@pytest.fixture
async def env(pg_server: PgTestServer) -> AsyncIterator[ClinicEnv]:
    clinic = ClinicEnv.create(pg_server)
    yield clinic
    await clinic.dispose()


@pytest.fixture
async def h(env: ClinicEnv, tmp_path: Path) -> AsyncIterator[Harness]:
    async with open_harness(env, tmp_path / "media-root") as harness:
        yield harness


@pytest.fixture(scope="module")
def kb_database() -> Generator[KbTestDatabase]:
    url = database_url_for_tests()
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres (with pgvector) to test against")
    kb_db = KbTestDatabase.create(url)
    yield kb_db
    kb_db.dispose()


@pytest.fixture
async def kb_api(kb_database: KbTestDatabase, tmp_path: Path) -> AsyncGenerator[KbApi]:
    kb_database.clear_kb()
    db = ClinicDatabase(kb_database.be_url)
    store = PostgresKnowledgeStore(db, data_dir=tmp_path)
    transport = httpx.ASGITransport(app=build_kb_api_app(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield KbApi(client, kb_database, store, tmp_path, uuid.uuid4())
    await db.dispose()


ClientFactory = Callable[[TestRig], httpx.AsyncClient]


@pytest.fixture
async def make_client() -> AsyncIterator[ClientFactory]:
    opened: list[httpx.AsyncClient] = []

    def make(rig: TestRig) -> httpx.AsyncClient:
        app = FastAPI()
        install_error_handlers(app)
        app.include_router(build_api_router())
        app.state.c2_services = rig.services
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        )
        opened.append(client)
        return client

    yield make
    for client in opened:
        await client.aclose()


__all__ = ["settings_env"]
