"""``ClinicPolicyHooks`` under the ``patient_channel`` profile: one section per hook (new module).

The central property, proved first: a red-flag message never reaches the model. A fake model counts its
calls through ``run_guarded_turn`` (the reference order of a turn); the real agent loop of package D1
must call the hooks in the same order. Everything is fictional.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from pema.policy.gateway import ApprovedTemplate, PatientPolicyFlags
from pema.policy.identity import link_code_hash, phone_hash
from pema.policy.review import red_flag_job_id
from pema.policy.testing import (
    FAKE_PATIENT_ID,
    FakePolicyGateway,
    make_hooks,
    make_policy_context,
)
from pema.policy.turn_guard import run_guarded_turn
from pema_contracts.channel import ChannelKind, InboundImage, InboundKind
from pema_contracts.clinic_actions import IdentityLink, IdentityLinkStatus
from pema_contracts.common import now_vn
from pema_contracts.policy import (
    BeforeLlmAction,
    JobAction,
    MemorySource,
    OutboundAction,
    OutboundOrigin,
    PolicyContext,
    PolicyProfileKey,
)
from pema_contracts.review import ReviewKind, ReviewOrigin, RiskLevel
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, OnceSchedule
from pema_contracts.testing import FAKE_CLINIC_ID, FakeTextGenerator, make_inbound

CTX = make_policy_context()
VERIFIED_CTX = make_policy_context(identity_verified=True, patient_id=FAKE_PATIENT_ID)


class CountingModel:
    """The fake LLM of the tests: records every prompt and answers with a scripted reply."""

    def __init__(self, reply: str = "Dạ em chào mình ạ") -> None:
        self.generator = FakeTextGenerator(reply=lambda _prompt: reply)

    @property
    def calls(self) -> int:
        return len(self.generator.prompts)

    @property
    def prompts(self) -> list[str]:
        return self.generator.prompts

    async def __call__(self, prompt: str) -> str:
        return (await self.generator.generate_text(prompt)).text


def _patient_gateway() -> FakePolicyGateway:
    gw = FakePolicyGateway()
    gw.add_patient(
        PatientPolicyFlags(
            patient_id=FAKE_PATIENT_ID,
            code="P025",
            full_name="Nguyễn Thị Hoa",
            marketing_opt_out=False,
            consent_messaging=True,
            consent_marketing=True,
        )
    )
    return gw


# ============================================================ red flags: the model is not called
@pytest.mark.parametrize(
    ("text", "flag"),
    [
        ("em bị chảy máu nhiều sau laser", "bleeding"),
        ("chay mau khong ngung", "bleeding"),
        ("em sốt cao từ tối qua", "fever"),
        ("sot 39 do", "fever"),
        ("vết thương mưng mủ", "pus"),
        ("vet thuong mung mu", "pus"),
        ("em khó thở", "dyspnea"),
        ("k thở được", "dyspnea"),
    ],
)
async def test_red_flag_hands_off_and_the_fake_model_is_never_called(text: str, flag: str) -> None:
    """tin cờ đỏ chuyển bác sĩ TRƯỚC khi gọi LLM: LLM giả không bị gọi, có triage_alert"""
    hooks, actions, _ = make_hooks()
    model = CountingModel()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound(text)], model)
    assert model.calls == 0
    assert turn.handed_off is True
    assert turn.model_called is False
    assert turn.reply is None
    assert turn.hand_off_reason == "red_flag"
    assert flag in turn.red_flags
    [item] = actions.review_items
    assert item.kind is ReviewKind.TRIAGE_ALERT
    assert item.origin is ReviewOrigin.POLICY
    assert item.risk_level is RiskLevel.RED_FLAG
    assert flag in item.red_flags


async def test_ordinary_message_reaches_the_model_once() -> None:
    """tin bình thường đi tiếp tới LLM (đối chứng: cờ đỏ là thứ duy nhất chặn lại)"""
    hooks, actions, _ = make_hooks()
    model = CountingModel()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound("cho em hỏi giá laser")], model)
    assert model.calls == 1
    assert turn.handed_off is False
    assert not actions.review_items


async def test_red_flag_in_any_message_of_the_batch_stops_the_whole_turn() -> None:
    """một tin cờ đỏ trong lô là đủ: cả lượt không gọi LLM"""
    hooks, actions, _ = make_hooks()
    model = CountingModel()
    batch = [
        make_inbound("chào bác sĩ", msg_id="m1"),
        make_inbound("em muốn đặt lịch", msg_id="m2"),
        make_inbound("mà em đang khó thở", msg_id="m3"),
    ]
    turn = await run_guarded_turn(hooks, CTX, batch, model)
    assert (model.calls, turn.handed_off) == (0, True)
    assert len(actions.review_items) == 1


async def test_negated_flag_does_not_stop_the_turn() -> None:
    """ "không sốt, không chảy máu" không chặn lượt"""
    hooks, actions, _ = make_hooks()
    model = CountingModel()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound("em không sốt, không chảy máu ạ")], model)
    assert (model.calls, turn.handed_off) == (1, False)
    assert not actions.review_items


async def test_the_triage_item_carries_ids_and_never_the_patient_words() -> None:
    """triage_alert chỉ mang mã/id, không chép nội dung tin nhắn của bệnh nhân"""
    hooks, actions, _ = make_hooks()
    text = "em chảy máu nhiều, nhà em ở số 12 đường Lê Lợi, sdt 0901234567"
    await hooks.before_llm(CTX, [make_inbound(text, msg_id="m-77", sender_name="Nguyễn Thị Hoa")])
    [item] = actions.review_items
    dumped = item.model_dump_json()
    for secret in ("Lê Lợi", "0901234567", "Nguyễn Thị Hoa", "chảy máu nhiều"):
        assert secret not in dumped
    assert item.payload is not None
    assert item.payload["msg_ids"] == ["m-77"]
    assert item.payload["thread_id"] == "thread-1"


async def test_the_same_batch_opens_one_triage_item_even_when_retried() -> None:
    """thử lại cùng lô chỉ mở một triage_alert (idempotent theo job_id)"""
    hooks, actions, _ = make_hooks()
    batch = [make_inbound("em khó thở", msg_id="m1")]
    first = await hooks.before_llm(CTX, batch)
    second = await hooks.before_llm(CTX, batch)
    assert first.action is second.action is BeforeLlmAction.HAND_OFF
    assert len(actions.review_items) == 1
    assert actions.review_items[0].job_id == red_flag_job_id(CTX, batch)


async def test_red_flag_item_names_the_patient_by_code_only_when_verified() -> None:
    """triage_alert của người đã xác minh gắn mã bệnh nhân (P025), người chưa xác minh thì không"""
    gw = _patient_gateway()
    hooks, actions, _ = make_hooks(gateway=gw)
    await hooks.before_llm(VERIFIED_CTX, [make_inbound("em sốt cao", msg_id="a")])
    await hooks.before_llm(CTX, [make_inbound("em sốt cao", msg_id="b", thread_id="t2")])
    assert [i.patient_ref for i in actions.review_items] == ["P025", None]


async def test_red_flag_still_hands_off_when_the_item_cannot_be_created() -> None:
    """tạo escalation lỗi vẫn HAND_OFF (không bao giờ gọi LLM), lý do ghi rõ để nơi gọi mở lại"""
    hooks, actions, _ = make_hooks()
    actions.fail_create_review_item = True
    model = CountingModel()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound("em khó thở")], model)
    assert model.calls == 0
    assert turn.handed_off is True
    assert turn.hand_off_reason == "red_flag_escalation_failed"


async def test_escalation_can_be_left_to_the_caller() -> None:
    """escalate=False: hook chỉ quyết định, nơi gọi tự mở item với cùng job_id"""
    hooks, actions, _ = make_hooks(escalate=False)
    decision = await hooks.before_llm(CTX, [make_inbound("em khó thở")])
    assert decision.action is BeforeLlmAction.HAND_OFF
    assert decision.red_flags == ["dyspnea"]
    assert not actions.review_items


async def test_own_messages_are_not_scanned() -> None:
    """tin của chính mình (is_self) không bị quét cờ đỏ"""
    hooks, actions, _ = make_hooks()
    decision = await hooks.before_llm(CTX, [make_inbound("em khó thở", is_self=True), make_inbound("chào")])
    assert decision.action is BeforeLlmAction.CONTINUE
    assert not actions.review_items


# ========================================================================= inbound images / files
@pytest.mark.parametrize("kind", [InboundKind.IMAGE, InboundKind.FILE, InboundKind.VOICE])
async def test_media_from_the_patient_flags_the_inbox_and_hands_off(kind: InboundKind) -> None:
    """khách gửi ảnh/tệp/voice: gắn cờ Inbox (media_flag) và chuyển người, LLM không được gọi"""
    hooks, actions, _ = make_hooks()
    model = CountingModel()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound("", kind=kind)], model)
    assert model.calls == 0
    assert turn.handed_off is True
    assert turn.hand_off_reason == "inbound_media"
    [item] = actions.review_items
    assert item.kind is ReviewKind.MEDIA_FLAG
    assert item.payload is not None
    assert item.payload["kinds"] == [kind.value]


async def test_text_message_with_an_attached_image_list_is_handed_off() -> None:
    """tin có kèm danh sách ảnh cũng chuyển người dù kind là text"""
    hooks, actions, _ = make_hooks()
    message = make_inbound("xem giúp em", images=[InboundImage(url="https://example.invalid/a.jpg")])
    decision = await hooks.before_llm(CTX, [message])
    assert decision.action is BeforeLlmAction.HAND_OFF
    assert [i.kind for i in actions.review_items] == [ReviewKind.MEDIA_FLAG]


async def test_sticker_is_not_media_to_hand_off() -> None:
    """sticker không phải ảnh cần chuyển người"""
    hooks, actions, _ = make_hooks()
    decision = await hooks.before_llm(CTX, [make_inbound("", kind=InboundKind.STICKER)])
    assert decision.action is BeforeLlmAction.CONTINUE
    assert not actions.review_items


async def test_red_flag_plus_image_opens_both_items_and_reports_the_red_flag() -> None:
    """vừa cờ đỏ vừa ảnh: mở cả triage_alert lẫn media_flag, lý do là red_flag"""
    hooks, actions, _ = make_hooks()
    batch = [make_inbound("em sốt cao", msg_id="a"), make_inbound("", kind=InboundKind.IMAGE, msg_id="b")]
    decision = await hooks.before_llm(CTX, batch)
    assert decision.reason == "red_flag"
    assert {i.kind for i in actions.review_items} == {ReviewKind.TRIAGE_ALERT, ReviewKind.MEDIA_FLAG}


# ========================================================================================== PII
async def test_pii_is_masked_before_the_model_and_names_are_restored_after() -> None:
    """PII được che trước khi gọi LLM; tên được khôi phục sau; SĐT/CCCD không bao giờ về lại"""
    gw = _patient_gateway()
    hooks, _, _ = make_hooks(gateway=gw)
    model = CountingModel("Dạ chào [KH_P025], em đã ghi nhận số [SDT_1] ạ")
    text = "Em là Nguyễn Thị Hoa, sdt 0901234567, cccd 079203123456, mail hoa.test@gmail.com"
    turn = await run_guarded_turn(hooks, VERIFIED_CTX, [make_inbound(text)], model)
    assert model.calls == 1
    seen = model.prompts[0]
    for secret in ("Nguyễn Thị Hoa", "0901234567", "079203123456", "hoa.test@gmail.com"):
        assert secret not in seen
    assert "KH_P025" in seen
    assert turn.reply == "Dạ chào Nguyễn Thị Hoa, em đã ghi nhận số [đã ẩn] ạ"


async def test_sender_name_from_the_channel_is_masked() -> None:
    """tên hiển thị của kênh (sender_name) bị che nếu xuất hiện trong tin"""
    hooks, _, _ = make_hooks()
    model = CountingModel()
    message = make_inbound("Chào em, mình là Trần Văn Bình đây", sender_name="Trần Văn Bình")
    await run_guarded_turn(hooks, CTX, [message], model)
    assert "Trần Văn Bình" not in model.prompts[0]
    assert "[NGUOI_1]" in model.prompts[0]


async def test_an_unverified_patient_name_is_not_resolved_to_a_code() -> None:
    """người chưa xác minh: tên không được đổi thành mã bệnh nhân thật (không tra hồ sơ)"""
    gw = _patient_gateway()
    hooks, _, _ = make_hooks(gateway=gw)
    model = CountingModel()
    await run_guarded_turn(hooks, CTX, [make_inbound("em là Nguyễn Thị Hoa")], model)
    assert "P025" not in model.prompts[0]


async def test_masked_text_is_reported_only_for_messages_that_changed() -> None:
    """masked_text_by_msg_id chỉ chứa tin có PII; mask_token luôn có"""
    hooks, _, _ = make_hooks()
    batch = [make_inbound("chào", msg_id="m1"), make_inbound("sdt 0901234567", msg_id="m2")]
    decision = await hooks.before_llm(CTX, batch)
    assert decision.action is BeforeLlmAction.CONTINUE
    assert set(decision.masked_text_by_msg_id) == {"m2"}
    assert decision.mask_token is not None


async def test_history_and_tool_results_get_the_same_placeholders_as_the_turn() -> None:
    """mask_text dùng cùng mã giữ chỗ với lượt chạy (cho lịch sử, kết quả tool)"""
    hooks, _, _ = make_hooks()
    await hooks.before_llm(CTX, [make_inbound("sdt 0901234567", msg_id="m1")])
    assert hooks.mask_text(CTX, "khách để lại 0901234567 hôm qua") == "khách để lại [SDT_1] hôm qua"


async def test_after_llm_without_a_token_still_hides_foreign_placeholders() -> None:
    """after_llm không có mask_token vẫn không để lọt mã giữ chỗ lạ"""
    hooks, _, _ = make_hooks()
    assert await hooks.after_llm(CTX, "gọi [SDT_4] nhé", None) == "gọi [đã ẩn] nhé"


async def test_the_thread_keeps_one_mask_session_across_turns() -> None:
    """cùng một luồng: số điện thoại giữ cùng mã giữa hai lượt, token ổn định"""
    hooks, _, _ = make_hooks()
    first = await hooks.before_llm(CTX, [make_inbound("sdt 0901234567", msg_id="m1")])
    second = await hooks.before_llm(CTX, [make_inbound("gọi lại 0901234567", msg_id="m2")])
    assert first.mask_token == second.mask_token
    assert second.masked_text_by_msg_id["m2"] == "gọi lại [SDT_1]"


# ================================================================================= identity link
async def test_phone_share_opens_an_identity_check_for_staff_and_keeps_the_turn_going() -> None:
    """khách chia sẻ SĐT khớp một hồ sơ: mở identity_check chờ nhân viên, lượt vẫn chạy với tin đã che"""
    gw = _patient_gateway()
    digest = phone_hash("0901234567")
    assert digest is not None
    gw.phone_index[digest] = [FAKE_PATIENT_ID]
    hooks, actions, _ = make_hooks(gateway=gw)
    model = CountingModel()
    turn = await run_guarded_turn(
        hooks, CTX, [make_inbound("sdt của em 0901234567", sender_id="zu-1")], model
    )
    assert turn.handed_off is False
    assert "0901234567" not in model.prompts[0]
    [item] = actions.review_items
    assert item.kind is ReviewKind.IDENTITY_CHECK
    assert item.patient_ref == "P025"
    assert item.payload is not None
    assert item.payload["method"] == "phone"
    assert item.payload["external_user_id"] == "zu-1"
    assert "0901234567" not in item.model_dump_json()
    assert digest not in item.model_dump_json()


async def test_reception_code_verifies_without_a_staff_review_item() -> None:
    """mã lễ tân đúng: xác minh ngay, không cần identity_check"""
    gw = _patient_gateway()
    code_digest = link_code_hash("K7QM4XNR")
    assert code_digest is not None
    gw.codes[code_digest] = FAKE_PATIENT_ID
    hooks, actions, _ = make_hooks(gateway=gw)
    await hooks.before_llm(CTX, [make_inbound("mã xác minh K7QM-4XNR", sender_id="zu-1")])
    assert gw.verified[(ChannelKind.ZALO_BOT, "zu-1")] == FAKE_PATIENT_ID
    assert not actions.review_items


async def test_no_identity_attempt_when_already_verified_or_for_ordinary_text() -> None:
    """đã xác minh, hoặc tin thường: không chạy luồng xác minh"""
    gw = _patient_gateway()
    hooks, _, _ = make_hooks(gateway=gw)
    await hooks.before_llm(VERIFIED_CTX, [make_inbound("sdt 0901234567")])
    await hooks.before_llm(CTX, [make_inbound("cho em hỏi giá")])
    assert gw.calls == []


async def test_identity_flow_needs_a_single_sender() -> None:
    """lô có nhiều người gửi (nhóm): không thử liên kết, tránh gán nhầm"""
    gw = _patient_gateway()
    hooks, _, _ = make_hooks(gateway=gw)
    batch = [
        make_inbound("sdt 0901234567", sender_id="u1", msg_id="a"),
        make_inbound("ok", sender_id="u2", msg_id="b"),
    ]
    await hooks.before_llm(CTX, batch)
    assert gw.calls == []


async def test_a_failing_gateway_does_not_break_the_turn() -> None:
    """cổng DB lỗi trong luồng xác minh: lượt vẫn chạy (không có xác minh, an toàn)"""
    gw = _patient_gateway()

    async def boom(*_args: object) -> object:
        raise RuntimeError("db down")

    gw.link_by_phone_hash = boom  # type: ignore[method-assign,assignment]  # pyright: ignore[reportAttributeAccessIssue]
    hooks, _, _ = make_hooks(gateway=gw)
    decision = await hooks.before_llm(CTX, [make_inbound("sdt 0901234567")])
    assert decision.action is BeforeLlmAction.CONTINUE


async def test_verify_identity_reports_only_a_verified_link_as_verified() -> None:
    """verify_identity: chỉ liên kết VERIFIED mới được coi là đã xác minh; PENDING cần nhân viên"""
    hooks, actions, _ = make_hooks()
    pid = uuid4()
    ch = ChannelKind.ZALO_BOT
    actions.links[(ch, "v")] = IdentityLink(
        channel=ch,
        external_user_id="v",
        status=IdentityLinkStatus.VERIFIED,
        patient_id=pid,
        patient_code="P025",
        verified_at=now_vn(),
    )
    actions.links[(ch, "p")] = IdentityLink(
        channel=ch, external_user_id="p", status=IdentityLinkStatus.PENDING, patient_id=pid
    )
    actions.links[(ch, "r")] = IdentityLink(
        channel=ch, external_user_id="r", status=IdentityLinkStatus.REJECTED
    )
    verified = await hooks.verify_identity(CTX, ch, "v")
    assert (verified.verified, verified.patient_id, verified.needs_staff_confirmation) == (True, pid, False)
    pending = await hooks.verify_identity(CTX, ch, "p")
    assert (pending.verified, pending.patient_id, pending.needs_staff_confirmation) == (False, None, True)
    for uid in ("r", "unknown"):
        status = await hooks.verify_identity(CTX, ch, uid)
        assert (status.verified, status.patient_id, status.needs_staff_confirmation) == (False, None, False)


async def test_verify_identity_fails_closed_when_the_lookup_fails() -> None:
    """tra cứu liên kết lỗi: coi như CHƯA xác minh (không nhắc tên/lịch/thuốc)"""
    hooks, actions, _ = make_hooks()
    actions.fail_resolve_identity = True
    status = await hooks.verify_identity(CTX, ChannelKind.ZALO_BOT, "v")
    assert status.verified is False


# ======================================================================================= tools
ALL_TOOLS = frozenset(
    {
        "add_reaction", "send_file", "create_word_document", "create_excel_file", "create_image",
        "tai_video", "tag_member", "save_memory", "schedule_task", "get_datetime", "web_search",
        "web_fetch", "read_image", "get_group_info", "kb_search",
        "patient.get_care_context", "appointment.book", "review_item.create",
        "mcp__crm__lookup", "mcp__drive__read",
    }
)  # fmt: skip


async def test_patient_channel_turns_off_media_web_mcp_and_save_memory() -> None:
    """patient_channel tắt tool ảnh/video/tài liệu/web, MCP và save_memory; còn lại giữ nguyên"""
    hooks, _, _ = make_hooks()
    kept = await hooks.filter_tool_keys(CTX, ALL_TOOLS)
    assert kept == {
        "add_reaction", "tag_member", "schedule_task", "get_datetime", "get_group_info", "kb_search",
        "patient.get_care_context", "appointment.book", "review_item.create",
    }  # fmt: skip


async def test_tool_filter_is_a_pure_subset() -> None:
    """bộ lọc tool chỉ bớt, không thêm tool nào"""
    hooks, _, _ = make_hooks()
    assert await hooks.filter_tool_keys(CTX, frozenset({"kb_search"})) == {"kb_search"}
    assert await hooks.filter_tool_keys(CTX, frozenset()) == frozenset()


@pytest.mark.parametrize(
    ("source", "allowed"),
    [(MemorySource.PATIENT_MESSAGE, False), (MemorySource.WEB_CONTENT, False), (MemorySource.STAFF, True)],
)
async def test_save_memory_is_off_for_patient_content_and_on_for_staff(
    source: MemorySource, allowed: bool
) -> None:
    """save_memory tắt với nội dung từ bệnh nhân/web; chỉ bác sĩ/CSKH ghi"""
    hooks, _, _ = make_hooks()
    assert await hooks.allow_memory_write(CTX, source) is allowed


# ==================================================================================== outbound
@pytest.mark.parametrize("origin", list(OutboundOrigin))
@pytest.mark.parametrize("proactive", [False, True])
async def test_every_outbound_text_waits_for_review(origin: OutboundOrigin, proactive: bool) -> None:
    """MỌI tin ra khách (trả lời, tin theo lịch, tool gửi) vào hàng chờ duyệt"""
    hooks, _, _ = make_hooks()
    decision = await hooks.on_outbound(CTX, "Dạ mình đặt lịch thứ 7 nhé", proactive=proactive, origin=origin)
    assert decision.action is OutboundAction.HOLD_FOR_REVIEW


async def test_empty_outbound_text_is_dropped() -> None:
    """tin rỗng bị bỏ, không tạo bản nháp trống"""
    hooks, _, _ = make_hooks()
    decision = await hooks.on_outbound(CTX, "  \n ", proactive=False, origin=OutboundOrigin.TURN_REPLY)
    assert decision.action is OutboundAction.DROP


async def test_a_held_turn_reply_is_not_sent_by_the_reference_turn() -> None:
    """lượt trả lời trả về HOLD_FOR_REVIEW, không phải SEND"""
    hooks, _, _ = make_hooks()
    turn = await run_guarded_turn(hooks, CTX, [make_inbound("giá laser")], CountingModel())
    assert turn.outbound is not None
    assert turn.outbound.action is OutboundAction.HOLD_FOR_REVIEW


# =================================================================================== scheduled jobs
def _job(
    kind: JobKind = JobKind.MESSAGE, payload: str = "followup_d1", **patch: Any
) -> CreateScheduledJobInput:
    data: dict[str, object] = {
        "clinic_id": FAKE_CLINIC_ID,
        "account_id": "acc-1",
        "thread_id": "thread-1",
        "thread_type": 0,
        "name": "Nhắc sau điều trị",
        "kind": kind,
        "payload": payload,
        "schedule": OnceSchedule(run_at_utc="2026-09-21T02:00:00Z"),
        "created_by": "crm_rule",
        **patch,
    }
    return CreateScheduledJobInput.model_validate(data)


def _gateway_with_templates() -> FakePolicyGateway:
    gw = _patient_gateway()
    gw.templates["followup_d1"] = ApprovedTemplate("followup_d1", marketing=False)
    gw.templates["promo_laser"] = ApprovedTemplate("promo_laser", marketing=True)
    gw.templates["birthday_greeting"] = ApprovedTemplate("birthday_greeting", marketing=True)
    return gw


async def test_agent_job_is_downgraded_to_a_draft() -> None:
    """job kind=agent theo lịch chỉ được soạn nháp"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    decision = await hooks.check_job(CTX, _job(JobKind.AGENT, "Nhắc khách tái khám"))
    assert decision.action is JobAction.DOWNGRADE_TO_DRAFT


