"""Fill the blanks of an approved template only for a verified identity (package G; no zalo-agent source).

The template of the demo clinic says "lịch hẹn vào {gio} ngày {ngay}". It used to be sent like that. These tests
pin the rule: the blanks are filled for a VERIFIED thread of the job's patient, and in every other case nothing
is sent (``text is None``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.ports import PatientRef
from pema.scheduler.run_context import RunContext
from pema.scheduler.template_placeholders import (
    NOT_FILLABLE,
    UNKNOWN_PLACEHOLDER,
    fill_template_placeholders,
)
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind
from pema_contracts.clinic_actions import AgentAppointmentView, CareContext
from pema_contracts.common import VN_TZ
from pema_contracts.policy import IdentityStatus

BODY = "Phòng khám nhắc bạn có lịch hẹn vào {gio} ngày {ngay}."
PATIENT = uuid4()
CLINIC = uuid4()
NOW = datetime(2026, 9, 20, 9, 0, tzinfo=VN_TZ)


@dataclass
class Hooks:
    identity: IdentityStatus
    asked: list[tuple[ChannelKind, str]] = field(default_factory=list[tuple[ChannelKind, str]])

    async def verify_identity(
        self, ctx: object, channel: ChannelKind, external_user_id: str
    ) -> IdentityStatus:
        self.asked.append((channel, external_user_id))
        return self.identity


@dataclass
class Actions:
    appointments: list[AgentAppointmentView] = field(default_factory=list[AgentAppointmentView])
    name: str | None = "Khách Mẫu"

    async def get_care_context(self, ctx: ActionContext, patient_ref: str) -> CareContext | None:
        return CareContext(patient_code=patient_ref, identity_verified=True, display_name=self.name)

    async def list_upcoming_appointments(
        self, ctx: ActionContext, patient_ref: str, limit: int = 5
    ) -> list[AgentAppointmentView]:
        return self.appointments


class Patients:
    async def get_patient_ref(self, clinic_id: UUID, patient_id: UUID) -> PatientRef | None:
        return PatientRef(code="P025", marketing_opt_out=False)


def appointment(starts: datetime) -> AgentAppointmentView:
    return AgentAppointmentView(id=uuid4(), starts_at=starts, duration_min=30, status="booked")


def rig(
    hooks: Hooks, actions: Actions, *, patient_id: UUID | None = PATIENT
) -> tuple[SchedulerDeps, RunContext]:
    deps = SimpleNamespace(hooks=hooks, clinic_actions=actions, patients=Patients())
    job = SimpleNamespace(clinic_id=CLINIC, patient_id=patient_id, thread_id="uid-1")
    context = SimpleNamespace(
        job=job,
        account=SimpleNamespace(channel=ChannelKind.ZALO_BOT),
        policy=object(),
        time_zone="Asia/Ho_Chi_Minh",
        now=NOW,
    )
    return cast("SchedulerDeps", deps), cast("RunContext", context)


async def test_mau_khong_co_cho_trong_giu_nguyen_khong_hoi_danh_tinh() -> None:
    """mẫu không có chỗ trống thì giữ nguyên, không đụng tới danh tính"""
    hooks = Hooks(IdentityStatus(verified=False))
    deps, rc = rig(hooks, Actions())

    result = await fill_template_placeholders(deps, rc, "Phòng khám hỏi thăm bạn sau điều trị.")

    assert result.text == "Phòng khám hỏi thăm bạn sau điều trị."
    assert hooks.asked == []


async def test_danh_tinh_da_xac_minh_dien_gio_va_ngay_cua_lich_hen_sap_toi() -> None:
    """đã xác minh -> điền {gio} và {ngay} bằng lịch hẹn sắp tới gần nhất, theo múi giờ phòng khám"""
    actions = Actions(
        [
            appointment(datetime(2026, 9, 25, 14, 30, tzinfo=VN_TZ)),
            appointment(datetime(2026, 9, 22, 8, 0, tzinfo=VN_TZ)),
        ]
    )
    deps, rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), actions)

    result = await fill_template_placeholders(deps, rc, BODY)

    assert result.text == "Phòng khám nhắc bạn có lịch hẹn vào 08:00 ngày 22/09/2026."


async def test_chua_xac_minh_thi_khong_gui_ban_nua_chung() -> None:
    """chưa xác minh (hoặc xác minh cho người khác) -> text None, không bao giờ gửi bản điền dở"""
    for identity in (IdentityStatus(verified=False), IdentityStatus(verified=True, patient_id=uuid4())):
        deps, rc = rig(Hooks(identity), Actions([appointment(datetime(2026, 9, 25, 9, 0, tzinfo=VN_TZ))]))
        result = await fill_template_placeholders(deps, rc, BODY)
        assert result.text is None
        assert result.reason == NOT_FILLABLE


async def test_khong_co_lich_hen_sap_toi_hoac_lich_da_qua_thi_khong_gui() -> None:
    """không có lịch hẹn nào trong tương lai -> không gửi"""
    past = appointment(datetime(2026, 9, 19, 9, 0, tzinfo=VN_TZ))
    for appointments in ([], [past]):
        deps, rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), Actions(appointments))
        result = await fill_template_placeholders(deps, rc, BODY)
        assert result.text is None


async def test_job_khong_gan_benh_nhan_hoac_cho_trong_la_thi_khong_gui() -> None:
    """job không có bệnh nhân, hoặc chỗ trống lạ -> không gửi"""
    deps, rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), Actions(), patient_id=None)
    assert (await fill_template_placeholders(deps, rc, BODY)).text is None

    deps, rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), Actions())
    unknown = await fill_template_placeholders(deps, rc, "Mã của bạn là {ma_so}.")
    assert unknown.text is None
    assert unknown.reason == UNKNOWN_PLACEHOLDER


async def test_cho_trong_ten_dung_ten_cua_nguoi_da_xac_minh() -> None:
    """{ten} lấy từ hồ sơ của người đã xác minh; thiếu tên thì không gửi"""
    ok_deps, ok_rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), Actions(name="Khách Mẫu"))
    assert (await fill_template_placeholders(ok_deps, ok_rc, "Chào {ten}.")).text == "Chào Khách Mẫu."

    miss_deps, miss_rc = rig(Hooks(IdentityStatus(verified=True, patient_id=PATIENT)), Actions(name=None))
    assert (await fill_template_placeholders(miss_deps, miss_rc, "Chào {ten}.")).text is None
