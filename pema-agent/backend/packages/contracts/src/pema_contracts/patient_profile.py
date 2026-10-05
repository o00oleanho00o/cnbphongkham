"""Patient 360 dialogs and cards of package U, step U9: "Thông tin cần nhớ", "Tiền sử & chẩn đoán",
"Ngày dự kiến quay lại", "Chăm sóc tại nhà" / "Nhắn tin" (a note on the patient app timeline), the templated
brief, and "Thêm dịch vụ vào liệu trình".

Source of the fields and the sentences: ``prototype/shared/clinic.js`` (``modalHtml``, ``action``),
``crm-automation.js`` (``clinical``, ``expected``), ``care-finance.js`` (``addService``), ``data.js``
(``brief``).
Rules the DTOs keep:

* Free text here is clinical or personal content. It travels in these bodies only, never in audit details,
  logs or the agent's view.
* Blank checks that have an exact sentence in the old web (``Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.``)
  are done by the action, not by a length constraint, so the message the staff sees is the old one.
* The brief is a template over existing facts: no model is called, no clinical judgement is made. A doctor
  edits and approves it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.patient_care import MAX_PLAN_SESSIONS
from pema_contracts.patients import PatientOut, TreatmentPlanOut

MAX_ALERTS: Final = 20
MAX_ALERT_CHARS: Final = 200
MAX_TEXT_CHARS: Final = 4000
MAX_APP_UPDATE_CHARS: Final = 2000
EXPECTED_SOURCES: Final = (
    "doctor_recommendation",
    "service_protocol",
    "treatment_plan",
    "followup_automation",
)
"""Old ``C.sources`` without ``appointment``: the booking itself is the source of an appointment date and is
never typed in (``Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.``)."""
EXPECTED_RETURN_INVALID_MESSAGE: Final = "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị."
CLINICAL_NOTE_BLANK_MESSAGE: Final = "Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận."
BRIEF_BLANK_MESSAGE: Final = "Brief không được để trống."
AFTERCARE_BLANK_MESSAGE: Final = "Hãy nhập hướng dẫn."
MESSAGE_BLANK_MESSAGE: Final = "Hãy nhập nội dung tin nhắn."


# --------------------------------------------------------------------------- the chips of /patients
class PatientListView(StrEnum):
    """Old ``patientFilter``: Tất cả, Đang điều trị, Tái khám tuần này, Có cảnh báo."""

    ALL = "all"
    ACTIVE = "active"
    """A plan still open with sessions left."""
    NEXT = "next"
    """An appointment from today to seven days ahead."""
    ALERTS = "alerts"
    """At least one line in 'Thông tin cần nhớ'."""


# --------------------------------------------------------------------------------------- Thông tin cần nhớ
class AlertsUpdate(ApiModel):
    """Old ``alerts-edit``: one warning per line. Blank lines are dropped, each line is trimmed."""

    alerts: list[str] = Field(max_length=MAX_ALERTS, description="One warning per entry.")


class AlertsOut(ApiModel):
    alerts: list[str]


# -------------------------------------------------------------------------------- Tiền sử & chẩn đoán
class ClinicalNoteUpdate(ApiModel):
    """Old ``crm-history`` and ``crm-diagnosis``. Both are required (the action answers with
    ``CLINICAL_NOTE_BLANK_MESSAGE``)."""

    history: str = Field(max_length=MAX_TEXT_CHARS, description="Tiền sử đã khai thác.")
    diagnosis: str = Field(
        max_length=MAX_TEXT_CHARS,
        description="Khám / chẩn đoán do bác sĩ xác nhận. Never written by a model.",
    )


class ClinicalNoteOut(ApiModel):
    history: str = ""
    diagnosis: str = ""
    reviewed_by_name: str | None = None
    reviewed_at: VnDatetime | None = None


# ----------------------------------------------------------------------------- Ngày dự kiến quay lại
class ExpectedReturnUpdate(ApiModel):
    """Old ``crm-expected-date``, ``crm-expected-reason``, ``crm-expected-source``. The date is a string so
    the action can answer an impossible date (``2026-02-30``) with the old sentence instead of a 422."""

    date: str = Field(max_length=10, description="YYYY-MM-DD")
    reason: str = Field(max_length=200)
    source: str = Field(max_length=40, description="One of EXPECTED_SOURCES.")


class ExpectedReturnOut(ApiModel):
    date: str
    reason: str
    source: str


# --------------------------------------------------------------- Chăm sóc tại nhà / Nhắn tin / Brief
class AppUpdateKind(StrEnum):
    MESSAGE = "message"
    """"Nhắn tin": a short note to the patient (needs ``conversation.reply``)."""
    AFTERCARE = "aftercare"
    """"Chăm sóc tại nhà": the approved aftercare instruction (needs ``session.write``)."""


class AppUpdateCreate(ApiModel):
    kind: AppUpdateKind
    body: str = Field(max_length=MAX_APP_UPDATE_CHARS)


class AppUpdateOut(ApiModel):
    """One note on the patient app timeline. Nothing is sent through Zalo or any channel."""

    id: UUID
    kind: AppUpdateKind
    body: str
    created_at: VnDatetime
    by_name: str | None = None


class BriefApprovedOut(ApiModel):
    id: UUID
    text: str
    approved_by_name: str | None = None
    approved_at: VnDatetime
    source_ids: list[str]


class BriefDraftOut(ApiModel):
    """The templated brief of a patient: ``text`` is built from existing records (``source_ids`` names them as
    ``kind:id`` like the timeline), never by a model. ``approved`` is the last version a doctor approved."""

    text: str
    source_ids: list[str]
    approved: BriefApprovedOut | None = None


class BriefApprove(ApiModel):
    text: str = Field(max_length=MAX_TEXT_CHARS, description="The brief as the doctor edited it.")


# ------------------------------------------------------------------ Thêm dịch vụ vào liệu trình
class PatientFinanceTabOut(ApiModel):
    """The data of the 'Dịch vụ & tài chính' tab without any clinical record (``finance.read``): who the
    patient is and the courses with sessions used and the price fixed on them. The accountant has no
    Patient 360; this is its tab. The catalog for 'Thêm dịch vụ' is ``GET /services`` (``finance.write``)."""

    patient: PatientOut
    plans: list[TreatmentPlanOut]


class ServicePlanCreate(ApiModel):
    """Old ``linked-service-form``: service, number of sessions (1 to 20), discount. The price is read
    from the catalog by the action and fixed on the plan."""

    service_id: UUID
    sessions: int = Field(ge=1, le=MAX_PLAN_SESSIONS)
    discount_vnd: int = Field(default=0, ge=0, le=10**10)