async def test_message_job_from_an_approved_template_is_allowed() -> None:
    """job kind=message từ template đã duyệt (không marketing) được chạy"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    assert (await hooks.check_job(CTX, _job(payload="followup_d1"))).action is JobAction.ALLOW


@pytest.mark.parametrize("payload", ["not_a_template", "Chào chị, mai chị nhớ tái khám nhé", "x"])
async def test_message_job_with_free_text_or_unknown_template_is_denied(payload: str) -> None:
    """job message không phải template đã duyệt (văn bản tự do, khóa lạ) bị từ chối"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    decision = await hooks.check_job(CTX, _job(payload=payload))
    assert decision.action is JobAction.DENY
    assert decision.reason == "template_not_approved"


async def test_marketing_template_is_blocked_by_marketing_opt_out() -> None:
    """marketingOptOut chặn template marketing; tin chăm sóc an toàn vẫn đi"""
    gw = _gateway_with_templates()
    gw.patients[FAKE_PATIENT_ID] = PatientPolicyFlags(
        patient_id=FAKE_PATIENT_ID,
        code="P025",
        full_name="Nguyễn Thị Hoa",
        marketing_opt_out=True,
        consent_messaging=True,
        consent_marketing=True,
    )
    hooks, _, _ = make_hooks(gateway=gw)
    blocked = await hooks.check_job(CTX, _job(payload="promo_laser", patient_id=FAKE_PATIENT_ID))
    assert (blocked.action, blocked.reason) == (JobAction.DENY, "marketing_opt_out")
    safety = await hooks.check_job(CTX, _job(payload="followup_d1", patient_id=FAKE_PATIENT_ID))
    assert safety.action is JobAction.ALLOW


