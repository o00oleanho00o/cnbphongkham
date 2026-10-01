"""Fixtures of the MCP tests.

* ``bundle`` runs a test against BOTH implementations of the stores: ``memory`` (``InMemoryMcpStore``) and ``pg``
  (``PgMcpServerStore`` + ``PgMcpPolicyStore`` on a throwaway Postgres, skipped without
  ``PEMA_TEST_DATABASE_URL``). One test body, two stores: the in-memory fake is only trusted because the same
  assertions hold on Postgres. Like ``tests/test_database.py`` the Postgres fixture DROPS every Pema schema and
  re-runs the alembic history, so point the variable at a throwaway database only.
* the secret cipher key and the tuning provider are reset around every test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pema.config import env as env_module
from pema.config.runtime_tuning_settings import reset_tuning_provider
from pema.core.db import ClinicDatabase
from pema.mcp.mcp_agent_binding import McpBindingCache, McpBindingStore, PgMcpPolicyStore
from pema.mcp.mcp_server_store import McpServerStore, PgMcpServerStore
from pema.mcp.testing import InMemoryMcpStore
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.testing import InMemoryAgentStore, fake_agent_profile

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
API_INI = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")


@pytest.fixture(autouse=True)
def _secret_key_and_tuning(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "c" * 64)
    env_module.get_settings.cache_clear()
    yield
    reset_tuning_provider()
    env_module.get_settings.cache_clear()


@pytest.fixture(scope="session")
def pg_admin() -> Iterator[Engine]:
    if not ADMIN_URL:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    patch = pytest.MonkeyPatch()
    patch.setenv("PEMA_MIGRATION_DATABASE_URL", ADMIN_URL)
    patch.setenv("PEMA_BE_APP_PASSWORD", BE_PASSWORD)
    patch.setenv("PEMA_AGENT_WORKER_PASSWORD", WORKER_PASSWORD)
    engine = create_engine(ADMIN_URL)
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))
    command.upgrade(Config(API_INI), "heads")
    yield engine
    engine.dispose()
    patch.undo()


@dataclass
class StoreBundle:
    kind: str
    clinic_id: uuid.UUID
    servers: McpServerStore
    bindings: McpBindingStore
    cache: McpBindingCache
    agent_store: InMemoryAgentStore
    add_agent: Callable[..., Awaitable[None]]
    db: ClinicDatabase | None = None
    admin: Engine | None = None


@pytest.fixture(params=["memory", "pg"])
async def bundle(request: pytest.FixtureRequest) -> AsyncIterator[StoreBundle]:
    clinic_id = uuid.uuid4()
    agent_store = InMemoryAgentStore()
    cache = McpBindingCache()

    if request.param == "memory":
        store = InMemoryMcpStore(agent_store=agent_store, binding_cache=cache)

        async def add_memory_agent(
            agent_id: str, profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT
        ) -> None:
            agent_store.agents[(clinic_id, agent_id)] = fake_agent_profile(
                id=agent_id, clinic_id=clinic_id, policy_profile=profile
            )

        yield StoreBundle("memory", clinic_id, store, store, cache, agent_store, add_memory_agent)
        return

    admin: Engine = request.getfixturevalue("pg_admin")
    assert ADMIN_URL is not None
    with admin.begin() as conn:
        conn.execute(
            text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'Synthetic')"),
            {"id": clinic_id, "slug": f"c-{clinic_id.hex[:12]}"},
        )
    db = ClinicDatabase(
        make_url(ADMIN_URL).set(username="be_app", password=BE_PASSWORD).render_as_string(False)
    )
    servers = PgMcpServerStore(db)
    bindings = PgMcpPolicyStore(db, agent_store=agent_store, binding_cache=cache)

    async def add_pg_agent(
        agent_id: str, profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT
    ) -> None:
        agent_store.agents[(clinic_id, agent_id)] = fake_agent_profile(
            id=agent_id, clinic_id=clinic_id, policy_profile=profile
        )
        with admin.begin() as conn:
            conn.execute(
                text("INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, :a, 'Synthetic')"),
                {"c": clinic_id, "a": agent_id},
            )

    try:
        yield StoreBundle("pg", clinic_id, servers, bindings, cache, agent_store, add_pg_agent, db, admin)
    finally:
        await db.dispose()
