# new tests (package U, step U6; the HTTP face of prototype/finance_server.py: /state, /command/*, /export)
"""The finance routes through the real HTTP API: status codes, the error envelope, the retry of a receipt, the month
workflow and who may call what. Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult

pytestmark = pytest.mark.db

F = "/api/v1/finance"
MONTH = f"{DEMO_DAY.year:04d}-{DEMO_DAY.month:02d}"
LAST_MONTH = "2026-08"


def _error(response: httpx.Response) -> tuple[int, str, str]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["message"]


async def _laser(client: httpx.AsyncClient) -> str:
    listed = (await client.get("/api/v1/services")).json()
    return next(s["id"] for s in listed if s["code"] == "laser-co2")


def _entry_body(world: SeedResult, service_id: str, day: str, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "patient_id": str(world.patients["P025"]),
        "service_id": service_id,
        "entry_date": day,
        "list_vnd": 2_500_000,
        "discount_vnd": 100_000,
        "note": "Đã hoàn tất (mẫu)",
        "people": [
            {"doctor_id": str(world.users["owner"]), "share_bp": 7000, "rate_bp": 1500},
            {"doctor_id": str(world.users["doctor.mai"]), "share_bp": 3000, "rate_bp": 500},
        ],
    }
    body.update(fields)
    return body


async def test_the_month_workflow_over_http(client_factory: ClientFactory, world: SeedResult) -> None:
    manager = await client_factory("manager")
    service = await _laser(manager)
    created = await manager.post(f"{F}/entries", json=_entry_body(world, service, "2026-08-10"))
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["status"] == "pending"
    assert entry["net_vnd"] == 2_400_000
    assert entry["owns_invoice"] is True
    assert [p["fee_vnd"] for p in entry["people"]] == [360_000, 120_000]

    periods = (await manager.get(f"{F}/periods")).json()
    august = next(p for p in periods["items"] if p["month"] == LAST_MONTH)
    assert (august["closable"], august["blocker"]) == (False, "Còn lượt chờ duyệt")
    assert _error(await manager.post(f"{F}/periods/{LAST_MONTH}/close"))[2] == "Còn lượt chờ duyệt"
    assert _error(await manager.post(f"{F}/periods/{MONTH}/close"))[0] == 409

    approved = await manager.post(f"{F}/entries/{entry['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    closed = await manager.post(f"{F}/periods/{LAST_MONTH}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert _error(await manager.post(f"{F}/entries/{entry['id']}/void", json={"reason": "Sai"})) == (
        409,
        "invalid_state",
        "Kỳ đã chốt, không được sửa",
    )
    assert (
        _error(await manager.post(f"{F}/entries", json=_entry_body(world, service, "2026-08-11")))[0] == 409
    )
    assert _error(await manager.post(f"{F}/periods/{LAST_MONTH}/pay", json={"reference": " "}))[0] == 422
    paid = await manager.post(f"{F}/periods/{LAST_MONTH}/pay", json={"reference": "CHI-HTTP"})
    assert paid.status_code == 200
    assert (paid.json()["status"], paid.json()["reference"]) == ("paid", "CHI-HTTP")

    owner = await client_factory("owner")
    overview = (await owner.get(f"{F}/overview", params={"month": LAST_MONTH})).json()
    assert overview["period"]["status"] == "paid"
    assert overview["scope"] == "clinic"
    assert overview["summary"]["revenue_vnd"] == 2_400_000
    assert overview["summary"]["fee_vnd"] == 480_000
    assert [t["entry_count"] for t in overview["team"] if t["doctor_name"].startswith("BS. Tâm")] == [1]
    personal = (await owner.get(f"{F}/overview", params={"month": LAST_MONTH, "scope": "own"})).json()
    assert personal["scope"] == "own"
    assert personal["summary"]["collected_vnd"] is None
    assert personal["summary"]["revenue_vnd"] == 1_680_000


async def test_a_receipt_over_http_is_201_then_200_and_errors_use_the_envelope(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    service = await _laser(manager)
    entry = (
        await manager.post(f"{F}/entries", json=_entry_body(world, service, DEMO_DAY.isoformat()))
    ).json()
    receipt = {
        "id": "http-receipt-0001",
        "invoice_id": entry["invoice_id"],
        "amount_vnd": 1_000_000,
        "method": "cash",
    }
    first = await manager.post(f"{F}/payments", json=receipt)
    assert first.status_code == 201
    assert first.json()["replayed"] is False
    retry = await manager.post(f"{F}/payments", json=receipt)
    assert retry.status_code == 200
    assert retry.json()["replayed"] is True
    assert retry.json()["id"] == first.json()["id"]
    assert _error(await manager.post(f"{F}/payments", json={**receipt, "amount_vnd": 5})) == (
        409,
        "duplicate_request",
        "Mã giao dịch đã dùng cho nội dung khác",
    )
    over = {**receipt, "id": "http-receipt-0002", "amount_vnd": 1_400_001}
    assert _error(await manager.post(f"{F}/payments", json=over)) == (
        422,
        "validation_failed",
        "Số thu vượt công nợ",
    )
    assert (await manager.post(f"{F}/payments", json={**receipt, "id": "ab"})).status_code == 422
    assert (await manager.post(f"{F}/payments", json={**receipt, "method": "card"})).status_code == 422
    listed = (await manager.get(f"{F}/payments", params={"month": MONTH})).json()
    assert listed["total"] == 1
    assert listed["items"][0]["method"] == "cash"
    due = (await manager.get(f"{F}/invoices", params={"due_only": "true"})).json()
    assert [(i["received_vnd"], i["due_vnd"]) for i in due["items"]] == [(1_000_000, 1_400_000)]


async def test_who_may_call_what_over_http(client_factory: ClientFactory, world: SeedResult) -> None:
    manager = await client_factory("manager")
    service = await _laser(manager)
    entry = (
        await manager.post(f"{F}/entries", json=_entry_body(world, service, DEMO_DAY.isoformat()))
    ).json()
    reception = await client_factory("reception.lan")
    doctor = await client_factory("doctor.mai")
    cs = await client_factory("cs.thu")
    owner = await client_factory("owner")

    receipt = {
        "id": "http-who-0001",
        "invoice_id": entry["invoice_id"],
        "amount_vnd": 100_000,
        "method": "transfer",
    }
    assert (await reception.post(f"{F}/payments", json=receipt)).status_code == 201  # the cashier collects
    for client in (doctor, cs):
        assert (
            await client.post(f"{F}/payments", json={**receipt, "id": "http-who-0002"})
        ).status_code == 403
    assert (await reception.get(f"{F}/invoices", params={"due_only": "true"})).status_code == 200
    assert (await reception.get(f"{F}/overview", params={"month": MONTH})).status_code == 403
    assert (await reception.get(f"{F}/payments", params={"month": MONTH})).status_code == 403
    assert (
        await reception.post(f"{F}/entries", json=_entry_body(world, service, DEMO_DAY.isoformat()))
    ).status_code == 403
    assert (await doctor.get(f"{F}/performers")).status_code == 403
    assert (await manager.get(f"{F}/performers")).status_code == 200
    assert (await doctor.get(f"{F}/periods")).status_code == 403
    assert (await cs.get(f"{F}/overview", params={"month": MONTH})).status_code == 403

    assert (await owner.get(f"{F}/notifications")).status_code == 200
    assert (await manager.get(f"{F}/notifications")).status_code == 403
    note = (await owner.get(f"{F}/notifications")).json()[0]
    assert note["body"] == "P025 · 100.000 đ · Chuyển khoản"
    assert note["read"] is False
    marked = await owner.post(f"{F}/notifications/{note['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["read"] is True
    assert (await manager.post(f"{F}/notifications/{note['id']}/read")).status_code == 403
    assert _error(await owner.post(f"{F}/notifications/00000000-0000-4000-8000-00000000dead/read"))[0] == 404


async def test_an_entry_is_checked_before_it_is_written(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    service = await _laser(manager)
    tomorrow = _entry_body(world, service, "2026-09-21")
    assert _error(await manager.post(f"{F}/entries", json=tomorrow)) == (
        422,
        "validation_failed",
        "Ngày thực hiện không hợp lệ",
    )
    stranger = _entry_body(
        world, service, DEMO_DAY.isoformat(), invoice_id="00000000-0000-4000-8000-00000000dead"
    )
    assert _error(await manager.post(f"{F}/entries", json=stranger))[2] == "Hóa đơn không thuộc bệnh nhân này"
    nurse = _entry_body(world, service, DEMO_DAY.isoformat())
    nurse["people"] = [{"doctor_id": str(world.users["reception.lan"]), "share_bp": 10000, "rate_bp": 0}]
    assert _error(await manager.post(f"{F}/entries", json=nurse))[2] == "Người thực hiện không hợp lệ"
    assert (await manager.get(f"{F}/entries", params={"month": MONTH})).json()["rows"] == []
