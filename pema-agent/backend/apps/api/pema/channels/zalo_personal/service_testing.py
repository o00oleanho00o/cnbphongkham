"""In-memory ``C2Services`` for the route tests (import in tests only).

The routers are thin: they authorise, call the manager/stores and answer. ``build_test_rig`` wires the REAL
``AccountManager``, ``QrLoginManager``, ``CredentialVault`` and ``BridgeEventHandler`` over fakes (a fake
bridge, in memory stores, a recording audit sink), so a route test exercises the same code path production
does without a database or a network. The real repository of the channel switchboard has database tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request

from pema.channels.pipeline_testing import FakeConversation
from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.bridge_events import BridgeEventHandler
from pema.channels.zalo_personal.channel_settings import (
    ChannelSettings,
    default_settings,
)
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.friend_request_store import FriendRequestRow
from pema.channels.zalo_personal.incoming_message_router import (
    RespondDecision,
    RouterDeps,
)
from pema.channels.zalo_personal.qr_login_manager import build_qr_manager
from pema.channels.zalo_personal.services import C2Services
from pema.channels.zalo_personal.testing import FakeBridge
from pema.channels.zalo_personal.zalo_message_parser import describe_for_history
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.admin import BridgeState, ChannelSettingsUpdate
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.conversation import StoredMessage
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission, Role
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    InMemoryAccountStore,
    InMemoryAgentStore,
    fake_agent_profile,
)

BRIDGE_SECRET = "synthetic-bridge-secret-0123456789"  # noqa: S105 - a fake secret


@dataclass
class MemorySettings:
    """``ChannelSettingsRepository`` semantics in memory (optimistic version, kill switch, bridge report)."""

    rows: dict[ChannelKind, ChannelSettings] = field(default_factory=dict[ChannelKind, ChannelSettings])
    audit: list[tuple[str, ChannelKind]] = field(default_factory=list[tuple[str, ChannelKind]])

    def _current(self, channel: ChannelKind) -> ChannelSettings:
        return self.rows.get(channel, default_settings(channel))

    async def get_policy(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        return self._current(channel)

    async def get(self, clinic_id: UUID, channel: ChannelKind) -> ChannelSettings:
        return self._current(channel)

    async def list_all(self, clinic_id: UUID) -> list[ChannelSettings]:
        return [self._current(kind) for kind in ChannelKind]

    async def update(
        self, ctx: ActionContext, channel: ChannelKind, patch: ChannelSettingsUpdate
    ) -> ChannelSettings:
        current = self._current(channel)
        if current.version != patch.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "Cài đặt kênh đã được người khác thay đổi.")
        changes: dict[str, object] = {}
        if patch.enabled is not None:
            changes["enabled"] = patch.enabled
        if patch.daily_cap is not None:
            changes["daily_cap"] = patch.daily_cap
        updated = replace(current, version=current.version + 1, updated_at=datetime.now(UTC), **changes)  # type: ignore[arg-type]
        self.rows[channel] = updated
        self.audit.append(("channel.update", channel))
        return updated

    async def set_kill_switch(
        self, ctx: ActionContext, channel: ChannelKind, *, on: bool, reason: str | None
    ) -> ChannelSettings:
        current = self._current(channel)
        updated = replace(
            current,
            kill_switch_on=on,
            kill_switch_reason=reason,
            kill_switch_changed_at=datetime.now(UTC),
            version=current.version + 1,
        )
        self.rows[channel] = updated
        self.audit.append(("channel.kill_switch", channel))
        return updated

    async def apply_bridge_report(
        self,
        ctx: ActionContext,
        channel: ChannelKind,
        *,
        bridge_state: BridgeState,
        kill_switch_reason: str | None,
    ) -> ChannelSettings:
        current = self._current(channel)
        updated = replace(current, bridge_state=bridge_state, version=current.version + 1)
        if kill_switch_reason is not None:
            updated = replace(updated, kill_switch_on=True, kill_switch_reason=kill_switch_reason)
        self.rows[channel] = updated
        self.audit.append(("channel.bridge_report", channel))
        return updated


@dataclass
class MemoryFriends:
    rows: dict[tuple[str, str], FriendRequestRow] = field(
        default_factory=dict[tuple[str, str], FriendRequestRow]
    )

    async def upsert_friend_request(self, clinic_id: UUID, row: FriendRequestRow) -> None:
        self.rows[(row.account_id, row.from_uid)] = row

    async def cap_nhat_ho_so_friend_request(
        self, clinic_id: UUID, account_id: str, from_uid: str, sender_name: str | None, avatar_url: str | None
    ) -> None:
        current = self.rows.get((account_id, from_uid))
        if current is not None:
            self.rows[(account_id, from_uid)] = replace(
                current, sender_name=sender_name, avatar_url=avatar_url
            )

    async def xoa_friend_request(self, clinic_id: UUID, account_id: str, from_uid: str) -> bool:
        return self.rows.pop((account_id, from_uid), None) is not None

    async def list_friend_requests(self, clinic_id: UUID, account_id: str) -> list[FriendRequestRow]:
        return sorted(
            (r for (acc, _), r in self.rows.items() if acc == account_id),
            key=lambda r: r.received_at,
            reverse=True,
        )

    async def lay_friend_request_qua_han(
        self, clinic_id: UUID, account_id: str, truoc_moc: datetime
    ) -> list[FriendRequestRow]:
        return [
            r for r in await self.list_friend_requests(clinic_id, account_id) if r.received_at <= truoc_moc
        ]


@dataclass
class RecordingAudit:
    records: list[tuple[str, str, str | None]] = field(default_factory=list[tuple[str, str, str | None]])

    async def record(
        self,
        ctx: ActionContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.records.append((action, entity_type, entity_id))


class MemoryDedupe:
    def __init__(self) -> None:
        self.seen: set[tuple[str, str]] = set()

    async def first_time(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        key = (account_id, update_id)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


@dataclass
class Batched:
    clinic_id: UUID
    thread_key: str
    msg: InboundMessage


@dataclass
class TestRig:
    services: C2Services
    bridge: FakeBridge
    accounts: InMemoryAccountStore
    settings: MemorySettings
    friends: MemoryFriends
    audit: RecordingAudit
    registry: InMemoryChannelRegistry
    conversation: FakeConversation
    batched: list[Batched]
    denied: set[Permission]
    asked: list[Permission]
    flag: dict[str, bool]
    listeners_called: list[tuple[UUID, str, str]]

    __test__ = False  # not a pytest class

    def set_flag(self, value: bool) -> None:
        self.flag["on"] = value


def build_test_rig(
    *,
    accounts: list[AccountConfig] | None = None,
    channel_enabled: bool = True,
    flag: bool = True,
    clinic_id: UUID = FAKE_CLINIC_ID,
) -> TestRig:
    """The ``C2Services`` container over fakes, plus handles on every fake. Install ``rig.services`` as
    ``app.state.c2_services`` of a FastAPI app to exercise the routers."""
    account_store = InMemoryAccountStore(*(accounts or []))
    agents = InMemoryAgentStore(fake_agent_profile(id="default", name="Default", is_default=True))
    bridge = FakeBridge()
    registry = InMemoryChannelRegistry()
    settings = MemorySettings()
    if channel_enabled:
        settings.rows[ChannelKind.ZALO_PERSONAL] = replace(
            default_settings(ChannelKind.ZALO_PERSONAL), enabled=True, version=1
        )
    friends = MemoryFriends()
    audit = RecordingAudit()
    conversation = FakeConversation()
    batched: list[Batched] = []
    flag_box = {"on": flag}
    denied: set[Permission] = set()
    asked: list[Permission] = []
    blocked_calls: list[tuple[UUID, str, str]] = []

    vault = CredentialVault(account_store, encrypt=lambda s: "enc:" + s, decrypt=lambda s: s[4:])
    manager = AccountManager(
        accounts=account_store,
        vault=vault,
        bridge=bridge,
        registry=registry,
        policy_reader=settings,
        flag_enabled=lambda: flag_box["on"],
        bridge_secret=lambda: BRIDGE_SECRET,
    )

    qr = build_qr_manager(bridge, manager, account_store, poll_seconds=0.0)

    class Names:
        def __init__(self) -> None:
            self.names: dict[str, str] = {}

        async def has_display_name(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
            return thread_id in self.names

        async def set_thread_display_name(
            self, clinic_id: UUID, account_id: str, thread_id: str, name: str
        ) -> None:
            self.names[thread_id] = name

    class Contacts:
        async def record_contact_activity(
            self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
        ) -> None:
            return None

    class Threads:
        async def record_thread_activity(self, clinic_id: UUID, **fields: object) -> None:
            return None

        async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
            return True

    async def record_incoming(cid: UUID, msg: InboundMessage, *, luu_anh_ngay: bool) -> int:
        row_id = await conversation.append_message(
            cid,
            msg.account_id,
            msg.thread_id,
            StoredMessage(role="user", content=describe_for_history(msg), sender_name=msg.sender_name),
        )
        msg.history_row_id = row_id
        return row_id

    class Batcher:
        async def enqueue_message(self, cid: UUID, thread_key: str, msg: InboundMessage) -> bool:
            batched.append(Batched(cid, thread_key, msg))
            return True

    router_deps = RouterDeps(
        accounts=account_store,
        contacts=Contacts(),
        threads=Threads(),
        thread_names=Names(),
        should_respond=lambda config, msg, enabled: RespondDecision(respond=True),
        record_incoming=record_incoming,
        report_anomalies=lambda account_id, msg: None,
        batcher=Batcher(),
        busy_notifier=None,
        persist_images=None,
        attach_images=None,
    )

    class Blocked:
        async def on_channel_blocked(self, cid: UUID, account_id: str, state: str) -> None:
            blocked_calls.append((cid, account_id, state))

    events = BridgeEventHandler(
        manager=manager,
        router_deps=router_deps,
        vault=vault,
        friends=friends,
        settings=settings,  # type: ignore[arg-type]
        dedupe=MemoryDedupe(),
        listeners=[Blocked()],
    )

    async def authorize(request: Request, permission: Permission) -> ActionContext:
        asked.append(permission)
        if request.headers.get("x-test-anonymous") == "1":
            raise DomainError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập.")
        if permission in denied:
            raise DomainError(ErrorCode.FORBIDDEN, "Không đủ quyền.")
        return ActionContext(
            clinic_id=clinic_id, actor_type=ActorType.USER, actor_role=Role.OWNER, source=ActionSource.UI
        )

    services = C2Services(
        flag_enabled=lambda: flag_box["on"],
        bridge_secret=lambda: BRIDGE_SECRET,
        authorize=authorize,
        accounts=account_store,
        agents=agents,
        vault=vault,
        manager=manager,
        qr=qr,
        friends=friends,
        settings=settings,  # type: ignore[arg-type]
        audit=audit,
        registry=registry,
        events=events,
        clinic_id=lambda: clinic_id,
    )
    return TestRig(
        services=services,
        bridge=bridge,
        accounts=account_store,
        settings=settings,
        friends=friends,
        audit=audit,
        registry=registry,
        conversation=conversation,
        batched=batched,
        denied=denied,
        asked=asked,
        flag=flag_box,
        listeners_called=blocked_calls,
    )
