"""Closed loop with the clinic tools (package G): the agent goes through the same actions as the UI.

``patient_channel`` only: a verified customer lets the model read the care context and PROPOSE an appointment (a
review item that staff confirm; confirming books it), an unverified one gets a marked failure that tells the
model to ask how to verify. ``staff_assistant`` never receives the clinic tools. The model is a fake that
records what it was given.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool, prompt_text, tool_keys, tra_loi
from pema.agent.tools.clinic_tools import NOT_VERIFIED
from pema.composition.testing import Loop, LoopFactory
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import CLINIC_TOOL_KEYS

pytestmark = [pytest.mark.db, pytest.mark.redis]

CLINIC_KEYS = {"patient.get_care_context", "appointment.book", "escalation.create"}


async def test_khach_da_xac_minh_model_tra_ho_so_cham_soc_qua_tool_va_ten_khong_lo(
    make_loop: LoopFactory,
) -> None:
    """đã xác minh -> tool patient.get_care_context chạy qua action của B1, kết quả có mốc chăm sóc, không có tên"""
    model = ScriptedModel(
        [
            lambda: goi_tool("patient.get_care_context"),
            lambda: tra_loi("Dạ chị còn 2 buổi trong liệu trình ạ."),
        ]
    )
    async with await make_loop.open_fresh(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await loop.send_zalo_text("cho em hỏi liệu trình của em", uid="demo-uid-025")

        items = await loop.wait_review_items(1)

        assert set(tool_keys(model.calls[0])) >= CLINIC_KEYS, "patient_channel nhận đủ tool phòng khám"
        tool_result = prompt_text(model.calls[1])
        assert "so_buoi_con_lai: 2" in tool_result
        assert "Bệnh nhân mẫu 025" not in tool_result, "kết quả tool không mang tên thật"
        assert items[0]["kind"] == "reply_draft"
        assert loop.bot.sent == []


async def test_khach_chua_xac_minh_tool_tra_loi_hong_bao_model_hoi_cach_xac_minh(
    make_loop: LoopFactory,
) -> None:
    """chưa xác minh -> tool trả kết quả lỗi có đánh dấu kèm hướng dẫn xác minh, hồ sơ không bị đụng tới"""
    model = ScriptedModel(
        [
            lambda: goi_tool("patient.get_care_context"),
            lambda: tra_loi("Dạ anh/chị cho em xin SĐT đăng ký ạ."),
        ]
    )
    async with await make_loop.open_fresh(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await loop.send_zalo_text("lịch của em khi nào", uid="uid-la-hoan-toan-chua-biet")

        await loop.wait_review_items(1)

        assert NOT_VERIFIED in prompt_text(model.calls[1])
        assert "so_buoi_con_lai" not in prompt_text(model.calls[1])


async def test_dat_lich_la_de_xuat_nhan_vien_xac_nhan_thi_lich_moi_duoc_dat_va_tin_moi_gui(
    make_loop: LoopFactory,
) -> None:
    """appointment.book -> review_item đề xuất (chưa có lịch); quản lý duyệt qua API -> lịch được đặt và tin đi"""
    model = ScriptedModel(
        [
            lambda: goi_tool(
                "appointment.book", {"starts_at": "2026-10-05T09:30:00+07:00", "duration_min": 30}
            ),
            lambda: tra_loi("Dạ em đã ghi nhận đề xuất, nhân viên sẽ xác nhận lại ạ."),
        ]
    )
    async with await make_loop.open_fresh(model, PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await loop.send_zalo_text("em muốn đặt lịch 9h30 sáng thứ hai", uid="demo-uid-025")

        items = await loop.wait_review_items(2)

        (proposal,) = [i for i in items if _is_appointment_proposal(i)]
        assert proposal["status"] == "pending"
        assert await _appointments_at(loop, "2026-10-05 09:30") == 0, "đề xuất chưa phải lịch hẹn"
        assert loop.bot.sent == []

        manager = await loop.staff("manager")
        approved = await manager.post(
            f"/api/v1/review-items/{proposal['id']}/approve",
            json={"version": proposal["version"], "send": True},
        )
        assert approved.status_code == 200, approved.text
        assert await _appointments_at(loop, "2026-10-05 09:30") == 1, "duyệt đề xuất thì lịch mới được đặt"
        await loop.wait_sent(1)


async def test_staff_assistant_khong_nhan_tool_phong_kham(make_loop: LoopFactory) -> None:
    """hồ sơ staff_assistant (hành vi zalo-agent gốc) không có tool phòng khám nào trong schema gửi cho model"""
    model = ScriptedModel([lambda: tra_loi("Dạ ok.")])
    async with make_loop.open(model, PolicyProfileKey.STAFF_ASSISTANT) as loop:
        await loop.send_zalo_text("chào em")

        await loop.wait_sent(1)

        offered = set(tool_keys(model.calls[0]))
        assert not offered & set(CLINIC_TOOL_KEYS)
        assert "get_datetime" in offered


def _is_appointment_proposal(item: dict[str, Any]) -> bool:
    payload: Any = item.get("payload")
    return isinstance(payload, dict) and payload.get("proposal") == "appointment"  # type: ignore[reportUnknownMemberType]


async def _appointments_at(loop: Loop, local_start: str) -> int:
    async with loop.api.db.session(loop.clinic_id) as session:
        return int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM clinic.appointment a JOIN clinic.patient p "
                        "ON p.id = a.patient_id AND p.clinic_id = a.clinic_id "
                        "WHERE p.code = 'P025' AND to_char(a.starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh', "
                        "'YYYY-MM-DD HH24:MI') = :start AND a.status <> 'cancelled'"
                    ),
                    {"start": local_start},
                )
            ).scalar_one()
        )
