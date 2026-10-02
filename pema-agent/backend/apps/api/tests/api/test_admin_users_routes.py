"""``GET/POST/PATCH /api/v1/admin/users``: the staff screen's backend (package H4).

New tests (zalo-agent had no accounts). Needs ``PEMA_TEST_DATABASE_URL``. The seeded accounts are shared by every
test of the session, so each test that changes an account creates its own through the route under test, and the
cases that need "the only owner of a clinic" seed a clinic of their own.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api import dashboard_auth as auth
from pema.api import dashboard_staff_store as staff_store
from pema.api.clinic_testing import ClientFactory, sign_in
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.auth import StaffUserUpdate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

PASSWORD = "owner-chosen-password-1"
STAFF_KEYS = ["doctor.mai", "cs.maianh", "reception.lan"]


async def _login(app: Any, email: str, password: str = PASSWORD) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post("/api/v1/auth/login", json={"email": email, "password": password})
    auth.reset_login_rate_limit()
    return response


async def _create(
    owner: httpx.AsyncClient,
    *,
    name: str | None = None,
    role: str = "cs_staff",
    email: str | None = None,
    password: str = PASSWORD,
) -> dict[str, Any]:
    """Create an account through the route and return it (the rate limit is reset: tests create many)."""
    auth.reset_login_rate_limit()
    tag = uuid4().hex[:10]
    response = await owner.post(
        "/api/v1/admin/users",
        json={
            "display_name": name or f"Nhân viên {tag} (mẫu)",
            "email": email or f"h4.{tag}@example.test",
            "role": role,
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _patch(client: httpx.AsyncClient, user: dict[str, Any] | str, **fields: Any) -> httpx.Response:
    ident = user if isinstance(user, str) else user["id"]
    version = 1 if isinstance(user, str) else user["version"]
    return await client.patch(f"/api/v1/admin/users/{ident}", json={"version": version, **fields})


async def _audit_rows(admin: Engine, request_id: str) -> list[Any]:
    with admin.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action, actor_user_id, actor_role, entity_type, entity_id, details::text AS details "
                    "FROM clinic.audit_log WHERE request_id = :r"
                ),
                {"r": request_id},
            ).all()
        )


# ---------------------------------------------------------------------------------------------- list


@pytest.mark.parametrize("key", ["owner", "manager"])
async def test_the_owner_and_the_manager_list_their_own_clinic_without_any_secret(
    client_factory: ClientFactory, world: SeedResult, key: str
) -> None:
    """chủ và quản lý xem được danh sách nhân viên của phòng khám mình, không có mật khẩu hay hash"""
    caller = await client_factory(key)

    response = await caller.get("/api/v1/admin/users?limit=200")

    assert response.status_code == 200
    page = response.json()
    ids = {item["id"] for item in page["items"]}
    assert {str(u) for u in world.users.values()} <= ids
    assert set(page["items"][0]) == {
        "id",
        "display_name",
        "email",
        "role",
        "active",
        "last_login_at",
        "created_at",
        "version",
    }
    assert "argon2" not in response.text
    assert "password" not in response.text
    assert all(item["role"] != "patient" for item in page["items"])
    assert page["total"] >= len(world.users)


@pytest.mark.parametrize("key", STAFF_KEYS)
async def test_doctor_cs_and_reception_cannot_list_staff(client_factory: ClientFactory, key: str) -> None:
    """bác sĩ, CSKH, lễ tân không xem được danh sách nhân viên (403, quyền admin.users.read)"""
    caller = await client_factory(key)

    response = await caller.get("/api/v1/admin/users")

    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"permission": "admin.users.read"}


async def test_the_list_needs_a_session(app: Any) -> None:
    """chưa đăng nhập thì không xem được danh sách"""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        assert (await http.get("/api/v1/admin/users")).status_code == 401


async def test_the_list_filters_by_role_status_and_name(client_factory: ClientFactory) -> None:
    """lọc theo vai trò, trạng thái khóa và tìm theo tên (không phân biệt hoa thường, không hiểu %, _ là ký tự đặc biệt)"""
    owner = await client_factory("owner")
    tag = uuid4().hex[:8]
    a = await _create(owner, name=f"Hà {tag} Bác sĩ", role="doctor")
    b = await _create(owner, name=f"Hà {tag} Lễ tân", role="reception")
    assert (await _patch(owner, b, active=False)).status_code == 200

    by_name = (await owner.get("/api/v1/admin/users", params={"q": f"hà {tag.upper()}"})).json()
    assert {i["id"] for i in by_name["items"]} == {a["id"], b["id"]}
    assert by_name["total"] == 2
    assert [i["display_name"] for i in by_name["items"]] == [f"Hà {tag} Bác sĩ", f"Hà {tag} Lễ tân"]

    by_role = (await owner.get("/api/v1/admin/users", params={"q": tag, "role": "doctor"})).json()
    assert [i["id"] for i in by_role["items"]] == [a["id"]]

    locked = (await owner.get("/api/v1/admin/users", params={"q": tag, "active": "false"})).json()
    assert [i["id"] for i in locked["items"]] == [b["id"]]
    assert locked["items"][0]["active"] is False
    working = (await owner.get("/api/v1/admin/users", params={"q": tag, "active": "true"})).json()
    assert [i["id"] for i in working["items"]] == [a["id"]]

    by_email = (await owner.get("/api/v1/admin/users", params={"q": a["email"]})).json()
    assert [i["id"] for i in by_email["items"]] == [a["id"]]

    wildcard = (await owner.get("/api/v1/admin/users", params={"q": "%"})).json()
    assert wildcard["total"] == 0, "a percent sign is text to find, not a wildcard"
    assert (await owner.get("/api/v1/admin/users", params={"role": "nonsense"})).status_code == 422


async def test_the_list_is_paged(client_factory: ClientFactory) -> None:
    """phân trang: limit, offset, total"""
    owner = await client_factory("owner")
    tag = uuid4().hex[:8]
    for n in range(3):
        await _create(owner, name=f"Trang {tag} {n}")

    first = (await owner.get("/api/v1/admin/users", params={"q": tag, "limit": 2})).json()
    second = (await owner.get("/api/v1/admin/users", params={"q": tag, "limit": 2, "offset": 2})).json()

    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (3, 2, 0, 2)
    assert (second["offset"], len(second["items"])) == (2, 1)
    assert [i["display_name"] for i in first["items"] + second["items"]] == [
        f"Trang {tag} {n}" for n in range(3)
    ]


async def test_a_patient_role_row_is_never_listed(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """dòng có vai trò bệnh nhân không bao giờ hiện trong danh sách nhân viên"""
    tag = uuid4().hex[:8]
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (clinic_id, email, display_name, role) "
                "VALUES (:c, :e, :n, 'patient')"
            ),
            {"c": world.clinic_id, "e": f"patient.{tag}@example.test", "n": f"Bệnh nhân {tag} (mẫu)"},
        )
    owner = await client_factory("owner")

    assert (await owner.get("/api/v1/admin/users", params={"q": tag})).json()["total"] == 0


# ---------------------------------------------------------------------------------------------- create


async def test_the_owner_creates_an_account_that_can_sign_in(
    app: Any, client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    """chủ tạo nhân viên; nhân viên đăng nhập được bằng mật khẩu ban đầu; email được chuẩn hóa chữ thường"""
    owner = await client_factory("owner")
    tag = uuid4().hex[:8]

    created = await _create(
        owner, name=f"Bác sĩ {tag} (mẫu)", role="doctor", email=f"H4.{tag.upper()}@Example.Test"
    )

    assert created["email"] == f"h4.{tag}@example.test"
    assert (created["role"], created["active"], created["version"], created["last_login_at"]) == (
        "doctor",
        True,
        1,
        None,
    )
    assert created["created_at"].endswith("+07:00")
    login = await _login(app, created["email"])
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "doctor"
    with admin.connect() as conn:
        stored = conn.execute(
            text("SELECT clinic_id, password_hash FROM clinic.user_account WHERE id = :i"),
            {"i": created["id"]},
        ).one()
    assert stored.clinic_id == world.clinic_id
    assert stored.password_hash.startswith("$argon2")
    assert PASSWORD not in stored.password_hash


async def test_the_owner_can_create_every_staff_role(client_factory: ClientFactory) -> None:
    """tạo được đủ năm vai trò nhân viên"""
    owner = await client_factory("owner")
    for role in ("owner", "manager", "doctor", "cs_staff", "reception"):
        assert (await _create(owner, role=role))["role"] == role


async def test_a_patient_account_cannot_be_created_here(client_factory: ClientFactory) -> None:
    """không tạo vai trò bệnh nhân ở màn nhân viên (422)"""
    owner = await client_factory("owner")
    response = await owner.post(
        "/api/v1/admin/users",
        json={
            "display_name": "Bệnh nhân",
            "email": "bn@example.test",
            "role": "patient",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == staff_store.NOT_A_STAFF_ROLE_MESSAGE


async def test_a_duplicate_email_is_a_409_even_in_another_case(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """email trùng trong phòng khám là 409, kể cả khác chữ hoa/thường; phòng khám khác dùng lại được"""
    owner = await client_factory("owner")
    first = await _create(owner)
    auth.reset_login_rate_limit()

    again = await owner.post(
        "/api/v1/admin/users",
        json={
            "display_name": "Trùng",
            "email": first["email"].upper(),
            "role": "cs_staff",
            "password": PASSWORD,
        },
    )
    seeded = await owner.post(
        "/api/v1/admin/users",
        json={
            "display_name": "Trùng",
            "email": "owner@example.test",
            "role": "cs_staff",
            "password": PASSWORD,
        },
    )

    assert again.status_code == seeded.status_code == 409
    assert again.json()["error"]["message"] == staff_store.DUPLICATE_EMAIL_MESSAGE
    assert again.json()["error"]["code"] == "invalid_state"


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"password": "ngan"}, "8 ký tự"),
        ({"email": "khong-phai-email"}, None),
        ({"display_name": "   "}, None),
        ({"role": "king"}, None),
    ],
)
async def test_a_bad_create_body_is_a_422_and_creates_nothing(
    client_factory: ClientFactory, admin: Engine, override: dict[str, str], fragment: str | None
) -> None:
    """mật khẩu dưới 8 ký tự, email sai dạng, tên trống, vai trò lạ: 422"""
    owner = await client_factory("owner")
    body = {
        "display_name": "Nhân viên mẫu",
        "email": f"bad.{uuid4().hex[:8]}@example.test",
        "role": "cs_staff",
    }
    body = {**body, "password": PASSWORD, **override}

    response = await owner.post("/api/v1/admin/users", json=body)

    assert response.status_code == 422
    if fragment:
        assert fragment in response.json()["error"]["message"]
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.user_account WHERE email = :e"), {"e": body["email"]}
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("key", ["manager", *STAFF_KEYS])
async def test_only_the_owner_can_create_everyone_else_gets_403(
    client_factory: ClientFactory, key: str, admin: Engine
) -> None:
    """chỉ chủ được tạo; vai trò khác 403 và không có dòng nào được tạo"""
    caller = await client_factory(key)
    email = f"denied.{uuid4().hex[:8]}@example.test"

    response = await caller.post(
        "/api/v1/admin/users",
        json={"display_name": "Bị chặn", "email": email, "role": "cs_staff", "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"permission": "admin.users"}
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.user_account WHERE email = :e"), {"e": email}
            ).scalar_one()
            == 0
        )


async def test_creating_is_rate_limited_per_owner_and_a_refused_caller_spends_nothing(
    client_factory: ClientFactory,
) -> None:
    """giới hạn tốc độ: 5 lần tạo mỗi phút mỗi chủ, lần thứ 6 bị 429; người bị 403 không tiêu giới hạn"""
    owner = await client_factory("owner")
    manager = await client_factory("manager")
    auth.reset_login_rate_limit()

    def attempt(who: httpx.AsyncClient) -> Any:
        return who.post(
            "/api/v1/admin/users",
            json={
                "display_name": "Giới hạn",
                "email": f"rate.{uuid4().hex[:10]}@example.test",
                "role": "cs_staff",
                "password": PASSWORD,
            },
        )

    for _ in range(auth.LOGIN_MAX_ATTEMPTS + 2):
        assert (await attempt(manager)).status_code == 403
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        assert (await attempt(owner)).status_code == 201
    blocked = await attempt(owner)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_a_create_is_audited_without_the_password_name_or_email(
    client_factory: ClientFactory,
    world: SeedResult,
    admin: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """audit user.create ghi ai tạo vai trò gì, không ghi mật khẩu, tên, email; log cũng sạch"""
    owner = await client_factory("owner")
    request_id = f"h4-create-{uuid4().hex}"
    tag = uuid4().hex[:8]
    email, name = f"audit.{tag}@example.test", f"Tên Kiểm Toán {tag}"
    auth.reset_login_rate_limit()

    with caplog.at_level(logging.DEBUG):
        response = await owner.post(
            "/api/v1/admin/users",
            headers={"X-Request-Id": request_id},
            json={"display_name": name, "email": email, "role": "doctor", "password": PASSWORD},
        )

    assert response.status_code == 201
    rows = await _audit_rows(admin, request_id)
    assert [r.action for r in rows] == ["user.create"]
    row = rows[0]
    assert (row.actor_user_id, row.actor_role, row.entity_type) == (
        world.users["owner"],
        "owner",
        "user_account",
    )
    assert row.entity_id == response.json()["id"]
    for secret in (PASSWORD, email, name, "argon2"):
        assert secret not in (row.details or "")
        assert secret not in caplog.text


# ---------------------------------------------------------------------------------------------- update


async def test_the_owner_renames_and_the_version_moves(client_factory: ClientFactory) -> None:
    """chủ đổi họ tên; version tăng; đổi vai trò và tên cùng lúc được"""
    owner = await client_factory("owner")
    user = await _create(owner, role="reception")

    renamed = await _patch(owner, user, display_name="Tên mới (mẫu)")
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "Tên mới (mẫu)"
    assert renamed.json()["version"] == user["version"] + 1
    assert renamed.json()["email"] == user["email"]

    both = await _patch(owner, renamed.json(), display_name="Tên khác (mẫu)", role="manager")
    assert both.status_code == 200
    assert (both.json()["role"], both.json()["display_name"]) == ("manager", "Tên khác (mẫu)")


async def test_a_stale_version_is_a_409_and_changes_nothing(client_factory: ClientFactory) -> None:
    """version cũ bị 409 version_conflict, bản ghi không đổi"""
    owner = await client_factory("owner")
    user = await _create(owner)
    assert (await _patch(owner, user, display_name="Lần một (mẫu)")).status_code == 200

    stale = await _patch(owner, user, display_name="Lần hai (mẫu)")

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    listed = (await owner.get("/api/v1/admin/users", params={"q": user["email"]})).json()["items"][0]
    assert listed["display_name"] == "Lần một (mẫu)"


async def test_an_empty_change_is_refused_and_an_unchanged_one_is_a_no_op(
    client_factory: ClientFactory, admin: Engine
) -> None:
    """không gửi trường nào thì 422; gửi đúng giá trị hiện tại thì trả nguyên trạng, không audit, không tăng version"""
    owner = await client_factory("owner")
    user = await _create(owner, role="doctor")

    assert (await _patch(owner, user)).status_code == 422

    request_id = f"h4-noop-{uuid4().hex}"
    same = await owner.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers={"X-Request-Id": request_id},
        json={
            "version": user["version"],
            "role": "doctor",
            "active": True,
            "display_name": user["display_name"],
        },
    )
    assert same.status_code == 200
    assert same.json()["version"] == user["version"]
    assert await _audit_rows(admin, request_id) == []


async def test_an_unknown_or_patient_id_is_the_same_404(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """id không có và dòng bệnh nhân đều trả cùng một 404 (không dò được loại tài khoản qua id)"""
    owner = await client_factory("owner")
    patient_id = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (id, clinic_id, email, display_name, role) "
                "VALUES (:i, :c, :e, 'Bệnh nhân (mẫu)', 'patient')"
            ),
            {"i": patient_id, "c": world.clinic_id, "e": f"p.{patient_id.hex[:8]}@example.test"},
        )

    answers = [
        await _patch(owner, str(target), display_name="Không được") for target in (uuid4(), patient_id)
    ]

    assert {a.status_code for a in answers} == {404}
    assert answers[0].json()["error"] == answers[1].json()["error"]
    names = {i["display_name"] for i in (await owner.get("/api/v1/admin/users?limit=200")).json()["items"]}
    assert "Không được" not in names


async def test_a_malformed_id_or_body_is_a_422(client_factory: ClientFactory) -> None:
    """id không phải UUID, thiếu version, trường lạ: 422"""
    owner = await client_factory("owner")
    assert (
        await owner.patch("/api/v1/admin/users/not-a-uuid", json={"version": 1, "active": False})
    ).status_code == 422
    user = await _create(owner)
    assert (await owner.patch(f"/api/v1/admin/users/{user['id']}", json={"active": False})).status_code == 422
    assert (
        await owner.patch(f"/api/v1/admin/users/{user['id']}", json={"version": 1, "email": "x@example.test"})
    ).status_code == 422
    assert (await _patch(owner, user, role="patient")).status_code == 422
    assert (await _patch(owner, user, display_name="  ")).status_code == 422


@pytest.mark.parametrize("key", ["manager", *STAFF_KEYS])
async def test_only_the_owner_can_edit_everyone_else_gets_403(
    client_factory: ClientFactory, world: SeedResult, key: str
) -> None:
    """chỉ chủ được sửa/khóa; quản lý và vai trò khác 403, không đổi gì"""
    caller = await client_factory(key)
    target = str(world.users["cs.thu"])

    response = await _patch(caller, target, active=False)

    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"permission": "admin.users"}
    owner = await client_factory("owner")
    row = next(
        i for i in (await owner.get("/api/v1/admin/users?limit=200")).json()["items"] if i["id"] == target
    )
    assert row["active"] is True


async def test_locking_ends_every_session_refuses_the_login_and_unlocking_restores_it(
    app: Any, client_factory: ClientFactory
) -> None:
    """khóa: mọi phiên bị thu hồi ngay, đăng nhập bị từ chối giống sai mật khẩu; mở khóa: đăng nhập lại được"""
    owner = await client_factory("owner")
    user = await _create(owner, role="cs_staff")
    laptop = await sign_in(app, user["email"], PASSWORD)
    phone = await sign_in(app, user["email"], PASSWORD)
    assert (await laptop.get("/api/v1/me")).status_code == 200

    locked = await _patch(owner, user, active=False)

    assert locked.status_code == 200
    assert locked.json()["active"] is False
    assert (await laptop.get("/api/v1/me")).status_code == 401
    assert (await phone.get("/api/v1/me")).status_code == 401
    assert (await owner.get("/api/v1/me")).status_code == 200
    refused = await _login(app, user["email"])
    wrong = await _login(app, user["email"], "wrong-password-1")
    assert refused.status_code == wrong.status_code == 401
    assert refused.json()["error"] == {
        **wrong.json()["error"],
        "request_id": refused.json()["error"]["request_id"],
    }

    unlocked = await _patch(owner, locked.json(), active=True)

    assert unlocked.status_code == 200
    assert unlocked.json()["active"] is True
    assert (await _login(app, user["email"])).status_code == 200
    for http in (laptop, phone):
        await http.aclose()


async def test_changing_the_role_ends_every_session_of_that_user(
    app: Any, client_factory: ClientFactory
) -> None:
    """đổi vai trò thu hồi mọi phiên của người đó; đăng nhập lại thì có quyền của vai trò mới"""
    owner = await client_factory("owner")
    user = await _create(owner, role="manager")
    session = await sign_in(app, user["email"], PASSWORD)
    assert "admin.users.read" in (await session.get("/api/v1/me")).json()["permissions"]

    assert (await _patch(owner, user, role="reception")).status_code == 200

    assert (await session.get("/api/v1/me")).status_code == 401
    again = await sign_in(app, user["email"], PASSWORD)
    assert "admin.users.read" not in (await again.get("/api/v1/me")).json()["permissions"]
    for http in (session, again):
        await http.aclose()


async def test_a_rename_alone_keeps_the_sessions(app: Any, client_factory: ClientFactory) -> None:
    """chỉ đổi họ tên thì phiên của người đó vẫn sống"""
    owner = await client_factory("owner")
    user = await _create(owner)
    session = await sign_in(app, user["email"], PASSWORD)

    assert (await _patch(owner, user, display_name="Chỉ đổi tên (mẫu)")).status_code == 200

    assert (await session.get("/api/v1/me")).status_code == 200
    await session.aclose()


async def test_the_owner_cannot_lock_or_re_role_their_own_account_but_can_rename_it(
    app: Any, client_factory: ClientFactory
) -> None:
    """tự khóa hoặc tự đổi vai trò của chính mình bị 422; tự đổi họ tên được"""
    seeded = await client_factory("owner")
    mine = await _create(seeded, role="owner")  # a second owner: no shared account is touched
    me = await sign_in(app, mine["email"], PASSWORD)

    lock = await _patch(me, mine, active=False)
    demote = await _patch(me, mine, role="manager")
    rename = await _patch(me, mine, display_name="Tên của tôi (mẫu)")

    assert lock.status_code == demote.status_code == 422
    assert lock.json()["error"]["message"] == staff_store.CANNOT_CHANGE_OWN_ACCESS_MESSAGE
    assert demote.json()["error"]["message"] == staff_store.CANNOT_CHANGE_OWN_ACCESS_MESSAGE
    assert rename.status_code == 200
    assert (rename.json()["role"], rename.json()["active"]) == ("owner", True)
    assert (await me.get("/api/v1/me")).status_code == 200
    await me.aclose()


async def test_one_owner_can_lock_and_demote_another_owner_while_one_remains(
    client_factory: ClientFactory,
) -> None:
    """chủ khóa hoặc hạ quyền chủ khác được khi vẫn còn một chủ hoạt động (việc mở: chủ phòng khám quyết định)"""
    seeded = await client_factory("owner")
    other = await _create(seeded, role="owner")
    third = await _create(seeded, role="owner")

    assert (await _patch(seeded, other, active=False)).status_code == 200
    assert (await _patch(seeded, third, role="manager")).status_code == 200


async def test_the_clinic_keeps_an_active_owner(db: ClinicDatabase, world: SeedResult) -> None:
    """không làm phòng khám mất chủ hoạt động cuối cùng (422), dù người gọi không phải một dòng thật"""
    only_owner = world.users["owner"]
    caller = ActionContext(
        clinic_id=world.clinic_id, actor_type=ActorType.USER, actor_user_id=uuid4(), actor_role=Role.OWNER
    )

    for change in (StaffUserUpdate(version=1, active=False), StaffUserUpdate(version=1, role=Role.MANAGER)):
        with pytest.raises(DomainError) as caught:
            await staff_store.update_staff(db, caller, only_owner, change)
        assert caught.value.code is ErrorCode.VALIDATION_FAILED
        assert caught.value.message == staff_store.LAST_OWNER_MESSAGE
    page = await staff_store.list_staff(db, caller, role=Role.OWNER, active=True)
    assert [i.id for i in page.items] == [only_owner]


async def test_two_owners_cannot_demote_each_other_at_the_same_moment(
    app: Any, db: ClinicDatabase, world: SeedResult
) -> None:
    """hai chủ hạ quyền nhau cùng lúc: đúng một lệnh thành công, phòng khám còn một chủ (khóa FOR UPDATE)"""
    first = await sign_in(app, "owner@example.test")
    created = await first.post(
        "/api/v1/admin/users",
        json={
            "display_name": "Chủ thứ hai (mẫu)",
            "email": "owner2@example.test",
            "role": "owner",
            "password": PASSWORD,
        },
    )
    assert created.status_code == 201
    second_user = created.json()
    second = await sign_in(app, second_user["email"], PASSWORD)
    first_user = next(
        i
        for i in (await first.get("/api/v1/admin/users")).json()["items"]
        if i["email"] == "owner@example.test"
    )

    results = await asyncio.gather(
        _patch(first, second_user, role="manager"),
        _patch(second, first_user, role="manager"),
    )

    assert sorted(r.status_code for r in results) == [200, 422]
    ctx = ActionContext(
        clinic_id=world.clinic_id, actor_type=ActorType.USER, actor_user_id=uuid4(), actor_role=Role.OWNER
    )
    owners = await staff_store.list_staff(db, ctx, role=Role.OWNER, active=True)
    assert owners.total == 1
    for http in (first, second):
        await http.aclose()


async def test_every_edit_is_audited_with_field_names_roles_and_never_a_name_or_email(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """audit user.update ghi trường nào đổi, vai trò cũ và mới, có thu hồi phiên hay không; không ghi tên, email"""
    owner = await client_factory("owner")
    user = await _create(owner, role="doctor")
    request_id = f"h4-update-{uuid4().hex}"
    new_name = f"Tên Audit {uuid4().hex[:8]}"

    response = await owner.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers={"X-Request-Id": request_id},
        json={"version": user["version"], "display_name": new_name, "role": "reception", "active": False},
    )

    assert response.status_code == 200
    rows = await _audit_rows(admin, request_id)
    assert [r.action for r in rows] == ["user.update"]
    row = rows[0]
    assert (row.actor_user_id, row.actor_role, row.entity_type, row.entity_id) == (
        world.users["owner"],
        "owner",
        "user_account",
        user["id"],
    )
    assert '"changed_fields": ["display_name", "role", "active"]' in row.details
    assert '"role_from": "doctor"' in row.details
    assert '"role_to": "reception"' in row.details
    assert '"sessions_revoked": true' in row.details
    for secret in (new_name, user["email"], PASSWORD):
        assert secret not in row.details


async def test_a_locked_account_can_still_have_its_password_reset_and_stays_locked(
    app: Any, client_factory: ClientFactory
) -> None:
    """đặt lại mật khẩu cho tài khoản đang khóa không mở khóa nó"""
    owner = await client_factory("owner")
    user = await _create(owner)
    assert (await _patch(owner, user, active=False)).status_code == 200

    reset = await owner.post(
        f"/api/v1/admin/users/{user['id']}/password", json={"new_password": "mat-khau-moi-123"}
    )

    assert reset.status_code == 204
    assert (await _login(app, user["email"], "mat-khau-moi-123")).status_code == 401


async def test_signing_in_sets_last_login_without_moving_the_version(
    app: Any, client_factory: ClientFactory
) -> None:
    """đăng nhập ghi lần đăng nhập cuối nhưng không làm tăng version (không gây 409 oan khi chủ đang sửa)"""
    owner = await client_factory("owner")
    user = await _create(owner)
    assert user["last_login_at"] is None

    assert (await _login(app, user["email"])).status_code == 200

    listed = (await owner.get("/api/v1/admin/users", params={"q": user["email"]})).json()["items"][0]
    assert listed["last_login_at"] is not None
    assert listed["version"] == user["version"]
    assert (await _patch(owner, user, display_name="Sửa sau khi họ đăng nhập (mẫu)")).status_code == 200


async def test_the_routes_are_in_the_contract(app: Any) -> None:
    """hợp đồng OpenAPI có ba route mới, bảo vệ bằng cookie phiên"""
    paths = app.openapi()["paths"]
    listing = paths["/api/v1/admin/users"]
    patch = paths["/api/v1/admin/users/{user_id}"]["patch"]
    assert listing["get"]["operationId"] == "admin_users_list_users"
    assert listing["post"]["operationId"] == "admin_users_create_user"
    assert "201" in listing["post"]["responses"]
    assert patch["operationId"] == "admin_users_update_user"
    for operation in (listing["get"], listing["post"], patch):
        assert any("SessionCookie" in requirement for requirement in operation["security"])
    schemas = app.openapi()["components"]["schemas"]
    assert not {"password", "password_hash"} & set(schemas["StaffUserOut"]["properties"])
