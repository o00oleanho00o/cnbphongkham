"""Channel switchboard on a real Postgres (marker ``db``): the repository (``be_app``), the worker's view
(``agent_worker``), optimistic locking, audit rows, row level security and the bridge report.

The kill switch is the instant emergency stop: what ``be_app`` writes here must be visible to the worker on its very
next read, through the only door the worker has (``clinic_agent.channel_policy``).
"""

from __future__ import annotations

import uuid
from datetime import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from pema.channels.zalo_personal.audit_writer import SqlAuditSink
from pema.channels.zalo_personal.bridge_events import SqlUpdateDedupe
from pema.channels.zalo_personal.channel_settings import (
    AUTO_KILL_REASON_BLOCKED,
    ChannelSettingsRepository,
    WorkerChannelPolicyReader,
)
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.admin import BridgeState, ChannelSettingsUpdate
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

PERSONAL = ChannelKind.ZALO_PERSONAL


def staff(clinic_id: uuid.UUID) -> ActionContext:
    return ActionContext(
        clinic_id=clinic_id, actor_type=ActorType.USER, actor_role=Role.OWNER, source=ActionSource.UI
    )


def system(clinic_id: uuid.UUID) -> ActionContext:
    return ActionContext(clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.WEBHOOK)


async def audit_actions(db: ClinicDatabase, clinic_id: uuid.UUID) -> list[str]:
    async with db.session(clinic_id) as session:
        rows = await session.execute(text("SELECT action FROM clinic.audit_log ORDER BY id"))
        return [r[0] for r in rows]


