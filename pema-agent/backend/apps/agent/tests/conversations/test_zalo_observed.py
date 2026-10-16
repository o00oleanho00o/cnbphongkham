"""Zalo and the conversations plugin end to end: what a personal account hears (answered or not), what its owner
types on another device, and what the agent says is kept with the right role; the agent's own replies coming
back as the account's messages are not kept twice."""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any

import pytest

from agent_app.plugins import PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore.harness.model.scripted import ScriptedModel, reply
from plugins.conversations.models import conversation_id
from tests.zalo.test_personal_channel import (
    CREDENTIAL,
    HEADERS,
    KEY,
    SECRET,
    FakeBridge,
    Setup,
)

CHANNEL = "zalo-nick"
CONVERSATIONS = "/v1/plugins/conversations"


def _runtime(tmp_path: Path, bridge: FakeBridge) -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        textwrap.dedent("""
        [agent]
        name = "t"
        system_prompt = "p"

        [plugins]
        enabled = ["zalo", "conversations"]
        """),
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY, "AGENT_DATA_DIR": str(tmp_path / "data")}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("zalo", {"bridge_transport": bridge.transport, "bridge_secret": SECRET, "echo_wait_s": 0.05})
    host.enable("conversations")
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host)


def _message(
    text: str,
    *,
    sender: str = "u1",
    name: str = "An",
    group: str | None = None,
    mentions: list[str] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "msgId": f"m-{text}",
        "cliMsgId": "c1",
        "uidFrom": sender,
        "idTo": group or "me-1",
        "dName": name,
        "msgType": "webchat",
        "ts": "1760000000000",
        "content": text,
    }
    if mentions:
        data["mentions"] = [{"uid": uid, "pos": 0, "len": 3} for uid in mentions]
    return {
        "type": "message",
        "message": {"type": 1 if group else 0, "threadId": group or sender, "data": data},
    }


def _from_the_owner(text: str, *, message_id: str, thread: str = "u1") -> dict[str, Any]:
    return {
        "type": "message",
        "message": {
            "type": 0,
            "threadId": thread,
            "isSelf": True,
            "data": {
                "msgId": message_id,
                "cliMsgId": "c9",
                "uidFrom": "me-1",
                "idTo": thread,
                "dName": "Phòng khám",
                "msgType": "webchat",
                "content": text,
            },
        },
    }


async def _started(
    tmp_path: Path,
    bridge: FakeBridge,
    *,
    staff: list[str] | None = None,
    listen: list[str] | None = None,
) -> Setup:
    """A running account; ``listen`` are the groups it listens to (none: only the one-to-one chats)."""
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal(listen_group_ids=listen or [])
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()
    saved = await setup.client.put(
        f"{CONVERSATIONS}/settings",
        json={"channels": {CHANNEL: {"enabled": True, "staff": staff or []}}},
        headers=HEADERS,
    )
    assert saved.status_code == 200
    return setup


async def _chat(setup: Setup, thread: str) -> list[tuple[str, str, bool]]:
    """(role, text, answered) of a chat's messages, oldest first."""
    found = await setup.client.get(
        f"{CONVERSATIONS}/conversations/{conversation_id(CHANNEL, thread)}", headers=HEADERS
    )
    if found.status_code == 404:
        return []
    return [(m["role"], m["text"], m["answered"]) for m in found.json()["messages"]]


async def _until_kept(setup: Setup, thread: str, count: int) -> list[tuple[str, str, bool]]:
    for _ in range(300):
        kept = await _chat(setup, thread)
        if len(kept) >= count:
            return kept
        await setup.hub.tick()
        await asyncio.sleep(0.01)
    raise AssertionError(f"{thread} has {len(await _chat(setup, thread))} messages, not {count}")


@pytest.fixture
def bridge() -> FakeBridge:
    return FakeBridge()


