"""Admin changes of the families without an audit of their own leave one ``audit_log`` row (package G,
SECURITY-REVIEW-AI01 SEC-15; no zalo-agent source): the knowledge base, MCP servers, schedules and tool settings."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from pema.composition.testing import Loop, LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def _rows(loop: Loop, action: str) -> list[dict[str, object]]:
    async with loop.api.db.session(loop.clinic_id) as session:
        found = (
            (
                await session.execute(
                    text(
                        "SELECT actor_role, entity_type, entity_id, details FROM clinic.audit_log "
                        "WHERE action = :a ORDER BY occurred_at"
                    ),
                    {"a": action},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in found]


async def test_mot_thay_doi_thanh_cong_o_ho_tools_ghi_mot_dong_audit_chi_co_duong_dan(
    make_loop: LoopFactory,
) -> None:
    """đổi cấu hình tool thành công ghi một dòng audit (đường dẫn + mã trạng thái, không có thân yêu cầu)"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        manager = await loop.staff("manager")
        before = len(await _rows(loop, "admin.tools.patch"))
        changed = await manager.patch("/api/v1/admin/tools/web_fetch", json={"fallback_enabled": True})
        assert changed.status_code == 200, changed.text
        rows = await _rows(loop, "admin.tools.patch")
        assert len(rows) == before + 1
        assert rows[-1]["entity_type"] == "admin_route"
        assert rows[-1]["entity_id"] == "/api/v1/admin/tools/web_fetch"
        assert rows[-1]["actor_role"] == "manager"
        assert rows[-1]["details"] == {"status": 200}


async def test_thay_doi_bi_tu_choi_hoac_chi_doc_khong_ghi_audit(make_loop: LoopFactory) -> None:
    """403 và GET không để lại dòng audit"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        manager = await loop.staff("manager")
        cs = await loop.staff("cs.maianh")
        before = len(await _rows(loop, "admin.tools.patch"))
        refused = await cs.patch("/api/v1/admin/tools/web_fetch", json={"fallback_enabled": True})
        read = await manager.get("/api/v1/admin/tools")
        assert refused.status_code == 403
        assert read.status_code == 200
        assert len(await _rows(loop, "admin.tools.patch")) == before
        assert await _rows(loop, "admin.tools.get") == []
