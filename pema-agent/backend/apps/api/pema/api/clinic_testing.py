"""Test support for everything that needs the clinic database (package B1; not imported by production code).

It lives in ``pema.api`` because it builds the whole application, which ``pema.clinic`` may not import.

New module, like ``pema_contracts.testing``. It holds the fixtures that every DB-backed test of the clinic
shares, so the conftest files only import them:

* ``pg_url``: the throwaway Postgres of ``PEMA_TEST_DATABASE_URL`` (superuser URL), migrated to ``heads``
  once per session; the test is SKIPPED when the variable is not set. The first use DROPS every Pema schema
  of that database, so never point it at data you care about;
* ``db`` / ``worker_db``: a ``ClinicDatabase`` as role ``be_app`` (API process) or ``agent_worker`` (worker),
  both subject to row level security;
* ``world_a`` / ``world_b``: two clinics seeded with ``seed_demo`` (all synthetic), one set of users per role;
* ``demo_clock``: freezes the action clock at the demo day 2026-09-20 09:00 (+07:00);
* ``app``, ``client_factory``: the FastAPI app wired to ``db`` and an async HTTP client per signed-in user.

The module is a pytest plugin by import: ``from pema.api.clinic_testing import db, world_a  # noqa: F401``.
"""

from __future__ import annotations

import itertools
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from pema.api import dashboard_auth
from pema.clinic.actions import _common
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult, seed_demo
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase
from pema_contracts.clinic_actions import InboxRef
from pema_contracts.common import VN_TZ

ENV_URL = "PEMA_TEST_DATABASE_URL"
BE_PASSWORD = "be-app-test-secret"  # noqa: S105  - throwaway test database only
WORKER_PASSWORD = "agent-worker-test-secret"  # noqa: S105
ACCOUNT_PASSWORD = "demo-account-test-secret"  # noqa: S105
JWT_SECRET = "test-only-jwt-secret-with-at-least-32-chars"  # noqa: S105
API_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
HEAD_TABLE = "alembic_version_pema"
DEMO_NOW = datetime(DEMO_DAY.year, DEMO_DAY.month, DEMO_DAY.day, 9, 0, tzinfo=VN_TZ)

ClientFactory = Callable[[str, str], Awaitable[httpx.AsyncClient]]


def _role_url(admin: str, role: str, password: str) -> str:
    return make_url(admin).set(username=role, password=password).render_as_string(hide_password=False)


def _migrate(admin: str, *, fresh: bool) -> None:
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = admin
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(admin)
    try:
        if fresh:
            with engine.begin() as conn:
                for schema in ("clinic_agent", "agent", "clinic", "ctx"):
                    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                conn.execute(text(f"DROP TABLE IF EXISTS public.{HEAD_TABLE}"))
        command.upgrade(Config(str(API_INI)), "heads")
    finally:
        engine.dispose()


def _schema_is_current(admin: str) -> bool:
    engine = create_engine(admin)
    try:
        with engine.connect() as conn:
            return bool(
                conn.execute(text("SELECT to_regclass('clinic.auth_session') IS NOT NULL")).scalar()
                and conn.execute(
                    text("SELECT to_regclass('clinic_agent.review_item_summary') IS NOT NULL")
                ).scalar()
            )
    except Exception:
        return False
    finally:
        engine.dispose()


_migrated = False


@pytest.fixture(scope="session")
def pg_url() -> str:
    global _migrated
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} not set; no Postgres to test against")
    if not _migrated:
        _migrate(url, fresh=True)
        _migrated = True
    elif not _schema_is_current(url):  # another test module reset the database in between
        _migrate(url, fresh=True)
    return url


@pytest.fixture(autouse=True)
def demo_clock() -> Iterator[None]:
    """Freeze the action clock at the demo day (only matters to tests that use the clinic actions)."""
    with _common.use_clock(lambda: DEMO_NOW):
        yield


