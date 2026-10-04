# ported from: src/knowledge/extract-docx-text.ts
"""``word/document.xml`` -> plain text, each ``<w:p>`` (Word paragraph) or each table becoming one
"paragraph", joined by "\\n\\n". A paragraph carrying a heading (through ``w:outlineLvl`` or a ``pStyle``
"HeadingN") is turned into a markdown line "#...# text" - so ``chunk_text`` recognises the title with the
SAME rule it already uses for .txt/.md.

Written on SAX (``docx_sax_paragraph_builder``) over the bounded inflate stream (``zip_stream_entry``),
REPLACING the old pair of regexes ``PARAGRAPH_RE``/``RUN_TEXT_RE`` entirely. Why: the original research
measured that pair as the root of 3 Critical bugs - quadratic ReDoS (a 1.7 KB bomb froze the event loop for
38 seconds), tab stops turned into raw XML (``<w:tab w:val="left" ...>`` wrongly matched ``<w:t[^>]*>``) and
tables losing their row structure.

Forced deviation: ``async`` -> plain function (see ``zip_stream_entry``); ``Buffer`` -> ``bytes``.
"""

from __future__ import annotations

from pema.knowledge.docx_sax_paragraph_builder import tao_docx_sax_builder
from pema.shared.xml_sax_scan import quet_xml_theo_luong
from pema.shared.zip_stream_entry import mo_phien_doc_zip


def extract_docx_text(buf: bytes) -> str:
    phien = mo_phien_doc_zip(buf)

    # EARLY check, a sentence the OPERATOR can read: a .zip (or .xlsx) renamed to .docx passes the "PK"
    # signature check (every zip file starts with exactly those 2 bytes, see ``kb_route_guards``) yet has no
    # word/document.xml at all. Without the check here the error would fall straight to
    # ``doc_entry_theo_luong`` with the developer's sentence (``Không tìm thấy "word/document.xml" trong
    # file``) - the person reading it on the dashboard does not know what "word/document.xml" is.
    if "word/document.xml" not in phien.danh_sach_entry():
        raise ValueError(
            "File này không phải .docx hợp lệ (thiếu nội dung Word bên trong) - có thể là file .zip đổi "
            "đuôi tên, hoặc file .docx đã bị hỏng."
        )

    builder = tao_docx_sax_builder()
    # ``mo_phien_doc_zip`` / ``doc_entry_theo_luong`` already raise a readable Vietnamese error when
    # ``buf`` is not a valid zip or exceeds any ceiling - no need to wrap another error layer here (a
    # missing document.xml is blocked above).
    quet_xml_theo_luong(phien.doc_entry_theo_luong("word/document.xml"), builder)

    ket_qua = "\n\n".join(builder.lay_doan_van_ban())
    if not ket_qua.strip():
        # Returning an empty string would let the worker (``kb_ingest_worker``) mark the source
        # "san_sang, 0 chunks" - a poisoned source (a docx that is all images/objects) looking healthy.
        # RAISE so the worker's "hong" branch catches it, the principle "an extractor must raise when it
        # extracts no text".
        raise ValueError(
            "Không đọc được chữ nào từ file docx (có thể chỉ chứa ảnh/đối tượng, không có văn bản)"
        )
    return ket_qua
