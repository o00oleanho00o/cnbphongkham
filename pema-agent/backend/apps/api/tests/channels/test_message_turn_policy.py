"""The policy seams of the turn pipeline (PLAN-AI01 section 5; new tests, no zalo-agent original).

``PolicyHooks.on_outbound`` only DECIDES; this pipeline (the CALLER) opens the review item with a stable ``job_id``
and the Inbox ``conversation_ref``, and never sends what the policy held. A hand-off by the ``before_llm`` hook
(red flag, patient media) sends nothing automatic. The canned technical apology goes through the same gate.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from pema.channels.deliver_chat_reply import DeliveryDeps, deliver_chat_reply
from pema.channels.pipeline_testing import FakeActions, FakeEngine, TurnRig, answer
from pema.channels.send_reply_in_parts import ReplyTarget, reset_khu_trung_bao_loi
from pema.channels.zalo_personal.kenh_ca_nhan import duong_gui_zca_js
from pema.policy.review import media_flag_job_id, red_flag_job_id
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TokenUsage, TurnCallbacks
from pema_contracts.channel import ThreadKind
from pema_contracts.conversations import MessageStatus
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    OutboundAction,
    OutboundDecision,
    OutboundOrigin,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyProfileKey,
)
from pema_contracts.review import ReviewKind, RiskLevel
from pema_contracts.testing import FAKE_CLINIC_ID
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind

THREAD = "t-policy"


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_khu_trung_bao_loi()
    yield
    reset_khu_trung_bao_loi()


class DecidingHooks(PermissivePolicyHooks):
    def __init__(self, action: OutboundAction) -> None:
        self.action = action
        self.calls: list[tuple[str, OutboundOrigin, bool]] = []

    async def on_outbound(
        self, ctx: PolicyContext, text: str, *, proactive: bool, origin: OutboundOrigin
    ) -> OutboundDecision:
        self.calls.append((text, origin, proactive))
        return OutboundDecision(action=self.action, reason="test")


def patient_rig(
    hooks: DecidingHooks, engine: FakeEngine | None = None, *, actions: FakeActions | None = None
) -> TurnRig:
    return TurnRig.create(
        engine=engine or FakeEngine(script=answer("Dạ em gửi anh lịch hẹn ạ")),
        profile=PolicyProfileKey.PATIENT_CHANNEL,
        hooks=hooks,
        actions=actions if actions is not None else FakeActions(),
    )


async def test_hold_for_review_khong_gui_gi_va_mo_review_item_ban_nhap_co_conversation_ref() -> None:
    hooks = DecidingHooks(OutboundAction.HOLD_FOR_REVIEW)
    rig = patient_rig(hooks)
    assert rig.actions is not None
    job_id = uuid4()

    await rig.run([await rig.receive("cho mình hỏi lịch hẹn", "m1", thread_id=THREAD)], job_id=job_id)

    assert rig.api.sent == [], "chính sách giữ lại thì KHÔNG một tin nào ra kênh"
    [item] = rig.actions.created
    assert item.kind is ReviewKind.REPLY_DRAFT
    assert item.draft_text == "Dạ em gửi anh lịch hẹn ạ"
    assert item.conversation_ref == str(rig.actions.conversation_id)
    assert item.job_id == f"{job_id}:turn_reply", "ổn định theo job: chạy lại không đẻ thêm bản nháp"
    assert item.payload is not None
    assert item.payload["origin"] == "turn_reply"
    assert [role for role, _ in rig.conversation.contents(rig.config.id, THREAD)] == ["user"], (
        "chưa gửi thì chưa vào history: history phải khớp cái người dùng nhìn thấy"
    )
    assert hooks.calls == [("Dạ em gửi anh lịch hẹn ạ", OutboundOrigin.TURN_REPLY, False)]
    assert rig.actions.outbound == [], "bản nháp chờ duyệt không phải một tin đã gửi"


async def test_hold_for_review_chay_lai_cung_job_chi_co_mot_review_item() -> None:
    rig = patient_rig(DecidingHooks(OutboundAction.HOLD_FOR_REVIEW))
    assert rig.actions is not None
    job_id = uuid4()
    msg = await rig.receive("cho mình hỏi lịch hẹn", "m1", thread_id=THREAD)

    await rig.run([msg], job_id=job_id)
    await rig.run([msg], job_id=job_id)

    assert len(rig.actions.created) == 2, "hai lần gọi create_review_item"
    assert len(rig.actions.review_items) == 1, "nhưng idempotent trên job_id: chỉ một item"


async def test_hold_for_review_khong_tao_duoc_item_thi_khong_gui_fail_closed() -> None:
    actions = FakeActions(fail_create=True)
    rig = patient_rig(DecidingHooks(OutboundAction.HOLD_FOR_REVIEW), actions=actions)

    await rig.run([await rig.receive("cho mình hỏi", "m1", thread_id=THREAD)])

    assert rig.api.sent == []


async def test_hold_for_review_khong_cau_hinh_clinic_actions_thi_cung_khong_gui() -> None:
    rig = TurnRig.create(
        engine=FakeEngine(script=answer("nội dung y tế")),
        profile=PolicyProfileKey.PATIENT_CHANNEL,
        hooks=DecidingHooks(OutboundAction.HOLD_FOR_REVIEW),
    )
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])
    assert rig.api.sent == []


async def test_drop_thi_khong_gui_va_khong_mo_item() -> None:
    rig = patient_rig(DecidingHooks(OutboundAction.DROP))
    assert rig.actions is not None
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])
    assert rig.api.sent == []
    assert rig.actions.created == []


async def test_send_thi_gui_ghi_history_va_ghi_hop_thu_da_gui() -> None:
    rig = TurnRig.create(
        engine=FakeEngine(script=answer("Chào anh")),
        hooks=DecidingHooks(OutboundAction.SEND),
        actions=FakeActions(),
    )
    assert rig.actions is not None
    await rig.run([await rig.receive("chào", "m1", thread_id=THREAD)])

    assert rig.sent_texts() == ["Chào anh"]
    assert rig.actions.outbound == [("Chào anh", MessageStatus.SENT, None)], "Inbox of record ghi tin đã gửi"


async def test_human_approved_di_cung_duong_gui_va_bo_qua_cong_chinh_sach() -> None:
    """bác sĩ/nhân viên duyệt rồi: cùng đường gửi (làm sạch, dịch định dạng, cắt, gửi, ghi history)"""
    rig = TurnRig.create()
    hooks = DecidingHooks(OutboundAction.HOLD_FOR_REVIEW)
    target = ReplyTarget(
        gui_mot_doan=duong_gui_zca_js(rig.api, THREAD, ThreadKind.USER),
        thread_key=f"{rig.config.id}:{THREAD}",
        thread_id=THREAD,
        thread_type=ThreadKind.USER,
    )
    policy = PolicyContext(
        clinic_id=FAKE_CLINIC_ID,
        account_id=rig.config.id,
        agent_id="agent-test",
        channel=rig.channel.kind,
        thread_id=THREAD,
        profile=DEFAULT_PROFILES[PolicyProfileKey.PATIENT_CHANNEL],
    )
    deps = DeliveryDeps(
        history=rig.conversation,  # type: ignore[arg-type]
        hooks=hooks,
        policy=policy,
        enqueue_send=rig.services.enqueue_send,
    )

    held = await deliver_chat_reply(target, deps, FAKE_CLINIC_ID, rig.config.id, THREAD, "**Lịch** hẹn 9h")
    approved = await deliver_chat_reply(
        target, deps, FAKE_CLINIC_ID, rig.config.id, THREAD, "**Lịch** hẹn 9h", human_approved=True
    )

    assert held.held_for_review is True
    assert held.hong is True, "không có hold_for_review cấu hình: coi là hỏng, không gửi"
    assert approved.da_gui == "Lịch hẹn 9h"
    assert rig.sent_texts() == ["Lịch hẹn 9h"]
    assert len(hooks.calls) == 1, "đường đã duyệt không hỏi lại chính sách"


async def test_hand_off_do_hook_da_tu_mo_item_thi_pipeline_khong_gui_va_khong_mo_them() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        return AgentTurnResult(text="", handed_off=True, hand_off_reason="red_flag")

    rig = patient_rig(DecidingHooks(OutboundAction.SEND), FakeEngine(script=script))
    assert rig.actions is not None
    await rig.run([await rig.receive("chảy máu nhiều", "m1", thread_id=THREAD)])

    assert rig.api.sent == [], "cờ đỏ: không một câu tự động nào cho bệnh nhân"
    assert rig.actions.created == [], "hook đã mở item, pipeline không mở đôi"
    turn = next(iter(rig.conversation.turns.values()))
    assert turn.finished == 1


async def test_hand_off_hook_bao_leo_thang_hong_thi_pipeline_mo_triage_alert_cung_job_id_cua_policy() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        return AgentTurnResult(text="", handed_off=True, hand_off_reason="red_flag_escalation_failed")

    rig = patient_rig(DecidingHooks(OutboundAction.SEND), FakeEngine(script=script))
    assert rig.actions is not None
    msg = await rig.receive("sốt cao mưng mủ", "m1", thread_id=THREAD)

    await rig.run([msg])

    [item] = rig.actions.created
    assert item.kind is ReviewKind.TRIAGE_ALERT
    assert item.risk_level is RiskLevel.RED_FLAG
    assert item.conversation_ref == str(rig.actions.conversation_id), "triage phải gắn hội thoại"
    policy_ctx = PolicyContext(
        clinic_id=FAKE_CLINIC_ID,
        account_id=rig.config.id,
        agent_id="agent-test",
        channel=msg.channel,
        thread_id=THREAD,
        profile=DEFAULT_PROFILES[PolicyProfileKey.PATIENT_CHANNEL],
    )
    assert item.job_id == red_flag_job_id(policy_ctx, [msg]), "cùng khóa với policy: không bao giờ hai item"
    assert rig.api.sent == []


async def test_hand_off_media_that_bai_mo_media_flag() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        return AgentTurnResult(text="", handed_off=True, hand_off_reason="inbound_media_flag_failed")

    rig = patient_rig(DecidingHooks(OutboundAction.SEND), FakeEngine(script=script))
    assert rig.actions is not None
    msg = await rig.receive(
        "ảnh vết thương", "m1", thread_id=THREAD, images=["http://x.example.invalid/a.jpg"]
    )

    await rig.run([msg])

    [item] = rig.actions.created
    assert item.kind is ReviewKind.MEDIA_FLAG
    assert item.conversation_ref == str(rig.actions.conversation_id)
    assert item.job_id.startswith("policy:media:")
    assert media_flag_job_id is not None
    assert rig.api.sent == []


async def test_loi_engine_trong_patient_channel_cau_xin_loi_bi_giu_lam_ban_nhap_khong_gui() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        raise AgentTurnError(ProviderErrorKind.AUTH, "401")

    rig = patient_rig(DecidingHooks(OutboundAction.HOLD_FOR_REVIEW), FakeEngine(script=script))
    assert rig.actions is not None
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])

    assert rig.api.sent == [], "câu xin lỗi cũng là tin ra khách: chờ người duyệt"
    [item] = rig.actions.created
    assert item.kind is ReviewKind.REPLY_DRAFT
    assert item.payload is not None
    assert item.payload["agent_failed"] is True
    assert item.payload["error_kind"] == "auth"
    turn = next(iter(rig.conversation.turns.values()))
    assert (turn.finished, turn.trace_saves) == (1, 1), "lượt chết vẫn được chốt sổ đúng một lần, có trace"
    assert turn.trace[0].finish_reason == "error:auth"


async def test_loi_engine_trong_staff_assistant_gui_cau_xin_loi_theo_loai_loi_khong_ghi_history() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        raise AgentTurnError(ProviderErrorKind.CONFIG, "no key")

    rig = TurnRig.create(engine=FakeEngine(script=script))
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])

    assert len(rig.api.sent) == 1
    assert "chưa được cài đặt xong" in rig.api.sent[0].text, "lỗi cấu hình có câu riêng"
    assert [r for r, _ in rig.conversation.contents(rig.config.id, THREAD)] == ["user"], (
        "thông báo hệ thống không vào history"
    )


async def test_loi_la_khong_phai_agent_turn_error_van_duoc_chot_so_va_bao_loi_chung() -> None:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        raise RuntimeError("bug bất ngờ")

    rig = TurnRig.create(engine=FakeEngine(script=script))
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])

    turn = next(iter(rig.conversation.turns.values()))
    assert (turn.finished, turn.trace_saves) == (1, 1)
    assert "trục trặc kỹ thuật" in rig.api.sent[0].text


async def test_luot_da_chot_so_roi_ma_buoc_sau_hong_thi_khong_chot_lan_hai() -> None:
    """đè token thật bằng {0,0,0} và nhân đôi dòng trace là lỗi đã trả giá ở bản gốc"""

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        assert callbacks is not None
        from pema_contracts.agent_turn import StepTrace

        callbacks.trace.append(StepTrace(step_number=1, text="step"))
        return AgentTurnResult(
            text="ok", usage=TokenUsage(input_tokens=60, output_tokens=15, total_tokens=75, steps=1)
        )

    rig = TurnRig.create(engine=FakeEngine(script=script))
    original = rig.conversation.save_turn_trace
    calls = {"n": 0}

    async def failing_once(clinic_id: UUID, turn_id: int, steps: list[object]) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("DB down")
        await original(clinic_id, turn_id, steps)  # type: ignore[arg-type]

    rig.conversation.save_turn_trace = failing_once  # type: ignore[method-assign]
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])

    turn = next(iter(rig.conversation.turns.values()))
    assert turn.finished == 1, "usage chốt đúng một lần với số token thật"
    assert turn.usage is not None
    assert turn.usage.total_tokens == 75
    assert calls["n"] == 1, "không INSERT trace lần hai trong nhánh lỗi"


async def test_luot_thanh_cong_chot_usage_mot_lan_va_chi_luu_trace_khi_co_step() -> None:
    rig = TurnRig.create(engine=FakeEngine(script=answer("ok")))
    await rig.run([await rig.receive("hỏi", "m1", thread_id=THREAD)])
    turn = next(iter(rig.conversation.turns.values()))
    assert (turn.finished, turn.trace_saves) == (1, 0), "engine không thêm step nào: không lưu trace rỗng"
    assert turn.usage is not None
    assert turn.usage.total_tokens == 75
