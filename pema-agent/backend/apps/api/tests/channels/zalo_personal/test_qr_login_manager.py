# ported from: src/zalo/qr-login-manager.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The default deps talk to the bridge (``bridge_qr_deps``); the original cases inject a fake login whose steps the test
drives (``emit`` / ``finish`` / ``fail``), exactly like here. The ``bridge_qr_deps`` translation of bridge states into
events has its own cases at the end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID

from pema.channels.zalo_personal.bridge_client import BridgeQrStatus
from pema.channels.zalo_personal.qr_login_manager import (
    QrLoginDeps,
    QrLoginEvent,
    QrLoginManager,
    QrLoginResult,
    bridge_qr_deps,
)
from pema.channels.zalo_personal.testing import FakeBridge
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.testing import FAKE_CLINIC_ID

CLINIC: UUID = FAKE_CLINIC_ID


class FakeLogin:
    """Login giả điều khiển được từng bước qua emit + finish/fail."""

    def __init__(self) -> None:
        self.attached: list[str] = []
        self._emit: Callable[[QrLoginEvent], None] | None = None
        self._future: asyncio.Future[QrLoginResult] | None = None
        self.deps = QrLoginDeps(login=self._login, attach=self._attach)

    async def _login(
        self, clinic_id: UUID, account_id: str, on_event: Callable[[QrLoginEvent], None]
    ) -> QrLoginResult:
        self._emit = on_event
        self._future = asyncio.get_running_loop().create_future()
        return await self._future

    async def _attach(self, clinic_id: UUID, account_id: str, result: QrLoginResult) -> None:
        self.attached.append(account_id)

    def emit(self, event: QrLoginEvent) -> None:
        assert self._emit is not None
        self._emit(event)

    def finish(self) -> None:
        assert self._future is not None
        self._future.set_result(QrLoginResult(own_id="self-1"))

    def fail(self, message: str) -> None:
        assert self._future is not None
        self._future.set_exception(RuntimeError(message))


async def started(manager: QrLoginManager, fake: FakeLogin, account: str):  # type: ignore[no-untyped-def]
    session = await manager.start_qr_login(CLINIC, account, fake.deps)
    await asyncio.sleep(0)  # let the login task run to its first await
    return session


def status(manager: QrLoginManager, account: str) -> str:
    return manager.get_qr_login_status(CLINIC, account).status


async def test_qr_login_manager_luong_chuan_starting_waiting_scan_scanned_success_attach() -> None:
    """luồng chuẩn: starting -> waiting_scan (có QR) -> scanned -> success + attach"""
    fake = FakeLogin()
    manager = QrLoginManager(fake.deps)
    await started(manager, fake, "acc-qr-1")
    assert status(manager, "acc-qr-1") == "starting"

    fake.emit(QrLoginEvent("qr", "QR_BASE64_DATA"))
    waiting = manager.get_qr_login_status(CLINIC, "acc-qr-1")
    assert waiting.status == "waiting_scan"
    assert waiting.qr_data_uri == "data:image/png;base64,QR_BASE64_DATA"

    fake.emit(QrLoginEvent("scanned"))
    assert status(manager, "acc-qr-1") == "scanned"

    fake.finish()
    await doi_cho_den_khi(
        lambda: status(manager, "acc-qr-1") == "success", WaitOptions(mo_ta="trạng thái chuyển sang success")
    )
    done = manager.get_qr_login_status(CLINIC, "acc-qr-1")
    assert done.status == "success"
    assert done.qr_data_uri is None, "QR phải bị xóa sau khi login xong"
    assert fake.attached == ["acc-qr-1"]


async def test_qr_login_manager_qr_het_han_zca_js_ban_lai_qr_moi_ui_nhan_anh_moi() -> None:
    """QR hết hạn: zca-js bắn lại QR mới, UI nhận ảnh mới"""
    fake = FakeLogin()
    manager = QrLoginManager(fake.deps)
    await started(manager, fake, "acc-qr-2")
    fake.emit(QrLoginEvent("qr", "QR_CU"))
    fake.emit(QrLoginEvent("expired"))
    fake.emit(QrLoginEvent("qr", "QR_MOI"))

    state = manager.get_qr_login_status(CLINIC, "acc-qr-2")
    assert state.status == "waiting_scan"
    assert state.qr_data_uri is not None
    assert "QR_MOI" in state.qr_data_uri


async def test_qr_login_manager_tu_choi_tren_dien_thoai_declined_login_loi_error_kem_message() -> None:
    """từ chối trên điện thoại -> declined; login lỗi -> error kèm message"""
    fake1 = FakeLogin()
    manager = QrLoginManager(fake1.deps)
    await started(manager, fake1, "acc-qr-3")
    fake1.emit(QrLoginEvent("declined"))
    assert status(manager, "acc-qr-3") == "declined"

    fake2 = FakeLogin()
    manager2 = QrLoginManager(fake2.deps)
    await started(manager2, fake2, "acc-qr-4")
    fake2.fail("mạng rớt")
    await doi_cho_den_khi(
        lambda: status(manager2, "acc-qr-4") == "error", WaitOptions(mo_ta="trạng thái chuyển sang error")
    )
    state = manager2.get_qr_login_status(CLINIC, "acc-qr-4")
    assert state.status == "error"
    assert state.error == "mạng rớt"


