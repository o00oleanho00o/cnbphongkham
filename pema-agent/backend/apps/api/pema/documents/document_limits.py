# ported from: src/documents/document-limits.ts
"""Block over-sized content BEFORE building the file. The bot reads messages from strangers, so this is a real
gate, not a precaution: building a file is the most CPU-hungry thing in an agent turn.

Returns a Vietnamese reason instead of raising - the tool hands that exact sentence to the model so it can
shorten the content and call again (same rule as web_search / read_image).

Forced deviations: the tagged union ``LimitCheck`` became a small frozen dataclass (``ok`` plus ``reason``),
``getTuning`` became ``get_tuning_int`` (the DOCUMENT_MAX_* keys are number parameters), and the unicode-aware
regex ``[^\\p{L}\\p{N}\\s._-]`` of ``safeFileName`` is a per-character test (``unicodedata``
categories L* / N*) because ``re`` has no ``\\p{..}``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.documents.document_content_schema import (
    BulletsBlock,
    DocumentBlock,
    HeadingBlock,
    ParagraphBlock,
    Sheet,
    TableBlock,
    TextCell,
)


@dataclass(frozen=True)
class LimitCheck:
    """``LimitCheck``: ``ok`` is True, or False with the Vietnamese ``reason`` for the model."""

    ok: bool
    reason: str = ""


_OK = LimitCheck(ok=True)


def _fail(reason: str) -> LimitCheck:
    return LimitCheck(ok=False, reason=reason)


def _count_block_chars(block: DocumentBlock) -> int:
    if isinstance(block, HeadingBlock | ParagraphBlock):
        return len(block.text)
    if isinstance(block, BulletsBlock):
        return sum(len(item) for item in block.items)
    if isinstance(block, TableBlock):
        return sum(len(h) for h in block.headers) + sum(len(cell) for row in block.rows for cell in row)
    # The union is closed: what is left is a TwoColumnsBlock
    return sum(len(line) for line in [*block.left, *block.right])


def check_document_limits(blocks: list[DocumentBlock]) -> LimitCheck:
    max_blocks = get_tuning_int("DOCUMENT_MAX_BLOCKS")
    if len(blocks) > max_blocks:
        return _fail(f"Tài liệu có {len(blocks)} phần, vượt trần {max_blocks}. Hãy rút gọn rồi gọi lại.")

    max_rows = get_tuning_int("DOCUMENT_MAX_ROWS")
    for block in blocks:
        if isinstance(block, TableBlock) and len(block.rows) > max_rows:
            return _fail(f"Bảng có {len(block.rows)} dòng, vượt trần {max_rows}. Hãy bớt dòng rồi gọi lại.")
        # A table whose rows do not match the header's column count builds a distorted file - block it now
        if isinstance(block, TableBlock):
            bad = next((i for i, row in enumerate(block.rows) if len(row) != len(block.headers)), -1)
            if bad >= 0:
                return _fail(
                    f"Dòng {bad + 1} của bảng có {len(block.rows[bad])} ô nhưng bảng có "
                    f"{len(block.headers)} cột. Mọi dòng phải đủ số ô."
                )

    chars = sum(_count_block_chars(block) for block in blocks)
    max_chars = get_tuning_int("DOCUMENT_MAX_CHARS")
    if chars > max_chars:
        return _fail(f"Nội dung dài {chars} ký tự, vượt trần {max_chars}. Hãy tóm gọn lại rồi gọi lại.")

    return _OK


def check_spreadsheet_limits(sheets: list[Sheet]) -> LimitCheck:
    max_sheets = get_tuning_int("DOCUMENT_MAX_SHEETS")
    if len(sheets) > max_sheets:
        return _fail(f"Có {len(sheets)} sheet, vượt trần {max_sheets}.")

    max_rows = get_tuning_int("DOCUMENT_MAX_ROWS")
    chars = 0
    for sheet in sheets:
        if len(sheet.rows) > max_rows:
            return _fail(f'Sheet "{sheet.name}" có {len(sheet.rows)} dòng, vượt trần {max_rows}.')
        bad = next((i for i, row in enumerate(sheet.rows) if len(row) != len(sheet.headers)), -1)
        if bad >= 0:
            return _fail(
                f'Sheet "{sheet.name}" dòng {bad + 1} có {len(sheet.rows[bad])} ô nhưng có '
                f"{len(sheet.headers)} cột. Mọi dòng phải đủ số ô."
            )
        chars += sum(len(h) for h in sheet.headers)
        for row in sheet.rows:
            for cell in row:
                if isinstance(cell, TextCell):
                    chars += len(cell.value)

    max_chars = get_tuning_int("DOCUMENT_MAX_CHARS")
    if chars > max_chars:
        return _fail(f"Nội dung dài {chars} ký tự, vượt trần {max_chars}.")

    return _OK


def _keep_char(ch: str) -> bool:
    """Letters (with diacritics), digits, whitespace, ``.`` ``_`` ``-``."""
    return unicodedata.category(ch)[0] in ("L", "N") or ch.isspace() or ch in "._-"


def safe_file_name(raw: str, extension: Literal["docx", "xlsx"]) -> str:
    """Safe file name: drop the path, drop odd characters, force the right extension. The model may send
    "../../data/accounts/credentials" or "bao gia.exe" - both must become harmless before touching
    the disk."""
    base = re.sub(r"[\\/]", " ", raw)  # block path traversal from the very start
    base = re.sub(r"\.[^.]*\Z", "", base)  # drop the old extension (even .exe)
    base = "".join(ch for ch in base if _keep_char(ch))
    # Merge runs of dots, then trim dots at both ends: "../.." after the steps above is still ".. .." - it
    # cannot leave the folder, but it is a dirty file name, and a leading dot makes a hidden file on Linux
    base = re.sub(r"\.{2,}", ".", base)
    base = re.sub(r"\A[.\s]+|[.\s]+\Z", "", base)
    base = base.strip()[:80]
    return f"{base or 'tai-lieu'}.{extension}"
