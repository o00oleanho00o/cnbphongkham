"""``POST /api/v1/admin/users/{user_id}/password``: the owner resets ANOTHER staff member's password (SEC-24).

New tests (zalo-agent had one dashboard password and a "delete one row" recovery). Needs
``PEMA_TEST_DATABASE_URL``. Every test resets a throw-away account (``add_staff_account``), never a seeded one.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api import dashboard_auth as auth
from pema.api.clinic_testing import ACCOUNT_PASSWORD, add_staff_account, sign_in
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

NEW_PASSWORD = "owner-chosen-password-1"


class Target:
    """The account being reset, with a way to log in as it and to look up its id."""

    def __init__(self, app: Any, db: ClinicDatabase, world: SeedResult, admin: Engine) -> None:
        self.app, self.db, self.world, self.admin = app, db, world, admin
        self.email = ""
        self.user_id = uuid4()
        self.clients: list[httpx.AsyncClient] = []

    async def create(self) -> Target:
        self.email = await add_staff_account(self.db, self.world)
        with self.admin.connect() as conn:
            self.user_id = conn.execute(
                text("SELECT id FROM clinic.user_account WHERE email = :e"), {"e": self.email}
            ).scalar_one()
        return self

    async def client(self, password: str = ACCOUNT_PASSWORD) -> httpx.AsyncClient:
        http = await sign_in(self.app, self.email, password)
        self.clients.append(http)
        return http

    async def login_status(self, password: str) -> int:
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(
                "/api/v1/auth/login",
                json={"email": self.email, "password": password},
            )
        auth.reset_login_rate_limit()
        return response.status_code


@pytest_asyncio.fixture
async def target(app: Any, db: ClinicDatabase, world: SeedResult, admin: Engine) -> AsyncIterator[Target]:
    made = await Target(app, db, world, admin).create()
    yield made
    for http in made.clients:
        await http.aclose()


def _reset(client: httpx.AsyncClient, user_id: UUID | str, password: str = NEW_PASSWORD) -> Any:
    return client.post(f"/api/v1/admin/users/{user_id}/password", json={"new_password": password})


async def test_the_owner_resets_a_password_and_login_uses_the_new_one(
    client_factory: Any, target: Target
) -> None:
    """chủ phòng khám đặt lại mật khẩu: đăng nhập bằng mật khẩu MỚI được, mật khẩu cũ hết dùng"""
    owner = await client_factory("owner")

    response = await _reset(owner, target.user_id)

    assert response.status_code == 204
    assert response.content == b""
    assert await target.login_status(NEW_PASSWORD) == 200
    assert await target.login_status(ACCOUNT_PASSWORD) == 401, "the old password must stop working"


async def test_every_session_of_the_reset_user_ends_and_the_owner_keeps_theirs(
    client_factory: Any, target: Target
) -> None:
    """MỌI phiên của người bị đặt lại đều bị thu hồi, phiên của chủ không bị ảnh hưởng"""
    owner = await client_factory("owner")
    laptop = await target.client()
    phone = await target.client()
    assert (await laptop.get("/api/v1/me")).status_code == 200
    assert (await phone.get("/api/v1/me")).status_code == 200

    assert (await _reset(owner, target.user_id)).status_code == 204

    assert (await laptop.get("/api/v1/me")).status_code == 401
    assert (await phone.get("/api/v1/me")).status_code == 401
    assert (await owner.get("/api/v1/me")).status_code == 200


@pytest.mark.parametrize("key", ["manager", "doctor.mai", "cs.maianh", "reception.lan"])
async def test_only_the_owner_may_reset_everyone_else_gets_403_and_nothing_changes(
    client_factory: Any, target: Target, key: str
) -> None:
    """chỉ vai trò chủ được đặt lại; vai trò khác bị 403 và mật khẩu không đổi"""
    caller = await client_factory(key)

    response = await _reset(caller, target.user_id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["error"]["details"] == {"permission": "admin.users"}
    assert await target.login_status(ACCOUNT_PASSWORD) == 200


async def test_it_cannot_be_called_without_signing_in(app: Any, target: Target) -> None:
    """chưa đăng nhập thì không gọi được"""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await _reset(http, target.user_id)
    assert response.status_code == 401
    assert await target.login_status(ACCOUNT_PASSWORD) == 200


async def test_an_unknown_id_is_a_404(client_factory: Any, world: SeedResult) -> None:
    """id không tồn tại trả 404 (không lộ gì về tài khoản)"""
    owner = await client_factory("owner")

    unknown = await _reset(owner, uuid4())

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"


async def test_the_owner_cannot_reset_their_own_password_through_this_route(
    client_factory: Any, world: SeedResult
) -> None:
    """không đặt lại cho chính mình qua route này (dùng POST /auth/password)"""
    owner = await client_factory("owner")

    response = await _reset(owner, world.users["owner"])

    assert response.status_code == 422
    assert "đổi mật khẩu" in response.json()["error"]["message"]
    assert (await owner.get("/api/v1/me")).status_code == 200


async def test_the_new_password_follows_the_same_8_character_floor(
    client_factory: Any, target: Target
) -> None:
    """mật khẩu mới dưới 8 ký tự bị chặn - cùng luật với đổi mật khẩu"""
    owner = await client_factory("owner")

    response = await _reset(owner, target.user_id, "ngan")

    assert response.status_code == 422
    assert "8 ký tự" in response.json()["error"]["message"]
    assert await target.login_status(ACCOUNT_PASSWORD) == 200

    assert (await _reset(owner, target.user_id, "12345678")).status_code == 204


async def test_a_malformed_user_id_is_a_validation_error(client_factory: Any) -> None:
    """id không phải UUID thì 422"""
    owner = await client_factory("owner")
    response = await owner.post(
        "/api/v1/admin/users/not-a-uuid/password", json={"new_password": NEW_PASSWORD}
    )
    assert response.status_code == 422


async def test_resets_are_rate_limited_per_owner(client_factory: Any, world: SeedResult) -> None:
    """giới hạn tốc độ: 5 lần mỗi phút cho mỗi chủ, lần thứ 6 bị 429"""
    owner = await client_factory("owner")
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        assert (await _reset(owner, uuid4())).status_code == 404

    blocked = await _reset(owner, uuid4())

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    auth.reset_login_rate_limit()
    assert (await _reset(owner, uuid4())).status_code == 404


async def test_a_refused_caller_does_not_spend_the_owners_rate_limit(
    client_factory: Any, target: Target
) -> None:
    """người không phải chủ bị 403 trước khi tính giới hạn tốc độ"""
    manager = await client_factory("manager")
    for _ in range(auth.LOGIN_MAX_ATTEMPTS + 2):
        assert (await _reset(manager, target.user_id)).status_code == 403


async def test_the_audit_row_names_who_reset_whom_and_never_holds_the_password(
    client_factory: Any,
    target: Target,
    world: SeedResult,
    admin: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """nhật ký audit ghi AI đặt lại cho AI, không ghi mật khẩu; log cũng không chứa mật khẩu"""
    owner = await client_factory("owner")
    request_id = f"reset-{uuid4().hex}"

    with caplog.at_level(logging.DEBUG):
        response = await owner.post(
            f"/api/v1/admin/users/{target.user_id}/password",
            headers={"X-Request-Id": request_id},
            json={"new_password": NEW_PASSWORD},
        )

    assert response.status_code == 204
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, actor_type, actor_user_id, actor_role, entity_type, entity_id, details::text "
                "FROM clinic.audit_log WHERE request_id = :r"
            ),
            {"r": request_id},
        ).all()
    assert [r.action for r in rows] == ["auth.reset_password"]
    row = rows[0]
    assert row.actor_type == "user"
    assert row.actor_user_id == world.users["owner"]
    assert row.actor_role == "owner"
    assert row.entity_type == "user_account"
    assert row.entity_id == str(target.user_id)
    assert NEW_PASSWORD not in (row.details or "")
    assert "argon2" not in (row.details or "")
    assert NEW_PASSWORD not in caplog.text


def test_the_reset_route_is_in_the_contract(app: Any) -> None:
    """hợp đồng OpenAPI có route, bảo vệ bằng cookie phiên và trả 204"""
    operation = app.openapi()["paths"]["/api/v1/admin/users/{user_id}/password"]["post"]
    assert operation["operationId"] == "admin_users_reset_user_password"
    assert "204" in operation["responses"]
    assert any("SessionCookie" in requirement for requirement in operation["security"])
