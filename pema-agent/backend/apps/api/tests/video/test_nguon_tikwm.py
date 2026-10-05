# ported from: src/video/nguon-tikwm.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

TikWM is the MAIN source of TikTok: every TikTok video a user sends goes through here.

The most important case in this file is ``play`` vs ``wmplay``. It is a decision the user checked by EYE on
two real downloaded files (``wmplay`` has a moving TikTok logo, ``play`` is clean), and taking the wrong
field turns nothing red: the bot still sends the video, still reports success, only the video carries a
watermark, exactly what this feature exists to avoid.

``httpx.MockTransport`` replaces the network instead of a real call: a real call turns the test red when the
network is slow, when TikWM hits its 1 request/second limit, or when the sample video is deleted.
"""

from __future__ import annotations

from typing import Any

import httpx

from pema.video.nguon_tikwm import lay_video_tu_tikwm
from pema.video.thong_tin_video import KetQuaNguonLoi, KetQuaNguonOk

URL = "https://www.tiktok.com/@a/video/1"


def _chan_fetch(than: object, status: int = 200) -> tuple[httpx.MockTransport, list[str]]:
    """A canned answer plus the list of URLs that were called."""
    url_da_goi: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_da_goi.append(str(request.url))
        return httpx.Response(status, json=than)

    return httpx.MockTransport(handler), url_da_goi


# A body with every field, identical to the shape measured from the real TikWM.
THAN_DU: dict[str, Any] = {
    "code": 0,
    "data": {
        "play": "https://tikwm.test/KHONG-watermark.mp4",
        "wmplay": "https://tikwm.test/CO-watermark.mp4",
        "cover": "https://tikwm.test/cover.jpg",
        "origin_cover": "https://tikwm.test/origin.jpg",
        "duration": 20,
        "size": 1_234_567,
        "title": "Video thử",
        "author": {"unique_id": "nguoidung123"},
    },
}


def _than_sua(**sua: Any) -> dict[str, Any]:
    """``{code: 0, data: {...THAN_DU.data, ...sua}}``; a value of ``None`` means the field is MISSING."""
    data = {**THAN_DU["data"], **sua}
    return {"code": 0, "data": {k: v for k, v in data.items() if v is not None}}


# ------------------------------------------------------------------ TikWM - chọn đúng bản không watermark


async def test_tikwm_chon_ban_khong_watermark_lay_play_chu_khong_lay_wmplay() -> None:
    """lấy `play` chứ KHÔNG lấy `wmplay`"""
    transport, _ = _chan_fetch(THAN_DU)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk)
    assert ket.video.video_url == "https://tikwm.test/KHONG-watermark.mp4", (
        "`wmplay` có logo TikTok di chuyển - đã kiểm bằng mắt trên hai file tải thật"
    )
    assert "CO-watermark" not in ket.video.video_url


async def test_tikwm_chon_ban_khong_watermark_thieu_play_la_hong_khong_roi_sang_wmplay() -> None:
    """thiếu `play` là HỎNG, KHÔNG được lặng lẽ rơi sang `wmplay`"""
    # This case guards the most tempting wrong fix: "play missing, use wmplay for now to have a video". A
    # watermarked video is worse than no video, since the user does not know they just got a dirty copy.
    transport, _ = _chan_fetch(_than_sua(play=None))
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert "CO-watermark" not in ket.loi


# ------------------------------------------------------------------ TikWM - quy đổi và mặc định


async def test_tikwm_quy_doi_doi_giay_sang_mili_giay() -> None:
    """đổi GIÂY sang MILI GIÂY - `sendVideo` nhận mili giây"""
    transport, _ = _chan_fetch(THAN_DU)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk)
    assert ket.video.duration_ms == 20_000, "quên nhân 1000 thì video 20 giây báo là 20 mili giây"


async def test_tikwm_quy_doi_thieu_thoi_luong_thi_de_0_chu_khong_de_nan() -> None:
    """thiếu thời lượng thì để 0 chứ không để NaN"""
    transport, _ = _chan_fetch(_than_sua(duration=None))
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk)
    assert ket.video.duration_ms == 0


async def test_tikwm_quy_doi_thieu_cover_thi_lui_ve_origin_cover() -> None:
    """thiếu `cover` thì lùi về `origin_cover`"""
    transport, _ = _chan_fetch(_than_sua(cover=None))
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk)
    assert ket.video.thumbnail_url == "https://tikwm.test/origin.jpg"


async def test_tikwm_quy_doi_thieu_ca_hai_anh_bia_thi_de_chuoi_rong_khong_nem_ca_luot_di() -> None:
    """thiếu cả hai ảnh bìa thì để chuỗi rỗng, KHÔNG ném cả lượt đi"""
    transport, _ = _chan_fetch(_than_sua(cover=None, origin_cover=None))
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk), "mất cái ảnh bìa mà bỏ luôn video là đánh đổi sai"
    assert ket.video.thumbnail_url == ""


async def test_tikwm_quy_doi_khung_hinh_mac_dinh_la_doc_tikwm_khong_tra_width_height() -> None:
    """khung hình mặc định là DỌC - TikWM không trả width/height"""
    transport, _ = _chan_fetch(THAN_DU)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonOk)
    assert ket.video.height > ket.video.width, "mặc định NGANG là Zalo dựng khung sai cho mọi video TikTok"


# ------------------------------------------------------------------ TikWM - phân loại lỗi


async def test_tikwm_phan_loai_loi_cham_gioi_han_toc_do_la_thu_lai_duoc() -> None:
    """chạm giới hạn tốc độ là THỬ LẠI ĐƯỢC"""
    transport, _ = _chan_fetch({"code": -1, "msg": "Free Api Limit: 1 request/second"})
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert ket.thu_lai_duoc, "nghỉ 1 giây rồi thử lại là qua - coi là hỏng hẳn thì mất video"


async def test_tikwm_phan_loai_loi_url_sai_la_hong_han_khong_thu_lai() -> None:
    """URL sai là hỏng HẲN, không thử lại"""
    transport, _ = _chan_fetch({"code": -1, "msg": "Url parsing is failed"})
    ket = await lay_video_tu_tikwm("https://www.facebook.com/watch/?v=1", transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert not ket.thu_lai_duoc, "thử lại một lỗi vĩnh viễn chỉ tốn thời gian người đang đợi"


async def test_tikwm_phan_loai_loi_http_5xx_la_phia_ho_thu_lai_duoc() -> None:
    """HTTP 5xx là phía họ - thử lại được"""
    transport, _ = _chan_fetch({}, 503)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert ket.thu_lai_duoc


async def test_tikwm_phan_loai_loi_http_4xx_la_ta_gui_sai_thu_lai_vo_ich() -> None:
    """HTTP 4xx là ta gửi sai - thử lại vô ích"""
    transport, _ = _chan_fetch({}, 404)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert not ket.thu_lai_duoc


async def test_tikwm_phan_loai_loi_khong_bao_gio_bao_loi_cau_hinh() -> None:
    """KHÔNG bao giờ báo `loiCauHinh` - TikWM không phải thứ cài trên máy chủ"""
    transport, _ = _chan_fetch({}, 500)
    ket = await lay_video_tu_tikwm(URL, transport=transport)

    assert isinstance(ket, KetQuaNguonLoi)
    assert not ket.loi_cau_hinh, "báo nhầm là bảo người vận hành đi cài thứ không cần cài"


# ------------------------------------------------------------------ TikWM - dựng URL gọi


async def test_tikwm_dung_url_goi_ma_hoa_url_nguoi_dung_vao_tham_so_truy_van() -> None:
    """mã hóa URL người dùng vào tham số truy vấn"""
    transport, url_da_goi = _chan_fetch(THAN_DU)
    await lay_video_tu_tikwm("https://vt.tiktok.com/ABC?a=1&b=2", transport=transport)

    assert len(url_da_goi) == 1
    assert "https%3A%2F%2Fvt.tiktok.com%2FABC%3Fa%3D1%26b%3D2" in url_da_goi[0], (
        "không mã hóa thì `&b=2` thành tham số của TikWM chứ không phải của URL"
    )
