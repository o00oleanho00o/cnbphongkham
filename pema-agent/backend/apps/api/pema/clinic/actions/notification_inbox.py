"""What an operator does with notifications (package O, step O3). New module, no zalo-agent original.

The staff side of the outbox: read one's own notices, acknowledge them (``POST /notifications/{id}/ack``,
or by opening the deep link, which acknowledges every unacknowledged notice of the caller about that
conversation or request), register and delete a push token, link the personal Zalo that rings as the bell,
set quiet hours, and (owner and manager) change the clinic's settings.

Every action works on the CALLER's rows only: the user id always comes from the session, never from the body.
``notify.self`` is held by the four assignable roles; ``notify.manage`` by the owner and the manager.

Rules worth knowing:

* an ack is idempotent and stops the chain of that row (the bell checks it again right before it rings); it
  does not accept a handoff: package M's ``accept`` stays the only way to take a patient, and its SLA runs on;
* a push token is stored encrypted (``pema.config.secret_cipher``) with its SHA-256 as the key, one token
  on one user at a time (registering it again from another account moves it); the token is never returned;
* the linking code is shown once, valid ``LINK_CODE_TTL``, stored as a hash, single use; asking for a new one
  voids the older unused ones. The audit rows carry ids and field names, never a Zalo id, a token or a code.
"""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import delete, func, or_, select, text

from pema.clinic import audit
from pema.clinic.actions._assignment_core import acting_user_id
from pema.clinic.actions._common import not_found, now
from pema.clinic.actions.notification_chain import (
    LINK_CODE_TTL,
    code_hash,
    load_settings,
    token_hash,
)
from pema.clinic.actions.roster import format_hhmm, parse_hhmm
from pema.clinic.models import NotificationOutbox, NotifyLinkCode, NotifyPreference, NotifySetting, PushToken
from pema.clinic.rbac import require
from pema.config.secret_cipher import encrypt_secret
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.ops import (
    NotificationOut,
    NotificationPayload,
    NotificationState,
    NotifyLinkOut,
    NotifyLinkStatus,
    NotifyPreferenceIn,
    NotifyPreferenceOut,
    NotifySettingsOut,
    NotifySettingsUpdate,
    PushTokenIn,
    PushTokenOut,
)
from pema_contracts.roles import Permission

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
"""No 0, O, 1, I, L: the code is typed from a screen into a chat."""
CODE_LENGTH = 8
LIST_LIMIT = 50
MAX_PUSH_TOKENS_PER_USER = 10

TOO_MANY_TOKENS_MESSAGE = "Đã đăng ký quá nhiều thiết bị. Hãy xóa bớt thiết bị cũ."
ACK_TARGET_MESSAGE = "Cần đúng một trong hai: hội thoại hoặc yêu cầu chuyển người."


def new_link_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def display_code(code: str) -> str:
    """``ABCD-2345``: the hyphen is only for reading; ``normalize_code`` drops it."""
    return f"{code[: CODE_LENGTH // 2]}-{code[CODE_LENGTH // 2 :]}"


def _notice_out(row: NotificationOutbox) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        kind=row.kind,
        state=NotificationState(row.state),
        created_at=row.created_at,
        acked_at=row.acked_at,
        payload=NotificationPayload.model_validate(row.payload),
    )


# ------------------------------------------------------------------------------------ own notices
async def list_own(
    db: ClinicDatabase, ctx: ActionContext, *, unacked_only: bool = False, limit: int = LIST_LIMIT
) -> list[NotificationOut]:
    """The caller's notices, newest first."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    query = (
        select(NotificationOutbox)
        .where(NotificationOutbox.clinic_id == ctx.clinic_id, NotificationOutbox.recipient_user_id == me)
        .order_by(NotificationOutbox.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if unacked_only:
        query = query.where(NotificationOutbox.acked_at.is_(None))
    async with db.session() as session:
        rows = (await session.scalars(query)).all()
    return [_notice_out(row) for row in rows]


def _mark_acked(row: NotificationOutbox, me: UUID) -> None:
    row.acked_at = now()
    row.acked_by = me
    row.chain_step = "done"
    if row.state == NotificationState.PENDING.value:
        row.state = NotificationState.SENT.value


async def ack(db: ClinicDatabase, ctx: ActionContext, notification_id: UUID) -> NotificationOut:
    """Acknowledge one notice of the caller. Repeating it changes nothing."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    async with db.session() as session:
        row = await session.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.clinic_id == ctx.clinic_id,
                NotificationOutbox.recipient_user_id == me,
            )
            .with_for_update()
        )
        if row is None:
            raise not_found("thông báo")
        if row.acked_at is None:
            _mark_acked(row, me)
            await session.flush()
            await audit.record(session, ctx, "notification.ack", "notification", row.id, {"kind": row.kind})
        result = _notice_out(row)
    emit_live(LiveEventType.NOTIFICATIONS_CHANGED, notification_id)
    return result


