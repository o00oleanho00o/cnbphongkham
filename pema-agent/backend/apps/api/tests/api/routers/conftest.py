"""Fixtures of the route tests under ``tests/api/routers``.

Knowledge base (package D3): the ``be_app`` database role - the role the API process really uses - behind a
FastAPI app with the knowledge router only (see ``pema.api.kb_test_support``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import httpx
import pytest

from pema.api.kb_test_support import KbApi, build_kb_api_app
from pema.core.db import ClinicDatabase
from pema.knowledge.kb_test_support import KbTestDatabase, database_url_for_tests
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore


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
