# ported from: src/shared/zip-stream-entry.ts
"""Read zip entries as a STREAM, replacing ``read_zip_entry_text`` for the OOXML reading branch of the
knowledge base (docx/xlsx); ``read_zip_entry`` is unchanged and still serves the WRITE path of the bot with
its old one-entry-at-a-time behaviour.

Core difference from ``read_zip_entry``: never builds ONE ``bytes`` or ``str`` holding the WHOLE inflated
content. Each chunk comes straight out of a ``zlib`` decompressor, bytes are counted WHILE inflating, and
the stream stops early when a ceiling is crossed: the peak memory is about the ceiling, not the size the
bomb declares (original measurement on a real 7.13 MB ``document.xml``: one-shot ``inflateRawSync`` +210
MB RSS against +13 MB streaming with early cut).

ONE SESSION (``PhienDocZip``) shares ONE total counter for every entry read in it: this is what catches the
case where ``extract_xlsx_text`` reads ``sharedStrings.xml`` PLUS every ``sheetN.xml``: each entry can be
under the entry ceiling while the total is over the archive ceiling.

Forced deviation: the original was an ``AsyncGenerator`` (Node streams). Nothing here awaits I/O (the input
is an in-memory ``bytes`` and the whole thing runs in the extraction worker process, see
``chay_trich_xuat_tach_luong``), so this is a plain generator: a sync generator cannot be starved of the
event loop in a place that has none. ``StringDecoder`` -> ``codecs`` incremental UTF-8 decoder (a
multi-byte Vietnamese character cut at a chunk boundary is buffered, never split).
"""

from __future__ import annotations

import codecs
import zlib
from collections.abc import Iterator
from typing import Final

from pema.knowledge.ooxml_limits import (
    TI_LE_NEN_TOI_DA,
    TRAN_MIEN_KIEM_TI_LE,
    TRAN_MOT_ENTRY,
    TRAN_SO_ENTRY,
    TRAN_TONG_GIAI_NEN,
    LoiVuotTran,
    NguonChanTran,
)
from pema.shared.read_zip_entry import central_entries, du_lieu_nen_cua_entry

CHUNK_OUT: Final = 64 * 1024
"""Maximum bytes asked from the decompressor per step: bounds the memory of one step."""
CHUNK_IN: Final = 64 * 1024
"""Compressed bytes fed per step."""


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.0f} MB"


def _loi_vuot_tran_mot_entry(entry_name: str, nguon: NguonChanTran) -> LoiVuotTran:
    """Three messages for "over a ceiling because BIG/MANY", NOT the words "nghi ngờ zip bomb": that would
    accuse a file that may be perfectly valid. The entry count over 256 ALSO belongs here: a ``.docx`` with
    many images (one entry per image) reaches 257 entries with about 250 images - entirely real; the
    corpus maximum of 99 only proves the corpus has no image-heavy file, not that 257 is abnormal. The
    words "zip bomb" are ONLY for a REALLY abnormal shape (unrealistic compression ratio), see the ratio
    branch in ``doc_entry_theo_luong``."""
    return LoiVuotTran(
        "File này quá lớn để xử lý (một phần bên trong giải nén ra vượt quá giới hạn "
        f"{_format_mb(TRAN_MOT_ENTRY)} cho một phần). "
        "Hãy rút gọn nội dung hoặc tách thành nhiều file nhỏ hơn.",
        entry_name=entry_name,
        nguon=nguon,
    )


def _loi_vuot_tran_tong(entry_name: str, nguon: NguonChanTran) -> LoiVuotTran:
    return LoiVuotTran(
        "File này quá lớn để xử lý (tổng nội dung bên trong giải nén ra vượt quá giới hạn "
        f"{_format_mb(TRAN_TONG_GIAI_NEN)}). Hãy rút gọn nội dung hoặc tách thành nhiều file nhỏ hơn.",
        entry_name=entry_name,
        nguon=nguon,
    )


def _loi_vuot_tran_so_entry(so_entry: int) -> LoiVuotTran:
    return LoiVuotTran(
        f"File này có quá nhiều phần bên trong ({so_entry}, trần là {TRAN_SO_ENTRY}). "
        "Hãy gộp lại hoặc tách thành nhiều file nhỏ hơn.",
        # Read STRAIGHT from the central directory, nothing inflated -> "khai-bao".
        nguon="khai-bao",
    )