@pytest.fixture
def jwt_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("PEMA_ENVIRONMENT", "dev")
    get_settings.cache_clear()
    dashboard_auth.get_auth_settings.cache_clear()
    dashboard_auth.reset_login_rate_limit()
    yield
    get_settings.cache_clear()
    dashboard_auth.get_auth_settings.cache_clear()
    dashboard_auth.reset_login_rate_limit()


@pytest_asyncio.fixture
async def db(pg_url: str) -> AsyncIterator[ClinicDatabase]:
    database = ClinicDatabase(_role_url(pg_url, "be_app", BE_PASSWORD), pool_size=3)
    try:
        yield database
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def worker_db(pg_url: str) -> AsyncIterator[ClinicDatabase]:
    database = ClinicDatabase(_role_url(pg_url, "agent_worker", WORKER_PASSWORD), pool_size=3)
    try:
        yield database
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def world_a(db: ClinicDatabase) -> SeedResult:
    return await seed_demo(db, password=ACCOUNT_PASSWORD, slug="clinic-a")


@pytest_asyncio.fixture
async def world_b(db: ClinicDatabase) -> SeedResult:
    return await seed_demo(db, password=ACCOUNT_PASSWORD, slug="clinic-b")


@pytest.fixture
def app(db: ClinicDatabase, jwt_env: None) -> FastAPI:
    from pema.bootstrap import create_app

    application = create_app()
    application.state.clinic_db = db
    return application


@pytest_asyncio.fixture
async def client_factory(app: FastAPI) -> AsyncIterator[ClientFactory]:
    """``await make("clinic-a", "doctor.mai")`` returns an HTTP client that is signed in as that user."""
    clients: list[httpx.AsyncClient] = []

    async def make(clinic_slug: str, user_key: str) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        http = httpx.AsyncClient(transport=transport, base_url="http://test")
        clients.append(http)
        response = await http.post(
            "/api/v1/auth/login",
            json={
                "clinic_slug": clinic_slug,
                "email": f"{user_key}@example.test",
                "password": ACCOUNT_PASSWORD,
            },
        )
        dashboard_auth.reset_login_rate_limit()  # frozen clock: a whole test shares one rate-limit minute
        assert response.status_code == 200, response.text  # noqa: S101
        return http

    yield make
    for http in clients:
        await http.aclose()


_days = itertools.count(1)


def fresh_start(hour: int = 9, minute: int = 0) -> str:
    """A unique future start time (ISO 8601, +07:00): every call is a new day of 2027, so tests never
    collide on a doctor or a patient slot."""
    day = datetime(2027, 1, 1, hour, minute, tzinfo=VN_TZ) + timedelta(days=next(_days))
    return day.isoformat()


@pytest.fixture
def admin(pg_url: str) -> Iterator[Engine]:
    """Superuser engine for tests that arrange or inspect raw state (never used by the code under test)."""
    engine = create_engine(pg_url)
    yield engine
    engine.dispose()


async def record_inbound(
    db: ClinicDatabase,
    world: SeedResult,
    *,
    uid: str = "demo-uid-025",
    thread: str | None = None,
    text: str = "Tin nhắn mẫu từ bệnh nhân",
    update_id: str | None = None,
) -> InboxRef:
    """Write one inbound message to the Inbox as the channel layer does (``system`` actor). With the default
    ``uid`` (verified identity of P025) the conversation is linked to that patient; a new ``uid`` stays
    unlinked."""
    from uuid import uuid4

    from pema.clinic.actions.agent_facing import ClinicAgentFacingActions
    from pema_contracts.actions import ActionContext, ActionSource
    from pema_contracts.channel import ChannelKind, InboundMessage
    from pema_contracts.roles import ActorType

    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.WEBHOOK)
    message = InboundMessage(
        channel=ChannelKind.ZALO_BOT,
        account_id="bot-1",
        update_id=update_id or uuid4().hex,
        thread_id=thread or uuid4().hex,
        sender_id=uid,
        sender_name="Khách mẫu",
        text=text,
        msg_id=uuid4().hex,
        sent_at=DEMO_NOW,
    )
    return await ClinicAgentFacingActions(db).record_inbound_message(ctx, message)
