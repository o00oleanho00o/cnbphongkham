"""Postgres readers the scheduler needs (new module, no zalo-agent source).

Each one reads exactly the surface the ``agent_worker`` role may touch: ``agent.threads`` (its own schema) and
the ``clinic_agent`` views of migration 0003 (``channel_policy``, ``message_template_approved``). No
``clinic.*`` table is read here: the import-linter rule "agent-side packages reach the clinic only through
``pema.clinic.actions``" is about Python imports; the DATABASE rule is the same, enforced by the grants."""

from __future__ import annotations

from datetime import time
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase
from pema.scheduler.ports import ApprovedTemplate, ChannelPolicy, PatientRef, ThreadStatus


def _hhmm(value: time | None) -> str | None:
    return None if value is None else value.strftime("%H:%M")


class PgThreadStatusReader:
    """``findThreadStatus`` of ``thread-store.ts`` over ``agent.threads``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def find_thread_status(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> ThreadStatus | None:
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT bot_enabled FROM agent.threads "
                        "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
                    ),
                    {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id},
                )
            ).first()
        return None if row is None else ThreadStatus(bot_enabled=bool(row[0]))


class PgChannelPolicyReader:
    """The clinic-wide switchboard per channel kind (``clinic_agent.channel_policy``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_channel_policy(self, clinic_id: UUID, channel: str) -> ChannelPolicy | None:
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT enabled, kill_switch_on, daily_cap, send_window_start, send_window_end "
                        "FROM clinic_agent.channel_policy WHERE channel = :channel"
                    ),
                    {"channel": channel},
                )
            ).first()
        if row is None:
            return None
        return ChannelPolicy(
            enabled=bool(row[0]),
            kill_switch_on=bool(row[1]),
            daily_cap=None if row[2] is None else int(row[2]),
            send_window_start=_hhmm(row[3]),
            send_window_end=_hhmm(row[4]),
        )


class PgApprovedTemplateReader:
    """Doctor-approved templates (``clinic_agent.message_template_approved``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_template(self, clinic_id: UUID, template_key: str) -> ApprovedTemplate | None:
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT template_key, title, body, marketing "
                        "FROM clinic_agent.message_template_approved WHERE template_key = :key"
                    ),
                    {"key": template_key},
                )
            ).first()
        if row is None:
            return None
        return ApprovedTemplate(
            template_key=str(row[0]), title=str(row[1]), body=str(row[2]), marketing=bool(row[3])
        )


class PgPatientRefReader:
    """Pseudonym code + marketing opt-out of a patient (``clinic_agent.patient_ref``: no phone, no birth date,
    no address, no free clinical text)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_patient_ref(self, clinic_id: UUID, patient_id: UUID) -> PatientRef | None:
        async with self._db.session() as s:
            row = (
                await s.execute(
                    text("SELECT code, marketing_opt_out FROM clinic_agent.patient_ref WHERE id = :id"),
                    {"id": patient_id},
                )
            ).first()
        return None if row is None else PatientRef(code=str(row[0]), marketing_opt_out=bool(row[1]))
