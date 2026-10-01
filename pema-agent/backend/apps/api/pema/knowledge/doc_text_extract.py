# ported from: src/knowledge/doc-text-extract.ts
"""Dispatch text extraction by format for the knowledge base."""

from __future__ import annotations

from typing import Final, Literal, TypeGuard

from pema.knowledge.extract_docx_text import extract_docx_text
from pema.knowledge.extract_pdf_text import extract_pdf_text
from pema.knowledge.extract_xlsx_text import extract_xlsx_text

type DinhDangKb = Literal["txt", "md", "docx", "xlsx", "pdf"]

DINH_DANG_HO_TRO: Final[tuple[DinhDangKb, ...]] = ("txt", "md", "docx", "xlsx", "pdf")
"""The 5 source formats whose text the knowledge base can read."""


def la_dinh_dang_ho_tro(x: str) -> TypeGuard[DinhDangKb]:
    return x in DINH_DANG_HO_TRO


def doc_chu_tu_file(buf: bytes, dinh_dang: DinhDangKb) -> str:
    """Read raw text from a file by format, so ``cat_thanh_doan`` can cut it right after.

    Raises an error with a readable Vietnamese sentence when the file is broken - the caller (the source
    processing worker) catches it and writes it straight into ``kb_document.error`` for the operator to
    read, not an engineer. Each extractor takes care of translating the library error (broken zip, broken
    PDF, scanned PDF) into its Vietnamese sentence - this function only dispatches by format and adds no
    generic error layer (to avoid the error appearing twice, once from the extractor and once from here).
    """
    if dinh_dang in ("txt", "md"):
        return buf.decode("utf-8", errors="replace")
    if dinh_dang == "docx":
        return extract_docx_text(buf)
    if dinh_dang == "xlsx":
        return extract_xlsx_text(buf)
    return extract_pdf_text(buf)