class PhienDocZip:
    """A reading session over ONE archive. Built by ``mo_phien_doc_zip``."""

    def __init__(self, buf: bytes) -> None:
        self._buf = buf
        self._entries = list(central_entries(buf))
        if len(self._entries) > TRAN_SO_ENTRY:
            raise _loi_vuot_tran_so_entry(len(self._entries))
        self._tong_byte_da_giai_nen = 0

    def danh_sach_entry(self) -> list[str]:
        """Names of every entry in the archive - the count is already checked, nothing is inflated."""
        return [e.name for e in self._entries]

    def _kiem_tran_byte(self, entry_name: str, byte_entry: int) -> None:
        if byte_entry > TRAN_MOT_ENTRY:
            raise _loi_vuot_tran_mot_entry(entry_name, "do-that")
        if self._tong_byte_da_giai_nen > TRAN_TONG_GIAI_NEN:
            raise _loi_vuot_tran_tong(entry_name, "do-that")

    def doc_entry_theo_luong(self, entry_name: str) -> Iterator[str]:
        """UTF-8 chunks of the inflated entry, counted into the session TOTAL. Raises a Vietnamese error
        as soon as any ceiling is crossed - possibly IN THE MIDDLE of the loop (after the first chunks
        were yielded); the caller (``xml_sax_scan``) must let that exception propagate, not swallow it."""
        entry = next((e for e in self._entries if e.name == entry_name), None)
        if entry is None:
            raise ValueError(f'Không tìm thấy "{entry_name}" trong file')

        # Refuse EARLY by the size DECLARED in the central directory - cheap, but NOT fully trustworthy
        # (the spec allows lying), so the loop below still counts the REAL bytes while inflating.
        if entry.uncomp_size > TRAN_MOT_ENTRY:
            raise _loi_vuot_tran_mot_entry(entry_name, "khai-bao")
        if self._tong_byte_da_giai_nen + entry.uncomp_size > TRAN_TONG_GIAI_NEN:
            raise _loi_vuot_tran_tong(entry_name, "khai-bao")

        comp_data = du_lieu_nen_cua_entry(self._buf, entry)

        if entry.method == 0:
            # STORED - not compressed, the real size IS len(comp_data)
            self._tong_byte_da_giai_nen += len(comp_data)
            self._kiem_tran_byte(entry_name, len(comp_data))
            yield comp_data.decode("utf-8", errors="replace")
            return

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        byte_entry = 0
        view = memoryview(comp_data)

        def _pieces() -> Iterator[bytes]:
            try:
                for start in range(0, len(view), CHUNK_IN):
                    piece = inflater.decompress(view[start : start + CHUNK_IN], CHUNK_OUT)
                    if piece:
                        yield piece
                    while inflater.unconsumed_tail:
                        piece = inflater.decompress(inflater.unconsumed_tail, CHUNK_OUT)
                        if piece:
                            yield piece
                rest = inflater.flush()
                if rest:
                    yield rest
            except zlib.error as err:
                raise ValueError(
                    "File bị hỏng: một phần bên trong không giải nén được. Hãy thử lưu lại file rồi nạp lại."
                ) from err

        for raw in _pieces():
            byte_entry += len(raw)
            self._tong_byte_da_giai_nen += len(raw)
            self._kiem_tran_byte(entry_name, byte_entry)

            # Exempt from the ratio check until ENOUGH OUTPUT has been read (byte_entry, NOT the compressed
            # input size) - exactly as Apache POI (ZipSecureFile.MIN_INFLATE_RATIO: no ratio until 100 KiB
            # of OUTPUT). The first version exempted by compressed size, which made this check dead code:
            # with a 32 MB entry ceiling, to keep a ratio over 500 AND be large enough not to be exempt
            # (>= 1 MB compressed) the output would have to exceed 500 MB - the one-entry ceiling would
            # have fired long before. Exempting by OUTPUT catches a real ``bom-1mb.docx`` (1.7 KB ->
            # 1 MB, ratio ~596:1) AT the 1 MB output mark.
            if byte_entry >= TRAN_MIEN_KIEM_TI_LE and byte_entry > len(comp_data) * TI_LE_NEN_TOI_DA:
                # An unrealistic compression ratio IS a really suspicious shape (real OOXML at most
                # 50.2x, degenerate generators up to 292.9x) - the words "zip bomb" stay.
                raise LoiVuotTran(
                    f'Entry "{entry_name}" có tỉ lệ nén vượt quá {TI_LE_NEN_TOI_DA}:1 - nghi ngờ zip bomb',
                    entry_name=entry_name,
                    nguon="do-that",
                )
            text = decoder.decode(raw)
            if text:
                yield text
        tail = decoder.decode(b"", final=True)
        if tail:
            yield tail


def mo_phien_doc_zip(buf: bytes) -> PhienDocZip:
    return PhienDocZip(buf)
