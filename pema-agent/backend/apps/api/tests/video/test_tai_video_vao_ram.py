# ported from: src/video/tai-video-vao-ram.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Getting video bytes into RAM.

What is most worth guarding here is NOT whether the download works, but two SILENT failures: (a) a wrongly
written ``-o -`` makes yt-dlp write to the DISK, exactly what the user said they dislike (grinding the SSD,
leaving junk); (b) a format selector with a picture+sound merge branch makes yt-dlp choose and then die for
lack of ffmpeg, and that infrastructure error falls into the generic sentence "the video may be private".
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pema.shared.safe_remote_download import DownloadOptions, RemoteFile
from pema.video import tai_video_vao_ram as mod
from pema.video.chay_yt_dlp import KetQuaChayYtDlp, TuyChonChay
from pema.video.chon_format_video import args_chon_format
from pema.video.tai_video_vao_ram import KetQuaTaiLoi, KetQuaTaiOk, PhuThuocTai

TRAN = 50 * 1024 * 1024


async def _tai_rong(_u: str, _o: DownloadOptions) -> RemoteFile:
    return RemoteFile(data=b"", media_type="video/mp4", file_name="v.mp4")


async def _chay_rong(_d: list[str], _t: int, _tc: TuyChonChay) -> KetQuaChayYtDlp:
    return KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=b"")


def _phu_thuoc(
    tai_url: Callable[[str, DownloadOptions], Awaitable[RemoteFile]] = _tai_rong,
    chay: Callable[[list[str], int, TuyChonChay], Awaitable[KetQuaChayYtDlp]] = _chay_rong,
) -> PhuThuocTai:
    return PhuThuocTai(tai_url=tai_url, chay=chay)


def _chay_tra(ket: KetQuaChayYtDlp) -> Callable[[list[str], int, TuyChonChay], Awaitable[KetQuaChayYtDlp]]:
    async def chay(_d: list[str], _t: int, _tc: TuyChonChay) -> KetQuaChayYtDlp:
        return ket

    return chay


# ------------------------------------------------------------------ đối số yt-dlp - hai cờ hỏng câm


def test_doi_so_yt_dlp_o_dash_xuat_ra_stdout_khong_ghi_ra_dia() -> None:
    """`-o -` xuất ra stdout, KHÔNG ghi ra đĩa"""
    d = mod.doi_so_tai_yt_dlp("https://x", TRAN)
    assert d[d.index("-o") + 1] == "-", "sai chỗ này là yt-dlp ghi file ra đĩa"


def test_doi_so_yt_dlp_bo_chon_format_khong_co_nhanh_ghep_hinh_tieng() -> None:
    """bộ chọn format KHÔNG có nhánh ghép hình+tiếng - image không cài ffmpeg"""
    d = mod.doi_so_tai_yt_dlp("https://x", TRAN)
    f = d[d.index("-f") + 1]
    assert "+" not in f, f"nhánh ghép cần ffmpeg: {f}"
    assert "mp4" in f, "phải ưu tiên mp4 để Zalo phát được"


def test_doi_so_yt_dlp_cho_nguyen_bo_chon_chung_hai_duong_phai_khop() -> None:
    """chở NGUYÊN bộ chọn chung (gồm -S ưu tiên h264) - hai đường yt-dlp phải khớp"""
    # The download path and the metadata path are two SEPARATE yt-dlp calls. If the selectors drift the bot
    # declares the size of one format but sends the bytes of another: it already crashed the Zalo phone app.
    # Both take their arguments from ``args_chon_format``.
    d = mod.doi_so_tai_yt_dlp("https://x", TRAN)
    assert " ".join(args_chon_format()) in " ".join(d), f"thiếu bộ chọn chung: {' '.join(args_chon_format())}"


def test_doi_so_yt_dlp_cho_tran_dung_luong_xuong_yt_dlp_de_no_chan_truoc_khi_tai() -> None:
    """chở trần dung lượng xuống yt-dlp để nó chặn TRƯỚC khi tải"""
    d = mod.doi_so_tai_yt_dlp("https://x", 12_345)
    assert d[d.index("--max-filesize") + 1] == "12345"


def test_doi_so_yt_dlp_url_dung_cuoi_sau_moi_co() -> None:
    """URL đứng CUỐI, sau mọi cờ - đứng trước là nó ăn mất giá trị của cờ"""
    d = mod.doi_so_tai_yt_dlp("https://vt.tiktok.com/ABC/", TRAN)
    assert d[-1] == "https://vt.tiktok.com/ABC/"


# ------------------------------------------------------------------ yt-dlp tự tải


async def test_yt_dlp_tu_tai_xin_stdout_nhi_phan_va_tran_buffer_rong_hon_tran_video() -> None:
    """xin stdout NHỊ PHÂN và trần buffer rộng hơn trần video"""
    thay: list[TuyChonChay] = []

    async def chay(_d: list[str], _t: int, tc: TuyChonChay) -> KetQuaChayYtDlp:
        thay.append(tc)
        return KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=bytes([1, 2, 3]))

    await mod.tai_bang_yt_dlp_vao_ram("https://x", TRAN, _phu_thuoc(chay=chay))
    tuy_chon = thay[0]
    assert tuy_chon.nhi_phan is True, "ép về chuỗi là hỏng file"
    assert tuy_chon.tran_stdout is not None
    assert tuy_chon.tran_stdout > TRAN, "trần buffer phải rộng hơn cả video"


