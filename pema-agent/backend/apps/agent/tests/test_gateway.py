"""The HTTP gateway and the dispatcher behind it, in process memory: replies, the same message sent twice,
busy sessions, errors, streaming, starting a conversation over, and messages a crash left behind."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from agent_app.dispatcher import Dispatcher, DispatchSettings
from agent_app.gateway import GatewaySettings, create_app
from agent_app.ingress import InMemorySessionLocks, SessionBusyError
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime
from agentcore import AssistantResult, LlmRequest, Message, ModelError, StreamSink, TextBlock, Usage
from agentcore.channels import InboundMessage

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"
TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class GateModel:
    """Answers ``reply:<text>`` once released; records which messages are running at the same time."""

    def __init__(self, *, released: bool = True, error: ModelError | None = None) -> None:
        self.release = asyncio.Event()
        if released:
            self.release.set()
        self.error = error
        self.started: list[str] = []
        self.running = 0
        self.peak = 0
        self.calls = 0

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.calls += 1
        last_user = next(m for m in reversed(request.messages) if m.role == "user")
        text = last_user.text().split("<agent-context>")[0].strip()
        self.started.append(text)
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await self.release.wait()
        finally:
            self.running -= 1
        if self.error is not None:
            raise self.error
        if sink is not None:
            sink.text(f"reply:{text}")
        message = Message(
            role="assistant", blocks=[TextBlock(text=f"reply:{text}")], usage=Usage(output_tokens=1)
        )
        return AssistantResult(message=message, stop_reason="end")


def _dispatcher(model: GateModel, *, max_attempts: int = 3) -> Dispatcher:
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    runtime.live.use_model(model)
    return runtime.dispatcher(DispatchSettings(poll_s=0.01, max_attempts=max_attempts))


class ClientFor:
    """Opens test clients on gateways and closes them, with their dispatchers, after the test."""

    def __init__(self) -> None:
        self.opened: list[tuple[httpx.AsyncClient, Dispatcher]] = []

    def __call__(self, dispatcher: Dispatcher, *, wait_s: float = 5.0) -> httpx.AsyncClient:
        app = create_app(dispatcher, GatewaySettings(token=TOKEN, wait_s=wait_s))
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")
        self.opened.append((client, dispatcher))
        return client


@pytest.fixture
async def client_for() -> AsyncGenerator[ClientFor]:
    clients = ClientFor()
    yield clients
    for client, dispatcher in clients.opened:
        await client.aclose()
        await dispatcher.close(grace_s=1.0)


def _chat(message_id: str, text: str, *, user: str = "u1", conversation: str | None = None) -> dict[str, str]:
    body = {"message_id": message_id, "user_id": user, "text": text}
    if conversation is not None:
        body["conversation_id"] = conversation
    return body


async def test_a_message_gets_a_reply_and_the_same_message_id_never_runs_twice(client_for: ClientFor) -> None:
    model = GateModel()
    client = client_for(_dispatcher(model))

    first = await client.post("/v1/chat", json=_chat("m1", "xin chào"), headers=AUTH)
    again = await client.post("/v1/chat", json=_chat("m1", "xin chào"), headers=AUTH)

    assert first.status_code == 200
    body = first.json()
    assert (body["text"], body["stop"], body["session_id"]) == (
        "reply:xin chào",
        "completed",
        "dev:http:u1:0",
    )
    assert again.json() == body
    assert model.calls == 1


async def test_requests_need_the_bearer_token(client_for: ClientFor) -> None:
    client = client_for(_dispatcher(GateModel()))

    missing = await client.post("/v1/chat", json=_chat("m1", "hi"))
    wrong = await client.post("/v1/chat", json=_chat("m1", "hi"), headers={"Authorization": "Bearer nope"})
    health = await client.get("/health")
    ready = await client.get("/ready")

    assert (missing.status_code, wrong.status_code) == (401, 401)
    assert wrong.headers["WWW-Authenticate"] == "Bearer"
    assert (health.status_code, ready.status_code) == (200, 200)
    with pytest.raises(ValueError, match="at least 32"):
        GatewaySettings(token="short")


async def test_bad_bodies_are_refused_before_anything_runs(client_for: ClientFor) -> None:
    model = GateModel()
    client = client_for(_dispatcher(model))

    too_long = await client.post("/v1/chat", json=_chat("m1", "x" * 8001), headers=AUTH)
    unknown = await client.post("/v1/chat", json={**_chat("m2", "hi"), "session_id": "x"}, headers=AUTH)
    huge = await client.post(
        "/v1/chat", content=b"{" + b" " * 70_000 + b"}", headers={**AUTH, "Content-Type": "application/json"}
    )

    assert (too_long.status_code, unknown.status_code, huge.status_code) == (422, 422, 413)
    assert model.calls == 0


async def test_a_slow_reply_is_answered_with_202_and_can_be_fetched_later(client_for: ClientFor) -> None:
    model = GateModel(released=False)
    client = client_for(_dispatcher(model), wait_s=0.05)

    accepted = await client.post("/v1/chat", json=_chat("m1", "hi"), headers=AUTH)
    pending = await client.get(accepted.headers["Location"], headers=AUTH)
    model.release.set()
    await asyncio.sleep(0.05)
    done = await client.get(accepted.headers["Location"], headers=AUTH)

    assert accepted.status_code == 202
    assert accepted.json()["status"] in {"queued", "processing"}
    assert pending.json()["status"] in {"queued", "processing"}
    assert (done.json()["status"], done.json()["reply"]["text"]) == ("done", "reply:hi")
    assert (await client.get("/v1/ingress/999", headers=AUTH)).status_code == 404


async def test_one_conversation_runs_in_order_while_others_run_alongside() -> None:
    model = GateModel(released=False)
    dispatcher = _dispatcher(model)
    messages = [
        InboundMessage("http", "c1", "u1", "a", "first"),
        InboundMessage("http", "c1", "u2", "b", "second"),
        InboundMessage("http", "c2", "u3", "c", "other"),
    ]

    records = [(await dispatcher.accept(m))[0] for m in messages]
    await asyncio.sleep(0.05)
    running_before_release = list(model.started)
    model.release.set()
    finished = [await dispatcher.wait(r.id, 2.0) for r in records]

    assert sorted(running_before_release) == ["first", "other"]
    assert model.started.index("first") < model.started.index("second")
    assert model.peak == 2
    assert [r.status for r in finished] == ["done", "done", "done"]
    session = await dispatcher.store.load(dispatcher.tenant_id, records[0].session_id)
    assert [m.text() for m in session if m.role == "user"] == ["first", "second"]
    await dispatcher.close()


async def test_a_model_error_is_stored_and_mapped_to_a_status(client_for: ClientFor) -> None:
    model = GateModel(error=ModelError("rate_limit", "slow down"))
    client = client_for(_dispatcher(model))

    first = await client.post("/v1/chat", json=_chat("m1", "hi"), headers=AUTH)
    again = await client.post("/v1/chat", json=_chat("m1", "hi"), headers=AUTH)

    assert first.status_code == 429
    assert first.json()["error"]["kind"] == "rate_limit"
    assert again.status_code == 429
    assert model.calls == 1


async def test_the_stream_sends_accepted_text_and_done(client_for: ClientFor) -> None:
    client = client_for(_dispatcher(GateModel()))

    async with client.stream("POST", "/v1/chat/stream", json=_chat("m1", "hi"), headers=AUTH) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])
        content_type = response.headers["content-type"]

    events = [
        (
            block.split("\n")[0].removeprefix("event: "),
            json.loads(block.split("\n")[1].removeprefix("data: ")),
        )
        for block in body.strip().split("\n\n")
        if block.startswith("event:")
    ]
    assert [name for name, _ in events] == ["accepted", "text", "done"]
    assert events[1][1] == {"delta": "reply:hi"}
    assert events[2][1]["text"] == "reply:hi"
    assert content_type.startswith("text/event-stream")


async def test_starting_over_opens_a_new_session_and_keeps_the_old_one(client_for: ClientFor) -> None:
    client = client_for(_dispatcher(GateModel()))

    old = (await client.post("/v1/chat", json=_chat("m1", "hi", conversation="c1"), headers=AUTH)).json()
    reset = await client.post(
        "/v1/conversations/reset", json={"user_id": "u1", "conversation_id": "c1"}, headers=AUTH
    )
    new = (await client.post("/v1/chat", json=_chat("m2", "again", conversation="c1"), headers=AUTH)).json()
    kept = await client.get(f"/v1/sessions/{old['session_id']}", headers=AUTH)
    missing = await client.get("/v1/sessions/dev:http:nobody:0", headers=AUTH)

    assert (old["session_id"], reset.json()["session_id"]) == ("dev:http:c1:0", "dev:http:c1:1")
    assert new["session_id"] == "dev:http:c1:1"
    assert [m["role"] for m in kept.json()["messages"]] == ["user", "assistant"]
    assert missing.status_code == 404


async def test_the_sweeper_requeues_a_message_a_crash_left_processing_then_gives_up() -> None:
    dispatcher = _dispatcher(GateModel(), max_attempts=2)
    record, _ = await dispatcher.ingress.accept(
        "default", InboundMessage("http", "c", "u", "m", "hi"), "dev:http:c:0"
    )
    await dispatcher.ingress.claim(record.id)  # the run that claimed it died

    await dispatcher.sweep()
    recovered = await dispatcher.wait(record.id, 2.0)
    stuck, _ = await dispatcher.ingress.accept(
        "default", InboundMessage("http", "c", "u", "n", "x"), "dev:http:c:0"
    )
    await dispatcher.ingress.claim(stuck.id)  # crashed once
    await dispatcher.ingress.requeue(stuck.id, max_attempts=2)
    await dispatcher.ingress.claim(stuck.id)  # and again
    await dispatcher.sweep()
    dead = await dispatcher.ingress.get("default", stuck.id)

    assert (recovered.status, recovered.attempts) == ("done", 2)
    assert dead is not None
    assert (dead.status, dead.error_kind) == ("dead", "interrupted")
    await dispatcher.close()


async def test_an_in_memory_session_lock_reports_a_busy_session() -> None:
    locks = InMemorySessionLocks()

    async with locks.hold("t", "s", timeout_s=None):
        with pytest.raises(SessionBusyError):
            async with locks.hold("t", "s", timeout_s=0):
                pass
        with pytest.raises(SessionBusyError):
            async with locks.hold("t", "s", timeout_s=0.01):
                pass
        async with locks.hold("t", "other", timeout_s=0):
            pass
    async with locks.hold("t", "s", timeout_s=0):
        pass
