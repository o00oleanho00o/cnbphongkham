"""The conversations plugin: what it keeps and from whom, roles, the staff list, leaving a chat out, deleting old
messages, and the admin routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from fastapi import FastAPI

from agent_app.plugins import PluginContext
from agent_app.plugins.records import InMemoryPluginRecords
from agentcore.channels import ObservedMessage, Origin
from plugins.conversations.models import conversation_id
from plugins.conversations.plugin import ChannelSetting, ConversationsPlugin, Settings, role_of
from plugins.conversations.routes import conversations_routes

NOW = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)
CHANNEL = "zalo-a"


class FakeCtx:
    """Just enough of ``PluginContext`` for the plugin to register itself and keep its settings."""

    database = None
    logger = logging.getLogger("conversations-test")

    def __init__(self) -> None:
        self.storage = InMemoryPluginRecords().storage("conversations")
        self.handlers: list[Any] = []
        self.jobs: dict[str, Any] = {}

    def on_message(self, handler: Any) -> None:
        self.handlers.append(handler)

    def register_job(self, name: str, run: Any) -> None:
        self.jobs[name] = run


def _plugin(now: datetime = NOW) -> ConversationsPlugin:
    plugin = ConversationsPlugin(cast(PluginContext, FakeCtx()), clock=lambda: now)
    plugin.register()
    return plugin


def _said(
    text: str,
    *,
    origin: Origin = "inbound",
    sender: str = "u1",
    name: str = "Lan",
    message_id: str = "m1",
    thread: str = "t1",
    group: bool = False,
    at: datetime = NOW,
    channel: str = CHANNEL,
) -> ObservedMessage:
    return ObservedMessage(
        channel=channel,
        conversation_id=thread,
        sender_id=sender,
        message_id=message_id,
        text=text,
        origin=origin,
        is_group=group,
        sender_name=name,
        at=at,
    )


async def _switch_on(plugin: ConversationsPlugin, *, staff: list[str] | None = None, days: int = 0) -> None:
    await plugin.save_settings(
        Settings(channels={CHANNEL: ChannelSetting(enabled=True, staff=staff or [])}, retention_days=days)
    )


async def _kept(plugin: ConversationsPlugin, thread: str = "t1") -> list[tuple[str, str]]:
    messages = await plugin.store.messages(conversation_id(CHANNEL, thread), limit=100)
    return [(m.role, m.text) for m in messages]


async def test_nothing_is_kept_until_a_channel_is_switched_on() -> None:
    plugin = _plugin()

    await plugin.hear(_said("xin chào"))
    assert await plugin.store.conversations(channel=None, query="", limit=10, offset=0) == ([], 0)

    await _switch_on(plugin)
    await plugin.hear(_said("xin chào"))
    assert await _kept(plugin) == [("customer", "xin chào")]

    await plugin.hear(_said("kênh khác", channel="zalo-b", message_id="m9"))
    _, total = await plugin.store.conversations(channel=None, query="", limit=10, offset=0)
    assert total == 1


async def test_each_message_has_the_role_of_who_wrote_it() -> None:
    plugin = _plugin()
    await _switch_on(plugin, staff=["s1"])

    await plugin.hear(_said("giá niềng răng?", message_id="m1"))
    await plugin.hear(
        _said("Dạ chị cho em xin số ạ", origin="own", sender="me", name="Phòng khám", message_id="m2")
    )
    await plugin.hear(_said("em là nhân viên", sender="s1", name="Hà", message_id="m3"))
    await plugin.hear(
        _said("câu trả lời của agent", origin="agent", sender="", name="", message_id="m4#reply")
    )

    assert [role for role, _ in await _kept(plugin)] == ["customer", "staff", "staff", "agent"]


async def test_a_message_heard_twice_is_kept_once_and_counted_once() -> None:
    plugin = _plugin()
    await _switch_on(plugin)

    await plugin.hear(_said("một"))
    await plugin.hear(_said("một"))

    rows, total = await plugin.store.conversations(channel=CHANNEL, query="", limit=10, offset=0)
    assert total == 1
    assert rows[0].message_count == 1


async def test_a_direct_chat_is_titled_with_the_customer_and_a_group_is_not() -> None:
    plugin = _plugin()
    await _switch_on(plugin)

    await plugin.hear(_said("hello", name="Lan"))
    await plugin.hear(_said("hi all", name="Minh", thread="g1", group=True, message_id="m2"))

    rows, _ = await plugin.store.conversations(channel=CHANNEL, query="", limit=10, offset=0)
    titles = {row.external_id: (row.title, row.is_group) for row in rows}
    assert titles == {"t1": ("Lan", False), "g1": ("", True)}


async def test_putting_someone_on_the_staff_list_gives_their_earlier_messages_the_staff_role() -> None:
    plugin = _plugin()
    await _switch_on(plugin)
    await plugin.hear(_said("khách hỏi", sender="u1", message_id="m1"))
    await plugin.hear(_said("người này là nhân viên", sender="s1", name="Hà", message_id="m2"))
    assert [role for role, _ in await _kept(plugin)] == ["customer", "customer"]

    await _switch_on(plugin, staff=["s1"])
    assert [role for role, _ in await _kept(plugin)] == ["customer", "staff"]

    await _switch_on(plugin, staff=[])
    assert [role for role, _ in await _kept(plugin)] == ["customer", "customer"]


async def test_the_people_of_a_channel_are_listed_with_their_role() -> None:
    plugin = _plugin()
    await _switch_on(plugin, staff=["s1"])
    await plugin.hear(_said("a", sender="u1", name="Lan", message_id="m1"))
    await plugin.hear(_said("b", sender="u1", name="Lan", message_id="m2"))
    await plugin.hear(_said("c", sender="s1", name="Hà", message_id="m3"))
    await plugin.hear(_said("d", origin="own", sender="me", message_id="m4"))

    people = await plugin.store.people(CHANNEL)

    assert [(p.sender_id, p.name, p.messages, p.role) for p in people] == [
        ("u1", "Lan", 2, "customer"),
        ("s1", "Hà", 1, "staff"),
    ]


async def test_a_conversation_left_out_keeps_nothing_new_and_one_deleted_can_start_again() -> None:
    plugin = _plugin()
    await _switch_on(plugin)
    await plugin.hear(_said("một"))
    cid = conversation_id(CHANNEL, "t1")

    await plugin.store.set_excluded(cid, True)
    await plugin.hear(_said("hai", message_id="m2"))
    assert await _kept(plugin) == [("customer", "một")]

    await plugin.store.delete(cid)
    assert await _kept(plugin) == []
    await plugin.hear(_said("ba", message_id="m3"))
    assert await _kept(plugin) == [("customer", "ba")]


async def test_search_looks_in_the_title_and_the_messages() -> None:
    plugin = _plugin()
    await _switch_on(plugin)
    await plugin.hear(_said("Giá niềng răng bao nhiêu", thread="t1", name="Lan"))
    await plugin.hear(_said("đặt lịch khám", thread="t2", name="Minh", message_id="m2"))

    by_text, _ = await plugin.store.conversations(channel=None, query="niềng", limit=10, offset=0)
    by_title, _ = await plugin.store.conversations(channel=None, query="minh", limit=10, offset=0)

    assert [c.external_id for c in by_text] == ["t1"]
    assert [c.external_id for c in by_title] == ["t2"]


async def test_old_messages_are_deleted_after_the_retention_and_empty_chats_go() -> None:
    plugin = _plugin(now=NOW)
    await _switch_on(plugin, days=30)
    await plugin.hear(_said("cũ", thread="old", at=NOW - timedelta(days=40), message_id="m1"))
    await plugin.hear(_said("cũ", thread="mixed", at=NOW - timedelta(days=40), message_id="m2"))
    await plugin.hear(_said("mới", thread="mixed", at=NOW - timedelta(days=1), message_id="m3"))

    assert await plugin.clean() == 2

    rows, total = await plugin.store.conversations(channel=None, query="", limit=10, offset=0)
    assert [(c.external_id, c.message_count) for c in rows] == [("mixed", 1)]
    assert total == 1


async def test_without_a_retention_nothing_is_deleted() -> None:
    plugin = _plugin()
    await _switch_on(plugin, days=0)
    await plugin.hear(_said("cũ", at=NOW - timedelta(days=4000)))

    assert await plugin.clean() == 0
    assert await _kept(plugin) == [("customer", "cũ")]


def test_the_role_of_an_agent_reply_does_not_depend_on_the_staff_list() -> None:
    channel = ChannelSetting(enabled=True, staff=[""])
    assert role_of(_said("x", origin="agent", sender=""), channel) == "agent"


def _client(plugin: ConversationsPlugin) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(conversations_routes(plugin))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_the_routes_read_and_change_settings_conversations_and_people() -> None:
    plugin = _plugin()
    async with _client(plugin) as http:
        saved = await http.put(
            "/settings",
            json={
                "channels": {CHANNEL: {"enabled": True, "staff": ["s1", " s1 ", ""]}},
                "retention_days": 90,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["channels"][CHANNEL]["staff"] == ["s1"]
        assert (await http.get("/settings")).json()["retention_days"] == 90

        await plugin.hear(_said("giá bao nhiêu?"))
        await plugin.hear(_said("dạ 2 triệu ạ", origin="own", sender="me", message_id="m2"))
        listing = (await http.get("/conversations", params={"channel": CHANNEL, "q": "giá"})).json()
        assert listing["total"] == 1
        cid = listing["conversations"][0]["id"]

        opened = (await http.get(f"/conversations/{cid}")).json()
        assert [(m["role"], m["text"]) for m in opened["messages"]] == [
            ("customer", "giá bao nhiêu?"),
            ("staff", "dạ 2 triệu ạ"),
        ]
        assert (await http.get("/people", params={"channel": CHANNEL})).json()["people"][0][
            "sender_id"
        ] == "u1"

        left_out = await http.patch(f"/conversations/{cid}", json={"excluded": True})
        assert left_out.json()["excluded"] is True
        assert (await http.delete(f"/conversations/{cid}")).json() == {"deleted": True}
        assert (await http.get(f"/conversations/{cid}")).status_code == 404


async def test_the_routes_refuse_bad_settings_and_ids() -> None:
    plugin = _plugin()
    async with _client(plugin) as http:
        assert (await http.put("/settings", json={"channels": {"Bad Name": {}}})).status_code == 422
        assert (await http.put("/settings", json={"retention_days": -1})).status_code == 422
        assert (await http.get("/conversations/not-an-id")).status_code == 422
        assert (await http.get("/conversations", params={"channel": "Bad Name"})).status_code == 422
