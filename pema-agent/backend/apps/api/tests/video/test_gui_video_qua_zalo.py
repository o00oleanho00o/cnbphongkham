# ported from: src/video/gui-video-qua-zalo.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The video send path. Every rule here comes from a REAL FAILED send to the user's phone, so do not loosen any
without measuring again:

  - ``sendVideo`` must get ZALO'S URL. Handing it a TikTok/Facebook URL means a computer can watch but the
    PHONE CANNOT: measured with three variants of the same video.
  - The frame size must be read from the very BUFFER about to be sent. A wrong declaration CRASHED the Zalo
    phone app; TikWM returns no size, yt-dlp declares a skewed one.
  - With a poster (source cover already uploaded to Zalo) send a VIDEO CARD; if no poster can be built send AS
    A FILE: better than a card stuck with a cheap placeholder, and Zalo also refuses an empty thumbnail (code
    114).
"""

from __future__ import annotations

import dataclasses
import struct
from dataclasses import dataclass
from typing import Any

import pytest

from pema.video import gui_video_qua_zalo as mod
from pema.video.chuan_bi_anh_bia_video import DichAnhBia
from pema.video.gui_video_qua_zalo import DichGuiVideo, LoiGuiVideo, PhuThuocGuiVideo
from pema.video.kiem_url_video_truoc_khi_gui import KetQuaDo, KetQuaDoLoi, KetQuaDoOk
from pema.video.tai_video_vao_ram import KetQuaTai, KetQuaTaiLoi, KetQuaTaiOk
from pema.video.thong_tin_video import ThongTinVideo


def _dung_mp4(width: int, height: int, thoi_luong_ms: int | None = None) -> bytes:
    """Build a minimal MP4 whose ``tkhd`` declares the right frame size. Passing ``thoi_luong_ms`` adds an
    ``mvhd`` box (timescale 1000) to test duration reading."""
    tkhd = bytearray(92)
    struct.pack_into(">I", tkhd, 0, 92)
    tkhd[4:8] = b"tkhd"
    than = 8
    struct.pack_into(">I", tkhd, than + 40, 0x00010000)  # identity matrix -> no rotation
    struct.pack_into(">I", tkhd, than + 76, round(width * 65536))
    struct.pack_into(">I", tkhd, than + 80, round(height * 65536))

    mvhd = bytearray()
    if thoi_luong_ms is not None:
        mvhd = bytearray(28)  # 8 header + 20 body (v0)
        struct.pack_into(">I", mvhd, 0, 28)
        mvhd[4:8] = b"mvhd"
        struct.pack_into(">I", mvhd, 8 + 12, 1000)  # timescale
        struct.pack_into(">I", mvhd, 8 + 16, thoi_luong_ms)  # duration (timescale 1000 -> ms)

    trak = bytearray(8)
    struct.pack_into(">I", trak, 0, 8 + len(tkhd))
    trak[4:8] = b"trak"
    moov = bytearray(8)
    struct.pack_into(">I", moov, 0, 8 + len(mvhd) + len(trak) + len(tkhd))
    moov[4:8] = b"moov"
    ftyp = bytearray(16)
    struct.pack_into(">I", ftyp, 0, 16)
    ftyp[4:16] = b"ftypisom\x00\x00\x00\x00"
    return bytes(ftyp + moov + mvhd + trak + tkhd)


VIDEO = ThongTinVideo(
    video_url="https://cdn.test/cdn-cua-nguon.mp4",
    thumbnail_url="https://cdn.test/anh-bia-cua-nguon.jpg",
    duration_ms=20_000,
    # DELIBERATELY wrong and DELIBERATELY PORTRAIT: the buffer below declares LANDSCAPE. The real crash had
    # exactly this shape: the source says portrait, the real file is landscape.
    width=576,
    height=1024,
    file_size=1_000_000,
    tac_gia="nguoidang",
    nguon="tikwm",
    nen_tang="tiktok",
)
URL_GOC = "https://vt.tiktok.com/ABC123/"
TRAN = 100 * 1024 * 1024
URL_ZALO = "https://ot147.dlfl.vn/abc/123"
POSTER_ZALO = "https://f120-zpc.zdn.vn/abc/poster.jpg"


@dataclass
class _Ctx:
    """What the fakes record (``daLam``) and what they answer, reset for every test."""

    da_lam: list[dict[str, Any]]
    ket_do: KetQuaDo
    byte_tai: bytes
    loi_tai: dict[str, Any] | None
    poster_url: str | None
    ket_upload: Any
    dem_ca: int = 0


@pytest.fixture
def ctx() -> _Ctx:
    return _Ctx(
        da_lam=[],
        ket_do=KetQuaDoOk(so_byte=5_000_000, kieu_noi_dung="video/mp4", url_cuoi=VIDEO.video_url),
        byte_tai=_dung_mp4(1002, 576),  # LANDSCAPE: quite unlike the 576x1024 the source declares
        loi_tai=None,
        poster_url=POSTER_ZALO,
        ket_upload=[{"fileUrl": URL_ZALO}],
    )


class _ApiGia:
    def __init__(self, ctx: _Ctx) -> None:
        self.ctx = ctx

    async def upload_attachment(self, items: list[dict[str, Any]], thread_id: str, thread_type: int) -> Any:
        self.ctx.da_lam.append({"k": "upload", "byte": len(items[0]["data"]), "ten": items[0]["filename"]})
        return self.ctx.ket_upload

    async def send_video(self, options: dict[str, Any], thread_id: str, thread_type: int) -> Any:
        self.ctx.da_lam.append(
            {
                "k": "sendVideo",
                "url": options["videoUrl"],
                "thumb": options["thumbnailUrl"],
                "w": options["width"],
                "h": options["height"],
                "d": options["duration"],
            }
        )
        return {}

    async def send_message(self, content: dict[str, Any], thread_id: str, thread_type: int) -> Any:
        att = content["attachments"][0]
        self.ctx.da_lam.append({"k": "sendFile", "byte": len(att["data"]), "ten": att["filename"]})
        return {}


def _dich(ctx: _Ctx) -> DichGuiVideo:
    ctx.dem_ca += 1
    return DichGuiVideo(api=_ApiGia(ctx), thread_key=f"acc:{ctx.dem_ca}", thread_id="t1", thread_type=0)


def _phu_thuoc(ctx: _Ctx) -> PhuThuocGuiVideo:
    async def kiem_url(u: str) -> KetQuaDo:
        ctx.da_lam.append({"k": "do", "url": u})
        return ctx.ket_do

    async def tai_url(u: str, _tran: int) -> KetQuaTai:
        ctx.da_lam.append({"k": "taiUrl", "url": u})
        if ctx.loi_tai:
            return KetQuaTaiLoi(**ctx.loi_tai)
        return KetQuaTaiOk(byte=ctx.byte_tai, duong="url")

    async def tai_yt_dlp(u: str, _tran: int) -> KetQuaTai:
        ctx.da_lam.append({"k": "taiYtDlp", "url": u})
        if ctx.loi_tai:
            return KetQuaTaiLoi(**ctx.loi_tai)
        return KetQuaTaiOk(byte=ctx.byte_tai, duong="yt-dlp")

    async def chuan_bi_anh_bia(_dich: DichAnhBia, thumb: str) -> str | None:
        ctx.da_lam.append({"k": "poster", "thumb": thumb})
        return ctx.poster_url

    return PhuThuocGuiVideo(
        kiem_url=kiem_url, tai_url=tai_url, tai_yt_dlp=tai_yt_dlp, chuan_bi_anh_bia=chuan_bi_anh_bia
    )


async def _chay(ctx: _Ctx, video: ThongTinVideo = VIDEO) -> mod.KetQuaGui:
    return await mod.gui_video_qua_zalo(_dich(ctx), video, URL_GOC, TRAN, _phu_thuoc(ctx))


def _viec(ctx: _Ctx, k: str) -> list[dict[str, Any]]:
    return [v for v in ctx.da_lam if v["k"] == k]


def _tin_gui(ctx: _Ctx) -> dict[str, Any]:
    return _viec(ctx, "sendVideo")[0]


# ------------------------------------------------------------------ sendVideo phải nhận URL CỦA ZALO


async def test_send_video_phai_nhan_url_cua_zalo_gui_dung_url_zalo_khong_phai_url_nguon(ctx: _Ctx) -> None:
    """gửi đúng URL Zalo trả về sau upload, không phải URL của nguồn"""
    await _chay(ctx)
    assert _tin_gui(ctx)["url"] == URL_ZALO
    assert _tin_gui(ctx)["url"] != VIDEO.video_url


async def test_send_video_phai_nhan_url_cua_zalo_upload_dung_so_byte_ten_file_duoi_mp4(ctx: _Ctx) -> None:
    """upload đúng số byte đã tải, tên file có đuôi .mp4"""
    await _chay(ctx)
    up = _viec(ctx, "upload")[0]
    assert up["byte"] == len(ctx.byte_tai)
    assert up["ten"].endswith(".mp4"), "sai đuôi thì Zalo không nhận là video"


async def test_send_video_phai_nhan_url_cua_zalo_upload_khong_tra_ve_duong_dan_thi_nem(ctx: _Ctx) -> None:
    """upload KHÔNG trả về đường dẫn thì NÉM, không gửi tin nào"""
    ctx.ket_upload = [{}]
    with pytest.raises(LoiGuiVideo, match="không trả về đường dẫn"):
        await _chay(ctx)
    assert not _viec(ctx, "sendVideo")


async def test_send_video_phai_nhan_url_cua_zalo_gui_dung_mot_lan(ctx: _Ctx) -> None:
    """gửi đúng MỘT lần"""
    await _chay(ctx)
    assert len(_viec(ctx, "sendVideo")) == 1


# ------------------------------------------------------------------ khung hình đọc từ CHÍNH buffer


async def test_khung_hinh_lay_so_trong_file_khong_lay_so_nguon_khai(ctx: _Ctx) -> None:
    """lấy số trong file, KHÔNG lấy số nguồn khai"""
    # The source declares 576x1024 (portrait), the real file is 1002x576 (landscape). Declaring by the
    # source is exactly the case that crashed the Zalo phone app.
    await _chay(ctx)
    assert (_tin_gui(ctx)["w"], _tin_gui(ctx)["h"]) == (1002, 576)


async def test_khung_hinh_video_doc_thi_ra_doc_khong_phai_cu_ngang_la_dung(ctx: _Ctx) -> None:
    """video DỌC thì ra dọc - không phải cứ ngang là đúng"""
    ctx.byte_tai = _dung_mp4(720, 1280)
    await _chay(ctx)
    assert (_tin_gui(ctx)["w"], _tin_gui(ctx)["h"]) == (720, 1280)


async def test_khung_hinh_khong_doc_duoc_thi_lui_ve_so_cua_nguon_chu_khong_bo_cuoc(ctx: _Ctx) -> None:
    """không đọc được thì lùi về số của nguồn chứ không bỏ cuộc"""
    ctx.byte_tai = b"khong phai mp4 gi ca"
    await _chay(ctx)
    assert (_tin_gui(ctx)["w"], _tin_gui(ctx)["h"]) == (VIDEO.width, VIDEO.height)


# ------------------------------------------------------------------ poster: có thì gửi thẻ video, không thì gửi file


async def test_poster_co_poster_gui_the_video_voi_dung_url_poster_cua_zalo(ctx: _Ctx) -> None:
    """có poster -> gửi THẺ VIDEO với đúng URL poster của Zalo"""
    await _chay(ctx)
    assert _tin_gui(ctx)["thumb"] == POSTER_ZALO
    assert not _viec(ctx, "sendFile"), "có poster thì không gửi dạng file"


async def test_poster_dung_poster_bang_anh_bia_nguon_khong_phai_url_nao_khac(ctx: _Ctx) -> None:
    """dựng poster bằng ẢNH BÌA NGUỒN, không phải URL nào khác"""
    await _chay(ctx)
    assert _viec(ctx, "poster")[0]["thumb"] == VIDEO.thumbnail_url


async def test_poster_khong_dung_duoc_poster_gui_dang_file_khong_goi_send_video(ctx: _Ctx) -> None:
    """KHÔNG dựng được poster -> gửi DẠNG FILE, KHÔNG gọi sendVideo"""
    # The user settled: better a file than a placeholder. And Zalo refuses an empty thumb.
    ctx.poster_url = None
    r = await _chay(ctx)
    assert _viec(ctx, "sendFile"), "phải lùi sang gửi file"
    assert not _viec(ctx, "sendVideo"), "không được gửi thẻ video khi thiếu poster"
    assert r.dang == "file"


async def test_poster_gui_dang_file_thi_dinh_dung_byte_da_tai_ten_duoi_mp4(ctx: _Ctx) -> None:
    """gửi dạng file thì đính đúng byte đã tải, tên có đuôi .mp4"""
    ctx.poster_url = None
    await _chay(ctx)
    f = _viec(ctx, "sendFile")[0]
    assert f["byte"] == len(ctx.byte_tai)
    assert f["ten"].endswith(".mp4")


async def test_poster_co_poster_thi_ket_qua_dang_la_video(ctx: _Ctx) -> None:
    """có poster thì ket qua dang = video"""
    r = await _chay(ctx)
    assert r.dang == "video"


# ------------------------------------------------------------------ chọn nguồn byte theo kết quả dò


async def test_chon_nguon_byte_do_qua_thi_tai_thang_url_da_xac_thuc(ctx: _Ctx) -> None:
    """dò QUA thì tải thẳng URL đã xác thực"""
    await _chay(ctx)
    t = _viec(ctx, "taiUrl")[0]
    assert t["url"] == VIDEO.video_url
    assert not _viec(ctx, "taiYtDlp")


async def test_chon_nguon_byte_do_truot_thi_de_yt_dlp_tu_tai_tu_url_goc(ctx: _Ctx) -> None:
    """dò TRƯỢT thì để yt-dlp tự tải, từ URL GỐC"""
    ctx.ket_do = KetQuaDoLoi(ly="HTTP 403")
    r = await _chay(ctx)
    t = _viec(ctx, "taiYtDlp")[0]
    assert t["url"] == URL_GOC
    assert r.duong == "yt-dlp"
    assert not _viec(ctx, "taiUrl")


async def test_chon_nguon_byte_ca_hai_duong_deu_hong_thi_nem_khong_gui_gi(ctx: _Ctx) -> None:
    """cả hai đường đều hỏng thì NÉM, không gửi gì"""
    ctx.ket_do = KetQuaDoLoi(ly="HTTP 404")
    ctx.loi_tai = {"loi": "video riêng tư"}
    with pytest.raises(LoiGuiVideo, match="riêng tư"):
        await _chay(ctx)
    assert not _viec(ctx, "sendVideo")
    assert not _viec(ctx, "sendFile")


async def test_chon_nguon_byte_thieu_cong_cu_thi_cho_co_loi_cau_hinh_len_tren(ctx: _Ctx) -> None:
    """thiếu công cụ thì chở cờ loiCauHinh lên trên"""
    ctx.ket_do = KetQuaDoLoi(ly="HTTP 404")
    ctx.loi_tai = {"loi": "chưa cài yt-dlp", "loi_cau_hinh": True}
    with pytest.raises(LoiGuiVideo) as thay:
        await _chay(ctx)
    assert thay.value.loi_cau_hinh


# ------------------------------------------------------------------ trần dung lượng


async def test_tran_dung_luong_buoc_do_bao_qua_nang_thi_nem_truoc_khi_tai_khong_keo_byte_nao_ve(
    ctx: _Ctx,
) -> None:
    """bước dò báo quá nặng thì NÉM TRƯỚC KHI tải - không kéo byte nào về"""
    ctx.ket_do = dataclasses.replace(ctx.ket_do, so_byte=TRAN + 1)  # type: ignore[type-var]
    with pytest.raises(LoiGuiVideo) as thay:
        await _chay(ctx)
    assert thay.value.qua_nang
    assert thay.value.so_byte == TRAN + 1
    assert not _viec(ctx, "taiUrl"), "biết thừa là quá nặng mà vẫn tải là phí băng thông"


async def test_tran_dung_luong_nguon_giau_dung_luong_tai_xong_moi_biet_vuot_thi_van_chan(ctx: _Ctx) -> None:
    """nguồn giấu dung lượng: tải xong mới biết vượt thì vẫn chặn"""
    ctx.ket_do = dataclasses.replace(ctx.ket_do, so_byte=None)  # type: ignore[type-var]
    ctx.byte_tai = bytes(TRAN + 1)
    with pytest.raises(LoiGuiVideo) as thay:
        await _chay(ctx)
    assert thay.value.qua_nang
    assert not _viec(ctx, "sendVideo")


async def test_tran_dung_luong_cdn_khong_khai_dung_luong_nhung_file_vua_van_thi_van_gui(ctx: _Ctx) -> None:
    """CDN không khai dung lượng nhưng file vừa vặn thì vẫn gửi"""
    ctx.ket_do = dataclasses.replace(ctx.ket_do, so_byte=None)  # type: ignore[type-var]
    await _chay(ctx)
    assert len(_viec(ctx, "sendVideo")) == 1


# ------------------------------------------------------------------ thời lượng: nguồn TRƯỚC, file LẤP CHỖ TRỐNG


async def test_thoi_luong_nguon_co_thoi_luong_thi_dung_cua_nguon_khong_lat_sang_file(ctx: _Ctx) -> None:
    """nguồn CÓ thời lượng -> dùng của nguồn (TikTok/FB), không lật sang file"""
    # VIDEO.duration_ms = 20000; the file declares 9999 -> must still be the source's 20000. Unlike the frame
    # size (the file always wins): a wrong duration is only a label, no crash.
    ctx.byte_tai = _dung_mp4(1002, 576, 9_999)
    await _chay(ctx)
    assert _tin_gui(ctx)["d"] == 20_000


async def test_thoi_luong_nguon_thieu_instagram_duration_0_thi_lay_tu_file(ctx: _Ctx) -> None:
    """nguồn THIẾU thời lượng (Instagram, durationMs=0) -> lấy từ FILE"""
    ctx.byte_tai = _dung_mp4(1002, 576, 51_360)
    video_ig = dataclasses.replace(VIDEO, duration_ms=0, nen_tang="instagram", nguon="yt-dlp")
    await _chay(ctx, video_ig)
    assert _tin_gui(ctx)["d"] == 51_360


async def test_thoi_luong_nguon_thieu_va_file_khong_co_mvhd_thi_0_khong_bia_so(ctx: _Ctx) -> None:
    """nguồn thiếu VÀ file không có mvhd -> 0, không bịa số"""
    ctx.byte_tai = _dung_mp4(1002, 576)  # no mvhd
    video_ig = dataclasses.replace(VIDEO, duration_ms=0)
    await _chay(ctx, video_ig)
    assert _tin_gui(ctx)["d"] == 0


# ------------------------------------------------------------------ added (not in the original): the upload ceiling


async def test_voi_tran_upload_treo_vinh_vien_thi_nem_loi_gui_video_thay_vi_treo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(thêm) upload treo vĩnh viễn thì NÉM LoiGuiVideo khi quá trần, không treo cả lượt"""
    # ``uploadAttachment`` for a video hangs forever when the websocket listener is lost; the ceiling is
    # what turns that into an error. A tiny ceiling and a never-resolving awaitable: deterministic.
    import asyncio

    monkeypatch.setattr(mod, "TRAN_UPLOAD_MS", 10)
    never: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    with pytest.raises(LoiGuiVideo, match="quá"):
        await mod.voi_tran_upload(never)
