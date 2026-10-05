# ported from: src/video/chuoi-nguon-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from dataclasses import dataclass

from pema.video.chuoi_nguon_video import (
    KetQuaChuoiLoi,
    KetQuaChuoiOk,
    MatXich,
    TuyChonChuoi,
    chuoi_nguon_cho,
    lay_video_qua_chuoi,
)
from pema.video.thong_tin_video import (
    KetQuaNguon,
    KetQuaNguonLoi,
    KetQuaNguonOk,
    TenNguonVideo,
    ThongTinVideo,
)


def _video_gia(nguon: TenNguonVideo) -> ThongTinVideo:
    return ThongTinVideo(
        video_url="https://cdn/x.mp4",
        thumbnail_url="https://cdn/x.jpg",
        duration_ms=24_000,
        width=576,
        height=1024,
        file_size=1000,
        tac_gia="ai_do",
        nguon=nguon,
        nen_tang="tiktok",
    )


HONG_THU_LAI = KetQuaNguonLoi(loi="chập chờn", thu_lai_duoc=True)
HONG_VINH_VIEN = KetQuaNguonLoi(loi="video riêng tư", thu_lai_duoc=False)


@dataclass
class _Dem:
    so_lan: int = 0


def _mat_gia(ten: TenNguonVideo, ket_qua: list[KetQuaNguon]) -> tuple[MatXich, _Dem]:
    """Build a fake link returning the listed results in turn, with a call counter.

    Past the end of the list it repeats the last element: so "always fails" needs only one element instead
    of listing the full number of tries."""
    dem = _Dem()

    async def chay(_url: str) -> KetQuaNguon:
        ket = ket_qua[min(dem.so_lan, len(ket_qua) - 1)]
        dem.so_lan += 1
        return ket

    return MatXich(ten=ten, chay=chay), dem


async def _khong_nghi(_ms: int) -> None:
    """No real pause: a real sleep slows the test and measures nothing more."""


def _tuy_chon(so_lan_thu: int, mats: list[MatXich], nghi_ms: int = 0, doi: object = None) -> TuyChonChuoi:
    return TuyChonChuoi(
        so_lan_thu=so_lan_thu,
        nghi_ms=nghi_ms,
        doi=doi or _khong_nghi,  # type: ignore[arg-type]
        chuoi=mats,
    )


# ------------------------------------------------------------------ chuoiNguonCho - thứ tự nguồn


def test_chuoi_nguon_cho_tiktok_tikwm_truoc_yt_dlp_sau() -> None:
    """TikTok: TikWM trước, yt-dlp sau"""
    # This order is a conclusion from measurements (TikWM 12/12 vs yt-dlp 3/7). Reversing it breaks the very
    # reason TikWM was chosen.
    assert [m.ten for m in chuoi_nguon_cho("tiktok")] == ["tikwm", "yt-dlp"]


def test_chuoi_nguon_cho_facebook_chi_yt_dlp_tikwm_khong_nhan_facebook() -> None:
    """Facebook: CHỈ yt-dlp - TikWM không nhận Facebook"""
    assert [m.ten for m in chuoi_nguon_cho("facebook")] == ["yt-dlp"]


def test_chuoi_nguon_cho_instagram_chi_yt_dlp_tikwm_khong_nhan_instagram() -> None:
    """Instagram: CHỈ yt-dlp - TikWM không nhận Instagram"""
    assert [m.ten for m in chuoi_nguon_cho("instagram")] == ["yt-dlp"]


# ------------------------------------------------------------------ layVideoQuaChuoi - luật rơi tầng


async def test_lay_video_qua_chuoi_nguon_dau_thanh_cong_khong_cham_nguon_sau() -> None:
    """nguồn đầu thành công -> KHÔNG chạm nguồn sau"""
    a, dem_a = _mat_gia("tikwm", [KetQuaNguonOk(video=_video_gia("tikwm"))])
    b, dem_b = _mat_gia("yt-dlp", [HONG_THU_LAI])

    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a, b]))

    assert isinstance(k, KetQuaChuoiOk)
    assert k.video.nguon == "tikwm"
    assert dem_a.so_lan == 1
    assert dem_b.so_lan == 0, "không được gọi nguồn dự phòng khi nguồn chính chạy"


