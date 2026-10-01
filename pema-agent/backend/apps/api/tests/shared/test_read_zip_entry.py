# ported from: src/shared/read-zip-entry.test.ts
"""``read_zip_entry`` / ``read_zip_entry_text`` are PURE modules (no environment, no database) - the zip is
hand built with ``zlib`` instead of depending on a document renderer, so this file pulls in no other import.

Minimal zip structure: local file header (30 bytes) + name + compressed data, then the central directory
header (46 bytes) + name, then End Of Central Directory (22 bytes). The offset of each field must match
EXACTLY what ``read_zip_entry`` reads - one field off and ``central_entries`` / ``read_zip_entry`` read wrong
silently.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from pema.shared.read_zip_entry import read_zip_entry


def build_zip(entry_name: str, data: bytes) -> bytes:
    compressor = zlib.compressobj(-1, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(data) + compressor.flush()
    name_buf = entry_name.encode("utf-8")

    local_header = bytearray(30)
    struct.pack_into("<I", local_header, 0, 0x04034B50)  # local file header signature
    struct.pack_into("<H", local_header, 8, 8)  # method = deflate
    struct.pack_into("<I", local_header, 18, len(compressed))  # compressed size
    struct.pack_into("<I", local_header, 22, len(data))  # uncompressed size
    struct.pack_into("<H", local_header, 26, len(name_buf))  # name length
    struct.pack_into("<H", local_header, 28, 0)  # extra length
    local_section = bytes(local_header) + name_buf + compressed

    central_header = bytearray(46)
    struct.pack_into("<I", central_header, 0, 0x02014B50)  # central dir signature
    struct.pack_into("<H", central_header, 10, 8)  # method = deflate
    struct.pack_into("<I", central_header, 20, len(compressed))
    struct.pack_into("<I", central_header, 24, len(data))
    struct.pack_into("<H", central_header, 28, len(name_buf))
    struct.pack_into("<I", central_header, 42, 0)  # local header offset (the only entry, at the start)
    central_section = bytes(central_header) + name_buf

    eocd = bytearray(22)
    struct.pack_into("<I", eocd, 0, 0x06054B50)  # EOCD signature
    struct.pack_into("<H", eocd, 10, 1)  # total number of entries
    struct.pack_into("<I", eocd, 12, len(central_section))  # size of the central directory
    struct.pack_into("<I", eocd, 16, len(local_section))  # offset of the central directory

    return local_section + central_section + bytes(eocd)


def test_read_zip_entry_normal_compressed_entry_still_reads_correctly_under_the_ceiling() -> None:
    """entry nén bình thường vẫn đọc đúng khi dưới trần"""
    goc = ("Bảo hành 12 tháng cho mọi sản phẩm." * 50).encode("utf-8")
    zip_bytes = build_zip("noi_dung.txt", goc)

    assert read_zip_entry(zip_bytes, "noi_dung.txt", 1_000_000) == goc


def test_read_zip_entry_entry_inflating_over_the_ceiling_raises_a_readable_vietnamese_error() -> None:
    """entry giải nén vượt trần ném lỗi tiếng Việt đọc được, không phải lỗi zlib thô"""
    # Repeated data compresses extremely well (high deflate ratio) - enough to inflate to much more than the
    # small ceiling given to the test, no real multi-GB bomb needed.
    goc = b"A" * 200_000  # 200 KB of 'A'
    zip_bytes = build_zip("bomb.bin", goc)

    with pytest.raises(ValueError, match="vượt quá giới hạn an toàn") as excinfo:
        read_zip_entry(zip_bytes, "bomb.bin", 1_000)  # 1000 byte ceiling, far below 200_000
    assert "zip bomb" in str(excinfo.value).lower()
    assert "zlib" not in str(excinfo.value).lower(), "không được lộ nguyên văn lỗi thư viện zlib"


def test_read_zip_entry_missing_entry_still_returns_none_unaffected_by_the_new_ceiling_parameter() -> None:
    """entry không tồn tại vẫn trả null như cũ, không bị ảnh hưởng bởi tham số trần mới"""
    zip_bytes = build_zip("co-that.txt", b"x")
    assert read_zip_entry(zip_bytes, "khong-ton-tai.txt") is None
