# ruff: noqa: PT018
# new tests (package U, step U9: Patient 360 dialogs, filter chips and the service added to a course)
"""The U9 actions through the real HTTP API on a real Postgres.

What these pin (recipes/U/10-U9-patient-parity-fixes.md): each dialog saves what the old web saved and says the old
sentence when it refuses; the permission of every action is the one the recipe names; the brief is a template over
records (no model, nothing inferred); the price of a course is fixed when the service is added; the amounts are
shown only to a caller with a finance permission; no audit row carries the text. Synthetic data only.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db

OWNER, MANAGER, DOCTOR, OTHER_DOCTOR, CS, RECEPTION = (
    "owner",
    "manager",
    "doctor.mai",
    "doctor.an",
    "cs.maianh",
    "reception.lan",
)
EXPECTED_INVALID = "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị."


def _audit_rows(admin: Engine, prefix: str) -> list[dict[str, Any]]:
    with admin.connect() as conn:
        rows = conn.execute(
            text("SELECT action, details FROM clinic.audit_log WHERE action LIKE :p ORDER BY id"),
            {"p": f"{prefix}%"},
        )
        return [{"action": r.action, "details": r.details or {}} for r in rows]


async def _laser(client: httpx.AsyncClient) -> dict[str, Any]:
    listed = (await client.get("/api/v1/services")).json()
    return next(s for s in listed if s["code"] == "laser-co2")


# ------------------------------------------------------------------------------------ Thông tin cần nhớ
async def test_the_warning_lines_are_trimmed_saved_shown_in_the_360_and_audited_without_the_text(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    owner = await client_factory(OWNER)
    patient = world.patients["P027"]
    saved = await owner.put(
        f"/api/v1/patients/{patient}/alerts",
        json={"alerts": ["  Da nhạy cảm (mẫu) ", "", "Dị ứng mẫu\nTheo dõi đỏ da"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["alerts"] == ["Da nhạy cảm (mẫu)", "Dị ứng mẫu", "Theo dõi đỏ da"]
    card = (await owner.get(f"/api/v1/patients/{patient}/360")).json()
    assert card["alerts"] == ["Da nhạy cảm (mẫu)", "Dị ứng mẫu", "Theo dõi đỏ da"]
    rows = _audit_rows(admin, "patient.alerts_save")
    assert rows[-1]["details"]["count_after"] == 3
    assert "Da nhạy" not in json.dumps(rows, ensure_ascii=False)


async def test_a_warning_line_over_the_limit_and_too_many_lines_are_refused(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    patient = world.patients["P027"]
    long_line = await owner.put(f"/api/v1/patients/{patient}/alerts", json={"alerts": ["x" * 201]})
    assert long_line.status_code == 422
    many = await owner.put(
        f"/api/v1/patients/{patient}/alerts", json={"alerts": [f"dòng {n}" for n in range(21)]}
    )
    assert many.status_code == 422


async def test_the_alerts_chip_lists_only_patients_with_a_warning(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    before = (await owner.get("/api/v1/patients", params={"view": "alerts"})).json()
    assert before["total"] == 0
    await owner.put(
        f"/api/v1/patients/{world.patients['P027']}/alerts", json={"alerts": ["Da nhạy cảm (mẫu)"]}
    )
    after = (await owner.get("/api/v1/patients", params={"view": "alerts"})).json()
    assert [p["code"] for p in after["items"]] == ["P027"]


async def test_the_active_and_next_chips_follow_plans_and_appointments(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    everyone = (await owner.get("/api/v1/patients", params={"view": "all", "limit": 100})).json()["total"]
    active = (await owner.get("/api/v1/patients", params={"view": "active", "limit": 100})).json()
    nxt = (await owner.get("/api/v1/patients", params={"view": "next", "limit": 100})).json()
    assert active["total"] <= everyone and nxt["total"] <= everyone
    assert all(p["code"] for p in active["items"])
    bad = await owner.get("/api/v1/patients", params={"view": "nonsense"})
    assert bad.status_code == 422


# ------------------------------------------------------------------------------ Tiền sử & chẩn đoán
async def test_the_doctor_saves_history_and_diagnosis_and_both_are_required(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    mai = await client_factory(DOCTOR)
    patient = world.patients["P027"]
    empty = await mai.get(f"/api/v1/patients/{patient}/clinical-note")
    assert empty.status_code == 200 and empty.json()["diagnosis"] == ""
    blank = await mai.put(
        f"/api/v1/patients/{patient}/clinical-note", json={"history": "Tiền sử mẫu", "diagnosis": "   "}
    )
    assert blank.status_code == 422
    assert blank.json()["error"]["message"] == "Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận."
    saved = await mai.put(
        f"/api/v1/patients/{patient}/clinical-note",
        json={"history": "Tiền sử mẫu", "diagnosis": "Nhận định mẫu do bác sĩ ghi"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["reviewed_by_name"] == "BS. Mai (mẫu)"
    again = await mai.put(
        f"/api/v1/patients/{patient}/clinical-note",
        json={"history": "Sửa mẫu", "diagnosis": "Nhận định mới mẫu"},
    )
    assert again.status_code == 200
    read = (await mai.get(f"/api/v1/patients/{patient}/clinical-note")).json()
    assert read["history"] == "Sửa mẫu"
    timeline = (await mai.get(f"/api/v1/patients/{patient}/360")).json()["timeline"]
    assert "Bác sĩ ghi nhận khám và chẩn đoán" in [e["title"] for e in timeline]
    assert "Nhận định" not in json.dumps(_audit_rows(admin, "patient.clinical"), ensure_ascii=False)


async def test_only_a_clinician_of_the_patient_writes_the_diagnosis(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    patient = world.patients["P027"]
    body = {"history": "a", "diagnosis": "b"}
    for who in (MANAGER, CS, RECEPTION):
        client = await client_factory(who)
        denied = await client.put(f"/api/v1/patients/{patient}/clinical-note", json=body)
        assert denied.status_code == 403, who
    stranger = await client_factory(OTHER_DOCTOR)
    assert (await stranger.put(f"/api/v1/patients/{patient}/clinical-note", json=body)).status_code == 403
    care = await client_factory(CS)
    assert (await care.get(f"/api/v1/patients/{patient}/clinical-note")).status_code in (200, 403)


# --------------------------------------------------------------------------- Ngày dự kiến quay lại
@pytest.mark.parametrize(
    "body",
    [
        {"date": "2026-02-30", "reason": "x", "source": "doctor_recommendation"},
        {"date": "20/09/2026", "reason": "x", "source": "doctor_recommendation"},
        {"date": "2026-10-01", "reason": "   ", "source": "doctor_recommendation"},
        {"date": "2026-10-01", "reason": "x", "source": "appointment"},
        {"date": "2026-10-01", "reason": "x", "source": "made_up"},
    ],
)
async def test_the_expected_return_answers_every_bad_input_with_the_old_sentence(
    client_factory: ClientFactory, world: SeedResult, body: dict[str, str]
) -> None:
    mai = await client_factory(DOCTOR)
    response = await mai.put(f"/api/v1/patients/{world.patients['P027']}/expected-return", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == EXPECTED_INVALID


async def test_the_expected_return_is_saved_and_the_360_profile_shows_it(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    mai = await client_factory(DOCTOR)
    patient = world.patients["P027"]
    saved = await mai.put(
        f"/api/v1/patients/{patient}/expected-return",
        json={"date": "2030-01-15", "reason": "Bác sĩ hẹn đánh giá (mẫu)", "source": "doctor_recommendation"},
    )
    assert saved.status_code == 200, saved.text
    profile = (await mai.get(f"/api/v1/patients/{patient}/360")).json()["profile"]
    assert profile["expected_next_visit_at"] == "2030-01-15"
    assert profile["expected_visit_source"] == "doctor_recommendation"
    detail = _audit_rows(admin, "patient.expected_return")[-1]["details"]
    assert detail["recommendation_at"] == "2030-01-15" and "Bác sĩ" not in json.dumps(
        detail, ensure_ascii=False
    )
    reception = await client_factory(RECEPTION)
    denied = await reception.put(
        f"/api/v1/patients/{patient}/expected-return",
        json={"date": "2030-01-15", "reason": "x", "source": "doctor_recommendation"},
    )
    assert denied.status_code == 403


# ---------------------------------------------------------- Chăm sóc tại nhà / Nhắn tin / patient app
async def test_aftercare_goes_on_the_patient_app_timeline_and_an_empty_text_is_refused(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    mai = await client_factory(DOCTOR)
    patient = world.patients["P027"]
    empty = await mai.post(
        f"/api/v1/patients/{patient}/app-updates", json={"kind": "aftercare", "body": "  "}
    )
    assert empty.status_code == 422 and empty.json()["error"]["message"] == "Hãy nhập hướng dẫn."
    sent = await mai.post(
        f"/api/v1/patients/{patient}/app-updates",
        json={"kind": "aftercare", "body": "SPF 50+ mỗi sáng (mẫu)"},
    )
    assert sent.status_code == 201, sent.text
    latest = (await mai.get(f"/api/v1/patients/{patient}/app-updates", params={"kind": "aftercare"})).json()
    assert latest[0]["body"] == "SPF 50+ mỗi sáng (mẫu)"
    titles = [e["title"] for e in (await mai.get(f"/api/v1/patients/{patient}/360")).json()["timeline"]]
    assert "Đã gửi hướng dẫn chăm sóc" in titles
    rows = _audit_rows(admin, "patient_app.send")
    assert rows[-1]["details"]["chars"] == len("SPF 50+ mỗi sáng (mẫu)")
    assert "SPF" not in json.dumps(rows, ensure_ascii=False)


async def test_a_message_needs_conversation_reply_and_aftercare_needs_session_write(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    patient = world.patients["P027"]
    care = await client_factory(CS)
    ok = await care.post(
        f"/api/v1/patients/{patient}/app-updates", json={"kind": "message", "body": "Chào bạn (mẫu)"}
    )
    assert ok.status_code == 201, ok.text
    assert (
        await care.post(f"/api/v1/patients/{patient}/app-updates", json={"kind": "aftercare", "body": "x"})
    ).status_code == 403
    reception = await client_factory(RECEPTION)
    assert (
        await reception.post(
            f"/api/v1/patients/{patient}/app-updates", json={"kind": "aftercare", "body": "x"}
        )
    ).status_code == 403
    blank = await care.post(f"/api/v1/patients/{patient}/app-updates", json={"kind": "message", "body": ""})
    assert blank.status_code == 422


# ----------------------------------------------------------------------------------------------- brief
async def test_the_brief_is_a_template_over_records_and_the_doctor_approves_what_she_edited(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    mai = await client_factory(DOCTOR)
    patient = world.patients["P029"]
    draft = (await mai.get(f"/api/v1/patients/{patient}/brief")).json()
    assert draft["approved"] is None
    assert (
        "Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch." in draft["text"]
    )
    assert "đã hoàn tất 3/6 buổi" in draft["text"]
    assert any(source.startswith("plan:") for source in draft["source_ids"])
    again = (await mai.get(f"/api/v1/patients/{patient}/brief")).json()
    assert again["text"] == draft["text"]  # deterministic: a template, not a model
    blank = await mai.post(f"/api/v1/patients/{patient}/brief/approve", json={"text": "  "})
    assert blank.status_code == 422 and blank.json()["error"]["message"] == "Brief không được để trống."
    edited = draft["text"] + " Bác sĩ thêm một ý (mẫu)."
    approved = await mai.post(f"/api/v1/patients/{patient}/brief/approve", json={"text": edited})
    assert approved.status_code == 201, approved.text
    assert approved.json()["source_ids"] == draft["source_ids"]
    assert (await mai.get(f"/api/v1/patients/{patient}/brief")).json()["approved"]["text"] == edited
    assert "Bác sĩ thêm" not in json.dumps(_audit_rows(admin, "patient.brief"), ensure_ascii=False)


async def test_the_brief_of_a_patient_without_records_uses_the_two_fallback_sentences(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    created = await owner.post("/api/v1/patients", json={"full_name": "Bệnh nhân mẫu mới"})
    assert created.status_code == 201
    text_ = (await owner.get(f"/api/v1/patients/{created.json()['id']}/brief")).json()["text"]
    assert "Chưa có cập nhật sau điều trị." in text_
    assert "Không có mục theo dõi đang mở." in text_


async def test_the_brief_is_for_the_clinical_roles_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    patient = world.patients["P027"]
    for who in (MANAGER, CS, RECEPTION):
        client = await client_factory(who)
        assert (await client.get(f"/api/v1/patients/{patient}/brief")).status_code == 403, who
    stranger = await client_factory(OTHER_DOCTOR)
    assert (await stranger.get(f"/api/v1/patients/{patient}/brief")).status_code == 403


# ------------------------------------------------------------------------------- service added to a course
async def test_a_service_added_to_a_course_fixes_its_price_and_a_catalog_change_does_not_move_it(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    manager = await client_factory(MANAGER)
    patient = world.patients["P027"]
    laser = await _laser(manager)
    added = await manager.post(
        f"/api/v1/patients/{patient}/service-plans",
        json={"service_id": laser["id"], "sessions": 4, "discount_vnd": 500_000},
    )
    assert added.status_code == 201, added.text
    plan = added.json()
    assert (plan["unit_price_vnd"], plan["discount_vnd"], plan["agreed_price_vnd"]) == (
        laser["price_vnd"],
        500_000,
        laser["price_vnd"] * 4 - 500_000,
    )
    assert (plan["total_sessions"], plan["completed_sessions"], plan["title"]) == (4, 0, laser["name"])
    changed = await manager.patch(
        f"/api/v1/services/{laser['id']}",
        json={"version": laser["version"], "price_vnd": laser["price_vnd"] + 1},
    )
    assert changed.status_code == 200
    card = (await manager.get(f"/api/v1/patients/{patient}/360")).json()
    stored = next(p for p in card["plans"] if p["id"] == plan["id"])
    assert stored["agreed_price_vnd"] == plan["agreed_price_vnd"]
    detail = _audit_rows(admin, "plan.add_service")[-1]["details"]
    assert detail["agreed_price_vnd"] == plan["agreed_price_vnd"] and detail["terms_version"] == 1


async def test_the_course_price_is_shown_only_to_a_caller_with_a_finance_permission(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    patient = world.patients["P027"]
    laser = await _laser(owner)
    added = await owner.post(
        f"/api/v1/patients/{patient}/service-plans", json={"service_id": laser["id"], "sessions": 2}
    )
    assert added.status_code == 201
    for who in (DOCTOR, CS):
        client = await client_factory(who)
        plans = (await client.get(f"/api/v1/patients/{patient}/360")).json()["plans"]
        assert plans and all(p["agreed_price_vnd"] is None for p in plans), who
    seen = (await owner.get(f"/api/v1/patients/{patient}/plans")).json()
    assert any(p["agreed_price_vnd"] is not None for p in seen)


async def test_adding_a_service_is_refused_for_the_wrong_role_and_for_bad_input(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    patient = world.patients["P027"]
    laser = await _laser(owner)
    ok_body = {"service_id": laser["id"], "sessions": 2, "discount_vnd": 0}
    for who in (DOCTOR, CS, RECEPTION):
        client = await client_factory(who)
        assert (
            await client.post(f"/api/v1/patients/{patient}/service-plans", json=ok_body)
        ).status_code == 403, who
    assert (
        await owner.post(f"/api/v1/patients/{patient}/service-plans", json={**ok_body, "sessions": 21})
    ).status_code == 422
    assert (
        await owner.post(f"/api/v1/patients/{patient}/service-plans", json={**ok_body, "sessions": 0})
    ).status_code == 422
    too_much = await owner.post(
        f"/api/v1/patients/{patient}/service-plans",
        json={**ok_body, "discount_vnd": laser["price_vnd"] * 2 + 1},
    )
    assert too_much.status_code == 422
    missing = await owner.post(
        f"/api/v1/patients/{patient}/service-plans",
        json={**ok_body, "service_id": str(UUID(int=7))},
    )
    assert missing.status_code == 404
    off = await owner.patch(
        f"/api/v1/services/{laser['id']}", json={"version": laser["version"], "active": False}
    )
    assert off.status_code == 200
    inactive = await owner.post(f"/api/v1/patients/{patient}/service-plans", json=ok_body)
    assert inactive.status_code == 422
