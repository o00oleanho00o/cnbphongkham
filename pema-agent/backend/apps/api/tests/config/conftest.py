"""Fixtures of the D2 store tests that live in ``tests/config`` (account and agent stores).

Same as ``tests/conversation/conftest.py``: one throwaway Postgres database per session on the server of
``PEMA_TEST_DATABASE_URL`` (a SUPERUSER URL of a throwaway server), one fresh clinic per test. Tests that do not
use ``env`` need no database and always run.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

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
    """A clinic with NO agent and NO account (the store tests create what they need)."""
    clinic = ClinicEnv.create(pg_server, account_ids=(), default_agent=False)
    yield clinic
    await clinic.dispose()
