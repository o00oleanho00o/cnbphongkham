"""The bookkeeping of the notification delivery chain (package O, step O3). New module, no zalo-agent
original.

Everything the consumer of ``pema.notify`` needs from the clinic database, and nothing else, so the consumer
never imports a model or runs SQL itself (the agent-side import contract). These functions are the SYSTEM side
of the outbox: they take ``clinic_id`` and a ``ClinicDatabase``, not a staff ``ActionContext``, and they write
with plain statements (delivery progress is bookkeeping, not a business mutation, so it is not audited row by
row; the enqueue and the ack are). The staff side (list, ack, settings, push tokens, linking) is
``notification_inbox.py``.

* ``claim_due``: rows that are ``pending`` and due, taken with ``FOR UPDATE SKIP LOCKED`` and a lease, so two
  consumers never deliver one row and a consumer that died lets go when its lease runs out.
* ``record_attempt``: one ``clinic.notification_log`` row per attempt (provider, status, latency, a short
  code; no text, no recipient).
* ``settle``: moves a row on (next step and time, or finished) and releases the lease. Retries are bounded:
  ``backoff_s`` grows with the attempt, ``MAX_ATTEMPTS`` ends a step as ``failed``.
* the lookups of the providers: the settings, the notification target of an operator (bell id, quiet hours,
  push tokens decrypted for the provider), the internal account, whether a reference is a customer's thread,
  the 24/7 contacts, and the consumption of a one-time linking code.

A push token is decrypted here and handed to the provider as ``PushTarget``; it never goes to a log.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.care.routing_types import OnCallRow
from pema.clinic import audit
from pema.clinic.actions.notifications import OutboxNotification
from pema.config.secret_cipher import decrypt_secret
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.common import VN_TZ
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationRecipientKind,
    NotificationState,
    NotifySettingsOut,
    PushPlatform,
)
from pema_contracts.roles import ActorType

MAX_ATTEMPTS = 3
"""A step that fails this many times is ``failed`` for good (the next one is not tried for it)."""
BACKOFF_BASE_S = 20
LEASE_S = 90
DEFAULT_ACK_TIMEOUT_S = 180
LINK_CODE_TTL = timedelta(minutes=10)

DEFAULT_SETTINGS = NotifySettingsOut(
    ack_timeout_s=DEFAULT_ACK_TIMEOUT_S,
    team_group_id=None,
    in_app_enabled=True,
    push_enabled=False,
    bell_enabled=True,
    group_enabled=True,
    public_base_url=None,
)


def backoff_s(attempts: int) -> int:
    """Seconds to wait before attempt ``attempts + 1``: 20, 40, 80 ..."""
    return BACKOFF_BASE_S * (2 ** max(attempts - 1, 0))


def in_quiet_hours(start: time | None, end: time | None, at: datetime) -> bool:
    """Is ``at`` inside the operator's quiet window (clinic clock, ``end`` excluded, a window with
    ``end < start`` crosses midnight)? No window: never quiet."""
    if start is None or end is None:
        return False
    clock = at.astimezone(VN_TZ).time().replace(tzinfo=None)
    if start < end:
        return start <= clock < end
    return clock >= start or clock < end


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_code(code: str) -> str:
    """Upper case, letters and digits only: "abcd-2345" and "ABCD 2345" are the same code."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def code_hash(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PushTarget:
    id: UUID
    platform: PushPlatform
    token: str
    """Decrypted; for the provider only."""


@dataclass(frozen=True)
class NotifyTarget:
    """Where one operator can be reached, and when not to ring the personal Zalo."""

    user_id: UUID
    zalo_user_id: str | None
    quiet_start: time | None
    quiet_end: time | None
    push_tokens: tuple[PushTarget, ...]


