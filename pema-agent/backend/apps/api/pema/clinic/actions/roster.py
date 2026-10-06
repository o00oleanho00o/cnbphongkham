"""Roster: who covers each channel identity, when (package O, step O1). New module, no zalo-agent original.

An entry says "operator X covers identity Y" for a set of weekdays (a repeating slot) or for one explicit
date, between a start and an end time on the clinic clock (+07:00). An end EARLIER than the start means the
slot ends the next morning (a night shift): ``22:00-06:00`` on Monday covers Monday 22:00 up to Tuesday
06:00. The start is included, the end is not. Several operators may cover the same identity at the same time
(a shared inbox), and the roster only RANKS: nobody is locked out of a thread because they are not on it
(assignment is step O2).

* ``who_is_on(account_id, at)``: the operators on duty at a moment. It looks at the account of each entry NOW,
  not when the entry was made: a user who was locked or moved to a role that cannot hold a conversation
  (reception, accountant) drops out of the answer, the entry stays for the manager to fix.
* Writes (``create``, ``update``, ``delete``): owner and manager (``roster.manage``). The user must be an
  ACTIVE member of an assignable role (owner, manager, doctor, cs_staff: ``load_assignable_user``) and the
  account must be a customer-facing identity (an internal notifier has no operators to cover it).
* Reads (``list_roster``, ``on_duty``): every operator (``roster.read``).
* Every write puts ids, weekdays, dates and times in its audit row, never the free-text note.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found
from pema.clinic.actions.assignees import ASSIGNABLE_ROLE_VALUES, load_assignable_user
from pema.clinic.models import AccountRoster, UserAccount
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import (
    WEEKDAY_ORDER,
    OnDutyOperator,
    OnDutyOut,
    RosterEntryCreate,
    RosterEntryOut,
    RosterEntryUpdate,
    Weekday,
)
from pema_contracts.roles import Permission, Role

INVALID_USER_MESSAGE = "Người trực phải là nhân viên đang hoạt động có vai trò xử lý hội thoại."
UNKNOWN_IDENTITY_MESSAGE = "Danh tính không tồn tại."
INTERNAL_IDENTITY_MESSAGE = "Danh tính nội bộ không có lịch trực."
ONE_KIND_MESSAGE = "Chọn lịch lặp theo thứ hoặc một ngày cụ thể, không chọn cả hai."
SAME_TIME_MESSAGE = "Giờ bắt đầu và giờ kết thúc phải khác nhau."

_WEEKDAY_INDEX = {day.value: index for index, day in enumerate(WEEKDAY_ORDER)}


def parse_hhmm(value: str) -> time:
    return time(int(value[:2]), int(value[3:5]))


def format_hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def slot_covers(
    weekdays: list[str] | None, on_date: date | None, start: time, end: time, at: datetime
) -> bool:
    """Does one roster entry cover the moment ``at``? Pure: the clock is the +07:00 one of the clinic.

    Start included, end excluded. ``end <= start`` is a slot that crosses midnight: it covers the evening of
    its
    day from ``start`` and the morning of the NEXT day up to ``end``."""
    local = at.astimezone(VN_TZ)
    clock = local.time().replace(tzinfo=None)

    def matches(day: date) -> bool:
        if on_date is not None:
            return day == on_date
        return weekdays is not None and WEEKDAY_ORDER[day.weekday()].value in weekdays

    if end > start:
        return matches(local.date()) and start <= clock < end
    return (matches(local.date()) and clock >= start) or (
        matches(local.date() - timedelta(days=1)) and clock < end
    )


def _out(row: AccountRoster, user: UserAccount) -> RosterEntryOut:
    return RosterEntryOut(
        id=row.id,
        account_id=row.account_id,
        user_id=row.user_id,
        user_name=user.display_name,
        user_role=Role(user.role),
        weekdays=[Weekday(d) for d in row.weekdays] if row.weekdays else None,
        on_date=row.on_date,
        start=format_hhmm(row.start_time),
        end=format_hhmm(row.end_time),
        note=row.note,
        version=row.version,
    )


def _audit_details(row: AccountRoster) -> dict[str, object]:
    return {
        "account_id": row.account_id,
        "user_id": str(row.user_id),
        "weekdays": list(row.weekdays) if row.weekdays else None,
        "on_date": row.on_date.isoformat() if row.on_date else None,
        "start": format_hhmm(row.start_time),
        "end": format_hhmm(row.end_time),
    }


async def _require_customer_identity(session: AsyncSession, ctx: ActionContext, account_id: str) -> None:
    purpose = await session.scalar(
        text("SELECT purpose FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :account_id"),
        {"clinic_id": ctx.clinic_id, "account_id": account_id},
    )
    if purpose is None:
        raise DomainError(ErrorCode.NOT_FOUND, UNKNOWN_IDENTITY_MESSAGE)
    if purpose != "customer":
        raise DomainError(ErrorCode.INVALID_STATE, INTERNAL_IDENTITY_MESSAGE)


async def _load_entry(session: AsyncSession, ctx: ActionContext, entry_id: UUID) -> AccountRoster:
    row = await session.scalar(
        select(AccountRoster).where(AccountRoster.id == entry_id, AccountRoster.clinic_id == ctx.clinic_id)
    )
    if row is None:
        raise not_found("lịch trực")
    return row


async def _user_of(session: AsyncSession, row: AccountRoster) -> UserAccount:
    user = await session.scalar(
        select(UserAccount).where(UserAccount.id == row.user_id, UserAccount.clinic_id == row.clinic_id)
    )
    if user is None:  # the foreign key cascades, so this is a lost race, not a normal state
        raise not_found("nhân viên")
    return user


async def list_roster(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    account_id: str | None = None,
    user_id: UUID | None = None,
) -> list[RosterEntryOut]:
    """The roster, optionally of one identity or one operator. Every operator may read it."""
    require(ctx, Permission.ROSTER_READ)
    query = (
        select(AccountRoster, UserAccount)
        .join(
            UserAccount,
            (UserAccount.clinic_id == AccountRoster.clinic_id) & (UserAccount.id == AccountRoster.user_id),
        )
        .where(AccountRoster.clinic_id == ctx.clinic_id)
        .order_by(
            AccountRoster.account_id, UserAccount.display_name, AccountRoster.start_time, AccountRoster.id
        )
    )
    if account_id is not None:
        query = query.where(AccountRoster.account_id == account_id)
    if user_id is not None:
        query = query.where(AccountRoster.user_id == user_id)
    async with db.session() as session:
        rows = (await session.execute(query)).all()
    return [_out(entry, user) for entry, user in rows]


async def create_entry(db: ClinicDatabase, ctx: ActionContext, body: RosterEntryCreate) -> RosterEntryOut:
    require(ctx, Permission.ROSTER_MANAGE)
    async with db.session() as session:
        await _require_customer_identity(session, ctx, body.account_id)
        user = await load_assignable_user(session, ctx, body.user_id, message=INVALID_USER_MESSAGE)
        row = AccountRoster(
            clinic_id=ctx.clinic_id,
            account_id=body.account_id,
            user_id=user.id,
            weekdays=[d.value for d in body.weekdays] if body.weekdays else None,
            on_date=body.on_date,
            start_time=parse_hhmm(body.start),
            end_time=parse_hhmm(body.end),
            note=body.note or None,
            created_by=ctx.actor_user_id,
        )
        session.add(row)
        await session.flush()
        await audit.record(session, ctx, "roster.create", "account_roster", row.id, _audit_details(row))
        return _out(row, user)


async def update_entry(
    db: ClinicDatabase, ctx: ActionContext, entry_id: UUID, body: RosterEntryUpdate
) -> RosterEntryOut:
    require(ctx, Permission.ROSTER_MANAGE)
    fields = body.model_fields_set
    async with db.session() as session:
        row = await _load_entry(session, ctx, entry_id)
        check_version(row.version, body.version)
        changed: list[str] = []

        if body.user_id is not None and body.user_id != row.user_id:
            await load_assignable_user(session, ctx, body.user_id, message=INVALID_USER_MESSAGE)
            row.user_id = body.user_id
            changed.append("user_id")

        if "weekdays" in fields or "on_date" in fields:
            weekdays = [d.value for d in body.weekdays] if body.weekdays else None
            if "weekdays" not in fields:
                weekdays = None if body.on_date is not None else row.weekdays
            on_date = body.on_date if "on_date" in fields else (None if weekdays else row.on_date)
            if (weekdays is None) == (on_date is None):
                raise DomainError(ErrorCode.VALIDATION_FAILED, ONE_KIND_MESSAGE)
            if weekdays != row.weekdays:
                row.weekdays = weekdays
                changed.append("weekdays")
            if on_date != row.on_date:
                row.on_date = on_date
                changed.append("on_date")

        for name, attribute in (("start", "start_time"), ("end", "end_time")):
            value = getattr(body, name)
            if value is not None and parse_hhmm(value) != getattr(row, attribute):
                setattr(row, attribute, parse_hhmm(value))
                changed.append(name)
        if row.start_time == row.end_time:
            raise DomainError(ErrorCode.VALIDATION_FAILED, SAME_TIME_MESSAGE)

        if "note" in fields and (body.note or None) != row.note:
            row.note = body.note or None
            changed.append("note")

        user = await _user_of(session, row)
        if not changed:
            return _out(row, user)
        with lost_race_is_conflict():
            await session.flush()
        details = _audit_details(row)
        details["changed_fields"] = changed
        await audit.record(session, ctx, "roster.update", "account_roster", row.id, details)
        return _out(row, user)


async def delete_entry(db: ClinicDatabase, ctx: ActionContext, entry_id: UUID) -> None:
    require(ctx, Permission.ROSTER_MANAGE)
    async with db.session() as session:
        row = await _load_entry(session, ctx, entry_id)
        details = _audit_details(row)
        await session.delete(row)
        await session.flush()
        await audit.record(session, ctx, "roster.delete", "account_roster", entry_id, details)


async def who_is_on(
    db: ClinicDatabase, clinic_id: UUID, account_id: str, at: datetime
) -> list[OnDutyOperator]:
    """The operators who cover ``account_id`` at ``at``: A to Z by name, each once. No permission: the lookup
    of the routing adapter and of the notification path (it returns id, name and role, like the assignee
    picker).
    Locked users and roles that cannot hold a conversation are left out (see the module docstring)."""
    async with db.session() as session:
        rows = (
            await session.execute(
                select(AccountRoster, UserAccount)
                .join(
                    UserAccount,
                    (UserAccount.clinic_id == AccountRoster.clinic_id)
                    & (UserAccount.id == AccountRoster.user_id),
                )
                .where(
                    AccountRoster.clinic_id == clinic_id,
                    AccountRoster.account_id == account_id,
                    UserAccount.active.is_(True),
                    UserAccount.role.in_(ASSIGNABLE_ROLE_VALUES),
                )
            )
        ).all()
    found: dict[UUID, OnDutyOperator] = {}
    for entry, user in rows:
        if user.id in found:
            continue
        if slot_covers(entry.weekdays, entry.on_date, entry.start_time, entry.end_time, at):
            found[user.id] = OnDutyOperator(id=user.id, name=user.display_name, role=Role(user.role))
    return sorted(found.values(), key=lambda op: (op.name.casefold(), op.id.int))


async def on_duty(db: ClinicDatabase, ctx: ActionContext, account_id: str, at: datetime) -> OnDutyOut:
    """``GET /identities/{id}/on-duty``: who covers the identity at ``at`` (every operator may ask)."""
    require(ctx, Permission.ROSTER_READ)
    async with db.session() as session:
        known = await session.scalar(
            text("SELECT 1 FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :account_id"),
            {"clinic_id": ctx.clinic_id, "account_id": account_id},
        )
    if known is None:
        raise DomainError(ErrorCode.NOT_FOUND, UNKNOWN_IDENTITY_MESSAGE)
    return OnDutyOut(
        account_id=account_id, at=at, operators=await who_is_on(db, ctx.clinic_id, account_id, at)
    )


async def identity_of_patient(db: ClinicDatabase, clinic_id: UUID, patient_id: UUID) -> str | None:
    """The customer-facing identity a patient wrote to most recently (``clinic.conversation.account_id`` of
    the conversation with the latest inbound message), or ``None`` when no conversation of the patient has
    one yet.
    Used by the routing adapter: the care routing asks about a patient, the roster is kept per identity."""
    async with db.session() as session:
        found = await session.scalar(
            text(
                "SELECT c.account_id FROM clinic.conversation c "
                "JOIN agent.accounts a ON a.clinic_id = c.clinic_id AND a.id = c.account_id "
                "WHERE c.clinic_id = :clinic_id AND c.patient_id = :patient_id AND a.purpose = 'customer' "
                "ORDER BY c.last_inbound_at DESC NULLS LAST, c.id LIMIT 1"
            ),
            {"clinic_id": clinic_id, "patient_id": patient_id},
        )
    return None if found is None else str(found)