async def test_qr_login_manager_phien_dang_song_thi_start_lan_2_la_idempotent_khong_tao_qr_moi() -> None:
    """phiên đang sống thì start lần 2 là idempotent (không tạo QR mới)"""
    fake = FakeLogin()
    manager = QrLoginManager(fake.deps)
    first = await started(manager, fake, "acc-qr-5")
    fake.emit(QrLoginEvent("qr", "QR_A"))

    second = await manager.start_qr_login(CLINIC, "acc-qr-5")
    assert second.seq == first.seq, "phải trả về đúng phiên đang chạy"


async def test_qr_login_manager_phien_moi_de_phien_chet_ket_qua_muon_cua_phien_cu_bi_bo_qua() -> None:
    """phiên mới đè phiên chết: kết quả muộn của phiên cũ bị bỏ qua"""
    fake1 = FakeLogin()
    # one manager for both sessions: they share the session table, as in the original
    manager = QrLoginManager(fake1.deps)
    await started(manager, fake1, "acc-qr-6")
    fake1.emit(QrLoginEvent("declined"))  # phiên 1 chết

    fake2 = FakeLogin()
    await started(manager, fake2, "acc-qr-6")
    fake2.emit(QrLoginEvent("qr", "QR_PHIEN_2"))

    # Phiên 1 resolve muộn - không được đè trạng thái phiên 2
    fake1.finish()
    await asyncio.sleep(0.01)
    assert status(manager, "acc-qr-6") == "waiting_scan"
    assert fake1.attached == [], "phiên cũ không được attach"
    assert fake2.attached == []


async def test_qr_login_manager_chua_tung_start_idle() -> None:
    """chưa từng start -> idle"""
    manager = QrLoginManager(FakeLogin().deps)
    assert status(manager, "acc-chua-start") == "idle"


async def test_qr_login_manager_start_dung_listener_cu_truoc_khi_login_lai() -> None:
    """Re-login account đang chạy: đá listener cũ trước (Zalo chỉ cho 1 listener)"""
    fake = FakeLogin()
    stopped: list[str] = []

    async def stop(clinic_id: UUID, account_id: str) -> None:
        stopped.append(account_id)

    manager = QrLoginManager(fake.deps, stop_account=stop)
    await started(manager, fake, "acc-qr-7")
    assert stopped == ["acc-qr-7"]


async def test_bridge_qr_deps_dich_trang_thai_bridge_thanh_su_kien_qr_scanned_expired_success() -> None:
    """(mới) bridge_qr_deps: poll bridge và phát lại đúng chuỗi sự kiện của bản gốc"""
    bridge = FakeBridge()
    bridge.states["acc-b"] = "connected"
    bridge.qr_answers = [
        BridgeQrStatus(state="starting"),  # answer of start
        BridgeQrStatus(state="waiting_scan", qr_png_base64="QR1"),
        BridgeQrStatus(state="waiting_scan", qr_png_base64="QR2"),  # expired -> a new QR
        BridgeQrStatus(state="scanned"),
        BridgeQrStatus(state="success"),
    ]
    attached: list[str] = []

    async def attach(clinic_id: UUID, account_id: str, result: QrLoginResult) -> None:
        attached.append(result.own_id)

    async def no_sleep(_: float) -> None:
        await asyncio.sleep(0)

    async def clinic_ref(clinic_id: UUID) -> str:
        return str(clinic_id)

    deps = bridge_qr_deps(bridge, attach, clinic_ref, sleep=no_sleep)
    manager = QrLoginManager(deps)
    await manager.start_qr_login(CLINIC, "acc-b")

    await doi_cho_den_khi(
        lambda: status(manager, "acc-b") == "success", WaitOptions(mo_ta="success từ bridge")
    )
    assert bridge.qr_started == ["acc-b"]
    assert attached == ["self-1"]


async def test_bridge_qr_deps_bridge_bao_declined_thi_giu_trang_thai_declined() -> None:
    """(mới) bị từ chối trên điện thoại: trạng thái là declined, không bị ghi đè thành error"""
    bridge = FakeBridge()
    bridge.qr_answers = [BridgeQrStatus(state="starting"), BridgeQrStatus(state="declined")]

    async def attach(clinic_id: UUID, account_id: str, result: QrLoginResult) -> None:
        raise AssertionError("must not attach")

    async def no_sleep(_: float) -> None:
        await asyncio.sleep(0)

    async def clinic_ref(clinic_id: UUID) -> str:
        return str(clinic_id)

    manager = QrLoginManager(bridge_qr_deps(bridge, attach, clinic_ref, sleep=no_sleep))
    await manager.start_qr_login(CLINIC, "acc-d")

    await doi_cho_den_khi(lambda: status(manager, "acc-d") == "declined", WaitOptions(mo_ta="declined"))
    await asyncio.sleep(0.01)
    assert status(manager, "acc-d") == "declined"
