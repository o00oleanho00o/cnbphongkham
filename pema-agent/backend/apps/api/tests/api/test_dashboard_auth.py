# ported from: src/server/dashboard-auth.test.ts
"""Test names are the snake_case English form of ``describe_it``; the original Vietnamese title is the docstring.

The original tested one password and a ``<id>.<secret>`` token; here the same invariants are proved for
per-user passwords and a signed JWT whose session row can be revoked. Needs ``PEMA_TEST_DATABASE_URL``.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr

from pema.api import dashboard_auth as auth
from pema.api import dashboard_session_store as sessions
from pema.api.clinic_testing import ACCOUNT_PASSWORD, DEMO_NOW, JWT_SECRET
from pema.clinic.actions import _common
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.auth import LoginRequest
from pema_contracts.errors import DomainError, ErrorCode

pytestmark = pytest.mark.db


def _request(email: str = "doctor.mai@example.test", password: str = ACCOUNT_PASSWORD) -> LoginRequest:
    return LoginRequest(email=email, password=SecretStr(password))


async def _login(db: ClinicDatabase, ip: str | None = None, **kwargs: str) -> auth.LoginResult:
    return await auth.login(db, _request(**kwargs), client_ip=ip or f"198.51.100.{uuid4().int % 250}")


# ---------------------------------------------------------------- password


async def test_login_correct_password_passes_wrong_and_empty_fail(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """password đúng pass, sai fail, rỗng fail"""
    assert (await _login(db)).user.display_name.startswith("BS. Mai")
    for bad in ("wrong-password", ""):
        with pytest.raises(DomainError) as caught:
            await _login(db, password=bad)
        assert caught.value.code is ErrorCode.UNAUTHENTICATED


async def test_login_unknown_email_and_wrong_password_give_the_same_401(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """mọi lỗi đăng nhập là cùng một 401, không lộ tài khoản có tồn tại hay không"""
    attempts = [
        _request(email="nobody@example.test"),
        _request(password="not-the-password"),
    ]
    messages: set[str] = set()
    for body in attempts:
        with pytest.raises(DomainError) as caught:
            await auth.login(db, body, client_ip=f"198.51.100.{uuid4().int % 250}")
        assert caught.value.code is ErrorCode.UNAUTHENTICATED
        messages.add(caught.value.message)
    assert len(messages) == 1


async def test_login_takes_only_email_and_password_and_the_clinic_is_the_installation_clinic(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """đăng nhập chỉ cần email và mật khẩu, phòng khám là phòng khám duy nhất của bản cài đặt"""
    assert set(LoginRequest.model_fields) == {"email", "password"}
    result = await _login(db)
    assert result.user.clinic_id == world.clinic_id
    assert result.user.summary().clinic_name


# ---------------------------------------------------------------- token


async def test_the_token_carries_no_clinic_and_a_token_of_an_older_version_with_one_still_verifies(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """token không mang mã phòng khám; token cũ còn claim cid vẫn đọc được (phiên đang mở không bị mất)"""
    result = await _login(db)
    claims = jwt.decode(result.token, options={"verify_signature": False})
    assert "cid" not in claims
    legacy = jwt.encode({**claims, "cid": str(world.clinic_id)}, JWT_SECRET, algorithm="HS256")
    assert await auth.verify_session_token(db, legacy) is not None


async def test_token_just_created_verifies_and_forged_tokens_do_not(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """token vừa tạo verify được, token giả mạo thì không"""
    result = await _login(db)
    assert (await auth.verify_session_token(db, result.token)) is not None

    assert await auth.verify_session_token(db, None) is None
    assert await auth.verify_session_token(db, "not-a-token") is None
    assert await auth.verify_session_token(db, "missing.") is None

    # a real session id and user but a forged signature
    claims = jwt.decode(result.token, options={"verify_signature": False})
    forged = jwt.encode(claims, "another-secret-another-secret-another-1", algorithm="HS256")
    assert await auth.verify_session_token(db, forged) is None
    # signed with the right key but for a session that does not exist
    unknown = jwt.encode({**claims, "sid": str(uuid4())}, JWT_SECRET, algorithm="HS256")
    assert await auth.verify_session_token(db, unknown) is None
    # the algorithm "none" is never accepted
    unsigned = jwt.encode(claims, key="", algorithm="none")
    assert await auth.verify_session_token(db, unsigned) is None


async def test_expired_token_is_rejected(jwt_env: None, db: ClinicDatabase, world: SeedResult) -> None:
    """token hết hạn bị từ chối"""
    result = await _login(db)
    later = DEMO_NOW + timedelta(hours=9)  # the session lives 480 minutes
    with _common.use_clock(lambda: later):
        assert await auth.verify_session_token(db, result.token) is None


async def test_logout_revokes_for_real_the_old_token_cannot_be_used_again(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """logout thu hồi thật: token cũ không dùng lại được"""
    result = await _login(db)
    user = await auth.verify_session_token(db, result.token)
    assert user is not None
    await auth.revoke_session(db, user)
    assert await auth.verify_session_token(db, result.token) is None


async def test_role_and_deactivation_are_read_from_the_user_row_at_request_time(
    jwt_env: None, db: ClinicDatabase, world: SeedResult, pg_url: str
) -> None:
    """vai trò và trạng thái hoạt động lấy từ bản ghi người dùng mỗi request, không tin token"""
    from sqlalchemy import create_engine, text

    result = await _login(db, email="cs.thu@example.test")
    admin = create_engine(pg_url)
    try:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE clinic.user_account SET role = 'reception' WHERE email = 'cs.thu@example.test' AND clinic_id = :c"
                ),
                {"c": world.clinic_id},
            )
        user = await auth.verify_session_token(db, result.token)
        assert user is not None
        assert user.role.value == "reception"
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE clinic.user_account SET active = false WHERE email = 'cs.thu@example.test' AND clinic_id = :c"
                ),
                {"c": world.clinic_id},
            )
        assert await auth.verify_session_token(db, result.token) is None
    finally:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE clinic.user_account SET role = 'cs_staff', active = true WHERE email = 'cs.thu@example.test' AND clinic_id = :c"
                ),
                {"c": world.clinic_id},
            )
        admin.dispose()


async def test_login_prunes_expired_sessions_so_the_table_does_not_grow_forever(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """login mới dọn phiên hết hạn, bảng không phình vô hạn"""
    await _login(db, email="reception.lan@example.test")
    async with db.session() as session:
        before = await sessions.count_sessions(session)
    later = DEMO_NOW + timedelta(hours=9)
    with _common.use_clock(lambda: later):
        await _login(db, email="reception.lan@example.test")
    async with db.session() as session:
        after = await sessions.count_sessions(session)
    assert after <= before, "the expired session of the same user must be pruned at login"


async def test_a_missing_jwt_secret_fails_closed_no_login_without_a_key(
    monkeypatch: pytest.MonkeyPatch, db: ClinicDatabase, world: SeedResult
) -> None:
    """không có khóa thì không đăng nhập (không bao giờ có khóa mặc định)"""
    from pema.config.env import get_settings

    monkeypatch.delenv("PEMA_JWT_SECRET", raising=False)
    monkeypatch.setenv("PEMA_JWT_SECRET", "too-short")
    get_settings.cache_clear()
    try:
        with pytest.raises(DomainError) as caught:
            await _login(db)
        assert caught.value.code is ErrorCode.INTERNAL
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------- rate limit (pure)


def test_rate_limit_five_per_minute_window_resets_and_success_clears_the_count() -> None:
    """rate limit: 5 lần/phút, cửa sổ trôi qua thì reset, login ok thì xóa đếm"""
    auth.reset_login_rate_limit()
    now = 1_000_000.0
    for attempt in range(5):
        assert auth.allow_login_attempt("1.2.3.4", now) is True, f"attempt {attempt + 1} must be allowed"
    assert auth.allow_login_attempt("1.2.3.4", now) is False, "the 6th must be blocked"
    # another address is not affected
    assert auth.allow_login_attempt("5.6.7.8", now) is True
    # after the 60 s window it may try again
    assert auth.allow_login_attempt("1.2.3.4", now + 61_000) is True
    # a cleared count resets at once
    for _ in range(5):
        auth.allow_login_attempt("9.9.9.9", now)
    auth.clear_login_attempts("9.9.9.9")
    assert auth.allow_login_attempt("9.9.9.9", now) is True
    auth.reset_login_rate_limit()


def test_expired_rate_limit_buckets_are_pruned_the_map_does_not_grow_with_every_ip_ever_seen() -> None:
    """bucket rate-limit hết hạn bị dọn, Map không phình theo số IP từng gặp"""
    auth.reset_login_rate_limit()
    now = 1_000_000.0
    for i in range(600):
        auth.allow_login_attempt(f"10.0.{i // 256}.{i % 256}", now)
    peak = auth.login_attempt_bucket_count()
    assert peak > auth.PRUNE_THRESHOLD, "must exceed the threshold before pruning"
    # the window of every old bucket has passed: the next call sweeps them
    auth.allow_login_attempt("8.8.8.8", now + 61_000)
    assert auth.login_attempt_bucket_count() < peak, "expired buckets must be pruned"
    auth.reset_login_rate_limit()


async def test_login_is_rate_limited_per_email_even_from_many_addresses(
    jwt_env: None, db: ClinicDatabase, world: SeedResult
) -> None:
    """một tài khoản không bị dò mật khẩu dù đổi nhiều địa chỉ IP (khóa theo email, không theo phòng khám)"""
    assert auth.allow_login_attempt("acct:someone@example.test") is True
    auth.reset_login_rate_limit()
    for attempt in range(auth.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(DomainError) as caught:
            await auth.login(db, _request(password="guess-guess"), client_ip=f"192.0.2.{attempt}")
        assert caught.value.code is ErrorCode.UNAUTHENTICATED
    with pytest.raises(DomainError) as limited:
        await auth.login(db, _request(password="guess-guess"), client_ip="192.0.2.200")
    assert limited.value.code is ErrorCode.RATE_LIMITED