# ------------------------------------------------------------------------------------------ the queue
_CLAIM_SQL = text("""
    UPDATE clinic.notification_outbox o SET lease_until = :until
     WHERE o.clinic_id = :clinic_id AND o.id IN (
        SELECT id FROM clinic.notification_outbox
         WHERE clinic_id = :clinic_id AND state = 'pending' AND next_attempt_at <= :now
           AND (lease_until IS NULL OR lease_until < :now)
         ORDER BY next_attempt_at, created_at
         LIMIT :limit FOR UPDATE SKIP LOCKED)
 RETURNING o.id, o.kind, o.recipient_kind, o.recipient_user_id, o.conversation_id, o.payload, o.attempts,
           o.chain_step, (o.acked_at IS NOT NULL) AS acked""")


async def claim_due(
    db: ClinicDatabase, clinic_id: UUID, now: datetime, *, limit: int = 20, lease_s: int = LEASE_S
) -> list[OutboxNotification]:
    async with db.session() as session:
        rows = (
            await session.execute(
                _CLAIM_SQL,
                {
                    "clinic_id": clinic_id,
                    "now": now,
                    "until": now + timedelta(seconds=lease_s),
                    "limit": limit,
                },
            )
        ).all()
    return [
        OutboxNotification(
            id=row.id,
            kind=row.kind,
            recipient_kind=NotificationRecipientKind(row.recipient_kind),
            recipient_user_id=row.recipient_user_id,
            conversation_id=row.conversation_id,
            payload=row.payload,
            attempts=row.attempts,
            chain_step=row.chain_step,
            acked=bool(row.acked),
        )
        for row in rows
    ]


_ATTEMPT_SQL = text("""
    INSERT INTO clinic.notification_log
        (clinic_id, outbox_id, provider, attempt, status, latency_ms, error_code)
    VALUES (:clinic_id, :outbox_id, :provider, :attempt, :status, :latency_ms, :error_code)""")


async def record_attempt(
    db: ClinicDatabase,
    clinic_id: UUID,
    outbox_id: UUID,
    provider: NotificationProvider,
    *,
    attempt: int,
    status: NotificationLogStatus,
    latency_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    async with db.session() as session:
        await session.execute(
            _ATTEMPT_SQL,
            {
                "clinic_id": clinic_id,
                "outbox_id": outbox_id,
                "provider": provider.value,
                "attempt": max(attempt, 1),
                "status": status.value,
                "latency_ms": None if latency_ms is None else max(latency_ms, 0),
                "error_code": None if error_code is None else error_code[:64],
            },
        )


_SETTLE_SQL = text("""
    UPDATE clinic.notification_outbox
       SET state = :state, chain_step = :chain_step, next_attempt_at = :next_attempt_at,
           attempts = :attempts, lease_until = NULL
     WHERE clinic_id = :clinic_id AND id = :id""")


async def settle(
    db: ClinicDatabase,
    clinic_id: UUID,
    outbox_id: UUID,
    *,
    state: NotificationState,
    chain_step: str | None,
    next_attempt_at: datetime,
    attempts: int,
) -> None:
    """Move a row on and let go of it. ``state`` ``pending`` keeps it in the queue for ``next_attempt_at``."""
    async with db.session() as session:
        await session.execute(
            _SETTLE_SQL,
            {
                "clinic_id": clinic_id,
                "id": outbox_id,
                "state": state.value,
                "chain_step": chain_step,
                "next_attempt_at": next_attempt_at,
                "attempts": attempts,
            },
        )


async def is_acked(db: ClinicDatabase, clinic_id: UUID, outbox_id: UUID) -> bool:
    """Read again right before the bell, so an ack that arrived while the row waited stops the chain."""
    async with db.session() as session:
        value = await session.scalar(
            text(
                "SELECT acked_at IS NOT NULL FROM clinic.notification_outbox WHERE clinic_id = :c AND id = :i"
            ),
            {"c": clinic_id, "i": outbox_id},
        )
    return bool(value)


# --------------------------------------------------------------------------------------- the lookups
async def load_settings(db: ClinicDatabase, clinic_id: UUID) -> NotifySettingsOut:
    """The clinic's settings; the defaults while nobody saved any."""
    async with db.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT ack_timeout_s, team_group_id, in_app_enabled, push_enabled, bell_enabled, "
                    "group_enabled, public_base_url FROM clinic.notify_setting WHERE clinic_id = :c"
                ),
                {"c": clinic_id},
            )
        ).first()
    if row is None:
        return DEFAULT_SETTINGS
    return NotifySettingsOut(
        ack_timeout_s=row.ack_timeout_s,
        team_group_id=row.team_group_id,
        in_app_enabled=row.in_app_enabled,
        push_enabled=row.push_enabled,
        bell_enabled=row.bell_enabled,
        group_enabled=row.group_enabled,
        public_base_url=row.public_base_url,
    )


