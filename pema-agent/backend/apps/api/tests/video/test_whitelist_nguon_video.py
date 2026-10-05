# ported from: src/video/whitelist-nguon-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import pytest

from pema.video.whitelist_nguon_video import (
    KetQuaWhitelistOk,
    kiem_nguon_video,
    tim_url_trong_chu,
)

# ------------------------------------------------------------------ kiemNguonVideo - nhận đúng nguồn hợp lệ

HOP_LE: list[tuple[str, str]] = [
    ("https://www.tiktok.com/@ai/video/123", "tiktok"),
    ("https://vt.tiktok.com/ZSV5bEotV/", "tiktok"),
    ("https://vm.tiktok.com/ABC/", "tiktok"),
    ("https://tiktok.com/@ai/video/123", "tiktok"),
    ("https://www.facebook.com/watch/?v=123", "facebook"),
    ("https://fb.watch/abcdef/", "facebook"),
    ("https://m.facebook.com/reel/123", "facebook"),
    ("https://web.facebook.com/reel/123", "facebook"),
    # Instagram: reel/post/share, both www and m. The app link comes with ?igsh=...
    ("https://www.instagram.com/reel/CigMSGeD4Hd/", "instagram"),
    ("https://www.instagram.com/reel/CigMSGeD4Hd/?igsh=abc123", "instagram"),
    ("https://instagram.com/p/ABC123/", "instagram"),
    ("https://www.instagram.com/share/reel/xyz/", "instagram"),
    ("https://m.instagram.com/reel/abc/", "instagram"),
]


@pytest.mark.parametrize(("url", "nen_tang"), HOP_LE)
def test_kiem_nguon_video_nhan_dung_nguon_hop_le(url: str, nen_tang: str) -> None:
    """nhận <url>"""
    k = kiem_nguon_video(url)
    assert k.ok is True, f"phải nhận: {k}"
    assert k.nen_tang == nen_tang


# ------------------------------------------------------------------ kiemNguonVideo - CHẶN đường tấn công
# This is the SSRF layer. The bot reads messages from STRANGERS, so every case below is a message someone
# could write to make the VPS send a request for them.

PHAI_CHAN: list[tuple[str, str]] = [
    ("http://127.0.0.1:3900/api/tuning", "chính dashboard của bot"),
    ("http://localhost:6379", "Redis trên cùng máy"),
    ("http://169.254.169.254/latest/meta-data/", "endpoint metadata đám mây"),
    ("http://[::1]:8080/", "loopback IPv6"),
    ("file:///etc/passwd", "đọc file trên máy"),
    ("file:///C:/Windows/win.ini", "đọc file trên Windows"),
    ("ftp://tiktok.com/x", "scheme lạ dù host đúng"),
    ("https://tiktok.com.ke-tan-cong.net/x", "tên miền giả dạng bằng tiền tố"),
    ("https://faketiktok.com/x", "tên miền chứa chữ tiktok"),
    ("https://instagram.com.ke-tan-cong.net/reel/x", "instagram giả dạng bằng tiền tố"),
    ("https://fakeinstagram.com/reel/x", "tên miền chứa chữ instagram"),
    ("https://www.threads.com/@a/post/x", "Threads - yt-dlp không hỗ trợ, phải chặn"),
    ("https://ke-tan-cong.net/?next=https://tiktok.com/", "host thật nằm ở query"),
    ("https://youtube.com/watch?v=1", "nền tảng ngoài phạm vi"),
    ("https://evil.com/tiktok.com/video", "tên miền đúng nằm ở đường dẫn"),
]


@pytest.mark.parametrize(("url", "vi_sao"), PHAI_CHAN, ids=[c[0] for c in PHAI_CHAN])
def test_kiem_nguon_video_chan_duong_tan_cong(url: str, vi_sao: str) -> None:
    """chặn <url> (<vì sao>)"""
    k = kiem_nguon_video(url)
    assert k.ok is False, f"PHẢI CHẶN nhưng lại nhận: {url} ({vi_sao})"


