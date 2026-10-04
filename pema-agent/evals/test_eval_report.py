# ported from: none (``eval-report.ts`` had no test in the original)
"""The result table: pure presentation, so it is checked with hand-built results.

The table must be readable in a Windows terminal and pasteable into a report: no ANSI codes.
"""

from __future__ import annotations

from evals.eval_report import KetQuaCase, in_bang


def render(kq: list[KetQuaCase]) -> str:
    lines: list[str] = []
    in_bang(kq, lines.append)
    return "\n".join(lines)


def test_in_bang_dem_so_case_dat_va_liet_ke_case_hong_voi_ly_do_va_cau_tra_loi() -> None:
    kq = [
        KetQuaCase(ten="tra-cuu", dat=True, tool_da_goi=["web_search"], tokens=1200, giay=3.46, tra_loi="ok"),
        KetQuaCase(
            ten="gio-chinh-xac",
            dat=False,
            tool_da_goi=[],
            tokens=900,
            giay=1.0,
            tra_loi="Chắc khoảng 3 giờ",
            ly_do_hong=['Phải gọi "get_datetime" nhưng không gọi (đã gọi: không tool nào)'],
        ),
    ]
    text = render(kq)

    assert "1/2 đạt" in text
    assert "HỎNG: gio-chinh-xac" in text
    assert '  - Phải gọi "get_datetime"' in text
    assert '  Bot trả lời: "Chắc khoảng 3 giờ"' in text
    assert "3.5" in text, "seconds are printed with one decimal"
    assert "(không)" in text, "a case that called no tool says so"


def test_in_bang_khong_dung_ma_mau_ansi() -> None:
    text = render([KetQuaCase(ten="x", dat=False, tool_da_goi=[], tokens=1, giay=0.1, tra_loi="")])
    assert "\x1b[" not in text


def test_in_bang_cat_ten_dai_bang_dau_ngang_va_cat_cau_tra_loi_o_300_ky_tu() -> None:
    kq = [
        KetQuaCase(
            ten="ten-case-rat-rat-dai-vuot-cot",
            dat=False,
            tool_da_goi=[],
            tokens=1,
            giay=0.1,
            tra_loi="a" * 500,
        )
    ]
    text = render(kq)

    assert "ten-case-rat-ra~" in text
    assert "a" * 300 in text
    assert "a" * 301 not in text
