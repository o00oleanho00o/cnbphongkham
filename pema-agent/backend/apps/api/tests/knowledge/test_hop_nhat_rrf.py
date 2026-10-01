# ported from: src/knowledge/hop-nhat-rrf.test.ts
"""Pure module (imports nothing but itself) - no environment or database."""

from __future__ import annotations

from pema.knowledge.hop_nhat_rrf import hop_nhat_rrf


def _identity(x: str) -> str:
    return x


def test_hop_nhat_rrf_one_list_rrf_keeps_the_order() -> None:
    """một danh sách: RRF giữ nguyên thứ tự"""
    r = hop_nhat_rrf([["a", "b", "c"]], _identity, 20)
    assert [x.item for x in r] == ["a", "b", "c"]


def test_hop_nhat_rrf_an_item_in_both_lists_is_pushed_up() -> None:
    """mục xuất hiện ở CẢ HAI danh sách được đẩy lên trên"""
    #  x: rank 2 and rank 1  ->  1/22 + 1/21
    #  a: rank 1, absent from list two  ->  1/21
    r = hop_nhat_rrf([["a", "x"], ["x", "b"]], _identity, 20)
    assert r[0].item == "x", "có mặt ở hai nguồn phải thắng hạng-1-một-nguồn"


def test_hop_nhat_rrf_small_k_gives_the_top_more_weight() -> None:
    """k nhỏ làm top có trọng lượng hơn"""
    nho = hop_nhat_rrf([["a"], ["b"]], _identity, 1)[0].diem
    lon = hop_nhat_rrf([["a"], ["b"]], _identity, 100)[0].diem
    assert nho > lon


def test_hop_nhat_rrf_an_empty_list_breaks_nothing() -> None:
    """danh sách rỗng không làm hỏng gì"""
    assert [x.item for x in hop_nhat_rrf([[], ["a"]], _identity, 20)] == ["a"]