def test_kiem_nguon_video_chuoi_rong_va_rac_deu_bi_chan() -> None:
    """chuỗi rỗng và rác đều bị chặn"""
    for x in ["", "   ", "không phải url", "javascript:alert(1)"]:
        assert kiem_nguon_video(x).ok is False, f"phải chặn: {x!r}"


def test_kiem_nguon_video_chan_userinfo_host_that_nam_sau_dau_a() -> None:
    """CHẶN userinfo - host thật nằm sau dấu @"""
    # ``tiktok.com`` here is the USERNAME, the real host is 127.0.0.1.
    k = kiem_nguon_video("http://tiktok.com:pass@127.0.0.1/x")
    assert k.ok is False, "PHẢI CHẶN: host thật là 127.0.0.1"


def test_kiem_nguon_video_chan_ca_khi_userinfo_tro_toi_host_hop_le() -> None:
    """chặn cả khi userinfo trỏ tới host HỢP LỆ - luật là chặn userinfo, không xét đích"""
    assert kiem_nguon_video("http://ai:do@www.tiktok.com/@a/video/1").ok is False


def test_kiem_nguon_video_host_viet_hoa_van_nhan_ra() -> None:
    """host viết HOA vẫn nhận ra - đừng để đổi chữ hoa là lách được"""
    assert kiem_nguon_video("https://WWW.TIKTOK.COM/@a/video/1").ok is True


def test_kiem_nguon_video_dau_cham_thua_cuoi_host_van_nhan_ra() -> None:
    """dấu chấm thừa cuối host vẫn nhận ra - `tiktok.com.` là cùng một host"""
    assert kiem_nguon_video("https://www.tiktok.com./@a/video/1").ok is True


# ------------------------------------------------------------------ URL trả về phải ĐÃ CHUẨN HÓA
# Real bug: this function checks the host with the WHATWG parser, while yt-dlp re-parses with Python's
# ``urllib``. The two do not agree about ``\``. Returning the RAW string means the whitelist guards one
# address while yt-dlp goes to another. A server was set up at 127.0.0.1:8791 and the real yt-dlp run: the
# internal server RECEIVED the request. Not a deduction.

BS = chr(92)


def test_url_tra_ve_da_chuan_hoa_dau_backslash_trong_host() -> None:
    """dấu \\ trong host: Node đọc ra tiktok.com nhưng Python đọc ra 127.0.0.1"""
    doc = f"http://tiktok.com{BS}@127.0.0.1:8791/api/tuning"
    k = kiem_nguon_video(doc)

    # The WHATWG parser LETS THIS THROUGH: that is exactly the problem, and why the returned ``url`` must be
    # the normalised form and not the input.
    assert isinstance(k, KetQuaWhitelistOk), "Node coi đây là tiktok.com - ca này vốn lọt whitelist"
    assert BS not in k.url, f"url trả về CÒN dấu \\ - Python sẽ đọc ra 127.0.0.1: {k.url}"
    assert k.url != doc, "trả nguyên chuỗi vào là mở lại lỗ hổng"
    assert k.url == "http://tiktok.com/@127.0.0.1:8791/api/tuning"


def test_url_tra_ve_url_hop_le_binh_thuong_van_dung_duoc_khong_bi_bop_meo() -> None:
    """url hợp lệ bình thường vẫn trả về dùng được, không bị bóp méo"""
    k = kiem_nguon_video("https://vt.tiktok.com/ZSV5bEotV/")
    assert isinstance(k, KetQuaWhitelistOk)
    assert k.url == "https://vt.tiktok.com/ZSV5bEotV/"


