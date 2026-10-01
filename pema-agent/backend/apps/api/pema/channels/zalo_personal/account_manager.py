# ported from: src/zalo/account-manager.ts
"""Vòng đời của các account đang chạy. Đường đi của tin nhắn nằm ở ``incoming_message_router`` (lọc + ghi) và
``message_turn_processor`` (lượt agent + trả lời).

Forced deviations:

* ``RunningAccount.kenh`` (a ``KenhLuot`` record) is a ``ZaloPersonalChannel`` registered in the shared
  ``InMemoryChannelRegistry`` of package A (``getRunningAccountKenh`` becomes ``registry.get_running``),
  keyed by
  ``(clinic_id, account_id)``. Only personal accounts are managed here; the Bot accounts are started by
  ``pema.channels.zalo_bot.bot_account_runner`` (package C1) and register in the SAME registry.
* zca-js lives in the Node bridge. ``start_account`` hands the stored credential to the bridge
(``/start``), the
  bridge owns the listener and reconnect. The reconnect planner and the listener moved with it.
* a process-level flag (``PEMA_ZALO_PERSONAL_ENABLED``) and the clinic switch
(``channel_setting.enabled``) must
  both be on, otherwise nothing starts. Nothing starts either without a stored credential, which only a
  QR scan
  produces: **the channel is dormant until somebody scans a QR code**.
* ``start_account`` does NOT log in again when the bridge already runs the account (``connected``): it
attaches.
  Every Zalo login is a risk of a lock, and several processes (API, worker) each want a channel object.
* ``getRunningAccountApi`` stays deleted, as in the original: the ``ZaloApi`` is reachable only through the
  channel (``manager.get_running(...).api``), so a caller cannot hard-wire itself to the personal channel.

Not here: ``startAllAccounts`` ran ``runStartupBackfill`` and ``runAccountsSeedMigration`` (one-off SQLite
upgrades, no port: Postgres starts clean).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_personal.bridge_client import BridgeGateway, KillSwitchState, ZaloApi, ZaloBridgeError
from pema.channels.zalo_personal.channel_settings import ChannelPolicyReader
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.proactive_gate import ProactiveGate
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import ProactiveSendGuard

log = create_logger("account-manager")


@dataclass
class RunningAccount:
    clinic_id: UUID
    config: AccountConfig
    channel: ZaloPersonalChannel
    api: ZaloApi
    self_id: str
    """The uid of the logged-in Zalo account (``getOwnId``)."""


@dataclass(frozen=True)
class RunningAccountInfo:
    clinic_id: UUID
    id: str
    label: str
    self_id: str


class AccountManager:
    def __init__(
        self,
        *,
        accounts: AccountStore,
        vault: CredentialVault,
        bridge: BridgeGateway,
        registry: InMemoryChannelRegistry,
        policy_reader: ChannelPolicyReader,
        flag_enabled: Callable[[], bool],
        bridge_secret: Callable[[], str | None],
        counter: ProactiveSendGuard | None = None,
        clinic_ref: Callable[[UUID], Awaitable[str]] | None = None,
    ) -> None:
        self._accounts = accounts
        self._vault = vault
        self._bridge = bridge
        self._registry = registry
        self._policy_reader = policy_reader
        self._flag_enabled = flag_enabled
        self._bridge_secret = bridge_secret
        self._counter = counter
        self._clinic_ref = clinic_ref or _clinic_id_as_ref
        self._running: dict[tuple[UUID, str], RunningAccount] = {}

    # ----------------------------------------------------------------------------- read

    def get_running_accounts(self) -> list[RunningAccountInfo]:
        """Trạng thái account đang chạy - cho dashboard."""
        return [
            RunningAccountInfo(clinic_id=a.clinic_id, id=a.config.id, label=a.config.label, self_id=a.self_id)
            for a in self._running.values()
        ]

    def is_account_running(self, clinic_id: UUID, account_id: str) -> bool:
        return (clinic_id, account_id) in self._running

    def get_running_account_kenh(self, clinic_id: UUID, account_id: str) -> ZaloPersonalChannel | None:
        """Kênh của account đang chạy - đường DUY NHẤT để một caller chỉ cầm ``account_id`` gửi được tin.
        ``None`` khi account chưa chạy (chưa login, đang tắt, đã dừng) - caller tự quyết định bỏ lượt. Cần
        ``api`` cho tool thì lấy qua ``get_running_account_kenh(...).api``: đường đó bắt người đọc thấy ngay
        rằng ``None`` là một khả năng thật."""
        running = self._running.get((clinic_id, account_id))
        return running.channel if running else None

    def get_running(self, clinic_id: UUID, account_id: str) -> RunningAccount | None:
        return self._running.get((clinic_id, account_id))

    # ---------------------------------------------------------------------------- attach

    async def attach_account(self, clinic_id: UUID, config: AccountConfig, self_id: str) -> RunningAccount:
        """Gắn 1 account mà bridge đã chạy (login QR xong gọi thẳng vào đây để không phải login lần 2).
        Account
        đang chạy thì thay thế."""
        # Lá chắn cuối: `attach_account` gắn kênh zca-js, chỉ đúng với kênh cá nhân. Gắn cho tài khoản bot là
        # giết vòng poll rồi để lại một tài khoản nửa nọ nửa kia. Route login đã chặn, nhưng
        # `qr_login_manager`
        # gọi thẳng vào đây nên phải có chốt ở chính hàm này.
        if config.channel is not ChannelKind.ZALO_PERSONAL:
            raise DomainError(
                ErrorCode.INVALID_STATE,
                f'Account "{config.id}" không phải tài khoản cá nhân - không gắn được.',
            )
        await self._forget(clinic_id, config.id)
        api = self._bridge.account_api(config.id, self_id)
        gate = ProactiveGate(
            clinic_id=clinic_id,
            account_id=config.id,
            reader=self._policy_reader,
            api=api,
            flag_enabled=self._flag_enabled,
            counter=self._counter,
        )
        await gate.refresh()
        channel = ZaloPersonalChannel(
            clinic_id_str=str(clinic_id), config=config, api=api, gate=gate, bridge_secret=self._bridge_secret
        )
        running = RunningAccount(
            clinic_id=clinic_id, config=config, channel=channel, api=api, self_id=self_id
        )
        self._running[(clinic_id, config.id)] = running
        self._registry.register(clinic_id, channel)
        log.info("Account sẵn sàng", account_id=config.id)
        return running

    # ----------------------------------------------------------------------------- start

    async def start_account(self, clinic_id: UUID, account_id: str) -> None:
        """Start bằng credentials đã lưu - dùng lúc boot và khi bật lại từ dashboard."""
        if not self._flag_enabled():
            raise DomainError(
                ErrorCode.CHANNEL_UNAVAILABLE, "Tài khoản cá nhân đang bị tắt bằng cờ cấu hình."
            )
        config = await self._accounts.get_account(clinic_id, account_id)
        if config is None:
            raise DomainError(ErrorCode.NOT_FOUND, f'Account "{account_id}" không tồn tại')
        if not config.enabled:
            raise DomainError(ErrorCode.INVALID_STATE, f'Account "{account_id}" đang tắt')
        if config.channel is not ChannelKind.ZALO_PERSONAL:
            raise DomainError(ErrorCode.INVALID_STATE, f'Account "{account_id}" không phải tài khoản cá nhân')

        policy = await self._policy_reader.get_policy(clinic_id, ChannelKind.ZALO_PERSONAL)
        if not policy.enabled:
            raise DomainError(
                ErrorCode.CHANNEL_UNAVAILABLE, "Kênh Zalo cá nhân đang tắt trong cài đặt phòng khám."
            )
        kill = KillSwitchState(on=policy.kill_switch_on, scope="proactive", reason=policy.kill_switch_reason)

        # The bridge may already hold a live session (another process started it, or the QR login just ended):
        # attach instead of logging in again. Every Zalo login is a risk of a lock.
        try:
            state = await self._bridge.get_state(account_id)
        except ZaloBridgeError as err:
            raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Không kết nối được bridge Zalo.") from err
        if state.state == "connected" and state.own_id:
            await self._bridge.set_kill_switch(kill)
            await self.attach_account(clinic_id, config, state.own_id)
            return

        credential = await self._vault.load_credentials(clinic_id, account_id)
        if credential is None:
            raise DomainError(
                ErrorCode.INVALID_STATE,
                f'Account "{account_id}" chưa đăng nhập - quét QR ở trang Accounts trước.',
            )
        try:
            own_id = await self._bridge.start_account(
                account_id,
                clinic_slug=await self._clinic_ref(clinic_id),
                credential=credential,
                kill_switch=kill,
            )
        except ZaloBridgeError as err:
            log.warning("bridge could not start the account", account_id=account_id, kind=err.kind)
            raise DomainError(
                ErrorCode.CHANNEL_UNAVAILABLE, "Bridge Zalo không khởi động được account."
            ) from err

        # Đọc LẠI `enabled` ngay trước khi cài vào `running`: `bridge.start_account` mất một vòng mạng
        # (đăng nhập
        # Zalo), đủ rộng để người vận hành bấm TẮT trong lúc chờ. Lúc đó `stop_account` của route là
        # no-op (chưa
        # có gì trong `running`), rồi dòng dưới cài kênh vào một account mà DB nói là tắt - công tắc an
        # toàn hỏng
        # CÂM, bot vẫn đọc tin người lạ.
        fresh = await self._accounts.get_account(clinic_id, account_id)
        if fresh is None or not fresh.enabled:
            await self._stop_bridge(account_id)
            log.info("Account bị tắt trong lúc đang khởi động - đã dừng listener", account_id=account_id)
            return
        await self.attach_account(clinic_id, fresh, own_id)

    async def start_all_accounts(self) -> None:
        """Không account nào chạy vẫn KHÔNG chết: dashboard cần sống để user thêm account + quét QR ngay trên
        web."""
        if not self._flag_enabled():
            log.info("Tài khoản cá nhân tắt bằng cờ - không khởi động account nào")
            return
        configured = [
            a
            for a in await self._accounts.list_all_enabled_accounts()
            if a.channel is ChannelKind.ZALO_PERSONAL
        ]
        for config in configured:
            try:
                await self.start_account(config.clinic_id, config.id)
            except Exception as err:
                log.error("Không khởi động được account - bỏ qua", account_id=config.id, err=err)
        log.info(
            "Account đã khởi động" if self._running else "Chưa account nào chạy - thêm/login qua dashboard",
            total=len(self._running),
            configured=len(configured),
        )

    # ------------------------------------------------------------------------------ stop

    async def stop_account(self, clinic_id: UUID, account_id: str) -> None:
        """Dừng và dọn luôn kênh: không để lại đường gửi cho account đã dừng."""
        was_running = await self._forget(clinic_id, account_id)
        await self._stop_bridge(account_id)
        if was_running:
            log.info("Đã dừng listener", account_id=account_id)

    async def stop_all_accounts(self) -> None:
        for clinic_id, account_id in list(self._running):
            await self._forget(clinic_id, account_id)
        try:
            await self._bridge.stop_all()
        except ZaloBridgeError as err:
            log.warning("bridge stop-all failed", kind=err.kind)
        log.info("Đã dừng toàn bộ listener")

    def forget_without_bridge(self, clinic_id: UUID, account_id: str) -> bool:
        """The bridge already stopped the account (blocked, logged out): drop the channel from this process
        without calling the bridge. Returns whether it was running."""
        running = self._running.pop((clinic_id, account_id), None)
        self._registry.unregister(clinic_id, account_id)
        return running is not None

    async def push_kill_switch(self, state: KillSwitchState) -> None:
        """Tell the bridge now (defence in depth: it enforces the switch itself, even if this process's policy
        read were stale)."""
        await self._bridge.set_kill_switch(state)

    # --------------------------------------------------------------------------- helpers

    async def _forget(self, clinic_id: UUID, account_id: str) -> bool:
        return self.forget_without_bridge(clinic_id, account_id)

    async def _stop_bridge(self, account_id: str) -> None:
        try:
            await self._bridge.stop_account(account_id)
        except ZaloBridgeError as err:
            # The bridge may be down or not know the account: the local state is already clean.
            log.warning("bridge stop failed", account_id=account_id, kind=err.kind)


async def _clinic_id_as_ref(clinic_id: UUID) -> str:
    """The webhook route accepts the clinic id in place of the slug, so the worker (no access to ``clinic.*``)
    can start accounts without knowing the slug."""
    return str(clinic_id)
