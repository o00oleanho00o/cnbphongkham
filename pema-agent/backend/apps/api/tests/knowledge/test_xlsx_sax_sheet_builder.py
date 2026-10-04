# ported from: src/knowledge/xlsx-sax-sheet-builder.test.ts
"""Pure module (computation only, no environment or database)."""

from __future__ import annotations

from collections.abc import Callable

from pema.knowledge.xlsx_sax_sheet_builder import NganSachO, tao_xlsx_sheet_sax_builder
from pema.shared.xml_sax_scan import SaxTag, XmlAttr

SPREADSHEETML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def tao_prng(seed: int) -> Callable[[], float]:
    """Small PRNG (mulberry32), FIXED SEED - the fuzz must repeat EXACTLY at every run, never flicker with
    a bare ``random()`` (a flaky test is worse than no test, as the original review demanded)."""
    a = seed & 0xFFFFFFFF

    def imul(x: int, y: int) -> int:
        return (x * y) & 0xFFFFFFFF

    def rand() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rand


def so_thanh_chu_cot(n: int) -> str:
    """Column number (1-based) -> Excel letters ("A", "AA", "XFD"...) - the OPPOSITE direction of the
    module's internal ``chu_cot_thanh_chi_so``, to stuff into the r= attribute."""
    s = ""
    x = n
    while x > 0:
        s = chr(65 + ((x - 1) % 26)) + s
        x = (x - 1) // 26
    return s


def tao_tag(local: str, r: str | None, tu_dong: bool) -> SaxTag:
    attributes = {} if r is None else {"r": XmlAttr(local="r", value=r)}
    return SaxTag(uri=SPREADSHEETML_NS, local=local, attributes=attributes, is_self_closing=tu_dong)


def test_fuzz_bat_bien_150_runs_random_columns_20_percent_without_r_all_self_closing_tong_o_is_always_at_least_the_real_append_count() -> (
    None
):
    """150 lượt, cột ngẫu nhiên 1..16.384, 20% ô không r=, toàn ô tự đóng - tongO luôn >= tổng push mảng THẬT"""
    # INVARIANT to keep (independent of any specific input shape): "no column order in a row makes
    # ``_them_o_vao_dong`` run real appends without ``tong_o`` recording that work". The original patched
    # Array.prototype.push to COUNT the real pushes. Here the row only ever grows by append and resets at
    # the next <row>, so the real number of appends of a row is exactly the length of the row when it
    # closes - read from the builder before the next row resets it.
    #
    # Every cell is SELF-CLOSING with an empty value (no t="s"/<v> reached) - on purpose:
    # ``any(o.strip())`` is always false so ``_cac_dong.append`` (at </row>) NEVER runs.
    so_luot = 150
    seed = 260809
    rand = tao_prng(seed)

    for luot in range(so_luot):
        ngan_sach_o = NganSachO()
        b = tao_xlsx_sheet_sax_builder([], ngan_sach_o)
        so_push_that = 0
        so_hang = 1 + int(rand() * 5)
        for _ in range(so_hang):
            b.mo_the(tao_tag("row", None, False))
            so_o = 1 + int(rand() * 8)
            for _ in range(so_o):
                co_r = rand() >= 0.2  # 20% cells without r= - inherit the expected column
                cot = 1 + int(rand() * 16384)  # exactly the 1..XFD edge
                tag = tao_tag("c", f"{so_thanh_chu_cot(cot)}1" if co_r else None, True)
                b.mo_the(tag)
                b.dong_the(tag)
            so_push_that += len(b.dong_hien_tai)  # real appends of this row (grows only)
            b.dong_the(tao_tag("row", None, False))
        assert so_push_that <= ngan_sach_o.tong_o, (
            f"lượt {luot} (seed {seed}): soPush thật={so_push_that} > tongO={ngan_sach_o.tong_o} "
            "- hoàn quỹ ÂM lọt qua"
        )
