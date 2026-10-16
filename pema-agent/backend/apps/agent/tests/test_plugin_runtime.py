"""What plugins get beyond tools and channels: their own storage, HTTP routes (admin and hooks), background jobs,
channels registered while running, typing shown while a reply is written; and the core staying free of any
one platform."""

from __future__ import annotations

import asyncio
import re
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

import agent_app
import agentcore
from agent_app.channel_hub import ChannelHub, DeliverySettings
from agent_app.dispatcher import DispatchSettings
from agent_app.gateway import HOOK_CALLS_PER_WINDOW, GatewaySettings, create_app
from agent_app.plugins import PluginError, PluginHost, discover
from agent_app.plugins.jobs import JobRunner, JobSettings
from agent_app.plugins.records import MAX_VALUE_BYTES, InMemoryPluginRecords
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import AssistantResult, LlmRequest, StreamSink
from agentcore.channels import ChannelCapabilities, InboundMessage, OutboundMessage, Receive
from agentcore.harness.model.scripted import reply

TOKEN = "t" * 40
ADMIN = "a" * 40

ROUTES_PLUGIN = """
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agentcore.channels import ChannelCapabilities

admin = APIRouter()
hooks = APIRouter()


class Quiet:
    capabilities = ChannelCapabilities()

    def __init__(self, name):
        self.name = name

    async def start(self, receive):
        pass

    async def stop(self):
        pass

    async def send(self, message):
        pass


@admin.get("/accounts/{account_id}")
async def show(account_id: str, request: Request):
    return {"account": account_id, "stored": await CTX.storage.get(account_id), "path": request.url.path}


@admin.put("/accounts/{account_id}")
async def save(account_id: str, request: Request):
    await CTX.storage.put(account_id, await request.json())
    return {"saved": account_id}


@admin.post("/channels/{name}")
async def add_channel(name: str):
    try:
        CTX.register_channel(Quiet(name))
    except ValueError as err:
        return JSONResponse({"error": str(err)}, status_code=409)
    return {"channel": name}


@hooks.post("/events")
async def event(request: Request):
    if request.headers.get("x-secret") != "s3cret":
        return JSONResponse({"error": "who are you"}, status_code=401)
    return {"got": (await request.json())["n"]}


def register(ctx):
    global CTX
    CTX = ctx
    ctx.register_routes(admin)
    ctx.register_routes(hooks, kind="hooks")
"""

CHANNEL_PLUGIN = """
from agentcore.channels import ChannelCapabilities


class Quiet:
    capabilities = ChannelCapabilities()
    name = "taken"

    async def start(self, receive):
        pass

    async def stop(self):
        pass

    async def send(self, message):
        pass


def register(ctx):
    ctx.register_channel(Quiet())
"""

JOB_PLUGIN = """
import asyncio


def register(ctx):
    log = ctx.config["log"]

    async def beat():
        log.append("start")
        try:
            if ctx.config.get("fail") and log.count("start") == 1:
                raise RuntimeError("first run fails")
            await asyncio.Event().wait()
        finally:
            log.append("end")

    ctx.register_job("beat", beat)
"""


