# ported from: prototype/shared/crm-data.js (the eight CRM01 cases P025..P032),
# prototype/shared/staff-context.js
"""Synthetic demo data for the clinic of the installation (single tenant): users of every role, patients,
care, appointments, an Inbox, a review queue, consents, message templates and a few CRM tasks. EVERYTHING
here is fictional (AGENT.md): the names say "mau" (sample), the phones are ``000...`` placeholders, the
e-mails end in ``@example.test``.

Run (needs the migrated database and the ``be_app`` URL)::

    PEMA_BE_APP_PASSWORD=... PEMA_DATABASE_URL=postgresql+psycopg://be_app:...@localhost:5432/pema \\
    PEMA_SEED_PASSWORD='choose-one' uv run python -m pema.clinic.actions.seed_demo

``PEMA_SEED_PASSWORD`` is the password of every demo account. When it is not set a random one is generated
and printed ONCE; there is no default password in the repository. The script is idempotent: a second run
finds the demo owner account and stops. The clinic row itself is not created here: the migration creates it
(``PEMA_CLINIC_NAME``) and the CLI makes sure it exists through ``pema.core.installation.ensure_clinic`` with
the owner URL when one is configured. The demo day is the prototype's 2026-09-20 (``--today`` overrides) so
the eight cases line up with ``crm-data.js``: P025 D+1 after laser, P026 D+3, P027 overdue, P028 missed,
P029 abandoned plan, P030 dormant 180, P031 dormant 95, P032 birthday in a week.

The ids of the demo rows are derived from the fixed key ``DEMO_SLUG`` (it is a namespace for ``uuid5``, not a
clinic selector), so a re-run and a test always see the same ids.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid5

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.actions.catalog_seed import seed_default_catalog
from pema.clinic.actions.seed_guide import seed_guide_articles
from pema.clinic.models import (
    Appointment,
    ChannelIdentity,
    Consent,
    Conversation,
    CrmTask,
    Episode,
    Message,
    MessageTemplate,
    Patient,
    ReviewItem,
    TreatmentPlan,
    TreatmentSession,
    UserAccount,
)
from pema.clinic.rbac import passwords
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema.core.installation import ensure_clinic_async
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.common import VN_TZ
from pema_contracts.roles import ActorType, Role

DEMO_SLUG = "pema-demo"
DEMO_DAY = date(2026, 9, 20)
_NAMESPACE = UUID("6f1c2b0e-0000-4000-8000-00000000b101")

USERS: tuple[tuple[str, str, Role], ...] = (
    ("owner", "BS. Tâm (mẫu)", Role.OWNER),
    ("manager", "Quản lý Hạnh (mẫu)", Role.MANAGER),
    ("doctor.mai", "BS. Mai (mẫu)", Role.DOCTOR),
    ("doctor.an", "BS. An (mẫu)", Role.DOCTOR),
    ("cs.maianh", "CSKH Mai Anh (mẫu)", Role.CS_STAFF),
    ("cs.thu", "CSKH Thu (mẫu)", Role.CS_STAFF),
    ("reception.lan", "Lễ tân Lan (mẫu)", Role.RECEPTION),
    ("accountant.hoa", "Kế toán Hoa (mẫu)", Role.ACCOUNTANT),
)

# code, label of the CRM01 case, days since the last session (None: no session), total/completed sessions
CASES: tuple[tuple[str, str, int | None, int, int], ...] = (
    ("P025", "Sau Laser CO2 D+1", 1, 3, 1),
    ("P026", "D+3 gửi ảnh", 3, 3, 1),
    ("P027", "Quá hạn tái khám 14 ngày", 30, 1, 1),
    ("P028", "Vắng hẹn 2 ngày", 35, 1, 1),
    ("P029", "Còn 3/6 buổi, vắng 60 ngày", 60, 6, 3),
    ("P030", "Khách cũ 180 ngày", 180, 1, 1),
    ("P031", "Gọi lại để đặt lịch", 95, 1, 1),
    ("P032", "Sinh nhật tuần này", 7, 1, 1),
)


def _id(*parts: str) -> UUID:
    return uuid5(_NAMESPACE, ":".join(parts))


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=VN_TZ)


@dataclass(frozen=True)
class SeedResult:
    clinic_id: UUID
    created: bool
    users: dict[str, UUID]
    patients: dict[str, UUID]
    conversation_id: UUID | None = None


async def seed_demo(db: ClinicDatabase, *, password: str, today: date = DEMO_DAY) -> SeedResult:
    """Add the demo data to the clinic of the installation; do nothing when it is already there."""
    slug = DEMO_SLUG
    clinic_id = await get_installation_clinic_id(db)
    users = {key: _id("user", slug, key) for key, _, _ in USERS}
    patient_ids = {code: _id("patient", slug, code) for code, *_ in CASES}
    conversation_id = _id("conversation", slug, "P025")
    async with db.session() as probe:
        already = await probe.scalar(select(UserAccount.id).where(UserAccount.id == users["owner"]))
    ctx = ActionContext(
        clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.SYSTEM, request_id="seed-demo"
    )
    if already is not None:
        await seed_default_catalog(db, ctx)  # a demo database from before the catalog gets it on a re-run
        return SeedResult(clinic_id, False, users, patient_ids, conversation_id)

    password_hash = passwords.hash_password(password)
    stamp = _at(today, 9)
    async with db.session() as session:
        for key, name, role in USERS:
            session.add(
                UserAccount(
                    id=users[key],
                    clinic_id=clinic_id,
                    email=f"{key}@example.test",
                    display_name=name,
                    role=role.value,
                    password_hash=password_hash,
                )
            )
        await session.flush()

        doctor = users["doctor.mai"]
        for index, (code, _label, age, _total, _done) in enumerate(CASES):
            pid = patient_ids[code]
            birthday = (
                today + timedelta(days=7) if code == "P032" else date(1985 + index, 3 + index, 10 + index)
            )
            session.add(
                Patient(
                    id=pid,
                    clinic_id=clinic_id,
                    code=code,
                    full_name=f"Bệnh nhân mẫu {code[1:]}",
                    phone=f"0000000{code[1:]}",
                    birth_date=birthday.replace(year=1990) if code == "P032" else birthday,
                    gender="female" if index % 2 == 0 else "male",
                    doctor_id=doctor if index % 2 == 0 else users["doctor.an"],
                    cs_owner_id=users["cs.maianh"] if index % 2 == 0 else users["cs.thu"],
                    first_contact_at=today - timedelta(days=(age or 0) + 40),
                    source="mẫu",
                    marketing_opt_out=code == "P030",
                    recommendation_at=today - timedelta(days=14) if code == "P027" else None,
                    expected_visit_source="doctor_recommendation" if code == "P027" else None,
                    expected_visit_reason="Tái khám theo khuyến nghị bác sĩ (mẫu)"
                    if code == "P027"
                    else None,
                )
            )
        await session.flush()

        for code, label, age, total, done in CASES:
            pid = patient_ids[code]
            episode_id = _id("episode", slug, code)
            plan_id = _id("plan", slug, code)
            session.add(
                Episode(
                    id=episode_id,
                    clinic_id=clinic_id,
                    patient_id=pid,
                    title=f"Đợt chăm sóc: {label}",
                    started_on=today - timedelta(days=(age or 0) + 40),
                )
            )
            await session.flush()
            session.add(
                TreatmentPlan(
                    id=plan_id,
                    clinic_id=clinic_id,
                    patient_id=pid,
                    episode_id=episode_id,
                    doctor_id=doctor,
                    service_code="laser-co2" if code in {"P025", "P026"} else "skin-care",
                    title="Liệu trình mẫu",
                    total_sessions=total,
                    completed_sessions=done,
                    status="active" if done < total else "completed",
                )
            )
            await session.flush()
            if age is not None:
                session.add(
                    TreatmentSession(
                        id=_id("session", slug, code),
                        clinic_id=clinic_id,
                        patient_id=pid,
                        plan_id=plan_id,
                        doctor_id=doctor,
                        performed_at=_at(today - timedelta(days=age), 10),
                        protocol_id="laser-co2" if code in {"P025", "P026"} else None,
                        title="Buổi điều trị mẫu",
                    )
                )

        # appointments: a future visit for P025, a missed one for P028, today's reception queue
        session.add_all(
            [
                Appointment(
                    id=_id("appt", slug, "P025-next"),
                    clinic_id=clinic_id,
                    patient_id=patient_ids["P025"],
                    doctor_id=doctor,
                    starts_at=_at(today + timedelta(days=10), 9),
                    duration_min=45,
                    status="booked",
                    created_by=users["reception.lan"],
                ),
                Appointment(
                    id=_id("appt", slug, "P028-missed"),
                    clinic_id=clinic_id,
                    patient_id=patient_ids["P028"],
                    doctor_id=users["doctor.an"],
                    starts_at=_at(today - timedelta(days=2), 14),
                    duration_min=30,
                    status="missed",
                    missed_at=_at(today - timedelta(days=2), 15),
                    created_by=users["reception.lan"],
                ),
                Appointment(
                    id=_id("appt", slug, "P026-today"),
                    clinic_id=clinic_id,
                    patient_id=patient_ids["P026"],
                    doctor_id=users["doctor.an"],
                    starts_at=_at(today, 15),
                    duration_min=30,
                    status="confirmed",
                    created_by=users["reception.lan"],
                ),
            ]
        )

        # consents: messaging for the first four, marketing refused by P030
        for code in ("P025", "P026", "P027", "P028"):
            session.add(
                Consent(
                    clinic_id=clinic_id,
                    patient_id=patient_ids[code],
                    kind="messaging",
                    granted=True,
                    granted_at=stamp,
                    source="mẫu",
                    recorded_by=users["reception.lan"],
                )
            )
        session.add(
            Consent(
                clinic_id=clinic_id,
                patient_id=patient_ids["P030"],
                kind="marketing",
                granted=False,
                revoked_at=stamp,
                source="mẫu",
                recorded_by=users["cs.thu"],
            )
        )

        # Inbox: P025 is verified on Zalo and wrote after the laser session; P026 is only pending
        identity_p025 = _id("identity", slug, "P025")
        session.add_all(
            [
                ChannelIdentity(
                    id=identity_p025,
                    clinic_id=clinic_id,
                    channel="zalo_bot",
                    external_user_id="demo-uid-025",
                    patient_id=patient_ids["P025"],
                    display_name="Khách mẫu 025",
                    verification_status="verified",
                    verified_at=stamp,
                    verified_by=users["cs.maianh"],
                    last_inbound_at=stamp,
                ),
                ChannelIdentity(
                    id=_id("identity", slug, "P026"),
                    clinic_id=clinic_id,
                    channel="zalo_bot",
                    external_user_id="demo-uid-026",
                    patient_id=patient_ids["P026"],
                    display_name="Khách mẫu 026",
                    verification_status="pending",
                ),
            ]
        )
        await session.flush()
        session.add(
            Conversation(
                id=conversation_id,
                clinic_id=clinic_id,
                channel="zalo_bot",
                external_ref="demo-thread-025",
                patient_id=patient_ids["P025"],
                identity_id=identity_p025,
                status="pending_review",
                last_message_at=stamp,
                last_inbound_at=stamp,
                unread_count=1,
            )
        )
        await session.flush()
        session.add(
            Message(
                clinic_id=clinic_id,
                conversation_id=conversation_id,
                channel="zalo_bot",
                direction="inbound",
                sender_type="patient",
                body="Em thấy da hơi đỏ sau buổi hôm qua, có bình thường không ạ? (tin mẫu)",
                status="received",
                update_id="demo-update-025-1",
                sent_at=stamp,
            )
        )
        session.add(
            ReviewItem(
                id=_id("review", slug, "P025-reply"),
                clinic_id=clinic_id,
                kind="reply_draft",
                origin="agent_turn",
                conversation_id=conversation_id,
                patient_id=patient_ids["P025"],
                job_id="demo-job-reply-025",
                draft_text=(
                    "Chào bạn, da hơi đỏ nhẹ có thể gặp sau thủ thuật. "
                    "Phòng khám sẽ nhờ nhân viên xem lại giúp bạn (nội dung mẫu)."
                ),
                sources=[],
                model="demo-model",
                prompt_version="demo-1",
            )
        )
        session.add(
            ReviewItem(
                id=_id("review", slug, "P026-alert"),
                clinic_id=clinic_id,
                kind="triage_alert",
                origin="policy",
                patient_id=patient_ids["P026"],
                job_id="demo-job-alert-026",
                draft_text="Cờ đỏ mẫu: bệnh nhân nhắc đến chảy máu (dữ liệu hư cấu).",
                risk_level="red_flag",
                red_flags=["bleeding"],
                requires_doctor=True,
            )
        )

        # message templates: one approved by a doctor, one still a draft
        session.add_all(
            [
                MessageTemplate(
                    clinic_id=clinic_id,
                    template_key="nhac_lich_hen",
                    title="Nhắc lịch hẹn",
                    body=(
                        "Phòng khám nhắc bạn có lịch hẹn vào {gio} ngày {ngay}. "
                        "Cần đổi lịch, xin nhắn lại cho chúng tôi."
                    ),
                    marketing=False,
                    active=True,
                    approved_by=users["doctor.mai"],
                    approved_at=stamp,
                ),
                MessageTemplate(
                    clinic_id=clinic_id,
                    template_key="hoi_tham_sau_dieu_tri",
                    title="Hỏi thăm sau điều trị",
                    body=(
                        "Phòng khám hỏi thăm bạn sau buổi điều trị. "
                        "Nếu có điều gì bất thường, xin nhắn ngay cho chúng tôi."
                    ),
                    marketing=False,
                    active=False,
                ),
            ]
        )

        # a few CRM tasks (the rule engine of package B2 creates them normally)
        for code, rule, reason, due_offset in (
            ("P025", "d1", "Sau thủ thuật D+1", 0),
            ("P027", "overdue", "Quá hạn tái khám", -1),
            ("P028", "no_show", "Vắng/hủy chưa đặt lại", 0),
            ("P029", "abandoned", "Nguy cơ bỏ liệu trình", 0),
        ):
            session.add(
                CrmTask(
                    clinic_id=clinic_id,
                    task_key=f"CRM:{rule}:{code}:demo",
                    patient_id=patient_ids[code],
                    rule_key=rule,
                    reason=reason,
                    priority="high",
                    owner_user_id=users["cs.maianh"],
                    due_at=_at(today + timedelta(days=due_offset), 9),
                    suggested_action="Liên hệ chăm sóc (mẫu)",
                    source_event_id="demo",
                )
            )
        await session.flush()
        await audit.record(
            session, ctx, "seed.demo", "clinic", clinic_id, {"patients": len(CASES), "users": len(USERS)}
        )
    await seed_default_catalog(db, ctx)
    return SeedResult(clinic_id, True, users, patient_ids, conversation_id)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed synthetic demo data for this installation's clinic.")
    parser.add_argument("--today", default=DEMO_DAY.isoformat(), help="demo day, YYYY-MM-DD")
    return parser.parse_args(argv)


async def _ensure_installed() -> None:
    """Create the clinic row when ``PEMA_MIGRATION_DATABASE_URL`` (the owner URL) is set (idempotent)."""
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("PEMA_MIGRATION_DATABASE_URL")
    if not url:
        return
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await ensure_clinic_async(conn)
    finally:
        await engine.dispose()


async def _run(today: date) -> int:
    import os

    from pema.config.env import get_settings

    password = os.environ.get("PEMA_SEED_PASSWORD") or ""
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    await _ensure_installed()
    db = ClinicDatabase(get_settings().database_url)
    try:
        result = await seed_demo(db, password=password, today=today)
        guide_added = await seed_guide_articles(db)  # idempotent, also on a clinic seeded before U7
    finally:
        await db.dispose()
    if not result.created:
        sys.stdout.write(f"The demo data is already there; guide articles added: {guide_added}.\n")
        return 0
    sys.stdout.write(f"Seeded the demo clinic with {len(USERS)} users and {len(CASES)} patients.\n")
    if generated:
        sys.stdout.write(f"Generated password for every demo account (shown once): {password}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ensure_selector_event_loop_policy()
    return asyncio.run(_run(date.fromisoformat(args.today)))


if __name__ == "__main__":
    raise SystemExit(main())
