# ported from: src/video/chuan-bi-anh-bia-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Build the poster = download the source cover -> upload to Zalo -> return the Zalo URL.

Every rule comes from a measurement on a phone:
  - An image URL on an outside host -> the video card is pitch black, so it MUST be uploaded, not handed over.
  - When it cannot be built return ``None`` (the caller falls back to a file), NEVER raise: losing the poster
    still leaves a file send, raising loses the whole video.
"""

from __future__ import annotations

import struct
from typing import Any

from pema.video.chuan_bi_anh_bia_video import DichAnhBia, PhuThuocAnhBia, chuan_bi_anh_bia_video


def _png_nho(w: int, h: int) -> bytes:
    """A valid PNG header so ``doc_kich_thuoc_anh`` can read the size."""
    b = bytearray(26)
    struct.pack_into(">I", b, 0, 0x89504E47)
    struct.pack_into(">I", b, 16, w)
    struct.pack_into(">I", b, 20, h)
    return bytes(b)


POSTER_ZALO = "https://f120-zpc.zdn.vn/abc/poster.jpg"


class _ApiGia:
    def __init__(self, tra_ve: Any = None, nem: Exception | None = None) -> None:
        self.tra_ve = tra_ve
        self.nem = nem
        self.da_upload: list[list[dict[str, Any]]] = []

    async def upload_attachment(self, items: list[dict[str, Any]], thread_id: str, thread_type: int) -> Any:
        self.da_upload.append(items)
        if self.nem is not None:
            raise self.nem
        return self.tra_ve


def _dich(api: _ApiGia) -> DichAnhBia:
    return DichAnhBia(api=api, thread_id="t1", thread_type=0)


def _tai(buf: bytes | None) -> PhuThuocAnhBia:
    async def tai_anh(_url: str, _max: int) -> bytes | None:
        return buf

    return PhuThuocAnhBia(tai_anh=tai_anh)


# ------------------------------------------------------------------ dựng poster từ ảnh bìa nguồn


async def test_dung_poster_tai_anh_upload_len_zalo_tra_normal_url() -> None:
    """tải ảnh -> upload lên Zalo -> trả normalUrl"""
    api = _ApiGia([{"normalUrl": POSTER_ZALO}])
    r = await chuan_bi_anh_bia_video(_dich(api), "https://cdn/cover.png", _tai(_png_nho(960, 540)))
    assert r == POSTER_ZALO
    assert len(api.da_upload) == 1
    # Read the size right from the image, not made up
    meta = api.da_upload[0][0]["metadata"]
    assert (meta["width"], meta["height"]) == (960, 540)


async def test_dung_poster_chap_nhan_hd_url_thumb_url_khi_thieu_normal_url() -> None:
    """chấp nhận hdUrl/thumbUrl khi thiếu normalUrl"""
    api = _ApiGia([{"hdUrl": POSTER_ZALO}])
    r = await chuan_bi_anh_bia_video(_dich(api), "https://cdn/c.png", _tai(_png_nho(10, 10)))
    assert r == POSTER_ZALO


# ------------------------------------------------------------------ trả null (lùi sang gửi file), KHÔNG ném


async def test_tra_null_khong_co_anh_bia_nguon_chuoi_rong() -> None:
    """không có ảnh bìa nguồn (chuỗi rỗng)"""
    goi_tai = False

    async def tai_anh(_url: str, _max: int) -> bytes | None:
        nonlocal goi_tai
        goi_tai = True
        return _png_nho(10, 10)

    r = await chuan_bi_anh_bia_video(
        _dich(_ApiGia([{"normalUrl": POSTER_ZALO}])), "", PhuThuocAnhBia(tai_anh=tai_anh)
    )
    assert r is None
    assert not goi_tai, "rỗng thì đừng tải gì cả"


async def test_tra_null_tai_anh_hong_tra_null() -> None:
    """tải ảnh hỏng (trả null)"""
    r = await chuan_bi_anh_bia_video(_dich(_ApiGia([{"normalUrl": POSTER_ZALO}])), "https://x", _tai(None))
    assert r is None


async def test_tra_null_doc_khong_ra_kich_thuoc_vd_webp_thi_bo_khong_upload() -> None:
    """đọc không ra kích thước (vd WebP) thì bỏ, không upload"""
    api = _ApiGia([{"normalUrl": POSTER_ZALO}])
    r = await chuan_bi_anh_bia_video(_dich(api), "https://x", _tai(b"RIFF....WEBP khong doc duoc kich thuoc"))
    assert r is None
    assert api.da_upload == [], "không đọc được kích thước thì đừng upload"


async def test_tra_null_upload_nem_thi_nuot_tra_null() -> None:
    """upload NÉM thì nuốt, trả null"""
    api = _ApiGia(nem=RuntimeError("Zalo từ chối ảnh"))
    r = await chuan_bi_anh_bia_video(_dich(api), "https://x", _tai(_png_nho(10, 10)))
    assert r is None


async def test_tra_null_upload_tra_ve_khong_co_url_nao_thi_null() -> None:
    """upload trả về không có URL nào thì null"""
    api = _ApiGia([{}])
    r = await chuan_bi_anh_bia_video(_dich(api), "https://x", _tai(_png_nho(10, 10)))
    assert r is None
