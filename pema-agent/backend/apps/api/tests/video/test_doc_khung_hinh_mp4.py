# ported from: src/video/doc-khung-hinh-mp4.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The MP4 frame reader. It is what cures a REAL CRASH case: a 1280x720 landscape Facebook video declared as
576x1024 portrait, and the Zalo phone app built the play surface from that number and died. No source can
declare correctly: TikWM returns no size at all, yt-dlp's chosen format carries none, and the ``formats``
array declares double the real stream.

The offsets in ``tkhd`` were MEASURED on a file and checked against ffprobe, not counted by head: my first
version was off by 4 bytes and read a height of 16384 (the last element of the transform matrix).
"""

from __future__ import annotations

import struct

from pema.video.doc_khung_hinh_mp4 import KhungHinh, doc_khung_hinh_mp4, doc_thong_tin_mp4


def _tkhd(width: float, height: float, ver: int = 0, ma_tran: tuple[int, int] = (0x00010000, 0)) -> bytes:
    """Build a ``tkhd`` box with the given version, frame size and matrix."""
    dich = 12 if ver == 1 else 0
    co = 92 + dich
    b = bytearray(co)
    struct.pack_into(">I", b, 0, co)
    b[4:8] = b"tkhd"
    than = 8
    b[than] = ver
    struct.pack_into(">i", b, than + 40 + dich, ma_tran[0])
    struct.pack_into(">i", b, than + 44 + dich, ma_tran[1])
    struct.pack_into(">I", b, than + 76 + dich, round(width * 65536))
    struct.pack_into(">I", b, than + 80 + dich, round(height * 65536))
    return bytes(b)


def _mvhd(timescale: int, duration: int, ver: int = 0) -> bytes:
    """Build an ``mvhd`` box with the given timescale + duration (v0 or v1)."""
    # v0 body: version(1)+flags(3)+ctime(4)+mtime(4)+timescale(4)+duration(4) = 20
    # v1 body: version(1)+flags(3)+ctime(8)+mtime(8)+timescale(4)+duration(8) = 32
    than = 32 if ver == 1 else 20
    b = bytearray(8 + than)
    struct.pack_into(">I", b, 0, 8 + than)
    b[4:8] = b"mvhd"
    b[8] = ver
    if ver == 1:
        struct.pack_into(">I", b, 8 + 20, timescale)
        struct.pack_into(">Q", b, 8 + 24, duration)
    else:
        struct.pack_into(">I", b, 8 + 12, timescale)
        struct.pack_into(">I", b, 8 + 16, duration)
    return bytes(b)


def _hop(ten: str, *con: bytes) -> bytes:
    """Wrap child boxes in a parent box of the given name."""
    than = b"".join(con)
    return struct.pack(">I", 8 + len(than)) + ten.encode("latin1") + than


FTYP = _hop("ftyp", b"isomiso2")


# ------------------------------------------------------------------ đọc khung hình từ MP4


def test_doc_khung_hinh_tu_mp4_doc_dung_video_ngang() -> None:
    """đọc đúng video NGANG"""
    b = FTYP + _hop("moov", _hop("trak", _tkhd(1002, 576)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(1002, 576)


def test_doc_khung_hinh_tu_mp4_doc_dung_video_doc() -> None:
    """đọc đúng video DỌC"""
    b = FTYP + _hop("moov", _hop("trak", _tkhd(576, 1024)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(576, 1024)


def test_doc_khung_hinh_tu_mp4_bo_qua_track_am_thanh_khai_0x0() -> None:
    """BỎ QUA track âm thanh (khai 0x0) rồi đi tiếp tới track hình"""
    # Real case: the FIRST ``tkhd`` in a TikTok file is the audio track. My first version read exactly that
    # track and returned a meaningless size.
    b = FTYP + _hop("moov", _hop("trak", _tkhd(0, 0)), _hop("trak", _tkhd(1280, 720)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(1280, 720)


def test_doc_khung_hinh_tu_mp4_hieu_tkhd_version_1() -> None:
    """hiểu tkhd version 1 (mốc thời gian 8 byte)"""
    b = FTYP + _hop("moov", _hop("trak", _tkhd(1920, 1080, ver=1)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(1920, 1080)


def test_doc_khung_hinh_tu_mp4_doi_chieu_khi_ma_tran_bao_xoay_90_do() -> None:
    """ĐỔI CHIỀU khi ma trận báo xoay 90 độ"""
    # A video shot portrait on a phone is often stored landscape with a rotation flag. Not handling it
    # declares the wrong orientation again: exactly the class of error that just crashed the phone.
    b = FTYP + _hop("moov", _hop("trak", _tkhd(1280, 720, ma_tran=(0, 0x00010000))))
    assert doc_khung_hinh_mp4(b) == KhungHinh(720, 1280)


def test_doc_khung_hinh_tu_mp4_doc_duoc_ca_khi_moov_dai_hon_phan_buffer_dang_co() -> None:
    """đọc được cả khi `moov` dài hơn phần buffer đang có"""
    # We only download the head of the file, and ``moov`` is usually bigger than that. The first version
    # gave up here and returned ``None`` for every real video.
    day = bytearray(FTYP + _hop("moov", _hop("trak", _tkhd(800, 600))))
    struct.pack_into(">I", day, len(FTYP), 9_000_000)  # ``moov`` declares itself bigger than the buffer
    assert doc_khung_hinh_mp4(bytes(day)) == KhungHinh(800, 600)


# ------------------------------------------------------------------ byte của người lạ


def test_byte_cua_nguoi_la_khong_phai_mp4_thi_tra_none_khong_nem() -> None:
    """không phải MP4 thì trả null, KHÔNG ném"""
    assert doc_khung_hinh_mp4(b"day khong phai video") is None


def test_byte_cua_nguoi_la_buffer_rong_hoac_qua_ngan() -> None:
    """buffer rỗng, hoặc quá ngắn"""
    assert doc_khung_hinh_mp4(b"") is None
    assert doc_khung_hinh_mp4(bytes(4)) is None


def test_byte_cua_nguoi_la_hop_khai_co_0_hoac_am_thi_dung_khong_lap_vo_han() -> None:
    """hộp khai cỡ 0 hoặc âm thì dừng, không lặp vô hạn"""
    b = bytearray(64)
    struct.pack_into(">I", b, 0, 0)
    b[4:8] = b"moov"
    assert doc_khung_hinh_mp4(bytes(b)) is None

    c = bytearray(64)
    struct.pack_into(">I", c, 0, 3)  # smaller than the box head itself
    c[4:8] = b"moov"
    assert doc_khung_hinh_mp4(bytes(c)) is None


def test_byte_cua_nguoi_la_hop_long_nhau_rat_sau_thi_dung_theo_tran_do_sau() -> None:
    """hộp lồng nhau rất sâu thì dừng theo trần độ sâu"""
    b = _hop("trak", _tkhd(100, 100))
    for _ in range(20):
        b = _hop("moov", b)
    # Does not assert whether it can be read: only that it RETURNS, it does not hang.
    r = doc_khung_hinh_mp4(FTYP + b)
    assert r is None or (r.width > 0 and r.height > 0)


def test_byte_cua_nguoi_la_bo_cuoc_khi_phai_loi_qua_qua_nhieu_hop_danh_doi_co_y() -> None:
    """BỎ CUỘC khi phải lội qua quá nhiều hộp - đây là đánh đổi cố ý"""
    # A file stuffed with thousands of empty boxes before ``moov`` is a shape that does not exist for real;
    # the box ceiling stops it. In return: a valid file that puts ``moov`` after more than 300 boxes is also
    # dropped, acceptable since real files put ``moov`` right at the start.
    rong = [_hop("free") for _ in range(400)]
    b = FTYP + b"".join(rong) + _hop("moov", _hop("trak", _tkhd(100, 100)))
    assert doc_khung_hinh_mp4(b) is None, "trần số hộp phải chặn, không đi tiếp mãi"


def test_byte_cua_nguoi_la_vai_chuc_hop_rong_thi_van_doc_duoc_binh_thuong() -> None:
    """nhưng vài chục hộp rỗng thì vẫn đọc được bình thường"""
    rong = [_hop("free") for _ in range(50)]
    b = FTYP + b"".join(rong) + _hop("moov", _hop("trak", _tkhd(100, 200)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(100, 200)


def test_byte_cua_nguoi_la_tkhd_khai_kich_thuoc_0_o_moi_track_thi_tra_none() -> None:
    """tkhd khai kích thước 0 ở mọi track thì trả null"""
    b = FTYP + _hop("moov", _hop("trak", _tkhd(0, 0)))
    assert doc_khung_hinh_mp4(b) is None


# ------------------------------------------------------------------ đọc THỜI LƯỢNG từ mvhd


def test_doc_thoi_luong_v0_duration_chia_timescale_ra_mili_giay_va_lay_khung_hinh_cung_luot() -> None:
    """v0: duration/timescale ra mili giây, VÀ lấy khung hình cùng một lượt"""
    # 3000/1000 = 3s = 3000ms. mvhd (child of moov) + tkhd (inside trak) in the same file.
    b = FTYP + _hop("moov", _mvhd(1000, 3000), _hop("trak", _tkhd(720, 1280)))
    r = doc_thong_tin_mp4(b)
    assert r.thoi_luong_ms == 3000
    assert r.khung == KhungHinh(720, 1280), "một lượt lấy cả hai"


def test_doc_thoi_luong_v1_moc_va_duration_8_byte_doc_dung() -> None:
    """v1 (mốc + duration 8 byte): đọc đúng"""
    b = FTYP + _hop("moov", _mvhd(600, 90_000, 1))  # 90000/600 = 150s
    assert doc_thong_tin_mp4(b).thoi_luong_ms == 150_000


def test_doc_thoi_luong_khop_so_do_tren_file_that_offset_mvhd_reel_ig_67196ms() -> None:
    """khớp số đo trên file THẬT (offset mvhd) - reel IG 67,196ms"""
    # Offset read from a real IG file and checked against ffprobe (67.195692s -> 67196ms).
    b = FTYP + _hop("moov", _mvhd(1000, 67_196))
    assert doc_thong_tin_mp4(b).thoi_luong_ms == 67_196


def test_doc_thoi_luong_khong_co_mvhd_thi_thoi_luong_null_van_doc_duoc_khung() -> None:
    """KHÔNG có mvhd -> thoiLuongMs null, vẫn đọc được khung (ca TikTok/FB cũ)"""
    b = FTYP + _hop("moov", _hop("trak", _tkhd(576, 1024)))
    r = doc_thong_tin_mp4(b)
    assert r.thoi_luong_ms is None
    assert r.khung == KhungHinh(576, 1024)


def test_doc_thoi_luong_timescale_0_thi_null_khong_chia_cho_0() -> None:
    """timescale = 0 -> null, KHÔNG chia cho 0"""
    b = FTYP + _hop("moov", _mvhd(0, 3000))
    assert doc_thong_tin_mp4(b).thoi_luong_ms is None


def test_doc_thoi_luong_duration_sentinel_0xffffffff_khong_biet_thi_null_khong_ra_so_khong_lo() -> None:
    """duration sentinel 0xFFFFFFFF ('không biết') -> null, không ra số khổng lồ"""
    # 0xFFFFFFFF/1000 ~ 49.7 days, over the ceiling -> null instead of sending Zalo a junk label.
    b = FTYP + _hop("moov", _mvhd(1000, 0xFFFFFFFF))
    assert doc_thong_tin_mp4(b).thoi_luong_ms is None


def test_doc_thoi_luong_doc_khung_hinh_mp4_van_tra_chi_khung_hinh_chu_ky_cu_nguyen_ven() -> None:
    """docKhungHinhMp4 vẫn trả CHỈ khung hình - chữ ký cũ nguyên vẹn"""
    b = FTYP + _hop("moov", _mvhd(1000, 5000), _hop("trak", _tkhd(100, 200)))
    assert doc_khung_hinh_mp4(b) == KhungHinh(100, 200)
