"""Tool resolution and the tools of the specialists (PLAN-AI01-M section 9, recipe M4 steps 1, 3, 4).

New module (not a port; the tools are new, the plumbing is ``pema.agent.tools.function_tool``).

Resolution (``SpecialistToolkit.resolve_keys`` / ``resolve_tool`` / ``build``). The tools of a specialist are
the allowlist of its ``SpecialistSpec`` MINUS what its ``agent.agents`` record disables MINUS what the policy
profile of the turn disables. Asking for anything outside the allowlist (``delegate`` above all) raises
``ToolResolutionError`` at resolution time, before any model call: depth 1 is a property of the tool set, not
of a prompt. A tool whose port is not wired is left out (and logged), never faked.

Tools (all return a marked failure instead of raising, like every tool of the project):

* ``appointment.search_slots`` (free, read only) over ``SlotSearch``;
* ``appointment.book`` PROPOSES an appointment through B1's ``propose_appointment`` (a draft a member of staff
  confirms; the agent never books). ``patient_chosen=true`` together with L1 ``appointment_confirm``
  (``AppointmentConfirmPolicy``) marks the artifact ``confirm_eligible`` so the care agent may send the
  confirmation through M3's gate; without it the text stays a draft too;
* ``kb_search`` over ``KnowledgeAccess``: every hit received is recorded in ``RunState.citations`` (the
  Knowledge
  agent's citations are THESE, not what the model writes); ``only_approved`` is true whenever the inherited
  profile is ``patient_channel`` (always, toward a patient);
* ``kb_ingest``: creates a text source, unbound and unapproved (staff bind and approve it);
* ``kb_list``.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool, NoArgs
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.care.ports import (
    AppointmentConfirmPolicy,
    KnowledgeAccess,
    SlotQuery,
    SlotSearch,
)
from pema.care.specialists.scheduler import slot_key
from pema.care.specialists.scope import CareTurnScope
from pema.care.specialists.spec import (
    DELEGATE_TOOL,
    TOOL_BOOK,
    TOOL_KB_INGEST,
    TOOL_KB_LIST,
    TOOL_KB_SEARCH,
    TOOL_SEARCH_SLOTS,
    RunState,
    SpecialistSpec,
)
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.agents import AgentProfile
from pema_contracts.clinic_actions import AgentFacingClinicActions, AppointmentProposalRequest
from pema_contracts.errors import DomainError
from pema_contracts.policy import DEFAULT_PROFILES, PolicyProfileKey
from pema_contracts.roles import ActorType
from pema_contracts.tools import AgentTool

logger = logging.getLogger(__name__)

MAX_SLOTS_RETURNED = 20
KB_CONTENT_CHARS = 700
"""A knowledge hit is cut before it goes back to the model (the token ceiling of the turn is small)."""
KB_LIST_LIMIT = 50

type Clock = Callable[[], datetime]


class ToolResolutionError(LookupError):
    """A specialist asked for a tool outside its allowlist (``delegate`` is the case the plan names)."""


# ------------------------------------------------------------------------------------ arguments
class SearchSlotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date = Field(description="Ngày bắt đầu tìm, dạng YYYY-MM-DD")
    to_date: date = Field(description="Ngày kết thúc tìm, dạng YYYY-MM-DD (tối đa 31 ngày sau ngày bắt đầu)")
    duration_min: int = Field(default=30, ge=5, le=480, description="Thời lượng cần (phút)")


class BookInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime = Field(
        description="Giờ bắt đầu, ISO 8601 có múi giờ, đúng một khung giờ appointment.search_slots đã trả về"
    )
    duration_min: int = Field(default=30, ge=5, le=480)
    note: str | None = Field(default=None, max_length=300, description="Ghi chú ngắn, không chứa tên hay SĐT")
    patient_chosen: bool = Field(
        default=False, description="true chỉ khi chính khách đã chọn khung giờ này trong tin nhắn của họ"
    )


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500, description="Câu hỏi cần tra trong kho tri thức")


class IngestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=20_000)


# --------------------------------------------------------------------------------------- toolkit
class SpecialistToolkit:
    """Builds the tools of a specialist run from the ports that are wired (any of them may be absent)."""

    def __init__(
        self,
        *,
        slots: SlotSearch | None = None,
        actions: AgentFacingClinicActions | None = None,
        knowledge: KnowledgeAccess | None = None,
        confirm_policy: AppointmentConfirmPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._slots = slots
        self._actions = actions
        self._knowledge = knowledge
        self._confirm_policy = confirm_policy
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------------------ resolution
    @staticmethod
    def resolve_keys(
        spec: SpecialistSpec, record: AgentProfile | None, profile_key: PolicyProfileKey
    ) -> frozenset[str]:
        """Allowlist - record deny list - profile deny list."""
        keys = set(spec.allowed_tools)
        if record is not None:
            keys -= set(record.disabled_tools)
        keys -= DEFAULT_PROFILES[profile_key].disabled_tool_keys
        keys.discard(DELEGATE_TOOL)
        return frozenset(keys)

    @staticmethod
    def resolve_tool(spec: SpecialistSpec, key: str) -> None:
        """Raises ``ToolResolutionError`` unless ``key`` is on the allowlist of ``spec``."""
        if key == DELEGATE_TOOL or key not in spec.allowed_tools:
            raise ToolResolutionError(f"{spec.agent_id} has no tool '{key}'")

    def build(
        self,
        spec: SpecialistSpec,
        record: AgentProfile | None,
        profile_key: PolicyProfileKey,
        scope: CareTurnScope,
        state: RunState,
    ) -> dict[str, AgentTool]:
        tools: dict[str, AgentTool] = {}
        for key in sorted(self.resolve_keys(spec, record, profile_key)):
            tool = self._build_one(key, profile_key, scope, state)
            if tool is None:
                logger.warning("specialist tool not wired", extra={"agent": spec.agent_id, "tool": key})
                continue
            tools[key] = tool
        return tools

    def _build_one(
        self, key: str, profile_key: PolicyProfileKey, scope: CareTurnScope, state: RunState
    ) -> AgentTool | None:
        if key == TOOL_SEARCH_SLOTS and self._slots is not None:
            return self._search_slots_tool(self._slots, state)
        if key == TOOL_BOOK and self._actions is not None:
            return self._book_tool(self._actions, scope, state)
        if key == TOOL_KB_SEARCH and self._knowledge is not None:
            only_approved = profile_key is PolicyProfileKey.PATIENT_CHANNEL
            return self._kb_search_tool(self._knowledge, state, only_approved=only_approved)
        if key == TOOL_KB_INGEST and self._knowledge is not None:
            return self._kb_ingest_tool(self._knowledge)
        if key == TOOL_KB_LIST and self._knowledge is not None:
            return self._kb_list_tool(self._knowledge)
        return None

    # ---------------------------------------------------------------------------------- tools
    @staticmethod
    def _search_slots_tool(slots: SlotSearch, state: RunState) -> FunctionTool[SearchSlotsInput]:
        async def handler(args: SearchSlotsInput) -> object:
            if args.to_date < args.from_date or (args.to_date - args.from_date).days > 31:
                return ket_qua_loi(
                    "Khoảng ngày không hợp lệ: ngày kết thúc phải sau ngày bắt đầu, tối đa 31 ngày."
                )
            try:
                found = await slots.search(SlotQuery(args.from_date, args.to_date, args.duration_min))
            except Exception as err:
                logger.error("slot search failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Tra khung giờ trống thất bại. Đừng bịa giờ; báo cần nhân viên xử lý.")
            listed: list[dict[str, Any]] = []
            for slot in list(found)[:MAX_SLOTS_RETURNED]:
                if slot.starts_at.tzinfo is None:
                    continue
                state.slots.add(slot_key(slot.starts_at))
                listed.append({"starts_at": slot.starts_at.isoformat(), "duration_min": slot.duration_min})
            return {"slots": listed, "count": len(listed)}

        return FunctionTool(
            name=TOOL_SEARCH_SLOTS,
            description=(
                "Tìm khung giờ còn trống của phòng khám trong một khoảng ngày. Chỉ đọc, không đặt gì. "
                "Chỉ đề xuất những khung giờ tool này trả về."
            ),
            input_model=SearchSlotsInput,
            handler=handler,
        )

    def _book_tool(
        self, actions: AgentFacingClinicActions, scope: CareTurnScope, state: RunState
    ) -> FunctionTool[BookInput]:
        async def handler(args: BookInput) -> object:
            if args.starts_at.tzinfo is None:
                return ket_qua_loi("Giờ hẹn phải có múi giờ, ví dụ +07:00.")
            if slot_key(args.starts_at) not in state.slots:
                return ket_qua_loi(
                    "Giờ này chưa được appointment.search_slots trả về. Tìm khung giờ trống trước, rồi "
                    "chọn đúng một khung."
                )
            digest = hashlib.sha256(f"{scope.turn_key}|{slot_key(args.starts_at)}".encode()).hexdigest()[:20]
            request = AppointmentProposalRequest(
                job_id=f"care:{scope.care_agent.id}:{digest}",
                patient_ref=scope.patient_ref,
                starts_at=args.starts_at,
                duration_min=args.duration_min,
                note=args.note,
            )
            try:
                item = await actions.propose_appointment(
                    ActionContext(
                        clinic_id=scope.care_agent.clinic_id,
                        actor_type=ActorType.AGENT,
                        source=ActionSource.AGENT,
                        request_id=scope.turn_key,
                    ),
                    request,
                )
            except DomainError as err:
                return ket_qua_loi(err.message)
            except Exception as err:
                logger.error("appointment proposal failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Tạo nháp lịch thất bại. Đừng nói với ai là lịch đã được đặt.")
            eligible = False
            if args.patient_chosen and self._confirm_policy is not None:
                eligible = await self._confirm_policy.l1_applies(scope.care_agent.id, self._clock())
            state.artifacts.append(
                {
                    "kind": "appointment_draft",
                    "review_item_id": str(item.id),
                    "starts_at": args.starts_at.isoformat(),
                    "duration_min": args.duration_min,
                    "patient_chosen": args.patient_chosen,
                    "confirm_eligible": eligible,
                }
            )
            return (
                "Đã tạo NHÁP đề xuất lịch hẹn, nhân viên phòng khám sẽ xác nhận. "
                "Đừng nói là lịch đã được đặt."
            )

        return FunctionTool(
            name=TOOL_BOOK,
            description=(
                "Tạo ĐỀ XUẤT (nháp) lịch hẹn cho khung giờ đã tìm thấy; nhân viên xác nhận sau. "
                "Không bao giờ nói lịch đã được đặt."
            ),
            input_model=BookInput,
            handler=handler,
        )

    @staticmethod
    def _kb_search_tool(
        knowledge: KnowledgeAccess, state: RunState, *, only_approved: bool
    ) -> FunctionTool[SearchInput]:
        async def handler(args: SearchInput) -> object:
            try:
                hits = await knowledge.search(args.question, only_approved=only_approved)
            except Exception as err:
                logger.error("knowledge search failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Tra kho tri thức thất bại. Đừng bịa; báo cần nhân viên xử lý.")
            if not hits:
                return {"hits": [], "note": "Không có nguồn phù hợp."}
            listed: list[dict[str, Any]] = []
            for hit in hits:
                state.citations.setdefault(hit.source_id, hit.title or hit.source_name)
                listed.append(
                    {
                        "source_id": hit.source_id,
                        "source": hit.source_name,
                        "title": hit.title,
                        "content": hit.content[:KB_CONTENT_CHARS],
                    }
                )
            return {"hits": listed}

        return FunctionTool(
            name=TOOL_KB_SEARCH,
            description=(
                "Tra kho tri thức của phòng khám. Mỗi kết quả có nguồn; "
                "không có kết quả nghĩa là không có nguồn."
            ),
            input_model=SearchInput,
            handler=handler,
        )

    @staticmethod
    def _kb_ingest_tool(knowledge: KnowledgeAccess) -> FunctionTool[IngestInput]:
        async def handler(args: IngestInput) -> object:
            try:
                brief = await knowledge.ingest_text(args.name, args.text)
            except Exception as err:
                logger.error("knowledge ingest failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Nạp tài liệu thất bại.")
            return (
                f"Đã tạo nguồn '{brief.name}' (mã {brief.source_id}). Nguồn CHƯA được gắn cho agent nào "
                f"và CHƯA "
                "được bác sĩ duyệt; nhân viên sẽ gắn quyền và duyệt trước khi dùng."
            )

        return FunctionTool(
            name=TOOL_KB_INGEST,
            description="Nạp một tài liệu văn bản vào kho tri thức (chưa duyệt, chưa gắn quyền).",
            input_model=IngestInput,
            handler=handler,
        )

    @staticmethod
    def _kb_list_tool(knowledge: KnowledgeAccess) -> FunctionTool[NoArgs]:
        async def handler(_args: NoArgs) -> object:
            try:
                sources = await knowledge.list_sources()
            except Exception as err:
                logger.error("knowledge list failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Liệt kê kho tri thức thất bại.")
            return {
                "sources": [
                    {"source_id": s.source_id, "name": s.name, "status": s.status, "approved": s.approved}
                    for s in sources[:KB_LIST_LIMIT]
                ]
            }

        return FunctionTool(
            name=TOOL_KB_LIST,
            description="Liệt kê các nguồn trong kho tri thức (tên, trạng thái, đã duyệt chưa).",
            input_model=NoArgs,
            handler=handler,
        )
