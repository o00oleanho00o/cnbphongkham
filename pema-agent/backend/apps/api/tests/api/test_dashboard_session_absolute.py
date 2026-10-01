"""SEC-24: a session has an ABSOLUTE lifetime counted from the login; ``refresh`` never goes past it.

New tests (no counterpart in zalo-agent, whose session was a rolling cookie too). Needs ``PEMA_TEST_DATABASE_URL``
except for the settings tests. The ceiling is set to ONE day in most tests so the clock only has to jump hours;
the default (7 days) has its own test. The clock is the action clock (``_common.use_clock``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api import dashboard_auth as auth
from pema.api.clinic_testing import (
    ACCOUNT_PASSWORD,
    API_INI,
    DEMO_NOW,
    JWT_SECRET,
    add_staff_account,
    sign_in,
)
from pema.clinic.actions import _common
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase
from pema_contracts.auth import LoginRequest
from pema_contracts.errors import DomainError, ErrorCode

TTL = timedelta(minutes=480)
"""The sliding (idle) lifetime: ``Settings.session_ttl_minutes``."""
NEW_PASSWORD = "mat-khau-moi-456"


@pytest.fixture
def one_day_ceiling(jwt_env: None) -> Iterator[None]:
    """``PEMA_SESSION_ABSOLUTE_DAYS=1`` for one test, and the cached settings restored afterwards."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PEMA_SESSION_ABSOLUTE_DAYS", "1")
        auth.get_auth_settings.cache_clear()
        yield
    auth.get_auth_settings.cache_clear()


def _at(moment: datetime) -> Any:
    return _common.use_clock(lambda: moment)


def _request(email: str, password: str = ACCOUNT_PASSWORD) -> LoginRequest:
    return LoginRequest(clinic_slug="clinic-a", email=email, password=SecretStr(password))


def _max_age(response: httpx.Response) -> int:
    match = re.search(r"Max-Age=(\d+)", response.headers["set-cookie"])
    assert match, response.headers["set-cookie"]
    return int(match.group(1))


async def _stored(db: ClinicDatabase, world: SeedResult, token: str) -> tuple[datetime, datetime, datetime]:
    """(created_at, expires_at, absolute_expires_at) of the session the token points at."""
    claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
    async with db.session(world.clinic_id) as session:
        row = (
            await session.execute(
                text(
                    "SELECT created_at, expires_at, absolute_expires_at FROM clinic.auth_session WHERE id = :i"
                ),
                {"i": claims["sid"]},
            )
        ).one()
    return row.created_at, row.expires_at, row.absolute_expires_at


# ---------------------------------------------------------------- settings (no database)


def test_the_default_ceiling_is_seven_days(jwt_env: None) -> None:
    """mặc định hạn tuyệt đối của phiên là 7 ngày"""
    assert auth.get_auth_settings().session_absolute_days == 7


@pytest.mark.parametrize("days", ["0", "-1", "31", "365"])
def test_a_ceiling_out_of_range_refuses_to_start(
    jwt_env: None, monkeypatch: pytest.MonkeyPatch, days: str
) -> None:
    """hạn tuyệt đối ngoài khoảng 1..30 ngày thì từ chối khởi động (không chạy với phiên vô hạn)"""
    monkeypatch.setenv("PEMA_SESSION_ABSOLUTE_DAYS", days)
    auth.get_auth_settings.cache_clear()
    try:
        with pytest.raises(ValidationError):
            auth.get_auth_settings()
    finally:
        monkeypatch.undo()
        auth.get_auth_settings.cache_clear()


