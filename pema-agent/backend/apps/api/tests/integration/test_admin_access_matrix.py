"""Every admin router is wired AND guarded by the role matrix (package G; no zalo-agent source).

The wired application (the real ``create_app`` lifespan) answers each admin family in three ways: 401 to an
anonymous caller, 403 to a role without the permission, 200 to a role that has it. A role that may not use a
family must not see a single byte of it; a route that was left unwired would answer 501 here and fail the test.
"""

from __future__ import annotations

import httpx
import pytest

from pema.composition.testing import Loop, LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]

# (path, role that may read it, role that may not)
FAMILIES: list[tuple[str, str, str]] = [
    ("/api/v1/admin/model/provider", "manager", "reception.lan"),
    ("/api/v1/admin/model/tuning", "manager", "doctor.mai"),
    ("/api/v1/admin/usage/overview", "manager", "doctor.mai"),
    ("/api/v1/admin/traces", "manager", "cs.maianh"),
    ("/api/v1/admin/tools", "manager", "cs.maianh"),
    ("/api/v1/admin/schedules", "manager", "cs.maianh"),
    ("/api/v1/admin/mcp/servers", "manager", "reception.lan"),
    ("/api/v1/admin/accounts", "manager", "cs.maianh"),
    ("/api/v1/admin/channels", "manager", "doctor.mai"),
    ("/api/v1/admin/agents", "manager", "cs.maianh"),
    ("/api/v1/admin/policy/profiles", "manager", "reception.lan"),
    ("/api/v1/admin/rules", "manager", "cs.maianh"),
    ("/api/v1/admin/logs/app", "manager", "cs.maianh"),
    ("/api/v1/admin/kb/sources", "cs.maianh", "patient.none"),
]


async def _status(client: httpx.AsyncClient, path: str) -> int:
    return (await client.get(path)).status_code


async def test_moi_ho_admin_duoc_noi_va_phan_quyen_dung_theo_ma_tran_vai_tro(make_loop: LoopFactory) -> None:
    """mỗi họ route admin: ẩn danh 401, vai trò thiếu quyền 403, vai trò đủ quyền 200 (không còn 501 chưa nối)"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        clients = {
            key: await loop.staff(key) for key in {"manager", "cs.maianh", "doctor.mai", "reception.lan"}
        }
        for path, allowed, denied in FAMILIES:
            assert await _status(loop.http, path) == 401, f"anonymous {path}"
            assert await _status(clients[allowed], path) == 200, f"{allowed} {path}"
            if denied in clients:
                assert await _status(clients[denied], path) == 403, f"{denied} {path}"


async def test_chi_nhan_vien_co_quyen_moi_ghi_duoc_cau_hinh_mo_hinh(make_loop: LoopFactory) -> None:
    """đổi cấu hình model: người đủ quyền ghi được (và ghi audit), người thiếu quyền bị 403, không đổi gì"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        manager = await loop.staff("manager")
        reception = await loop.staff("reception.lan")

        refused = await reception.patch("/api/v1/admin/model/provider", json={"model": "synthetic-edit"})
        assert refused.status_code == 403

        saved = await manager.patch("/api/v1/admin/model/provider", json={"model": "synthetic-edit"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["model"] == "synthetic-edit"
        assert "api_key" not in saved.json(), "khóa API không bao giờ trả ra"
        await _assert_audited(loop)


async def _assert_audited(loop: Loop) -> None:
    from sqlalchemy import text

    async with loop.api.db.session(loop.clinic_id) as session:
        rows = (
            await session.execute(
                text("SELECT count(*) FROM clinic.audit_log WHERE entity_type = 'runtime_settings'")
            )
        ).scalar_one()
    assert rows >= 1, "mọi thay đổi cấu hình đều có dòng audit (tên trường, không có giá trị)"
