"""SchedulerAgent: finds free slots, proposes a time, creates a DRAFT appointment (PLAN-AI01-M section 9).

New module (not a port). Config factory only: ``scheduler_spec()`` is the data of the ``care-scheduler``
record. Its tools are built by ``pema.care.specialists.toolkit``:

* ``appointment.search_slots``: free (read only), through the ``SlotSearch`` port;
* ``appointment.book``: ``propose_appointment`` of B1: the agent never books, it PROPOSES; the result is a
  ``reply_draft`` review item a member of staff confirms (product decision of 2026-10-01). Whether the
  confirmation message may then go out without review is M3's call: when ``appointment_confirm`` is L1 for
  this care agent AND the patient picked the slot, the run flags ``confirm_eligible`` in the artifact; the
  send itself stays with ``pema.care.autonomy.evaluate_auto_send``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pema.care.specialists.spec import (
    SCHEDULER_ID,
    TOOL_BOOK,
    TOOL_SEARCH_SLOTS,
    RunState,
    SpecialistSpec,
)
from pema.care.task_result import TaskResult
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyProfileKey

NO_SLOT_SUMMARY = "Không có khung giờ phù hợp hoặc chưa tạo được nháp lịch; cần nhân viên xử lý."

SCHEDULER_PERSONA = (
    "Bạn là trợ lý đặt lịch của phòng khám, làm việc phía sau agent chăm sóc khách hàng. Bạn không nói "
    "chuyện "
    "với khách. Việc của bạn: tìm khung giờ trống bằng appointment.search_slots, đề xuất khung giờ phù "
    "hợp, và "
    "chỉ khi được yêu cầu rõ ràng mới tạo ĐỀ XUẤT lịch (nháp) bằng appointment.book. Bạn không bao giờ khẳng "
    "định lịch đã được đặt: nhân viên sẽ xác nhận. Không đoán giờ; chỉ dùng khung giờ tool trả về. Không ghi "
    "tên hay số điện thoại vào bất kỳ trường nào. Kết thúc bằng submit_result: artifacts liệt kê các "
    "khung giờ "
    "({starts_at, duration_min}) hoặc mã nháp; không có khung giờ phù hợp thì needs_human=true."
)


def scheduler_spec() -> SpecialistSpec:
    return SpecialistSpec(
        agent_id=SCHEDULER_ID,
        name="Chuyên viên đặt lịch",
        icon="📅",
        persona=SCHEDULER_PERSONA,
        allowed_tools=frozenset({TOOL_SEARCH_SLOTS, TOOL_BOOK}),
        policy_profile=PolicyProfileKey.STAFF_ASSISTANT,
    )


def slot_key(starts_at: datetime) -> str:
    """The canonical form of a slot start (UTC ISO) used to compare what the tool saw with what the model "
    "says."""
    return starts_at.astimezone(UTC).isoformat()


def _artifact_slot_key(artifact: JsonObject) -> str | None:
    raw = artifact.get("starts_at")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return slot_key(parsed) if parsed.tzinfo is not None else None


def finalize_scheduler_result(result: TaskResult, state: RunState) -> TaskResult:
    """Offer only slots the search really returned, plus the drafts the tools really created.

    A slot the model invented is dropped (never offered to a patient). Nothing real left -> a person decides.
    """
    kept = [a for a in result.artifacts if a.get("kind") == "slot" and _artifact_slot_key(a) in state.slots]
    artifacts = [*kept, *state.artifacts]
    if not artifacts:
        return result.model_copy(update={"artifacts": [], "confidence": 0.0}).with_needs_human(
            NO_SLOT_SUMMARY
        )
    return result.model_copy(update={"artifacts": artifacts})
