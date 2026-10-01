"""Closed loops 3 and 4 (package G): red flags and customer images, profile ``patient_channel``.

A red flag (with and without diacritics) reaches a doctor BEFORE any model call: an escalation (a
``triage_alert`` review item) is created, the fake LLM is never called and nothing is sent to the customer. An
image from a customer is flagged in the Inbox for a person; the system does not analyse it (no model call).
"""

from __future__ import annotations

import pytest

from pema.composition.testing import LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = pytest.mark.db

RED_FLAG_TEXTS = [
    "em bị chảy máu nhiều sau khi làm",
    "em bi chay mau khong cam duoc",
    "bé sot cao tu toi qua",
]


@pytest.mark.parametrize("text", RED_FLAG_TEXTS)
async def test_co_do_tao_escalation_va_llm_gia_khong_bi_goi(make_loop: LoopFactory, text: str) -> None:
    """cờ đỏ (có dấu, không dấu) -> triage_alert cho bác sĩ, LLM giả KHÔNG bị gọi, không tin nào ra khách"""
    model = scripted("câu này không bao giờ được gửi")
    async with make_loop.open(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        response = await loop.send_zalo_text(text, uid="demo-uid-025")
        assert response.status_code == 200, response.text

        (item,) = await loop.wait_review_items(1)

        assert item["kind"] == "triage_alert"
        assert item["status"] == "pending"
        assert item["risk_level"] == "red_flag"
        assert item["red_flags"], "mã cờ đỏ được ghi lại để bác sĩ thấy lý do"
        assert model.count == 0, "cờ đỏ phải chuyển bác sĩ TRƯỚC khi gọi LLM"
        assert loop.bot.sent == []

        doctor = await loop.staff("doctor.mai")
        listed = await doctor.get("/api/v1/review-items")
        assert listed.status_code == 200, listed.text
        mine = [row for row in listed.json()["items"] if row["id"] == str(item["id"])]
        assert mine
        assert mine[0]["requires_doctor"] is True


async def test_anh_khach_gui_gan_co_inbox_khong_phan_tich_va_khong_gui_gi(make_loop: LoopFactory) -> None:
    """ảnh khách gửi -> media_flag cho nhân viên, model không bị gọi (không phân tích), không tin nào ra khách"""
    model = scripted("không được phân tích ảnh")
    async with make_loop.open(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        response = await loop.send_zalo_image(uid="demo-uid-025")
        assert response.status_code == 200, response.text

        (item,) = await loop.wait_review_items(1)

        assert item["kind"] == "media_flag"
        assert item["status"] == "pending"
        assert model.count == 0, "ảnh bệnh nhân không đi qua model (không phân tích ảnh)"
        assert loop.bot.sent == []

        staff = await loop.staff("cs.maianh")
        listed = await staff.get("/api/v1/review-items")
        assert str(item["id"]) in {row["id"] for row in listed.json()["items"]}
