# ported from: src/knowledge/extract-pdf-text.ts
"""Read text from a PDF with ``pypdf``.

Forced deviation: ``unpdf`` (pdf.js wrapper) -> ``pypdf`` (pure Python, no native dependency).

``unpdf`` does NOT raise when a PDF has no text layer (a scanned image) - it returns an empty string - so
this case must be recognised here instead of letting the caller see an empty string and believe the document
is truly empty. A structurally broken PDF makes the library raise a raw English error ("Invalid PDF
structure.") - wrapped into a Vietnamese sentence so the operator can read it in ``kb_document.error``,
without being an engineer.

Pages are joined by a blank line (``mergePages: true`` of ``unpdf``), which is a chunk boundary for
``cat_thanh_doan``. The extraction runs inside the isolated worker process (``chay_trich_xuat_tach_luong``):
a hostile PDF that spins the CPU or eats memory is cut by the timeout/memory ceiling there, not here.
"""

from __future__ import annotations

import io

from pypdf import PdfReader


def extract_pdf_text(buf: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(buf))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as err:
        chi_tiet = str(err) or type(err).__name__
        raise ValueError(f"PDF này hỏng, không đọc được: {chi_tiet}") from err

    if not text.strip():
        raise ValueError("PDF này là ảnh quét, chưa đọc được chữ (chưa hỗ trợ OCR)")

    return text