async def test_marketing_template_for_an_opted_in_patient_is_allowed() -> None:
    """khách không opt-out nhận được template marketing đã duyệt"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    decision = await hooks.check_job(CTX, _job(payload="promo_laser", patient_id=FAKE_PATIENT_ID))
    assert decision.action is JobAction.ALLOW


async def test_marketing_without_a_known_patient_is_denied() -> None:
    """marketing mà không biết bệnh nhân nào: từ chối (không kiểm tra được opt-out)"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    decision = await hooks.check_job(CTX, _job(payload="promo_laser"))
    assert (decision.action, decision.reason) == (JobAction.DENY, "marketing_patient_unknown")
    unknown = await hooks.check_job(CTX, _job(payload="promo_laser", patient_id=uuid4()))
    assert (unknown.action, unknown.reason) == (JobAction.DENY, "marketing_patient_unknown")


@pytest.mark.parametrize(
    "patch",
    [
        {"payload": "birthday_greeting"},
        {"name": "Chúc mừng sinh nhật chị Hoa"},
        {"dedupe_key": "birthday:P025:2026-09-20"},
        {"name": "SINH NHẬT", "kind": JobKind.AGENT, "payload": "Chúc mừng sinh nhật khách"},
        {"name": "Sinh-nhat khach hang"},
    ],
)
async def test_birthday_is_never_auto_sent(patch: dict[str, Any]) -> None:
    """sinh nhật không tự gửi: job sinh nhật (theo khóa, tên, dedupe, kể cả agent) bị từ chối"""
    hooks, _, _ = make_hooks(gateway=_gateway_with_templates())
    decision = await hooks.check_job(CTX, _job(patient_id=FAKE_PATIENT_ID, **patch))
    assert (decision.action, decision.reason) == (JobAction.DENY, "birthday_never_auto_sent")


