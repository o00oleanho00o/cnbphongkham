# ported from: src/knowledge/ooxml-zip-test-helper.ts
"""Helpers that build zip files BY HAND for the safe-OOXML-reading tests. NOT used by running code - zips are
built by hand (instead of calling a docx/xlsx renderer) to create edge cases the repo's generators NEVER
write (a bomb, an entry over the ceiling, deeply nested XML) - see ``tests/shared/test_read_zip_entry.py``
for the original reason for hand-built zips (the offset of each field must match EXACTLY what
``read_zip_entry`` / ``zip_stream_entry`` read).

Forced deviation: ``Buffer`` -> ``bytes``; ``crypto.randomBytes`` -> ``secrets.token_bytes``.
"""

from __future__ import annotations

import secrets
import struct
import zlib
from dataclasses import dataclass
from typing import Final

WORDML_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SPREADSHEETML_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@dataclass(frozen=True, slots=True)
class ZipEntryInput:
    name: str
    data: bytes


@dataclass(frozen=True, slots=True)
class _ZipEntryNenSan:
    """An entry ALREADY compressed - used when several entries share content so ``zlib`` is not run again on
    the SAME block of bytes (see ``build_zip_buffer_tai_su_dung_nen``)."""

    name: str
    compressed: bytes
    uncomp_size: int


def _deflate_raw(data: bytes, level: int = -1) -> bytes:
    compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def _rapon_mot_entry(entry: _ZipEntryNenSan, offset: int) -> tuple[bytes, bytes]:
    """Assemble the local section + central section for ONE compressed entry - shared by
    ``build_zip_buffer`` (compresses itself) and ``build_zip_buffer_tai_su_dung_nen`` (already compressed)."""
    name_buf = entry.name.encode("utf-8")

    local_header = bytearray(30)
    struct.pack_into("<I", local_header, 0, 0x04034B50)
    struct.pack_into("<H", local_header, 8, 8)  # method = deflate
    struct.pack_into("<I", local_header, 18, len(entry.compressed))
    struct.pack_into("<I", local_header, 22, entry.uncomp_size)
    struct.pack_into("<H", local_header, 26, len(name_buf))
    struct.pack_into("<H", local_header, 28, 0)
    local = bytes(local_header) + name_buf + entry.compressed

    central_header = bytearray(46)
    struct.pack_into("<I", central_header, 0, 0x02014B50)
    struct.pack_into("<H", central_header, 10, 8)
    struct.pack_into("<I", central_header, 20, len(entry.compressed))
    struct.pack_into("<I", central_header, 24, entry.uncomp_size)
    struct.pack_into("<H", central_header, 28, len(name_buf))
    struct.pack_into("<I", central_header, 42, offset)
    central = bytes(central_header) + name_buf

    return local, central


def _goi_zip(entries: list[_ZipEntryNenSan]) -> bytes:
    local_sections: list[bytes] = []
    central_sections: list[bytes] = []
    offset = 0
    for entry in entries:
        local, central = _rapon_mot_entry(entry, offset)
        local_sections.append(local)
        central_sections.append(central)
        offset += len(local)

    central_directory = b"".join(central_sections)
    local_total = b"".join(local_sections)

    eocd = bytearray(22)
    struct.pack_into("<I", eocd, 0, 0x06054B50)
    struct.pack_into("<H", eocd, 10, len(entries))
    struct.pack_into("<I", eocd, 12, len(central_directory))
    struct.pack_into("<I", eocd, 16, len(local_total))

    return local_total + central_directory + bytes(eocd)


def build_zip_buffer(entries: list[ZipEntryInput]) -> bytes:
    """Minimal zip, MANY entries - extends the 1-entry version of ``test_read_zip_entry``."""
    return _goi_zip(
        [
            _ZipEntryNenSan(name=e.name, compressed=_deflate_raw(e.data), uncomp_size=len(e.data))
            for e in entries
        ]
    )


def build_zip_buffer_tai_su_dung_nen(data: bytes, ten_cac_entry: list[str]) -> bytes:
    """MANY entries with the SAME content (``data``) but DIFFERENT names - compressed ONCE and reused,
    instead of ``build_zip_buffer`` running ``zlib`` again on the SAME block of bytes for each entry. Used
    for fixtures needing MANY large entries (``zip_nhieu_entry_vua_du``). ``level=1`` (FASTEST, not best):
    the ratio barely changes and a test only needs a ratio LOW ENOUGH not to hit the 500:1 check."""
    compressed = _deflate_raw(data, level=1)
    return _goi_zip(
        [_ZipEntryNenSan(name=n, compressed=compressed, uncomp_size=len(data)) for n in ten_cac_entry]
    )


def docx_tu_xml(fragment: str) -> bytes:
    """Wrap an XML fragment into a ``word/document.xml`` that is valid IN TERMS OF NAMESPACE - the
    ``xmlns:w=...`` at the root is mandatory, otherwise the namespace-aware parser raises "unbound
    namespace prefix" at the FIRST ``<w:...>`` tag, hiding the very mechanism under test (the depth
    counter) - a trap found while writing the original tests."""
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORDML_NS}"><w:body>{fragment}</w:body></w:document>'
    )
    return build_zip_buffer([ZipEntryInput("word/document.xml", document_xml.encode("utf-8"))])


