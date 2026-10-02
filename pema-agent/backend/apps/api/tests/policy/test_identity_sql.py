"""The SQL side of the policy on a clean Postgres: identity link functions, grants, admin service.

Skipped without ``PEMA_TEST_DATABASE_URL`` (same convention as ``tests/test_database.py``; use a THROWAWAY
database, the fixture drops every Pema schema and re-runs the alembic history). Covers revision
``p0001_identity_link`` as the two runtime roles use it: ``agent_worker`` (functions only) and ``be_app``
(tables). Single tenant: the database holds ONE clinic. All data is synthetic.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic
from pema.policy.gateway import LinkOutcome, SqlPolicyGateway
from pema.policy.identity import link_code_hash, phone_hash
from pema.policy.identity_admin import PolicyAdminService
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.admin_agent import AccountPolicyUpdate, IdentityConfirm
from pema_contracts.channel import ChannelKind
from pema_contracts.clinic_actions import IdentityLinkStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.roles import ActorType, Role
from pema_contracts.testing import InMemoryAccountStore, fake_account_config

API_DIR = Path(__file__).resolve().parents[2]
API_INI = API_DIR / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
CH = ChannelKind.ZALO_BOT

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against", allow_module_level=True)


def _url(role: str, password: str) -> str:
    assert ADMIN_URL is not None
    return make_url(ADMIN_URL).set(username=role, password=password).render_as_string(hide_password=False)


@asynccontextmanager
async def _db(role: str, password: str) -> AsyncGenerator[ClinicDatabase]:
    db = ClinicDatabase(_url(role, password))
    try:
        yield db
    finally:
        await db.dispose()


def worker_db() -> AbstractAsyncContextManager[ClinicDatabase]:
    return _db("agent_worker", WORKER_PASSWORD)


def be_db() -> AbstractAsyncContextManager[ClinicDatabase]:
    return _db("be_app", BE_PASSWORD)


class World:
    """The one clinic. It has: an owner, a reception user, patients P025 (phone), P026 and P027 (the same
    family phone), P028 (opted out of marketing, a marketing template, consents)."""

    def __init__(self, clinic_id: uuid.UUID) -> None:
        self.clinic_a = clinic_id
        self.owner = uuid.uuid4()
        self.reception = uuid.uuid4()
        self.p025 = uuid.uuid4()
        self.p026 = uuid.uuid4()
        self.p027 = uuid.uuid4()
        self.p028 = uuid.uuid4()


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    assert ADMIN_URL is not None
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    _reset(engine)
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def world(admin_engine: Engine) -> World:
    with admin_engine.begin() as conn:
        w = World(ensure_test_clinic(conn))
        for user_id, role, email in (
            (w.owner, "owner", "owner@example.invalid"),
            (w.reception, "reception", "reception@example.invalid"),
        ):
            conn.execute(
                text(
                    "INSERT INTO clinic.user_account (id, clinic_id, email, display_name, role) "
                    "VALUES (:id, :c, :email, 'Synthetic Staff', :role)"
                ),
                {"id": user_id, "c": w.clinic_a, "email": email, "role": role},
            )
        patients = [
            (w.p025, w.clinic_a, "P025", "Nguyen Thi Hoa (synthetic)", "+84 901 234 567", False),
            (w.p026, w.clinic_a, "P026", "Synthetic Parent", "0912 345 678", False),
            (w.p027, w.clinic_a, "P027", "Synthetic Child", "0912-345-678", False),
            (w.p028, w.clinic_a, "P028", "Synthetic Optout", "0987654321", True),
        ]
        for pid, clinic_id, code, name, phone, opt_out in patients:
            conn.execute(
                text(
                    "INSERT INTO clinic.patient (id, clinic_id, code, full_name, phone, marketing_opt_out) "
                    "VALUES (:id, :c, :code, :name, :phone, :opt)"
                ),
                {"id": pid, "c": clinic_id, "code": code, "name": name, "phone": phone, "opt": opt_out},
            )
        for kind, granted in (("messaging", True), ("marketing", False)):
            conn.execute(
                text(
                    "INSERT INTO clinic.consent (clinic_id, patient_id, kind, granted, granted_at) "
                    "VALUES (:c, :p, :k, :g, now())"
                ),
                {"c": w.clinic_a, "p": w.p028, "k": kind, "g": granted},
            )
        conn.execute(
            text(
                "INSERT INTO clinic.message_template (clinic_id, template_key, title, body, marketing, approved_at) "
                "VALUES (:c, 'promo_laser', 'Khuyến mãi', 'Nội dung giả', true, now()), "
                "(:c, 'followup_d1', 'Nhắc D1', 'Nội dung giả', false, now())"
            ),
            {"c": w.clinic_a},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.message_template (clinic_id, template_key, title, body, marketing, active, approved_at) "
                "VALUES (:c, 'retired', 'Cũ', 'Nội dung giả', false, false, NULL)"
            ),
            {"c": w.clinic_a},
        )
    return w


def _identity_row(engine: Engine, clinic_id: uuid.UUID, uid: str) -> dict[str, object] | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT verification_status, patient_id, verified_by FROM clinic.channel_identity "
                "WHERE clinic_id = :c AND channel = 'zalo_bot' AND external_user_id = :u"
            ),
            {"c": clinic_id, "u": uid},
        ).first()
    return None if row is None else {"status": row[0], "patient_id": row[1], "verified_by": row[2]}


def _staff(world: World, user: uuid.UUID, role: Role) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_a,
        actor_type=ActorType.USER,
        actor_user_id=user,
        actor_role=role,
        source=ActionSource.UI,
    )


# ------------------------------------------------------------------------------------ phone
@pytest.mark.parametrize(
    "stored",
    [
        "+84 901 234 567",
        "0901234567",
        "090 123 4567",
        "+84901234567",
        "84901234567",
        "0084901234567",
        "(090) 123-4567",
    ],
)
async def test_sql_normalisation_agrees_with_python_for_every_stored_format(
    admin_engine: Engine, stored: str
) -> None:
    """SQL norm_phone và Python normalize_vn_phone cho cùng kết quả với mọi cách lưu SĐT"""
    expected = phone_hash("0901234567")
    with admin_engine.begin() as conn:
        got = conn.execute(
            text("SELECT encode(sha256(convert_to(clinic_agent.norm_phone(:p), 'UTF8')), 'hex')"),
            {"p": stored},
        ).scalar_one()
    assert got == expected


async def test_phone_hash_creates_a_pending_candidate_and_never_verifies(
    admin_engine: Engine, world: World
) -> None:
    """băm SĐT khớp một hồ sơ: liên kết chờ xác nhận (pending), không bao giờ verified"""
    digest = phone_hash("0901234567")
    assert digest is not None
    async with worker_db() as db:
        result = await SqlPolicyGateway(db).link_by_phone_hash(world.clinic_a, CH, "uid-phone-1", digest)
    assert result.outcome is LinkOutcome.CANDIDATE_CREATED
    assert result.patient_id == world.p025
    assert result.patient_code == "P025"
    row = _identity_row(admin_engine, world.clinic_a, "uid-phone-1")
    assert row is not None
    assert (row["status"], row["patient_id"], row["verified_by"]) == ("pending", world.p025, None)


async def test_a_family_phone_is_ambiguous_and_links_nobody(admin_engine: Engine, world: World) -> None:
    """SĐT của hai hồ sơ (cha mẹ/con): ambiguous, không gán cho ai"""
    digest = phone_hash("0912345678")
    assert digest is not None
    async with worker_db() as db:
        result = await SqlPolicyGateway(db).link_by_phone_hash(world.clinic_a, CH, "uid-family", digest)
    assert result.outcome is LinkOutcome.AMBIGUOUS
    row = _identity_row(admin_engine, world.clinic_a, "uid-family")
    assert row is not None
    assert (row["status"], row["patient_id"]) == ("unlinked", None)


async def test_unknown_phone_is_no_match_and_five_failures_rate_limit(world: World) -> None:
    """SĐT lạ: no_match; sau 5 lần sai trong một giờ thì rate_limited, kể cả khi lần sau đúng"""
    wrong = phone_hash("0911111111")
    right = phone_hash("0901234567")
    assert wrong is not None
    assert right is not None
    async with worker_db() as db:
        gw = SqlPolicyGateway(db)
        outcomes = [
            (await gw.link_by_phone_hash(world.clinic_a, CH, "uid-brute", wrong)).outcome for _ in range(5)
        ]
        assert outcomes == [LinkOutcome.NO_MATCH] * 5
        blocked = await gw.link_by_phone_hash(world.clinic_a, CH, "uid-brute", right)
        other_user = await gw.link_by_phone_hash(world.clinic_a, CH, "uid-brute-2", right)
    assert blocked.outcome is LinkOutcome.RATE_LIMITED
    assert other_user.outcome is LinkOutcome.CANDIDATE_CREATED


async def test_a_staff_rejected_identity_is_not_relinked_by_phone(admin_engine: Engine, world: World) -> None:
    """liên kết bị nhân viên từ chối thì SĐT không tự liên kết lại"""
    digest = phone_hash("0901234567")
    assert digest is not None
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, verification_status) "
                "VALUES (:c, 'zalo_bot', 'uid-rejected', 'rejected')"
            ),
            {"c": world.clinic_a},
        )
    async with worker_db() as db:
        result = await SqlPolicyGateway(db).link_by_phone_hash(world.clinic_a, CH, "uid-rejected", digest)
    assert result.outcome is LinkOutcome.REJECTED_BY_STAFF


# ------------------------------------------------------------------------------------- codes
async def test_reception_code_round_trip_verifies_with_the_issuing_staff_member(
    admin_engine: Engine, world: World
) -> None:
    """lễ tân phát mã -> khách nhập -> verified, verified_by = người phát mã, mã chỉ dùng một lần"""
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        issued = await service.issue_link_code(_staff(world, world.reception, Role.RECEPTION), world.p025)
    digest = link_code_hash(issued.code)
    assert digest is not None
    async with worker_db() as db:
        gw = SqlPolicyGateway(db)
        first = await gw.redeem_link_code(world.clinic_a, CH, "uid-code-1", digest)
        again = await gw.redeem_link_code(world.clinic_a, CH, "uid-code-2", digest)
    assert first.outcome is LinkOutcome.VERIFIED
    assert (first.patient_id, first.patient_code) == (world.p025, "P025")
    assert again.outcome is LinkOutcome.INVALID_CODE
    row = _identity_row(admin_engine, world.clinic_a, "uid-code-1")
    assert row is not None
    assert (row["status"], row["patient_id"], row["verified_by"]) == ("verified", world.p025, world.reception)


async def test_the_database_stores_only_the_hash_of_a_code(admin_engine: Engine, world: World) -> None:
    """DB chỉ lưu băm của mã, không lưu mã thật"""
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        issued = await service.issue_link_code(_staff(world, world.owner, Role.OWNER), world.p025)
    plain = issued.code.replace("-", "")
    with admin_engine.begin() as conn:
        stored = (
            conn.execute(
                text("SELECT code_hash FROM clinic.identity_link_code WHERE clinic_id = :c"),
                {"c": world.clinic_a},
            )
            .scalars()
            .all()
        )
        dump = conn.execute(
            text("SELECT string_agg(row_to_json(t)::text, ' ') FROM clinic.identity_link_code t")
        ).scalar_one()
    assert link_code_hash(issued.code) in stored
    assert plain not in dump
    assert issued.code not in dump


async def test_expired_and_unknown_codes_are_refused(admin_engine: Engine, world: World) -> None:
    """mã hết hạn và mã lạ đều bị từ chối"""
    expired = link_code_hash("EXPDAAAA")
    unknown = link_code_hash("UNKNCCCC")
    assert expired is not None
    assert unknown is not None
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.identity_link_code (clinic_id, patient_id, code_hash, issued_by, expires_at) "
                "VALUES (:c, :p, :h, :u, now() - interval '1 minute')"
            ),
            {"c": world.clinic_a, "p": world.p025, "h": expired, "u": world.owner},
        )
    async with worker_db() as db:
        gw = SqlPolicyGateway(db)
        assert (
            await gw.redeem_link_code(world.clinic_a, CH, "uid-x1", expired)
        ).outcome is LinkOutcome.EXPIRED_CODE
        assert (
            await gw.redeem_link_code(world.clinic_a, CH, "uid-x3", unknown)
        ).outcome is LinkOutcome.INVALID_CODE


async def test_a_valid_code_overrides_an_earlier_rejection_and_refuses_a_second_patient(
    admin_engine: Engine, world: World
) -> None:
    """mã hợp lệ do nhân viên phát được phép thay một từ chối cũ; đã xác minh cho người khác thì conflict"""
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        staff = _staff(world, world.owner, Role.OWNER)
        code_a = await service.issue_link_code(staff, world.p025)
        code_b = await service.issue_link_code(staff, world.p026)
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, verification_status) "
                "VALUES (:c, 'zalo_bot', 'uid-override', 'rejected')"
            ),
            {"c": world.clinic_a},
        )
    async with worker_db() as db:
        gw = SqlPolicyGateway(db)
        first = await gw.redeem_link_code(
            world.clinic_a, CH, "uid-override", link_code_hash(code_a.code) or ""
        )
        second = await gw.redeem_link_code(
            world.clinic_a, CH, "uid-override", link_code_hash(code_b.code) or ""
        )
    assert first.outcome is LinkOutcome.VERIFIED
    assert second.outcome is LinkOutcome.CONFLICT


# ------------------------------------------------------------------------- grants and context
async def test_worker_cannot_read_identity_tables_or_call_the_helpers(world: World) -> None:
    """agent_worker không đọc được bảng mã/lần thử và không gọi được hàm phụ trợ"""
    async with worker_db() as db:
        for statement in (
            "SELECT * FROM clinic.identity_link_code",
            "SELECT * FROM clinic.identity_link_attempt",
            "SELECT clinic_agent.norm_phone('0901234567')",
            "SELECT clinic_agent.link_attempts_exceeded(gen_random_uuid(), 'zalo_bot', 'x')",
        ):
            with pytest.raises((ProgrammingError, DBAPIError)):
                async with db.session() as session:
                    await session.execute(text(statement))


async def test_functions_reject_a_hash_that_is_not_a_sha256(world: World) -> None:
    """hàm từ chối chuỗi không phải băm SHA-256 (không nhận SĐT/mã thô)"""
    async with worker_db() as db:
        for statement in (
            "SELECT * FROM clinic_agent.link_identity_by_phone_hash('zalo_bot', 'u', '0901234567')",
            "SELECT * FROM clinic_agent.redeem_identity_code('zalo_bot', 'u', 'K7QM4XNR')",
        ):
            with pytest.raises(DBAPIError):
                async with db.session() as session:
                    await session.execute(text(statement))


async def test_attempt_log_is_append_only_for_the_api_role(world: World) -> None:
    """be_app đọc được nhật ký thử liên kết nhưng không sửa/xóa được"""
    async with be_db() as db:
        async with db.session() as session:
            count = (
                await session.execute(text("SELECT count(*) FROM clinic.identity_link_attempt"))
            ).scalar_one()
        assert count > 0
        for statement in (
            "UPDATE clinic.identity_link_attempt SET succeeded = true",
            "DELETE FROM clinic.identity_link_attempt",
        ):
            with pytest.raises((ProgrammingError, DBAPIError)):
                async with db.session() as session:
                    await session.execute(text(statement))


async def test_audit_rows_exist_and_hold_no_phone_hash_or_code(admin_engine: Engine, world: World) -> None:
    """mỗi liên kết ghi audit (actor agent); chi tiết không chứa SĐT, băm hay mã"""
    with admin_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_type, action, details::text FROM clinic.audit_log "
                "WHERE clinic_id = :c AND action LIKE 'identity.%'"
            ),
            {"c": world.clinic_a},
        ).all()
    actions = {r[1] for r in rows}
    assert {"identity.link_candidate", "identity.verified_by_code", "identity.code_issued"} <= actions
    for actor_type, action, details in rows:
        if action in ("identity.link_candidate", "identity.verified_by_code"):
            assert actor_type == "agent"
        assert "0901234567" not in details
        assert phone_hash("0901234567") not in details


# --------------------------------------------------------------------------- read helpers
async def test_gateway_reads_flags_and_approved_templates_through_views(world: World) -> None:
    """cổng đọc cờ bệnh nhân và template đã duyệt qua view clinic_agent"""
    async with worker_db() as db:
        gw = SqlPolicyGateway(db)
        optout = await gw.patient_flags(world.clinic_a, world.p028)
        plain = await gw.patient_flags(world.clinic_a, world.p025)
        unknown_patient = await gw.patient_flags(world.clinic_a, uuid.uuid4())
        promo = await gw.approved_template(world.clinic_a, "promo_laser")
        followup = await gw.approved_template(world.clinic_a, "followup_d1")
        retired = await gw.approved_template(world.clinic_a, "retired")
    assert optout is not None
    assert optout.marketing_opt_out is True
    assert (optout.consent_messaging, optout.consent_marketing) == (True, False)
    assert plain is not None
    assert plain.marketing_opt_out is False
    assert unknown_patient is None
    assert promo is not None
    assert promo.marketing is True
    assert followup is not None
    assert followup.marketing is False
    assert retired is None


# --------------------------------------------------------------------------- admin service
async def test_confirm_lists_pending_links_and_verifies_with_the_staff_member(
    admin_engine: Engine, world: World
) -> None:
    """nhân viên xem danh sách chờ rồi xác nhận: verified, ghi người xác nhận và audit"""
    digest = phone_hash("0901234567")
    assert digest is not None
    async with worker_db() as db:
        await SqlPolicyGateway(db).link_by_phone_hash(world.clinic_a, CH, "uid-confirm", digest)
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        staff = _staff(world, world.owner, Role.OWNER)
        pending = await service.list_pending(staff)
        assert "uid-confirm" in {link.external_user_id for link in pending}
        link = next(p for p in pending if p.external_user_id == "uid-confirm")
        assert (link.status, link.patient_code) == (IdentityLinkStatus.PENDING, "P025")
        confirmed = await service.confirm(
            staff, IdentityConfirm(channel=CH, external_user_id="uid-confirm", patient_id=world.p025)
        )
        again = None
        with pytest.raises(DomainError) as exc:
            again = await service.confirm(
                staff, IdentityConfirm(channel=CH, external_user_id="uid-confirm", patient_id=world.p025)
            )
        assert again is None
        assert exc.value.code is ErrorCode.INVALID_STATE
    assert confirmed.status is IdentityLinkStatus.VERIFIED
    assert confirmed.patient_code == "P025"
    row = _identity_row(admin_engine, world.clinic_a, "uid-confirm")
    assert row is not None
    assert (row["status"], row["verified_by"]) == ("verified", world.owner)
    with admin_engine.begin() as conn:
        audited = conn.execute(
            text(
                "SELECT count(*) FROM clinic.audit_log WHERE action = 'identity.confirm' AND actor_user_id = :u"
            ),
            {"u": world.owner},
        ).scalar_one()
    assert audited >= 1


async def test_reject_clears_the_candidate(admin_engine: Engine, world: World) -> None:
    """từ chối: bỏ ứng viên, trạng thái rejected, verified_by ghi người từ chối"""
    digest = phone_hash("0901234567")
    assert digest is not None
    async with worker_db() as db:
        await SqlPolicyGateway(db).link_by_phone_hash(world.clinic_a, CH, "uid-reject", digest)
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        out = await service.confirm(
            _staff(world, world.owner, Role.OWNER),
            IdentityConfirm(channel=CH, external_user_id="uid-reject", patient_id=world.p025, reject=True),
        )
    assert out.status is IdentityLinkStatus.REJECTED
    row = _identity_row(admin_engine, world.clinic_a, "uid-reject")
    assert row is not None
    assert (row["status"], row["patient_id"]) == ("rejected", None)


async def test_admin_actions_are_deny_by_default(world: World) -> None:
    """lễ tân/bác sĩ không xác nhận được liên kết; tác nhân agent không làm được gì ở API quản trị"""
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        body = IdentityConfirm(channel=CH, external_user_id="uid-confirm", patient_id=world.p025)
        for role in (Role.RECEPTION, Role.DOCTOR, Role.CS_STAFF, Role.PATIENT):
            with pytest.raises(DomainError) as exc:
                await service.confirm(_staff(world, world.reception, role), body)
            assert exc.value.code is ErrorCode.FORBIDDEN
        agent = ActionContext(clinic_id=world.clinic_a, actor_type=ActorType.AGENT, source=ActionSource.AGENT)
        with pytest.raises(DomainError) as exc2:
            await service.list_pending(agent)
        assert exc2.value.code is ErrorCode.FORBIDDEN
        with pytest.raises(DomainError) as exc3:
            await service.issue_link_code(_staff(world, world.reception, Role.DOCTOR), world.p025)
        assert exc3.value.code is ErrorCode.FORBIDDEN


async def test_issue_code_for_an_unknown_patient_is_not_found(world: World) -> None:
    """phát mã cho hồ sơ không tồn tại báo not_found"""
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=InMemoryAccountStore())
        for patient in (uuid.uuid4(),):
            with pytest.raises(DomainError) as exc:
                await service.issue_link_code(_staff(world, world.owner, Role.OWNER), patient)
            assert exc.value.code is ErrorCode.NOT_FOUND


async def test_set_account_profile_updates_the_store_and_audits(admin_engine: Engine, world: World) -> None:
    """đổi hồ sơ chính sách của tài khoản: cập nhật kho tài khoản và ghi audit (từ -> đến)"""
    accounts = InMemoryAccountStore(
        fake_account_config(
            id="acc-9", clinic_id=world.clinic_a, policy_profile=PolicyProfileKey.STAFF_ASSISTANT
        )
    )
    async with be_db() as be:
        service = PolicyAdminService(db=be, accounts=accounts)
        out = await service.set_account_profile(
            _staff(world, world.owner, Role.OWNER),
            "acc-9",
            AccountPolicyUpdate(policy_profile=PolicyProfileKey.PATIENT_CHANNEL),
        )
        with pytest.raises(DomainError) as exc:
            await service.set_account_profile(
                _staff(world, world.owner, Role.OWNER),
                "missing",
                AccountPolicyUpdate(policy_profile=PolicyProfileKey.PATIENT_CHANNEL),
            )
        assert exc.value.code is ErrorCode.NOT_FOUND
    assert out.policy_profile is PolicyProfileKey.PATIENT_CHANNEL
    with admin_engine.begin() as conn:
        details = conn.execute(
            text(
                "SELECT details::text FROM clinic.audit_log "
                "WHERE action = 'policy.account_profile.set' AND entity_id = 'acc-9'"
            )
        ).scalar_one()
    assert "staff_assistant" in details
    assert "patient_channel" in details
