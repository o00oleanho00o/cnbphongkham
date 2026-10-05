# ruff: noqa: PT018
# new tests (package U, step U8: security pass over the actions and routes that U2..U7 added)
"""Security pass over the screens of package U.

Four things are pinned here, none of them with a fixed list of roles typed by hand where the matrix can say it:

* every route of U2..U7 answers 403 to exactly the roles whose permissions do not include what the action
  requires (derived from ``ROLE_PERMISSIONS``), and a few business sentences of the owner's rules are pinned as
  literals so a matrix edit cannot silently widen them (the cashier reads no finance totals, a doctor sees
  none of the clinic's money, care staff do not touch orders or the product catalog);
* every public action of the U modules starts with a permission check;
* the audit guard sees only ORM writes, so the U modules may not write with raw SQL or Core DML (one audited
  exception is named); and no U module logs or prints (nothing to leak a name or a phone number to);
* the CSV of the commission table and the photo limits have their own tests (``test_finance_domain``,
  ``test_finance_equivalence``, ``test_patient_care``); the last test here only checks they still exist.

Synthetic data only.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.rbac import ROLE_PERMISSIONS
from pema_contracts.roles import Permission, Role

pytestmark = pytest.mark.db

P = Permission
ROLE_OF = {
    "owner": Role.OWNER,
    "manager": Role.MANAGER,
    "doctor.mai": Role.DOCTOR,
    "cs.maianh": Role.CS_STAFF,
    "reception.lan": Role.RECEPTION,
}
FAKE = "00000000-0000-4000-8000-000000000001"
MONTH = "2026-09"


@dataclass(frozen=True)
class Route:
    name: str
    method: str
    path: str
    needs: tuple[Permission, ...]  # any of
    body: Callable[[SeedResult], dict[str, object]] | None = None


def _line(_: SeedResult) -> dict[str, object]:
    return {"product_code": "H002", "quantity": 1, "usage": "Bôi lớp mỏng (mẫu)"}


ROUTES: tuple[Route, ...] = (
    # U2
    Route("dashboard_kpis", "GET", "/dashboard/kpis", (P.APPOINTMENT_READ,)),
    # U3: sessions, plans, consult notes, photos (all through the patient)
    Route("list_sessions", "GET", "/patients/{P025}/sessions", (P.SESSION_READ,)),
    Route(
        "create_session",
        "POST",
        "/patients/{P025}/sessions",
        (P.SESSION_WRITE,),
        lambda w: {"performed_on": "2026-09-20", "session_type": "Laser CO2"},
    ),
    Route(
        "complete_session",
        "POST",
        f"/sessions/{FAKE}/complete",
        (P.SESSION_WRITE,),
        lambda w: {"version": 1},
    ),
    Route("review_session", "POST", f"/sessions/{FAKE}/review", (P.SESSION_WRITE,), lambda w: {"version": 1}),
    Route("list_plans", "GET", "/patients/{P025}/plans", (P.PATIENT_READ_360,)),
    Route(
        "create_plan",
        "POST",
        "/patients/{P025}/plans",
        (P.SESSION_WRITE,),
        lambda w: {"title": "Liệu trình mẫu", "service_code": "laser-co2", "total_sessions": 3},
    ),
    Route("update_plan", "PATCH", f"/plans/{FAKE}", (P.SESSION_WRITE,), lambda w: {"version": 1}),
    Route("list_consult_notes", "GET", "/patients/{P025}/consult-notes", (P.SESSION_READ,)),
    Route(
        "create_consult_draft",
        "POST",
        "/patients/{P025}/consult-notes",
        (P.SESSION_WRITE,),
        lambda w: {"input_text": "Khách mô tả nám hai bên má (mẫu)."},
    ),
    Route("list_media", "GET", "/patients/{P025}/media", (P.MEDIA_READ,)),
    Route(
        "media_upload_intent",
        "POST",
        "/patients/{P025}/media/upload-intent",
        (P.MEDIA_WRITE,),
        lambda w: {"stage": "before", "mime": "image/jpeg", "size_bytes": 1000},
    ),
    Route("confirm_media", "POST", f"/media/{FAKE}/confirm", (P.MEDIA_WRITE,)),
    Route("read_media", "GET", f"/media/{FAKE}/content", (P.MEDIA_READ,)),
    Route("studio", "GET", "/studio/{P025}", (P.PATIENT_READ_360,)),
    # U4
    Route("resources", "GET", "/resources", (P.APPOINTMENT_READ, P.ADMIN_RULES)),
    Route("create_room", "POST", "/rooms", (P.ADMIN_RULES,), lambda w: {"name": "Phòng mẫu"}),
    Route("update_room", "PATCH", f"/rooms/{FAKE}", (P.ADMIN_RULES,), lambda w: {"version": 1}),
    Route(
        "create_room_block",
        "POST",
        "/room-blocks",
        (P.ADMIN_RULES,),
        lambda w: {
            "room_id": FAKE,
            "day": "2026-09-21",
            "start": "09:00",
            "end": "10:00",
            "reason": "Vệ sinh",
        },
    ),
    Route("delete_room_block", "DELETE", f"/room-blocks/{FAKE}", (P.ADMIN_RULES,)),
    Route("list_services", "GET", "/services", (P.APPOINTMENT_READ, P.ADMIN_RULES)),
    Route(
        "create_service",
        "POST",
        "/services",
        (P.ADMIN_RULES,),
        lambda w: {
            "code": f"rbac-{uuid4().hex[:6]}",
            "name": "Dịch vụ mẫu",
            "price_vnd": 1000,
            "duration_min": 30,
        },
    ),
    Route("update_service", "PATCH", f"/services/{FAKE}", (P.ADMIN_RULES,), lambda w: {"version": 1}),
    Route("list_protocols", "GET", "/protocols", (P.ADMIN_RULES, P.SESSION_WRITE)),
    Route(
        "create_protocol",
        "POST",
        "/protocols",
        (P.ADMIN_RULES,),
        lambda w: {"code": f"rbac-{uuid4().hex[:6]}", "name": "Phác đồ mẫu"},
    ),
    Route("update_protocol", "PATCH", f"/protocols/{FAKE}", (P.ADMIN_RULES,), lambda w: {"version": 1}),
    # U5
    Route("list_orders", "GET", "/orders", (P.ORDER_READ, P.ORDER_WRITE)),
    Route(
        "create_order",
        "POST",
        "/orders",
        (P.ORDER_WRITE,),
        lambda w: {"patient_id": str(w.patients["P025"]), "items": [_line(w)]},
    ),
    Route("get_order", "GET", f"/orders/{FAKE}", (P.ORDER_READ, P.ORDER_WRITE)),
    Route(
        "update_order",
        "PUT",
        f"/orders/{FAKE}",
        (P.ORDER_WRITE,),
        lambda w: {"version": 1, "items": [_line(w)]},
    ),
    Route("approve_order", "POST", f"/orders/{FAKE}/approve", (P.ORDER_APPROVE,), lambda w: {"version": 1}),
    Route("print_data", "GET", f"/orders/{FAKE}/print-data", (P.ORDER_READ, P.ORDER_WRITE)),
    Route("approved_orders", "GET", "/patients/{P025}/approved-orders", (P.ORDER_READ, P.ORDER_WRITE)),
    Route("catalog_products", "GET", "/catalog/products", (P.ORDER_READ, P.ORDER_WRITE)),
    Route("catalog_summary", "GET", "/catalog/summary", (P.ORDER_READ, P.ORDER_WRITE)),
    # U6
    Route(
        "finance_overview", "GET", f"/finance/overview?month={MONTH}", (P.FINANCE_READ, P.FINANCE_READ_OWN)
    ),
    Route("finance_entries", "GET", f"/finance/entries?month={MONTH}", (P.FINANCE_READ, P.FINANCE_READ_OWN)),
    Route("finance_export", "GET", f"/finance/export?month={MONTH}", (P.FINANCE_READ, P.FINANCE_READ_OWN)),
    Route("finance_performers", "GET", "/finance/performers", (P.FINANCE_WRITE,)),
    Route(
        "finance_create_entry",
        "POST",
        "/finance/entries",
        (P.FINANCE_WRITE,),
        lambda w: {
            "patient_id": str(w.patients["P025"]),
            "service_id": FAKE,
            "entry_date": "2026-09-20",
            "list_vnd": 1000,
            "note": "Đã hoàn tất (mẫu)",
            "people": [{"doctor_id": str(w.users["owner"]), "share_bp": 10000, "rate_bp": 1000}],
        },
    ),
    Route("finance_approve_entry", "POST", f"/finance/entries/{FAKE}/approve", (P.FINANCE_WRITE,)),
    Route(
        "finance_void_entry",
        "POST",
        f"/finance/entries/{FAKE}/void",
        (P.FINANCE_WRITE,),
        lambda w: {"reason": "Nhập nhầm (mẫu)"},
    ),
    Route("finance_periods", "GET", "/finance/periods", (P.FINANCE_READ,)),
    Route("finance_close_period", "POST", f"/finance/periods/{MONTH}/close", (P.FINANCE_WRITE,)),
    Route(
        "finance_pay_period",
        "POST",
        f"/finance/periods/{MONTH}/pay",
        (P.FINANCE_WRITE,),
        lambda w: {"reference": "UNC-0001 (mẫu)"},
    ),
    Route("finance_invoices", "GET", "/finance/invoices", (P.FINANCE_READ, P.FINANCE_COLLECT)),
    Route("finance_billable_orders", "GET", "/finance/billable-orders", (P.FINANCE_READ, P.FINANCE_COLLECT)),
    Route(
        "finance_invoice_from_order",
        "POST",
        "/finance/invoices/from-order",
        (P.FINANCE_COLLECT,),
        lambda w: {"order_id": FAKE},
    ),
    Route("finance_payments", "GET", f"/finance/payments?month={MONTH}", (P.FINANCE_READ,)),
    Route(
        "finance_record_payment",
        "POST",
        "/finance/payments",
        (P.FINANCE_COLLECT,),
        lambda w: {"id": f"rbac-{uuid4().hex[:8]}", "invoice_id": FAKE, "amount_vnd": 1000, "method": "cash"},
    ),
    Route("finance_notifications", "GET", "/finance/notifications", (P.FINANCE_NOTIFICATIONS,)),
    Route(
        "finance_read_notification",
        "POST",
        f"/finance/notifications/{FAKE}/read",
        (P.FINANCE_NOTIFICATIONS,),
    ),
    # U7
    Route("crm_segments", "GET", "/crm/segments", (P.CRM_TASK_READ,)),
)


def _allowed(route: Route) -> frozenset[str]:
    return frozenset(user for user, role in ROLE_OF.items() if ROLE_PERMISSIONS[role] & set(route.needs))


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r.name)
async def test_each_role_gets_403_exactly_when_the_matrix_denies_it(
    route: Route, client_factory: ClientFactory, world: SeedResult
) -> None:
    path = route.path
    for code, patient_id in world.patients.items():
        path = path.replace("{" + code + "}", str(patient_id))
    body = route.body(world) if route.body else None
    allowed = _allowed(route)
    for user in sorted(ROLE_OF):
        client = await client_factory(user)
        kwargs: dict[str, object] = {"json": body} if body is not None else {}
        response = await client.request(route.method, f"/api/v1{path}", **kwargs)  # type: ignore[arg-type]
        denied = user not in allowed
        assert (response.status_code == 403) is denied, (
            f"{user} {route.method} {route.path}: got {response.status_code}, "
            f"expected {'403' if denied else 'anything but 403'}"
        )
        if denied:
            assert response.json()["error"]["code"] == "forbidden"


def test_the_owners_money_rules_are_pinned_as_literals() -> None:
    """A matrix edit that widens one of these fails here, not in production."""

    def holds(role: Role, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[role]

    # the cashier work of the clinic: reception and manager collect, only the owner sees the owner's inbox
    assert holds(Role.RECEPTION, P.FINANCE_COLLECT)
    assert not holds(Role.RECEPTION, P.FINANCE_READ)
    assert not holds(Role.RECEPTION, P.FINANCE_WRITE)
    assert not holds(Role.MANAGER, P.FINANCE_NOTIFICATIONS)
    # a doctor sees only the rows of their own and never changes a commission
    assert holds(Role.DOCTOR, P.FINANCE_READ_OWN)
    assert not holds(Role.DOCTOR, P.FINANCE_READ)
    assert not holds(Role.DOCTOR, P.FINANCE_WRITE)
    assert not holds(Role.DOCTOR, P.FINANCE_COLLECT)
    # care staff: no money, no orders, no clinical writes
    for permission in (P.FINANCE_READ, P.FINANCE_WRITE, P.FINANCE_COLLECT, P.ORDER_WRITE, P.SESSION_WRITE):
        assert not holds(Role.CS_STAFF, permission)
    # signing an order is a clinician's act; neither the manager nor the cashier holds it
    assert holds(Role.DOCTOR, P.ORDER_APPROVE)
    assert not holds(Role.MANAGER, P.ORDER_APPROVE)
    assert not holds(Role.RECEPTION, P.ORDER_APPROVE)
    # photos: written only by those who look after the patient, never by reception
    assert not holds(Role.RECEPTION, P.MEDIA_WRITE)
    assert not holds(Role.RECEPTION, P.MEDIA_READ)
    # the patient role has no staff permission at all
    assert not ROLE_PERMISSIONS[Role.PATIENT]


# ------------------------------------------------------------------------------------------------ static guards
ACTIONS = Path(__file__).resolve().parents[2] / "pema" / "clinic" / "actions"
FINANCE = Path(__file__).resolve().parents[2] / "pema" / "clinic" / "finance"
ROUTERS = Path(__file__).resolve().parents[2] / "pema" / "api" / "routers"

# the action modules and routers that U2..U7 added or reshaped
U_ACTION_MODULES = (
    "resources",
    "services",
    "protocols",
    "studio",
    "orders",
    "catalog",
    "media",
    "sessions",
    "plans",
    "consult_notes",
    "finance",
    "finance_cash",
    "patient_360",
    "guide",
    "crm_overview",
)
U_ROUTERS = ("resources", "services", "orders", "finance", "guide", "patient_care", "dashboard")
GATES = {"require", "require_any", "resolve_scope", "has_permission"}


def _calls(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return names


@pytest.mark.parametrize("module", U_ACTION_MODULES)
def test_every_public_action_checks_a_permission(module: str) -> None:
    """An action is a public ``async def`` taking ``(db, ctx, ...)``; it must reach a permission gate itself or
    through a sibling helper of its own module that does."""
    tree = ast.parse((ACTIONS / f"{module}.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    gated = {name for name, fn in functions.items() if _calls(fn) & GATES}
    # one round of helpers is enough for this code base: ``overview`` -> ``resolve_scope``
    gated |= {name for name, fn in functions.items() if _calls(fn) & gated}
    actions = [
        fn
        for fn in functions.values()
        if isinstance(fn, ast.AsyncFunctionDef)
        and not fn.name.startswith("_")
        and [a.arg for a in fn.args.args][:2] == ["db", "ctx"]
    ]
    assert actions, f"{module}: no action found (the check itself is broken)"
    unguarded = [fn.name for fn in actions if fn.name not in gated]
    assert not unguarded, f"{module}: actions without a permission check: {unguarded}"


DML = re.compile(r"""text\(\s*f?(?:\"\"\"|\"|')\s*(INSERT|UPDATE|DELETE)\b""", re.IGNORECASE)
CORE_DML = re.compile(r"\b(?:update|delete|insert)\((?=[A-Z])")  # update(Order), delete(Room) ...
AUDIT_WINDOW = 1500  # characters: the audit row of the same unit of work follows the write closely


@pytest.mark.parametrize("module", U_ACTION_MODULES)
def test_a_write_outside_the_orm_is_followed_by_its_audit_row(module: str) -> None:
    """``clinic.audit.guard`` sees ORM objects only. The U actions write through the ORM; the few raw or Core
    statements (the order-to-invoice link, the tags of a KB source) must write their audit row right after, in
    the same transaction, because the guard cannot do it for them."""
    source = (ACTIONS / f"{module}.py").read_text(encoding="utf-8")
    for match in [*DML.finditer(source), *CORE_DML.finditer(source)]:
        tail = source[match.start() : match.start() + AUDIT_WINDOW]
        line = source.count("\n", 0, match.start()) + 1
        assert "audit.record(" in tail, (
            f"{module}.py line {line}: a write the guard cannot see has no audit row"
        )


def test_the_two_known_writes_outside_the_orm_are_still_the_only_ones() -> None:
    """A third one is allowed only by adding it here, on purpose, with its audit row."""
    found = {
        module: len(DML.findall(text)) + len(CORE_DML.findall(text))
        for module in U_ACTION_MODULES
        if (text := (ACTIONS / f"{module}.py").read_text(encoding="utf-8"))
    }
    assert {m: n for m, n in found.items() if n} == {"finance_cash": 1, "guide": 1}


@pytest.mark.parametrize("path", [*(ACTIONS / f"{m}.py" for m in U_ACTION_MODULES), FINANCE / "domain.py"])
def test_no_u_module_logs_or_prints(path: Path) -> None:
    """The logger must never see a name, a phone number or a note; the U modules have no logger at all."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name=node.module or "")])
    }
    assert "logging" not in imported and "structlog" not in imported, f"{path.name} imports a logger"
    assert "print" not in _calls(tree), f"{path.name} prints"


@pytest.mark.parametrize("router", U_ROUTERS)
def test_no_u_router_logs_or_prints(router: str) -> None:
    source = (ROUTERS / f"{router}.py").read_text(encoding="utf-8")
    assert "logging" not in source and "logger" not in source and "print(" not in source


def test_the_csv_guard_and_the_photo_limits_keep_their_own_tests() -> None:
    here = Path(__file__).parent
    finance = (here / "test_finance_domain.py").read_text(encoding="utf-8")
    assert "csv_safe" in finance and "formula" in finance
    care = (here / "test_patient_care.py").read_text(encoding="utf-8")
    assert "image/gif" in care and "413" in care  # wrong type refused, too large refused