async def ack_target(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    conversation_id: UUID | None = None,
    request_id: UUID | None = None,
) -> int:
    """The deep link was opened: acknowledge every unacknowledged notice of the caller about that conversation
    (or handoff request). Returns how many. The caller must be signed in: the route needs the session."""
    require(ctx, Permission.NOTIFY_SELF)
    if (conversation_id is None) == (request_id is None):
        raise DomainError(ErrorCode.VALIDATION_FAILED, ACK_TARGET_MESSAGE)
    me = acting_user_id(ctx)
    target = (
        NotificationOutbox.conversation_id == conversation_id
        if conversation_id is not None
        else NotificationOutbox.payload["request_id"].astext == str(request_id)
    )
    async with db.session() as session:
        rows = (
            await session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.clinic_id == ctx.clinic_id,
                    NotificationOutbox.recipient_user_id == me,
                    NotificationOutbox.acked_at.is_(None),
                    target,
                )
                .with_for_update()
            )
        ).all()
        for row in rows:
            _mark_acked(row, me)
        if rows:
            await session.flush()
            await audit.record(
                session,
                ctx,
                "notification.ack",
                "notification",
                None,
                {"count": len(rows), "by": "deep_link"},
            )
    if rows:
        emit_live(LiveEventType.NOTIFICATIONS_CHANGED, rows[0].id)
    return len(rows)


# -------------------------------------------------------------------------------------- push tokens
async def register_push_token(db: ClinicDatabase, ctx: ActionContext, body: PushTokenIn) -> PushTokenOut:
    """Register (or refresh) the device. The same token again only moves ``last_seen``; a token that belonged
    to another user moves to the caller (a phone changes hands)."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    digest = token_hash(body.token)
    async with db.session() as session:
        row = await session.scalar(
            select(PushToken).where(PushToken.clinic_id == ctx.clinic_id, PushToken.token_hash == digest)
        )
        if row is None:
            count = await session.scalar(
                select(func.count())
                .select_from(PushToken)
                .where(PushToken.clinic_id == ctx.clinic_id, PushToken.user_id == me)
            )
            if (count or 0) >= MAX_PUSH_TOKENS_PER_USER:
                raise DomainError(ErrorCode.VALIDATION_FAILED, TOO_MANY_TOKENS_MESSAGE)
            row = PushToken(
                clinic_id=ctx.clinic_id,
                user_id=me,
                platform=body.platform.value,
                token_hash=digest,
                token_enc=encrypt_secret(body.token),
            )
            session.add(row)
        else:
            row.user_id = me
            row.platform = body.platform.value
            row.last_seen = now()
        await session.flush()
        await audit.record(
            session, ctx, "push_token.register", "push_token", row.id, {"platform": body.platform.value}
        )
        return PushTokenOut(id=row.id, platform=body.platform, last_seen=row.last_seen)


async def delete_push_token(db: ClinicDatabase, ctx: ActionContext, token_id: UUID) -> None:
    """Forget one of the caller's devices (sign-out). Somebody else's token is a 404."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    async with db.session() as session:
        row = await session.scalar(
            select(PushToken).where(
                PushToken.id == token_id, PushToken.clinic_id == ctx.clinic_id, PushToken.user_id == me
            )
        )
        if row is None:
            raise not_found("thiết bị")
        await session.delete(row)
        await session.flush()
        await audit.record(session, ctx, "push_token.delete", "push_token", token_id, {})


# --------------------------------------------------------------------------------- the bell (linking)
async def start_link(db: ClinicDatabase, ctx: ActionContext) -> NotifyLinkOut:
    """A new one-time code. The operator sends it, as a message, to the internal Zalo account; the inbound
    handler of that account links the sender (``pema.notify.link``)."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    code = new_link_code()
    at = now()
    async with db.session() as session:
        await session.execute(
            delete(NotifyLinkCode).where(
                NotifyLinkCode.clinic_id == ctx.clinic_id,
                NotifyLinkCode.user_id == me,
                or_(NotifyLinkCode.used_at.is_(None), NotifyLinkCode.expires_at < at),
            )
        )
        row = NotifyLinkCode(
            clinic_id=ctx.clinic_id, user_id=me, code_hash=code_hash(code), expires_at=at + LINK_CODE_TTL
        )
        session.add(row)
        await session.flush()
        await audit.record(session, ctx, "notification.link_started", "user", me, {})
        label = await session.scalar(
            text(
                "SELECT label FROM agent.accounts WHERE clinic_id = :c AND purpose = 'internal' AND enabled "
                "ORDER BY id LIMIT 1"
            ),
            {"c": ctx.clinic_id},
        )
    return NotifyLinkOut(code=display_code(code), expires_at=row.expires_at, internal_label=label)


async def link_status(db: ClinicDatabase, ctx: ActionContext) -> NotifyLinkStatus:
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    async with db.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT notify_zalo_consented_at FROM clinic.staff_profiles "
                    "WHERE clinic_id = :c AND user_id = :u AND notify_zalo_user_id IS NOT NULL"
                ),
                {"c": ctx.clinic_id, "u": me},
            )
        ).first()
    return NotifyLinkStatus(
        linked=row is not None, consented_at=row.notify_zalo_consented_at if row else None
    )


async def unlink(db: ClinicDatabase, ctx: ActionContext) -> NotifyLinkStatus:
    """The operator withdraws consent: the bell stops ringing their personal Zalo."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    async with db.session() as session:
        await session.execute(
            text(
                "UPDATE clinic.staff_profiles "
                "SET notify_zalo_user_id = NULL, notify_zalo_consented_at = NULL "
                "WHERE clinic_id = :c AND user_id = :u"
            ),
            {"c": ctx.clinic_id, "u": me},
        )
        await audit.record(session, ctx, "notification.zalo_unlinked", "user", me, {})
    return NotifyLinkStatus(linked=False)


