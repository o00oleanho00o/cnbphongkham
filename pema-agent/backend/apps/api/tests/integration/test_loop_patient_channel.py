"""Closed loop 2 (package G): profile ``patient_channel``.

Nothing the agent writes reaches a patient before a person approves it. An unverified customer gets a draft
that asks for verification; a verified one gets a draft that a member of staff approves through the API, and
only then does the text leave through the channel. The LLM and Zalo are fakes.
"""

from __future__ import annotations

import pytest

from pema.agent.streaming_model_test_helper import prompt_text
from pema.composition.testing import LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]

ASK_VERIFY = "Dạ anh/chị cho em xin số điện thoại đã đăng ký tại phòng khám để nhân viên xác minh ạ."
DRAFT = "Dạ chào chị, da hơi đỏ nhẹ sau laser trong 1-2 ngày là thường gặp ạ."


async def test_patient_channel_khach_chua_xac_minh_duoc_nhac_xac_minh_va_ban_nhap_vao_hang_duyet(
    make_loop: LoopFactory,
) -> None:
    """khách chưa xác minh -> engine nhắc xác minh (persona), câu trả lời thành nháp chờ duyệt, KHÔNG gửi"""
    model = scripted(ASK_VERIFY)
    async with make_loop.open(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        response = await loop.send_zalo_text("cho mình hỏi lịch hẹn của mình", uid="uid-la-chua-xac-minh")
        assert response.status_code == 200, response.text

        (item,) = await loop.wait_review_items(1)

        assert item["kind"] == "reply_draft"
        assert item["status"] == "pending"
        assert item["draft_text"] == ASK_VERIFY
        assert loop.bot.sent == [], "patient_channel: không có tin nào ra khỏi hệ thống khi chưa ai duyệt"
        system = model.calls[0].system
        assert "CHƯA được xác minh" in system, "persona phải dặn model hỏi cách xác minh"
        assert "Khách mẫu 025" not in prompt_text(model.calls[0]), "chưa xác minh thì không nhắc tên ai"


async def test_patient_channel_khach_da_xac_minh_nhan_vien_duyet_qua_api_roi_moi_gui_qua_kenh(
    make_loop: LoopFactory,
) -> None:
    """khách đã xác minh -> engine soạn nháp -> review_item -> nhân viên duyệt qua API -> gửi qua kênh"""
    model = scripted(DRAFT)
    async with make_loop.open(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await loop.send_zalo_text("da em hơi đỏ sau buổi hôm qua có sao không ạ", uid="demo-uid-025")

        (item,) = await loop.wait_review_items(1)
        assert item["kind"] == "reply_draft"
        assert item["draft_text"] == DRAFT
        assert "CHƯA được xác minh" not in model.calls[0].system, (
            "đã xác minh thì không có dòng nhắc xác minh"
        )
        assert loop.bot.sent == []

        staff = await loop.staff("cs.maianh")
        listed = await staff.get("/api/v1/review-items")
        assert listed.status_code == 200, listed.text
        assert str(item["id"]) in {row["id"] for row in listed.json()["items"]}

        approved = await staff.post(
            f"/api/v1/review-items/{item['id']}/approve", json={"version": item["version"], "send": True}
        )
        assert approved.status_code == 200, approved.text

        sent = await loop.wait_sent(1)
        assert sent[0] == ("demo-uid-025", DRAFT, None)
        assert approved.json()["status"] == "approved"
