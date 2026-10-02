# ruff: noqa: PT018
"""Doctor-approved message templates: draft, doctor sign-off, edit clears the approval, worker view."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db


def _body(key: str | None = None, **kw: object) -> dict[str, object]:
    body: dict[str, object] = {
        "template_key": key or f"mau_{uuid4().hex[:10]}",
        "title": "Mẫu thử",
        "body": "Phòng khám nhắc bạn lịch hẹn sắp tới (nội dung mẫu).",
    }
    body.update(kw)
    return body


async def test_a_new_template_is_an_inactive_draft_and_only_a_doctor_approves_it(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    mai = await client_factory("doctor.mai")
    draft = await manager.post("/api/v1/admin/templates", json=_body())
    assert draft.status_code == 201, draft.text
    template = draft.json()
    assert template["active"] is False
    assert template["approved_at"] is None
    url = f"/api/v1/admin/templates/{template['id']}/approve"
    assert (await manager.post(url, json={"version": 1})).status_code == 403, "a manager is not a clinician"
    approved = await mai.post(url, json={"version": 1})
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["active"] is True
    assert body["approved_by"] == str(world.users["doctor.mai"])
    assert body["approved_at"] is not None
    # a doctor also reads the list to find what to approve
    keys = [t["template_key"] for t in (await mai.get("/api/v1/admin/templates")).json()]
    assert template["template_key"] in keys


async def test_editing_the_body_clears_the_approval_but_editing_the_title_does_not(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    mai = await client_factory("doctor.mai")
    template = (await manager.post("/api/v1/admin/templates", json=_body())).json()
    approved = (
        await mai.post(f"/api/v1/admin/templates/{template['id']}/approve", json={"version": 1})
    ).json()
    base = f"/api/v1/admin/templates/{template['id']}"
    retitled = (
        await manager.patch(base, json={"version": approved["version"], "title": "Tiêu đề mới"})
    ).json()
    assert retitled["active"] is True and retitled["approved_at"] is not None
    edited = (
        await manager.patch(base, json={"version": retitled["version"], "body": "Nội dung đã đổi (mẫu)."})
    ).json()
    assert edited["active"] is False
    assert edited["approved_at"] is None and edited["approved_by"] is None
    reactivate = await manager.patch(base, json={"version": edited["version"], "active": True})
    assert reactivate.status_code == 409
    assert reactivate.json()["error"]["code"] == "review_required"
    marketing = (await mai.post(f"{base}/approve", json={"version": edited["version"]})).json()
    flipped = (await manager.patch(base, json={"version": marketing["version"], "marketing": True})).json()
    assert flipped["approved_at"] is None, "turning a text into marketing needs a new sign-off"


async def test_an_approved_template_can_always_be_deactivated(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    mai = await client_factory("doctor.mai")
    template = (await manager.post("/api/v1/admin/templates", json=_body())).json()
    approved = (
        await mai.post(f"/api/v1/admin/templates/{template['id']}/approve", json={"version": 1})
    ).json()
    off = await manager.patch(
        f"/api/v1/admin/templates/{template['id']}", json={"version": approved["version"], "active": False}
    )
    assert off.json()["active"] is False
    assert off.json()["approved_at"] is not None


async def test_duplicate_keys_and_bad_keys_are_refused_and_care_staff_cannot_write(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    cs = await client_factory("cs.maianh")
    body = _body()
    assert (await manager.post("/api/v1/admin/templates", json=body)).status_code == 201
    assert (await manager.post("/api/v1/admin/templates", json=body)).status_code == 422
    assert (await manager.post("/api/v1/admin/templates", json=_body(key="Bad Key!"))).status_code == 422
    assert (await cs.post("/api/v1/admin/templates", json=_body())).status_code == 403
    assert (await cs.get("/api/v1/admin/templates")).status_code == 403


async def test_the_worker_sees_only_active_and_approved_templates_through_its_view(
    client_factory: ClientFactory, world: SeedResult, worker_db: ClinicDatabase
) -> None:
    """chỉ job kind: message đã được bác sĩ duyệt mới có thể gửi trong patient_channel"""
    manager = await client_factory("manager")
    mai = await client_factory("doctor.mai")
    draft = (await manager.post("/api/v1/admin/templates", json=_body())).json()
    live = (await manager.post("/api/v1/admin/templates", json=_body())).json()
    await mai.post(f"/api/v1/admin/templates/{live['id']}/approve", json={"version": 1})
    async with worker_db.session() as session:
        keys = set(
            (
                await session.execute(text("SELECT template_key FROM clinic_agent.message_template_approved"))
            ).scalars()
        )
    assert live["template_key"] in keys
    assert draft["template_key"] not in keys