def test_url_tra_ve_moi_ca_hop_le_tra_url_phan_tich_lai_ra_dung_host_ban_dau() -> None:
    """mọi ca hợp lệ đều trả url PHÂN TÍCH LẠI ra đúng host ban đầu"""
    # Final lock: however it is normalised, the host of the returned url must still be in the allow-list.
    # Otherwise normalising becomes a new detour.
    for u in [
        "https://www.tiktok.com/@ai/video/123",
        "https://vt.tiktok.com/ABC/",
        "https://www.facebook.com/watch/?v=1",
        "https://fb.watch/abc/",
    ]:
        k = kiem_nguon_video(u)
        assert isinstance(k, KetQuaWhitelistOk), u
        assert kiem_nguon_video(k.url).ok is True, f"url trả về không tự qua lại được: {k.url}"


# ------------------------------------------------------------------ timUrlTrongChu


def test_tim_url_trong_chu_boc_duoc_url_nam_giua_cau() -> None:
    """bóc được url nằm giữa câu"""
    assert (
        tim_url_trong_chu("tải hộ cái này https://vt.tiktok.com/ZSV5bEotV/ nhé bạn")
        == "https://vt.tiktok.com/ZSV5bEotV/"
    )


def test_tim_url_trong_chu_bo_dau_cau_dinh_duoi() -> None:
    """bỏ dấu câu dính đuôi"""
    # People often write "... link https://a.b/c." - the dot does not belong to the URL.
    assert tim_url_trong_chu("xem link https://vt.tiktok.com/ABC.") == "https://vt.tiktok.com/ABC"
    assert tim_url_trong_chu("(https://fb.watch/xyz/)") == "https://fb.watch/xyz/"


def test_tim_url_trong_chu_khong_co_url_thi_tra_none_khong_tra_chuoi_rong() -> None:
    """không có url thì trả null, không trả chuỗi rỗng"""
    # An empty string would slip into ``kiem_nguon_video`` and report an error unlike the real reason.
    assert tim_url_trong_chu("chào bạn") is None


def test_tim_url_trong_chu_lay_url_dau_tien_khi_co_nhieu() -> None:
    """lấy url ĐẦU TIÊN khi có nhiều"""
    assert tim_url_trong_chu("https://vt.tiktok.com/A và https://fb.watch/B") == "https://vt.tiktok.com/A"


# ------------------------------------------------------------------ chặn đường dẫn chuyển tiếp
# The FIRST patch of this hole forbade by DOMAIN NAME (``l.facebook.com``), and that was the WRONG WAY: the
# redirect capability ``/l.php?u=`` and ``/flx/warn/?u=`` works just the same on ``www.facebook.com``,
# ``m.facebook.com``, ``mbasic.facebook.com``, names that MUST be let through because real videos live
# there. MEASURED with a real listener at ``127.0.0.1:8791``: all 8 variants below passed the whitelist AND
# made yt-dlp send a real request to the internal address.

CHUYEN_TIEP: list[tuple[str, str]] = [
    ("https://www.facebook.com/l.php?u=http%3A%2F%2F169.254.169.254%2F", "www - tên miền phải cho qua"),
    ("https://facebook.com/l.php?u=http%3A%2F%2F127.0.0.1%3A3900%2F", "không có www"),
    ("https://m.facebook.com/l.php?u=http%3A%2F%2F127.0.0.1%3A3900%2F", "bản mobile"),
    ("https://mbasic.facebook.com/l.php?u=http%3A%2F%2F127.0.0.1%3A3900%2F", "bản mbasic"),
    ("https://free.facebook.com/l.php?u=http%3A%2F%2F127.0.0.1%3A3900%2F", "bản free"),
    ("https://www.facebook.com/flx/warn/?u=http%3A%2F%2F127.0.0.1%3A3900%2F", "endpoint cảnh báo"),
    ("https://www.tiktok.com/redirect?target=http%3A%2F%2F127.0.0.1%2F", "tham số tên khác, nền tảng khác"),
    (
        "https://www.facebook.com/watch?v=1&next=http%3A%2F%2F127.0.0.1%2F",
        "nhét thêm vào link trông như thật",
    ),
]


