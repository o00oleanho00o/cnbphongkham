# ported from: src/knowledge/extract-xlsx-text.ts
"""``sharedStrings.xml`` + the ``xl/worksheets/sheetN.xml`` -> text by ROW.

Cut by ROW, not by cell: a row is a meaningful record (item name | price | warranty). Merging the whole
sheet into one block of text loses the structure, splitting cell by cell loses the relation between the
cells of one row.

Written on SAX (``xlsx_sax_shared_strings``, ``xlsx_sax_sheet_builder``) over the bounded inflate stream
whose TOTAL ceiling is shared by one ``PhienDocZip`` for every entry read in this function - this is what
catches the case the per-entry ceiling lets through: ``sharedStrings.xml`` PLUS every ``sheetN.xml`` may each
be under the entry ceiling while the total is over the archive ceiling. Replaces ``CELL_RE``/``T_TAG_RE``
entirely - see section 1.3 of the original research note (an empty self-closing cell swallowing the next
cell, a sharedString index leaking out as a meaningless number).

Forced deviation: ``async`` -> plain function (see ``zip_stream_entry``); ``Buffer`` -> ``bytes``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pema.knowledge.xlsx_sax_shared_strings import tao_shared_strings_sax_builder
from pema.knowledge.xlsx_sax_sheet_builder import NganSachO, tao_xlsx_sheet_sax_builder
from pema.shared.xml_sax_scan import quet_xml_theo_luong
from pema.shared.zip_stream_entry import mo_phien_doc_zip

_SHEET_FILE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")


def _sheet_number(entry: str) -> int:
    return int(re.findall(r"\d+", entry)[0])


def extract_xlsx_text(buf: bytes) -> str:
    phien = mo_phien_doc_zip(buf)
    entries = phien.danh_sach_entry()

    # A workbook of numbers only (no text cell) makes Excel drop sharedStrings.xml altogether
    chuoi_dung_chung: Sequence[str] = []
    if "xl/sharedStrings.xml" in entries:
        ss_builder = tao_shared_strings_sax_builder()
        quet_xml_theo_luong(phien.doc_entry_theo_luong("xl/sharedStrings.xml"), ss_builder)
        chuoi_dung_chung = ss_builder.lay_chuoi_dung_chung()

    # Read in FILE ORDER (sheet1.xml, sheet2.xml, ...) - an acceptable approximation: the knowledge base
    # needs to read ALL the content, not the exact display order if the user dragged sheets around in Excel.
    sheet_files = sorted((e for e in entries if _SHEET_FILE.match(e)), key=_sheet_number)
    if not sheet_files:
        raise ValueError("File xlsx không có sheet nào đọc được")

    # Use ONE budget book for EVERY sheet, on BOTH axes (allocated cells AND extracted characters) -
    # splitting into many sheets, each under its ceiling, must not dodge the total (the same "total
    # ceiling" principle already applied to ``zip_stream_entry``). The ``tong_ky_tu`` axis was once
    # forgotten: it lived inside the builder, which is created AGAIN for each sheet - see ``NganSachO``.
    ngan_sach_o = NganSachO()
    doan_theo_sheet: list[str] = []
    for file in sheet_files:
        # ``mo_phien_doc_zip`` / ``doc_entry_theo_luong`` already raise a readable Vietnamese error when
        # any ceiling is exceeded - no need to wrap another error layer here.
        sheet_builder = tao_xlsx_sheet_sax_builder(chuoi_dung_chung, ngan_sach_o)
        quet_xml_theo_luong(phien.doc_entry_theo_luong(file), sheet_builder)
        dong = sheet_builder.lay_cac_dong()
        if dong:
            doan_theo_sheet.append("\n".join(dong))

    ket_qua = "\n\n".join(doan_theo_sheet)
    if not ket_qua.strip():
        # Returning an empty string makes the worker mark "san_sang, 0 chunks" - see the full reason in
        # ``extract_docx_text`` (same principle, applied to xlsx).
        raise ValueError("Không đọc được chữ nào từ file xlsx (có thể mọi ô đều trống)")
    return ket_qua
