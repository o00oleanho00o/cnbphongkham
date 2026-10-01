# ported from: src/server/dashboard-password-store.test.ts
"""Test names are the snake_case English form of ``describe_it``; the original Vietnamese title is the docstring.

Password handling is security code, so the invariants are guarded: no clear text in the database, a changed
password kills the old sessions, and a corrupt stored value never falls back to anything weaker.
Needs ``PEMA_TEST_DATABASE_URL`` for the parts that touch the database.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from pema.api import dashboard_auth as auth
from pema.api import dashboard_password_store as store
from pema.api.clinic_testing import ACCOUNT_PASSWORD
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.models import UserAccount
from pema.clinic.rbac import passwords
from pema.core.db import ClinicDatabase
from pema_contracts.auth import LoginRequest
from pema_contracts.errors import DomainError, ErrorCode

CHEAP = {"time_cost": 1, "memory_cost": 1024}
NEW_PASSWORD = "a-brand-new-password-456"


# ---------------------------------------------------------------- hashing (pure)


def test_hash_is_not_clear_text_and_is_argon2id() -> None:
    """KHÔNG lưu bản rõ - đọc được file DB cũng không thấy mật khẩu"""
    stored = passwords.hash_password("very-secret-password-789", **CHEAP)
    assert "very-secret-password-789" not in stored
    assert stored.startswith("$argon2id$")


def test_every_hash_uses_a_different_salt_the_same_password_gives_two_records() -> None:
    """mỗi lần đặt dùng salt KHÁC nhau - cùng mật khẩu ra hai bản ghi khác nhau"""
    first = passwords.hash_password("same-password-twice", **CHEAP)
    second = passwords.hash_password("same-password-twice", **CHEAP)
    assert first != second
    assert passwords.verify_password(first, "same-password-twice")
    assert passwords.verify_password(second, "same-password-twice")


def test_a_corrupt_stored_value_never_matches_and_never_falls_back() -> None:
    """bản ghi hỏng KHÔNG rơi về giá trị khác - xoá/sửa liều không hạ được mật khẩu"""
    for corrupt in (None, "", "garbage-not-a-hash", "$argon2id$truncated"):
        assert passwords.verify_password(corrupt, "anything") is False
        assert passwords.verify_password(corrupt, "") is False


def test_verify_password_wrong_password_is_false() -> None:
    """mật khẩu sai thì không khớp"""
    stored = passwords.hash_password("right-password-123", **CHEAP)
    assert passwords.verify_password(stored, "right-password-123") is True
    assert passwords.verify_password(stored, "right-password-124") is False


def test_fingerprint_changes_with_the_hash_and_never_contains_it() -> None:
    """dấu vân tay đổi khi đổi mật khẩu và không chứa bản băm"""
    one = passwords.hash_password("first-password-1", **CHEAP)
    two = passwords.hash_password("first-password-1", **CHEAP)
    assert passwords.fingerprint(one) != passwords.fingerprint(two)
    assert one not in passwords.fingerprint(one)


def test_verify_user_password_for_an_unknown_user_is_false() -> None:
    """người dùng không tồn tại thì sai, nhưng vẫn tốn cùng một lần băm"""
    assert store.verify_user_password(None, "whatever-password") is False


# ---------------------------------------------------------------- with the database

pytestmark_db = pytest.mark.db


def _req(email: str, password: str) -> LoginRequest:
    return LoginRequest(clinic_slug="clinic-a", email=email, password=SecretStr(password))


@pytest.mark.db
async def test_password_in_the_database_is_a_hash_not_the_clear_text(
    db: ClinicDatabase, world_a: SeedResult, pg_url: str
) -> None:
    """KHÔNG lưu bản rõ trong DB"""
    engine = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            stored = conn.execute(
                text(
                    "SELECT password_hash FROM clinic.user_account WHERE clinic_id = :c AND email = 'owner@example.test'"
                ),
                {"c": world_a.clinic_id},
            ).scalar_one()
    finally:
        engine.dispose()
    assert ACCOUNT_PASSWORD not in stored
    assert stored.startswith("$argon2id$")


@pytest.mark.db
async def test_changing_the_password_kills_every_other_session_at_once_and_the_changer_keeps_working(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """đổi mật khẩu là mọi phiên cũ hết hiệu lực NGAY, phiên vừa đổi dùng tiếp được"""
    email = f"change.{uuid4().hex[:8]}@example.test"
    await _add_user(db, world_a, email)
    mine = await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.10")
    other_device = await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.11")
    me = await auth.verify_session_token(db, mine.token)
    assert me is not None
    assert await auth.verify_session_token(db, other_device.token) is not None

    await store.change_password(
        db,
        me.action_context(),
        current_password=ACCOUNT_PASSWORD,
        new_password=NEW_PASSWORD,
        keep_session_id=me.session_id,
    )

    assert await auth.verify_session_token(db, other_device.token) is None, (
        "another device must be signed out"
    )
    assert await auth.verify_session_token(db, mine.token) is not None, (
        "the session that changed it keeps working"
    )
    # the new password logs in, the old one does not
    await auth.login(db, _req(email, NEW_PASSWORD), client_ip="198.51.100.12")
    with pytest.raises(DomainError):
        await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.13")


@pytest.mark.db
async def test_a_borrowed_cookie_cannot_change_the_password_without_the_current_one(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """SAI mật khẩu hiện tại thì bị từ chối - cookie bị mượn không đổi được mật khẩu"""
    email = f"borrow.{uuid4().hex[:8]}@example.test"
    await _add_user(db, world_a, email)
    session = await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.20")
    me = await auth.verify_session_token(db, session.token)
    assert me is not None
    with pytest.raises(DomainError) as caught:
        await store.change_password(
            db,
            me.action_context(),
            current_password="guess",
            new_password=NEW_PASSWORD,
            keep_session_id=me.session_id,
        )
    assert caught.value.code is ErrorCode.UNAUTHENTICATED
    await auth.login(
        db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.21"
    )  # the old password still works


@pytest.mark.db
async def test_a_short_or_unchanged_new_password_is_refused(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """mật khẩu mới dưới 8 ký tự hoặc trùng mật khẩu cũ bị chặn"""
    email = f"short.{uuid4().hex[:8]}@example.test"
    await _add_user(db, world_a, email)
    session = await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.30")
    me = await auth.verify_session_token(db, session.token)
    assert me is not None
    for candidate in ("short", ACCOUNT_PASSWORD):
        with pytest.raises(DomainError) as caught:
            await store.change_password(
                db,
                me.action_context(),
                current_password=ACCOUNT_PASSWORD,
                new_password=candidate,
                keep_session_id=me.session_id,
            )
        assert caught.value.code is ErrorCode.VALIDATION_FAILED


@pytest.mark.db
async def test_an_owner_resets_another_account_and_every_session_of_it_ends(
    jwt_env: None, db: ClinicDatabase, world_a: SeedResult
) -> None:
    """chủ phòng khám đặt lại mật khẩu tài khoản khác, mọi phiên của tài khoản đó kết thúc"""
    email = f"reset.{uuid4().hex[:8]}@example.test"
    user_id = await _add_user(db, world_a, email)
    victim = await auth.login(db, _req(email, ACCOUNT_PASSWORD), client_ip="198.51.100.40")
    owner_session = await auth.login(
        db, _req("owner@example.test", ACCOUNT_PASSWORD), client_ip="198.51.100.41"
    )
    owner = await auth.verify_session_token(db, owner_session.token)
    assert owner is not None
    await store.set_password(db, owner.action_context(), user_id, NEW_PASSWORD)
    assert await auth.verify_session_token(db, victim.token) is None

    reception_session = await auth.login(
        db, _req("reception.lan@example.test", ACCOUNT_PASSWORD), client_ip="198.51.100.42"
    )
    reception = await auth.verify_session_token(db, reception_session.token)
    assert reception is not None
    with pytest.raises(DomainError) as caught:
        await store.set_password(db, reception.action_context(), user_id, NEW_PASSWORD)
    assert caught.value.code is ErrorCode.FORBIDDEN


async def _add_user(db: ClinicDatabase, world: SeedResult, email: str) -> UUID:
    from pema.clinic import audit

    user_id = uuid4()
    async with db.session(world.clinic_id) as session:
        session.add(
            UserAccount(
                id=user_id,
                clinic_id=world.clinic_id,
                email=email,
                display_name="Tài khoản thử (mẫu)",
                role="cs_staff",
                password_hash=passwords.hash_password(ACCOUNT_PASSWORD),
            )
        )
        await session.flush()
        from pema_contracts.actions import ActionContext
        from pema_contracts.roles import ActorType

        await audit.record(
            session,
            ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.SYSTEM),
            "test.add_user",
            "user_account",
            user_id,
        )
    return user_id
