# ported from: prototype/shared/crm-automation.js, prototype/shared/crm-data.js (behavioural equivalence)
"""Equivalence of the Python rule engine with the ORIGINAL JavaScript engine (acceptance test of package B2).

``tests/fixtures/crm_rules/export_js_fixture.cjs`` runs ``prototype/shared/crm-data.js`` and
``crm-automation.js`` under node with the fixed clock 2026-09-20 on the synthetic CRM01 seed (46 patients, the
eight stories P025..P032 and the ten mobile cases) and records, per scenario, the engine INPUT (rules, patient
snapshots, stored tasks) and the OUTPUT (every task after the run, every patient's CRM profile). These tests
feed the same input to ``pema.clinic.crm_rules`` and require the same task set, field for field, and the same
read model. Node is not needed to run them; the JSON is committed.

Where the Python deliberately differs (all listed in ``pema/clinic/crm_rules/engine.py``) the comparison
normalises the JavaScript side, and says so below: ``createdAt`` is not compared (constant 08:00 vs ``now``),
a synthetic ``LP-<patient>`` plan id becomes None.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from pema.clinic.crm_rules.engine import SUPERSEDED_RESOLUTION, run_rules
from pema.clinic.crm_rules.records import (
    AppointmentSnapshot,
    AppointmentStatus,
    ExistingTask,
    PatientSnapshot,
    RulesOutcome,
    SessionSnapshot,
)
from pema.clinic.crm_rules.rules import RuleConfig
from pema.clinic.crm_rules.testing import NOW
from pema_contracts.crm import RuleKey, TaskPriority, TaskStatus

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "crm_rules" / "crm_rules_js_scenarios.json"
NAMESPACE = UUID("6f1c0d4e-2b57-4f0e-9a43-5d1e7a9c8b21")
BASE_SCENARIO = "rerun_is_idempotent"

Js = dict[str, Any]


def uid(name: str) -> UUID:
    """Staff names and patient codes of the prototype become stable uuids (the Python side uses user ids)."""
    return uuid5(NAMESPACE, name)


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    rules: list[Js]
    patients: list[Js]
    existing_tasks: list[Js]
    expected_tasks: dict[str, Js]
    expected_patients: dict[str, Js]


def _load() -> list[Scenario]:
    data: Js = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw: list[Js] = data["scenarios"]
    base = next(s for s in raw if s["name"] == BASE_SCENARIO)
    base_patients: dict[str, Js] = {p["id"]: p for p in base["input"]["patients"]}
    base_tasks: dict[str, Js] = {t["id"]: t for t in base["expected"]["tasks"]}
    base_profiles: dict[str, Js] = dict(base["expected"]["patients"])
    scenarios: list[Scenario] = []
    for s in raw:
        if "patients" in s["input"]:
            patients = list(s["input"]["patients"])
            tasks = {t["id"]: t for t in s["expected"]["tasks"]}
            profiles: dict[str, Js] = dict(s["expected"]["patients"])
        else:
            changed = {p["id"]: p for p in s["input"]["patientsChanged"]}
            patients = [changed.get(code, p) for code, p in base_patients.items()]
            changed_tasks = {t["id"]: t for t in s["expected"]["tasksChanged"]}
            tasks = {i: changed_tasks.get(i, base_tasks.get(i)) for i in s["expected"]["taskIds"]}
            profiles = {**base_profiles, **s["expected"]["patientsChanged"]}
        scenarios.append(
            Scenario(
                name=s["name"],
                description=s["description"],
                rules=s["input"]["rules"],
                patients=patients,
                existing_tasks=s["input"]["existingTasks"],
                expected_tasks=tasks,
                expected_patients=profiles,
            )
        )
    return scenarios


SCENARIOS = _load()
_IDS = [s.name for s in SCENARIOS]


def _dt(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def to_rule(js: Js) -> RuleConfig:
    return RuleConfig(
        key=RuleKey(js["id"]),
        name=js["name"],
        trigger=js["trigger"],
        delay_days=js["delayDays"],
        suggested_action=js["suggestedAction"],
        priority=TaskPriority(js["priority"]),
        active=js["active"],
        protocol=js["protocol"],
        marketing=bool(js["marketing"]),
    )


def to_patient(js: Js) -> PatientSnapshot:
    appointments = tuple(
        AppointmentSnapshot(
            id=a["id"],
            starts_at=datetime.fromisoformat(f"{a['date']}T{a['time']}:00+07:00"),
            status=AppointmentStatus(a["status"]),
            cancelled_at=_dt(a["cancelledAt"]),
            missed_at=_dt(a["missedAt"]),
        )
        for a in js["appointments"]
    )
    return PatientSnapshot(
        id=uid(js["id"]),
        code=js["id"],
        doctor_id=uid(js["doctor"]),
        cs_owner_id=uid(js["owner"]),
        last_visit=date.fromisoformat(js["lastVisit"]) if js["lastVisit"] else None,
        total_sessions=js["total"],
        completed_sessions=js["completed"],
        sessions=tuple(
            SessionSnapshot(s["id"], date.fromisoformat(s["date"]), s["protocolId"]) for s in js["sessions"]
        ),
        appointments=appointments,
        birth_date=date.fromisoformat(js["birthday"]) if js["birthday"] else None,
        marketing_opt_out=js["marketingOptOut"],
        recommendation_at=date.fromisoformat(js["recommendationAt"]) if js["recommendationAt"] else None,
        expected_visit_source=js["expectedVisitSource"],
        expected_visit_reason=js["expectedVisitReason"],
        last_protocol_session_id=js["lastProtocolSession"],
        reactivated_at=_dt(js["reactivatedAt"]),
        first_plan_id=js["firstPlanId"],
    )


def to_existing(js: Js) -> ExistingTask:
    return ExistingTask(js["id"], RuleKey(js["ruleId"]), TaskStatus(js["status"]))


def run(scenario: Scenario) -> RulesOutcome:
    return run_rules(
        [to_patient(p) for p in scenario.patients],
        [to_rule(r) for r in scenario.rules],
        [to_existing(t) for t in scenario.existing_tasks],
        NOW,
    )


def _final_statuses(scenario: Scenario, outcome: RulesOutcome) -> dict[str, str]:
    statuses = {t["id"]: t["status"] for t in scenario.existing_tasks}
    for task in outcome.new_tasks:
        statuses[task.task_key] = TaskStatus.OPEN.value
    for key in outcome.superseded_keys:
        statuses[key] = TaskStatus.SUPERSEDED.value
    return statuses


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_the_task_set_equals_the_javascript_task_set(scenario: Scenario) -> None:
    """Tập việc giống bản JavaScript: cùng mã, cùng trạng thái, chạy lại không trùng."""
    outcome = run(scenario)
    statuses = _final_statuses(scenario, outcome)
    expected = {i: t["status"] for i, t in scenario.expected_tasks.items()}
    assert statuses == expected


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_every_new_task_matches_the_javascript_task_field_for_field(scenario: Scenario) -> None:
    """Mỗi việc mới khớp từng trường với việc JavaScript cùng mã (việc đã lưu giữ nguyên trường cũ)."""
    outcome = run(scenario)
    mismatches: list[str] = []
    for c in outcome.new_tasks:
        js = scenario.expected_tasks[c.task_key]
        expected_plan = None if str(js["relatedPlanId"] or "").startswith("LP-") else js["relatedPlanId"]
        actual = {
            "patientId": c.patient_code,
            "ruleId": c.rule_key.value,
            "reason": c.reason,
            "priority": c.priority.value,
            "dueAt": c.due_at,
            "owner": c.owner_user_id,
            "suggestedAction": c.suggested_action,
            "sourceEventId": c.source_event_id,
            "relatedAppointmentId": c.related_appointment_id,
            "relatedPlanId": c.related_plan_id,
        }
        wanted = {
            "patientId": js["patientId"],
            "ruleId": js["ruleId"],
            "reason": js["reason"],
            "priority": js["priority"],
            "dueAt": datetime.fromisoformat(js["dueAt"]),
            "owner": uid(js["owner"]) if js["owner"] else None,
            "suggestedAction": js["suggestedAction"],
            "sourceEventId": js["sourceEventId"],
            "relatedAppointmentId": js["relatedAppointmentId"],
            "relatedPlanId": expected_plan,
        }
        if actual != wanted:
            mismatches.append(f"{c.task_key}: {actual} != {wanted}")
    assert mismatches == []


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_superseded_tasks_carry_the_javascript_resolution_text(scenario: Scenario) -> None:
    """Việc bị thay thế giữ đúng lý do như bản JavaScript."""
    outcome = run(scenario)
    for key in outcome.superseded_keys:
        js = scenario.expected_tasks[key]
        assert js["status"] == "superseded"
        assert js["resolution"] == SUPERSEDED_RESOLUTION


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_the_patient_read_model_equals_the_javascript_one(scenario: Scenario) -> None:
    """Mô hình đọc (ngày tái khám, quá hạn, vòng đời, rủi ro) khớp cho cả 46 hồ sơ."""
    outcome = run(scenario)
    mismatches: list[str] = []
    for patient in outcome.refreshed:
        js = scenario.expected_patients[patient.code]
        view = outcome.profiles[patient.id]
        actual = {
            "recommendationAt": patient.recommendation_at.isoformat() if patient.recommendation_at else None,
            "expectedVisitSource": patient.expected_visit_source,
            "expectedVisitReason": patient.expected_visit_reason,
            "lastProtocolSession": patient.last_protocol_session_id,
            "expectedNextVisitAt": (
                view.expected_next_visit_at.isoformat() if view.expected_next_visit_at else None
            ),
            "overdueDays": view.overdue_days,
            "lifecycleStage": view.lifecycle_stage.value,
            "riskLevel": view.risk_level.value,
            "lastVisitAt": view.last_visit_at.isoformat() if view.last_visit_at else None,
        }
        wanted = {
            "recommendationAt": js["recommendationAt"],
            "expectedVisitSource": js["expectedVisitSource"],
            "expectedVisitReason": js["expectedVisitReason"],
            "lastProtocolSession": js["lastProtocolSession"],
            "expectedNextVisitAt": js["expectedNextVisitAt"],
            "overdueDays": js["overdueDays"],
            "lifecycleStage": js["lifecycleStage"],
            "riskLevel": js["riskLevel"],
            "lastVisitAt": js["lastVisitAt"],
        }
        if actual != wanted:
            mismatches.append(f"{patient.code}: {actual} != {wanted}")
    assert mismatches == []


def test_the_fixture_covers_all_ten_rules_and_the_p025_to_p032_stories() -> None:
    """Kịch bản đầu có đủ mười quy tắc và các câu chuyện P025..P032."""
    fresh = SCENARIOS[0]
    assert fresh.name == "fresh_seed"
    assert {t["ruleId"] for t in fresh.expected_tasks.values()} == {
        "d1", "d3", "d7", "due", "overdue", "no_show", "abandoned", "dormant90", "dormant180", "birthday",
    }  # fmt: skip
    codes = {t["patientId"] for t in fresh.expected_tasks.values()}
    assert {f"P0{n}" for n in range(25, 33)} <= codes
    assert len(fresh.patients) == 46


def test_the_first_run_on_the_seed_creates_every_task_and_a_second_run_creates_none() -> None:
    """Chạy lần đầu tạo đủ việc; chạy lại không tạo và không thay thế gì."""
    first = run(SCENARIOS[0])
    assert len(first.new_tasks) == len(SCENARIOS[0].expected_tasks) == 78
    again = run(next(s for s in SCENARIOS if s.name == "rerun_is_idempotent"))
    assert again.new_tasks == ()
    assert again.superseded_keys == ()
    assert again.patient_updates == ()
