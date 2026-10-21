"""The crm plugin against a fake crm-signer (docs/PLAN-crm-plugin.md 3.3, 4): the person comes from the chat and
never from the model, the plugin sends no credential, writes carry an idempotency key, and every failure is a
sentence the agent can pass on."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from agent_app.plugins import PluginContext, PluginHost, discover
from agent_app.runtime import BUNDLED_PLUGINS
from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec
from plugins.crm import IN_GROUP, NO_PERSON, CrmTools
from plugins.crm.client import CLOSED, UNREACHABLE, CrmClient
from plugins.crm.store import MemoryReminderStore

BASE = "http://crm-signer:8090/agent-gateway"
ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
VISIT = str(uuid4())
TURN = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
PERSON_FIELDS = {"channel", "external_id", "user_id", "patient_id", "person", "contact"}


class Signer:
    """A fake crm-signer: records each request and answers from ``replies`` (default 200 with ``body``)."""

    def __init__(self, body: Any = None, replies: list[httpx.Response] | None = None) -> None:
        self.seen: list[httpx.Request] = []
        self.body: Any = {} if body is None else body
        self.replies = replies or []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.replies.pop(0) if self.replies else httpx.Response(200, json=self.body)


class Chat:
    """What the tools need of the plugin context: which plugin a channel comes from."""

    def channel_plugin(self, channel: str) -> str | None:
        return "zalo" if channel.startswith("zalo-") else None


def _tools(signer: Signer) -> dict[str, ToolSpec[Any]]:
    client = CrmClient(BASE, timeout_s=5, transport=signer.transport)
    return {s.name: s for s in CrmTools(cast(PluginContext, Chat()), client, ZONE).specs()}


def _ctx(channel: str | None = "zalo-acc1", user: str | None = "u123", now: datetime = TURN) -> ToolContext:
    return ToolContext(session_id="s1", user_id=user, channel=channel, now=now)


async def _run(spec: ToolSpec[Any], args: dict[str, Any], ctx: ToolContext | None = None) -> ToolOutput:
    return await spec.handler(spec.args_model.model_validate(args), ctx or _ctx())


def _visit(**over: Any) -> dict[str, Any]:
    row = {"id": VISIT, "starts_at": "2026-10-22T09:30:00+07:00", "duration_min": 30, "status": "booked"}
    return row | over


def test_the_plugin_registers_the_seven_tools_and_only_two_read() -> None:
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, {})
    host.enable("crm", {})
    specs = {t.name: t for t in host.contributions().tools}

    assert set(specs) == {
        "crm_free_slots",
        "crm_save_contact",
        "crm_book_appointment",
        "crm_my_appointments",
        "crm_confirm_appointment",
        "crm_reschedule_appointment",
        "crm_cancel_appointment",
    }
    assert {n for n, s in specs.items() if s.read_only} == {"crm_free_slots", "crm_my_appointments"}


def test_no_tool_lets_the_model_name_a_person() -> None:
    for spec in _tools(Signer()).values():
        assert not set(spec.args_model.model_fields) & PERSON_FIELDS, spec.name


@pytest.mark.parametrize(
    ("channel", "user"),
    [(None, "u1"), ("zalo-acc1", None), ("http", "sso:staff"), ("cli", "cli"), ("zalo-acc1", "u/../x")],
)
async def test_a_turn_without_a_chat_person_is_refused_and_nothing_is_sent(
    channel: str | None, user: str | None
) -> None:
    signer = Signer()
    out = await _run(_tools(signer)["crm_my_appointments"], {}, _ctx(channel, user))

    assert out.is_error
    assert out.text == NO_PERSON
    assert signer.seen == []


async def test_the_person_is_the_chats_and_no_credential_is_sent() -> None:
    signer = Signer(body=[_visit()])
    out = await _run(_tools(signer)["crm_my_appointments"], {})

    sent = signer.seen[0]
    assert str(sent.url) == f"{BASE}/contacts/zalo-acc1/u123/appointments"
    assert "authorization" not in sent.headers
    assert "22/10/2026 09:30, 30 phút, đã đặt, chưa xác nhận" in out.text
    assert VISIT in out.text


async def test_free_slots_asks_for_the_days_and_shows_local_times() -> None:
    body = {"duration_min": 30, "days": [{"day": "2026-10-22", "starts": ["2026-10-22T02:00:00+00:00"]}]}
    signer = Signer(body=body)
    out = await _run(_tools(signer)["crm_free_slots"], {"day_from": "2026-10-22", "days": 2})

    assert signer.seen[0].url.params["days"] == "2"
    assert "2026-10-22: 09:00" in out.text


async def test_save_contact_sends_what_the_person_said() -> None:
    signer = Signer(body={"created": True, "messages_consent": True})
    out = await _run(
        _tools(signer)["crm_save_contact"],
        {"full_name": "Nguyễn Văn A", "phone": "0901 234 567", "messages_consent": True},
    )

    sent = signer.seen[0]
    assert sent.method == "PUT"
    assert str(sent.url) == f"{BASE}/contacts/zalo-acc1/u123"
    assert json.loads(sent.content)["phone"] == "0901 234 567"
    assert "hồ sơ mới" in out.text


async def test_a_time_without_offset_is_the_clinics_and_a_retry_in_the_turn_reuses_its_key() -> None:
    signer = Signer(body=_visit())
    book = _tools(signer)["crm_book_appointment"]
    args = {"starts_at": "2026-10-22T09:30", "note": "triệt lông"}

    await _run(book, args)
    await _run(book, args)
    await _run(book, args, _ctx(now=datetime(2026, 10, 21, 10, 0, tzinfo=UTC)))

    first, retry, later = signer.seen
    assert json.loads(first.content)["starts_at"] == "2026-10-22T09:30:00+07:00"
    assert first.headers["idempotency-key"] == retry.headers["idempotency-key"]
    assert later.headers["idempotency-key"] != first.headers["idempotency-key"]


async def test_reschedule_confirm_and_cancel_go_to_the_visit_of_this_person() -> None:
    signer = Signer(body=_visit(status="cancelled"))
    tools = _tools(signer)

    await _run(
        tools["crm_reschedule_appointment"], {"appointment_id": VISIT, "starts_at": "2026-10-23T10:00+07:00"}
    )
    await _run(tools["crm_confirm_appointment"], {"appointment_id": VISIT})
    out = await _run(tools["crm_cancel_appointment"], {"appointment_id": VISIT, "reason": "bận"})

    paths = [r.url.path for r in signer.seen]
    person = "/agent-gateway/contacts/zalo-acc1/u123/appointments"
    assert paths == [f"{person}/{VISIT}/reschedule", f"{person}/{VISIT}/confirm", f"{person}/{VISIT}/cancel"]
    assert "idempotency-key" in signer.seen[0].headers
    assert "đã hủy" in out.text


@pytest.mark.parametrize(
    ("reply", "sentence"),
    [
        (
            httpx.Response(409, json={"error": {"code": "conflict", "message": "Giờ này vừa có người đặt."}}),
            "Giờ này vừa có người đặt.",
        ),
        (httpx.Response(409, text="no json"), "Lịch vừa thay đổi"),
        (httpx.Response(403, json={"error": {"message": "secret detail"}}), CLOSED),
        (httpx.Response(502, json={"error": {"code": "upstream_unavailable"}}), UNREACHABLE),
        (httpx.Response(302, headers={"location": "http://evil.example/"}), UNREACHABLE),
    ],
)
async def test_every_failure_is_a_sentence(reply: httpx.Response, sentence: str) -> None:
    signer = Signer(replies=[reply])
    out = await _run(_tools(signer)["crm_my_appointments"], {})

    assert out.is_error
    assert out.text.startswith(sentence)
    assert len(signer.seen) == 1  # a redirect is not followed


async def test_crm_signer_down_is_a_sentence() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = CrmClient(BASE, timeout_s=5, transport=httpx.MockTransport(refuse))
    tools = {s.name: s for s in CrmTools(cast(PluginContext, Chat()), client, ZONE).specs()}
    out = await _run(tools["crm_free_slots"], {"day_from": "2026-10-22"})

    assert out.is_error
    assert out.text == UNREACHABLE


async def test_in_a_group_chat_every_tool_refuses_and_nothing_is_sent() -> None:
    signer = Signer(body=[_visit()])
    group = ToolContext(
        session_id="s1", user_id="u123", channel="zalo-acc1", conversation_id="g1", is_group=True
    )

    for name, spec in _tools(signer).items():
        out = await spec.handler(spec.args_model.model_construct(), group)
        assert out.is_error, name
        assert out.text == IN_GROUP

    assert signer.seen == []


async def test_a_one_to_one_chat_is_remembered_for_its_reminders() -> None:
    signer = Signer(body=[])
    store = MemoryReminderStore()
    client = CrmClient(BASE, timeout_s=5, transport=signer.transport)
    tools = {s.name: s for s in CrmTools(cast(PluginContext, Chat()), client, ZONE, store).specs()}
    chat = ToolContext(session_id="s1", user_id="u123", channel="zalo-acc1", conversation_id="u123", now=TURN)

    await tools["crm_my_appointments"].handler(tools["crm_my_appointments"].args_model(), chat)

    person = await store.person("zalo-acc1", "u123")
    assert person is not None
    assert person.conversation_id == "u123"


def test_a_zalo_group_message_is_a_group_for_the_core() -> None:
    from agentcore.channels import in_group
    from plugins.zalo.inbound import ZaloInbound, to_inbound

    def said(is_group: bool) -> ZaloInbound:
        return ZaloInbound(
            account_id="a",
            thread_id="t",
            is_group=is_group,
            sender_id="s",
            sender_name="",
            message_id="m",
            text="hi",
        )

    assert in_group(to_inbound(said(True)).metadata)
    assert not in_group(to_inbound(said(False)).metadata)
