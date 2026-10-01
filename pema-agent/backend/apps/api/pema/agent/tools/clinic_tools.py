"""The clinic tools of the agent (package G, no TS source): PLAN-AI01 principle 3, "the agent goes through the
same action layer as the UI".

Three tools, each one is a method of ``AgentFacingClinicActions`` (package B1), the only door of the agent
side
into clinic data:

* ``patient.get_care_context``: the care context of the patient this turn is talking to (visit and session
  counters, next appointments, consents), never a name, a phone number or a note;
* ``appointment.book``: PROPOSES an appointment (``propose_appointment``): the agent never books, a member of
  staff confirms (product decision of 2026-10-01);
* ``escalation.create``: raises a ``triage_alert`` that goes to a doctor (``create_escalation``).

Rules shared by the three, and the reasons:

* the patient is NEVER an argument. The model could be talked into asking for another patient's context, so
  the
  tool resolves the patient from the VERIFIED identity of the turn (``PolicyContext.identity_verified``, then
  ``resolve_identity`` for the patient code). An unverified person gets a marked failure that tells the
  model to
  ask the person how to verify, not a guess;
* nothing personal goes back to the model except what the action returns (it holds no name);
* the idempotency key of a write (``job_id``) is derived from the clinic, the account, the thread and the id
  of
  the message that started the turn, so a retried turn or a repeated tool call never queues the same proposal
  twice;
* a failed action is a marked failure with the Vietnamese message of the ``DomainError`` (it carries no PII),
  never an exception into the loop.

The tools exist only when ``ToolDeps.clinic_actions`` is given, and ``patient_channel`` is the profile that
keeps them: ``ClinicPolicyHooks.filter_tool_keys`` removes them where identity verification is not required.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool, NoArgs
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.clinic_actions import (
    AgentFacingClinicActions,
    AppointmentProposalRequest,
    CareContext,
    EscalationRequest,
    IdentityLinkStatus,
)
from pema_contracts.errors import DomainError
from pema_contracts.roles import ActorType
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolSpec

log = create_logger("clinic-tools")

NOT_VERIFIED = (
    "Người đang nhắn chưa được xác minh với hồ sơ của phòng khám nên chưa tra được thông tin cá nhân. "
    "Mời họ cho biết số điện thoại đã đăng ký hoặc mã xác nhận do lễ tân gửi để nhân viên xác minh."
)


def _action_context(ctx: ToolContext) -> ActionContext:
    return ActionContext(
        clinic_id=ctx.clinic_id,
        actor_type=ActorType.AGENT,
        source=ActionSource.AGENT,
        request_id=ctx.policy.request_id,
    )


def _turn_key(ctx: ToolContext, tool: str, *parts: str) -> str:
    """Idempotency key: the same turn asking for the same thing is the same request."""
    batch_ids = "|".join(m.msg_id for m in ctx.batch if not m.is_self) or ctx.message.msg_id
    digest = hashlib.sha256("|".join([batch_ids, *parts]).encode("utf-8")).hexdigest()[:20]
    return f"tool:{tool}:{ctx.account.id}:{ctx.message.thread_id}:{digest}"


async def _verified_patient_code(actions: AgentFacingClinicActions, ctx: ToolContext) -> str | None:
    """The code of the patient of this turn, only for a verified identity of the sender."""
    if not ctx.policy.identity_verified:
        return None
    link = await actions.resolve_identity(_action_context(ctx), ctx.account.channel, ctx.message.sender_id)
    if link.status is not IdentityLinkStatus.VERIFIED or link.patient_code is None:
        return None
    return link.patient_code


async def _conversation_ref(actions: AgentFacingClinicActions, ctx: ToolContext) -> str | None:
    """The Inbox conversation of this turn, so a review item can be sent from (``record_inbound_message`` is
    idempotent on ``update_id``: the message is already recorded, the answer carries the conversation id)."""
    try:
        ref = await actions.record_inbound_message(_action_context(ctx), ctx.message)
    except Exception as err:
        log.warning("conversation of the turn not found", err=err)
        return None
    return str(ref.conversation_id)


def _care_lines(care: CareContext) -> list[str]:
    fields: dict[str, Any] = {
        "giai_doan": care.lifecycle_stage,
        "so_ngay_tu_lan_kham_cuoi": care.days_since_last_visit,
        "lieu_trinh_gan_nhat": care.last_protocol_id,
        "so_ngay_tu_buoi_dieu_tri_cuoi": care.days_since_last_session,
        "so_buoi_con_lai": care.remaining_sessions,
        "so_ngay_den_lich_hen_ke_tiep": care.days_to_next_appointment,
        "moc_cham_soc": care.followup_milestone.value if care.followup_milestone else None,
        "tu_choi_tiep_thi": care.marketing_opt_out,
        "dong_y_nhan_tin": care.consent_messaging,
    }
    return [f"- {name}: {value}" for name, value in fields.items() if value is not None]


def create_get_care_context_tool(ctx: ToolContext, actions: AgentFacingClinicActions) -> FunctionTool[NoArgs]:
    async def handler(_args: NoArgs) -> object:
        try:
            code = await _verified_patient_code(actions, ctx)
            if code is None:
                return ket_qua_loi(NOT_VERIFIED)
            care = await actions.get_care_context(_action_context(ctx), code)
            if care is None:
                return ket_qua_loi("Không tìm thấy hồ sơ chăm sóc của người này.")
            appointments = await actions.list_upcoming_appointments(_action_context(ctx), code, 3)
        except DomainError as err:
            return ket_qua_loi(err.message)
        except Exception as err:
            log.error("get_care_context failed", err=err)
            return ket_qua_loi("Tra hồ sơ chăm sóc thất bại. Nói thật với người dùng, đừng bịa.")
        lines = ["Hồ sơ chăm sóc của người đang trò chuyện:", *_care_lines(care)]
        for item in appointments:
            lines.append(
                f"- lịch hẹn: {item.starts_at.isoformat()} ({item.duration_min} phút, {item.status})"
            )
        return "\n".join(lines)

    return FunctionTool(
        name="patient.get_care_context",
        description=(
            "Tra mốc chăm sóc của CHÍNH người đang nhắn (số ngày từ buổi điều trị cuối, số buổi còn lại, "
            "lịch hẹn sắp tới, đồng ý nhận tin). Không cần tham số: hệ thống tự lấy hồ sơ của người đã "
            "được xác minh. Chưa xác minh thì không tra được."
        ),
        input_model=NoArgs,
        handler=handler,
    )


class BookInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime = Field(
        description="Giờ bắt đầu mong muốn, ISO 8601 có múi giờ +07:00, ví dụ 2026-10-05T09:30:00+07:00"
    )
    duration_min: int = Field(default=30, ge=5, le=480, description="Thời lượng (phút)")
    note: str | None = Field(default=None, max_length=300, description="Ghi chú ngắn, không chứa tên hay SĐT")


def create_book_tool(ctx: ToolContext, actions: AgentFacingClinicActions) -> FunctionTool[BookInput]:
    async def handler(args: BookInput) -> object:
        if args.starts_at.tzinfo is None:
            return ket_qua_loi("Giờ hẹn phải có múi giờ, ví dụ +07:00.")
        try:
            code = await _verified_patient_code(actions, ctx)
            if code is None:
                return ket_qua_loi(NOT_VERIFIED)
            request = AppointmentProposalRequest(
                job_id=_turn_key(ctx, "appointment.book", args.starts_at.isoformat()),
                patient_ref=code,
                conversation_ref=await _conversation_ref(actions, ctx),
                starts_at=args.starts_at,
                duration_min=args.duration_min,
                note=args.note,
            )
            await actions.propose_appointment(_action_context(ctx), request)
        except DomainError as err:
            return ket_qua_loi(err.message)
        except Exception as err:
            log.error("appointment.book failed", err=err)
            return ket_qua_loi("Ghi nhận đề xuất lịch thất bại. Nói thật với người dùng, đừng hứa đã đặt.")
        return (
            "Đã ghi nhận ĐỀ XUẤT lịch hẹn. Nhân viên phòng khám sẽ xác nhận rồi nhắn lại. "
            "Đừng nói với người dùng là lịch đã được đặt."
        )

    return FunctionTool(
        name="appointment.book",
        description=(
            "Đề xuất một lịch hẹn cho CHÍNH người đang nhắn (đã xác minh). Bạn KHÔNG đặt được lịch: đây "
            "chỉ là đề xuất, nhân viên xác nhận sau. Nói rõ điều đó với người dùng."
        ),
        input_model=BookInput,
        handler=handler,
    )


class EscalationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        min_length=1,
        max_length=300,
        description="Tóm tắt ngắn lý do cần bác sĩ, không chứa tên, SĐT hay địa chỉ",
    )
    red_flags: list[str] = Field(
        default_factory=list[str],
        max_length=5,
        description="Mã triệu chứng nếu có, ví dụ bleeding, fever, pus, dyspnea",
    )


def create_escalation_tool(
    ctx: ToolContext, actions: AgentFacingClinicActions
) -> FunctionTool[EscalationInput]:
    async def handler(args: EscalationInput) -> object:
        try:
            code = await _verified_patient_code(actions, ctx)
            request = EscalationRequest(
                job_id=_turn_key(ctx, "escalation.create", args.summary),
                patient_ref=code,
                conversation_ref=await _conversation_ref(actions, ctx),
                red_flags=[flag[:40] for flag in args.red_flags],
                summary=args.summary,
            )
            await actions.create_escalation(_action_context(ctx), request)
        except DomainError as err:
            return ket_qua_loi(err.message)
        except Exception as err:
            log.error("escalation.create failed", err=err)
            return ket_qua_loi(
                "Chuyển cho bác sĩ thất bại. Nói thật với người dùng và mời họ gọi phòng khám."
            )
        return "Đã chuyển cho bác sĩ. Báo người dùng là phòng khám sẽ liên hệ lại sớm."

    return FunctionTool(
        name="escalation.create",
        description=(
            "Chuyển cuộc trò chuyện cho BÁC SĨ khi người dùng nêu dấu hiệu đáng lo hoặc yêu cầu gặp bác sĩ. "
            "Không chẩn đoán, không trấn an thay bác sĩ."
        ),
        input_model=EscalationInput,
        handler=handler,
    )


def clinic_tool_definitions(deps: ToolDeps) -> list[ToolSpec]:
    """The three specs, or none when no clinic actions are wired."""
    actions = deps.clinic_actions
    if actions is None:
        return []

    def build_care(ctx: ToolContext) -> AgentTool:
        return create_get_care_context_tool(ctx, actions)

    def build_book(ctx: ToolContext) -> AgentTool:
        return create_book_tool(ctx, actions)

    def build_escalation(ctx: ToolContext) -> AgentTool:
        return create_escalation_tool(ctx, actions)

    return [
        ToolSpec(
            key="patient.get_care_context",
            label="Hồ sơ chăm sóc",
            description="Tra mốc chăm sóc của người đang nhắn (chỉ khi đã xác minh danh tính)",
            group=ToolGroup.READ,
            runs_in_scheduled_turn=False,
            build=build_care,
        ),
        ToolSpec(
            key="appointment.book",
            label="Đề xuất lịch hẹn",
            description="Đề xuất lịch hẹn cho người đang nhắn; nhân viên xác nhận, bot không tự đặt",
            group=ToolGroup.ACTION,
            runs_in_scheduled_turn=False,
            build=build_book,
        ),
        ToolSpec(
            key="escalation.create",
            label="Chuyển bác sĩ",
            description="Chuyển hội thoại cho bác sĩ khi có dấu hiệu đáng lo",
            group=ToolGroup.ACTION,
            runs_in_scheduled_turn=False,
            build=build_escalation,
        ),
    ]
