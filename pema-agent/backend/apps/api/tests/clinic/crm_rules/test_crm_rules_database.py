# new tests (SQL store and admin service of the CRM rules)
"""The CRM rules against a clean Postgres with pgvector, as the real runtime role ``be_app``.

Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a THROWAWAY database (see ``tests/test_database.py``);
without it every test here is skipped. The module fixture drops every Pema schema and re-runs the alembic
history (including ``b2_0001_crm_protocol_marker``), so never point it at data you care about.

All data is synthetic: patient codes P025.., uuid user ids, no names, phones or messages.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from pema.clinic.crm_rules.admin import SqlCrmRuleAdminService
from pema.clinic.crm_rules.engine import SUPERSEDED_RESOLUTION
from pema.clinic.crm_rules.rules import DEFAULT_RULES
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.clinic.crm_rules.testing import NOW, FakeScheduler
from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic, truncate_installation_data
from pema_contracts.actions import ActionContext
from pema_contracts.crm import CrmRuleUpdate, RuleKey, RuleSendMode
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role
from pema_contracts.scheduler import JobKind

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against", allow_module_level=True)

API_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
VN = "+07:00"

Ids = dict[str, uuid.UUID]


def _ts(text_value: str) -> datetime:
    return datetime.fromisoformat(text_value)


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    assert ADMIN_URL is not None
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


def _role_url(role: str, password: str) -> str:
    assert ADMIN_URL is not None
    return make_url(ADMIN_URL).set(username=role, password=password).render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def db(admin_engine: Engine) -> AsyncIterator[ClinicDatabase]:
    database = ClinicDatabase(_role_url("be_app", BE_PASSWORD), pool_size=2)
    yield database
    await database.dispose()


def _run(conn: Any, sql: str, **params: object) -> Any:
    return conn.execute(text(sql), params)


@pytest.fixture
def clinic(admin_engine: Engine) -> Ids:
    """The one clinic, emptied, with staff, an agent, a bot account, an approved template and six patients."""
    with admin_engine.begin() as conn:
        c = ensure_test_clinic(conn)
        truncate_installation_data(conn)
        ids: Ids = {"clinic": c}
        for role, key in (("owner", "owner"), ("doctor", "doctor"), ("cs_staff", "cs"), ("doctor", "other")):
            ids[key] = _run(
                conn,
                "INSERT INTO clinic.user_account (clinic_id, email, display_name, role) "
                "VALUES (:c, :e, :n, :r) RETURNING id",
                c=c,
                e=f"{key}-{c.hex[:6]}@example.test",
                n=f"Synthetic {key}",
                r=role,
            ).scalar_one()
        _run(conn, "INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, 'default', 'Default')", c=c)
        _run(
            conn,
            "INSERT INTO agent.accounts (clinic_id, id, label, channel, agent_id) "
            "VALUES (:c, 'bot-1', 'Bot', 'zalo_bot', 'default')",
            c=c,
        )
        _run(
            conn,
            "INSERT INTO clinic.message_template (clinic_id, template_key, title, body, marketing, active, "
            "approved_by, approved_at) VALUES (:c, 'crm.d1', 'D+1', 'Synthetic body', false, true, :u, now())",
            c=c,
            u=ids["doctor"],
        )
        for code in ("P025", "P027", "P028", "P030", "P031", "P032"):
            ids[code] = _run(
                conn,
                "INSERT INTO clinic.patient (clinic_id, code, full_name, doctor_id, cs_owner_id, birth_date, "
                "recommendation_at, expected_visit_source) "
                "VALUES (:c, :code, 'Synthetic', :d, :cs, :b, :rec, :src) RETURNING id",
                c=c,
                code=code,
                d=ids["doctor"],
                cs=ids["cs"],
                b="1996-09-23" if code == "P032" else None,
                rec="2026-09-06" if code == "P027" else None,
                src="doctor_recommendation" if code == "P027" else None,
            ).scalar_one()

        def session(
            code: str, when: str, protocol: str | None = None, title: str = "Synthetic session"
        ) -> None:
            _run(
                conn,
                "INSERT INTO clinic.treatment_session (clinic_id, patient_id, performed_at, protocol_id, title) "
                "VALUES (:c, :p, :t, :proto, :title)",
                c=c,
                p=ids[code],
                t=_ts(when),
                proto=protocol,
                title=title,
            )

        session("P025", f"2026-09-19T10:00:00{VN}", "laser-co2")
        session("P027", f"2026-08-21T10:00:00{VN}")
        session("P028", f"2026-08-21T10:00:00{VN}")
        session("P030", f"2026-03-24T10:00:00{VN}")
        session("P031", f"2026-06-16T10:00:00{VN}")
        for code in ("P025", "P030"):
            _run(
                conn,
                "INSERT INTO clinic.treatment_plan (clinic_id, patient_id, service_code, title, total_sessions, "
                "completed_sessions) VALUES (:c, :p, 'svc', 'Synthetic plan', 6, 3)",
                c=c,
                p=ids[code],
            )
        _run(
            conn,
            "INSERT INTO clinic.appointment (clinic_id, patient_id, starts_at, status, missed_at) "
            "VALUES (:c, :p, :t, 'missed', :m)",
            c=c,
            p=ids["P028"],
            t=_ts(f"2026-09-18T10:00:00{VN}"),
            m=_ts(f"2026-09-18T10:00:00{VN}"),
        )
        _run(
            conn,
            "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, patient_id, "
            "verification_status, verified_at) VALUES (:c, 'zalo_bot', 'uid-025', :p, 'verified', now())",
            c=c,
            p=ids["P025"],
        )
        _run(
            conn,
            "INSERT INTO clinic.consent (clinic_id, patient_id, kind, granted, granted_at) "
            "VALUES (:c, :p, 'messaging', true, now())",
            c=c,
            p=ids["P025"],
        )
    return ids


def _owner(clinic_id: uuid.UUID, user: uuid.UUID, role: Role = Role.OWNER) -> ActionContext:
    return ActionContext(clinic_id=clinic_id, actor_type=ActorType.USER, actor_user_id=user, actor_role=role)


def _tasks(engine: Engine, clinic_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT task_key, rule_key, status, priority, due_at, owner_user_id, resolution, source_event_id, "
                "related_appointment_id, related_plan_id FROM clinic.crm_task WHERE clinic_id = :c"
            ),
            {"c": clinic_id},
        ).mappings()
        return {r["task_key"]: dict(r) for r in rows}


def _audit(engine: Engine, clinic_id: uuid.UUID, action: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM clinic.audit_log WHERE clinic_id = :c AND action = :a ORDER BY id"),
            {"c": clinic_id, "a": action},
        ).mappings()
        return [dict(r) for r in rows]


def _runner(db: ClinicDatabase, scheduler: FakeScheduler) -> CrmRulesRunner:
    return CrmRulesRunner(SqlCrmRuleStore(db), scheduler, daily_cap=10, max_lateness_days=1)


async def test_the_ten_rules_are_seeded_per_clinic_and_listed_in_order(
    db: ClinicDatabase, clinic: Ids
) -> None:
    """Mười quy tắc được tạo sẵn cho từng phòng khám và liệt kê đúng thứ tự."""
    service = SqlCrmRuleAdminService(db)
    rules = await service.list_rules(_owner(clinic["clinic"], clinic["owner"]))
    assert [r.rule_key for r in rules] == [d.key for d in DEFAULT_RULES]
    d1 = rules[0]
    assert (d1.delay_days, d1.priority.value, d1.send_mode, d1.version) == (
        1,
        "high",
        RuleSendMode.STAFF_TASK,
        1,
    )
    assert d1.conditions == {"protocol": "laser-co2"}
    assert next(r for r in rules if r.rule_key is RuleKey.DORMANT90).conditions == {"marketing": True}


async def test_tuning_a_rule_uses_a_version_lock_is_audited_and_birthday_stays_staff_only(
    db: ClinicDatabase, clinic: Ids, admin_engine: Engine
) -> None:
    """Chỉnh quy tắc có khoá phiên bản, có ghi audit, và quy tắc sinh nhật luôn là việc cho nhân viên."""
    service = SqlCrmRuleAdminService(db)
    ctx = _owner(clinic["clinic"], clinic["owner"])
    updated = await service.update_rule(
        ctx, RuleKey.D1, CrmRuleUpdate(version=1, send_mode=RuleSendMode.AUTO_REMINDER, delay_days=2)
    )
    assert (updated.version, updated.send_mode, updated.delay_days) == (2, RuleSendMode.AUTO_REMINDER, 2)

    with pytest.raises(DomainError) as stale:
        await service.update_rule(ctx, RuleKey.D1, CrmRuleUpdate(version=1, active=False))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT

    with pytest.raises(DomainError) as birthday:
        await service.update_rule(
            ctx, RuleKey.BIRTHDAY, CrmRuleUpdate(version=1, send_mode=RuleSendMode.AUTO_REMINDER)
        )
    assert birthday.value.code is ErrorCode.VALIDATION_FAILED
    with pytest.raises(DomainError) as manual:
        await service.update_rule(ctx, RuleKey.MANUAL, CrmRuleUpdate(version=1, active=False))
    assert manual.value.code is ErrorCode.NOT_FOUND

    for role in (Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT):
        with pytest.raises(DomainError) as denied:
            await service.list_rules(_owner(clinic["clinic"], clinic["doctor"], role))
        assert denied.value.code is ErrorCode.FORBIDDEN

    rows = _audit(admin_engine, clinic["clinic"], "crm_rule.update")
    assert len(rows) == 1
    assert rows[0]["actor_role"] == "owner"
    assert rows[0]["entity_id"] == "d1"
    assert rows[0]["details"] == {"fields": ["delay_days", "send_mode"], "version": 2}


def test_the_database_itself_refuses_an_automatic_birthday_rule(admin_engine: Engine, clinic: Ids) -> None:
    """Chính cơ sở dữ liệu cũng từ chối quy tắc sinh nhật tự động (ràng buộc CHECK)."""
    with admin_engine.begin() as conn:
        _run(
            conn,
            "INSERT INTO clinic.crm_rule (clinic_id, rule_key, name, trigger, suggested_action, send_mode) "
            "VALUES (:c, 'birthday', 'b', 't', 'a', 'staff_task')",
            c=clinic["clinic"],
        )
    with pytest.raises(Exception, match="crm_rule"), admin_engine.begin() as conn:
        _run(
            conn,
            "UPDATE clinic.crm_rule SET send_mode = 'auto_reminder' WHERE clinic_id = :c AND rule_key = 'birthday'",
            c=clinic["clinic"],
        )


async def test_a_run_writes_the_tasks_once_and_a_rerun_writes_nothing(
    db: ClinicDatabase, clinic: Ids, admin_engine: Engine
) -> None:
    """Lần chạy ghi việc vào Postgres đúng một lần; chạy lại không ghi thêm gì và không audit thêm."""
    scheduler = FakeScheduler()
    runner = _runner(db, scheduler)
    first = await runner.run_clinic(clinic["clinic"], NOW)
    tasks = _tasks(admin_engine, clinic["clinic"])
    assert first.tasks_created == len(tasks) > 0
    rules = {t["rule_key"] for t in tasks.values()}
    assert {"d1", "d3", "d7", "overdue", "no_show", "abandoned", "dormant180", "birthday"} <= rules

    d7 = next(t for k, t in tasks.items() if k.startswith("CRM:d7:P025:"))
    d1 = next(t for k, t in tasks.items() if k.startswith("CRM:d1:P025:"))
    assert d7["owner_user_id"] == clinic["doctor"]
    assert d1["owner_user_id"] == clinic["cs"]
    assert d1["due_at"] == _ts(f"2026-09-20T09:00:00{VN}")
    assert d1["status"] == "open"
    assert d1["priority"] == "high"
    no_show = next(t for k, t in tasks.items() if k.startswith("CRM:no_show:P028:"))
    assert no_show["related_appointment_id"] is not None
    abandoned = next(t for k, t in tasks.items() if k.startswith("CRM:abandoned:P030:"))
    assert abandoned["related_plan_id"] is not None

    with admin_engine.connect() as conn:
        patient = conn.execute(
            text(
                "SELECT recommendation_at, expected_visit_source, last_protocol_session_id, version "
                "FROM clinic.patient WHERE id = :p"
            ),
            {"p": clinic["P025"]},
        ).one()
    assert str(patient[0]) == "2026-10-19"
    assert patient[1] == "service_protocol"
    assert patient[2] is not None
    assert patient[3] == 2
    assert first.patients_updated == 1

    second = await runner.run_clinic(clinic["clinic"], NOW)
    assert (second.tasks_created, second.tasks_superseded, second.patients_updated) == (0, 0, 0)
    assert _tasks(admin_engine, clinic["clinic"]) == tasks
    runs = _audit(admin_engine, clinic["clinic"], "crm_rules.run")
    assert len(runs) == 1
    assert runs[0]["actor_type"] == "system"
    assert runs[0]["details"]["new_tasks"] == first.tasks_created
    assert scheduler.create_calls == 0


async def test_a_message_job_is_created_only_for_a_verified_consenting_patient(
    db: ClinicDatabase, clinic: Ids
) -> None:
    """Job tin nhắn chỉ tạo cho bệnh nhân đã xác minh danh tính và đồng ý nhận tin; chạy lại không tạo thêm."""
    await SqlCrmRuleAdminService(db).update_rule(
        _owner(clinic["clinic"], clinic["owner"]),
        RuleKey.D1,
        CrmRuleUpdate(version=1, send_mode=RuleSendMode.AUTO_REMINDER),
    )
    scheduler = FakeScheduler()
    runner = _runner(db, scheduler)
    first = await runner.run_clinic(clinic["clinic"], NOW)
    assert first.jobs_created == 1
    job = next(iter(scheduler.jobs.values()))
    assert (job.kind, job.payload, job.account_id, job.thread_id) == (
        JobKind.MESSAGE,
        "crm.d1",
        "bot-1",
        "uid-025",
    )
    assert job.patient_id == clinic["P025"]
    assert job.dedupe_key is not None
    assert job.dedupe_key.startswith("CRM:d1:P025:")
    assert job.next_run_at == (NOW + timedelta(0)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    second = await runner.run_clinic(clinic["clinic"], NOW)
    assert (second.jobs_created, second.jobs_already_scheduled) == (0, 1)
    assert scheduler.create_calls == 1


async def test_a_new_booking_supersedes_the_open_task_and_a_resolved_task_is_left_alone(
    db: ClinicDatabase, clinic: Ids, admin_engine: Engine
) -> None:
    """Đặt lịch mới thay thế việc đang mở; việc đã xử lý xong không bị đụng tới."""
    runner = _runner(db, FakeScheduler())
    await runner.run_clinic(clinic["clinic"], NOW)
    tasks = _tasks(admin_engine, clinic["clinic"])
    overdue = next(k for k in tasks if k.startswith("CRM:overdue:P027:"))
    d1 = next(k for k in tasks if k.startswith("CRM:d1:P025:"))
    with admin_engine.begin() as conn:
        _run(conn, "UPDATE clinic.crm_task SET status = 'resolved' WHERE clinic_id = :c AND task_key = :k",
             c=clinic["clinic"], k=d1)  # fmt: skip
        _run(
            conn,
            "INSERT INTO clinic.appointment (clinic_id, patient_id, starts_at, status) VALUES (:c, :p, :t, 'booked')",
            c=clinic["clinic"],
            p=clinic["P027"],
            t=_ts(f"2026-09-27T10:00:00{VN}"),
        )
    report = await runner.run_clinic(clinic["clinic"], NOW)
    after = _tasks(admin_engine, clinic["clinic"])
    assert after[overdue]["status"] == "superseded"
    assert after[overdue]["resolution"] == SUPERSEDED_RESOLUTION
    assert after[d1]["status"] == "resolved"
    assert report.tasks_superseded >= 1


async def test_opting_out_supersedes_the_marketing_task_and_keeps_the_clinical_one(
    db: ClinicDatabase, clinic: Ids, admin_engine: Engine
) -> None:
    """Từ chối nhận tin thay thế việc marketing nhưng giữ việc lâm sàng."""
    runner = _runner(db, FakeScheduler())
    await runner.run_clinic(clinic["clinic"], NOW)
    with admin_engine.begin() as conn:
        _run(conn, "UPDATE clinic.patient SET marketing_opt_out = true WHERE id = :p", p=clinic["P030"])
    await runner.run_clinic(clinic["clinic"], NOW)
    tasks = _tasks(admin_engine, clinic["clinic"])
    status = {k.split(":")[1]: t["status"] for k, t in tasks.items() if ":P030:" in k}
    assert status["dormant180"] == "superseded"
    assert status["abandoned"] == "open"


async def test_the_worker_role_cannot_read_the_crm_task_table(db: ClinicDatabase, clinic: Ids) -> None:
    """Vai trò agent_worker không đọc được bảng việc CRM."""
    await _runner(db, FakeScheduler()).run_clinic(clinic["clinic"], NOW)
    worker = create_engine(_role_url("agent_worker", WORKER_PASSWORD))
    try:
        with pytest.raises(ProgrammingError), worker.connect() as conn:
            conn.execute(text("SELECT count(*) FROM clinic.crm_task"))
    finally:
        worker.dispose()


async def test_a_rule_can_name_its_own_approved_template_in_its_conditions(
    db: ClinicDatabase, clinic: Ids, admin_engine: Engine
) -> None:
    """Quy tắc có thể chỉ định mẫu đã duyệt riêng trong điều kiện; job dùng đúng khoá mẫu đó."""
    await SqlCrmRuleStore(db).ensure_rules(clinic["clinic"])
    with admin_engine.begin() as conn:
        _run(
            conn,
            "INSERT INTO clinic.message_template (clinic_id, template_key, title, body, active, approved_by, "
            "approved_at) VALUES (:c, 'crm.custom', 'Custom', 'Synthetic body', true, :u, now())",
            c=clinic["clinic"],
            u=clinic["doctor"],
        )
        _run(
            conn,
            "UPDATE clinic.crm_rule SET send_mode = 'auto_reminder', conditions = CAST(:j AS jsonb) "
            "WHERE clinic_id = :c AND rule_key = 'd3'",
            c=clinic["clinic"],
            j=json.dumps({"protocol": "laser-co2", "template_key": "crm.custom"}),
        )
    scheduler = FakeScheduler()
    await _runner(db, scheduler).run_clinic(clinic["clinic"], NOW)
    assert [j.payload for j in scheduler.jobs.values()] == ["crm.custom"]
