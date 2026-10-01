"""Fixtures of the scheduler tests: a real Postgres (skipped without ``PEMA_TEST_DATABASE_URL``), one NEW clinic
per test (RLS keeps tests apart, nothing to clean), and the fakes of ``pema.scheduler.testing``.

The database is the throwaway one of ``tests/test_database.py`` (superuser URL): the module-scoped fixture
drops every Pema schema and re-runs the alembic history, then the tests connect as the REAL runtime role
``agent_worker`` so grants and RLS are exercised exactly as in production.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pema.channels.registry import InMemoryChannelRegistry
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.core.db import ClinicDatabase
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.testing import (
    FakeClinicActions,
    FakeEngine,
    FakeHistory,
    FakeOutbound,
    FakeUsage,
    fake_wrap_untrusted,
)
from pema.scheduler.testing_env import ACC, AGENT, Env
from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.policy import PermissivePolicyHooks, PolicyHooks, PolicyProfileKey
from pema_contracts.testing import FakeChannel, InMemoryAccountStore, InMemoryAgentStore, InMemoryThreadLock

API_DIR = Path(__file__).resolve().parents[2]
API_INI = API_DIR / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
def _tuning_reset() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    if not ADMIN_URL:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


def worker_url() -> str:
    if not ADMIN_URL:
        raise RuntimeError("PEMA_TEST_DATABASE_URL not set")
    return make_url(ADMIN_URL).set(username="agent_worker", password=WORKER_PASSWORD).render_as_string(False)


@pytest_asyncio.fixture
async def make_env(admin_engine: Engine) -> AsyncIterator[Callable[..., Env]]:
    """``env = make_env(profile=..., hooks=..., tuning={...})``: a fresh clinic with a running account."""
    created: list[Env] = []

    def factory(
        profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
        *,
        hooks: PolicyHooks | None = None,
        tuning: dict[str, str | int | float | bool] | None = None,
        channel_kind: ChannelKind = ChannelKind.ZALO_PERSONAL,
        supports_formatting: bool = True,
        max_text_length: int = 2000,
        online: bool = True,
        stale_run_seconds: float = 120.0,
        heartbeat_seconds: float = 30.0,
    ) -> Env:
        all_tuning: dict[str, str | int | float | bool] = {"SCHEDULER_SEND_GAP_MS": 0, **(tuning or {})}
        install_tuning_provider(StaticTuningProvider(all_tuning))
        clinic_id = uuid.uuid4()
        with admin_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'Synthetic')"),
                {"id": clinic_id, "slug": f"s-{clinic_id.hex[:12]}"},
            )
            conn.execute(
                text(
                    "INSERT INTO agent.agents (clinic_id, id, name, policy_profile) "
                    "VALUES (:c, :a, 'Agent S', :p)"
                ),
                {"c": clinic_id, "a": AGENT, "p": profile.value},
            )
            conn.execute(
                text(
                    "INSERT INTO agent.accounts (clinic_id, id, label, channel, agent_id, policy_profile) "
                    "VALUES (:c, :id, 'Account S', :ch, :a, :p)"
                ),
                {"c": clinic_id, "id": ACC, "ch": channel_kind.value, "a": AGENT, "p": profile.value},
            )
        db = ClinicDatabase(worker_url())
        caps = ChannelCapabilities(
            channel=channel_kind,
            can_send_proactive=True,
            max_text_length=max_text_length,
            supports_formatting=supports_formatting,
        )
        channel = FakeChannel(caps=caps, account=ACC)
        registry = InMemoryChannelRegistry()
        if online:
            registry.register(clinic_id, channel)
        history = FakeHistory()
        usage = FakeUsage()
        engine = FakeEngine()
        outbound = FakeOutbound()
        actions = FakeClinicActions()
        accounts = InMemoryAccountStore(
            AccountConfig(
                id=ACC,
                clinic_id=clinic_id,
                label="Account S",
                channel=channel_kind,
                agent_id=AGENT,
                policy_profile=profile,
            )
        )
        agents = InMemoryAgentStore(
            AgentProfile(
                id=AGENT, clinic_id=clinic_id, name="Agent S", policy_profile=profile, is_default=True
            )
        )
        deps = SchedulerDeps(
            db=db,
            channels=registry,
            accounts=accounts,
            agents=agents,
            history=history,  # type: ignore[arg-type]
            usage=usage,  # type: ignore[arg-type]
            engine=engine,
            outbound=outbound,
            thread_lock=InMemoryThreadLock(),  # type: ignore[arg-type]  # fake of A: __aexit__ is narrower than the protocol
            clinic_actions=actions,  # type: ignore[arg-type]
            wrap_untrusted=fake_wrap_untrusted,
            hooks=hooks if hooks is not None else PermissivePolicyHooks(),
            stale_run_seconds=stale_run_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )
        env = Env(
            clinic_id=clinic_id,
            db=db,
            admin=admin_engine,
            deps=deps,
            channel=channel,
            registry=registry,
            history=history,
            usage=usage,
            engine=engine,
            outbound=outbound,
            actions=actions,
            accounts=accounts,
            agents=agents,
            profile=profile,
        )
        created.append(env)
        return env

    yield factory
    for env in created:
        await env.db.dispose()
        for extra in env.extra_dbs:
            await extra.dispose()
