"""``GET /api/v1/staff/assignable``: the picker behind "Phụ trách" (package ST-S).

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL``. The route is open to every signed-in staff
member, shows the minimum a picker needs and never lists a locked account or a role that cannot work the item.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api import dashboard_auth as auth
from pema.api.clinic_testing import ClientFactory, add_staff_account
from pema.api.read_rate_limit import STAFF_LIST_MAX_PER_MINUTE, staff_list_limiter
from pema.clinic.actions import assignees
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

URL = "/api/v1/staff/assignable"
ALL_STAFF_KEYS = ["owner", "manager", "doctor.mai", "cs.maianh", "reception.lan"]
ASSIGNABLE_KEYS = ["owner", "manager", "doctor.mai", "doctor.an", "cs.maianh", "cs.thu"]


@pytest.fixture(autouse=True)
def _fresh_limiter() -> Iterator[None]:
    staff_list_limiter.reset()
    yield
    staff_list_limiter.reset()


def _lock(admin: Engine, user_id: object) -> None:
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.user_account SET active = false WHERE id = :u"), {"u": user_id})


def _rename(admin: Engine, user_id: object, name: str) -> None:
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.user_account SET display_name = :n WHERE id = :u"), {"n": name, "u": user_id}
        )


async def test_the_route_refuses_a_caller_without_a_session(app: FastAPI, world: SeedResult) -> None:
    """không có phiên đăng nhập thì 401, không lộ danh sách"""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        response = await anonymous.get(URL)
    assert response.status_code == 401
    assert "name" not in response.text


@pytest.mark.parametrize("key", ALL_STAFF_KEYS)
async def test_every_staff_role_may_read_the_list(
    client_factory: ClientFactory, world: SeedResult, key: str
) -> None:
    """mọi vai trò nhân viên (kể cả lễ tân, CSKH) đọc được, không cần quyền quản trị"""
    caller = await client_factory(key)
    response = await caller.get(URL)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert {row["id"] for row in rows} == {str(world.users[k]) for k in ASSIGNABLE_KEYS}


async def test_each_row_carries_only_id_name_and_role(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """không email, SĐT, hash, lần đăng nhập cuối hay trạng thái khóa"""
    caller = await client_factory("cs.thu")
    response = await caller.get(URL)
    rows: list[dict[str, Any]] = response.json()
    assert rows
    for row in rows:
        assert set(row) == {"id", "name", "role"}
    body = response.text.lower()
    for leak in ("@example.test", "argon2", "password", "email", "phone", "last_login", "active", "version"):
        assert leak not in body


async def test_reception_and_patient_roles_are_not_assignable(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    """lễ tân không xử lý hội thoại hay việc CSKH nên không được liệt kê; vai trò bệnh nhân cũng không"""
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (id, clinic_id, email, display_name, role, active) "
                "VALUES (:i, :c, :e, 'Tài khoản bệnh nhân (mẫu)', 'patient', true)"
            ),
            {"i": uuid4(), "c": world.clinic_id, "e": f"patient.{uuid4().hex[:8]}@example.test"},
        )
    caller = await client_factory("owner")
    rows = (await caller.get(URL)).json()
    roles = {row["role"] for row in rows}
    assert roles == {"owner", "manager", "doctor", "cs_staff"}
    assert str(world.users["reception.lan"]) not in {row["id"] for row in rows}
    assert "Tài khoản bệnh nhân (mẫu)" not in {row["name"] for row in rows}


async def test_a_locked_account_is_not_listed(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """tài khoản đã khóa không hiện trong danh sách"""
    _lock(admin, world.users["cs.thu"])
    caller = await client_factory("cs.maianh")
    ids = {row["id"] for row in (await caller.get(URL)).json()}
    assert str(world.users["cs.thu"]) not in ids
    assert str(world.users["cs.maianh"]) in ids


async def test_the_list_is_sorted_by_name_ignoring_case_with_the_id_as_tie_break(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    """sắp A-Z theo tên không phân biệt hoa thường, trùng tên thì theo id (thứ tự ổn định)"""
    twin_a = await add_staff_account(db, world)
    twin_b = await add_staff_account(db, world)
    with admin.connect() as conn:
        ids = {
            row.email: row.id
            for row in conn.execute(
                text("SELECT email, id FROM clinic.user_account WHERE email IN (:a, :b)"),
                {"a": twin_a, "b": twin_b},
            )
        }
    _rename(admin, ids[twin_a], "bbb Trùng tên (mẫu)")
    _rename(admin, ids[twin_b], "bbb Trùng tên (mẫu)")
    _rename(admin, world.users["cs.thu"], "AAA Đầu danh sách (mẫu)")
    _rename(admin, world.users["cs.maianh"], "zzz Cuối danh sách (mẫu)")
    caller = await client_factory("owner")

    first = (await caller.get(URL)).json()
    second = (await caller.get(URL)).json()

    assert first == second
    names = [row["name"] for row in first]
    assert names.index("AAA Đầu danh sách (mẫu)") < names.index("bbb Trùng tên (mẫu)")
    assert names.index("bbb Trùng tên (mẫu)") < names.index("zzz Cuối danh sách (mẫu)")
    twins = [row["id"] for row in first if row["name"] == "bbb Trùng tên (mẫu)"]
    assert twins == sorted(twins)
    assert len(twins) == 2


async def test_an_agent_or_a_non_staff_actor_is_refused_by_the_action(
    db: ClinicDatabase, world: SeedResult
) -> None:
    """tác nhân agent/scheduler hay vai trò bệnh nhân không đọc được danh sách"""
    for actor, role in ((ActorType.AGENT, None), (ActorType.SCHEDULER, None), (ActorType.USER, Role.PATIENT)):
        ctx = ActionContext(clinic_id=world.clinic_id, actor_type=actor, actor_role=role)
        with pytest.raises(DomainError) as refused:
            await assignees.list_assignable_staff(db, ctx)
        assert refused.value.code is ErrorCode.FORBIDDEN


async def test_the_route_is_limited_per_user(client_factory: ClientFactory, world: SeedResult) -> None:
    """quá 60 lần mỗi phút thì 429 (mã rate_limited), người khác không bị ảnh hưởng"""
    busy = await client_factory("cs.maianh")
    other = await client_factory("cs.thu")
    for _ in range(STAFF_LIST_MAX_PER_MINUTE):
        assert (await busy.get(URL)).status_code == 200
    limited = await busy.get(URL)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert (await other.get(URL)).status_code == 200


async def test_the_login_rate_limit_is_not_spent_by_the_picker(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """mở danh sách nhiều lần không làm cạn hạn mức đăng nhập 5 lần/phút"""
    caller = await client_factory("owner")
    for _ in range(10):
        assert (await caller.get(URL)).status_code == 200
    assert auth.allow_login_attempt("ip:probe-after-picker")
