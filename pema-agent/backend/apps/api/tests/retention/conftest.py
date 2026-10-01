"""Fixtures of the retention tests: a throwaway database with the real Alembic history, one fresh clinic per test.

Set ``PEMA_TEST_DATABASE_URL`` to a SUPERUSER URL of a throwaway server (see ``tests/test_database.py``); without
it every test that uses ``env`` is skipped. Rows are seeded as the superuser (bypassing RLS) with explicit ages;
the code under test always runs as a runtime role: ``env.worker_db`` (``agent_worker``) for scope ``agent`` and
``env.db`` (``be_app``) for scope ``clinic``, so a missing grant fails the test instead of passing silently.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

from pema.conversation.pg_testing import ClinicEnv, PgTestServer
from pema.retention.pg_testing import Seed


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
def seed(env: ClinicEnv) -> Seed:
    return Seed(env)
