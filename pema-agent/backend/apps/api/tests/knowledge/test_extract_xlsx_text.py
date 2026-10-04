# ported from: src/knowledge/extract-xlsx-text.test.ts
"""Forced deviation: the original builds its spreadsheets with ``renderXlsx`` (the document tool of the bot,
package D4 here). This test builds them with ``openpyxl`` directly - the library D4's renderer sits on - and
by hand where a CACHED formula value is needed (``openpyxl`` cannot write one, ``exceljs`` can)."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

import pytest
from openpyxl import Workbook

from pema.knowledge.doc_text_extract import doc_chu_tu_file
from pema.knowledge.ooxml_zip_test_helper import (
    chu_kho_nen,
    xlsx_nhieu_sheet_va_chuoi,
    xlsx_rong,
    xlsx_tu_sheet_va_chuoi,
    zip_nhieu_entry_vua_du,
)

FIXTURES = Path(__file__).parent / "fixtures"


def excel_o_rong() -> bytes:
    return (FIXTURES / "excel-o-rong-co-dinh-dang.xlsx").read_bytes()


def render_xlsx(sheets: list[tuple[str, list[str], list[list[str | int]]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    for name, headers, rows in sheets:
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def test_extract_xlsx_text_via_doc_chu_tu_file_each_row_becomes_a_line_cells_joined_by_pipe() -> None:
    """mỗi hàng thành một dòng chữ, các ô nối bằng ' | '"""
    buf = render_xlsx([("Bảng giá", ["Món", "Giá"], [["Cà phê", 25000]])])
    chu = doc_chu_tu_file(buf, "xlsx")
    assert re.search(r"Cà phê \| 25000", chu)


def test_extract_xlsx_text_via_doc_chu_tu_file_header_row_is_read_too_not_only_data_rows() -> None:
    """hàng header cũng đọc ra, không chỉ hàng dữ liệu"""
    buf = render_xlsx([("Bảng giá", ["Món", "Giá"], [["Trà", 15000]])])
    chu = doc_chu_tu_file(buf, "xlsx")
    assert re.search(r"Món \| Giá", chu)


def test_extract_xlsx_text_via_doc_chu_tu_file_several_sheets_are_all_read_not_only_the_first() -> None:
    """nhiều sheet đều đọc được, không chỉ sheet đầu"""
    buf = render_xlsx([("Sheet A", ["X"], [["một"]]), ("Sheet B", ["Y"], [["hai"]])])
    chu = doc_chu_tu_file(buf, "xlsx")
    assert "một" in chu
    assert "hai" in chu


def test_extract_xlsx_text_via_doc_chu_tu_file_formula_cell_reads_the_computed_value_not_the_formula_string() -> (
    None
):
    """ô công thức đọc ra GIÁ TRỊ đã tính, không phải chuỗi công thức"""
    buf = xlsx_tu_sheet_va_chuoi(
        '<row r="1"><c r="A1"><v>2</v></c><c r="B1"><v>1500</v></c><c r="C1"><f>A1*B1</f><v>3000</v></c></row>',
        [],
    )
    chu = doc_chu_tu_file(buf, "xlsx")
    assert "3000" in chu, "phải ra giá trị đã tính (2 x 1500), không phải '=A2*B2'"
    assert "A1*B1" not in chu


def test_extract_xlsx_text_via_doc_chu_tu_file_broken_xlsx_not_a_zip_raises_a_readable_vietnamese_error() -> (
    None
):
    """file xlsx hỏng (không phải zip) ném lỗi tiếng Việt đọc được"""
    with pytest.raises(ValueError, match=r"(?i)không phải file zip"):
        doc_chu_tu_file(b"khong phai file zip", "xlsx")


def test_extract_xlsx_text_real_excel_fixture_self_closing_empty_cell_does_not_swallow_the_next_cell() -> (
    None
):
    """ô rỗng tự đóng của Excel KHÔNG nuốt ô kế tiếp"""
    # The case MEASURED as broken in the old regex version: "Mon | 1" instead of "Mon |  | Gia" - the 1 is
    # the sharedString INDEX leaking out, not real text. The fixture holds unaccented text ("Mon"/"Gia") -
    # exactly the bytes Excel wrote, not a missing-diacritics mistake of the test.
    chu = doc_chu_tu_file(excel_o_rong(), "xlsx")
    dong_dau = chu.split("\n")[0]
    assert re.search(r"Mon \|\s*\| Gia", dong_dau), f"hàng đầu đọc ra: {dong_dau!r}"
    dong_hai = chu.split("\n")[1]
    assert re.search(r"Ca phe \|\s*\| 25000", dong_hai), f"hàng hai đọc ra: {dong_hai!r}"


def test_extract_xlsx_text_real_excel_fixture_self_closing_empty_cell_at_the_end_of_a_row_keeps_the_column_count() -> (
    None
):
    """ô rỗng tự đóng Ở CUỐI HÀNG vẫn giữ đúng số cột (không có ô sau để lấp hộ)"""
    # Different from the case above: the real Excel fixture has the empty cell in the MIDDLE of a row, so
    # the "fill the column by the next cell" mechanism accidentally hides a missing self-closing-cell
    # handling. This test puts the empty cell AT THE END - no later cell to fill in - isolating exactly the
    # "self-closing cell" branch.
    buf = xlsx_tu_sheet_va_chuoi(
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" s="1"/></row>',
        ["X", "Y", "Z"],
    )
    chu = doc_chu_tu_file(buf, "xlsx")
    dong = chu.split("\n")
    assert dong[0] == "X | Y"
    assert dong[1] == "Z | ", f"hàng 2 phải giữ đủ 2 cột (ô B rỗng ở cuối): {dong[1]!r}"


def test_extract_xlsx_text_real_excel_fixture_cell_t_s_without_v_does_not_invent_content_from_another_cell() -> (
    None
):
    """ô t="s" KHÔNG có <v> (rỗng nhưng không tự đóng) không bịa nội dung từ ô khác"""
    # The case MEASURED as broken: an empty buffer converted to a number gave 0 -> took the string at index
    # 0 of sharedStrings although this cell declares no index. Different from the self-closing case: this
    # cell is NOT self-closing (<c t="s"></c>) but has no <v> inside - another code path.
    buf = xlsx_tu_sheet_va_chuoi(
        '<row r="1"><c r="A1" t="s"><v>1</v></c><c r="B1" t="s"></c></row>',
        ["Bi-mat", "That"],
    )
    chu = doc_chu_tu_file(buf, "xlsx")
    assert chu == "That | ", f'ô B1 rỗng không được bịa ra "Bi-mat": {chu!r}'


# Measured BEFORE the fix in the original: the column letters were not clamped, and filling a gap
# allocated an array by the index derived from r= - r="AAAAAAA1" (7 letters) gave over 321 MILLION, the
# gap-filling loop allocated an array of that many elements. The fix keeps that from ever happening.


def test_tran_cot_excel_column_aaaaaaa1_321_million_is_refused_at_once_without_allocating_a_huge_array() -> (
    None
):
    """cột r="AAAAAAA1" (~321 triệu) bị từ chối NGAY, không cấp phát mảng khổng lồ"""
    buf = xlsx_tu_sheet_va_chuoi('<row r="1"><c r="AAAAAAA1" t="s"><v>0</v></c></row>', ["x"])
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn thật của Excel"):
        doc_chu_tu_file(buf, "xlsx")


def test_tran_cot_excel_column_aaaaa1_475_thousand_still_over_xfd_leaks_no_junk_into_the_result() -> None:
    """cột r="AAAAA1" (~475 nghìn, vẫn vượt XFD) KHÔNG để lọt ký tự rác nào vào kết quả"""
    buf = xlsx_tu_sheet_va_chuoi('<row r="1"><c r="AAAAA1" t="s"><v>0</v></c></row>', ["x"])
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn thật của Excel"):
        doc_chu_tu_file(buf, "xlsx")


def test_tran_cot_excel_column_xfd1_16384_the_last_real_column_still_reads_normally() -> None:
    """cột XFD1 (16.384, cột CUỐI CÙNG thật của Excel) vẫn đọc được bình thường - không kẹp nhầm ca hợp lệ"""
    buf = xlsx_tu_sheet_va_chuoi('<row r="1"><c r="XFD1" t="s"><v>0</v></c></row>', ["Cot cuoi"])
    chu = doc_chu_tu_file(buf, "xlsx")
    assert chu.endswith("Cot cuoi")


def test_tran_cot_excel_cells_without_r_after_xfd1_do_not_push_the_column_count_past_16384() -> None:
    """ô KHÔNG có r= sau ô XFD1 không đẩy số cột vượt 16.384 - kẹp cotKyVong đúng trần (O1)"""
    # A cell without r= inherits the next expected column; before the fix it was not clamped to XFD in this
    # branch (only the branch WITH r=). After the fix every cell without r= AFTER XFD1 overwrites exactly
    # column 16,384. The XFD1 cell wrote "9" first but is OVERWRITTEN by the last write ("1") - the right
    # consequence of clamping. There is only ONE row in this fixture; do NOT strip() before split(" | "):
    # the row has 16,383 empty cells FIRST so the string starts with a REAL space.
    hang = '<c r="XFD1"><v>9</v></c>' + "<c><v>1</v></c>" * 5000
    buf = xlsx_tu_sheet_va_chuoi(f"<row>{hang}</row>", [])
    chu = doc_chu_tu_file(buf, "xlsx")
    so_cot = len(chu.split(" | "))
    assert so_cot == 16384, f"phải đúng 16.384 cột (trần XFD), đo được {so_cot}"


def test_tran_cot_excel_100000_rows_of_empty_cells_at_column_xfd_are_refused_in_under_a_second_ceiling_by_allocation_work() -> (
    None
):
    """100.000 hàng ô rỗng ở cột XFD bị từ chối trong dưới 1 giây - trần theo CÔNG CẤP PHÁT, không theo chữ trích ra"""
    # Clamping ONE cell (TRAN_SO_COT_EXCEL) only lowered the bug from "kill the process" to "freeze the
    # event loop for minutes". Each row has 1 self-closing cell at column XFD (s=1, no t=) - a row of only
    # empty cells is dropped BEFORE it is added to tong_ky_tu, so TRAN_TONG_KY_TU_TRICH cannot catch it,
    # yet the gap-filling loop still runs 16,383 appends PER ROW. Measured BEFORE TRAN_TONG_SO_O existed:
    # 100,000 rows -> 21.7 seconds of frozen loop in the original.
    hang = '<row><c r="XFD1" s="1"/></row>' * 100_000
    buf = xlsx_tu_sheet_va_chuoi(hang, [])
    t0 = time.perf_counter()
    with pytest.raises(Exception, match=r"(?i)quá nhiều ô"):
        doc_chu_tu_file(buf, "xlsx")
    ton_ms = (time.perf_counter() - t0) * 1000
    assert ton_ms < 1000, f"tốn {ton_ms}ms - phải dưới 1 giây (trước khi sửa: 21 700ms)"


def test_tran_cot_excel_descending_columns_xfd1_then_a1_do_not_refund_budget_so_it_still_refuses_in_under_a_second() -> (
    None
):
    """hàng có cột GIẢM DẦN (XFD1 rồi A1) không hoàn quỹ - BẤT BIẾN: tongO luôn >= số push mảng thật đã chạy"""
    # The INVARIANT to keep, not one specific string: "no input makes the gap-filling run real appends
    # without ``tong_o`` recording that work". 2 cells per row in DESCENDING order (column 16,384 first,
    # then column 1) - exactly the shape measured as broken: the second cell "refunded" 16,383 though the
    # append loop still ran for the XFD1 cell. After clamping the floor to 1 each row costs 16,384 + 1 into
    # ``tong_o`` so the 2,000,000 ceiling is exceeded at about row 123: refused VERY quickly.
    hang = '<row><c r="XFD1" s="1"/><c r="A1" s="1"/></row>' * 100_000
    buf = xlsx_tu_sheet_va_chuoi(hang, [])
    t0 = time.perf_counter()
    with pytest.raises(Exception, match=r"(?i)quá nhiều ô"):
        doc_chu_tu_file(buf, "xlsx")
    ton_ms = (time.perf_counter() - t0) * 1000
    assert ton_ms < 1000, (
        f"tốn {ton_ms}ms - phải dưới 1 giây (trước khi sửa: không bao giờ bị chặn, khoá ~20s)"
    )


def test_xlsx_bomb_and_ceilings_total_inflate_over_the_ceiling_is_refused_although_each_entry_is_under_the_entry_ceiling() -> (
    None
):
    """tổng giải nén vượt trần bị từ chối dù mỗi entry đều dưới trần"""
    # A per-ENTRY ceiling is not enough: xlsx reads sharedStrings.xml PLUS every sheet - 4 entries x 20 MB
    # (each under the 32 MB ceiling) but 80 MB in total over the 64 MB archive ceiling (see
    # ooxml_zip_test_helper for why 20 MB with full tags instead of leaving them open).
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn"):
        doc_chu_tu_file(zip_nhieu_entry_vua_du(), "xlsx")


def test_xlsx_bomb_and_ceilings_xlsx_of_only_empty_cells_raises() -> None:
    """xlsx toàn ô rỗng NÉM lỗi"""
    with pytest.raises(ValueError, match=r"(?i)không đọc được chữ nào"):
        doc_chu_tu_file(xlsx_rong(), "xlsx")


def test_xlsx_bomb_and_ceilings_text_over_the_8_mb_ceiling_is_refused_with_the_right_message_not_mislabelled_invalid_xml() -> (
    None
):
    """chữ trích ra vượt trần 8 MB (xlsx) bị từ chối với thông báo ĐÚNG NGHĨA, KHÔNG bị dán nhãn sai 'XML không hợp lệ'"""
    # Same hole as the docx side but a different code path (xlsx_sax_sheet_builder, checked at </row> and
    # not at </w:p>) - needs its own test.
    buf = xlsx_tu_sheet_va_chuoi(
        f'<row r="1"><c r="A1" t="inlineStr"><is><t>{chu_kho_nen(int(8.5 * 1024 * 1024))}</t></is></c></row>',
        [],
    )
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn 8 MB") as excinfo:
        doc_chu_tu_file(buf, "xlsx")
    assert not re.search("(?i)XML không hợp lệ", str(excinfo.value)), (
        "không được dán nhãn sai là lỗi cú pháp XML"
    )


def test_xlsx_bomb_and_ceilings_text_accumulated_over_many_sheets_over_8_mb_is_refused_each_sheet_alone_is_under_it() -> (
    None
):
    """chữ trích ra CỘNG DỒN qua NHIỀU SHEET vượt trần 8 MB bị từ chối - mỗi sheet đều dưới trần"""
    # The case MEASURED as broken: ``tong_ky_tu`` lived inside the builder body, and the extractor created
    # a builder ONCE PER SHEET - the 8 MB ceiling turned out to be a PER-SHEET ceiling. Amplified by
    # sharedStrings: one shared string of 100,000 characters, each ``<c t="s"><v>0</v></c>`` is only ~25
    # XML bytes yet returns the WHOLE string. 12 sheets x 83 cells = 8,300,000 characters PER SHEET (UNDER
    # the 8,388,608 ceiling - each sheet alone is valid), 99,600,000 characters = 95.0 MB in total.
    chuoi_dung_chung = "A" * 100_000
    than_sheet = '<row><c t="s"><v>0</v></c></row>' * 83
    buf = xlsx_nhieu_sheet_va_chuoi([than_sheet for _ in range(12)], [chuoi_dung_chung])

    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn 8 MB"):
        doc_chu_tu_file(buf, "xlsx")


def test_xlsx_bomb_and_ceilings_one_sheet_under_the_ceiling_still_reads_the_cumulative_ceiling_does_not_clamp_a_valid_case() -> (
    None
):
    """MỘT sheet dưới trần vẫn đọc bình thường - trần cộng dồn không kẹp nhầm ca hợp lệ"""
    # The NEGATIVE side of the case above: same shape (big shared string, t="s" cells) but a total UNDER
    # the ceiling must read out text, not raise. Without this case a patch that "always raises" would also
    # make the case above green.
    buf = xlsx_nhieu_sheet_va_chuoi(
        ['<row><c t="s"><v>0</v></c></row>' * 2 for _ in range(3)],
        ["A" * 100_000],
    )
    chu = doc_chu_tu_file(buf, "xlsx")
    assert len(chu) == 3 * 2 * 100_000 + 3 * 1 + 2 * 2, f"độ dài chữ trích ra: {len(chu)}"