async def test_hang_chua_ton_tai_thi_doc_ra_mac_dinh_tat_fail_closed(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    settings = await repo.get(clinic_ids[1], ChannelKind.ZALO_OA)
    assert (settings.enabled, settings.kill_switch_on, settings.version) == (False, False, 0)


async def test_update_tao_hang_khoa_lac_quan_va_ghi_audit(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    clinic = clinic_ids[0]

    created = await repo.update(
        staff(clinic),
        PERSONAL,
        ChannelSettingsUpdate(
            version=0,
            enabled=True,
            daily_cap=12,
            send_window_start="08:00",
            send_window_end="18:30",
            min_gap_seconds=5,
            max_gap_seconds=20,
        ),
    )

    assert created.version == 1
    assert created.enabled is True
    assert created.daily_cap == 12
    assert (created.send_window_start, created.send_window_end) == (time(8, 0), time(18, 30))
    assert created.requires_friend is True, "tài khoản cá nhân mặc định phải là bạn bè"
    with pytest.raises(DomainError) as stale:
        await repo.update(staff(clinic), PERSONAL, ChannelSettingsUpdate(version=0, daily_cap=1))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    assert "channel.update" in await audit_actions(be_db, clinic)


async def test_update_khoang_nghi_toi_da_nho_hon_toi_thieu_bi_tu_choi(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    current = await repo.get(clinic_ids[0], PERSONAL)
    with pytest.raises(DomainError) as info:
        await repo.update(
            staff(clinic_ids[0]),
            PERSONAL,
            ChannelSettingsUpdate(version=current.version, min_gap_seconds=30, max_gap_seconds=10),
        )
    assert info.value.code is ErrorCode.VALIDATION_FAILED


async def test_kill_switch_ghi_audit_va_worker_thay_ngay_qua_view(
    be_db: ClinicDatabase, worker_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    reader = WorkerChannelPolicyReader(worker_db)
    clinic = clinic_ids[0]
    assert (await reader.get_policy(clinic, PERSONAL)).kill_switch_on is False

    after = await repo.set_kill_switch(staff(clinic), PERSONAL, on=True, reason="khẩn cấp")

    assert after.kill_switch_on is True
    assert after.kill_switch_reason == "khẩn cấp"
    assert after.kill_switch_changed_at is not None
    seen_by_worker = await reader.get_policy(clinic, PERSONAL)
    assert seen_by_worker.kill_switch_on is True, "worker đọc lại ở lần gửi kế tiếp thì thấy ngay"
    assert (seen_by_worker.daily_cap, seen_by_worker.enabled) == (12, True)
    assert "channel.kill_switch" in await audit_actions(be_db, clinic)

    await repo.set_kill_switch(staff(clinic), PERSONAL, on=False, reason=None)
    assert (await reader.get_policy(clinic, PERSONAL)).kill_switch_on is False


async def test_worker_khong_doc_duoc_bang_that_chi_doc_qua_view(
    worker_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    with pytest.raises(DBAPIError):
        async with worker_db.session(clinic_ids[0]) as session:
            await session.execute(text("SELECT kill_switch_reason FROM clinic.channel_setting"))


async def test_bridge_bao_bi_khoa_thi_bat_kill_switch_cung_giao_dich_va_ghi_audit_he_thong(
    be_db: ClinicDatabase, worker_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    reader = WorkerChannelPolicyReader(worker_db)
    clinic = clinic_ids[0]

    blocked = await repo.apply_bridge_report(
        system(clinic),
        PERSONAL,
        bridge_state=BridgeState.BLOCKED,
        kill_switch_reason=AUTO_KILL_REASON_BLOCKED,
    )

    assert blocked.bridge_state is BridgeState.BLOCKED
    assert blocked.kill_switch_on is True
    assert blocked.kill_switch_reason == AUTO_KILL_REASON_BLOCKED
    assert (await reader.get_policy(clinic, PERSONAL)).kill_switch_on is True
    async with be_db.session(clinic) as session:
        row = (
            await session.execute(
                text(
                    "SELECT actor_type, details FROM clinic.audit_log "
                    "WHERE action = 'channel.bridge_report' ORDER BY id DESC LIMIT 1"
                )
            )
        ).one()
    assert row[0] == "system"
    assert row[1]["kill_switch_engaged"] is True


async def test_ket_noi_lai_khong_bao_gio_tu_tat_kill_switch(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """một người quyết định khi nào gửi lại"""
    repo = ChannelSettingsRepository(be_db)
    clinic = clinic_ids[0]
    after = await repo.apply_bridge_report(
        system(clinic), PERSONAL, bridge_state=BridgeState.CONNECTED, kill_switch_reason=None
    )
    assert after.bridge_state is BridgeState.CONNECTED
    assert after.kill_switch_on is True


async def test_hai_phong_kham_khong_thay_cai_dat_kenh_cua_nhau(
    be_db: ClinicDatabase, worker_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    other = clinic_ids[1]
    assert (await repo.get(other, PERSONAL)).kill_switch_on is False
    assert (await WorkerChannelPolicyReader(worker_db).get_policy(other, PERSONAL)).kill_switch_on is False
    assert len(await repo.list_all(other)) == 3, "đủ ba kênh, kênh chưa có hàng hiện mặc định"


async def test_clinic_slug_doc_duoc_trong_ngu_canh_phong_kham(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    repo = ChannelSettingsRepository(be_db)
    assert await repo.clinic_slug(clinic_ids[0]) == "c2-clinic-a"
    assert await repo.clinic_slug(uuid.uuid4()) is None, "id lạ: không có hàng nào hiện ra (RLS)"


async def test_update_id_khong_lap_lai_khi_bridge_gui_lai_cung_mot_tin(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    dedupe = SqlUpdateDedupe(be_db)
    clinic = clinic_ids[0]
    assert await dedupe.first_time(clinic, "zp-1", "msg-xyz") is True
    assert await dedupe.first_time(clinic, "zp-1", "msg-xyz") is False
    assert await dedupe.first_time(clinic_ids[1], "zp-1", "msg-xyz") is True, "mỗi phòng khám đếm riêng"


async def test_audit_sink_ghi_mot_dong_chi_co_ten_truong_va_ma(
    be_db: ClinicDatabase, clinic_ids: tuple[uuid.UUID, uuid.UUID]
) -> None:
    sink = SqlAuditSink(be_db)
    await sink.record(staff(clinic_ids[0]), "account.update", "account", "zp-1", {"fields": ["label"]})
    assert "account.update" in await audit_actions(be_db, clinic_ids[0])