def chu_kho_nen(so_byte: int) -> str:
    """HARD-TO-COMPRESS text (hex of random bytes) - for fixtures needing a LARGE inflated size that must NOT
    exceed the COMPRESSION RATIO ceiling (500:1, see ``ooxml_limits``). Content repeating ONE character
    ("x" * n) compresses beyond 1000:1 (measured in the original: 1 MB of repeated "x" -> 1033 bytes, ratio
    1015:1) and the ratio check would catch such a fixture BEFORE the entry/total check under test, hiding
    the code path. Hex of random bytes compresses ~1.85:1."""
    return secrets.token_bytes((so_byte + 1) // 2).hex()[:so_byte]


def docx_chi_co_anh() -> bytes:
    """A docx with one empty paragraph (no ``<w:t>``) - simulates a file that holds only an image."""
    return docx_tu_xml("<w:p><w:r><w:drawing/></w:r></w:p>")


def docx_nhieu_chu(so_mb_chu: float) -> bytes:
    """A docx holding about ``so_mb_chu`` MB of REAL text split into many paragraphs - a VALID document
    (under every ceiling of ``ooxml_limits``), just big. Used to measure the RAM breaker of the worker by
    LOWERING the memory ceiling, instead of building a hostile document: every existing ceiling is set
    precisely so that no document can eat hundreds of MB, so there is no valid "RAM bomb" to build -
    lowering the ceiling is the honest way to reach the branch under test. HARD-TO-COMPRESS text: repeated
    text compresses beyond 1000:1 and the ratio check would catch it first."""
    so_doan = 64
    moi_doan = int((so_mb_chu * 1024 * 1024) // so_doan)
    # Spaces spread evenly so ``cat_thanh_doan`` can cut many real chunks, not one solid block with no break.
    chu = chu_kho_nen(moi_doan)
    chu = " ".join(chu[i : i + 80] for i in range(0, len(chu), 80))
    return docx_tu_xml(f"<w:p><w:r><w:t>{chu}</w:t></w:r></w:p>" * so_doan)


def zip_entry_qua_tran() -> bytes:
    """Entry ``word/document.xml`` that inflates over the ONE-entry ceiling (32 MB)."""
    raw = b"A" * (33 * 1024 * 1024)  # compresses extremely well (all 'A') - fast test
    return build_zip_buffer([ZipEntryInput("word/document.xml", raw)])


def zip_nhieu_entry_vua_du() -> bytes:
    """xlsx-shaped: ``sharedStrings.xml`` + 3 sheets, EACH entry UNDER the entry ceiling (32 MB) but the TOTAL
    over the archive ceiling (64 MB) - exactly the case the per-entry ceiling lets through and the total
    ceiling must catch. EACH entry is XML with every tag CLOSED (``<sst><si><t>...text...</t></si></sst>``)
    WITH HARD-TO-COMPRESS text - on purpose, three traps otherwise: raw random bytes (not nested in a tag)
    make the parser fail on SYNTAX in the first chunk, hiding the accumulator under test; leaving a tag
    unclosed makes the first entry fail only at ``Parse(final)`` so the test never reaches entries 3-4;
    text repeating ONE character compresses beyond 1000:1 and the ratio check fires first. With full tags
    and hard text the first 3 entries pass (20+20+20 = 60 MB, ratio 1.85:1), the 4th hits the total."""
    noi_dung = f"<sst><si><t>{chu_kho_nen(20 * 1024 * 1024)}</t></si></sst>"
    moi_entry = noi_dung.encode("utf-8")
    return build_zip_buffer_tai_su_dung_nen(
        moi_entry,
        [
            "xl/sharedStrings.xml",
            "xl/worksheets/sheet1.xml",
            "xl/worksheets/sheet2.xml",
            "xl/worksheets/sheet3.xml",
        ],
    )


def xlsx_rong() -> bytes:
    """An xlsx made only of self-closing empty cells - no sharedStrings, no readable value."""
    sheet1 = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{SPREADSHEETML_NS}"><sheetData><row r="1"><c r="A1" s="1"/><c r="B1" s="1"/>'
        "</row></sheetData></worksheet>"
    )
    return build_zip_buffer([ZipEntryInput("xl/worksheets/sheet1.xml", sheet1.encode("utf-8"))])


def xlsx_tu_sheet_va_chuoi(sheet1_body: str, shared_strings: list[str]) -> bytes:
    """An xlsx with a HAND-WRITTEN ``xl/worksheets/sheet1.xml`` + ``sharedStrings.xml`` (not through a
    spreadsheet library) - needed for a self-closing cell AT THE END OF A ROW, with no cell behind it to let
    the "fill the column by the next cell" mechanism accidentally hide the defect."""
    return xlsx_nhieu_sheet_va_chuoi([sheet1_body], shared_strings)


def xlsx_nhieu_sheet_va_chuoi(sheet_bodies: list[str], shared_strings: list[str]) -> bytes:
    """Like ``xlsx_tu_sheet_va_chuoi`` but MANY sheets (``sheet1.xml``, ``sheet2.xml``, ...) sharing ONE
    ``sharedStrings.xml`` - needed for the cases that measure the TOTAL ceiling of the whole file: each sheet
    is under the ceiling but together they exceed it. A counter re-created per sheet would let exactly this
    shape through (see ``NganSachO``)."""
    items = "".join(f"<si><t>{s}</t></si>" for s in shared_strings)
    sst = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{SPREADSHEETML_NS}" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f"{items}</sst>"
    )

    def to_sheet(body: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{SPREADSHEETML_NS}"><sheetData>{body}</sheetData></worksheet>'
        )

    entries = [ZipEntryInput("xl/sharedStrings.xml", sst.encode("utf-8"))]
    entries.extend(
        ZipEntryInput(f"xl/worksheets/sheet{i + 1}.xml", to_sheet(body).encode("utf-8"))
        for i, body in enumerate(sheet_bodies)
    )
    return build_zip_buffer(entries)