@pytest.mark.parametrize(("url", "vi"), CHUYEN_TIEP, ids=[c[1] for c in CHUYEN_TIEP])
def test_chan_duong_dan_chuyen_tiep_chan(url: str, vi: str) -> None:
    """chặn <vì sao>"""
    assert kiem_nguon_video(url).ok is False, f"phải chặn: {url}"


def test_chan_duong_dan_chuyen_tiep_dang_luoc_scheme_double_slash() -> None:
    """chặn dạng lược scheme `//host` - không có `http:` vẫn là địa chỉ"""
    from urllib.parse import quote

    u = f"https://www.facebook.com/l.php?u={quote('//127.0.0.1:3900/x', safe='')}"
    assert kiem_nguon_video(u).ok is False


def test_chan_duong_dan_chuyen_tiep_dang_ma_hoa_hai_lop() -> None:
    """chặn dạng MÃ HÓA HAI LỚP - cách né hiển nhiên nhất khi biết có bộ lọc"""
    # %2568ttp -> %68ttp -> http
    u = "https://www.facebook.com/l.php?u=%2568ttp%3A%2F%2F127.0.0.1%3A3900%2Fx"
    assert kiem_nguon_video(u).ok is False


def test_chan_duong_dan_chuyen_tiep_host_chi_de_chuyen_huong_bi_cam_ke_ca_query_khong_mang_url() -> None:
    """host CHỈ ĐỂ CHUYỂN HƯỚNG bị cấm kể cả khi query KHÔNG mang URL"""
    # A REGRESSION caught by the superset check: the shape rule sees nothing in ``u=x`` (not a URL), so if the
    # domain rule were dropped this payload would GET THROUGH while the previous version blocked it.
    for u in [
        "https://l.facebook.com/l.php?u=x",
        "https://L.FaceBook.CoM/l.php?u=x",
        "https://lm.facebook.com/?a=1",
    ]:
        assert kiem_nguon_video(u).ok is False, f"phải chặn: {u}"


def test_chan_duong_dan_chuyen_tiep_l_instagram_bi_chan_ke_ca_query_khong_mang_url() -> None:
    """l.instagram.com bị chặn kể cả khi query KHÔNG mang URL - nó KHỚP đuôi instagram.com"""
    # Since instagram.com was added to the whitelist, ``l.instagram.com`` matches the suffix
    # ``.instagram.com``. It is now blocked ONLY because the redirect rule runs first. Removing
    # ``l.instagram.com`` from HOST_CHI_DE_CHUYEN_HUONG opens SSRF: ``?u=x`` is not a URL so
    # ``mang_url_khac_trong_query`` sees nothing. This case locks that.
    for u in [
        "https://l.instagram.com/?u=x",
        "https://L.InstaGram.CoM/?u=x",
        "https://l.instagram.com/?u=http%3A%2F%2F127.0.0.1%3A3900%2F",
    ]:
        assert kiem_nguon_video(u).ok is False, f"phải chặn: {u}"


def test_chan_duong_dan_chuyen_tiep_khong_chan_oan_link_that_ke_ca_tham_so_theo_doi() -> None:
    """KHÔNG chặn oan link thật - kể cả khi kèm tham số theo dõi"""
    # A real video link never puts another URL in its query. ``fbclid``, ``mibextid``, ``is_from_webapp`` are
    # identifier strings, not addresses.
    for u in [
        "https://www.facebook.com/watch/?v=123",
        "https://www.facebook.com/reel/123",
        "https://www.facebook.com/share/v/abcdef/",
        "https://www.facebook.com/trang/videos/123?fbclid=IwAR123&mibextid=abc",
        "https://m.facebook.com/watch/?v=123&_rdr",
        "https://fb.watch/abc/",
        "https://www.tiktok.com/@ai/video/766?is_from_webapp=1&sender_device=pc",
        "https://vt.tiktok.com/ZSV5bEotV/",
        "https://www.tiktok.com/t/ZSabc/",
    ]:
        assert kiem_nguon_video(u).ok is True, f"phải cho qua: {u}"
