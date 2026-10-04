# ported from: src/server/dashboard-password-route.test.ts
"""``POST /api/v1/auth/password``: a signed-in user changes their OWN password. Needs ``PEMA_TEST_DATABASE_URL``.

Test names are the snake_case English form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviations from the original: the route answers 204 and keeps the SAME cookie (the session row is
rebound to the new password fingerprint, so there is no new cookie to issue); a too-short new password is a
422 with the Vietnamese message (the original used 400); the original had one password for the dashboard, here
there are accounts, so "another device" means another session of the same user. The original file was kept
apart from the dashboard-server tests because the route shares the login rate-limit counter; here the counter
is reset by the fixtures for the same reason.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from pema.api import dashboard_auth as auth
from pema.api.clinic_testing import ACCOUNT_PASSWORD, add_staff_account, sign_in
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

NEW_PASSWORD = "mat-khau-moi-456"


class Account:
    """A throw-away staff account: these tests change its password, so they must not use a seeded one."""

    def __init__(self, app: Any, db: ClinicDatabase, world: SeedResult) -> None:
        self.app, self.db, self.world = app, db, world
        self.email = ""
        self.clients: list[httpx.AsyncClient] = []

    async def create(self) -> Account:
        self.email = await add_staff_account(self.db, self.world)
        return self

    async def client(self) -> httpx.AsyncClient:
        http = await sign_in(self.app, "clinic-a", self.email)
        self.clients.append(http)
        return http

    async def login(self, password: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(
                "/api/v1/auth/login",
                json={"clinic_slug": "clinic-a", "email": self.email, "password": password},
            )
        auth.reset_login_rate_limit()
        return response


@pytest_asyncio.fixture
async def account(app: Any, db: ClinicDatabase, world_a: SeedResult) -> AsyncIterator[Account]:
    made = await Account(app, db, world_a).create()
    yield made
    for http in made.clients:
        await http.aclose()


async def _change(client: httpx.AsyncClient, current: str, new: str) -> httpx.Response:
    return await client.post("/api/v1/auth/password", json={"current_password": current, "new_password": new})


async def test_change_works_with_the_right_current_password_and_login_uses_the_new_one(
    account: Account,
) -> None:
    """đổi được khi nhập đúng mật khẩu hiện tại, và đăng nhập lại bằng mật khẩu MỚI"""
    client = await account.client()

    response = await _change(client, ACCOUNT_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 204
    assert (await account.login(NEW_PASSWORD)).status_code == 200
    assert (await account.login(ACCOUNT_PASSWORD)).status_code == 401, "the old password must stop working"


async def test_a_wrong_current_password_is_refused_so_a_borrowed_cookie_cannot_change_it(
    account: Account,
) -> None:
    """SAI mật khẩu hiện tại thì bị từ chối - cookie bị mượn không đổi được mật khẩu"""
    client = await account.client()

    response = await _change(client, "doan-bua", NEW_PASSWORD)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert (await account.login(ACCOUNT_PASSWORD)).status_code == 200, "the old password must stay as it was"


async def test_it_cannot_be_called_without_signing_in(app: Any, world_a: SeedResult) -> None:
    """chưa đăng nhập thì không gọi được"""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await _change(http, ACCOUNT_PASSWORD, NEW_PASSWORD)
    assert response.status_code == 401


async def test_a_new_password_under_8_characters_is_refused(account: Account) -> None:
    """mật khẩu mới dưới 8 ký tự bị chặn - khớp ràng buộc của schema env"""
    client = await account.client()

    response = await _change(client, ACCOUNT_PASSWORD, "ngan")

    assert response.status_code == 422
    assert "8 ký tự" in response.json()["error"]["message"]


async def test_a_new_password_equal_to_the_old_one_is_refused(account: Account) -> None:
    """mật khẩu mới trùng mật khẩu cũ bị chặn"""
    client = await account.client()

    response = await _change(client, ACCOUNT_PASSWORD, ACCOUNT_PASSWORD)

    assert response.status_code == 422


async def test_the_session_that_changed_it_keeps_working(account: Account) -> None:
    """đổi xong người vừa đổi được dùng tiếp ngay (không bị đá ra khỏi trang)"""
    client = await account.client()

    await _change(client, ACCOUNT_PASSWORD, NEW_PASSWORD)

    assert (await client.get("/api/v1/me")).status_code == 200


async def test_sessions_on_another_device_are_revoked_after_the_change(account: Account) -> None:
    """phiên trên thiết bị KHÁC bị thu hồi sau khi đổi"""
    mine = await account.client()
    other_device = await account.client()
    assert (await other_device.get("/api/v1/me")).status_code == 200

    await _change(mine, ACCOUNT_PASSWORD, NEW_PASSWORD)

    assert (await other_device.get("/api/v1/me")).status_code == 401, (
        "another device that still gets in means a leaked account is not rescued by a password change"
    )


async def test_wrong_guesses_are_rate_limited_per_user_and_a_success_clears_the_count(
    account: Account,
) -> None:
    """đoán sai mật khẩu hiện tại bị chặn tốc độ theo người dùng (5 lần mỗi phút), thành công thì xóa bộ đếm"""
    client = await account.client()
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        assert (await _change(client, f"guess-{uuid4().hex[:6]}", NEW_PASSWORD)).status_code == 401

    blocked = await _change(client, ACCOUNT_PASSWORD, NEW_PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"

    auth.reset_login_rate_limit()
    assert (await _change(client, ACCOUNT_PASSWORD, NEW_PASSWORD)).status_code == 204
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        assert (await _change(client, "wrong-again", "x-another-new-1")).status_code == 401
