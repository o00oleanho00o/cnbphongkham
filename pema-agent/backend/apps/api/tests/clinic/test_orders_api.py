# ruff: noqa: PT018
# new tests (package U, step U5; rule parity with prototype/order-test.cjs and product-catalog-test.cjs)
"""Catalog import and quick orders through the real HTTP API on a real Postgres: version must match, no edit
after payment, an approved order is immutable, the doctor of the order approves, drafts never print, and the
price list is imported once and idempotently. Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions import catalog, orders
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.domain.orders import CatalogRow, parse_catalog_rows
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.errors import ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

CATALOG_JSON = Path(__file__).resolve().parents[6] / "prototype" / "shared" / "product-catalog.json"
ORDERS = "/api/v1/orders"


def _rows() -> list[CatalogRow]:
    if not CATALOG_JSON.exists():
        pytest.skip("prototype catalog not in this checkout")
    return parse_catalog_rows(json.loads(CATALOG_JSON.read_text(encoding="utf-8")))


def _system(world: SeedResult) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.SYSTEM,
        source=ActionSource.SYSTEM,
        request_id="test-catalog",
    )


def _as(world: SeedResult, key: str, role: Role) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_id, actor_type=ActorType.USER, actor_user_id=world.users[key], actor_role=role
    )


@pytest.fixture
async def loaded(db: ClinicDatabase, world: SeedResult) -> SeedResult:
    """The demo clinic with the real catalog imported (the way ``pema catalog import`` does it)."""
    await catalog.import_catalog(db, _system(world), _rows(), source_name="product-catalog.json")
    return world


def _line(code: str, **fields: Any) -> dict[str, Any]:
    return {"product_code": code, "quantity": 1, "usage": "Bôi lớp mỏng, sáng và tối (mẫu)", **fields}


def _draft(world: SeedResult, items: list[dict[str, Any]] | None = None, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "patient_id": str(world.patients["P025"]),
        "diagnosis": "Nám · tăng sắc tố (mẫu)",
        "items": items if items is not None else [_line("H002"), _line("H005")],
    }
    return {**body, **fields}


async def _create(client: httpx.AsyncClient, world: SeedResult, **kw: Any) -> dict[str, Any]:
    response = await client.post(ORDERS, json=_draft(world, **kw))
    assert response.status_code == 201, response.text
    return response.json()


def _error(response: httpx.Response) -> tuple[int, str, str]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["message"]


# ----------------------------------------------------------------------------------------------- catalog
async def test_the_import_loads_115_products_and_a_second_run_changes_nothing(
    db: ClinicDatabase, world: SeedResult, admin: Engine, client_factory: ClientFactory
) -> None:
    rows = _rows()
    first = await catalog.import_catalog(db, _system(world), rows, source_name="product-catalog.json")
    assert (first.total, first.created, first.updated, first.deactivated) == (115, 115, 0, 0)
    assert first.unchanged_run is False
    again = await catalog.import_catalog(db, _system(world), rows, source_name="product-catalog.json")
    assert (again.created, again.updated, again.unchanged, again.unchanged_run) == (0, 0, 115, True)
    assert again.sha256 == first.sha256
    with admin.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic.catalog_import")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM clinic.product")).scalar_one() == 115
        audited = conn.execute(text("SELECT count(*) FROM clinic.audit_log WHERE action = 'catalog.import'"))
        assert audited.scalar_one() == 1  # the repeated run wrote nothing

    manager = await client_factory("manager")
    summary = (await manager.get("/api/v1/catalog/summary")).json()
    assert (summary["total"], summary["prescription"], summary["consultation"], summary["unresolved"]) == (
        115,
        30,
        78,
        7,
    )
    assert summary["source_name"] == "product-catalog.json"
    assert summary["sha256"] == first.sha256


async def test_a_changed_catalog_updates_rows_and_switches_off_codes_that_left_the_file(
    db: ClinicDatabase, world: SeedResult
) -> None:
    rows = _rows()
    await catalog.import_catalog(db, _system(world), rows, source_name="v1.json")
    edited = [r if r.code != "H002" else replace(r, price_vnd=6000) for r in rows][:-1]
    result = await catalog.import_catalog(db, _system(world), edited, source_name="v2.json")
    assert (result.updated, result.created, result.deactivated, result.unchanged_run) == (1, 0, 1, False)
    page = await catalog.list_products(db, _system(world), q="H002")
    assert page.items[0].price_vnd == 6000
    assert (await catalog.catalog_summary(db, _system(world))).total == 114


async def test_search_ignores_accents_and_puts_an_exact_code_first(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    found = (await reception.get("/api/v1/catalog/products", params={"q": "cicaderm"})).json()
    assert found["total"] >= 1 and found["items"][0]["code"] == "H005"
    assert found["items"][0]["route"] == "CONSULTATION"
    by_type = (await reception.get("/api/v1/catalog/products", params={"q": "thuoc", "limit": 200})).json()
    assert by_type["total"] >= 30
    exact = (await reception.get("/api/v1/catalog/products", params={"q": "h002"})).json()
    assert exact["items"][0]["code"] == "H002" and exact["items"][0]["price_vnd"] == 5500
    everything = (await reception.get("/api/v1/catalog/products", params={"limit": 200})).json()
    assert everything["total"] == 115 and len(everything["items"]) == 115


async def test_the_catalog_is_not_for_care_staff_and_nobody_imports_through_a_route(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    care = await client_factory("cs.maianh")
    assert (await care.get("/api/v1/catalog/products")).status_code == 403
    assert (await care.get("/api/v1/catalog/summary")).status_code == 403
    reception = await client_factory("reception.lan")
    assert (await reception.post("/api/v1/catalog/import")).status_code in {404, 405}


# --------------------------------------------------------------------------------------------- the draft
async def test_a_draft_snapshots_the_catalog_and_totals_the_lines(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(
        reception,
        loaded,
        items=[_line("H002", quantity=3), _line("h005", note="Ghi chú riêng", usage="Sáng và tối")],
        note="Dặn dò chung (mẫu)",
    )
    assert (order["status"], order["version"], order["editable"]) == ("draft", 1, True)
    assert order["total_vnd"] == 3 * 5500 + 715_000
    first, second = order["items"]
    assert (first["product_code"], first["quantity"], first["unit_price_vnd"], first["route"]) == (
        "H002",
        3,
        5500,
        "PRESCRIPTION",
    )
    assert (second["product_code"], second["route"], second["note"]) == (
        "H005",
        "CONSULTATION",
        "Ghi chú riêng",
    )
    assert order["doctor_name"].startswith("BS. Mai")  # the doctor of the patient
    assert order["ready_to_approve"] is True


async def test_a_draft_is_refused_for_an_unknown_product_a_bad_doctor_and_a_route_change_without_reason(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    unknown = await reception.post(ORDERS, json=_draft(loaded, items=[_line("ZZZ999")]))
    assert _error(unknown) == (422, "validation_failed", "Dòng 1: chọn sản phẩm từ catalog.")
    for quantity in (0, 10_000):
        bad = await reception.post(ORDERS, json=_draft(loaded, items=[_line("H002", quantity=quantity)]))
        assert bad.status_code == 422
    assert (await reception.post(ORDERS, json=_draft(loaded, items=[]))).status_code == 422
    no_reason = await reception.post(ORDERS, json=_draft(loaded, items=[_line("H095", route="CONSULTATION")]))
    assert _error(no_reason) == (422, "validation_failed", "Dòng 1: ghi lý do thay đổi phân loại.")
    not_a_doctor = await reception.post(ORDERS, json=_draft(loaded, doctor_id=str(loaded.users["cs.thu"])))
    assert _error(not_a_doctor) == (422, "validation_failed", "Chọn bác sĩ trong danh sách.")
    other_doctor = await reception.post(ORDERS, json=_draft(loaded, doctor_id=str(loaded.users["doctor.an"])))
    assert other_doctor.status_code == 201
    with_reason = await reception.post(
        ORDERS,
        json=_draft(loaded, items=[_line("H095", route="CONSULTATION", route_reason="Phân loại thủ công")]),
    )
    assert with_reason.status_code == 201
    assert with_reason.json()["items"][0]["catalog_route"] == "UNRESOLVED"


async def test_an_unclassified_product_is_a_draft_line_that_blocks_approval(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(reception, loaded, items=[_line("H002"), _line("H095")])
    assert (order["unresolved_count"], order["ready_to_approve"]) == (1, False)
    doctor = await client_factory("doctor.mai")
    refused = await doctor.post(f"{ORDERS}/{order['id']}/approve", json={"version": order["version"]})
    assert _error(refused) == (422, "validation_failed", "Dòng 2: cần phân loại trước khi duyệt hoặc in.")


# ------------------------------------------------------------------------------------------ edit rules
async def test_an_edit_must_carry_the_current_version_and_every_save_is_a_new_version(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(reception, loaded)
    body = {"version": order["version"], "diagnosis": "Đã sửa (mẫu)", "items": [_line("H002", quantity=2)]}
    saved = await reception.put(f"{ORDERS}/{order['id']}", json=body)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["version"], len(saved.json()["items"]), saved.json()["total_vnd"]) == (2, 1, 11_000)
    again = await reception.put(f"{ORDERS}/{order['id']}", json=body)  # the old window saves its stale copy
    assert _error(again) == (409, "version_conflict", "Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại.")
    unchanged = await reception.put(f"{ORDERS}/{order['id']}", json={**body, "version": 2})
    assert unchanged.json()["version"] == 3  # saving the same content still counts, as in the prototype


async def test_a_saved_line_keeps_its_name_and_price_when_the_catalog_changes_later(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(reception, loaded, items=[_line("H002", quantity=2)])
    repriced = [r if r.code != "H002" else replace(r, price_vnd=9999) for r in _rows()]
    await catalog.import_catalog(db, _system(loaded), repriced, source_name="v2.json")
    body = {"version": order["version"], "diagnosis": "Chẩn đoán (mẫu)", "items": [_line("H002", quantity=4)]}
    saved = (await reception.put(f"{ORDERS}/{order['id']}", json=body)).json()
    assert saved["items"][0]["unit_price_vnd"] == 5500  # the snapshot, not the new catalog price
    assert saved["total_vnd"] == 4 * 5500
    fresh = (await reception.post(ORDERS, json=_draft(loaded, items=[_line("H002")]))).json()
    assert fresh["items"][0]["unit_price_vnd"] == 9999  # a new order reads the new catalog


async def test_a_draft_with_money_received_cannot_be_edited(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(reception, loaded)
    async with db.session() as session:
        await orders.set_payment_state(
            session, _as(loaded, "owner", Role.OWNER), UUID(order["id"]), received_vnd=1000, paid=False
        )
    current = (await reception.get(f"{ORDERS}/{order['id']}")).json()
    body = {"version": current["version"], "diagnosis": "x", "items": [_line("H002")]}
    refused = await reception.put(f"{ORDERS}/{order['id']}", json=body)
    assert _error(refused) == (409, "invalid_state", "Đơn đã thu tiền; không thể sửa.")
    shown = (await reception.get(f"{ORDERS}/{order['id']}")).json()
    assert (shown["received_vnd"], shown["editable"]) == (1000, False)


# ----------------------------------------------------------------------------------------------- approval
async def test_only_the_responsible_doctor_or_the_owner_approves_and_the_order_is_then_immutable(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    # the patient P025 belongs to BS. Mai; the order is BS. An's
    order = await _create(reception, loaded, doctor_id=str(loaded.users["doctor.an"]))
    url = f"{ORDERS}/{order['id']}/approve"
    payload = {"version": order["version"]}
    for who in ("reception.lan", "manager", "cs.maianh"):
        refused = await (await client_factory(who)).post(url, json=payload)
        assert refused.status_code == 403, who
    wrong = await (await client_factory("doctor.mai")).post(url, json=payload)
    assert _error(wrong) == (403, "forbidden", "Bác sĩ duyệt phải là bác sĩ phụ trách đơn.")

    doctor = await client_factory("doctor.an")  # not the doctor of the patient, but the doctor of the order
    stale = await doctor.post(url, json={"version": 99})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "version_conflict"
    approved = await doctor.post(url, json=payload)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert (body["status"], body["version"], body["editable"]) == ("approved", 2, False)
    assert body["reviewed_by_name"].startswith("BS. An") and body["reviewed_at"] is not None
    again = await doctor.post(url, json=payload)  # idempotent: nothing changes
    assert again.status_code == 200 and again.json()["version"] == 2

    edit = {"version": 2, "diagnosis": "x", "items": [_line("H002")]}
    refused_edit = await reception.put(f"{ORDERS}/{order['id']}", json=edit)
    assert _error(refused_edit) == (409, "invalid_state", "Chỉ được sửa đơn nháp còn tồn tại.")

    # the database refuses it as well, whatever the code does
    with admin.connect() as conn:
        with pytest.raises(DBAPIError, match="approved order is immutable"):
            conn.execute(
                text("UPDATE clinic.\"order\" SET diagnosis = 'đổi' WHERE id = :id"), {"id": order["id"]}
            )
        conn.rollback()
        with pytest.raises(DBAPIError, match="lines of an approved order are immutable"):
            conn.execute(text("DELETE FROM clinic.order_item WHERE order_id = :id"), {"id": order["id"]})
        conn.rollback()


async def test_the_owner_may_approve_any_order_and_signs_it(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(reception, loaded, doctor_id=str(loaded.users["doctor.an"]))
    owner = await client_factory("owner")
    approved = await owner.post(f"{ORDERS}/{order['id']}/approve", json={"version": order["version"]})
    assert approved.status_code == 200
    assert approved.json()["reviewed_by_name"].startswith("BS. Tâm")
    assert approved.json()["doctor_name"].startswith("BS. An")


async def test_approval_needs_a_usage_a_diagnosis_and_something_to_print(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    doctor = await client_factory("doctor.mai")

    async def approve(**kw: Any) -> httpx.Response:
        order = await _create(reception, loaded, **kw)
        return await doctor.post(f"{ORDERS}/{order['id']}/approve", json={"version": order["version"]})

    no_usage = await approve(items=[_line("H002", usage="")])
    assert _error(no_usage) == (422, "validation_failed", "Dòng 1: cần cách dùng trước khi duyệt.")
    no_diagnosis = await approve(diagnosis="")
    assert _error(no_diagnosis) == (
        422,
        "validation_failed",
        "Cần nội dung tư vấn / chẩn đoán trước khi duyệt.",
    )
    only_excluded = await approve(items=[_line("H002", route="NONE", route_reason="Đã cấp riêng", usage="")])
    assert _error(only_excluded) == (422, "validation_failed", "Đơn không có sản phẩm để phát hành.")
    mixed = await approve(
        items=[_line("H002", route="NONE", route_reason="Đã cấp riêng", usage=""), _line("H005")]
    )
    assert mixed.status_code == 200  # a line that is not printed needs no usage


# --------------------------------------------------------------------------------------------- the print
async def test_a_draft_cannot_be_printed_and_an_approved_order_is_split_into_two_sheets(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _create(
        reception,
        loaded,
        items=[
            _line("H002"),
            _line("H005"),
            _line("H006"),
            _line("H007", route="NONE", route_reason="Đã cấp riêng", usage=""),
        ],
        diagnosis="<script>window.injected=true</script> & giữ nguyên",
    )
    draft = (await reception.get(f"{ORDERS}/{order['id']}/print-data")).json()
    assert draft["printable"] is False and draft["order"]["status"] == "draft"
    strict = await reception.get(f"{ORDERS}/{order['id']}/print-data", params={"require_approved": "true"})
    assert _error(strict) == (409, "invalid_state", "Đơn nháp cần bác sĩ duyệt trước khi in.")

    doctor = await client_factory("doctor.mai")
    assert (
        await doctor.post(f"{ORDERS}/{order['id']}/approve", json={"version": order["version"]})
    ).status_code == 200
    data = (
        await reception.get(f"{ORDERS}/{order['id']}/print-data", params={"require_approved": "true"})
    ).json()
    assert data["printable"] is True
    assert [x["product_code"] for x in data["prescription"]] == ["H002"]
    assert [x["product_code"] for x in data["consultation"]] == ["H005", "H006"]
    assert [x["product_code"] for x in data["excluded"]] == ["H007"] and data["unresolved"] == []
    assert data["order"]["total_vnd"] == 5500 + 715_000 + 2_808_000 + 660_000  # "Không in" is still billed
    assert data["patient"]["code"] == "P025"
    assert data["order"]["diagnosis"].startswith("<script>")  # stored verbatim: the page escapes it


async def test_the_patient_app_preview_lists_approved_orders_only_grouped_by_sheet(
    loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    doctor = await client_factory("doctor.mai")
    approved = await _create(
        reception,
        loaded,
        items=[
            _line("H002"),
            _line("H005"),
            _line("H007", route="NONE", route_reason="Đã cấp riêng", usage=""),
        ],
    )
    await doctor.post(f"{ORDERS}/{approved['id']}/approve", json={"version": approved["version"]})
    await _create(reception, loaded, items=[_line("H006")])  # a draft: never shown
    url = f"/api/v1/patients/{loaded.patients['P025']}/approved-orders"
    groups = (await doctor.get(url)).json()
    assert len(groups) == 1
    assert [x["product_code"] for x in groups[0]["prescription"]] == ["H002"]
    assert [x["product_code"] for x in groups[0]["consultation"]] == ["H005"]  # "Không in" never appears


# ---------------------------------------------------------------------------------- list, scope, audit
async def test_the_list_filters_by_patient_and_status_and_a_doctor_sees_only_his_patients(
    loaded: SeedResult, client_factory: ClientFactory, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    mine = await _create(reception, loaded)
    with admin.begin() as conn:  # P026 belongs to another doctor and is not scheduled with doctor.mai
        conn.execute(
            text("UPDATE clinic.patient SET doctor_id = :d WHERE id = :p"),
            {"d": str(loaded.users["doctor.an"]), "p": str(loaded.patients["P026"])},
        )
        conn.execute(
            text("DELETE FROM clinic.appointment WHERE patient_id = :p AND doctor_id = :d"),
            {"d": str(loaded.users["doctor.mai"]), "p": str(loaded.patients["P026"])},
        )
    other = await _create(
        reception, loaded, patient_id=str(loaded.patients["P026"]), doctor_id=str(loaded.users["doctor.an"])
    )
    everything = (await reception.get(ORDERS)).json()
    assert everything["total"] == 2
    assert [o["id"] for o in everything["items"]] == [other["id"], mine["id"]]  # newest first
    assert everything["items"][1]["item_count"] == 2 and everything["items"][1]["patient_code"] == "P025"
    by_patient = (await reception.get(ORDERS, params={"patient_id": str(loaded.patients["P025"])})).json()
    assert [o["id"] for o in by_patient["items"]] == [mine["id"]]
    drafts = (await reception.get(ORDERS, params={"status": "approved"})).json()
    assert drafts["total"] == 0

    doctor = await client_factory("doctor.mai")
    seen = (await doctor.get(ORDERS)).json()
    assert [o["id"] for o in seen["items"]] == [mine["id"]]
    forbidden = await doctor.get(f"{ORDERS}/{other['id']}")
    assert forbidden.status_code == 403
    care = await client_factory("cs.maianh")
    assert (await care.get(ORDERS)).status_code == 403
    assert (await care.post(ORDERS, json=_draft(loaded))).status_code == 403


async def test_every_order_mutation_is_audited_without_clinical_text(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    doctor = await client_factory("doctor.mai")
    order = await _create(
        reception, loaded, diagnosis="Chẩn đoán riêng tư (mẫu)", note="Dặn dò riêng tư (mẫu)"
    )
    saved = (
        await reception.put(
            f"{ORDERS}/{order['id']}",
            json={"version": 1, "diagnosis": "Chẩn đoán riêng tư (mẫu)", "items": [_line("H002")]},
        )
    ).json()
    await doctor.post(f"{ORDERS}/{order['id']}/approve", json={"version": saved["version"]})
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, details::text FROM clinic.audit_log WHERE entity_id = :id ORDER BY occurred_at, id"
            ),
            {"id": order["id"]},
        ).all()
    assert [r[0] for r in rows] == ["order.create_draft", "order.update_draft", "order.approve"]
    assert all("riêng tư" not in r[1] and "Bôi" not in r[1] for r in rows)


async def test_a_missing_order_is_a_404(loaded: SeedResult, client_factory: ClientFactory) -> None:
    doctor = await client_factory("doctor.mai")
    missing = await doctor.get(f"{ORDERS}/{uuid4()}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert (await doctor.get(f"{ORDERS}/{uuid4()}/print-data")).status_code == 404
    assert (await doctor.post(f"{ORDERS}/{uuid4()}/approve", json={"version": 1})).status_code == 404
