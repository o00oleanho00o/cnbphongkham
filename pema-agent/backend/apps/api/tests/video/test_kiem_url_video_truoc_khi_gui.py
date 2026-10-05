# ported from: src/video/kiem-url-video-truoc-khi-gui.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The probe is the replacement for the assumption "a broken URL makes sendVideo raise": that assumption was
WRONG and made the bot report "sent" for a dead video.

The two pure functions are tested straight. The network part only tests the branches that BLOCK BEFORE
OPENING A CONNECTION, since every internal address is blocked by the guard layer itself: a real server cannot
be set up to try the rest. ``localhost`` is resolved by an injected resolver so no real DNS runs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from pema.video.kiem_url_video_truoc_khi_gui import (
    KetQuaDoLoi,
    KetQuaDoOk,
    do_co_that,
    kiem_url_video_con_song,
    la_kieu_video,
    quyet_dinh_tu_header,
)

# ------------------------------------------------------------------ doCoThat - lấy cỡ THẬT của cả file


def test_do_co_that_206_thi_doc_duoi_content_range_khong_doc_content_length() -> None:
    """206 thì đọc đuôi content-range, KHÔNG đọc content-length"""
    # The main trap: with a 206, ``content-length`` is the length of the PART just asked for (1 byte), not
    # the file size. Reading it wrongly makes every video "1 byte" and the size ceiling meaningless.
    assert do_co_that(206, "bytes 0-0/6667679", 1) == 6_667_679


def test_do_co_that_206_voi_khoang_trang_thua_van_doc_duoc() -> None:
    """206 với khoảng trắng thừa vẫn đọc được"""
    assert do_co_that(206, "bytes 0-0/1024  ", 1) == 1024


def test_do_co_that_206_ma_content_range_hong_hoac_thieu_thi_null_khong_lui_ve_content_length() -> None:
    """206 mà content-range hỏng hoặc thiếu thì trả null, KHÔNG lùi về content-length"""
    # Falling back to ``content-length`` here records a size of 1 byte: wrong is worse than unknown, since
    # the size ceiling would let everything through.
    assert do_co_that(206, None, 1) is None
    assert do_co_that(206, "bytes */*", 1) is None
    assert do_co_that(206, "rac", 1) is None


def test_do_co_that_200_thi_content_length_chinh_la_co_day_du() -> None:
    """200 thì content-length CHÍNH LÀ cỡ đầy đủ"""
    # A server that ignores ``Range`` returns the whole file with its real size.
    assert do_co_that(200, None, 5_000_000) == 5_000_000


def test_do_co_that_khong_co_gi_dang_tin_thi_null_tha_khong_biet_con_hon_biet_sai() -> None:
    """không có gì đáng tin thì null - thà không biết còn hơn biết sai"""
    assert do_co_that(200, None, math.nan) is None
    assert do_co_that(200, None, 0) is None


# ------------------------------------------------------------------ laKieuVideo


def test_la_kieu_video_nhan_video_sao() -> None:
    """nhận video/*"""
    for k in ["video/mp4", "video/webm", "VIDEO/MP4", "video/mp4; charset=binary", " video/mp4 "]:
        assert la_kieu_video(k) is True, k


def test_la_kieu_video_nhan_application_octet_stream_do_la_khong_biet() -> None:
    """nhận application/octet-stream - đó là 'không biết', không phải 'biết là HTML'"""
    assert la_kieu_video("application/octet-stream") is True


def test_la_kieu_video_tu_choi_text_html_trang_link_het_han_hoac_trang_chan_bot() -> None:
    """TỪ CHỐI text/html - trang 'link hết hạn' hoặc trang chặn bot"""
    # This case does not raise and ``bytes > 0``, so every safety net based on exceptions lets it through.
    for k in ["text/html", "text/html; charset=utf-8", "text/plain", "application/json", ""]:
        assert la_kieu_video(k) is False, k


# ------------------------------------------------------------------ quyetDinhTuHeader - phần QUYẾT ĐỊNH
# Measured before this group of cases existed: dropping the ``la_kieu_video`` gate or the status gate kept
# the WHOLE suite green, because every network case is blocked by ``open_guarded_request`` before a
# connection opens, so none reaches the decision part. ``la_kieu_video`` is proven right, but "the probe
# CALLS it" was proven by nobody, and that second one is exactly the bug the review round went to fix.


def test_quyet_dinh_tu_header_206_video_mp4_la_qua_va_doc_co_that_tu_content_range() -> None:
    """206 + video/mp4 là QUA, và đọc cỡ thật từ content-range"""
    r = quyet_dinh_tu_header(206, "video/mp4", "bytes 0-0/6667679", 1)
    assert isinstance(r, KetQuaDoOk)
    assert r.so_byte == 6_667_679