async def test_a_group_message_nobody_asked_the_agent_about_is_kept_and_a_mentioned_one_and_its_reply_too(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = await _started(tmp_path, bridge, listen=["g1"])

    await setup.event("nick", _message("giá niềng răng bao nhiêu?", group="g1"))
    await setup.event(
        "nick", _message("@bot đặt lịch", group="g1", mentions=["me-1"], sender="u2", name="Bình")
    )
    kept = await _until_kept(setup, "g1", 3)

    assert kept[0] == ("customer", "giá niềng răng bao nhiêu?", False)
    assert kept[1] == ("customer", "@bot đặt lịch", True)
    assert kept[2][0] == "agent"
    assert len(bridge.sent) == 1  # the agent answered only the mention
    await setup.close()


async def test_a_group_off_the_list_is_not_kept_even_when_the_agent_answers_a_mention_there(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = await _started(tmp_path, bridge, listen=["g-chosen"])

    await setup.event("nick", _message("chuyện riêng của nhóm", group="g-other"))
    await setup.event(
        "nick", _message("@bot giá?", group="g-other", mentions=["me-1"], sender="u2", name="Bình")
    )
    await setup.event("nick", _message("nhóm được chọn", group="g-chosen"))
    await setup.event("nick", _message("chào", sender="u1"))
    await setup.until(lambda: len(bridge.sent) >= 2)  # the mention in the other group and the private chat
    await _until_kept(setup, "g-chosen", 1)
    await _until_kept(setup, "u1", 2)

    assert await _chat(setup, "g-other") == []  # neither the messages nor the agent's reply
    assert [role for role, _, _ in await _chat(setup, "g-chosen")] == ["customer"]
    await setup.close()


async def test_choosing_a_group_takes_effect_at_once_and_unchoosing_stops_it(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = await _started(tmp_path, bridge)

    await setup.event("nick", _message("trước khi chọn", group="g1"))
    await setup.client.patch(
        "/v1/plugins/zalo/accounts/nick", json={"listen_group_ids": ["g1"]}, headers=HEADERS
    )
    await setup.event("nick", _message("sau khi chọn", group="g1"))
    await _until_kept(setup, "g1", 1)
    await setup.client.patch("/v1/plugins/zalo/accounts/nick", json={"listen_group_ids": []}, headers=HEADERS)
    await setup.event("nick", _message("sau khi bỏ chọn", group="g1"))
    await asyncio.sleep(0.2)

    assert [text for _, text, _ in await _chat(setup, "g1")] == ["sau khi chọn"]
    await setup.close()


async def test_what_the_owner_types_on_another_device_is_kept_as_staff_and_never_answered(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = await _started(tmp_path, bridge)

    await setup.event("nick", _message("giá khám bao nhiêu ạ?", sender="u1"))
    await setup.until(lambda: bridge.sent)
    await setup.event("nick", _from_the_owner("Dạ 200k ạ, chị đặt lịch giúp em nhé", message_id="owner-1"))
    kept = await _until_kept(setup, "u1", 3)

    roles = [(role, text) for role, text, _ in kept]
    assert ("customer", "giá khám bao nhiêu ạ?") in roles
    assert ("staff", "Dạ 200k ạ, chị đặt lịch giúp em nhé") in roles
    assert len(bridge.sent) == 1  # the owner's own message never ran a turn
    await setup.close()


async def test_the_agents_own_reply_coming_back_as_the_accounts_message_is_not_kept_twice(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = await _started(tmp_path, bridge)

    await setup.event("nick", _message("chào", sender="u1"))
    await setup.until(lambda: bridge.sent)
    await _until_kept(setup, "u1", 2)
    # the bridge answered the send with msg_id "out-1"; the listener now hears the same message as the account's
    await setup.event("nick", _from_the_owner(bridge.sent[0]["text"], message_id="out-1"))
    await asyncio.sleep(0.3)

    assert [role for role, _, _ in await _chat(setup, "u1")] == ["customer", "agent"]
    await setup.close()


async def test_a_person_on_the_staff_list_is_kept_as_staff(tmp_path: Path, bridge: FakeBridge) -> None:
    setup = await _started(tmp_path, bridge, staff=["s1"], listen=["g1"])

    await setup.event("nick", _message("em đã gọi cho khách", group="g1", sender="s1", name="Hà"))
    kept = await _until_kept(setup, "g1", 1)

    assert kept == [("staff", "em đã gọi cho khách", False)]
    await setup.close()


async def test_nothing_is_kept_from_a_channel_that_is_not_switched_on(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    setup = Setup(_runtime(tmp_path, bridge))
    await setup.personal()
    await setup.event("nick", {"type": "credential_updated", "credential": CREDENTIAL})
    await setup.hub.sync()

    await setup.event("nick", _message("xin chào", group="g1"))
    await asyncio.sleep(0.1)

    assert await _chat(setup, "g1") == []
    await setup.close()


async def test_how_the_staff_answered_a_customer_reaches_the_agent_when_another_customer_asks_the_same(
    tmp_path: Path, bridge: FakeBridge
) -> None:
    model = ScriptedModel([reply("Dạ em xin thông tin ạ"), reply("Dạ em hỏi lại chị một chút nhé")])
    setup = await _started(tmp_path, bridge)
    setup.runtime.live.use_model(model)
    staff_answer = "Dạ chị cho em hỏi da mình bị nám lâu chưa ạ, em tư vấn gói rồi báo giá chị nhé"

    await setup.event(
        "nick", _message("Cho mình hỏi giá điều trị nám bao nhiêu vậy ạ", sender="u1", name="Lan")
    )
    await setup.until(lambda: len(bridge.sent) == 1)
    await setup.event("nick", _from_the_owner(staff_answer, message_id="owner-7", thread="u1"))
    await _until_kept(setup, "u1", 3)
    refreshed = await setup.client.post(f"{CONVERSATIONS}/scenarios/refresh", headers=HEADERS)
    first_request = len(model.requests)

    await setup.event("nick", _message("Giá điều trị nám là bao nhiêu thế em", sender="u2", name="Minh"))
    await setup.until(lambda: len(bridge.sent) == 2)

    assert refreshed.json()["new"] == 1
    asked_first = " ".join(m.text() for m in model.requests[0].messages)
    asked_second = " ".join(m.text() for m in model.requests[first_request].messages)
    assert "Kịch bản mẫu" not in asked_first
    assert "Kịch bản mẫu" in asked_second
    assert staff_answer in asked_second
    assert "Lan" not in asked_second.split("Kịch bản mẫu", 1)[1]
    await setup.close()