def _plugin(root: Path, name: str, code: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(f'name = "{name}"\n', encoding="utf-8")
    (folder / "__init__.py").write_text(textwrap.dedent(code), encoding="utf-8")


def _runtime(tmp_path: Path, enabled: Sequence[str]) -> Runtime:
    folder = tmp_path / "agent"
    plugins = folder / "plugins"
    plugins.mkdir(parents=True)
    _plugin(plugins, "hooky", ROUTES_PLUGIN)
    _plugin(plugins, "other", CHANNEL_PLUGIN)
    names = ", ".join(f'"{name}"' for name in enabled)
    (folder / "agent.toml").write_text(
        f'[agent]\nname = "t"\nsystem_prompt = "p"\n\n[plugins]\nenabled = [{names}]\n', encoding="utf-8"
    )
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(
        runtime.dispatcher(),
        GatewaySettings(token=TOKEN, admin_token=ADMIN),
        plugins=runtime.plugin_manager,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


# --- storage ---


async def test_each_plugin_sees_only_its_own_records() -> None:
    records = InMemoryPluginRecords()
    mine, theirs = records.storage("mine"), records.storage("theirs")

    await mine.put("account:b", {"label": "B"})
    await mine.put("account:a", {"label": "A", "ids": [1, 2]})
    await mine.put("contact:x", "X")
    await theirs.put("account:a", "not yours")

    assert await mine.get("account:a") == {"label": "A", "ids": [1, 2]}
    assert await mine.list("account:") == [
        ("account:a", {"label": "A", "ids": [1, 2]}),
        ("account:b", {"label": "B"}),
    ]
    assert await mine.list(limit=1) == [("account:a", {"label": "A", "ids": [1, 2]})]
    assert (await mine.delete("account:a"), await mine.delete("account:a")) == (True, False)
    assert (await mine.get("account:a"), await theirs.get("account:a")) == (None, "not yours")


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("", 1, "a key has 1 to 300"),
        ("k" * 301, 1, "a key has 1 to 300"),
        ("k", None, "delete the key instead"),
        ("k", "x" * MAX_VALUE_BYTES, "at most"),
        ("k", "a\x00b", "NUL"),
        ("k", float("nan"), "Out of range"),
    ],
    ids=["empty-key", "long-key", "none", "too-big", "nul", "nan"],
)
async def test_bad_keys_and_values_are_refused(key: str, value: Any, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        await InMemoryPluginRecords().storage("p").put(key, value)


# --- routes ---


SEALING_PLUGIN = """
def register(ctx):
    log = ctx.config["log"]
    try:
        sealed = ctx.encrypt("token-123")
    except ValueError as err:
        log.append(str(err))
        return
    log.append(sealed)
    log.append(ctx.decrypt(sealed))
    try:
        ctx.decrypt("not sealed")
    except ValueError as err:
        log.append(str(err))
"""


def test_a_plugin_seals_secrets_with_the_service_key_it_cannot_read(tmp_path: Path) -> None:
    _plugin(tmp_path, "sealer", SEALING_PLUGIN)
    sources = discover([("agent", tmp_path)]).plugins
    without: list[str] = []
    PluginHost(sources, {}).enable("sealer", {"log": without})
    with_key: list[str] = []
    PluginHost(sources, {"AGENT_SECRET_ENCRYPTION_KEY": "0f" * 32}).enable("sealer", {"log": with_key})

    assert without == [
        "plugin sealer: the service has no secret key (agent serve creates one in its home folder)"
    ]
    sealed, opened, refused = with_key
    assert "token-123" not in sealed
    assert opened == "token-123"
    assert refused == "plugin sealer: a stored secret does not decrypt (was the secret key file replaced?)"


async def test_plugin_admin_routes_need_the_admin_scope_and_reach_the_plugin(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["hooky"])
    async with _client(runtime) as client:
        anonymous = await client.get("/v1/plugins/hooky/accounts/a1")
        chat_token = await client.get(
            "/v1/plugins/hooky/accounts/a1", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        admin = {"Authorization": f"Bearer {ADMIN}"}
        saved = await client.put("/v1/plugins/hooky/accounts/a1", json={"label": "Lễ tân"}, headers=admin)
        shown = await client.get("/v1/plugins/hooky/accounts/a1", headers=admin)
        unknown = await client.get("/v1/plugins/nobody/accounts/a1", headers=admin)
        no_route = await client.get("/v1/plugins/hooky/nothing", headers=admin)
        hook_path = await client.post("/v1/hooks/hooky/accounts/a1", headers=admin)

    assert (anonymous.status_code, chat_token.status_code) == (401, 403)
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert saved.json() == {"saved": "a1"}
    assert shown.json() == {
        "account": "a1",
        "stored": {"label": "Lễ tân"},
        "path": "/v1/plugins/hooky/accounts/a1",
    }
    assert (unknown.status_code, no_route.status_code, hook_path.status_code) == (404, 404, 404)
    runtime.close()


async def test_hooks_are_open_checked_by_the_plugin_and_limited_per_address(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["hooky"])
    async with _client(runtime) as client:
        refused = await client.post("/v1/hooks/hooky/events", json={"n": 1})
        accepted = await client.post("/v1/hooks/hooky/events", json={"n": 2}, headers={"x-secret": "s3cret"})
        statuses = [
            (await client.post("/v1/hooks/hooky/events", json={"n": 3})).status_code
            for _ in range(HOOK_CALLS_PER_WINDOW)
        ]

    assert (refused.status_code, accepted.json()) == (401, {"got": 2})
    assert statuses[-1] == 429
    assert statuses.count(429) == 2
    runtime.close()


async def test_routes_go_away_with_their_plugin(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["hooky"])
    admin = {"Authorization": f"Bearer {ADMIN}"}
    async with _client(runtime) as client:
        before = await client.get("/v1/plugins/hooky/accounts/a1", headers=admin)
        described = (await client.get("/v1/admin/plugins/hooky", headers=admin)).json()
        await client.post("/v1/admin/plugins/hooky/disable", headers=admin)
        after = await client.get("/v1/plugins/hooky/accounts/a1", headers=admin)
        hook = await client.post("/v1/hooks/hooky/events", json={"n": 1}, headers={"x-secret": "s3cret"})

    assert (before.status_code, after.status_code, hook.status_code) == (200, 404, 404)
    assert described["routes"] == ["admin", "hooks"]
    runtime.close()


async def test_a_channel_registered_while_running_may_not_take_another_plugins_name(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, ["hooky", "other"])
    admin = {"Authorization": f"Bearer {ADMIN}"}
    async with _client(runtime) as client:
        clash = await client.post("/v1/plugins/hooky/channels/taken", headers=admin)
        added = await client.post("/v1/plugins/hooky/channels/front-desk", headers=admin)
        twice = await client.post("/v1/plugins/hooky/channels/front-desk", headers=admin)

    assert (clash.status_code, clash.json()) == (
        409,
        {"error": "plugin hooky: channel taken already comes from other"},
    )
    assert added.json() == {"channel": "front-desk"}
    assert twice.status_code == 409
    assert [c.name for c in runtime.plugins.contributions().channels] == ["front-desk", "taken"]
    runtime.close()


# --- jobs ---


def _job_host(tmp_path: Path) -> PluginHost:
    _plugin(tmp_path, "jobs", JOB_PLUGIN)
    return PluginHost(discover([("agent", tmp_path)]).plugins, {})


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_job_runs_restarts_after_a_failure_and_stops_with_its_plugin(tmp_path: Path) -> None:
    host = _job_host(tmp_path)
    log: list[str] = []
    host.enable("jobs", {"log": log, "fail": True})
    runner = JobRunner(lambda: host.contributions().jobs, settings=JobSettings(restart_s=(0.0,)))

    await runner.sync()
    await _settle()
    await runner.sync()
    failed = runner.status()
    await _settle()
    host.disable("jobs")
    await runner.sync()

    assert failed == [{"name": "jobs/beat", "running": True, "error": "RuntimeError: first run fails"}]
    assert log == ["start", "end", "start", "end"]
    assert (runner.running, runner.status()) == ([], [])


async def test_a_job_that_keeps_failing_waits_longer_each_time(tmp_path: Path) -> None:
    host = _job_host(tmp_path)
    host.enable("jobs", {"log": [], "fail": True})
    now = [0.0]
    runner = JobRunner(
        lambda: host.contributions().jobs, settings=JobSettings(restart_s=(5.0, 30.0)), clock=lambda: now[0]
    )

    await runner.sync()
    await _settle()
    await runner.sync()
    waiting = runner.running
    now[0] = 5.0
    await runner.sync()

    assert (waiting, runner.running) == ([], ["jobs/beat"])
    await runner.close()
    host.close()


def test_job_names_are_checked(tmp_path: Path) -> None:
    _plugin(tmp_path, "badjob", "def register(ctx):\n    ctx.register_job('Bad Name', None)\n")
    _plugin(
        tmp_path,
        "twice",
        "def register(ctx):\n    ctx.register_job('a', None)\n    ctx.register_job('a', None)\n",
    )
    host = PluginHost(discover([("agent", tmp_path)]).plugins, {})

    with pytest.raises(PluginError, match="invalid job name 'Bad Name'"):
        host.enable("badjob")
    with pytest.raises(PluginError, match="job a registered twice"):
        host.enable("twice")


# --- typing ---


class SlowModel:
    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        await asyncio.sleep(0.15)
        return reply("done")


class TypingChannel:
    def __init__(self) -> None:
        self.name = "typer"
        self.capabilities = ChannelCapabilities()
        self.receive: Receive | None = None
        self.sent: list[OutboundMessage] = []
        self.typing_calls: list[tuple[str, dict[str, str]]] = []

    async def start(self, receive: Receive) -> None:
        self.receive = receive

    async def stop(self) -> None:
        pass

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)

    async def typing(self, conversation_id: str, metadata: Mapping[str, str]) -> None:
        self.typing_calls.append((conversation_id, dict(metadata)))


async def test_typing_is_shown_while_the_reply_is_written_and_stops_after(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, [])
    runtime.live.use_model(SlowModel())
    channel = TypingChannel()
    dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.01, queue_mode="followup"))
    hub = ChannelHub(
        dispatcher,
        channels=lambda: [channel],
        settings=DeliverySettings(tick_s=0.01, typing_every_s=0.02),
    )
    await hub.sync()
    assert channel.receive is not None

    await channel.receive(InboundMessage("x", "c1", "u1", "m1", "hi", {"thread": "user"}))
    for _ in range(100):
        await hub.tick()
        if channel.sent:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    shown = len(channel.typing_calls)
    await asyncio.sleep(0.1)

    assert [m.text for m in channel.sent] == ["done"]
    assert channel.typing_calls[0] == ("c1", {"thread": "user"})
    assert 2 <= shown == len(channel.typing_calls)
    await hub.close()
    await dispatcher.close()
    runtime.close()


# --- the core knows no platform ---


def test_the_core_names_no_chat_platform() -> None:
    platforms = re.compile(r"zalo|slack|telegram|discord|whatsapp", re.IGNORECASE)
    found = [
        f"{path.name}: {match.group(0)}"
        for package in (agentcore, agent_app)
        for path in Path(package.__file__ or "").parent.rglob("*.py")
        for match in platforms.finditer(path.read_text(encoding="utf-8"))
    ]
    assert found == []
