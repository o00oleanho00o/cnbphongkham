# ported from: src/shared/read-zip-entry.ts
"""Read ONE entry of a zip file (used for ``.docx`` / ``.xlsx``, both zip archives of XML).

MUST go through the CENTRAL DIRECTORY, not the local file header: some libraries write zips in streaming
style and leave ``compSize = 0`` in the local header (flag bit 3, the real size is in a data descriptor
AFTER the data). Reading by the local header yields EMPTY data, and a test built on it would be green for
no reason because there is nothing to compare. The central directory always has the real size.

Hand written on ``struct`` + ``zlib`` so that no dependency is added just to inflate (the standard
``zipfile`` does not give the control over ceilings that ``zip_stream_entry`` needs).

Forced deviation: Node ``Buffer`` -> ``bytes``; ``RangeError`` on a damaged structure -> ``ValueError``
(``struct.error`` is translated, so a truncated archive is a catchable Vietnamese error).
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

EOCD_SIGNATURE: Final = bytes([0x50, 0x4B, 0x05, 0x06])
CENTRAL_HEADER_SIGNATURE: Final = 0x02014B50

TRAN_GIAI_NEN_MAC_DINH: Final = 300 * 1024 * 1024
"""Ceiling on the DECOMPRESSED data of one entry - stops a "zip bomb". The deflate ratio can reach ~1000:1,
so a file valid by its magic bytes (``PK``) and smaller than the UPLOAD ceiling can still inflate to many GB
and allocate a buffer BEFORE any size ceiling (``KB_MAX_FILE_MB``, up to 100 MB) can stop it. A structural
zip error is safe (caught), but without this ceiling an OOM kills the whole process (all accounts running
in it), and cannot be caught.

300 MB = 3x the largest file the knowledge base allows (100 MB): wide enough for a real docx/xlsx (none
inflates beyond a few tens of MB) yet small enough not to OOM a self-hosted 1-4 GB VPS. A FIXED constant,
not read from the ``KB_MAX_FILE_MB`` tuning: this module also serves the WRITE path of the bot
(self-generated docx/xlsx) and must not pull the knowledge base's own configuration into a shared utility.

Two limits of this mechanism, so it is not thought to stop more than it does:
* the ceiling is per ENTRY, not per archive: this function has no notion of a "session". The READ branch of
  the knowledge base (``sharedStrings.xml`` PLUS every ``sheetN.xml``) no longer goes through it, see
  ``zip_stream_entry`` (which reuses ``central_entries`` below) for the TOTAL archive ceiling;
* the size is checked as the data is produced, not preallocated, so peak memory can still approach the
  ceiling before the error is raised: it lowers the OOM risk, it does not remove it."""


@dataclass(frozen=True, slots=True)
class CentralEntry:
    name: str
    method: int
    comp_size: int
    uncomp_size: int
    """Size AFTER inflating as DECLARED by the central directory: NOT fully trustworthy (the spec allows
    lying), only used to refuse EARLY before inflating; the caller must still count real bytes while
    inflating."""
    local_offset: int


def central_entries(buf: bytes) -> Iterator[CentralEntry]:
    """Walk the central directory. Exported for ``zip_stream_entry`` (streaming read with a total ceiling)
    so the parsing, already correct and verified, is not written twice."""
    eocd = buf.rfind(EOCD_SIGNATURE)
    if eocd < 0:
        raise ValueError("Không phải file zip hợp lệ (thiếu End Of Central Directory)")

    try:
        (count,) = struct.unpack_from("<H", buf, eocd + 10)
        (off,) = struct.unpack_from("<I", buf, eocd + 16)
        for _ in range(count):
            (signature,) = struct.unpack_from("<I", buf, off)
            if signature != CENTRAL_HEADER_SIGNATURE:
                raise ValueError("Central directory hỏng")
            (method,) = struct.unpack_from("<H", buf, off + 10)
            (comp_size, uncomp_size) = struct.unpack_from("<II", buf, off + 20)
            (name_len, extra_len, comment_len) = struct.unpack_from("<HHH", buf, off + 28)
            (local_offset,) = struct.unpack_from("<I", buf, off + 42)
            yield CentralEntry(
                name=buf[off + 46 : off + 46 + name_len].decode("utf-8", errors="replace"),
                method=method,
                comp_size=comp_size,
                uncomp_size=uncomp_size,
                local_offset=local_offset,
            )
            off += 46 + name_len + extra_len + comment_len
    except struct.error as err:
        raise ValueError("Central directory hỏng") from err


def du_lieu_nen_cua_entry(buf: bytes, entry: CentralEntry) -> bytes:
    """RAW compressed data of one entry (not inflated) - sliced by the LOCAL header because the name/extra
    lengths there can differ from the central directory. Exported for ``zip_stream_entry``: the streaming
    read needs this very slice to feed it to a ``zlib`` decompressor instead of inflating in one call."""
    try:
        (name_len,) = struct.unpack_from("<H", buf, entry.local_offset + 26)
        (extra_len,) = struct.unpack_from("<H", buf, entry.local_offset + 28)
    except struct.error as err:
        raise ValueError("Central directory hỏng") from err
    start = entry.local_offset + 30 + name_len + extra_len
    return buf[start : start + entry.comp_size]


def read_zip_entry(
    buf: bytes, entry_name: str, max_output_bytes: int = TRAN_GIAI_NEN_MAC_DINH
) -> bytes | None:
    """Content of the inflated entry, or ``None`` if no entry has that name.

    ``max_output_bytes``: ceiling on the data AFTER inflating, default ``TRAN_GIAI_NEN_MAC_DINH``.
    Parametrised so a test can build an over-ceiling case with a small number, no real multi-GB bomb."""
    for entry in central_entries(buf):
        if entry.name != entry_name:
            continue
        data = du_lieu_nen_cua_entry(buf, entry)
        if entry.method == 0:
            return data
        inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        try:
            # max_length makes zlib stop WHILE inflating instead of allocating until OOM.
            out = inflater.decompress(data, max_output_bytes + 1)
        except zlib.error as err:
            raise ValueError(f'Entry "{entry_name}" bị hỏng, không giải nén được') from err
        if len(out) > max_output_bytes:
            raise ValueError(
                f'Entry "{entry_name}" giải nén ra vượt quá giới hạn an toàn (nghi ngờ zip bomb) '
                "- đã chặn trước khi giải nén hết"
            )
        return out
    return None


def read_zip_entry_text(buf: bytes, entry_name: str, max_output_bytes: int = TRAN_GIAI_NEN_MAC_DINH) -> str:
    """Entry as UTF-8 text; raises if missing (a test needs to know at once)."""
    data = read_zip_entry(buf, entry_name, max_output_bytes)
    if data is None:
        raise ValueError(f'Không tìm thấy "{entry_name}" trong file')
    return data.decode("utf-8", errors="replace")


def list_zip_entries(buf: bytes) -> list[str]:
    return [e.name for e in central_entries(buf)]
