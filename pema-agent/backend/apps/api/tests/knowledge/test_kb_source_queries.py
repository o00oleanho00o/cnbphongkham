# ported from: src/knowledge/kb-source-queries.test.ts
from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

from pema.knowledge.kb_source_queries import (
    co_nguon_nao,
    gianh_nguon_cho_xu_ly,
    lay_nguon_theo_trang_thai,
)
from pema.knowledge.kb_source_store import dat_trang_thai, lay_nguon, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


async def test_gianh_nguon_cho_xu_ly_counter_is_raised_at_claim_time_not_when_it_fails(kb: KbHarness) -> None:
    """bá»™ Ä‘áº¿m tÄƒng NGAY LÃšC GIÃ€NH, khÃ´ng pháº£i lÃºc há»ng - chÆ°a xá»­ lÃ½ gÃ¬ mÃ  Ä‘áº¿m pháº£i Ä‘Ã£ tÄƒng"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        da_gianh = await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 2)
    assert da_gianh is True
    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    assert sau.so_lan_thu == 1, "chÆ°a xá»­ lÃ½ gÃ¬ mÃ  Ä‘áº¿m pháº£i Ä‘Ã£ tÄƒng"


async def test_gianh_nguon_cho_xu_ly_each_reclaim_after_going_back_to_pending_raises_the_count_by_1(
    kb: KbHarness,
) -> None:
    """má»—i láº§n giÃ nh láº¡i (sau khi tráº£ vá» cho_xu_ly) Ä‘áº¿m tÄƒng thÃªm 1"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 5)
        await dat_trang_thai(s, kb.clinic_id, n.id, "cho_xu_ly")  # simulates go_nguon_ket_dau_tick
        await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 5)
    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    assert sau.so_lan_thu == 2


async def test_gianh_nguon_cho_xu_ly_claiming_a_source_not_in_pending_fails_and_does_not_raise_the_count(
    kb: KbHarness,
) -> None:
    """giÃ nh nguá»“n KHÃ”NG á»Ÿ cho_xu_ly tháº¥t báº¡i, KHÃ”NG tÄƒng Ä‘áº¿m"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        await dat_trang_thai(s, kb.clinic_id, n.id, "san_sang", so_doan=1)
        da_gianh = await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 2)
    assert da_gianh is False
    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    assert sau.so_lan_thu == 0, "giÃ nh tháº¥t báº¡i thÃ¬ khÃ´ng Ä‘Æ°á»£c tÄƒng Ä‘áº¿m"


async def test_gianh_nguon_cho_xu_ly_a_source_at_the_ceiling_can_no_longer_be_claimed_even_if_pending(
    kb: KbHarness,
) -> None:
    """nguá»“n Ä‘Ã£ cháº¡m tráº§n (so_lan_thu >= tranLanThu) khÃ´ng giÃ nh Ä‘Æ°á»£c ná»¯a dÃ¹ Ä‘ang cho_xu_ly"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 1)  # raises attempts to 1, exactly the ceiling 1
        await dat_trang_thai(s, kb.clinic_id, n.id, "cho_xu_ly")  # still pending (rare case)
        da_gianh = await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 1)
    assert da_gianh is False, "so_lan_thu Ä‘Ã£ báº±ng tráº§n thÃ¬ khÃ´ng Ä‘Æ°á»£c giÃ nh thÃªm"


async def test_gianh_nguon_cho_xu_ly_two_concurrent_claims_exactly_one_wins(kb: KbHarness) -> None:
    """(thÃªm) hai lÆ°á»£t giÃ nh Ä‘á»“ng thá»i: Ä‘Ãºng Má»˜T lÆ°á»£t tháº¯ng - so sÃ¡nh-rá»“i-Ä‘á»•i nguyÃªn tá»­ trong Postgres"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")

    async def gianh() -> bool:
        async with kb.session() as s:
            return await gianh_nguon_cho_xu_ly(s, kb.clinic_id, n.id, 5)

    ket_qua = await asyncio.gather(*(gianh() for _ in range(8)))
    assert ket_qua.count(True) == 1
    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    assert sau.so_lan_thu == 1


async def test_lay_nguon_theo_trang_thai_waiting_list_does_not_pull_the_full_text(kb: KbHarness) -> None:
    """danh sÃ¡ch nguá»“n chá» KHÃ”NG kÃ©o noi_dung_goc"""
    async with kb.session() as s:
        await tao_nguon(s, kb.clinic_id, ten="to", loai="text", noi_dung_goc="x" * 5_000_000)
    async with kb.session() as s:
        ds = await lay_nguon_theo_trang_thai(s, kb.clinic_id, "cho_xu_ly")
    assert len(ds) == 1
    assert "noi_dung_goc" not in {f.name for f in fields(ds[0])}, (
        "kÃ©o toÃ n vÄƒn má»i nguá»“n chá» vÃ o RAM cÃ¹ng lÃºc"
    )


async def test_lay_nguon_theo_trang_thai_still_returns_the_other_metadata_fields(kb: KbHarness) -> None:
    """váº«n tráº£ Ä‘Ãºng cÃ¡c trÆ°á»ng metadata khÃ¡c (khÃ´ng chá»‰ bá» noiDungGoc mÃ  bá» luÃ´n field khÃ¡c)"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="co-du-lieu", loai="text", noi_dung_goc="abc")
    async with kb.session() as s:
        [row] = await lay_nguon_theo_trang_thai(s, kb.clinic_id, "cho_xu_ly")
    assert row.id == n.id
    assert row.ten == "co-du-lieu"
    assert row.so_lan_thu == 0


async def test_lay_nguon_theo_trang_thai_returns_only_the_asked_state(kb: KbHarness) -> None:
    """chá»‰ tráº£ nguá»“n ÄÃšNG tráº¡ng thÃ¡i Ä‘Æ°á»£c há»i, khÃ´ng láº«n tráº¡ng thÃ¡i khÃ¡c"""
    async with kb.session() as s:
        await tao_nguon(s, kb.clinic_id, ten="cho", loai="text", noi_dung_goc="a")
        xong = await tao_nguon(s, kb.clinic_id, ten="xong", loai="text", noi_dung_goc="b")
        await dat_trang_thai(s, kb.clinic_id, xong.id, "san_sang", so_doan=1)
    async with kb.session() as s:
        ds = await lay_nguon_theo_trang_thai(s, kb.clinic_id, "cho_xu_ly")
    assert len(ds) == 1
    assert ds[0].ten == "cho"


async def test_co_nguon_nao_is_false_on_an_empty_base_and_true_after_one_source(kb: KbHarness) -> None:
    """(thÃªm) coNguonNao: false khi kho trá»‘ng, true khi cÃ³ Ã­t nháº¥t má»™t nguá»“n"""
    async with kb.session() as s:
        assert await co_nguon_nao(s, kb.clinic_id) is False
        await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="a")
        assert await co_nguon_nao(s, kb.clinic_id) is True
