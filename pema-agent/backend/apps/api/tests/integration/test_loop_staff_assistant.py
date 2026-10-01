"""Closed loop 1 (package G): profile ``staff_assistant``.

A synthetic Zalo update -> webhook (API process) -> allowlist -> history AND Inbox -> batcher -> Redis turn
queue -> turn worker (worker process, role ``agent_worker``) -> engine with a TOOL -> the answer goes straight
to the channel. The LLM and Zalo are fakes; everything between them is the real code over a real Postgres and
Redis.
"""

from __future__ import annotations

import pytest

from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool, tra_loi
from pema.composition.testing import Loop, LoopFactory
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def test_staff_assistant_tin_zalo_den_engine_goi_tool_roi_tra_loi_gui_thang(
    make_loop: LoopFactory,
) -> None:
    """tin Zalo -> webhook -> batcher -> TurnQueue -> engine với tool -> trả lời gửi thẳng, không qua duyệt"""
    model = ScriptedModel(
        [
            lambda: goi_tool("get_datetime"),
            lambda: tra_loi("Dạ bây giờ là giờ hành chính, em đã xem đồng hồ giúp anh ạ."),
        ]
    )
    async with make_loop.open(model, PolicyProfileKey.STAFF_ASSISTANT) as loop:
        response = await loop.send_zalo_text("mấy giờ rồi em")
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True

        sent = await loop.wait_sent(1)

        assert sent[0][0] == "demo-uid-025"
        assert "đồng hồ" in sent[0][1]
        assert model.count == 2, "bước 1 gọi tool get_datetime, bước 2 trả lời"
        await _assert_inbox_and_history(loop)


async def _count(loop: Loop, sql: str, **params: object) -> int:
    from sqlalchemy import text

    async with loop.api.db.session(loop.clinic_id) as session:
        return int((await session.execute(text(sql), params)).scalar_one())


async def _assert_inbox_and_history(loop: Loop) -> None:
    """The message is in the Inbox of record (clinic.message) and in the LLM history (agent.history); the
    reply was written to both after it was sent; the turn closed with one usage row and a step trace."""
    inbound = await _count(
        loop, "SELECT count(*) FROM clinic.message WHERE direction = 'inbound' AND body = 'mấy giờ rồi em'"
    )
    assert inbound == 1
    await loop.wait_for(lambda: _history_rows(loop), "reply written to agent.history after it was sent")
    await loop.wait_for(lambda: _usage_rows(loop), "turn closed with a usage row")
    steps = await _count(
        loop,
        "SELECT count(*) FROM agent.usage_steps s JOIN agent.usage u "
        "ON u.id = s.turn_id AND u.clinic_id = s.clinic_id WHERE u.account_id = :account",
        account=loop.account_id,
    )
    assert steps == 2
    await loop.wait_for(lambda: _outbound_rows(loop), "the sent reply recorded in the Inbox of record")


async def _history_rows(loop: Loop) -> bool:
    sql = "SELECT count(*) FROM agent.history WHERE account_id = :account"
    return await _count(loop, sql, account=loop.account_id) >= 2


async def _usage_rows(loop: Loop) -> bool:
    sql = "SELECT count(*) FROM agent.usage WHERE account_id = :account"
    return await _count(loop, sql, account=loop.account_id) == 1


async def _outbound_rows(loop: Loop) -> bool:
    sql = "SELECT count(*) FROM clinic.message WHERE direction = 'outbound' AND status = 'sent'"
    return await _count(loop, sql) >= 1
