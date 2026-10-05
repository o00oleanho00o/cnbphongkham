"""Fixtures of the ingest-worker process tests (a real Postgres, role ``agent_worker``)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import pytest

from pema.core.db import ClinicDatabase
from pema.knowledge.kb_test_support import KbHarness, KbTestDatabase, database_url_for_tests


@pytest.fixture(scope="module")
def kb_database() -> Generator[KbTestDatabase]:
    url = database_url_for_tests()
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres (with pgvector) to test against")
    kb_db = KbTestDatabase.create(url)
    yield kb_db
    kb_db.dispose()


@pytest.fixture
async def kb(kb_database: KbTestDatabase) -> AsyncGenerator[KbHarness]:
    kb_database.clear_kb()
    db = ClinicDatabase(kb_database.worker_url)
    yield KbHarness(kb_database, db)
    await db.dispose()