async def load_target(db: ClinicDatabase, clinic_id: UUID, user_id: UUID) -> NotifyTarget:
    """Bell id (only when the operator consented), quiet hours and push tokens of one operator. A token that
    cannot be decrypted (the key changed) is left out and never reported with its value."""
    async with db.session() as session:
        profile = (
            await session.execute(
                text(
                    "SELECT notify_zalo_user_id FROM clinic.staff_profiles "
                    "WHERE clinic_id = :c AND user_id = :u "
                    "AND notify_zalo_consented_at IS NOT NULL"
                ),
                {"c": clinic_id, "u": user_id},
            )
        ).first()
        quiet = (
            await session.execute(
                text(
                    "SELECT quiet_start, quiet_end FROM clinic.notify_preference "
                    "WHERE clinic_id = :c AND user_id = :u"
                ),
                {"c": clinic_id, "u": user_id},
            )
        ).first()
        tokens = (
            await session.execute(
                text(
                    "SELECT id, platform, token_enc FROM clinic.push_token "
                    "WHERE clinic_id = :c AND user_id = :u "
                    "ORDER BY last_seen DESC LIMIT 10"
                ),
                {"c": clinic_id, "u": user_id},
            )
        ).all()
    pushes: list[PushTarget] = []
    for token in tokens:
        try:
            pushes.append(
                PushTarget(
                    id=token.id, platform=PushPlatform(token.platform), token=decrypt_secret(token.token_enc)
                )
            )
        except Exception:  # noqa: S112 - a token we cannot read is not a token; its value is never reported
            continue
    return NotifyTarget(
        user_id=user_id,
        zalo_user_id=profile.notify_zalo_user_id if profile is not None else None,
        quiet_start=quiet.quiet_start if quiet is not None else None,
        quiet_end=quiet.quiet_end if quiet is not None else None,
        push_tokens=tuple(pushes),
    )


async def drop_push_token(db: ClinicDatabase, clinic_id: UUID, token_id: UUID) -> None:
    """The provider said the token is dead (unregistered device): forget it."""
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM clinic.push_token WHERE clinic_id = :c AND id = :i"),
            {"c": clinic_id, "i": token_id},
        )


async def internal_account_id(db: ClinicDatabase, clinic_id: UUID) -> str | None:
    """The enabled internal account (the notifier), first by id. ``None``: none is set up."""
    async with db.session() as session:
        return await session.scalar(
            text(
                "SELECT id FROM agent.accounts WHERE clinic_id = :c AND purpose = 'internal' AND enabled "
                "ORDER BY id LIMIT 1"
            ),
            {"c": clinic_id},
        )


async def list_internal_account_ids(db: ClinicDatabase, clinic_id: UUID) -> frozenset[str]:
    """Every account whose purpose is ``internal`` (enabled or not): the intake path never records their
    messages as conversations and never starts a turn for them."""
    async with db.session() as session:
        rows = (
            await session.execute(
                text("SELECT id FROM agent.accounts WHERE clinic_id = :c AND purpose = 'internal'"),
                {"c": clinic_id},
            )
        ).all()
    return frozenset(row.id for row in rows)


