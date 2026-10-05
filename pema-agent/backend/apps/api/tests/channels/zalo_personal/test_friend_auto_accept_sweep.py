# ported from: src/zalo/friend-auto-accept-sweep.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``quet_mot_luot`` là hàm thuần (mọi phụ thuộc tiêm vào).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pema.channels.zalo_personal.friend_auto_accept_sweep import (
    AutoAcceptConfig,
    PendingRequestRef,
    QuetDeps,
    RunningAccountRef,
    quet_mot_luot,
)
from pema.channels.zalo_personal.testing import FakeZaloApi

CLINIC = uuid4()
API_GIA = FakeZaloApi()
NOW = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)


@dataclass
class Rig:
    deps: QuetDeps
    accepted: list[str] = field(default_factory=list[str])
    xoaed: list[str] = field(default_factory=list[str])
    moc_goi: list[datetime] = field(default_factory=list[datetime])


def dung_deps(
    *,
    accounts: Sequence[RunningAccountRef] | None = None,
    config: AutoAcceptConfig | None = AutoAcceptConfig(True, 2),
    qua_han: Sequence[str] = ("u1",),
    accept_fails_for: str | None = None,
) -> Rig:
    """Dựng deps ghi lại mọi lời gọi để khẳng định."""
    rig = Rig(deps=None)  # type: ignore[arg-type]

    async def get_config(_clinic: UUID, _account: str) -> AutoAcceptConfig | None:
        return config

    async def lay_qua_han(_clinic: UUID, _account: str, moc: datetime) -> Sequence[PendingRequestRef]:
        rig.moc_goi.append(moc)
        return [PendingRequestRef(uid) for uid in qua_han]

    async def xoa(_clinic: UUID, _account: str, uid: str) -> None:
        rig.xoaed.append(uid)

    async def accept(_api: object, uid: str) -> None:
        if uid == accept_fails_for:
            raise RuntimeError("Zalo từ chối")
        rig.accepted.append(uid)

    rig.deps = QuetDeps(
        ds_account=lambda: accounts or [RunningAccountRef(CLINIC, "acc-1", API_GIA)],
        get_config=get_config,
        lay_qua_han=lay_qua_han,
        xoa=xoa,
        accept=accept,
    )
    return rig


async def test_quet_mot_luot_account_bat_auto_dong_qua_han_accept_xoa_moc_la_now_tru_delay() -> None:
    """account BẬT auto + dòng quá hạn -> accept + xóa; mốc = now - delay*60000"""
    t = dung_deps()
    await quet_mot_luot(NOW, t.deps)
    assert t.accepted == ["u1"]
    assert t.xoaed == ["u1"]
    assert t.moc_goi == [NOW - timedelta(minutes=2)], "delay 2 phút -> mốc lùi 120000ms"


async def test_quet_mot_luot_account_tat_auto_khong_hoi_pending_khong_accept() -> None:
    """account TẮT auto -> KHÔNG hỏi pending, KHÔNG accept"""
    t = dung_deps(config=AutoAcceptConfig(False, 2))
    await quet_mot_luot(NOW, t.deps)
    assert t.moc_goi == [], "tắt thì không được gọi lay_qua_han"
    assert t.accepted == []


async def test_quet_mot_luot_mot_dong_accept_nem_dong_sau_van_accept_dong_loi_khong_bi_xoa() -> None:
    """một dòng accept NÉM -> dòng sau vẫn accept, dòng lỗi KHÔNG bị xóa"""
    t = dung_deps(qua_han=("u-loi", "u-ok"), accept_fails_for="u-loi")
    await quet_mot_luot(NOW, t.deps)
    assert t.xoaed == ["u-ok"], "chỉ xóa dòng accept THÀNH CÔNG; dòng lỗi giữ lại để thử lượt sau"


async def test_quet_mot_luot_nhieu_account_mot_luot_chi_account_bat_va_co_api_moi_accept() -> None:
    """nhiều account một lượt: chỉ account BẬT + có api mới accept (isolation)"""
    accepted: list[str] = []

    async def get_config(_clinic: UUID, account: str) -> AutoAcceptConfig | None:
        return AutoAcceptConfig(account != "off", 2)

    async def lay_qua_han(_clinic: UUID, account: str, _moc: datetime) -> Sequence[PendingRequestRef]:
        return [PendingRequestRef(f"u-{account}")]

    async def xoa(_clinic: UUID, _account: str, _uid: str) -> None:
        return None

    async def accept(_api: object, uid: str) -> None:
        accepted.append(uid)

    deps = QuetDeps(
        ds_account=lambda: [
            RunningAccountRef(CLINIC, "on", API_GIA),
            RunningAccountRef(CLINIC, "off", API_GIA),
            RunningAccountRef(CLINIC, "bot", None),
        ],
        get_config=get_config,
        lay_qua_han=lay_qua_han,
        xoa=xoa,
        accept=accept,
    )
    await quet_mot_luot(NOW, deps)
    assert accepted == ["u-on"], "off (tắt) và bot (api None) đều bị bỏ; chỉ on được accept"


async def test_quet_mot_luot_api_null_kenh_bot_chua_chay_bo_qua_khong_hoi_config_accept() -> None:
    """api null (kênh bot / chưa chạy) -> bỏ qua, không hỏi config/accept"""
    goi_config = 0
    t = dung_deps(accounts=[RunningAccountRef(CLINIC, "acc-bot", None)])
    inner = t.deps.get_config

    async def counting(clinic: UUID, account: str) -> AutoAcceptConfig | None:
        nonlocal goi_config
        goi_config += 1
        return await inner(clinic, account)

    t.deps.get_config = counting
    await quet_mot_luot(NOW, t.deps)
    assert goi_config == 0, "api None thì bỏ trước cả khi đọc config"
    assert t.accepted == []
