# ported from: src/knowledge/kb-agent-binding.test.ts
from __future__ import annotations

import pytest

from pema.knowledge.kb_agent_binding import (
    agent_cua_nguon,
    dat_agent_cho_nguon,
    dat_nguon_cho_agent,
    dem_agent_theo_nguon,
    nguon_cua_agent,
)
from pema.knowledge.kb_source_store import KbSource, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


async def _hai_nguon(kb: KbHarness) -> tuple[KbSource, KbSource]:
    async with kb.session() as s:
        n1 = await tao_nguon(s, kb.clinic_id, ten="nguồn 1", loai="text", noi_dung_goc="a")
        n2 = await tao_nguon(s, kb.clinic_id, ten="nguồn 2", loai="text", noi_dung_goc="b")
    return n1, n2


async def test_kb_agent_binding_default_deny_an_agent_with_no_source_bound_reads_empty(kb: KbHarness) -> None:
    """agent chưa gán nguồn nào thì đọc được RỖNG - mặc định đóng"""
    kb.kb_database.add_agent("agent-moi")
    async with kb.session() as s:
        assert await nguon_cua_agent(s, kb.clinic_id, "agent-moi") == []


async def test_kb_agent_binding_default_deny_another_agent_being_bound_does_not_make_this_one_see_the_source(
    kb: KbHarness,
) -> None:
    """agent khác được gán không làm agent này thấy nguồn"""
    n1, _ = await _hai_nguon(kb)
    kb.kb_database.add_agent("agent-a")
    kb.kb_database.add_agent("agent-b")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "agent-a", [n1.id])
        assert await nguon_cua_agent(s, kb.clinic_id, "agent-b") == []


async def test_kb_agent_binding_default_deny_an_empty_id_also_reads_empty(kb: KbHarness) -> None:
    """id rỗng cũng đọc ra RỖNG - route /api/tools dùng chuỗi rỗng làm quy ước 'không có agent'"""
    async with kb.session() as s:
        assert await nguon_cua_agent(s, kb.clinic_id, "") == []


async def test_kb_agent_binding_reset_replaces_never_accumulates(kb: KbHarness) -> None:
    """đặt lại danh sách là THAY THẾ, không cộng dồn"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id, n2.id])
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n2.id])
        assert await nguon_cua_agent(s, kb.clinic_id, "a1") == [n2.id]


async def test_kb_agent_binding_reset_to_an_empty_list_revokes_all_access(kb: KbHarness) -> None:
    """đặt lại thành mảng rỗng thì thu hồi hết quyền đọc"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id, n2.id])
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [])
        assert await nguon_cua_agent(s, kb.clinic_id, "a1") == []


async def test_kb_agent_binding_reset_duplicate_ids_do_not_blow_up_unique(kb: KbHarness) -> None:
    """id trùng trong danh sách truyền vào không làm nổ UNIQUE"""
    n1, _ = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id, n1.id])
        assert await nguon_cua_agent(s, kb.clinic_id, "a1") == [n1.id]


async def test_agent_cua_nguon_a_source_bound_by_several_agents_returns_every_id(kb: KbHarness) -> None:
    """một nguồn được nhiều agent gán thì trả đủ cả hai id"""
    n1, _ = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    kb.kb_database.add_agent("a2")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id])
        await dat_nguon_cho_agent(s, kb.clinic_id, "a2", [n1.id])
        assert await agent_cua_nguon(s, kb.clinic_id, n1.id) == ["a1", "a2"]


async def test_agent_cua_nguon_a_source_no_agent_has_bound_returns_empty(kb: KbHarness) -> None:
    """nguồn chưa agent nào gán thì trả rỗng"""
    n1, _ = await _hai_nguon(kb)
    async with kb.session() as s:
        assert await agent_cua_nguon(s, kb.clinic_id, n1.id) == []


async def test_agent_cua_nguon_returns_only_agents_bound_to_exactly_this_source(kb: KbHarness) -> None:
    """chỉ trả agent gán ĐÚNG nguồn này, không lẫn nguồn khác"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    kb.kb_database.add_agent("a2")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id])
        await dat_nguon_cho_agent(s, kb.clinic_id, "a2", [n2.id])
        assert await agent_cua_nguon(s, kb.clinic_id, n1.id) == ["a1"]


async def test_dat_agent_cho_nguon_reverse_direction_replaces_and_only_touches_this_source(
    kb: KbHarness,
) -> None:
    """(từ kb-routes.test) gán ngược THAY THẾ và chỉ đụng nguồn đang gán, không xóa gán của nguồn khác"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("ban-hang")
    kb.kb_database.add_agent("ho-tro")
    async with kb.session() as s:
        await dat_agent_cho_nguon(s, kb.clinic_id, n1.id, ["ban-hang", "ho-tro"])
        await dat_agent_cho_nguon(s, kb.clinic_id, n2.id, ["ban-hang"])
        assert await agent_cua_nguon(s, kb.clinic_id, n1.id) == ["ban-hang", "ho-tro"]
        assert sorted(await nguon_cua_agent(s, kb.clinic_id, "ban-hang")) == sorted([n1.id, n2.id])
        await dat_agent_cho_nguon(s, kb.clinic_id, n1.id, [])
        assert await agent_cua_nguon(s, kb.clinic_id, n1.id) == [], (
            "cộng dồn thì gỡ quyền không bao giờ có tác dụng"
        )


async def test_dem_agent_theo_nguon_counts_per_source_and_an_unbound_source_has_no_key(kb: KbHarness) -> None:
    """(từ kb-routes.test) đếm ĐÚNG TỪNG nguồn; nguồn chưa gán ai vắng mặt (= 0)"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("ban-hang")
    async with kb.session() as s:
        await dat_agent_cho_nguon(s, kb.clinic_id, n1.id, ["ban-hang"])
        dem = await dem_agent_theo_nguon(s, kb.clinic_id)
    assert dem.get(n1.id, 0) == 1
    assert dem.get(n2.id, 0) == 0


async def test_kb_agent_binding_deleting_an_agent_removes_its_bindings_a_new_agent_with_the_same_id_inherits_none(
    kb: KbHarness,
) -> None:
    """(thêm) xóa agent rồi tạo lại CÙNG id không thừa kế gán cũ - khóa ngoại ON DELETE CASCADE"""
    n1, _ = await _hai_nguon(kb)
    kb.kb_database.add_agent("ban-hang")
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "ban-hang", [n1.id])
    kb.kb_database.delete_agent("ban-hang")
    kb.kb_database.add_agent("ban-hang")
    async with kb.session() as s:
        assert await nguon_cua_agent(s, kb.clinic_id, "ban-hang") == []


async def test_kb_agent_binding_only_approved_filter_hides_unapproved_sources(kb: KbHarness) -> None:
    """(thêm) chi_da_duyet: chỉ trả nguồn đã được bác sĩ duyệt"""
    n1, n2 = await _hai_nguon(kb)
    kb.kb_database.add_agent("a1")
    kb.kb_database.execute(
        "UPDATE agent.kb_document SET approved_by_clinical_owner = true WHERE id = :id", {"id": n2.id}
    )
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, "a1", [n1.id, n2.id])
        assert await nguon_cua_agent(s, kb.clinic_id, "a1", chi_da_duyet=True) == [n2.id]
        assert sorted(await nguon_cua_agent(s, kb.clinic_id, "a1")) == sorted([n1.id, n2.id])
