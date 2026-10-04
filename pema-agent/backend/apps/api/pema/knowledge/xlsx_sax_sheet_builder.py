# ported from: src/knowledge/xlsx-sax-sheet-builder.ts
"""``xl/worksheets/sheetN.xml`` -> text by ROW (a row is one meaningful record). Replaces the old
``ROW_RE``/``CELL_RE``/``V_RE`` - see sections 1.3 and 3.2 of the original research note."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pema.knowledge.ooxml_limits import (
    TRAN_SO_COT_EXCEL,
    TRAN_TONG_KY_TU_TRICH,
    TRAN_TONG_SO_O,
    LoiVuotTran,
)
from pema.knowledge.xlsx_sax_shared_strings import thay_the_escape_excel
from pema.shared.xml_sax_scan import SaxTag, XmlSaxHandlers

SPREADSHEETML_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

_CHU_CAI_DAU: Final = re.compile(r"^[A-Za-z]+")


@dataclass(slots=True)
class NganSachO:
    """Budget book shared by EVERY sheet of the same xlsx file - ``extract_xlsx_text`` creates ONE and passes
    it to each ``tao_xlsx_sheet_sax_builder()`` (as ``zip_stream_entry`` uses one session for the total
    ceiling). NOT a module-level variable: each ``doc_chu_tu_file`` needs its own.

    TWO axes, both shared - splitting into many sheets, each under the ceiling, must NOT dodge the total:
    * ``tong_o``: ALLOCATION WORK (real cells + padding cells from jumping columns) - ``TRAN_TONG_SO_O``;
    * ``tong_ky_tu``: REAL text gathered into the result - ``TRAN_TONG_KY_TU_TRICH``.

    ``tong_ky_tu`` once lived INSIDE the builder body (a local re-initialised per sheet) so the 8 MB ceiling
    turned out to be a PER-SHEET ceiling. ``sharedStrings`` amplifies this: one shared string of 100,000
    characters, each cell ``<c t="s"><v>0</v></c>`` is only ~25 XML bytes yet returns the WHOLE string.
    Measured in the original: 12 sheets x 83 cells (a 3.9 KB .xlsx, 13 entries, 996 cells - under EVERY
    zip/entry/cell ceiling) extracted 95.0 MB of text in 71 ms and no ceiling caught it; 250 sheets killed
    Node with a FATAL heap limit. The extraction timeout does not save it either: 250 sheets only take
    ~2.5 seconds."""

    tong_o: int = 0
    tong_ky_tu: int = 0


def gia_tri_thuoc_tinh(tag: SaxTag, local_name: str) -> str | None:
    for attr in tag.attributes.values():
        if attr.local == local_name:
            return attr.value
    return None


def chu_cot_thanh_chi_so(chu_cai: str) -> int:
    """ "B" -> 2, "AA" -> 27 (1-based column index, Excel style)."""
    idx = 0
    for c in chu_cai:
        idx = idx * 26 + (ord(c) - 64)  # 'A' = 65
    return idx


class XlsxSheetSaxBuilder(XmlSaxHandlers):
    """``chuoi_dung_chung``: the ``sharedStrings.xml`` array in EXACT index order. ``ngan_sach_o``: the budget
    book (cells + extracted characters) SHARED with the other sheets of the same file - see ``NganSachO``.
    It must NOT be replaced by a local variable in this class: the builder is created AGAIN for each sheet,
    so a local variable would turn the total ceiling into a per-sheet ceiling."""

    def __init__(self, chuoi_dung_chung: Sequence[str], ngan_sach_o: NganSachO) -> None:
        self._chuoi_dung_chung = chuoi_dung_chung
        self._ngan_sach_o = ngan_sach_o
        self._cac_dong: list[str] = []

        self._dong_hien_tai: list[str] = []
        self._cot_ky_vong = 1  # (1-based) column index the NEXT cell is expected at

        self._kieu_o: str | None = None  # t= attribute of the open <c>
        self._chi_so_cot_hien_tai = 1
        self._bo_dem_v = ""
        self._bo_dem_is = ""
        self._dang_trong_v = False
        self._dang_trong_f = False  # <f>...</f> is a FORMULA, not a value - always skipped
        self._dang_trong_is = False
        self._dang_trong_t_trong_is = False
        self._do_sau_rph = 0  # furigana phonetics in <is> - excluded as in sharedStrings

    def lay_cac_dong(self) -> list[str]:
        return self._cac_dong

    @property
    def dong_hien_tai(self) -> list[str]:
        """The row being built (read-only view, for the budget invariant test)."""
        return self._dong_hien_tai

    def _gia_tri_o_theo_loai(self) -> str:
        kieu = self._kieu_o
        if kieu == "s":
            # A cell t="s" with NO <v> (or an empty <v></v>) - ``_bo_dem_v == ""`` would give
            # ``Number("") === 0`` in the original and EXPOSE the string at index 0 of someone else's cell
            # instead of an empty cell. Measured: '<c t="s"><v>1</v></c><c t="s"></c>' came out as
            # "That | BI-MAT" - the empty cell B made up the text of cell A. Must test for empty BEFORE
            # converting to a number.
            if self._bo_dem_v.strip() == "":
                return ""
            try:
                gia_tri_so = float(self._bo_dem_v)
            except ValueError:
                return ""
            # ``chuoiDungChung[Number(v)] ?? ""``: NaN, a fraction or an index out of range give "".
            if not gia_tri_so.is_integer() or not 0 <= gia_tri_so < len(self._chuoi_dung_chung):
                return ""
            return thay_the_escape_excel(self._chuoi_dung_chung[int(gia_tri_so)])
        if kieu == "inlineStr":
            return thay_the_escape_excel(self._bo_dem_is)
        if kieu == "str":
            return thay_the_escape_excel(self._bo_dem_v)  # formula result of kind text
        if kieu == "b":
            return "Đúng" if self._bo_dem_v == "1" else "Sai"
        return self._bo_dem_v  # "e" (formula error), or no t= (a plain number)

    def _them_o_vao_dong(self, gia_tri: str, chi_so_cot: int) -> None:
        """Insert empty cells for a column that jumped - otherwise the next cell sticks to the previous one
        and the columns shift. Counts ALLOCATION WORK (padding cells + this cell) BEFORE the append loop,
        whether or not the row has text: a row of only empty cells is dropped at ``</row>`` BEFORE it is
        added to ``ngan_sach_o.tong_ky_tu``, so ``TRAN_TONG_KY_TU_TRICH`` does not catch this case."""
        # max(1, ...) - NEVER refund. ``_dong_hien_tai`` resets on each <row> but ``ngan_sach_o.tong_o``
        # does NOT (on purpose, it is shared across the whole sheet) - letting a NEGATIVE difference (a
        # LOW-column cell AFTER a HIGH-column cell in the same row, e.g. <c r="XFD1"/><c r="A1"/>) be added
        # straight in would be a fake "refund" that erases the real CPU cost of the append just run from the
        # book. Measured in the original: 100,000 rows of that shape ran 20 seconds with NO ceiling firing
        # (final tong_o only 100,000, each row "net" +1 though it cost 16,383 appends). Clamping to a floor
        # of 1: each call charges max(1, real appends + 1) >= real appends, so the accumulated ``tong_o``
        # is ALWAYS an upper bound of the total real appends - no column order can dodge it.
        so_o_them_vao = max(1, chi_so_cot - len(self._dong_hien_tai))
        self._ngan_sach_o.tong_o += so_o_them_vao
        if self._ngan_sach_o.tong_o > TRAN_TONG_SO_O:
            raise LoiVuotTran(
                "File xlsx có quá nhiều ô để xử lý (kể cả ô trống do cột nhảy cóc), vượt quá giới hạn "
                f"{TRAN_TONG_SO_O:,} ô".replace(",", ".")
                + ". Hãy rút gọn bảng tính hoặc tách thành nhiều file nhỏ hơn."
            )
        if len(self._dong_hien_tai) < chi_so_cot - 1:
            self._dong_hien_tai.extend([""] * (chi_so_cot - 1 - len(self._dong_hien_tai)))
        if len(self._dong_hien_tai) < chi_so_cot:
            self._dong_hien_tai.append(gia_tri)
        else:
            self._dong_hien_tai[chi_so_cot - 1] = gia_tri
        self._cot_ky_vong = chi_so_cot + 1

    def _chi_so_cot_cua(self, tag: SaxTag) -> int:
        r = gia_tri_thuoc_tinh(tag, "r")
        match = _CHU_CAI_DAU.match(r) if r is not None else None
        # A cell without r= inherits ``_cot_ky_vong`` - clamped to the SAME XFD ceiling as the branch with
        # r= below, otherwise a run of cells without r= after XFD1 pushes ``_cot_ky_vong`` past 16,384.
        if match is None:
            return min(self._cot_ky_vong, TRAN_SO_COT_EXCEL)
        chi_so = chu_cot_thanh_chi_so(match.group(0).upper())
        # MUST clamp: the real maximum column of Excel is XFD = 16,384. Without it ``_them_o_vao_dong``
        # would allocate a list by an UNBOUNDED index - r="AAAAAAA1" (7 letters) gives over 321 MILLION,
        # the gap-filling loop would allocate a list of that many elements (an OOM that no try/except
        # catches). No zip/entry/total/depth ceiling above catches this case.
        if chi_so > TRAN_SO_COT_EXCEL:
            raise LoiVuotTran(
                "File xlsx có ô ở cột vượt quá giới hạn thật của Excel (cột tối đa là XFD, tức "
                f"{TRAN_SO_COT_EXCEL}) - nghi ngờ file bị chỉnh sửa bất thường"
            )
        return chi_so

    def mo_the(self, tag: SaxTag) -> None:
        if tag.uri != SPREADSHEETML_NS:
            return
        local = tag.local
        if local == "row":
            self._dong_hien_tai = []
            self._cot_ky_vong = 1
        elif local == "c":
            self._kieu_o = gia_tri_thuoc_tinh(tag, "t")
            self._chi_so_cot_hien_tai = self._chi_so_cot_cua(tag)
            self._bo_dem_v = ""
            self._bo_dem_is = ""
            if tag.is_self_closing:
                self._them_o_vao_dong("", self._chi_so_cot_hien_tai)  # formatted but empty cell
        elif local == "v":
            self._dang_trong_v = True
        elif local == "f":
            self._dang_trong_f = True
        elif local == "is":
            self._dang_trong_is = True
        elif local == "rPh":
            if self._dang_trong_is:
                self._do_sau_rph += 1
        elif local == "t" and self._dang_trong_is and self._do_sau_rph == 0:
            self._dang_trong_t_trong_is = True

    def dong_the(self, tag: SaxTag) -> None:
        if tag.uri != SPREADSHEETML_NS:
            return
        local = tag.local
        if local == "row":
            if any(o.strip() for o in self._dong_hien_tai):
                dong = " | ".join(self._dong_hien_tai)
                self._ngan_sach_o.tong_ky_tu += len(dong)
                if self._ngan_sach_o.tong_ky_tu > TRAN_TONG_KY_TU_TRICH:
                    raise LoiVuotTran(
                        f"Chữ trích ra từ file vượt quá giới hạn {TRAN_TONG_KY_TU_TRICH // (1024 * 1024)} MB "
                        "(tính cho CẢ file, cộng mọi sheet). Hãy tách bảng tính thành nhiều file nhỏ hơn "
                        "rồi nạp thành nhiều nguồn."
                    )
                self._cac_dong.append(dong)
        elif local == "c":
            if not tag.is_self_closing:
                self._them_o_vao_dong(self._gia_tri_o_theo_loai(), self._chi_so_cot_hien_tai)
        elif local == "v":
            self._dang_trong_v = False
        elif local == "f":
            self._dang_trong_f = False
        elif local == "is":
            self._dang_trong_is = False
        elif local == "rPh":
            if self._dang_trong_is:
                self._do_sau_rph -= 1
        elif local == "t":
            self._dang_trong_t_trong_is = False

    def chu_van_ban(self, text: str) -> None:
        if self._dang_trong_f:
            return  # <f> always skipped - a formula string, not a value
        if self._dang_trong_v:
            self._bo_dem_v += text
        elif self._dang_trong_t_trong_is:
            self._bo_dem_is += text


def tao_xlsx_sheet_sax_builder(
    chuoi_dung_chung: Sequence[str], ngan_sach_o: NganSachO
) -> XlsxSheetSaxBuilder:
    return XlsxSheetSaxBuilder(chuoi_dung_chung, ngan_sach_o)