def test_quyet_dinh_tu_header_200_video_mp4_la_qua() -> None:
    """200 + video/mp4 là QUA"""
    assert quyet_dinh_tu_header(200, "video/mp4", None, 5_000_000).ok is True


def test_quyet_dinh_tu_header_403_la_truot_sendvideo_khong_nem_voi_403() -> None:
    """403 là TRƯỢT - đây là ca đã trả giá, sendVideo KHÔNG ném với 403"""
    r = quyet_dinh_tu_header(403, "video/mp4", None, 0)
    assert isinstance(r, KetQuaDoLoi)
    assert "403" in r.ly


def test_quyet_dinh_tu_header_moi_status_ngoai_2xx_deu_truot() -> None:
    """mọi status ngoài 2xx đều TRƯỢT"""
    for st in [0, 400, 404, 429, 500, 503]:
        assert quyet_dinh_tu_header(st, "video/mp4", None, 1).ok is False, f"status {st}"


def test_quyet_dinh_tu_header_200_text_html_la_truot_trang_link_het_han() -> None:
    """200 + text/html là TRƯỢT - trang 'link hết hạn' không ném và bytes > 0"""
    # This case slips past EVERY safety net based on exceptions. Without a block here the HTML content is
    # written to ``<name>.mp4`` and sent as a video.
    r = quyet_dinh_tu_header(200, "text/html; charset=utf-8", None, 2048)
    assert isinstance(r, KetQuaDoLoi)
    assert "không phải video" in r.ly.lower()


def test_quyet_dinh_tu_header_kieu_noi_dung_trong_cung_truot() -> None:
    """kiểu nội dung TRỐNG cũng TRƯỢT"""
    assert quyet_dinh_tu_header(200, "", None, 100).ok is False


def test_quyet_dinh_tu_header_octet_stream_qua_khong_biet_khac_biet_la_html() -> None:
    """application/octet-stream QUA - 'không biết' khác 'biết là HTML'"""
    assert quyet_dinh_tu_header(200, "application/octet-stream", None, 100).ok is True


# ------------------------------------------------------------------ mang theo URL đã xác thực


def test_quyet_dinh_mang_theo_url_tra_ve_url_cuoi_de_caller_tai_dung_cho_da_kiem() -> None:
    """trả về URL CUỐI để caller tải đúng chỗ đã kiểm"""
    # The caller downloads with this URL, not the original string: the probe already followed every
    # redirect and checked the address at EACH hop, so this is the only thing that was verified.
    r = quyet_dinh_tu_header(206, "video/mp4", "bytes 0-0/100", 1, "https://cdn.test/cuoi.mp4")
    assert isinstance(r, KetQuaDoOk)
    assert r.url_cuoi == "https://cdn.test/cuoi.mp4"


# ------------------------------------------------------------------ kiemUrlVideoConSong - lớp chặn nội bộ
# ``videoUrl`` is a string returned by TikWM/yt-dlp. Without this step it goes straight into ``sendVideo``,
# and zca-js follows ``location`` RECURSIVELY, without counting hops, without checking the address.


async def _resolver_noi_bo(_hostname: str) -> Sequence[str]:
    """``localhost`` resolves to loopback without touching a real DNS server."""
    return ["127.0.0.1"]


@pytest.mark.parametrize(
    ("url", "vi"),
    [
        ("http://127.0.0.1:3900/x.mp4", "dashboard của chính bot"),
        ("http://localhost:6379/x.mp4", "dịch vụ trên cùng máy"),
        ("http://169.254.169.254/latest/meta-data/", "metadata đám mây"),
        ("http://192.168.1.1/x.mp4", "mạng LAN"),
        ("http://[::1]:8080/x.mp4", "loopback IPv6"),
    ],
)
async def test_kiem_url_video_con_song_thua_huong_lop_chan_dia_chi_noi_bo(url: str, vi: str) -> None:
    """chặn <vì sao>"""
    r = await kiem_url_video_con_song(url, resolver=_resolver_noi_bo)
    assert isinstance(r, KetQuaDoLoi)
    assert "nội bộ" in r.ly.lower(), f"phải nói rõ lý do: {url}"


async def test_kiem_url_video_con_song_chi_nhan_http_https() -> None:
    """chỉ nhận http/https"""
    r = await kiem_url_video_con_song("file:///C:/Windows/win.ini")
    assert isinstance(r, KetQuaDoLoi)
    assert "http" in r.ly.lower()


async def test_kiem_url_video_con_song_url_rac_tra_loi_ro_rang_khong_nem() -> None:
    """URL rác trả lỗi rõ ràng, KHÔNG ném"""
    r = await kiem_url_video_con_song("khong-phai-url")
    assert isinstance(r, KetQuaDoLoi)
    assert "không hợp lệ" in r.ly.lower()
