# ported from: src/knowledge/docx-sax-paragraph-builder.ts
"""State machine that reads ``word/document.xml`` through SAX events, replacing the old
``PARAGRAPH_RE``/``RUN_TEXT_RE`` - see section 3.1 of the original research note for each edge case (tab
stop in ``w:pPr`` versus in ``w:r``, self-closing ``<w:p/>``, tables keeping their row structure, headings
through ``w:outlineLvl``). Tracking of tables (nested ones included) lives in ``docx_sax_table_tracker``.
"""

from __future__ import annotations

import re
from typing import Final

from pema.knowledge.docx_sax_table_tracker import tao_docx_table_tracker
from pema.knowledge.ooxml_limits import TRAN_TONG_KY_TU_TRICH, LoiVuotTran
from pema.shared.xml_sax_scan import SaxTag, XmlSaxHandlers

W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

THE_BO_QUA_NOI_DUNG: Final = frozenset({"pPr", "rPr", "tblPr", "tcPr", "trPr", "sectPr"})
"""Entering these tags STOPS counting the text inside as paragraph content - it is a property/format, not
text the reader sees. ``<w:tab/>`` inside ``w:pPr><w:tabs>`` is the DEFINITION of a tab stop (not a real tab
character) so it is also skipped just by sitting inside ``pPr``, no need to list "tabs" separately."""

OUTLINE_LVL_TOI_DA: Final = 8
"""A valid outlineLvl is only 0-8 (Heading1-9). Word writes 9 for "Body Text" (ECMA-376) - NOT a heading,
though it uses the same outline-level mechanism."""

_HEADING_STYLE: Final = re.compile(r"^heading([1-9])$")


def gia_tri_thuoc_tinh(tag: SaxTag, local_name: str) -> str | None:
    for attr in tag.attributes.values():
        if attr.local == local_name:
            return attr.value
    return None


def cap_tu_style_id(style_id: str) -> int | None:
    """ "Heading2" / "Heading 2" / "heading 2"... -> 2. ``None`` if no match. Word writes the styleId in
    PascalCase with no space ("Heading2"); ``w:name`` in styles.xml (not read in this phase) uses the
    lowercase form with a space "heading 2" - trim + lowercase + dropping whitespace catches both with one
    regex."""
    chuan = re.sub(r"\s+", "", style_id.strip().lower())
    m = _HEADING_STYLE.match(chuan)
    return int(m.group(1)) if m else None


def _js_number(val: str) -> float | None:
    """``Number(val)``: ``None`` for NaN. (``Number("")`` is 0 in JS: an empty attribute reads as 0.)"""
    stripped = val.strip()
    if stripped == "":
        return 0.0
    try:
        return float(stripped)
    except ValueError:
        return None


