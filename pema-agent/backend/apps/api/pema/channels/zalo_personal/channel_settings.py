"""Channel switchboard of the personal account: the flag, the kill switch, the caps (table
``clinic.channel_setting``).

New module (no zalo-agent source: the original had no kill switch table; the daily cap lived in the tuning key
``SCHEDULER_MAX_PROACTIVE_PER_DAY``). Two readers of the SAME row, one per database role:

* ``ChannelSettingsRepository`` (role ``be_app``, API process): full read, optimistic update, kill
switch, bridge
  state. Every mutation writes ``clinic.audit_log`` in the SAME transaction (actor user for the admin routes,
  actor ``system`` for what the bridge reports);
* ``WorkerChannelPolicyReader`` (role ``agent_worker``): reads the view ``clinic_agent.channel_policy``,
the only
  door of the worker into this table (migration 0003; no bridge state, no reason, no actor).

The kill switch is checked on EVERY proactive send by reading the row again (no cache): flipping it in
the admin
UI is effective for the next message, in every process.

A missing row means "feature off": ``enabled=False`` (fail closed). The first ``PUT
/admin/channels/{channel}``
creates it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, time
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.channels.zalo_personal.audit_writer import write_audit
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.admin import BridgeState, ChannelSettingsUpdate
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode

AUTO_KILL_REASON_BLOCKED = "bridge_blocked"
AUTO_KILL_REASON_LOGGED_OUT = "bridge_logged_out"
AUTO_KILL_REASON_SESSION_DEAD = "bridge_session_dead"


@dataclass(frozen=True)
class ChannelSettings:
    channel: ChannelKind
    enabled: bool = False
    kill_switch_on: bool = False
    kill_switch_reason: str | None = None
    kill_switch_changed_at: datetime | None = None
    kill_switch_changed_by: UUID | None = None
    daily_cap: int | None = None
    send_window_start: time | None = None
    send_window_end: time | None = None
    min_gap_seconds: int = 0
    max_gap_seconds: int = 0
    requires_friend: bool = False
    bridge_state: BridgeState | None = None
    updated_at: datetime | None = None
    version: int = 0
    """0 = the row does not exist yet."""


class ChannelPolicyReader(Protocol):
    """What the sending side needs: the current policy row of a channel."""

    async def get_policy(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings: ...


_COLUMNS = (
    "channel, enabled, kill_switch_on, kill_switch_reason, kill_switch_changed_at, kill_switch_changed_by, "
    "daily_cap, send_window_start, send_window_end, min_gap_seconds, max_gap_seconds, requires_friend, "
    "bridge_state, updated_at, version"
)
_WORKER_COLUMNS = (
    "channel, enabled, kill_switch_on, daily_cap, send_window_start, send_window_end, min_gap_seconds, "
    "max_gap_seconds, requires_friend"
)


def _row_to_settings(mapping: Mapping[Any, Any]) -> ChannelSettings:
    row: dict[str, Any] = dict(mapping)
    bridge_state = row.get("bridge_state")
    return ChannelSettings(
        channel=ChannelKind(row["channel"]),
        enabled=bool(row["enabled"]),
        kill_switch_on=bool(row["kill_switch_on"]),
        kill_switch_reason=row.get("kill_switch_reason"),
        kill_switch_changed_at=row.get("kill_switch_changed_at"),
        kill_switch_changed_by=row.get("kill_switch_changed_by"),
        daily_cap=row.get("daily_cap"),
        send_window_start=row.get("send_window_start"),
        send_window_end=row.get("send_window_end"),
        min_gap_seconds=int(row.get("min_gap_seconds") or 0),
        max_gap_seconds=int(row.get("max_gap_seconds") or 0),
        requires_friend=bool(row.get("requires_friend", False)),
        bridge_state=BridgeState(bridge_state) if bridge_state else None,
        updated_at=row.get("updated_at"),
        version=int(row.get("version") or 0),
    )


def _parse_hhmm(value: str | None) -> time | None:
    if value is None:
        return None
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def default_settings(channel: ChannelKind) -> ChannelSettings:
    """The row that does not exist yet. Personal accounts require a friend by default."""
    return ChannelSettings(channel=channel, requires_friend=channel is ChannelKind.ZALO_PERSONAL)


class WorkerChannelPolicyReader:
    """Reads ``clinic_agent.channel_policy`` as role ``agent_worker`` (no privilege on ``clinic.*``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_policy(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                text(f"SELECT {_WORKER_COLUMNS} FROM clinic_agent.channel_policy WHERE channel = :channel"),  # noqa: S608
                {"channel": channel.value},
            )
            row = result.mappings().first()
        if row is None:
            return default_settings(channel)
        return _row_to_settings(row)


class ChannelSettingsRepository:
    """Role ``be_app``. Also a ``ChannelPolicyReader`` (the API process sends too, e.g. a friend accept)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_policy(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        return await self.get(clinic_id, channel)

    async def get(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        async with self._db.session(clinic_id) as session:
            return await self._load(session, channel)

    async def list_all(self, clinic_id: UUID) -> list[ChannelSettings]:
        """All three channels; a channel without a row appears with its defaults (``version == 0``)."""
        async with self._db.session(clinic_id) as session:
            return [await self._load(session, kind) for kind in ChannelKind]

    async def update(
        self, ctx: ActionContext, channel: ChannelKind, patch: ChannelSettingsUpdate
    ) -> ChannelSettings:
        """Optimistic update (``patch.version`` must be the stored one; ``0`` creates the row)."""
        changes: dict[str, object] = {}
        if patch.enabled is not None:
            changes["enabled"] = patch.enabled
        if patch.daily_cap is not None:
            changes["daily_cap"] = patch.daily_cap
        if patch.send_window_start is not None:
            changes["send_window_start"] = _parse_hhmm(patch.send_window_start)
        if patch.send_window_end is not None:
            changes["send_window_end"] = _parse_hhmm(patch.send_window_end)
        if patch.min_gap_seconds is not None:
            changes["min_gap_seconds"] = patch.min_gap_seconds
        if patch.max_gap_seconds is not None:
            changes["max_gap_seconds"] = patch.max_gap_seconds

        async with self._db.session(ctx.clinic_id) as session:
            current = await self._load(session, channel)
            if current.version != patch.version:
                raise DomainError(ErrorCode.VERSION_CONFLICT, "Cài đặt kênh đã được người khác thay đổi.")
            min_gap = int(changes.get("min_gap_seconds", current.min_gap_seconds))  # type: ignore[call-overload]
            max_gap = int(changes.get("max_gap_seconds", current.max_gap_seconds))  # type: ignore[call-overload]
            if max_gap < min_gap:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, "Khoảng nghỉ tối đa phải không nhỏ hơn tối thiểu."
                )
            await self._ensure_row(session, ctx.clinic_id, channel)
            if changes:
                assignments = ", ".join(f"{column} = :{column}" for column in changes)
                # A row created by this very call starts at version 1: no bump (``current.version == 0``).
                params: dict[str, object] = {
                    **changes,
                    "channel": channel.value,
                    "actor": ctx.actor_user_id,
                    "bump": 1 if current.version else 0,
                }
                await session.execute(
                    text(
                        f"UPDATE clinic.channel_setting SET {assignments}, version = version + :bump, "  # noqa: S608
                        "updated_by = :actor WHERE channel = :channel"
                    ),
                    params,
                )
            await write_audit(
                session, ctx, "channel.update", "channel_setting", channel.value, {"fields": sorted(changes)}
            )
            return await self._load(session, channel)

    async def set_kill_switch(
        self, ctx: ActionContext, channel: ChannelKind, *, on: bool, reason: str | None
    ) -> ChannelSettings:
        """Audited. Turning it ON must never need the ``version`` of the form: speed matters more."""
        async with self._db.session(ctx.clinic_id) as session:
            await self._ensure_row(session, ctx.clinic_id, channel)
            await session.execute(
                text(
                    "UPDATE clinic.channel_setting SET kill_switch_on = :on, kill_switch_reason = :reason, "
                    "kill_switch_changed_at = now(), kill_switch_changed_by = :actor, "
                    "version = version + 1, updated_by = :actor WHERE channel = :channel"
                ),
                {"on": on, "reason": reason, "actor": ctx.actor_user_id, "channel": channel.value},
            )
            await write_audit(
                session,
                ctx,
                "channel.kill_switch",
                "channel_setting",
                channel.value,
                {"on": on, "has_reason": bool(reason)},
            )
            return await self._load(session, channel)

    async def apply_bridge_report(
        self,
        ctx: ActionContext,
        channel: ChannelKind,
        *,
        bridge_state: BridgeState,
        kill_switch_reason: str | None,
    ) -> ChannelSettings:
        """The bridge says the account is blocked, logged out or its session is dead (or connected again).

        ``bridge_state`` is stored. When ``kill_switch_reason`` is given the kill switch is turned ON in
        the same
        transaction: every proactive send is then rejected with ``channel_kill_switch_on`` in every
        process, which
        is the signal that moves the scheduled jobs to manual sending. A reconnect NEVER turns the kill switch
        off by itself: a human decides when sending resumes.
        """
        async with self._db.session(ctx.clinic_id) as session:
            await self._ensure_row(session, ctx.clinic_id, channel)
            if kill_switch_reason is not None:
                await session.execute(
                    text(
                        "UPDATE clinic.channel_setting SET bridge_state = :state, kill_switch_on = true, "
                        "kill_switch_reason = :reason, kill_switch_changed_at = now(), "
                        "kill_switch_changed_by = NULL, version = version + 1 WHERE channel = :channel"
                    ),
                    {"state": bridge_state.value, "reason": kill_switch_reason, "channel": channel.value},
                )
            else:
                await session.execute(
                    text(
                        "UPDATE clinic.channel_setting SET bridge_state = :state, version = version + 1 "
                        "WHERE channel = :channel"
                    ),
                    {"state": bridge_state.value, "channel": channel.value},
                )
            await write_audit(
                session,
                ctx,
                "channel.bridge_report",
                "channel_setting",
                channel.value,
                {"bridge_state": bridge_state.value, "kill_switch_engaged": kill_switch_reason is not None},
            )
            return await self._load(session, channel)

    async def clinic_slug(self, clinic_id: UUID) -> str | None:
        async with self._db.session(clinic_id) as session:
            row = (
                await session.execute(
                    text("SELECT slug FROM clinic.clinic WHERE id = :clinic_id"), {"clinic_id": clinic_id}
                )
            ).scalar()
        return str(row) if row is not None else None

    # ------------------------------------------------------------------------------------------ helpers

    async def _load(self, session: AsyncSession, channel: ChannelKind) -> ChannelSettings:
        result = await session.execute(
            text(f"SELECT {_COLUMNS} FROM clinic.channel_setting WHERE channel = :channel"),  # noqa: S608
            {"channel": channel.value},
        )
        row = result.mappings().first()
        return default_settings(channel) if row is None else _row_to_settings(row)

    async def _ensure_row(self, session: AsyncSession, clinic_id: UUID, channel: ChannelKind) -> None:
        await session.execute(
            text(
                "INSERT INTO clinic.channel_setting (clinic_id, channel, requires_friend) "
                "VALUES (:clinic_id, :channel, :requires_friend) ON CONFLICT (clinic_id, channel) DO NOTHING"
            ),
            {
                "clinic_id": clinic_id,
                "channel": channel.value,
                "requires_friend": channel is ChannelKind.ZALO_PERSONAL,
            },
        )


def with_window(settings: ChannelSettings, start: str | None, end: str | None) -> ChannelSettings:
    """Test helper: a copy with a send window given as ``HH:MM`` strings."""
    return replace(settings, send_window_start=_parse_hhmm(start), send_window_end=_parse_hhmm(end))
