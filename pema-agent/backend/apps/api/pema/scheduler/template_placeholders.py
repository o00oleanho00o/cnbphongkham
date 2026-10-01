"""Fill the blanks of an approved message template, safely (package G, no TS source).

A doctor-approved template may carry blanks: ``{ten}`` (the patient's name), ``{ngay}`` and ``{gio}``
(date and time of the next appointment). Before this module the scheduler sent the body as it was and the
patient read
"lịch hẹn vào {gio} ngày {ngay}".

The blanks hold personal data, so they are filled ONLY when the identity of the thread is VERIFIED
(``PolicyHooks.verify_identity``) and belongs to the patient of the job. Anything that cannot be filled (not
verified, no job patient, no upcoming appointment, a blank this module does not know) means the text is NOT
sent: the caller keeps the run slot (``conclude_blocked_not_run``) and a person fixes the cause. A half-filled
text never leaves.

Only the three blanks above exist: a template is not a programming language, and every new blank is a new way
to put personal data in a message, which is a product decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.run_context import RunContext
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.roles import ActorType

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_]+)\}")
SUPPORTED_PLACEHOLDERS = frozenset({"ten", "ngay", "gio"})

NOT_FILLABLE = (
    "Mẫu tin có chỗ trống chưa điền được (chưa xác minh danh tính hoặc không có lịch hẹn) - chưa gửi."
)
UNKNOWN_PLACEHOLDER = "Mẫu tin có chỗ trống không được hỗ trợ - chưa gửi."


@dataclass(frozen=True)
class FilledTemplate:
    text: str | None
    """``None``: do NOT send."""
    reason: str = ""


def _scheduler_context(rc: RunContext) -> ActionContext:
    return ActionContext(
        clinic_id=rc.job.clinic_id, actor_type=ActorType.SCHEDULER, source=ActionSource.SCHEDULER
    )


async def fill_template_placeholders(deps: SchedulerDeps, rc: RunContext, body: str) -> FilledTemplate:
    names = set(PLACEHOLDER_RE.findall(body))
    if not names:
        return FilledTemplate(body)
    if not names <= SUPPORTED_PLACEHOLDERS:
        return FilledTemplate(None, UNKNOWN_PLACEHOLDER)

    job = rc.job
    if job.patient_id is None:
        return FilledTemplate(None, NOT_FILLABLE)
    identity = await deps.hooks.verify_identity(rc.policy, rc.account.channel, job.thread_id)
    if not identity.verified or identity.patient_id != job.patient_id:
        return FilledTemplate(None, NOT_FILLABLE)
    patient = await deps.patients.get_patient_ref(job.clinic_id, job.patient_id)
    if patient is None:
        return FilledTemplate(None, NOT_FILLABLE)

    values: dict[str, str] = {}
    context = _scheduler_context(rc)
    if "ten" in names:
        care = await deps.clinic_actions.get_care_context(context, patient.code)
        if care is None or not care.identity_verified or not care.display_name:
            return FilledTemplate(None, NOT_FILLABLE)
        values["ten"] = care.display_name
    if names & {"ngay", "gio"}:
        zone = ZoneInfo(rc.time_zone)
        upcoming = await deps.clinic_actions.list_upcoming_appointments(context, patient.code, 5)
        future = [a for a in upcoming if a.starts_at.astimezone(zone) > rc.now.astimezone(zone)]
        if not future:
            return FilledTemplate(None, NOT_FILLABLE)
        starts: datetime = min(future, key=lambda a: a.starts_at).starts_at.astimezone(zone)
        values["ngay"] = starts.strftime("%d/%m/%Y")
        values["gio"] = starts.strftime("%H:%M")
    return FilledTemplate(PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], body))