class DocxSaxBuilder(XmlSaxHandlers):
    def __init__(self) -> None:
        self._doan: list[str] = []
        self._tong_ky_tu = 0

        self._bo_qua_noi_dung = 0  # >0: inside pPr/rPr/tblPr/tcPr/trPr/sectPr (any nesting level)
        self._dang_trong_run_text = False  # inside <w:t> - ONLY text here is content

        self._bo_dem_doan_van = ""  # buffer of the current paragraph (outside a table)
        self._cap_tieu_de: int | None = None  # from pStyle (tier 3)
        self._outline_lvl: int | None = None  # from w:outlineLvl (tier 1, takes priority)

        self._bang = tao_docx_table_tracker()  # stack of tables (nested ones included)

    def lay_doan_van_ban(self) -> list[str]:
        """The final list of "paragraphs" - each element is one paragraph or one table (rows joined by
        "\\n"), headings turned into a markdown "#" prefix."""
        return self._doan

    def _them_doan(self, text: str) -> None:
        if not text:
            return
        self._tong_ky_tu += len(text)
        if self._tong_ky_tu > TRAN_TONG_KY_TU_TRICH:
            raise LoiVuotTran(
                f"Chữ trích ra từ file vượt quá giới hạn {TRAN_TONG_KY_TU_TRICH // (1024 * 1024)} MB. "
                "Hãy tách tài liệu thành nhiều file nhỏ hơn rồi nạp thành nhiều nguồn."
            )
        self._doan.append(text)

    def _ket_thuc_doan_van(self) -> None:
        van_ban = self._bo_dem_doan_van.strip()
        if self._bang.dang_trong_o():
            self._bang.them_vao_o_dang_mo(van_ban)
        elif van_ban:
            # outlineLvl is 0-based (0 = Heading1) - tier 1 is more durable than a localised pStyle
            cap = self._outline_lvl + 1 if self._outline_lvl is not None else self._cap_tieu_de
            self._them_doan(f"{'#' * min(cap, 9)} {van_ban}" if cap else van_ban)
        self._bo_dem_doan_van = ""
        self._cap_tieu_de = None
        self._outline_lvl = None

    def mo_the(self, tag: SaxTag) -> None:
        if tag.uri != W_NS:
            return  # ignore drawing/mc/... - only wordprocessingml matters
        ten = tag.local

        if ten in THE_BO_QUA_NOI_DUNG:
            self._bo_qua_noi_dung += 1
            return
        if self._bo_qua_noi_dung > 0:
            # pStyle/outlineLvl MUST still be read although we are inside pPr - that is exactly where they
            # are declared. Every other tag inside the "skip content" zone is ignored.
            if ten == "pStyle":
                val = gia_tri_thuoc_tinh(tag, "val")
                if val is not None:
                    self._cap_tieu_de = cap_tu_style_id(val)
            elif ten == "outlineLvl":
                val = gia_tri_thuoc_tinh(tag, "val")
                # Word writes "9" for outline level "Body Text" (ECMA-376) - not a heading. Accept only 0-8
                # (Heading1-9); another value is ignored, letting ``_cap_tieu_de`` (tier 3) or no heading
                # at all decide instead.
                if val is not None:
                    n = _js_number(val)
                    if n is not None and 0 <= n <= OUTLINE_LVL_TOI_DA:
                        self._outline_lvl = int(n)
            return

        if ten == "p":
            self._bo_dem_doan_van = ""
            self._cap_tieu_de = None
            self._outline_lvl = None
        elif ten == "t":
            self._dang_trong_run_text = True
        elif ten == "tab":
            self._bo_dem_doan_van += "\t"  # reached only when NOT inside pPr - a real tab inside w:r
        elif ten in ("br", "cr"):
            self._bo_dem_doan_van += "\n"
        elif ten == "noBreakHyphen":
            self._bo_dem_doan_van += "-"
        elif ten == "tbl":
            self._bang.mo_bang()
        elif ten == "tr":
            self._bang.mo_hang()
        elif ten == "tc":
            self._bang.mo_o()

    def dong_the(self, tag: SaxTag) -> None:
        if tag.uri != W_NS:
            return
        ten = tag.local

        if ten in THE_BO_QUA_NOI_DUNG:
            self._bo_qua_noi_dung -= 1
            return
        if self._bo_qua_noi_dung > 0:
            return

        if ten == "t":
            self._dang_trong_run_text = False
        elif ten == "p":
            self._ket_thuc_doan_van()
        elif ten == "tc":
            self._bang.dong_o()
        elif ten == "tr":
            self._bang.dong_hang()
        elif ten == "tbl":
            self._bang.dong_bang(self._them_doan)

    def chu_van_ban(self, text: str) -> None:
        # ``<w:delText>`` (deleted text, track changes) and ``<w:instrText>`` (field code) do NOT match the
        # local name "t" so they are excluded automatically - no separate filter needed.
        if self._dang_trong_run_text and self._bo_qua_noi_dung == 0:
            self._bo_dem_doan_van += text


def tao_docx_sax_builder() -> DocxSaxBuilder:
    return DocxSaxBuilder()
