"""Channel switchboard and kill switch (package C2 implements; C1 reads the same settings)."""

from __future__ import annotations

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin import ChannelSettingsOut, ChannelSettingsUpdate, KillSwitchRequest
from pema_contracts.channel import ChannelKind

router = admin_router("channels", "admin-channels")


@router.get("", response_model=list[ChannelSettingsOut], summary="Channel settings and state")
async def list_channels() -> list[ChannelSettingsOut]:
    not_implemented()


@router.get(
    "/{channel}",
    response_model=ChannelSettingsOut,
    summary="One channel (zalo_personal includes kill switch, daily cap, bridge state)",
)
async def get_channel(channel: ChannelKind) -> ChannelSettingsOut:
    not_implemented()


@router.put("/{channel}", response_model=ChannelSettingsOut, summary="Update channel settings")
async def update_channel(channel: ChannelKind, body: ChannelSettingsUpdate) -> ChannelSettingsOut:
    not_implemented()


@router.post(
    "/{channel}/kill-switch",
    response_model=ChannelSettingsOut,
    summary="Turn the proactive-send kill switch on or off (audited)",
)
async def set_kill_switch(channel: ChannelKind, body: KillSwitchRequest) -> ChannelSettingsOut:
    not_implemented()