async def test_yt_dlp_tu_tai_tra_ve_byte_va_ghi_dung_duong_da_di() -> None:
    """trả về byte và ghi đúng ĐƯỜNG đã đi"""
    r = await mod.tai_bang_yt_dlp_vao_ram(
        "https://x",
        TRAN,
        _phu_thuoc(chay=_chay_tra(KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=bytes(99)))),
    )
    assert isinstance(r, KetQuaTaiOk)
    assert len(r.byte) == 99
    assert r.duong == "yt-dlp"


async def test_yt_dlp_tu_tai_stdout_rong_ma_thoat_ma_0_van_la_hong() -> None:
    """stdout RỖNG mà thoát mã 0 vẫn là HỎNG - đó là ca vượt --max-filesize"""
    # yt-dlp does not report an error when it skips an oversize file, it just outputs nothing. Treating that
    # as success uploads an empty buffer to Zalo.
    r = await mod.tai_bang_yt_dlp_vao_ram(
        "https://x",
        TRAN,
        _phu_thuoc(chay=_chay_tra(KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=b""))),
    )
    assert isinstance(r, KetQuaTaiLoi)


async def test_yt_dlp_tu_tai_thieu_han_stdout_nhi_phan_cung_la_hong_khong_nem() -> None:
    """thiếu hẳn stdoutNhiPhan cũng là hỏng, không ném"""
    r = await mod.tai_bang_yt_dlp_vao_ram(
        "https://x", TRAN, _phu_thuoc(chay=_chay_tra(KetQuaChayYtDlp(ok=True, stdout="")))
    )
    assert isinstance(r, KetQuaTaiLoi)


async def test_yt_dlp_tu_tai_buffer_vuot_tran_thi_chan_max_filesize_vo_hieu_khi_nguon_khong_khai_co() -> None:
    """buffer vượt trần thì CHẶN - `--max-filesize` vô hiệu khi nguồn không khai cỡ"""
    r = await mod.tai_bang_yt_dlp_vao_ram(
        "https://x",
        100,
        _phu_thuoc(chay=_chay_tra(KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=bytes(101)))),
    )
    assert isinstance(r, KetQuaTaiLoi)


async def test_yt_dlp_tu_tai_cho_co_loi_cau_hinh_len_nguyen_ven() -> None:
    """chở cờ `loiCauHinh` lên nguyên vẹn - đây là lỗi người VẬN HÀNH phải sửa"""
    # Losing this flag turns "the server has no yt-dlp" into "the video is private", and the user retries in
    # vain.
    r = await mod.tai_bang_yt_dlp_vao_ram(
        "https://x",
        TRAN,
        _phu_thuoc(
            chay=_chay_tra(KetQuaChayYtDlp(ok=False, loi="No module named yt_dlp", loi_cau_hinh=True))
        ),
    )
    assert isinstance(r, KetQuaTaiLoi)
    assert r.loi_cau_hinh is True


# ------------------------------------------------------------------ tải thẳng từ URL


async def test_tai_thang_tu_url_cho_tran_dung_luong_xuong_bo_tai_co_gac() -> None:
    """chở trần dung lượng xuống bộ tải có gác"""
    opt: list[DownloadOptions] = []

    async def tai_url(_u: str, o: DownloadOptions) -> RemoteFile:
        opt.append(o)
        return RemoteFile(data=bytes(10), media_type="video/mp4", file_name="v.mp4")

    await mod.tai_tu_url_vao_ram("https://cdn/x.mp4", 777, _phu_thuoc(tai_url=tai_url))
    assert opt[0].max_bytes == 777, "không chở trần xuống là tải hết rồi mới biết"


async def test_tai_thang_tu_url_tai_ve_rong_la_hong_khong_phai_thanh_cong() -> None:
    """tải về rỗng là hỏng, không phải thành công"""
    r = await mod.tai_tu_url_vao_ram("https://x", TRAN, _phu_thuoc())
    assert isinstance(r, KetQuaTaiLoi)


async def test_tai_thang_tu_url_bo_tai_nem_thi_tra_ket_qua_hong_khong_de_ngoai_le_thoat_ra() -> None:
    """bộ tải NÉM thì trả kết quả hỏng, không để ngoại lệ thoát ra"""

    async def tai_url(_u: str, _o: DownloadOptions) -> RemoteFile:
        raise RuntimeError("vượt trần dung lượng")

    r = await mod.tai_tu_url_vao_ram("https://x", TRAN, _phu_thuoc(tai_url=tai_url))
    assert isinstance(r, KetQuaTaiLoi)
    assert "vượt trần" in r.loi
