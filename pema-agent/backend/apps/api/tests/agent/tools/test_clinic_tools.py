"""The clinic tools of the agent (package G; no zalo-agent source).

The tools are the actions of ``AgentFacingClinicActions`` seen from the model. The rules pinned here: the
patient is never an argument (it comes from the VERIFIED identity of the turn), an unverified person gets a
marked failure, a booking is a PROPOSAL, a write has a stable idempotency key, and a refused action is a marked
failure with the (PII-free) message of the ``DomainError``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from pema.agent.tools.clinic_tools import (
    NOT_VERIFIED,
    clinic_tool_definitions,
    create_book_tool,
    create_escalation_tool,
    create_get_care_context_tool,
    create_review_draft_tool,
)
from pema.agent.tools.testing import make_policy_context, make_tool_context, make_tool_deps
from pema.agent.tools.tool_failure_result import la_ket_qua_loi
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate, AppointmentOut
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.clinic_actions import (
    AgentAppointmentView,
    AppointmentProposalRequest,
    CareContext,
    EscalationRequest,
    FollowupMilestone,
    IdentityLink,
    IdentityLinkStatus,
    InboxRef,
)
from pema_contracts.common import VN_TZ, now_vn
from pema_contracts.conversations import MessageStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.review import (
    ReviewItemCreate,
    ReviewItemOut,
    ReviewKind,
    ReviewOrigin,
    ReviewStatus,
    RiskLevel,
)
from pema_contracts.testing import make_inbound
from pema_contracts.tools import CLINIC_TOOL_KEYS, ToolContext

PATIENT_ID = uuid4()


@dataclass
class FakeActions:
    link: IdentityLink = field(
        default_factory=lambda: IdentityLink(
            channel=ChannelKind.ZALO_PERSONAL,
            external_user_id="u-1",
            status=IdentityLinkStatus.VERIFIED,
            patient_id=PATIENT_ID,
            patient_code="P025",
        )
    )
    proposals: list[AppointmentProposalRequest] = field(default_factory=list[AppointmentProposalRequest])
    escalations: list[EscalationRequest] = field(default_factory=list[EscalationRequest])
    review_items: list[ReviewItemCreate] = field(default_factory=list[ReviewItemCreate])
    contexts_asked: list[str] = field(default_factory=list[str])
    refuse: DomainError | None = None

    async def get_care_context(self, ctx: ActionContext, patient_ref: str) -> CareContext | None:
        self.contexts_asked.append(patient_ref)
        return CareContext(
            patient_code=patient_ref,
            identity_verified=True,
            display_name="Tên Thật Không Được Lộ",
            remaining_sessions=2,
            followup_milestone=FollowupMilestone.D1,
            consent_messaging=True,
        )

    async def list_upcoming_appointments(
        self, ctx: ActionContext, patient_ref: str, limit: int = 5
    ) -> list[AgentAppointmentView]:
        return [
            AgentAppointmentView(
                id=uuid4(),
                starts_at=datetime(2026, 10, 5, 9, 30, tzinfo=VN_TZ),
                duration_min=45,
                status="booked",
            )
        ]

    async def book_appointment(self, ctx: ActionContext, request: AppointmentCreate) -> AppointmentOut:
        raise NotImplementedError

    async def propose_appointment(
        self, ctx: ActionContext, request: AppointmentProposalRequest
    ) -> ReviewItemOut:
        if self.refuse is not None:
            raise self.refuse
        self.proposals.append(request)
        return self._item(request.job_id)

    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        if self.refuse is not None:
            raise self.refuse
        self.review_items.append(request)
        return self._item(request.job_id)

    async def create_escalation(self, ctx: ActionContext, request: EscalationRequest) -> ReviewItemOut:
        self.escalations.append(request)
        return self._item(request.job_id)

    async def resolve_identity(
        self, ctx: ActionContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityLink:
        return self.link

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        raise NotImplementedError

    async def record_outbound_message(
        self,
        ctx: ActionContext,
        *,
        conversation_id: UUID,
        text: str,
        status: MessageStatus,
        proactive: bool = False,
        review_item_id: UUID | None = None,
        error_code: str | None = None,
    ) -> InboxRef:
        raise NotImplementedError

    @staticmethod
    def _item(job_id: str) -> ReviewItemOut:
        return ReviewItemOut(
            id=uuid4(),
            kind=ReviewKind.REPLY_DRAFT,
            origin=ReviewOrigin.AGENT_TURN,
            status=ReviewStatus.PENDING,
            conversation_id=None,
            patient_id=None,
            patient_code=None,
            draft_text=None,
            risk_level=RiskLevel.NORMAL,
            requires_doctor=False,
            job_id=job_id,
            created_at=now_vn(),
            version=1,
        )


def context(*, verified: bool, msg_id: str = "m-1") -> ToolContext:
    base = make_tool_context(
        profile=PolicyProfileKey.PATIENT_CHANNEL,
        message=make_inbound("cho em hỏi", sender_id="u-1", msg_id=msg_id, channel=ChannelKind.ZALO_PERSONAL),
    )
    policy = dataclasses.replace(
        make_policy_context(PolicyProfileKey.PATIENT_CHANNEL),
        identity_verified=verified,
        patient_id=PATIENT_ID if verified else None,
    )
    return dataclasses.replace(base, policy=policy)


async def test_chua_xac_minh_thi_ca_ba_tool_tra_loi_hong_co_danh_dau_khong_cham_vao_ho_so() -> None:
    """chưa xác minh -> cả các tool là kết quả lỗi có đánh dấu (không đoán, không chạm hồ sơ)"""
    actions = FakeActions()
    ctx = context(verified=False)
    care = await create_get_care_context_tool(ctx, actions).execute({})
    book = await create_book_tool(ctx, actions).execute({"starts_at": "2026-10-05T09:30:00+07:00"})

    assert la_ket_qua_loi(care)
    assert care["loi"] == NOT_VERIFIED
    assert la_ket_qua_loi(book)
    assert actions.contexts_asked == []
    assert actions.proposals == []


async def test_da_xac_minh_tra_moc_cham_soc_khong_co_ten_va_ma_benh_nhan_khong_phai_tham_so() -> None:
    """đã xác minh: kết quả có mốc chăm sóc và lịch hẹn, KHÔNG có tên; mã bệnh nhân lấy từ danh tính, không từ model"""
    actions = FakeActions()
    tool = create_get_care_context_tool(context(verified=True), actions)

    result = await tool.execute({})

    assert isinstance(result, str)
    assert "so_buoi_con_lai: 2" in result
    assert "moc_cham_soc: d1" in result
    assert "2026-10-05T09:30:00+07:00" in result
    assert "Tên Thật" not in result
    assert actions.contexts_asked == ["P025"]
    assert "patient_ref" not in tool.parameters.get("properties", {})


async def test_dat_lich_chi_la_de_xuat_va_job_id_on_dinh_theo_luot() -> None:
    """appointment.book chỉ gửi ĐỀ XUẤT; gọi lại cùng yêu cầu trong cùng lượt ra cùng job_id (idempotent)"""
    actions = FakeActions()
    ctx = context(verified=True)
    tool = create_book_tool(ctx, actions)
    args = {"starts_at": "2026-10-05T09:30:00+07:00", "duration_min": 45}

    first = await tool.execute(args)
    await tool.execute(args)
    await create_book_tool(context(verified=True, msg_id="m-2"), actions).execute(args)

    assert isinstance(first, str)
    assert "ĐỀ XUẤT" in first
    assert actions.proposals[0].patient_ref == "P025"
    assert actions.proposals[0].duration_min == 45
    assert actions.proposals[0].job_id == actions.proposals[1].job_id
    assert actions.proposals[2].job_id != actions.proposals[0].job_id, "tin khác -> yêu cầu khác"


async def test_dat_lich_thieu_mui_gio_hoac_bi_tu_choi_thi_tra_loi_hong() -> None:
    """thiếu múi giờ hoặc action từ chối -> kết quả lỗi có đánh dấu, mang câu của DomainError, không ném"""
    actions = FakeActions(
        refuse=DomainError(ErrorCode.APPOINTMENT_CONFLICT, "Khung giờ này đã có người đặt.")
    )
    tool = create_book_tool(context(verified=True), actions)

    naive = await tool.execute({"starts_at": "2026-10-05T09:30:00"})
    refused = await tool.execute({"starts_at": "2026-10-05T09:30:00+07:00"})

    assert la_ket_qua_loi(naive)
    assert la_ket_qua_loi(refused)
    assert refused["loi"] == "Khung giờ này đã có người đặt."


async def test_escalation_chuyen_bac_si_voi_ma_benh_nhan_khi_da_xac_minh_va_van_chay_khi_chua() -> None:
    """escalation.create: đã xác minh -> kèm mã bệnh nhân; chưa xác minh vẫn chuyển được (không kèm mã)"""
    actions = FakeActions()
    args = {"summary": "khách báo sưng đau tăng", "red_flags": ["swelling"]}

    ok = await create_escalation_tool(context(verified=True), actions).execute(args)
    anonymous = await create_escalation_tool(context(verified=False), actions).execute(args)

    assert isinstance(ok, str)
    assert isinstance(anonymous, str)
    assert actions.escalations[0].patient_ref == "P025"
    assert actions.escalations[1].patient_ref is None
    assert actions.escalations[0].red_flags == ["swelling"]


def test_tool_phong_kham_chi_co_khi_noi_actions_va_dung_khoa_hop_dong() -> None:
    """không nối clinic_actions -> không có tool nào; nối -> đúng 4 khóa của hợp đồng"""
    assert clinic_tool_definitions(make_tool_deps()) == []
    keys = [spec.key for spec in clinic_tool_definitions(make_tool_deps(clinic_actions=FakeActions()))]
    assert keys == ["patient.get_care_context", "appointment.book", "review_item.create", "escalation.create"]
    assert set(keys) == set(CLINIC_TOOL_KEYS), "every key of the contract is a registered tool"


async def test_the_inbox_lookup_never_receives_the_masked_name_or_text() -> None:
    """tra hội thoại Inbox không được truyền tên/nội dung đã che (sẽ ghi đè tên thật bằng [NGUOI_1])"""

    class Recording(FakeActions):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[InboundMessage] = []

        async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
            self.seen.append(message)
            return InboxRef(conversation_id=uuid4(), duplicate=True)

    actions = Recording()
    base = context(verified=True)
    masked = base.message.model_copy(update={"sender_name": "[NGUOI_1]", "text": "sdt [SDT_1]"})
    ctx = dataclasses.replace(base, message=masked)
    await create_escalation_tool(ctx, actions).execute(
        {"summary": "sưng đau tăng", "red_flags": ["swelling"]}
    )
    assert actions.seen, "the tool must look the conversation up"
    assert actions.seen[0].sender_name == ""
    assert actions.seen[0].text == ""
    assert actions.escalations[0].conversation_ref is not None


async def test_review_item_create_soan_nhap_followup_cho_nhan_vien_duyet_khong_gui_di() -> None:
    """review_item.create: tạo bản NHÁP followup_draft (idempotent theo lượt), không có tham số bệnh nhân, không gửi"""
    actions = FakeActions()
    ctx = context(verified=True)
    tool = create_review_draft_tool(ctx, actions, make_tool_deps().policy)
    args = {"draft_text": "Chào chị, phòng khám hỏi thăm sau buổi điều trị hôm qua ạ."}

    first = await tool.execute(args)
    await tool.execute(args)
    await create_review_draft_tool(
        context(verified=True, msg_id="m-2"), actions, make_tool_deps().policy
    ).execute(args)

    assert isinstance(first, str)
    assert "CHƯA được gửi" in first
    item = actions.review_items[0]
    assert item.kind is ReviewKind.FOLLOWUP_DRAFT
    assert item.origin is ReviewOrigin.AGENT_TURN
    assert item.patient_ref == "P025"
    assert item.draft_text == args["draft_text"]
    assert item.clinic_id == ctx.clinic_id
    assert item.risk_level is RiskLevel.NORMAL
    assert item.job_id == actions.review_items[1].job_id
    assert actions.review_items[2].job_id != item.job_id, "tin khác -> yêu cầu khác"
    props = tool.parameters.get("properties", {})
    assert set(props) == {"draft_text"}, "bệnh nhân, loại, rủi ro, cờ đỏ không phải tham số của model"


async def test_review_item_create_chua_xac_minh_van_soan_nhap_nhung_khong_kem_ma_benh_nhan() -> None:
    """chưa xác minh: bản nháp vẫn vào hàng chờ (nhân viên duyệt) nhưng không gắn hồ sơ nào"""
    actions = FakeActions()
    tool = create_review_draft_tool(context(verified=False), actions, make_tool_deps().policy)
    await tool.execute({"draft_text": "Nhắc lịch tái khám."})
    assert actions.review_items[0].patient_ref is None


async def test_review_item_create_bi_tu_choi_hoac_loi_thi_tra_loi_hong_khong_hua_da_gui() -> None:
    """action từ chối -> kết quả lỗi có đánh dấu mang câu của DomainError; nháp rỗng bị schema chặn"""
    actions = FakeActions(refuse=DomainError(ErrorCode.FORBIDDEN, "Không được tạo mục chờ duyệt."))
    tool = create_review_draft_tool(context(verified=True), actions, make_tool_deps().policy)

    refused = await tool.execute({"draft_text": "Chào chị."})

    assert la_ket_qua_loi(refused)
    assert refused["loi"] == "Không được tạo mục chờ duyệt."
    assert actions.review_items == []


async def test_review_item_create_khoi_phuc_ten_that_nhu_cau_tra_loi_cua_luot() -> None:
    """bản nháp model viết với mã giữ chỗ được khôi phục bằng after_llm (nhân viên đọc chữ thật)"""

    class Restoring:
        async def after_llm(self, ctx: object, text: str, mask_token: str | None) -> str:
            assert mask_token is None
            return text.replace("[NGUOI_1]", "chị Lan")

    actions = FakeActions()
    tool = create_review_draft_tool(context(verified=True), actions, Restoring())  # pyright: ignore[reportArgumentType]
    await tool.execute({"draft_text": "Chào [NGUOI_1], hẹn gặp lại."})
    assert actions.review_items[0].draft_text == "Chào chị Lan, hẹn gặp lại."