async def account_purpose(db: ClinicDatabase, clinic_id: UUID, account_id: str) -> str | None:
    """``customer`` or ``internal``; ``None`` for an account that does not exist."""
    async with db.session() as session:
        return await session.scalar(
            text("SELECT purpose FROM agent.accounts WHERE clinic_id = :c AND id = :a"),
            {"c": clinic_id, "a": account_id},
        )


async def is_customer_thread(db: ClinicDatabase, clinic_id: UUID, ref: str) -> bool:
    """Is ``ref`` the thread of a customer? The internal account refuses to write to one."""
    async with db.session() as session:
        found = await session.scalar(
            text("SELECT 1 FROM clinic.conversation WHERE clinic_id = :c AND external_ref = :r LIMIT 1"),
            {"c": clinic_id, "r": ref},
        )
    return found is not None


async def list_on_call(db: ClinicDatabase, clinic_id: UUID) -> list[OnCallRow]:
    """Active 24/7 contacts (``pema.care.oncall.pick_on_call`` chooses the current one)."""
    async with db.session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, zalo_number, owner, valid_from, valid_to, active, is_fixture "
                    "FROM clinic.on_call_contacts WHERE clinic_id = :c AND active"
                ),
                {"c": clinic_id},
            )
        ).all()
    return [
        OnCallRow(
            id=row.id,
            zalo_number=row.zalo_number,
            owner=row.owner,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            active=row.active,
            is_fixture=row.is_fixture,
        )
        for row in rows
    ]


# ------------------------------------------------------------------------------------------- linking
@dataclass(frozen=True)
class LinkOutcome:
    linked: bool
    user_id: UUID | None = None
    reason: str | None = None
    """``unknown_or_expired`` when no live code matched."""


async def consume_link_code(
    db: ClinicDatabase, clinic_id: UUID, code: str, zalo_user_id: str, at: datetime
) -> LinkOutcome:
    """The operator sent ``code`` to the internal account from the personal Zalo ``zalo_user_id``.

    Single use: the update that marks the code used is the check (a code that was used, or has expired,
    matches nothing). The Zalo id is stored with the time of consent on the operator's staff profile and moves
    from any other operator that had it. The audit row names the operator only; the Zalo id is never logged
    or audited."""
    async with db.session() as session:
        user_id = await session.scalar(
            text(
                "UPDATE clinic.notify_link_code SET used_at = :now WHERE clinic_id = :c AND code_hash = :h "
                "AND used_at IS NULL AND expires_at > :now RETURNING user_id"
            ),
            {"c": clinic_id, "h": code_hash(code), "now": at},
        )
        if user_id is None:
            return LinkOutcome(linked=False, reason="unknown_or_expired")
        await session.execute(
            text(
                "UPDATE clinic.staff_profiles "
                "SET notify_zalo_user_id = NULL, notify_zalo_consented_at = NULL "
                "WHERE clinic_id = :c AND notify_zalo_user_id = :z AND user_id <> :u"
            ),
            {"c": clinic_id, "z": zalo_user_id, "u": user_id},
        )
        updated = await session.execute(
            text(
                "UPDATE clinic.staff_profiles SET notify_zalo_user_id = :z, notify_zalo_consented_at = :now "
                "WHERE clinic_id = :c AND user_id = :u"
            ),
            {"c": clinic_id, "z": zalo_user_id, "u": user_id, "now": at},
        )
        if updated.rowcount == 0:  # type: ignore[attr-defined]
            await session.execute(
                text(
                    "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role, notify_zalo_user_id, "
                    "notify_zalo_consented_at) SELECT clinic_id, id, role, :z, :now FROM clinic.user_account "
                    "WHERE clinic_id = :c AND id = :u"
                ),
                {"c": clinic_id, "z": zalo_user_id, "u": user_id, "now": at},
            )
        await audit.record(
            session,
            ActionContext(clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.WEBHOOK),
            "notification.zalo_linked",
            "user",
            user_id,
            {"user_id": str(user_id)},
        )
    return LinkOutcome(linked=True, user_id=user_id)


def payload_urgent(payload: Mapping[str, Any]) -> bool:
    return payload.get("urgency") == "urgent"