def test_the_bounds_are_accepted(jwt_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """biên 1 và 30 ngày được chấp nhận"""
    try:
        for days in (1, 30):
            monkeypatch.setenv("PEMA_SESSION_ABSOLUTE_DAYS", str(days))
            auth.get_auth_settings.cache_clear()
            assert auth.get_auth_settings().session_absolute_days == days
    finally:
        monkeypatch.undo()
        auth.get_auth_settings.cache_clear()
        get_settings.cache_clear()


# ---------------------------------------------------------------- login


@pytest.mark.db
async def test_login_fixes_the_ceiling_at_seven_days_and_the_cookie_lives_the_idle_time(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """đăng nhập đặt mốc tuyệt đối = lúc đăng nhập + 7 ngày; cookie sống theo hạn trượt (8 giờ) vì nó ngắn hơn"""
    result = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.60")

    created, expires, absolute = await _stored(db, world_a, result.token)
    assert absolute == created + timedelta(days=7) == DEMO_NOW + timedelta(days=7)
    assert expires == DEMO_NOW + TTL
    assert result.max_age_seconds == int(TTL.total_seconds())
    assert result.user.absolute_expires_at == absolute


# ---------------------------------------------------------------- refresh


@pytest.mark.db
async def test_refresh_before_the_ceiling_works_and_slides_the_idle_expiry(
    one_day_ceiling: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """refresh trước mốc tuyệt đối thì được, hạn trượt dịch về sau"""
    result = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.61")
    user = await auth.verify_session_token(db, result.token)
    assert user is not None

    later = DEMO_NOW + timedelta(hours=7)
    with _at(later):
        renewed = await auth.refresh(db, user)
        assert await auth.verify_session_token(db, renewed.token) is not None

    assert renewed.user.expires_at == later + TTL
    assert renewed.user.expires_at < DEMO_NOW + timedelta(days=1)


@pytest.mark.db
async def test_refresh_never_pushes_the_expiry_past_the_ceiling_and_the_cookie_never_outlives_it(
    one_day_ceiling: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """refresh không bao giờ đẩy hạn quá mốc tuyệt đối; Max-Age của cookie và exp của JWT cũng không vượt mốc"""
    result = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.62")
    ceiling = DEMO_NOW + timedelta(days=1)
    user = await auth.verify_session_token(db, result.token)
    assert user is not None

    for hours in (7, 14, 21):  # each refresh lands inside the idle time of the one before
        with _at(DEMO_NOW + timedelta(hours=hours)):
            renewed = await auth.refresh(db, user)
            refreshed_user = await auth.verify_session_token(db, renewed.token)
        assert refreshed_user is not None
        user = refreshed_user

    # the last refresh, at +21h, wanted +29h: it is cut to the ceiling (+24h), i.e. 3 hours away
    assert renewed.user.expires_at == ceiling
    assert renewed.max_age_seconds == 3 * 3600
    claims = jwt.decode(renewed.token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert claims["exp"] == int(ceiling.timestamp())
    _, expires, absolute = await _stored(db, world_a, renewed.token)
    assert expires == absolute == ceiling

    # another refresh a minute before the ceiling is still cut to it
    with _at(ceiling - timedelta(minutes=1)):
        last = await auth.refresh(db, user)
    assert last.user.expires_at == ceiling
    assert last.max_age_seconds == 60


@pytest.mark.db
async def test_past_the_ceiling_the_session_is_dead_and_refresh_answers_401(
    one_day_ceiling: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """quá mốc tuyệt đối thì phiên chết, refresh trả 401 và phải đăng nhập lại"""
    result = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.63")
    user = await auth.verify_session_token(db, result.token)
    assert user is not None
    ceiling = DEMO_NOW + timedelta(days=1)

    for hours in (7, 14, 21):
        with _at(DEMO_NOW + timedelta(hours=hours)):
            renewed = await auth.refresh(db, user)
            user = (await auth.verify_session_token(db, renewed.token)) or user

    with _at(ceiling + timedelta(seconds=1)):
        assert await auth.verify_session_token(db, renewed.token) is None, "the cookie must stop working"
    with _at(ceiling):
        assert await auth.verify_session_token(db, renewed.token) is None, (
            "the ceiling itself is already dead"
        )

    # a request checked JUST before the ceiling but refreshed just after it (the race): still 401, nothing stored
    with _at(ceiling + timedelta(seconds=5)), pytest.raises(DomainError) as caught:
        await auth.refresh(db, user)
    assert caught.value.code is ErrorCode.UNAUTHENTICATED
    _, expires, absolute = await _stored(db, world_a, renewed.token)
    assert expires <= absolute == ceiling

    # signing in again works and starts a new ceiling
    with _at(ceiling + timedelta(hours=1)):
        again = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.64")
        assert await auth.verify_session_token(db, again.token) is not None
        _, _, new_absolute = await _stored(db, world_a, again.token)
    assert new_absolute == ceiling + timedelta(hours=1) + timedelta(days=1)


@pytest.mark.db
async def test_the_refresh_route_answers_401_past_the_ceiling_and_a_capped_max_age_before_it(
    one_day_ceiling: None, app: Any, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """POST /auth/refresh: 200 với Max-Age bị chặn bởi mốc tuyệt đối, sau mốc thì 401"""
    http = await sign_in(app, "clinic-a", "reception.lan@example.test")
    try:
        ceiling = DEMO_NOW + timedelta(days=1)
        for hours in (7, 14):
            with _at(DEMO_NOW + timedelta(hours=hours)):
                assert (await http.post("/api/v1/auth/refresh")).status_code == 200

        with _at(DEMO_NOW + timedelta(hours=21)):
            response = await http.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert _max_age(response) == 3 * 3600, "21h in, 3h to the ceiling: the cookie must not say 8h"
        assert response.json()["expires_at"].startswith(ceiling.isoformat()[:16])

        with _at(ceiling + timedelta(minutes=1)):
            expired = await http.post("/api/v1/auth/refresh")
            me = await http.get("/api/v1/me")
        assert expired.status_code == 401
        assert expired.json()["error"]["code"] == "unauthenticated"
        assert me.status_code == 401
    finally:
        await http.aclose()


@pytest.mark.db
async def test_a_short_ceiling_caps_even_the_first_cookie(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """hạn trượt dài hơn mốc tuyệt đối thì ngay cookie đầu tiên cũng bị chặn bởi mốc"""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PEMA_SESSION_TTL_MINUTES", str(3 * 24 * 60))
        patch.setenv("PEMA_SESSION_ABSOLUTE_DAYS", "1")
        get_settings.cache_clear()
        auth.get_auth_settings.cache_clear()
        try:
            result = await auth.login(db, _request("reception.lan@example.test"), client_ip="198.51.100.65")
        finally:
            patch.undo()
            get_settings.cache_clear()
            auth.get_auth_settings.cache_clear()
    assert result.max_age_seconds == 24 * 3600
    assert result.user.expires_at == result.user.absolute_expires_at == DEMO_NOW + timedelta(days=1)


# ---------------------------------------------------------------- password change keeps revoking


@pytest.mark.db
async def test_a_password_change_still_revokes_the_other_sessions_and_keeps_the_ceiling_of_this_one(
    one_day_ceiling: None, app: Any, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """đổi mật khẩu vẫn thu hồi các phiên khác; phiên vừa đổi giữ nguyên mốc tuyệt đối"""
    email = await add_staff_account(db, world_a)
    mine = await sign_in(app, "clinic-a", email)
    other = await sign_in(app, "clinic-a", email)
    try:
        before = await _stored(db, world_a, mine.cookies["pema_session"])
        assert (await other.get("/api/v1/me")).status_code == 200

        response = await mine.post(
            "/api/v1/auth/password",
            json={"current_password": ACCOUNT_PASSWORD, "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 204
        assert (await other.get("/api/v1/me")).status_code == 401
        assert (await mine.get("/api/v1/me")).status_code == 200
        after = await _stored(db, world_a, mine.cookies["pema_session"])
        assert after[2] == before[2], "changing the password must not move the ceiling"
        with _at(DEMO_NOW + timedelta(days=1, minutes=1)):
            assert (await mine.get("/api/v1/me")).status_code == 401, "the ceiling still applies after it"
    finally:
        await mine.aclose()
        await other.aclose()


@pytest.mark.db
async def test_login_prunes_sessions_past_their_ceiling(
    one_day_ceiling: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """đăng nhập dọn phiên đã quá mốc tuyệt đối"""
    email = await add_staff_account(db, world_a)
    old = await auth.login(db, _request(email), client_ip="198.51.100.66")
    with _at(DEMO_NOW + timedelta(days=2)):
        await auth.login(db, _request(email), client_ip="198.51.100.67")
        async with db.session(world_a.clinic_id) as session:
            claims = jwt.decode(old.token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
            left = await session.scalar(
                text("SELECT count(*) FROM clinic.auth_session WHERE id = :i"), {"i": claims["sid"]}
            )
    assert left == 0


# ---------------------------------------------------------------- migration backfill


@pytest.mark.db
async def test_the_migration_backfills_existing_sessions_with_created_at_plus_seven_days(
    world_a: SeedResult, admin: Engine
) -> None:
    """migration thêm cột và backfill phiên đang có = created_at + 7 ngày; cột NOT NULL"""
    config = Config(str(API_INI))
    session_id = uuid4()
    command.downgrade(config, "g_0006_definer_search_path")
    try:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.auth_session "
                    "(id, clinic_id, user_id, password_fingerprint, created_at, expires_at) "
                    "VALUES (:i, :c, :u, 'fp', '2026-09-01T00:00:00+00', '2026-09-01T08:00:00+00')"
                ),
                {"i": session_id, "c": world_a.clinic_id, "u": world_a.users["reception.lan"]},
            )
    finally:
        command.upgrade(config, "heads")
    with admin.begin() as conn:
        absolute = conn.execute(
            text("SELECT absolute_expires_at FROM clinic.auth_session WHERE id = :i"), {"i": session_id}
        ).scalar_one()
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'clinic' "
                "AND table_name = 'auth_session' AND column_name = 'absolute_expires_at'"
            )
        ).scalar_one()
        conn.execute(text("DELETE FROM clinic.auth_session WHERE id = :i"), {"i": session_id})
    assert absolute.isoformat() == "2026-09-08T00:00:00+00:00"
    assert nullable == "NO"
