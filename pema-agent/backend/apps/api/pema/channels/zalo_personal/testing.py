"""Test doubles of the personal-account channel (import in tests only, like ``pema_contracts.testing``).

``FakeZaloApi`` stands in for the zca-js ``API`` object: it records every call and never touches a network.
The suite runs with ``--import-mode=importlib`` and no ``tests`` package, so shared fakes live in the package.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pema.channels.zalo_personal.bridge_client import (
    BridgeAccountState,
    BridgeQrStatus,
    KillSwitchState,
    ReceiptParams,
    ZaloApi,
    ZaloBridgeError,
)
from pema.channels.zalo_personal.channel_settings import ChannelSettings
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.proactive_gate import ProactiveGate
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import ChannelKind, QuoteRef, TextStyle, ThreadKind
from pema_contracts.common import JsonObject
from pema_contracts.scheduler import ProactiveSendGuard
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config


@dataclass
class SentMessage:
    text: str
    thread_id: str
    thread_type: ThreadKind
    styles: tuple[TextStyle, ...]
    quote: QuoteRef | None
    proactive: bool
    mentions: tuple[JsonObject, ...] = ()


@dataclass
class FakeZaloApi:
    """Records every call. ``fail_send_with`` makes ``send_message`` raise (one entry per call, in order)."""

    account: str = "acc-1"
    own_id: str = "self-1"
    sent: list[SentMessage] = field(default_factory=list[SentMessage])
    typing: list[tuple[str, ThreadKind]] = field(default_factory=list[tuple[str, ThreadKind]])
    delivered: list[tuple[bool, tuple[ReceiptParams, ...], ThreadKind]] = field(
        default_factory=list[tuple[bool, tuple[ReceiptParams, ...], ThreadKind]]
    )
    seen: list[tuple[tuple[ReceiptParams, ...], ThreadKind]] = field(
        default_factory=list[tuple[tuple[ReceiptParams, ...], ThreadKind]]
    )
    reactions: list[tuple[str, str, str, ThreadKind]] = field(
        default_factory=list[tuple[str, str, str, ThreadKind]]
    )
    user_info: dict[str, JsonObject] = field(default_factory=dict[str, JsonObject])
    friends: list[JsonObject] = field(default_factory=list[JsonObject])
    accepted: list[str] = field(default_factory=list[str])
    rejected: list[str] = field(default_factory=list[str])
    fail_send_with: list[ZaloBridgeError] = field(default_factory=list[ZaloBridgeError])
    fail_accept_for: set[str] = field(default_factory=set[str])
    send_attempts: int = 0
    """Every call of ``send_message``, failed or not."""

    @property
    def account_id(self) -> str:
        return self.account

    def get_own_id(self) -> str:
        return self.own_id

    async def send_message(
        self,
        *,
        text: str,
        thread_id: str,
        thread_type: ThreadKind,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        mentions: Sequence[JsonObject] = (),
        proactive: bool = False,
    ) -> JsonObject:
        self.send_attempts += 1
        if self.fail_send_with:
            raise self.fail_send_with.pop(0)
        self.sent.append(
            SentMessage(text, thread_id, thread_type, tuple(styles), quote, proactive, tuple(mentions))
        )
        return {"msg_id": f"sent-{len(self.sent)}"}

    async def send_typing_event(self, thread_id: str, thread_type: ThreadKind) -> None:
        self.typing.append((thread_id, thread_type))

    async def send_delivered_event(
        self, is_seen: bool, params: Sequence[ReceiptParams], thread_type: ThreadKind
    ) -> None:
        self.delivered.append((is_seen, tuple(params), thread_type))

    async def send_seen_event(self, params: Sequence[ReceiptParams], thread_type: ThreadKind) -> None:
        self.seen.append((tuple(params), thread_type))

    async def add_reaction(
        self, icon_key: str, *, msg_id: str, cli_msg_id: str, thread_id: str, thread_type: ThreadKind
    ) -> None:
        self.reactions.append((icon_key, msg_id, thread_id, thread_type))

    async def get_user_info(self, uid: str) -> JsonObject:
        return self.user_info.get(uid, {"changed_profiles": {}})

    async def get_all_friends(self) -> list[JsonObject]:
        return list(self.friends)

    async def accept_friend_request(self, uid: str) -> None:
        if uid in self.fail_accept_for:
            raise ZaloBridgeError("zalo_rejected", "synthetic failure", code=1)
        self.accepted.append(uid)

    async def reject_friend_request(self, uid: str) -> None:
        self.rejected.append(uid)

    async def get_group_info(self, thread_id: str) -> JsonObject:
        return {"gridInfoMap": {thread_id: {"name": "Synthetic group"}}}

    async def send_attachment(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        filename: str,
        data: bytes,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return {"msg_id": "att-1"}

    async def send_video(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        video_url: str,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return {"msg_id": "vid-1"}


_check: ZaloApi = FakeZaloApi()


@dataclass
class StaticPolicyReader:
    """``ChannelPolicyReader`` over a mutable row: change ``settings`` to flip the kill switch."""

    settings: ChannelSettings = field(
        default_factory=lambda: ChannelSettings(channel=ChannelKind.ZALO_PERSONAL, enabled=True, version=1)
    )
    reads: int = 0

    async def get_policy(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        self.reads += 1
        return self.settings


def make_personal_channel(
    api: ZaloApi | None = None,
    *,
    config: AccountConfig | None = None,
    reader: StaticPolicyReader | None = None,
    flag: bool = True,
    counter: ProactiveSendGuard | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    uniform: Callable[[float, float], float] | None = None,
    secret: str | None = "bridge-test-secret-0123456789",  # noqa: S107 - a fake secret
) -> ZaloPersonalChannel:
    """A ``ZaloPersonalChannel`` over fakes. The policy row defaults to ``enabled`` with no kill switch."""
    fake_api = api or FakeZaloApi()
    cfg = config or fake_account_config(channel=ChannelKind.ZALO_PERSONAL, id=fake_api.account_id)
    extra: dict[str, object] = {}
    if now is not None:
        extra["now"] = now
    if sleep is not None:
        extra["sleep"] = sleep
    if uniform is not None:
        extra["uniform"] = uniform
    gate = ProactiveGate(
        clinic_id=FAKE_CLINIC_ID,
        account_id=cfg.id,
        reader=reader or StaticPolicyReader(),
        api=fake_api,
        flag_enabled=lambda: flag,
        counter=counter,
        **extra,  # type: ignore[arg-type]
    )
    return ZaloPersonalChannel(
        clinic_id_str=str(FAKE_CLINIC_ID), config=cfg, api=fake_api, gate=gate, bridge_secret=lambda: secret
    )


@dataclass
class FakeBridge:
    """``BridgeGateway`` in memory: records every call, never touches a network."""

    own_id: str = "self-1"
    states: dict[str, str] = field(default_factory=dict[str, str])
    started: list[tuple[str, JsonObject, KillSwitchState]] = field(
        default_factory=list[tuple[str, JsonObject, KillSwitchState]]
    )
    stopped: list[str] = field(default_factory=list[str])
    stop_all_calls: int = 0
    kill_switch: KillSwitchState | None = None
    qr_started: list[str] = field(default_factory=list[str])
    qr_answers: list[BridgeQrStatus] = field(default_factory=list[BridgeQrStatus])
    fail_start: ZaloBridgeError | None = None
    before_start_returns: Callable[[], None] | None = None
    apis: dict[str, FakeZaloApi] = field(default_factory=dict[str, FakeZaloApi])

    async def start_account(
        self, account_id: str, *, credential: JsonObject, kill_switch: KillSwitchState
    ) -> str:
        if self.fail_start is not None:
            raise self.fail_start
        self.started.append((account_id, credential, kill_switch))
        self.kill_switch = kill_switch
        self.states[account_id] = "connected"
        if self.before_start_returns is not None:
            self.before_start_returns()
        return self.own_id

    async def stop_account(self, account_id: str) -> None:
        self.stopped.append(account_id)
        self.states[account_id] = "stopped"

    async def stop_all(self) -> None:
        self.stop_all_calls += 1
        for key in self.states:
            self.states[key] = "stopped"

    async def get_state(self, account_id: str) -> BridgeAccountState:
        state = self.states.get(account_id, "stopped")
        return BridgeAccountState(
            account_id=account_id, state=state, own_id=self.own_id if state == "connected" else ""
        )

    async def start_qr_login(self, account_id: str) -> BridgeQrStatus:
        self.qr_started.append(account_id)
        return self.qr_answers.pop(0) if self.qr_answers else BridgeQrStatus(state="starting")

    async def get_qr_login(self, account_id: str) -> BridgeQrStatus:
        return self.qr_answers.pop(0) if self.qr_answers else BridgeQrStatus(state="idle")

    async def set_kill_switch(self, state: KillSwitchState) -> None:
        self.kill_switch = state

    def account_api(self, account_id: str, own_id: str = "") -> ZaloApi:
        api = self.apis.get(account_id)
        if api is None:
            api = FakeZaloApi(account=account_id, own_id=own_id or self.own_id)
            self.apis[account_id] = api
        return api
