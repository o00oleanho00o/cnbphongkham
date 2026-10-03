# ruff: noqa: PT018
# new tests (package U, step U3: sessions, plans, consult notes and clinical photos of Patient 360)
"""Plans, sessions, consult notes and photos through the real HTTP API on a real Postgres.

What these pin (recipes/U/04-U3-patient360.md acceptance): completing a session produces what the old
``save-session`` produced and gives the CRM rules their D+1/3/7 milestones; a photo cannot be uploaded without
the patient's consent; every role outside the matrix is refused; every mutation is audited. Synthetic data only.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import DEMO_NOW, ClientFactory
from pema.clinic.actions import _common
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.clinic.crm_rules.testing import FakeScheduler
from pema.clinic.media_storage import InMemoryMediaStorage
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

TODAY = DEMO_DAY
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic-jpeg-bytes" * 4
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-png-bytes" * 4


@pytest.fixture
def storage(app: FastAPI) -> InMemoryMediaStorage:
    memory = InMemoryMediaStorage()
    app.state.media_storage = memory
    return memory


def _body(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "performed_on": TODAY.isoformat(),
        "session_type": "Laser CO2",
        "protocol_id": "laser-co2",
        "region": "Mặt",
        "view": "Chính diện",
        "note": "Da ổn, đỏ nhẹ giảm (mẫu).",
        "aftercare": "Dưỡng ẩm dịu nhẹ, chống nắng (mẫu).",
        "with_photo": True,
    }
    return {**base, **fields}


async def _new_plan(client: httpx.AsyncClient, patient: UUID, total: int = 3) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/patients/{patient}/plans",
        json={"title": "Laser CO2 phục hồi (mẫu)", "service_code": "laser-co2", "total_sessions": total},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _grant_media_consent(client: httpx.AsyncClient, patient: UUID, granted: bool = True) -> None:
    response = await client.post(
        f"/api/v1/patients/{patient}/consents", json={"kind": "media", "granted": granted, "source": "mẫu"}
    )
    assert response.status_code == 201, response.text


async def _upload(
    client: httpx.AsyncClient,
    patient: UUID,
    data: bytes = JPEG,
    *,
    mime: str = "image/jpeg",
    session_id: str | None = None,
    stage: str = "before",
) -> dict[str, Any]:
    intent = await client.post(
        f"/api/v1/patients/{patient}/media/upload-intent",
        json={"stage": stage, "mime": mime, "size_bytes": len(data), "session_id": session_id},
    )
    assert intent.status_code == 201, intent.text
    target = intent.json()
    put = await client.put(target["upload_path"], content=data, headers={"content-type": mime})
    assert put.status_code == 200, put.text
    confirm = await client.post(f"/api/v1/media/{target['media_id']}/confirm")
    assert confirm.status_code == 200, confirm.text
    return confirm.json()


def _audit_actions(admin: Engine) -> list[str]:
    with admin.connect() as conn:
        return list(conn.execute(text("SELECT action FROM clinic.audit_log ORDER BY id")).scalars())


# ------------------------------------------------------------------------------------------- sessions
async def test_completing_a_session_does_what_save_session_did_and_feeds_the_crm_milestones(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    """Hoàn tất buổi: tăng số buổi, đóng lịch đến khám, đặt gợi ý tái khám, và D+1/3/7 xuất hiện ở lần chạy CRM."""
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    plan = await _new_plan(mai, p027, total=3)
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.appointment (clinic_id, patient_id, doctor_id, starts_at, duration_min, status) "
                "VALUES (:c, :p, :d, :s, 30, 'in_progress')"
            ),
            {"c": world.clinic_id, "p": p027, "d": world.users["doctor.mai"], "s": DEMO_NOW},
        )

    created = await mai.post(
        f"/api/v1/patients/{p027}/sessions",
        json=_body(plan_id=plan["id"], next_visit_on=(TODAY + timedelta(days=21)).isoformat()),
    )
    assert created.status_code == 201, created.text
    done = created.json()
    assert done["status"] == "completed"
    assert done["title"] == "Buổi 1/3 · Laser CO2"
    assert done["reviewed"] is True
    assert done["doctor_name"]

    plans = (await mai.get(f"/api/v1/patients/{p027}/plans")).json()
    assert {p["id"]: p["completed_sessions"] for p in plans}[plan["id"]] == 1
    with admin.connect() as conn:
        visit = conn.execute(
            text("SELECT status FROM clinic.appointment WHERE patient_id = :p AND starts_at = :s"),
            {"p": p027, "s": DEMO_NOW},
        ).scalar_one()
        patient = conn.execute(
            text("SELECT recommendation_at, expected_visit_source FROM clinic.patient WHERE id = :p"),
            {"p": p027},
        ).one()
        photo_tasks = conn.execute(
            text("SELECT count(*) FROM clinic.crm_task WHERE patient_id = :p AND rule_key = 'manual'"),
            {"p": p027},
        ).scalar_one()
    assert visit == "completed"
    assert (patient.recommendation_at, patient.expected_visit_source) == (
        TODAY + timedelta(days=21),
        "doctor_recommendation",
    )
    assert photo_tasks == 0  # with_photo: no "Thiếu ảnh mốc" task

    report = await CrmRulesRunner(SqlCrmRuleStore(db), FakeScheduler()).run_clinic(world.clinic_id, DEMO_NOW)
    assert report.tasks_created >= 3
    with admin.connect() as conn:
        rules = set(
            conn.execute(
                text("SELECT rule_key FROM clinic.crm_task WHERE patient_id = :p AND status = 'open'"),
                {"p": p027},
            ).scalars()
        )
    assert {"d1", "d3", "d7"} <= rules


async def test_the_rules_of_the_old_form_still_hold(client_factory: ClientFactory, world: SeedResult) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    url = f"/api/v1/patients/{p027}/sessions"
    plan = await _new_plan(mai, p027, total=1)

    missing_note = await mai.post(url, json=_body(plan_id=plan["id"], note=" "))
    assert missing_note.status_code == 422
    assert missing_note.json()["error"]["message"] == "Hãy ghi đánh giá trước buổi."
    missing_aftercare = await mai.post(url, json=_body(plan_id=plan["id"], aftercare=""))
    assert missing_aftercare.status_code == 422
    assert missing_aftercare.json()["error"]["message"] == "Hãy nhập hướng dẫn chăm sóc sau buổi."
    future = await mai.post(
        url, json=_body(plan_id=plan["id"], performed_on=(TODAY + timedelta(days=1)).isoformat())
    )
    assert future.status_code == 422
    # the seeded last session of P027 is 30 days ago: a date before it is refused
    before_last = await mai.post(
        url, json=_body(plan_id=plan["id"], performed_on=(TODAY - timedelta(days=60)).isoformat())
    )
    assert before_last.status_code == 422

    ok = await mai.post(url, json=_body(plan_id=plan["id"]))
    assert ok.status_code == 201
    full = await mai.post(url, json=_body(plan_id=plan["id"]))
    assert full.status_code == 409
    assert (
        full.json()["error"]["message"]
        == "Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch trước khi thêm buổi mới."
    )
    plans = {p["id"]: p for p in (await mai.get(f"/api/v1/patients/{p027}/plans")).json()}
    assert plans[plan["id"]]["status"] == "completed"


async def test_a_session_without_a_photo_raises_the_missing_photo_task_and_the_photo_resolves_it(
    client_factory: ClientFactory, world: SeedResult, admin: Engine, storage: InMemoryMediaStorage
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    await _grant_media_consent(mai, p027)
    plan = await _new_plan(mai, p027)
    created = await mai.post(
        f"/api/v1/patients/{p027}/sessions", json=_body(plan_id=plan["id"], with_photo=False)
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    def open_tasks() -> list[tuple[str, str | None]]:
        with admin.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT reason, resolution FROM clinic.crm_task "
                    "WHERE patient_id = :p AND rule_key = 'manual' AND status IN ('open', 'rescheduled')"
                ),
                {"p": p027},
            ).all()
        return [(r.reason, r.resolution) for r in rows]

    assert open_tasks() == [("Thiếu ảnh mốc đánh giá", None)]
    media = await _upload(mai, p027, session_id=session_id, stage="after")
    assert media["status"] == "confirmed" and media["session_id"] == session_id
    assert open_tasks() == []
    assert len(storage.objects) == 1


async def test_a_scheduled_session_is_completed_later_and_review_is_idempotent(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    plan = await _new_plan(mai, p027)
    draft = await mai.post(
        f"/api/v1/patients/{p027}/sessions",
        json=_body(plan_id=plan["id"], complete=False, note="", aftercare=""),
    )
    assert draft.status_code == 201
    row = draft.json()
    assert row["status"] == "scheduled" and row["reviewed"] is False

    too_early = await mai.post(f"/api/v1/sessions/{row['id']}/complete", json={"version": row["version"]})
    assert too_early.status_code == 422  # note and aftercare are still empty
    finished = await mai.post(
        f"/api/v1/sessions/{row['id']}/complete",
        json={
            "version": row["version"],
            "note": "Đánh giá (mẫu)",
            "aftercare": "Hướng dẫn (mẫu)",
            "with_photo": True,
        },
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "completed"
    again = await mai.post(
        f"/api/v1/sessions/{row['id']}/complete", json={"version": finished.json()["version"]}
    )
    assert again.status_code == 409
    review = await mai.post(
        f"/api/v1/sessions/{row['id']}/review", json={"version": finished.json()["version"]}
    )
    assert review.status_code == 200 and review.json()["reviewed"] is True


async def test_a_stale_plan_version_is_a_conflict_and_the_total_cannot_drop_below_the_done_sessions(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    plan = await _new_plan(mai, p027, total=4)
    await mai.post(f"/api/v1/patients/{p027}/sessions", json=_body(plan_id=plan["id"]))
    fresh = next(p for p in (await mai.get(f"/api/v1/patients/{p027}/plans")).json() if p["id"] == plan["id"])
    stale = await mai.patch(
        f"/api/v1/plans/{plan['id']}", json={"version": plan["version"], "title": "Đổi tên"}
    )
    assert stale.status_code == 409
    below = await mai.patch(
        f"/api/v1/plans/{plan['id']}", json={"version": fresh["version"], "total_sessions": 0}
    )
    assert below.status_code == 422
    ok = await mai.patch(
        f"/api/v1/plans/{plan['id']}",
        json={"version": fresh["version"], "title": "Đổi tên", "total_sessions": 2},
    )
    assert ok.status_code == 200
    assert (ok.json()["title"], ok.json()["total_sessions"], ok.json()["status"]) == ("Đổi tên", 2, "active")
    close = await mai.patch(
        f"/api/v1/plans/{plan['id']}", json={"version": ok.json()["version"], "total_sessions": 1}
    )
    assert close.status_code == 200 and close.json()["status"] == "completed"


# ------------------------------------------------------------------------------------- consult notes
async def test_consult_note_draft_edit_and_approval(client_factory: ClientFactory, world: SeedResult) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    empty = await mai.post(f"/api/v1/patients/{p027}/consult-notes", json={"input_text": "  "})
    assert empty.status_code == 422

    first = (
        await mai.post(f"/api/v1/patients/{p027}/consult-notes", json={"input_text": "Da ổn hơn"})
    ).json()
    assert first["status"] == "draft"
    assert first["body"].startswith("Bản nháp ghi chú · 20/09/2026: Da ổn hơn")
    second = (await mai.post(f"/api/v1/patients/{p027}/consult-notes", json={"input_text": "Đỏ giảm"})).json()
    assert second["id"] == first["id"]  # one open draft: the text is replaced
    assert "Đỏ giảm" in second["body"]

    blank = await mai.post(
        f"/api/v1/consult-notes/{second['id']}/approve", json={"version": second["version"], "body": "   "}
    )
    assert blank.status_code == 422
    approved = await mai.post(
        f"/api/v1/consult-notes/{second['id']}/approve",
        json={"version": second["version"], "body": "Ghi chú đã chỉnh (mẫu)"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved" and approved.json()["approved_by_name"]
    again = await mai.post(
        f"/api/v1/consult-notes/{second['id']}/approve", json={"version": approved.json()["version"]}
    )
    assert again.status_code == 409

    notes = (await mai.get(f"/api/v1/patients/{p027}/consult-notes")).json()
    assert [n["status"] for n in notes] == ["approved"]
    timeline = (await mai.get(f"/api/v1/patients/{p027}/360")).json()["timeline"]
    event = [e for e in timeline if e["kind"] == "consult"]
    assert event and event[0]["title"] == "Ghi chú tư vấn đã được duyệt"
    assert "Ghi chú đã chỉnh" not in str(timeline)  # the text itself never enters the 360


# ------------------------------------------------------------------------------------------- photos
async def test_media_upload_is_refused_without_the_patients_consent(
    client_factory: ClientFactory, world: SeedResult, storage: InMemoryMediaStorage
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    intent = {"stage": "before", "mime": "image/jpeg", "size_bytes": len(JPEG)}
    refused = await mai.post(f"/api/v1/patients/{p027}/media/upload-intent", json=intent)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "consent_required"

    await _grant_media_consent(mai, p027)
    allowed = await mai.post(f"/api/v1/patients/{p027}/media/upload-intent", json=intent)
    assert allowed.status_code == 201
    target = allowed.json()
    assert target["upload_path"].startswith(f"/api/v1/media/{target['media_id']}/content?exp=")

    # withdrawing the consent between the intent and the bytes stops the upload as well
    await _grant_media_consent(mai, p027, granted=False)
    late = await mai.put(target["upload_path"], content=JPEG, headers={"content-type": "image/jpeg"})
    assert late.status_code == 422 and late.json()["error"]["code"] == "consent_required"
    assert storage.objects == {}


async def test_the_upload_checks_type_size_signature_and_the_signed_path(
    client_factory: ClientFactory, world: SeedResult, storage: InMemoryMediaStorage
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    await _grant_media_consent(mai, p027)
    url = f"/api/v1/patients/{p027}/media/upload-intent"

    gif = await mai.post(url, json={"stage": "before", "mime": "image/gif", "size_bytes": 10})
    assert gif.status_code == 422
    huge = await mai.post(url, json={"stage": "before", "mime": "image/png", "size_bytes": 9 * 1024 * 1024})
    assert huge.status_code == 413

    async def intent(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
        response = await mai.post(url, json={"stage": "after", "mime": mime, "size_bytes": len(data)})
        assert response.status_code == 201
        return response.json()

    target = await intent(JPEG)
    wrong_size = await mai.put(
        target["upload_path"], content=JPEG + b"x", headers={"content-type": "image/jpeg"}
    )
    assert wrong_size.status_code == 422
    target = await intent(PNG, "image/png")  # declared PNG, but the signature of the bytes is a JPEG
    wrong_type = await mai.put(target["upload_path"], content=JPEG[: len(PNG)].ljust(len(PNG), b"x"))
    assert wrong_type.status_code == 422
    target = await intent(JPEG)
    forged = target["upload_path"].rsplit("sig=", 1)[0] + "sig=" + "0" * 64
    assert (await mai.put(forged, content=JPEG)).status_code == 403
    other_size = await intent(JPEG + b"yy")
    swapped = target["upload_path"].replace(target["media_id"], other_size["media_id"])
    assert (await mai.put(swapped, content=JPEG + b"yy")).status_code == 403  # a path is bound to its photo

    expiring = await intent(JPEG)
    with _common.use_clock(lambda: DEMO_NOW + timedelta(minutes=11)):
        late = await mai.put(expiring["upload_path"], content=JPEG, headers={"content-type": "image/jpeg"})
    assert late.status_code == 403

    fine = await mai.put(target["upload_path"], content=JPEG, headers={"content-type": "image/jpeg"})
    assert fine.status_code == 200 and fine.json()["status"] == "uploaded"
    twice = await mai.put(target["upload_path"], content=JPEG, headers={"content-type": "image/jpeg"})
    assert twice.status_code == 409
    premature = await intent(JPEG)
    assert (await mai.post(f"/api/v1/media/{premature['media_id']}/confirm")).status_code == 409
    assert len(storage.objects) == 1


async def test_a_photo_is_listed_and_served_with_the_consent_and_every_read_is_audited(
    client_factory: ClientFactory, world: SeedResult, storage: InMemoryMediaStorage, admin: Engine
) -> None:
    mai = await client_factory("doctor.mai")
    maianh = await client_factory("cs.maianh")  # the care owner of P025
    p025 = world.patients["P025"]
    await _grant_media_consent(mai, p025)
    media = await _upload(mai, p025, PNG, mime="image/png", stage="after")

    listed = (await maianh.get(f"/api/v1/patients/{p025}/media")).json()
    assert [m["id"] for m in listed] == [media["id"]] and listed[0]["consent_active"] is True
    served = await maianh.get(listed[0]["content_path"])
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private, no-store"

    await _grant_media_consent(mai, p025, granted=False)
    assert (
        await maianh.get(listed[0]["content_path"])
    ).status_code == 422  # care staff: only with the consent
    assert (await mai.get(listed[0]["content_path"])).status_code == 200  # the clinician keeps access
    assert _audit_actions(admin).count("media.read") == 2


# --------------------------------------------------------------------------------------------- RBAC
@pytest.mark.parametrize("role_key", ["reception.lan", "manager"])
async def test_reception_and_manager_have_no_access_to_the_clinical_tabs(
    client_factory: ClientFactory, world: SeedResult, role_key: str
) -> None:
    client = await client_factory(role_key)
    p025 = world.patients["P025"]
    for path in (
        f"/api/v1/patients/{p025}/sessions",
        f"/api/v1/patients/{p025}/consult-notes",
        f"/api/v1/patients/{p025}/media",
    ):
        assert (await client.get(path)).status_code == 403, path
    writes = [
        (f"/api/v1/patients/{p025}/plans", {"title": "x", "service_code": "x", "total_sessions": 1}),
        (f"/api/v1/patients/{p025}/sessions", _body()),
        (f"/api/v1/patients/{p025}/consult-notes", {"input_text": "x"}),
        (
            f"/api/v1/patients/{p025}/media/upload-intent",
            {"stage": "before", "mime": "image/png", "size_bytes": 5},
        ),
    ]
    for path, body in writes:
        assert (await client.post(path, json=body)).status_code == 403, path


async def test_care_staff_read_their_own_patients_only_and_never_write_a_session(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    maianh = await client_factory("cs.maianh")
    p025, p026 = world.patients["P025"], world.patients["P026"]  # P025 is hers, P026 belongs to cs.thu
    assert (await maianh.get(f"/api/v1/patients/{p025}/sessions")).status_code == 200
    other = await maianh.get(f"/api/v1/patients/{p026}/sessions")
    assert other.status_code == 403 and other.json()["error"]["details"] == {"scope": "assignment"}
    assert (await maianh.get(f"/api/v1/patients/{p026}/media")).status_code == 403
    assert (await maianh.post(f"/api/v1/patients/{p025}/sessions", json=_body())).status_code == 403
    assert (
        await maianh.post(f"/api/v1/patients/{p025}/consult-notes", json={"input_text": "x"})
    ).status_code == 403
    assert (
        await maianh.post(
            f"/api/v1/patients/{p025}/plans", json={"title": "x", "service_code": "x", "total_sessions": 1}
        )
    ).status_code == 403


async def test_a_doctor_writes_only_for_their_own_patients(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    an = await client_factory("doctor.an")
    p025 = world.patients["P025"]  # doctor.mai's patient, not scheduled with doctor.an
    assert (await an.get(f"/api/v1/patients/{p025}/sessions")).status_code == 403
    assert (await an.post(f"/api/v1/patients/{p025}/sessions", json=_body())).status_code == 403
    assert (
        await an.post(f"/api/v1/patients/{p025}/consult-notes", json={"input_text": "x"})
    ).status_code == 403
    owner = await client_factory("owner")
    assert (await owner.get(f"/api/v1/patients/{p025}/sessions")).status_code == 200


async def test_every_mutation_of_the_tabs_writes_an_audit_row_without_clinical_text(
    client_factory: ClientFactory, world: SeedResult, storage: InMemoryMediaStorage, admin: Engine
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    await _grant_media_consent(mai, p027)
    plan = await _new_plan(mai, p027)
    session = (
        await mai.post(f"/api/v1/patients/{p027}/sessions", json=_body(plan_id=plan["id"], with_photo=False))
    ).json()
    await _upload(mai, p027, session_id=session["id"])
    note = (await mai.post(f"/api/v1/patients/{p027}/consult-notes", json={"input_text": "ý chính"})).json()
    await mai.post(f"/api/v1/consult-notes/{note['id']}/approve", json={"version": note["version"]})
    await mai.patch(
        f"/api/v1/plans/{plan['id']}", json={"version": plan["version"] + 1, "goal": "Mục tiêu (mẫu)"}
    )
    actions = _audit_actions(admin)
    for expected in (
        "plan.create",
        "plan.update",
        "session.complete",
        "media.upload_intent",
        "media.upload",
        "media.confirm",
        "consult_note.draft",
        "consult_note.approve",
    ):
        assert expected in actions, expected
    with admin.connect() as conn:
        details = " ".join(
            str(d)
            for d in conn.execute(
                text("SELECT details FROM clinic.audit_log WHERE action LIKE 'session.%'")
            ).scalars()
        )
    assert "Da ổn" not in details and "Dưỡng ẩm" not in details


# ------------------------------------------------------------------------------------ the 360 and the agent
async def test_patient_360_carries_the_richer_plans_and_sessions(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    plan = await _new_plan(mai, p027)
    await mai.patch(
        f"/api/v1/plans/{plan['id']}", json={"version": plan["version"], "goal": "Giảm sắc tố (mẫu)"}
    )
    await mai.post(f"/api/v1/patients/{p027}/sessions", json=_body(plan_id=plan["id"]))
    body = (await mai.get(f"/api/v1/patients/{p027}/360")).json()
    created = next(p for p in body["plans"] if p["id"] == plan["id"])
    assert created["goal"] == "Giảm sắc tố (mẫu)" and created["completed_sessions"] == 1
    newest = body["recent_sessions"][0]
    assert newest["session_type"] == "Laser CO2" and newest["reviewed"] is True
    assert "note" not in newest and "aftercare" not in newest  # the 360 never carries clinical text
    for key in newest:
        assert key != "note"


async def test_the_agent_care_context_shows_the_plan_progress_as_codes_and_numbers(
    world: SeedResult, worker_db: ClinicDatabase, db: ClinicDatabase
) -> None:
    from pema.clinic.actions import ClinicAgentFacingActions
    from pema_contracts.actions import ActionContext
    from pema_contracts.roles import ActorType

    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)
    care = await ClinicAgentFacingActions(worker_db).get_care_context(ctx, "P025")
    assert care is not None
    assert care.plan_service_code == "laser-co2"
    assert (care.plan_completed_sessions, care.plan_total_sessions) == (1, 3)
    dump = care.model_dump_json()
    assert "Liệu trình mẫu" not in dump  # titles are free text; the agent gets codes and numbers only


async def test_a_photo_above_the_global_body_ceiling_uploads_and_one_above_the_photo_ceiling_is_refused(
    client_factory: ClientFactory, world: SeedResult, storage: InMemoryMediaStorage
) -> None:
    """The 4 MB ceiling of every other route does not apply to the photo route, which cuts at 8 MB itself."""
    mai = await client_factory("doctor.mai")
    p027 = world.patients["P027"]
    await _grant_media_consent(mai, p027)
    big = JPEG + b"\x00" * (5 * 1024 * 1024)
    assert len(big) > 4 * 1024 * 1024
    uploaded = await _upload(mai, p027, big)
    assert uploaded["size_bytes"] == len(big)

    intent = await mai.post(
        f"/api/v1/patients/{p027}/media/upload-intent",
        json={"stage": "before", "mime": "image/jpeg", "size_bytes": 1024},
    )
    oversized = await mai.put(intent.json()["upload_path"], content=JPEG + b"\x00" * (9 * 1024 * 1024))
    assert oversized.status_code == 413
    assert len(storage.objects) == 1
