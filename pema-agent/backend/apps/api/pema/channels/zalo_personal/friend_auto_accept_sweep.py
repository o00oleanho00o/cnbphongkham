# ported from: src/zalo/friend-auto-accept-sweep.ts
"""Vòng quét tự động chấp nhận kết bạn (chỉ tài khoản cá nhân).

Forced deviations: ``setInterval`` becomes one asyncio task; every dependency is async and carries the
clinic id
(accounts are unique per clinic only); ``now`` and the cut-off are aware ``datetime`` values instead of epoch
milliseconds; the zca-js ``API`` is the bridge-backed ``ZaloApi``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from pema.channels.zalo_personal.bridge_client import ZaloApi
from pema.shared.logger import create_logger

log = create_logger("friend-sweep")

# Chu kỳ quét. Hằng số, KHÔNG chỉnh runtime (YAGNI) - delay per-account mới là thứ người dùng chỉnh. 30s
# đủ nhanh
# cho "1-2 phút mới accept" mà không đốt CPU.
SWEEP_MS = 30_000


@dataclass(frozen=True)
class RunningAccountRef:
    clinic_id: UUID
    id: str
    api: ZaloApi | None
    """``None``: Bot channel or not running; nothing to accept."""


@dataclass(frozen=True)
class AutoAcceptConfig:
    auto_accept_friends: bool
    auto_accept_friend_delay_minutes: int


@dataclass(frozen=True)
class PendingRequestRef:
    from_uid: str


@dataclass
class QuetDeps:
    """Phụ thuộc của một lượt quét. Tách hết ra để ``quet_mot_luot`` là hàm THUẦN test được (không đụng
    registry
    account, DB hay mạng thật)."""

    ds_account: Callable[[], Sequence[RunningAccountRef]]
    """Các account đang chạy + api (None với kênh bot / chưa login)."""
    get_config: Callable[[UUID, str], Awaitable[AutoAcceptConfig | None]]
    """Cấu hình auto-accept HIỆN TẠI (đọc từ DB mỗi lượt -> đổi toggle không cần restart)."""
    lay_qua_han: Callable[[UUID, str, datetime], Awaitable[Sequence[PendingRequestRef]]]
    xoa: Callable[[UUID, str, str], Awaitable[object]]
    accept: Callable[[ZaloApi, str], Awaitable[object]]


async def quet_mot_luot(now: datetime, deps: QuetDeps) -> None:
    """Một lượt quét: mỗi account cá nhân đang chạy có auto-accept BẬT thì accept mọi request đã chờ quá
    ``delay_minutes`` rồi xóa dòng. Một dòng hỏng KHÔNG chặn dòng khác (bọc try/except từng dòng). Idempotent:
    dòng đã xóa mà sự kiện ADD tới sau cũng chỉ xóa lại vô hại."""
    for account in deps.ds_account():
        if account.api is None:
            continue  # kênh bot / chưa chạy - không có gì để accept
        cfg = await deps.get_config(account.clinic_id, account.id)
        if cfg is None or not cfg.auto_accept_friends:
            continue

        moc = now - timedelta(minutes=cfg.auto_accept_friend_delay_minutes)
        # ĐUA hiếm với nút thủ công: nếu người dùng bấm Accept/Reject đúng một dòng trong 30s cửa sổ này,
        # cả hai
        # đường có thể cùng gọi Zalo (một bên nhận lỗi "đã là bạn" -> tự lành). Không dựng lớp khóa: xác suất
        # thấp (cần auto BẬT + thao tác tay trong 30s). Xóa-sau-khi-accept giữ đúng ngữ nghĩa thử-lại nên chấp
        # nhận cửa sổ đua.
        for row in await deps.lay_qua_han(account.clinic_id, account.id, moc):
            try:
                await deps.accept(account.api, row.from_uid)
                await deps.xoa(account.clinic_id, account.id, row.from_uid)
                log.info("auto-accept yêu cầu kết bạn", account_id=account.id, from_uid=row.from_uid)
            except Exception as err:
                log.warning(
                    "auto-accept 1 dòng hỏng - bỏ qua dòng này",
                    account_id=account.id,
                    from_uid=row.from_uid,
                    err=err,
                )


def start_friend_auto_accept_sweep(
    deps: QuetDeps,
    *,
    now: Callable[[], datetime],
    interval_seconds: float = SWEEP_MS / 1000,
) -> Callable[[], None]:
    """Khởi động vòng quét (1 task toàn cục). Trả hàm dừng cho shutdown."""

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await quet_mot_luot(now(), deps)
            except Exception as err:
                log.error("vòng quét auto-accept lỗi", err=err)

    task = asyncio.get_running_loop().create_task(loop())

    def stop() -> None:
        task.cancel()

    return stop
