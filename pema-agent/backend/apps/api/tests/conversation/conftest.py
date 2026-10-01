"""Fixtures of the D2 store tests: one throwaway Postgres database per session, one fresh clinic per test.

Set ``PEMA_TEST_DATABASE_URL`` to a SUPERUSER URL of a throwaway server (see ``tests/test_database.py``); the
fixtures create and drop their own database on it. Without the variable every test that uses ``env`` is
skipped (tests that need no database still run).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
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


@pytest.fixture(autouse=True)
def _reset_tuning() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(StaticTuningProvider({}))
    yield
    reset_tuning_provider()
