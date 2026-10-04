"""Closed loop 7 (package ST-R): live events and presence over the REAL Redis, API and worker.

The webhook is handled by the API process, the draft is written by the worker process: an event of each reaches
the stream of a signed-in member of staff through the Redis channel of the installation. LLM and Zalo are
fakes."""

from __future__ import annotations

import json

import pytest

from pema.composition.testing import Loop, LoopFactory, scripted
from pema.live.testing import OpenStream, session_cookie
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]

DRAFT = "Dạ chào chị, da hơi đỏ nhẹ sau laser trong 1-2 ngày là thường gặp ạ."
CUSTOMER_TEXT = "da em hơi đỏ sau buổi hôm qua có sao không ạ"


def events_in(stream: OpenStream) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for line in stream.body.split("\n"):
        if line.startswith("data: "):
            found.append(json.loads(line.removeprefix("data: ")))
    return found


async def _open(loop: Loop, user_key: str) -> OpenStream:
    staff = await loop.staff(user_key)
    stream = await OpenStream(loop.app, "/api/v1/events", cookie=session_cookie(staff)).start()
    assert stream.status == 200
    await stream.read_until("retry:")
    return stream


async def test_an_inbound_message_and_the_draft_of_the_worker_both_reach_the_stream_through_redis(
    make_loop: LoopFactory,
) -> None:
    """tin khách (API) và bản nháp (worker) đều tới luồng sự kiện của nhân viên qua Redis; payload chỉ có type và id"""
    async with make_loop.open(scripted(DRAFT), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        stream = await _open(loop, "owner")
        try:
            response = await loop.send_zalo_text(CUSTOMER_TEXT, uid="demo-uid-025")
            assert response.status_code == 200, response.text
            await stream.read_until("inbox.changed")  # written by the API process
            (item,) = await loop.wait_review_items(1)  # written by the worker process
            chunk = await stream.read_until("review.changed")
            assert json.loads(chunk.removeprefix("data: ")) == {
                "type": "review.changed",
                "id": str(item["id"]),
            }
            for event in events_in(stream):
                assert set(event) == {"type", "id"}
            assert CUSTOMER_TEXT not in stream.body
            assert DRAFT not in stream.body
        finally:
            await stream.close()


async def test_a_colleague_sees_who_is_on_the_conversation_through_redis_and_it_expires_with_leave(
    make_loop: LoopFactory,
) -> None:
    """hai nhân viên cùng mở một hội thoại thấy nhau (Redis thật); rời đi thì biến mất ngay"""
    async with make_loop.open(scripted(DRAFT), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        conversation_id = loop.world.conversation_id
        mai_anh = await loop.staff("cs.maianh")
        thu = await loop.staff("cs.thu")
        stream = await _open(loop, "owner")
        try:
            beat = await mai_anh.post(
                f"/api/v1/conversations/{conversation_id}/presence", json={"state": "replying"}
            )
            assert beat.status_code == 204, beat.text
            chunk = await stream.read_until("presence.changed")
            assert json.loads(chunk.removeprefix("data: ")) == {
                "type": "presence.changed",
                "id": str(conversation_id),
            }
            seen = (await thu.get(f"/api/v1/conversations/{conversation_id}")).json()["viewers"]
            assert [(v["name"], v["state"]) for v in seen] == [("CSKH Mai Anh (mẫu)", "replying")]
            assert (await mai_anh.get(f"/api/v1/conversations/{conversation_id}")).json()["viewers"] == []
            left = await mai_anh.delete(f"/api/v1/conversations/{conversation_id}/presence")
            assert left.status_code == 204
            assert (await thu.get(f"/api/v1/conversations/{conversation_id}")).json()["viewers"] == []
        finally:
            await stream.close()
