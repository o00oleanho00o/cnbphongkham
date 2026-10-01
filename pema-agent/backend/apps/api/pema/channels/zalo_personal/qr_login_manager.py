# ported from: src/zalo/qr-login-manager.ts (+ QrLoginEvent of src/zalo/zalo-client.ts)
"""Quản lý phiên login QR từ dashboard: mỗi account tối đa 1 phiên, UI polling trạng thái. QR là chìa
khóa đăng
nhập tài khoản - KHÔNG log base64, chỉ đi qua API đã auth.

Forced deviations:

* ``loginWithQRForWeb`` (zca-js, in-process) is the Node bridge: ``bridge_qr_deps`` starts the QR session
in the
  bridge and POLLS it, translating the bridge states into the same ``QrLoginEvent`` stream the original
  callback produced (``qr``, ``scanned``, ``expired``, ``declined``). ``QrLoginDeps`` keeps the original
  seam so
  the tests inject a fake login.
* the result of a successful login is not an ``API`` object but the own uid; ``attach`` registers the running
  account with the ``AccountManager``. The credential itself never passes through here: the bridge posts a
  ``credential_updated`` event and ``bridge_events`` stores it encrypted.
* sessions are keyed by ``(clinic_id, account_id)``; ``asyncio`` tasks replace promises, ``time.monotonic``
  replaces ``Date.now``.
* statuses ``starting``, ``declined`` and ``timeout`` exist here as in the original; the REST layer maps
them onto
  the ``QrLoginState`` enum of the contract (``admin_accounts``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Literal
from uuid import UUID

from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.bridge_client import BridgeGateway, ZaloBridgeError
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountStore

log = create_logger("qr-login-manager")

type QrLoginStatusName = Literal["starting", "waiting_scan", "scanned", "success", "declined", "error"]

SESSION_TTL_MS = 3 * 60_000

_PENDING = ("starting", "waiting_scan", "scanned")


@dataclass(frozen=True)
class QrLoginEvent:
    type: Literal["qr", "scanned", "expired", "declined", "info"]
    qr_base64: str | None = None
    """Base64 PNG without the ``data:`` prefix - only on ``qr``."""


@dataclass(frozen=True)
class QrLoginResult:
    own_id: str


class QrLoginDeclinedError(Exception):
    """The user declined the login on the phone; the session already shows ``declined``."""


@dataclass
class QrSession:
    seq: int
    status: QrLoginStatusName
    started_at: float
    qr_base64: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class QrLoginState:
    status: str
    """``QrLoginStatusName`` | ``idle`` | ``timeout``."""
    qr_data_uri: str | None = None
    error: str | None = None


@dataclass
class QrLoginDeps:
    """Cho test inject login/attach giả - mặc định dùng bridge thật."""

    login: Callable[[UUID, str, Callable[[QrLoginEvent], None]], Awaitable[QrLoginResult]]
    attach: Callable[[UUID, str, QrLoginResult], Awaitable[None]]


def _now_ms() -> float:
    return monotonic() * 1000


class QrLoginManager:
    def __init__(
        self, deps: QrLoginDeps, *, stop_account: Callable[[UUID, str], Awaitable[None]] | None = None
    ) -> None:
        self._deps = deps
        self._stop_account = stop_account
        self._sessions: dict[tuple[UUID, str], QrSession] = {}
        self._seq_counter = 0
        self._tasks: set[asyncio.Task[None]] = set()

    async def start_qr_login(
        self, clinic_id: UUID, account_id: str, deps: QrLoginDeps | None = None
    ) -> QrSession:
        """``deps`` overrides the manager's own for this session (the original took it per call, tests inject
        a fake login)."""
        use = deps or self._deps
        key = (clinic_id, account_id)
        existing = self._sessions.get(key)
        active = (
            existing is not None
            and existing.status in _PENDING
            and _now_ms() - existing.started_at < SESSION_TTL_MS
        )
        if active and existing is not None:
            return existing

        # Re-login account đang chạy: đá listener cũ trước (Zalo chỉ cho 1 listener)
        if self._stop_account is not None:
            await self._stop_account(clinic_id, account_id)

        self._seq_counter += 1
        seq = self._seq_counter
        session = QrSession(seq=seq, status="starting", started_at=_now_ms())
        self._sessions[key] = session

        # Phiên mới đè phiên cũ: mọi update từ task cũ bị bỏ qua nhờ check seq
        def still_current() -> bool:
            current = self._sessions.get(key)
            return current is not None and current.seq == seq

        def on_event(event: QrLoginEvent) -> None:
            if not still_current():
                return
            if event.type == "qr":
                session.status = "waiting_scan"
                session.qr_base64 = event.qr_base64
            elif event.type == "scanned":
                session.status = "scanned"
            elif event.type == "declined":
                session.status = "declined"
            # "expired": zca-js tự tạo QR mới rồi bắn lại event "qr" - không cần xử lý

        async def run() -> None:
            try:
                result = await use.login(clinic_id, account_id, on_event)
            except Exception as err:
                if not still_current():
                    return
                if session.status != "declined":
                    session.status = "error"
                    session.error = str(err)
                log.warning("Login QR thất bại", account_id=account_id, declined=session.status == "declined")
                return
            if not still_current():
                return
            session.status = "success"
            session.qr_base64 = None
            await use.attach(clinic_id, account_id, result)
            log.info("Login QR từ dashboard thành công", account_id=account_id)

        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return session

    def get_qr_login_status(self, clinic_id: UUID, account_id: str) -> QrLoginState:
        key = (clinic_id, account_id)
        session = self._sessions.get(key)
        if session is None:
            return QrLoginState(status="idle")

        pending = session.status in _PENDING
        if pending and _now_ms() - session.started_at >= SESSION_TTL_MS:
            # Quá 3 phút không quét: coi như hết phiên, promise về sau bị bỏ qua theo seq
            del self._sessions[key]
            return QrLoginState(status="timeout")

        return QrLoginState(
            status=session.status,
            qr_data_uri=f"data:image/png;base64,{session.qr_base64}" if session.qr_base64 else None,
            error=session.error,
        )


def bridge_qr_deps(
    bridge: BridgeGateway,
    attach: Callable[[UUID, str, QrLoginResult], Awaitable[None]],
    clinic_ref: Callable[[UUID], Awaitable[str]],
    *,
    poll_seconds: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> QrLoginDeps:
    """Default deps: the QR session lives in the Node bridge; this polls it and replays its states as
    events."""

    async def login(
        clinic_id: UUID, account_id: str, on_event: Callable[[QrLoginEvent], None]
    ) -> QrLoginResult:
        status = await bridge.start_qr_login(account_id, clinic_slug=await clinic_ref(clinic_id))
        last_qr: str | None = None
        last_state = ""
        while True:
            if status.state == "waiting_scan" and status.qr_png_base64 and status.qr_png_base64 != last_qr:
                if last_qr is not None:
                    on_event(QrLoginEvent("expired"))
                last_qr = status.qr_png_base64
                on_event(QrLoginEvent("qr", status.qr_png_base64))
            elif status.state == "scanned" and last_state != "scanned":
                on_event(QrLoginEvent("scanned"))
            elif status.state == "declined":
                on_event(QrLoginEvent("declined"))
                raise QrLoginDeclinedError
            elif status.state == "success":
                bridge_state = await bridge.get_state(account_id)
                return QrLoginResult(own_id=bridge_state.own_id)
            elif status.state in ("error", "timeout"):
                raise ZaloBridgeError("transport", status.error or status.state)
            last_state = status.state
            await sleep(poll_seconds)
            status = await bridge.get_qr_login(account_id)

    return QrLoginDeps(login=login, attach=attach)


def build_qr_manager(
    bridge: BridgeGateway,
    manager: AccountManager,
    accounts: AccountStore,
    clinic_ref: Callable[[UUID], Awaitable[str]],
    *,
    poll_seconds: float = 1.0,
) -> QrLoginManager:
    """The production wiring: QR session in the bridge, ``attach`` registers the account with the manager."""

    async def attach(clinic_id: UUID, account_id: str, result: QrLoginResult) -> None:
        config = await accounts.get_account(clinic_id, account_id)
        # Account đã bị xóa/tắt trong lúc chờ quét thì thôi - credentials vẫn được lưu (bridge event)
        if config is not None and config.enabled:
            await manager.attach_account(clinic_id, config, result.own_id)

    return QrLoginManager(
        bridge_qr_deps(bridge, attach, clinic_ref, poll_seconds=poll_seconds),
        stop_account=manager.stop_account,
    )