# ------------------------------------------------------------------------------------- quiet hours
def _preference_out(row: NotifyPreference | None) -> NotifyPreferenceOut:
    if row is None or row.quiet_start is None or row.quiet_end is None:
        return NotifyPreferenceOut()
    return NotifyPreferenceOut(quiet_start=format_hhmm(row.quiet_start), quiet_end=format_hhmm(row.quiet_end))


async def get_preference(db: ClinicDatabase, ctx: ActionContext) -> NotifyPreferenceOut:
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    async with db.session() as session:
        row = await session.get(NotifyPreference, (ctx.clinic_id, me))
    return _preference_out(row)


async def set_preference(
    db: ClinicDatabase, ctx: ActionContext, body: NotifyPreferenceIn
) -> NotifyPreferenceOut:
    """Quiet hours of the caller (clinic clock). Both ``null``: no quiet hours. An ``urgent`` notice rings
    anyway; quiet hours silence the personal Zalo only (the in-app notice is never silent)."""
    require(ctx, Permission.NOTIFY_SELF)
    me = acting_user_id(ctx)
    start = parse_hhmm(body.quiet_start) if body.quiet_start else None
    end = parse_hhmm(body.quiet_end) if body.quiet_end else None
    async with db.session() as session:
        row = await session.get(NotifyPreference, (ctx.clinic_id, me))
        if row is None:
            row = NotifyPreference(clinic_id=ctx.clinic_id, user_id=me, quiet_start=start, quiet_end=end)
            session.add(row)
        else:
            row.quiet_start = start
            row.quiet_end = end
        await session.flush()
        await audit.record(
            session,
            ctx,
            "notification.preference",
            "user",
            me,
            {"fields": ["quiet_start", "quiet_end"], "has_quiet_hours": start is not None},
        )
        return _preference_out(row)


# ------------------------------------------------------------------------------------ the settings
async def get_settings(db: ClinicDatabase, ctx: ActionContext) -> NotifySettingsOut:
    require(ctx, Permission.NOTIFY_SELF)
    return await load_settings(db, ctx.clinic_id)


async def update_settings(
    db: ClinicDatabase, ctx: ActionContext, body: NotifySettingsUpdate
) -> NotifySettingsOut:
    """Owner and manager. A field left out stays; ``team_group_id`` sent as ``null`` unsets the group. The
    audit row names the fields that changed, never the group id."""
    require(ctx, Permission.NOTIFY_MANAGE)
    fields = body.model_fields_set
    async with db.session() as session:
        row = await session.get(NotifySetting, ctx.clinic_id)
        if row is None:
            row = NotifySetting(clinic_id=ctx.clinic_id)
            session.add(row)
            _fill_defaults(row)
        for name in sorted(fields):
            value = getattr(body, name)
            if name in _CLEARABLE:
                setattr(row, name, (value.strip() or None) if isinstance(value, str) else None)
            elif value is not None:
                setattr(row, name, value)
        row.updated_by = ctx.actor_user_id
        await session.flush()
        await audit.record(
            session, ctx, "notification.settings", "notify_setting", ctx.clinic_id, {"fields": sorted(fields)}
        )
    return await load_settings(db, ctx.clinic_id)


_CLEARABLE = ("team_group_id", "public_base_url")


def _fill_defaults(row: NotifySetting) -> None:
    row.ack_timeout_s = 180
    row.in_app_enabled = True
    row.push_enabled = False
    row.bell_enabled = True
    row.group_enabled = True


__all__ = [
    "ack",
    "ack_target",
    "delete_push_token",
    "get_preference",
    "get_settings",
    "link_status",
    "list_own",
    "register_push_token",
    "set_preference",
    "start_link",
    "unlink",
    "update_settings",
]