async def test_job_check_fails_closed_when_the_template_lookup_fails() -> None:
    """tra template lỗi: từ chối job (không gửi thứ chưa kiểm tra được)"""
    gw = _gateway_with_templates()
    gw.fail_template_lookup = True
    hooks, _, _ = make_hooks(gateway=gw)
    decision = await hooks.check_job(CTX, _job())
    assert (decision.action, decision.reason) == (JobAction.DENY, "policy_unavailable")


# =============================================================================== proactive cap
async def test_proactive_cap_is_per_patient_and_account_when_the_patient_is_known() -> None:
    """trần tin chủ động theo bệnh nhân + account (cùng bệnh nhân qua hai luồng chung một bộ đếm)"""
    hooks, _, _ = make_hooks()
    a = await hooks.proactive_cap(make_policy_context(patient_id=FAKE_PATIENT_ID, thread_id="t1"), 10)
    b = await hooks.proactive_cap(make_policy_context(patient_id=FAKE_PATIENT_ID, thread_id="t2"), 10)
    other_account = await hooks.proactive_cap(
        make_policy_context(patient_id=FAKE_PATIENT_ID, account_id="acc-2"), 10
    )
    assert a.scope_key == b.scope_key == f"patient:{FAKE_PATIENT_ID}:acc-1"
    assert other_account.scope_key != a.scope_key
    assert a.max_per_day == 10


async def test_proactive_cap_falls_back_to_the_conversation_for_an_unknown_patient() -> None:
    """chưa biết bệnh nhân: vẫn có trần, tính theo hội thoại"""
    hooks, _, _ = make_hooks()
    cap = await hooks.proactive_cap(CTX, 7)
    assert cap.scope_key == "thread:acc-1:thread-1"
    assert cap.max_per_day == 7
    none = await hooks.proactive_cap(CTX, None)
    assert none.max_per_day is None


async def test_the_cap_key_contains_no_pii() -> None:
    """khóa bộ đếm chỉ có id, không có tên/SĐT"""
    hooks, _, _ = make_hooks()
    cap = await hooks.proactive_cap(make_policy_context(patient_id=UUID(int=5)), 10)
    assert cap.scope_key == f"patient:{UUID(int=5)}:acc-1"


def test_context_default_profile_is_patient_channel() -> None:
    """ngữ cảnh mặc định của test là patient_channel (an toàn mặc định)"""
    ctx: PolicyContext = make_policy_context()
    assert ctx.profile.key is PolicyProfileKey.PATIENT_CHANNEL
