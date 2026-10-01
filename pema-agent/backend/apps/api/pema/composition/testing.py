"""Harness of the closed-loop integration tests (package G; import in tests only).

It runs the REAL application twice, as in production: the API (``create_app`` with its lifespan, role
``be_app``) and the worker (``start_worker``, role ``agent_worker``), over a real Postgres and a real Redis. The
only fakes are the two things that leave the building: the Zalo Bot API (one ``FakeBotClient`` shared by both
processes, it records every message the system sends) and the LLM (a ``ScriptedModel`` that records every
prompt). No real Zalo, no real model, no network.

``open_loop`` is an async context manager; the object it yields knows how to send a synthetic Zalo update to
the webhook, wait for the system to answer, and sign in a member of staff.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from pema.agent.model_types import ChatModel
from pema.agent.streaming_model_test_helper import ScriptedModel, tra_loi
from pema.bootstrap import create_app
from pema.channels.zalo_bot.settings import derive_webhook_secret
from pema.channels.zalo_bot.testing import SYNTHETIC_TOKEN, FakeBotClient
from pema.clinic.actions.seed_demo import SeedResult, seed_demo
from pema.composition.runtime import ProcessRole, Runtime, build_runtime
from pema.config.account_store import AccountStoreImpl
from pema.config.agent_store import AgentStoreImpl
from pema.config.env import Settings
from pema.conversation.media_store import DownloadedImage
from pema.core.db import ClinicDatabase
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema.workers.main import WorkerHandle, start_worker
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import PolicyProfileKey

ACCOUNT_PASSWORD = "demo-account-test-secret"  # noqa: S105 - the password seed_demo gives every account
TEST_ENCRYPTION_KEY = "0123456789abcdef" * 4
"""64 hex characters: a synthetic key, never a real one."""


@dataclass
class Loop:
    settings: Settings
    world: SeedResult
    slug: str
    app: FastAPI
    api: Runtime
    worker_rt: Runtime
    worker: WorkerHandle
    bot: FakeBotClient
    model: ScriptedModel
    http: httpx.AsyncClient
    redis_url: str
    downloads: list[str]
    """URLs the media store was asked to fetch (never fetched: the downloader of the harness returns None)."""
    account_id: str
    """A bot account of its own for every loop, so one test never reads the rows of another."""
    _updates: int = field(default=0)
    _run: str = field(default_factory=lambda: uuid4().hex[:8])
    """Part of every message id: ``agent.channel_update_seen`` outlives a test, a repeated id is a duplicate."""
    _baseline_review_ids: set[UUID] = field(default_factory=set[UUID])
    _clients: list[httpx.AsyncClient] = field(default_factory=list[httpx.AsyncClient])

    @property
    def clinic_id(self) -> UUID:
        return self.world.clinic_id

    async def send_zalo_text(
        self, text: str, *, uid: str = "demo-uid-025", thread: str | None = None
    ) -> httpx.Response:
        """One synthetic text update from a customer, delivered to the real webhook route."""
        self._updates += 1
        thread_id = thread or uid
        payload: dict[str, Any] = {
            "ok": True,
            "result": {
                "event_name": "message.text.received",
                "message": {
                    "from": {"id": uid, "display_name": "Khách Mẫu", "is_bot": False},
                    "chat": {"id": thread_id, "chat_type": "PRIVATE"},
                    "text": text,
                    "message_id": f"mid-{self._run}-{self._updates}",
                    "date": 1750316131602 + self._updates,
                },
            },
        }
        return await self._deliver(payload)

    async def send_zalo_image(
        self, *, uid: str = "demo-uid-025", url: str = "https://img.example.test/a.jpg"
    ) -> httpx.Response:
        """One synthetic image update. The URL is never fetched by the test (the media store is faked out)."""
        self._updates += 1
        payload: dict[str, Any] = {
            "ok": True,
            "result": {
                "event_name": "message.image.received",
                "message": {
                    "from": {"id": uid, "display_name": "Khách Mẫu", "is_bot": False},
                    "chat": {"id": uid, "chat_type": "PRIVATE"},
                    "photo": url,
                    "message_id": f"mid-{self._run}-{self._updates}",
                    "date": 1750316131602 + self._updates,
                },
            },
        }
        return await self._deliver(payload)

    async def _deliver(self, payload: dict[str, Any]) -> httpx.Response:
        secret = derive_webhook_secret(self.clinic_id, self.account_id)
        return await self.http.post(
            f"/api/v1/webhooks/zalo-bot/{self.slug}/{self.account_id}",
            content=json.dumps(payload),
            headers={"content-type": "application/json", "X-Bot-Api-Secret-Token": secret},
        )

    async def wait_for(
        self, condition: Callable[[], bool | Awaitable[bool]], what: str, ms: int = 15000
    ) -> None:
        await doi_cho_den_khi(condition, WaitOptions(tran_ms=ms, nhip_ms=20, mo_ta=what))

    async def wait_sent(self, count: int = 1) -> list[tuple[str, str, str | None]]:
        await self.wait_for(lambda: len(self.bot.sent) >= count, f"{count} message(s) sent to Zalo")
        return list(self.bot.sent)

    async def close_clients(self) -> None:
        for client in self._clients:
            await client.aclose()

    async def staff(self, user_key: str) -> httpx.AsyncClient:
        """A client signed in as a member of the demo clinic (``cs.maianh``, ``doctor.mai``, ``owner`` ...)."""
        from pema.api import dashboard_auth

        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False), base_url="http://test"
        )
        self._clients.append(client)
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "clinic_slug": self.slug,
                "email": f"{user_key}@example.test",
                "password": ACCOUNT_PASSWORD,
            },
        )
        dashboard_auth.reset_login_rate_limit()
        if response.status_code != 200:
            raise RuntimeError(f"login of {user_key} failed with {response.status_code}")
        return client

    async def review_items(self) -> list[dict[str, Any]]:
        """Review items created since the loop opened (the seeded demo items are left out)."""
        from sqlalchemy import text

        async with self.api.db.session(self.clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id, kind, status, origin, draft_text, risk_level, red_flags, payload, "
                            "version, job_id FROM clinic.review_item ORDER BY created_at"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [dict(r) for r in rows if r["id"] not in self._baseline_review_ids]

    async def wait_review_items(self, count: int = 1) -> list[dict[str, Any]]:
        await self.wait_for(lambda: _has_reviews(self, count), f"{count} new review item(s) in the queue")
        return await self.review_items()

    async def wait_model_calls(self, count: int = 1) -> None:
        await self.wait_for(lambda: self.model.count >= count, f"{count} model call(s)")


@contextlib.asynccontextmanager
async def open_loop(
    *,
    db: ClinicDatabase,
    worker_db: ClinicDatabase,
    world: SeedResult,
    slug: str,
    redis_url: str,
    model: ScriptedModel,
    profile: PolicyProfileKey,
    data_dir: Path,
    scheduler: bool = False,
) -> AsyncGenerator[Loop]:
    """Start the API and the worker over ``db`` / ``worker_db`` and one Redis. ``profile`` is the policy
    profile of the account AND of the default agent (``staff_assistant`` = send directly, ``patient_channel`` =
    every outbound text is held for a person)."""
    settings = Settings(
        redis_url=redis_url,
        data_dir=data_dir,
        crm_runner_interval_seconds=0,
        zalo_personal_enabled=False,
    )
    await _flush_redis(redis_url)
    account_id = f"bot-{uuid4().hex[:8]}"

    accounts = AccountStoreImpl(db, AgentStoreImpl(db))
    agents = AgentStoreImpl(db)
    default_agent = await agents.ensure_default_agent(world.clinic_id)
    await agents.update_agent(world.clinic_id, default_agent.id, {"policy_profile": profile})
    if await accounts.get_account(world.clinic_id, account_id) is None:
        await accounts.create_account(
            world.clinic_id,
            account_id=account_id,
            label="Bot thử vòng khép kín",
            channel=ChannelKind.ZALO_BOT,
            agent_id=default_agent.id,
            policy_profile=profile,
        )
    await accounts.update_account(world.clinic_id, account_id, {"policy_profile": profile, "enabled": True})
    await accounts.set_bot_token(world.clinic_id, account_id, SYNTHETIC_TOKEN)
    for other in await accounts.list_accounts(world.clinic_id):
        if other.id != account_id and other.enabled:
            await accounts.update_account(world.clinic_id, other.id, {"enabled": False})

    bot = FakeBotClient()

    def client_factory(_token: str) -> FakeBotClient:
        return bot

    def resolve_model(*_args: object) -> ChatModel:
        return model

    downloads: list[str] = []

    async def download(url: str) -> DownloadedImage | None:
        downloads.append(url)  # nothing is fetched: the test only wants to know it was asked
        return None

    api_rt = build_runtime(
        settings,
        ProcessRole.API,
        db=db,
        resolve_model=resolve_model,
        embedder=None,
        image_downloader=download,
    )
    worker_rt = build_runtime(
        settings,
        ProcessRole.WORKER,
        db=worker_db,
        resolve_model=resolve_model,
        embedder=None,
        image_downloader=download,
    )
    app = create_app(runtime=api_rt, bot_client_factory=client_factory)
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(app.router.lifespan_context(app))
        worker = await start_worker(worker_rt, bot_client_factory=client_factory, with_scheduler=scheduler)
        stack.push_async_callback(worker.wait)
        stack.callback(worker.stop)
        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        )
        stack.push_async_callback(http.aclose)
        loop = Loop(
            settings=settings,
            world=world,
            slug=slug,
            app=app,
            api=api_rt,
            worker_rt=worker_rt,
            worker=worker,
            bot=bot,
            model=model,
            http=http,
            redis_url=redis_url,
            account_id=account_id,
            downloads=downloads,
        )
        loop._baseline_review_ids = {UUID(str(r["id"])) for r in await _all_review_ids(db, world.clinic_id)}
        stack.push_async_callback(loop.close_clients)
        yield loop


async def _flush_redis(redis_url: str) -> None:
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        await client.flushdb()
    finally:
        await client.aclose()


def scripted(*texts: str) -> ScriptedModel:
    """A fake model that answers with these texts in order (the last one repeats)."""
    return ScriptedModel([lambda t=t: tra_loi(t) for t in texts])


class LoopFactory:
    """What the ``make_loop`` fixture hands to a test: the databases and Redis, ready to ``open`` a loop."""

    def __init__(
        self, db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, redis_url: str, tmp: Path
    ) -> None:
        self._db = db
        self._worker_db = worker_db
        self._world = world
        self._redis_url = redis_url
        self._tmp = tmp

    def open(
        self, model: ScriptedModel, profile: PolicyProfileKey, *, scheduler: bool = False
    ) -> contextlib.AbstractAsyncContextManager[Loop]:
        """The shared demo clinic ``clinic-a``."""
        return self._open(self._world, "clinic-a", model, profile, scheduler)

    async def open_fresh(
        self, model: ScriptedModel, profile: PolicyProfileKey, *, scheduler: bool = False
    ) -> contextlib.AbstractAsyncContextManager[Loop]:
        """A demo clinic of its own: the tasks, jobs and review items of other tests stay out of the way."""
        slug = f"loop-{uuid4().hex[:8]}"
        world = await seed_demo(self._db, password=ACCOUNT_PASSWORD, slug=slug)
        return self._open(world, slug, model, profile, scheduler)

    def _open(
        self, world: SeedResult, slug: str, model: ScriptedModel, profile: PolicyProfileKey, scheduler: bool
    ) -> contextlib.AbstractAsyncContextManager[Loop]:
        return open_loop(
            db=self._db,
            worker_db=self._worker_db,
            world=world,
            slug=slug,
            redis_url=self._redis_url,
            model=model,
            profile=profile,
            data_dir=self._tmp,
            scheduler=scheduler,
        )


async def _has_reviews(loop: Loop, count: int) -> bool:
    return len(await loop.review_items()) >= count


async def _all_review_ids(db: ClinicDatabase, clinic_id: UUID) -> list[dict[str, Any]]:
    from sqlalchemy import text

    async with db.session(clinic_id) as session:
        rows = (await session.execute(text("SELECT id FROM clinic.review_item"))).mappings().all()
    return [dict(r) for r in rows]
