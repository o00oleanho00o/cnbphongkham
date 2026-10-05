"""Channel switchboard and kill switch (package C2 implements; C1 reads the same settings).

The kill switch is the instant emergency stop of proactive sends: the row of ``clinic.channel_setting``
is updated
(every process reads it again on its next send, no cache) AND the bridge is told at once (it enforces the
switch on
its own, as a second layer). Both writes are audited. Turning the channel flag ``enabled`` off stops
every account
of the personal channel and drops the credentials from the bridge's memory (the stored encrypted
credential stays,
so switching it on again needs no new QR scan unless Zalo logged the account out).
"""

from __future__ import annotations

from fastapi import Request

from pema.api.deps import admin_router
from pema.channels.zalo_personal.bridge_client import KillSwitchState
from pema.channels.zalo_personal.channel_settings import ChannelSettings
from pema.channels.zalo_personal.services import get_c2
from pema.shared.logger import create_logger
from pema_contracts.admin import ChannelSettingsOut, ChannelSettingsUpdate, KillSwitchRequest
from pema_contracts.channel import ChannelKind
from pema_contracts.roles import Permission

router = admin_router("channels", "admin-channels")

log = create_logger("admin.channels")


def to_out(settings: ChannelSettings) -> ChannelSettingsOut:
    return ChannelSettingsOut(
        channel=settings.channel,
        enabled=settings.enabled,
        kill_switch_on=settings.kill_switch_on,
        kill_switch_reason=settings.kill_switch_reason,
        kill_switch_changed_at=settings.kill_switch_changed_at,
        kill_switch_changed_by=settings.kill_switch_changed_by,
        daily_cap=settings.daily_cap,
        proactive_sent_today=0,
        send_window_start=settings.send_window_start.strftime("%H:%M")
        if settings.send_window_start
        else None,
        send_window_end=settings.send_window_end.strftime("%H:%M") if settings.send_window_end else None,
        min_gap_seconds=settings.min_gap_seconds,
        max_gap_seconds=settings.max_gap_seconds,
        requires_friend=settings.requires_friend,
        bridge_state=settings.bridge_state if settings.channel is ChannelKind.ZALO_PERSONAL else None,
        updated_at=settings.updated_at,
        version=settings.version,
    )


@router.get("", response_model=list[ChannelSettingsOut], summary="Channel settings and state")
async def list_channels(request: Request) -> list[ChannelSettingsOut]:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_CHANNELS)
    return [to_out(s) for s in await services.settings.list_all(ctx.clinic_id)]


@router.get(
    "/{channel}",
    response_model=ChannelSettingsOut,
    summary="One channel (zalo_personal includes kill switch, daily cap, bridge state)",
)
async def get_channel(channel: ChannelKind, request: Request) -> ChannelSettingsOut:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_CHANNELS)
    return to_out(await services.settings.get(ctx.clinic_id, channel))


@router.put("/{channel}", response_model=ChannelSettingsOut, summary="Update channel settings")
async def update_channel(
    channel: ChannelKind, body: ChannelSettingsUpdate, request: Request
) -> ChannelSettingsOut:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_CHANNELS)
    before = await services.settings.get(ctx.clinic_id, channel)
    updated = await services.settings.update(ctx, channel, body)

    if channel is ChannelKind.ZALO_PERSONAL and body.enabled is not None and body.enabled != before.enabled:
        if not body.enabled:
            # The flag is the "off means no traffic" switch: stop everything NOW.
            await services.manager.stop_all_accounts()
        else:
            # Nothing starts without a stored credential (a QR scan); an account that has one comes back.
            try:
                await services.manager.start_all_accounts()
            except Exception as err:
                log.error("starting the personal accounts after enabling the channel failed", err=err)
    return to_out(updated)


@router.post(
    "/{channel}/kill-switch",
    response_model=ChannelSettingsOut,
    summary="Turn the proactive-send kill switch on or off (audited)",
)
async def set_kill_switch(
    channel: ChannelKind, body: KillSwitchRequest, request: Request
) -> ChannelSettingsOut:
    services = get_c2(request)
    ctx = await services.authorize(request, Permission.ADMIN_KILL_SWITCH)
    # Database first: it is authoritative, audited, and read by every process on its next send.
    updated = await services.settings.set_kill_switch(ctx, channel, on=body.on, reason=body.reason)
    if channel is ChannelKind.ZALO_PERSONAL:
        try:
            await services.manager.push_kill_switch(
                KillSwitchState(on=body.on, scope="proactive", reason=body.reason)
            )
        except Exception as err:
            # The row already blocks every send of the Python side; the bridge keeps its own breaker and picks
            # the state up again on the next account start.
            log.warning("kill switch saved but the bridge could not be told", on=body.on, err=err)
    return to_out(updated)
