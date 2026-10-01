"""Fixtures of the route tests of package D2 (``admin_agents`` and ``admin_threads``).

Same database fixtures as ``tests/conversation/conftest.py``; ``h`` is the harness of
``pema.api.routers.admin_stores_testing`` (real router, real stores, fake auth middleware).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from pema.api.routers.admin_stores_testing import Harness, open_harness
from pema.conversation.pg_testing import ClinicEnv, PgTestServer


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
