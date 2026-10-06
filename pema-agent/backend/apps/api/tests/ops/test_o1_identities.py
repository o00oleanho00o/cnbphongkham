"""Identities and their own send limits (package O, step O1). New tests (no zalo-agent original).

Needs ``PEMA_TEST_DATABASE_URL``. A channel account of ``agent.accounts`` is an identity: ``purpose`` (customer or
internal), per-identity send limits that fall back to the channel row of ``clinic.channel_setting``, RBAC
(``identity.manage`` owner and manager, ``roster.read`` every operator) and one audit row per change.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from pema.clinic.actions import identities
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import IdentityPurpose, IdentityUpdate

pytestmark = pytest.mark.db


def _audit(admin: Engine, action: str, entity_id: str) -> list[dict[str, Any]]:
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_role, details FROM clinic.audit_log "
                "WHERE action = :a AND entity_id = :e ORDER BY id"
            ),
            {"a": action, "e": entity_id},
        ).all()
    return [{"actor_role": row.actor_role, "details": row.details} for row in rows]


# -------------------------------------------------------------------------------- the columns and CHECKs
def test_a_new_account_is_a_customer_identity_with_no_overrides(admin: Engine, add_account: Any) -> None:
    add_account("long")
    with admin.connect() as conn:
        row = conn.execute(
            text(
                "SELECT purpose, send_gap_min_s, send_gap_max_s, daily_cap FROM agent.accounts WHERE id = 'long'"
            )
        ).one()
    assert (row.purpose, row.send_gap_min_s, row.send_gap_max_s, row.daily_cap) == (
        "customer",
        None,
        None,
        None,
    )


def test_purpose_is_customer_or_internal(admin: Engine, add_account: Any) -> None:
    add_account("long")
    add_account("bell", purpose="internal")
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text("UPDATE agent.accounts SET purpose = 'staff' WHERE id = 'long'"))


@pytest.mark.parametrize(
    "assignment",
    [
        "send_gap_min_s = -1",
        "send_gap_max_s = -1",
        "daily_cap = -1",
        "send_gap_min_s = 9, send_gap_max_s = 3",
    ],
)
def test_send_limit_overrides_must_be_sane(admin: Engine, add_account: Any, assignment: str) -> None:
    add_account("long")
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text(f"UPDATE agent.accounts SET {assignment} WHERE id = 'long'"))  # noqa: S608


# ------------------------------------------------------------------------------------- effective limits
async def test_effective_limits_fall_back_to_the_channel_row(
    db: ClinicDatabase, world: SeedResult, add_account: Any, set_channel: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long")
    limits = await identities.effective_limits(db, world.clinic_id, "long")
    assert limits is not None
    assert (limits.send_gap_min_s, limits.send_gap_max_s, limits.daily_cap) == (3, 9, 50)


async def test_an_override_wins_field_by_field(
    db: ClinicDatabase, world: SeedResult, add_account: Any, set_channel: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long", send_gap_min_s=5, daily_cap=20)  # the max gap is not overridden
    limits = await identities.effective_limits(db, world.clinic_id, "long")
    assert limits is not None
    assert (limits.send_gap_min_s, limits.send_gap_max_s, limits.daily_cap) == (5, 9, 20)


async def test_without_a_channel_row_or_override_there_is_no_limit(
    db: ClinicDatabase, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    limits = await identities.effective_limits(db, world.clinic_id, "long")
    assert limits is not None
    assert (limits.send_gap_min_s, limits.send_gap_max_s, limits.daily_cap) == (0, 0, None)


async def test_two_identities_of_one_channel_have_their_own_limits(
    db: ClinicDatabase, world: SeedResult, add_account: Any, set_channel: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long", daily_cap=10)
    add_account("hoa")
    long = await identities.effective_limits(db, world.clinic_id, "long")
    hoa = await identities.effective_limits(db, world.clinic_id, "hoa")
    assert long is not None
    assert hoa is not None
    assert (long.daily_cap, hoa.daily_cap) == (10, 50)


async def test_effective_limits_of_an_unknown_account_is_none(db: ClinicDatabase, world: SeedResult) -> None:
    assert await identities.effective_limits(db, world.clinic_id, "ghost") is None


# --------------------------------------------------------------------------------------------- reading
async def test_every_operator_lists_the_identities_customer_facing_first(
    db: ClinicDatabase, add_account: Any, staff_ctx: Any
) -> None:
    add_account("bell", purpose="internal", label="Chuông nội bộ")
    add_account("long", label="Long")
    for key in ("owner", "manager", "doctor.mai", "cs.thu"):
        rows = await identities.list_identities(db, staff_ctx(key))
        assert [row.id for row in rows] == ["long", "bell"], key
        assert [row.purpose for row in rows] == [IdentityPurpose.CUSTOMER, IdentityPurpose.INTERNAL]


@pytest.mark.parametrize("key", ["reception.lan", "accountant.hoa"])
async def test_reception_and_the_accountant_do_not_read_identities(
    db: ClinicDatabase, add_account: Any, staff_ctx: Any, key: str
) -> None:
    add_account("long")
    with pytest.raises(DomainError) as refused:
        await identities.list_identities(db, staff_ctx(key))
    assert refused.value.code is ErrorCode.FORBIDDEN


async def test_the_listing_shows_the_channel_state(
    db: ClinicDatabase, add_account: Any, set_channel: Any, staff_ctx: Any, admin: Engine, world: SeedResult
) -> None:
    set_channel("zalo_personal", gap_min=1, gap_max=2)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.channel_setting SET kill_switch_on = true WHERE clinic_id = :c"),
            {"c": world.clinic_id},
        )
    add_account("long")
    [row] = await identities.list_identities(db, staff_ctx("owner"))
    assert (row.channel_enabled, row.kill_switch_on) == (True, True)


# --------------------------------------------------------------------------------------------- changing
@pytest.mark.parametrize("key", ["owner", "manager"])
async def test_owner_and_manager_change_the_settings_and_the_change_is_audited(
    db: ClinicDatabase, admin: Engine, add_account: Any, set_channel: Any, staff_ctx: Any, key: str
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long")
    out = await identities.update_identity_settings(
        db, staff_ctx(key), "long", IdentityUpdate(label="Long (CSKH)", send_gap_min_s=4, daily_cap=30)
    )
    assert out.label == "Long (CSKH)"
    assert (out.overrides.send_gap_min_s, out.overrides.send_gap_max_s, out.overrides.daily_cap) == (
        4,
        None,
        30,
    )
    assert (out.effective.send_gap_min_s, out.effective.send_gap_max_s, out.effective.daily_cap) == (4, 9, 30)
    [row] = _audit(admin, "identity.update", "long")
    assert row["actor_role"] == key
    assert row["details"] == {
        "changed_fields": ["daily_cap", "label", "send_gap_min_s"],
        "send_gap_min_s": 4,
        "daily_cap": 30,
    }  # numbers and field names only: the label is not copied into the trail


@pytest.mark.parametrize("key", ["doctor.mai", "cs.thu", "reception.lan", "accountant.hoa"])
async def test_nobody_else_changes_an_identity(
    db: ClinicDatabase, admin: Engine, add_account: Any, staff_ctx: Any, key: str
) -> None:
    add_account("long")
    with pytest.raises(DomainError) as refused:
        await identities.update_identity_settings(db, staff_ctx(key), "long", IdentityUpdate(daily_cap=1))
    assert refused.value.code is ErrorCode.FORBIDDEN
    assert _audit(admin, "identity.update", "long") == []


async def test_a_limit_sent_as_null_clears_its_override(
    db: ClinicDatabase, add_account: Any, set_channel: Any, staff_ctx: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long", daily_cap=5)
    out = await identities.update_identity_settings(
        db, staff_ctx("owner"), "long", IdentityUpdate.model_validate({"daily_cap": None})
    )
    assert out.overrides.daily_cap is None
    assert out.effective.daily_cap == 50


async def test_the_effective_gap_must_stay_ordered(
    db: ClinicDatabase, admin: Engine, add_account: Any, set_channel: Any, staff_ctx: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9)
    add_account("long")
    with pytest.raises(DomainError) as refused:
        await identities.update_identity_settings(
            db, staff_ctx("owner"), "long", IdentityUpdate(send_gap_min_s=20)
        )
    assert refused.value.code is ErrorCode.VALIDATION_FAILED
    assert _audit(admin, "identity.update", "long") == []


async def test_an_empty_change_writes_nothing(
    db: ClinicDatabase, admin: Engine, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    out = await identities.update_identity_settings(db, staff_ctx("owner"), "long", IdentityUpdate())
    assert out.id == "long"
    assert _audit(admin, "identity.update", "long") == []


async def test_an_unknown_identity_is_not_found(db: ClinicDatabase, staff_ctx: Any) -> None:
    with pytest.raises(DomainError) as refused:
        await identities.update_identity_settings(
            db, staff_ctx("owner"), "ghost", IdentityUpdate(daily_cap=1)
        )
    assert refused.value.code is ErrorCode.NOT_FOUND


def test_purpose_and_label_cannot_be_cleared() -> None:
    with pytest.raises(ValueError, match="cannot be cleared"):
        IdentityUpdate.model_validate({"purpose": None})
    with pytest.raises(ValueError, match="cannot be cleared"):
        IdentityUpdate.model_validate({"label": None})


async def test_an_identity_can_become_internal_only_while_nothing_points_at_it(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("bell")
    out = await identities.update_identity_settings(
        db, staff_ctx("manager"), "bell", IdentityUpdate(purpose=IdentityPurpose.INTERNAL)
    )
    assert out.purpose is IdentityPurpose.INTERNAL

    add_account("long")
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 'thread-1', 'long')"
            ),
            {"c": world.clinic_id},
        )
    with pytest.raises(DomainError) as refused:
        await identities.update_identity_settings(
            db, staff_ctx("manager"), "long", IdentityUpdate(purpose=IdentityPurpose.INTERNAL)
        )
    assert refused.value.code is ErrorCode.INVALID_STATE
    still = [row for row in await identities.list_identities(db, staff_ctx("owner")) if row.id == "long"]
    assert [row.purpose for row in still] == [IdentityPurpose.CUSTOMER]


async def test_an_identity_with_a_roster_cannot_become_internal(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.account_roster "
                "(clinic_id, account_id, user_id, weekdays, start_time, end_time) "
                "VALUES (:c, 'long', :u, ARRAY['mon'], '08:00', '17:00')"
            ),
            {"c": world.clinic_id, "u": world.users["cs.thu"]},
        )
    with pytest.raises(DomainError) as refused:
        await identities.update_identity_settings(
            db, staff_ctx("owner"), "long", IdentityUpdate(purpose=IdentityPurpose.INTERNAL)
        )
    assert refused.value.code is ErrorCode.INVALID_STATE


# ------------------------------------------------------------------------------------------------- HTTP
async def test_the_http_routes_follow_the_permissions(
    client_factory: Any, add_account: Any, set_channel: Any
) -> None:
    set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)
    add_account("long")
    add_account("bell", purpose="internal")
    doctor = await client_factory("doctor.mai")
    listed = await doctor.get("/api/v1/identities")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == ["long", "bell"]
    assert (await doctor.patch("/api/v1/identities/long", json={"daily_cap": 1})).status_code == 403

    reception = await client_factory("reception.lan")
    assert (await reception.get("/api/v1/identities")).status_code == 403

    manager = await client_factory("manager")
    changed = await manager.patch("/api/v1/identities/long", json={"daily_cap": 7})
    assert changed.status_code == 200, changed.text
    assert changed.json()["effective"]["daily_cap"] == 7


@pytest.mark.parametrize(
    "field", ["bot_token_enc", "credential_enc", "webhook_secret_enc", "channel", "agent_id"]
)
async def test_the_patch_refuses_a_credential_or_any_other_field(
    client_factory: Any, add_account: Any, field: str
) -> None:
    add_account("long")
    owner = await client_factory("owner")
    refused = await owner.patch("/api/v1/identities/long", json={field: "x"})
    assert refused.status_code == 422, refused.text
    assert json.loads(refused.text)["error"]["code"] == "validation_failed"
