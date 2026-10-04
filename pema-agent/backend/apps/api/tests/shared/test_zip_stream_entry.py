# ported from: src/shared/zip-stream-entry.test.ts
"""Pure module (only zip/zlib) - no environment or database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.knowledge.ooxml_limits import LoiVuotTran
from pema.knowledge.ooxml_zip_test_helper import (
    ZipEntryInput,
    build_zip_buffer,
    build_zip_buffer_tai_su_dung_nen,
    chu_kho_nen,
)
from pema.shared.zip_stream_entry import mo_phien_doc_zip


def gom_het_chunk(gen: Iterator[str]) -> tuple[str, int]:
    text = ""
    so_chunk = 0
    for chunk in gen:
        text += chunk
        so_chunk += 1
    return text, so_chunk


def test_zip_stream_entry_dung_noi_dung_small_entry_reads_correctly_keeping_vietnamese_diacritics() -> None:
    """entry nhỏ đọc đúng nội dung, giữ nguyên tiếng Việt có dấu"""
    goc = "Chính sách bảo hành 12 tháng cho mọi sản phẩm."
    zip_bytes = build_zip_buffer([ZipEntryInput("word/document.xml", goc.encode("utf-8"))])
    text, _ = gom_het_chunk(mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("word/document.xml"))
    assert text == goc


def test_zip_stream_entry_dung_noi_dung_large_entry_is_read_as_a_stream_in_several_chunks_and_reassembles_to_the_original() -> (
    None
):
    """entry lớn đọc THEO LUỒNG (ra nhiều chunk), ráp lại đúng byte gốc"""
    # More than one decompressor step so zlib MUST emit several times - if the code silently went back to
    # reading in one shot this test would catch it.
    goc = "Báo giá tháng 8: cà phê 25.000đ, trà đá 10.000đ. " * 20_000  # ~950 KB
    zip_bytes = build_zip_buffer([ZipEntryInput("xl/sharedStrings.xml", goc.encode("utf-8"))])
    text, so_chunk = gom_het_chunk(mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("xl/sharedStrings.xml"))
    assert text == goc, "ráp các chunk lại phải ra ĐÚNG BYTE gốc, không lệch/thiếu/dư"
    assert so_chunk > 1, f"phải ra nhiều chunk (đo được {so_chunk}) - chứng minh có đọc theo luồng"


def test_zip_stream_entry_dung_noi_dung_keeps_vietnamese_characters_even_when_a_chunk_boundary_cuts_a_multibyte_character() -> (
    None
):
    """giữ đúng ký tự tiếng Việt dù ranh giới chunk cắt ngay giữa ký tự nhiều byte"""
    # The UTF-8 trap: an accented character takes 2-3 bytes, the chunk boundary almost surely falls in the
    # middle of one inside this dense block of Vietnamese diacritics. The incremental decoder must buffer
    # the partial bytes.
    goc = "Tiếng Việt có dấu: ă â đ ê ô ơ ư, á à ả ã ạ, ế ề ể ễ ệ. " * 15_000
    zip_bytes = build_zip_buffer([ZipEntryInput("word/document.xml", goc.encode("utf-8"))])
    text, _ = gom_het_chunk(mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("word/document.xml"))
    assert text == goc
    assert "�" not in text, "không được có ký tự thay thế - dấu hiệu decode UTF-8 sai"


def test_zip_stream_entry_dung_noi_dung_missing_entry_raises_a_clear_vietnamese_error() -> None:
    """entry không tồn tại ném lỗi tiếng Việt rõ ràng"""
    zip_bytes = build_zip_buffer([ZipEntryInput("word/document.xml", b"x")])
    with pytest.raises(ValueError, match=r"(?i)không tìm thấy"):
        for _ in mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("khong-ton-tai.xml"):
            pass


def test_zip_stream_entry_dung_noi_dung_danh_sach_entry_lists_the_names_without_inflating_anything() -> None:
    """danhSachEntry() liệt kê đúng tên, không cần giải nén gì"""
    zip_bytes = build_zip_buffer(
        [ZipEntryInput("word/document.xml", b"a"), ZipEntryInput("[Content_Types].xml", b"b")]
    )
    assert mo_phien_doc_zip(zip_bytes).danh_sach_entry() == ["word/document.xml", "[Content_Types].xml"]


def test_zip_stream_entry_tran_an_toan_entry_inflating_over_the_one_entry_ceiling_is_refused_without_accusing_zip_bomb() -> (
    None
):
    """entry giải nén vượt trần MỘT entry (32 MB) bị từ chối, thông báo KHÔNG buộc tội 'zip bomb'"""
    # Over the ceiling because the file is TRULY BIG is very different from over it because of a suspicious
    # SHAPE (abnormal ratio/entry count) - accusing a legitimate, simply LARGE spreadsheet of being a "zip
    # bomb" is wrong, and the operator cannot match it against the file on their disk.
    raw = b"A" * (33 * 1024 * 1024)
    zip_bytes = build_zip_buffer([ZipEntryInput("word/document.xml", raw)])
    with pytest.raises(LoiVuotTran) as excinfo:
        for _ in mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("word/document.xml"):
            pass
    err = excinfo.value
    assert "quá lớn để xử lý" in str(err).lower()
    assert "vượt quá giới hạn" in str(err).lower()
    assert "zip bomb" not in str(err).lower(), "không được buộc tội file to thật là zip bomb"
    # The size is read STRAIGHT from the central directory (nothing inflated yet) -> "khai-bao".
    assert err.entry_name == "word/document.xml"
    assert err.nguon == "khai-bao"


def test_zip_stream_entry_tran_an_toan_total_over_the_archive_ceiling_even_though_each_entry_is_under_the_entry_ceiling() -> (
    None
):
    """tổng giải nén vượt trần archive (64 MB) dù mỗi entry đều dưới trần entry"""
    # HARD-TO-COMPRESS text (not a repeated single byte) - repeating one byte compresses beyond 1000:1 and
    # the ratio check would catch it first, hiding the total check under test. ``..._tai_su_dung_nen``:
    # compress ONCE, reuse for 3 names.
    moi_entry = chu_kho_nen(25 * 1024 * 1024).encode("utf-8")
    zip_bytes = build_zip_buffer_tai_su_dung_nen(moi_entry, ["a.xml", "b.xml", "c.xml"])
    phien = mo_phien_doc_zip(zip_bytes)
    # The first 2 entries (50 MB) are under both the entry AND the total ceiling - must read through
    for ten in ("a.xml", "b.xml"):
        for _ in phien.doc_entry_theo_luong(ten):
            pass
    # The 3rd pushes the total to 75 MB - over the archive ceiling although it alone (25 MB) is under the
    # entry ceiling (32 MB). Same "do not accuse of zip bomb" reason as the one-entry ceiling above.
    with pytest.raises(LoiVuotTran) as excinfo:
        for _ in phien.doc_entry_theo_luong("c.xml"):
            pass
    err = excinfo.value
    assert "quá lớn để xử lý" in str(err).lower()
    assert "vượt quá giới hạn" in str(err).lower()
    assert "zip bomb" not in str(err).lower(), "không được buộc tội file to thật là zip bomb"
    # Raised on the EARLY branch (real total of a.xml+b.xml PLUS the DECLARED size of c.xml, nothing of
    # c.xml inflated) -> "khai-bao", although the 2 earlier entries were really read.
    assert err.entry_name == "c.xml"
    assert err.nguon == "khai-bao"


def test_zip_stream_entry_tran_an_toan_ratio_over_500_to_1_is_refused_early_same_class_of_bomb_as_the_real_bom_1mb_docx() -> (
    None
):
    """tỉ lệ nén vượt 500:1 bị từ chối SỚM (trước khi chạm trần entry) - cùng LỚP bom với bom-1mb.docx thật"""
    # Content repeating ONE character, inflating to 1 MB (far under the 32 MB entry ceiling) - the ratio of
    # this very fixture was MEASURED in the original: 1 MB of "x" -> 1,033 bytes, ratio 1015:1. That differs
    # from the real bom-1mb.docx of the research (1.7 KB -> 1 MB, ~596:1) but it is the SAME class of bomb
    # (an unrealistic compression ratio) and both are far beyond the 500:1 ceiling. The ratio check must be
    # the FIRST path that blocks it - measured by the message saying "tỉ lệ nén", not "vượt quá giới hạn"
    # (the message of the entry/total ceiling).
    raw = "x" * (1024 * 1024)  # 1 MB, compresses extremely well
    zip_bytes = build_zip_buffer([ZipEntryInput("word/document.xml", raw.encode("utf-8"))])
    with pytest.raises(LoiVuotTran) as excinfo:
        for _ in mo_phien_doc_zip(zip_bytes).doc_entry_theo_luong("word/document.xml"):
            pass
    err = excinfo.value
    assert "tỉ lệ nén vượt quá 500:1" in str(err).lower()
    # An unrealistic compression ratio IS a really suspicious shape - the words "zip bomb" STAY here
    # (positive confirmation, not only the negative checks of the 2 tests above).
    assert "zip bomb" in str(err).lower()
    # Raised in the MIDDLE of the streaming loop, comparing the byte count MEASURED while inflating (not the
    # size declared in the central directory) -> "do-that".
    assert err.entry_name == "word/document.xml"
    assert err.nguon == "do-that"


def test_zip_stream_entry_tran_an_toan_entry_count_over_the_256_ceiling_is_refused_without_inflating_anything_and_without_accusing_zip_bomb() -> (
    None
):
    """số entry vượt trần 256 bị từ chối, không cần giải nén entry nào, KHÔNG buộc tội 'zip bomb'"""
    # Corrected after review: a .docx with many images (one entry per image) reaches 257 entries with about
    # 250 images - entirely valid. The corpus maximum of 99 only proves the corpus has no image-heavy file,
    # not that 257 is abnormal - the case must not be accused of being a "zip bomb".
    entries = [ZipEntryInput(f"f{i}.xml", b"x") for i in range(257)]
    zip_bytes = build_zip_buffer(entries)
    with pytest.raises(LoiVuotTran) as excinfo:
        mo_phien_doc_zip(zip_bytes)
    err = excinfo.value
    assert "quá nhiều phần bên trong" in str(err).lower()
    assert "257" in str(err)
    assert "zip bomb" not in str(err).lower(), "không được buộc tội 257 entry là zip bomb"
    # Read STRAIGHT from the central directory, nothing inflated -> "khai-bao". Not tied to ONE entry.
    assert err.entry_name is None
    assert err.nguon == "khai-bao"


def test_zip_stream_entry_tran_an_toan_broken_zip_raises_a_vietnamese_error_like_read_zip_entry() -> None:
    """zip hỏng (không phải zip) ném lỗi tiếng Việt như read-zip-entry.ts"""
    with pytest.raises(ValueError, match=r"(?i)không phải file zip"):
        mo_phien_doc_zip(b"khong phai zip")