async def test_lay_video_qua_chuoi_nguon_dau_chap_chon_thu_du_so_lan_roi_moi_sang_nguon_sau() -> None:
    """nguồn đầu chập chờn -> thử ĐỦ số lần rồi mới sang nguồn sau"""
    a, dem_a = _mat_gia("tikwm", [HONG_THU_LAI])
    b, _ = _mat_gia("yt-dlp", [KetQuaNguonOk(video=_video_gia("yt-dlp"))])

    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a, b]))

    assert dem_a.so_lan == 4, "phải thử đủ 4 lần trước khi bỏ nguồn chính"
    assert isinstance(k, KetQuaChuoiOk)
    assert k.video.nguon == "yt-dlp"


async def test_lay_video_qua_chuoi_loi_vinh_vien_bo_qua_thu_lai_sang_nguon_sau_ngay() -> None:
    """lỗi VĨNH VIỄN -> bỏ qua phần thử lại, sang nguồn sau NGAY"""
    # Retrying a permanent error (wrong url, deleted video) only wastes the time of the person waiting AND
    # holds one of the two parallel slots.
    a, dem_a = _mat_gia("tikwm", [HONG_VINH_VIEN])
    b, dem_b = _mat_gia("yt-dlp", [KetQuaNguonOk(video=_video_gia("yt-dlp"))])

    await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a, b]))

    assert dem_a.so_lan == 1, "lỗi vĩnh viễn chỉ được gọi ĐÚNG MỘT lần"
    assert dem_b.so_lan == 1


async def test_lay_video_qua_chuoi_nguon_dau_hong_2_lan_roi_chay_van_thang() -> None:
    """nguồn đầu hỏng 2 lần rồi chạy -> vẫn thắng, không cần nguồn sau"""
    a, dem_a = _mat_gia("tikwm", [HONG_THU_LAI, HONG_THU_LAI, KetQuaNguonOk(video=_video_gia("tikwm"))])
    b, dem_b = _mat_gia("yt-dlp", [HONG_THU_LAI])

    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a, b]))

    assert isinstance(k, KetQuaChuoiOk)
    assert dem_a.so_lan == 3
    assert dem_b.so_lan == 0


async def test_lay_video_qua_chuoi_ca_hai_nguon_hong_bao_hong_kem_da_thu_nhung_gi() -> None:
    """cả hai nguồn hỏng -> báo hỏng, kèm ĐÃ THỬ NHỮNG GÌ"""
    a, dem_a = _mat_gia("tikwm", [HONG_THU_LAI])
    b, dem_b = _mat_gia("yt-dlp", [HONG_THU_LAI])

    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a, b]))

    assert isinstance(k, KetQuaChuoiLoi)
    # Without this part, when it fails you only know "failed", not where.
    assert [t.nguon for t in k.da_thu] == ["tikwm", "yt-dlp"]
    assert "tikwm" in k.loi_cho_log
    assert "yt-dlp" in k.loi_cho_log
    assert dem_a.so_lan == 4
    assert dem_b.so_lan == 4


async def test_lay_video_qua_chuoi_so_lan_thu_0_van_goi_dung_mot_lan_khong_bo_qua_nguon() -> None:
    """soLanThu = 0 vẫn gọi ĐÚNG MỘT lần, không bỏ qua nguồn"""
    # A bad configuration must not turn into "try nothing and report failure".
    a, dem_a = _mat_gia("tikwm", [KetQuaNguonOk(video=_video_gia("tikwm"))])
    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(0, [a]))
    assert isinstance(k, KetQuaChuoiOk)
    assert dem_a.so_lan == 1


# ------------------------------------------------------------------ layVideoQuaChuoi - cờ tamThoi


async def test_co_tam_thoi_co_nguon_hong_thu_lai_duoc_thi_tam_thoi_true() -> None:
    """có nguồn hỏng THỬ-LẠI-ĐƯỢC -> tamThoi:true (nguồn chặn tạm, đợi là được)"""
    a, _ = _mat_gia("tikwm", [HONG_THU_LAI])
    b, _ = _mat_gia("yt-dlp", [HONG_THU_LAI])
    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(2, [a, b]))
    assert isinstance(k, KetQuaChuoiLoi)
    assert k.tam_thoi is True


async def test_co_tam_thoi_tat_ca_hong_vinh_vien_thi_tam_thoi_false() -> None:
    """tất cả hỏng VĨNH VIỄN -> tamThoi:false (riêng tư/đã xóa, thử lại vô ích)"""
    a, _ = _mat_gia("tikwm", [HONG_VINH_VIEN])
    b, _ = _mat_gia("yt-dlp", [HONG_VINH_VIEN])
    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(2, [a, b]))
    assert isinstance(k, KetQuaChuoiLoi)
    assert k.tam_thoi is False


async def test_co_tam_thoi_mot_nguon_vinh_vien_mot_nguon_thu_lai_duoc_thi_tam_thoi_true() -> None:
    """MỘT nguồn vĩnh viễn + MỘT nguồn thử-lại-được -> tamThoi:true (đúng ca fptbongda thật)"""
    # Real case: TikWM returned "Url parsing failed" (permanent, region lock) while yt-dlp returned "Unable
    # to extract" (anti-bot, retryable). Only ONE source still having a retry door means the user must be
    # told "wait and retry", not told to give up.
    a, _ = _mat_gia("tikwm", [HONG_VINH_VIEN])
    b, _ = _mat_gia("yt-dlp", [HONG_THU_LAI])
    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(2, [a, b]))
    assert isinstance(k, KetQuaChuoiLoi)
    assert k.tam_thoi is True


async def test_co_tam_thoi_thu_lai_duoc_truoc_vinh_vien_sau_van_true_or_tich_luy_khong_last_wins() -> None:
    """thử-lại-được TRƯỚC + vĩnh viễn SAU -> vẫn tamThoi:true (OR tích lũy, KHÔNG last-wins)"""
    # The REVERSE of the case above, deliberately to lock the accumulating OR: TikWM 5xx/rate-limit
    # (retryable) then yt-dlp "Private" (permanent). If someone changes it to last-wins assignment
    # (``tam_thoi = ket.thu_lai_duoc``) this case comes out wrongly false, while the fptbongda case above
    # stays green, so missing this direction lets exactly that mutation through.
    a, _ = _mat_gia("tikwm", [HONG_THU_LAI])
    b, _ = _mat_gia("yt-dlp", [HONG_VINH_VIEN])
    k = await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(2, [a, b]))
    assert isinstance(k, KetQuaChuoiLoi)
    assert k.tam_thoi is True


# ------------------------------------------------------------------ nhịp nghỉ - TikWM giới hạn 1 request/giây


async def test_nhip_nghi_khong_nghi_sau_lan_thu_cuoi_cua_mot_nguon() -> None:
    """KHÔNG nghỉ sau lần thử CUỐI của một nguồn"""
    # Pausing and then dropping that source wastes the time of the person waiting, and holds a slot in the
    # parallel queue (only 2 slots).
    nghi: list[int] = []

    async def doi(ms: int) -> None:
        nghi.append(ms)

    a, dem_a = _mat_gia("tikwm", [HONG_THU_LAI])

    await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(3, [a], nghi_ms=1000, doi=doi))

    assert dem_a.so_lan == 3
    assert len(nghi) == 2, "3 lần thử thì chỉ nghỉ 2 lần (giữa 1-2 và 2-3)"
    assert nghi == [1000, 1000]


async def test_nhip_nghi_thanh_cong_ngay_lan_dau_thi_khong_nghi_lan_nao() -> None:
    """thành công ngay lần đầu thì KHÔNG nghỉ lần nào"""
    nghi: list[int] = []

    async def doi(ms: int) -> None:
        nghi.append(ms)

    a, _ = _mat_gia("tikwm", [KetQuaNguonOk(video=_video_gia("tikwm"))])
    await lay_video_qua_chuoi("u", "tiktok", _tuy_chon(4, [a], nghi_ms=1000, doi=doi))
    assert len(nghi) == 0
