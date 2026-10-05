# ported from: src/video/nguon-yt-dlp.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

yt-dlp is the ONLY source of Facebook and the fallback tier of TikTok.

``doc_stdout_yt_dlp`` is a PURE function: it is where every SILENT MISREAD lives (seconds/milliseconds,
cover image, frame size), so it is tested straight with ready-made JSON.

The MISSING TOOL case has its own file (``test_chay_yt_dlp``) because it belongs to the process-running
layer, shared by the metadata path and the file-download path.
"""

from __future__ import annotations

import json

from pema.video import nguon_yt_dlp as mod
from pema.video.chon_format_video import args_chon_format
from pema.video.thong_tin_video import CO_MAC_DINH, KetQuaNguonLoi, KetQuaNguonOk

# The real shape of an info dict, cut down to the fields the code reads.
JSON_DU = json.dumps(
    {
        "url": "https://cdn.test/video.mp4",
        "thumbnail": "https://cdn.test/thumb.jpg",
        "duration": 32.6,
        "width": 576,
        "height": 1024,
        "filesize": 2_000_000,
        "uploader_id": "nguoidung123",
        "title": "Video thử",
    }
)


def _ok(stdout: str, nen_tang: mod.NenTangVideo) -> KetQuaNguonOk:
    ket = mod.doc_stdout_yt_dlp(stdout, nen_tang)
    assert isinstance(ket, KetQuaNguonOk), ket
    return ket


# ------------------------------------------------------------------ yt-dlp - đọc JSON


def test_yt_dlp_doc_json_doi_giay_sang_mili_giay_lam_tron() -> None:
    """đổi GIÂY sang MILI GIÂY, làm tròn"""
    assert _ok(JSON_DU, "tiktok").video.duration_ms == 32_600


def test_yt_dlp_doc_json_json_hong_thi_bao_loi_thu_lai_duoc_chu_khong_nem() -> None:
    """JSON hỏng thì báo lỗi THỬ LẠI ĐƯỢC chứ không ném"""
    ket = mod.doc_stdout_yt_dlp("{khong phai json", "tiktok")
    assert isinstance(ket, KetQuaNguonLoi)
    assert ket.thu_lai_duoc


def test_yt_dlp_doc_json_thieu_url_phang_la_hong_han() -> None:
    """thiếu `url` phẳng là hỏng HẲN - ca đó buộc phải ghép hình và tiếng"""
    # Merging picture+sound means running ffmpeg on a stranger's content, exactly what this design avoids.
    # Falls to another source instead of merging itself.
    ket = mod.doc_stdout_yt_dlp(json.dumps({"duration": 10, "width": 1, "height": 1}), "tiktok")
    assert isinstance(ket, KetQuaNguonLoi)
    assert not ket.thu_lai_duoc, "thử lại không làm video mọc ra luồng phát sẵn"


def test_yt_dlp_doc_json_thieu_thumbnail_thi_lay_anh_cuoi_trong_thumbnails() -> None:
    """thiếu `thumbnail` thì lấy ảnh CUỐI trong `thumbnails` (yt-dlp xếp nhỏ tới lớn)"""
    ket = _ok(
        json.dumps(
            {
                "url": "https://cdn.test/v.mp4",
                "thumbnails": [{"url": "https://cdn.test/nho.jpg"}, {"url": "https://cdn.test/to.jpg"}],
            }
        ),
        "tiktok",
    )
    assert ket.video.thumbnail_url == "https://cdn.test/to.jpg"


def test_yt_dlp_doc_json_facebook_khong_tra_anh_bia_van_ra_ok_voi_chuoi_rong() -> None:
    """Facebook không trả ảnh bìa nào - vẫn phải ra kết quả OK với chuỗi rỗng"""
    # MEASURED: Facebook returns ``thumbnail: null`` AND ``thumbnails: null``. Throwing the whole turn away
    # over a missing cover loses Facebook's only source.
    ket = _ok(
        json.dumps({"url": "https://cdn.test/v.mp4", "thumbnail": None, "thumbnails": None}), "facebook"
    )
    assert ket.video.thumbnail_url == ""


def test_yt_dlp_doc_json_khung_hinh_doc_tu_formats_khi_cap_tren_khong_co() -> None:
    """KHUNG HÌNH: đọc từ `formats` khi cấp trên không có - ca đã làm crash máy"""
    # REAL CASE: a 1280x720 LANDSCAPE Facebook video. yt-dlp chose format ``hd`` which carries no
    # width/height anywhere. The old version fell straight back to the PORTRAIT default 576x1024, Zalo built
    # a portrait frame for a landscape one -> black card, and the phone app CRASHED opening the chat.
    #
    # The real size IS in ``formats``: the old version simply did not read that far.
    ket = _ok(
        json.dumps(
            {
                "url": "https://cdn.test/v.mp4",
                "width": None,
                "height": None,
                "formats": [
                    {"format_id": "sd", "width": None, "height": None},
                    {"format_id": "hd", "width": None, "height": None},
                    # Ratio 2.4:1 (cinema): DELIBERATELY unlike the platform default 16:9. Using 16:9 here
                    # would make this case green even when the code skips ``formats`` and falls to the
                    # default, i.e. green for the wrong reason: the mutation check caught exactly that.
                    {"format_id": "dash", "width": 1920, "height": 800},
                ],
            }
        ),
        "facebook",
    )
    assert ket.video.width > ket.video.height, "khai DỌC cho video NGANG là ca đã làm crash máy"
    # The small error comes from making the side even on normalisation (533.3 -> 534), not from misreading.
    # Assert by TOLERANCE, tight enough to exclude the 16:9 default (1.78).
    ty_le = ket.video.width / ket.video.height
    assert abs(ty_le - 1920 / 800) < 0.01, (
        f"phải lấy tỉ lệ THẬT từ formats (2,4), không phải mặc định nền tảng (1,78). Nhận: {ty_le}"
    )


def test_yt_dlp_doc_json_khung_hinh_giu_ti_le_chuan_hoa_canh_dai_ve_1280() -> None:
    """KHUNG HÌNH: giữ tỉ lệ, chuẩn hóa cạnh dài về 1280"""
    # Measured: the formats array reaches 2560x1440 while ffprobe on the very stream that was sent gives
    # 1280x720. Only the RATIO is known, not the real resolution.
    ket = _ok(
        json.dumps({"url": "https://cdn.test/v.mp4", "formats": [{"width": 2560, "height": 1440}]}),
        "facebook",
    )
    assert (ket.video.width, ket.video.height) == (1280, 720)


def test_yt_dlp_doc_json_khung_hinh_cap_tren_co_thi_tin_cap_tren_khong_chuan_hoa() -> None:
    """KHUNG HÌNH: cấp trên có thì tin cấp trên, KHÔNG chuẩn hóa"""
    # TikTok through yt-dlp measured 1080x1920 at the top level: the number of the stream about to be sent,
    # so more exact than any guess from ``formats``.
    ket = _ok(
        json.dumps(
            {
                "url": "https://cdn.test/v.mp4",
                "width": 1080,
                "height": 1920,
                "formats": [{"width": 2560, "height": 1440}],
            }
        ),
        "tiktok",
    )
    assert (ket.video.width, ket.video.height) == (1080, 1920)


def test_yt_dlp_doc_json_khung_hinh_khong_biet_gi_thi_mac_dinh_theo_nen_tang() -> None:
    """KHUNG HÌNH: không biết gì thì mặc định theo NỀN TẢNG"""
    fb = _ok(json.dumps({"url": "https://cdn.test/v.mp4"}), "facebook")
    tt = _ok(json.dumps({"url": "https://cdn.test/v.mp4"}), "tiktok")
    ig = _ok(json.dumps({"url": "https://cdn.test/v.mp4"}), "instagram")
    assert fb.video.width > fb.video.height, "Facebook đa số NGANG"
    assert tt.video.height > tt.video.width, "TikTok gần như luôn DỌC"
    assert ig.video.height > ig.video.width, "Instagram (reel) gần như luôn DỌC"
    assert tt.video.width == CO_MAC_DINH["width"]
    assert ig.video.width == CO_MAC_DINH["width"]


def test_yt_dlp_doc_json_mang_theo_dung_nen_tang_duoc_truyen_vao() -> None:
    """mang theo đúng nền tảng được truyền vào"""
    fb = _ok(JSON_DU, "facebook")
    tt = _ok(JSON_DU, "tiktok")
    assert fb.video.nen_tang == "facebook"
    assert tt.video.nen_tang == "tiktok"


def test_yt_dlp_doc_json_cat_ten_tac_gia_nguon_khai_200000_ky_tu() -> None:
    """CẮT tên tác giả - nguồn khai 200.000 ký tự thì không nuốt đủ 200.000"""
    # ``uploader`` is a DISPLAY NAME, a free string the poster chose. Uncut it burns tokens, bloats the log
    # and the DB.
    ket = _ok(json.dumps({"url": "https://cdn.test/v.mp4", "uploader": "A" * 200_000}), "tiktok")
    assert ket.video.tac_gia is not None
    assert len(ket.video.tac_gia) <= 64, f"dài {len(ket.video.tac_gia)} ký tự"


def test_yt_dlp_doc_json_khong_cho_tieu_de_video_truong_do_da_bi_bo_han() -> None:
    """KHÔNG chở tiêu đề video - trường đó đã bị bỏ hẳn"""
    # The title is also a free string of the poster, and nobody reads it. Carrying a stranger's string around
    # unused only waits for the day somebody uses it in the wrong place.
    ket = _ok(json.dumps({"url": "https://cdn.test/v.mp4", "title": "bất kỳ"}), "tiktok")
    assert not hasattr(ket.video, "tieu_de"), "trường tieuDe không được sống lại"


def test_yt_dlp_doc_json_filesize_approx_dung_khi_khong_co_filesize() -> None:
    """`filesize_approx` dùng khi không có `filesize`"""
    ket = _ok(json.dumps({"url": "https://cdn.test/v.mp4", "filesize_approx": 999}), "tiktok")
    assert ket.video.file_size == 999


# ------------------------------------------------------------------ phanLoaiLoiYtDlp - nói ĐÚNG loại bệnh
# Three very different kinds, saying the wrong kind makes the user do the wrong thing: needs login (never
# possible), missing tool (the operator fixes), video/source errors (some are worth retrying).


def test_phan_loai_loi_facebook_day_sang_login_php_can_dang_nhap_khong_thu_lai() -> None:
    """Facebook đẩy sang login.php -> CẦN ĐĂNG NHẬP, không thử lại"""
    # The string below has the shape copied from a real run on a user's story, the ID replaced by a fake
    # number: a story ID is the user's personal data and has no business in the repo.
    loi = (
        "ERROR: Unsupported URL: https://www.facebook.com/login.php?next=https%3A%2F%2F"
        "www.facebook.com%2Fstories%2F000000000000000%2FUzpf%3D%2F&_fb_noscript=1"
    )
    r = mod.phan_loai_loi_yt_dlp(loi, False)

    assert isinstance(r, KetQuaNguonLoi)
    assert r.can_dang_nhap is True, "thiếu cờ là bot bảo người dùng thử lại vô ích"
    assert not r.thu_lai_duoc
    assert "Unsupported URL" not in r.loi, "stderr thô KHÔNG được chảy vào câu model đọc"
    assert "login.php" not in r.loi, "stderr thô KHÔNG được chảy vào câu model đọc"


def test_phan_loai_loi_bat_ca_checkpoint_va_login_next() -> None:
    """bắt cả checkpoint và /login/?next="""
    for loi in [
        "ERROR: https://www.facebook.com/checkpoint/?next=x",
        "ERROR: redirected to https://www.instagram.com/login/?next=/p/abc/",
    ]:
        r = mod.phan_loai_loi_yt_dlp(loi, False)
        assert isinstance(r, KetQuaNguonLoi), loi
        assert r.can_dang_nhap is True, loi


def test_phan_loai_loi_thieu_cong_cu_co_loi_cau_hinh_khong_phai_can_dang_nhap() -> None:
    """thiếu công cụ -> cờ loiCauHinh, KHÔNG phải canDangNhap"""
    r = mod.phan_loai_loi_yt_dlp("Máy chủ chưa cài yt-dlp...", True)
    assert isinstance(r, KetQuaNguonLoi)
    assert r.loi_cau_hinh is True
    assert not r.can_dang_nhap
    assert not r.thu_lai_duoc, "thiếu binary thì thử lại vô ích"


def test_phan_loai_loi_trang_thu_thach_cua_tiktok_la_ca_dang_thu_lai() -> None:
    """trang thử thách của TikTok là ca ĐÁNG THỬ LẠI"""
    r = mod.phan_loai_loi_yt_dlp("ERROR: [TikTok] Unable to extract universal data", False)
    assert isinstance(r, KetQuaNguonLoi)
    assert r.thu_lai_duoc, "đo được: 4 lần thử -> 5/6 phiên thành công"
    assert not r.can_dang_nhap


def test_phan_loai_loi_video_rieng_tu_da_xoa_thi_khong_thu_lai() -> None:
    """video riêng tư / đã xóa thì KHÔNG thử lại"""
    for loi in ["ERROR: This video is private", "ERROR: Video unavailable"]:
        r = mod.phan_loai_loi_yt_dlp(loi, False)
        assert isinstance(r, KetQuaNguonLoi)
        assert not r.thu_lai_duoc, loi
        assert not r.can_dang_nhap, "đừng nhận nhầm thành 'cần đăng nhập'"


def test_phan_loai_loi_instagram_empty_media_response_rate_limit_la_ca_dang_thu_lai() -> None:
    """Instagram 'empty media response' / 'rate-limit' là ca ĐÁNG THỬ LẠI (tamThoi), KHÔNG phải cần đăng nhập"""
    # yt-dlp cannot tell rate-limit / private / deleted apart for IG: all come out as "empty media
    # response". The most common case (rate-limit) passes after a few minutes, so it is filed as retryable
    # so the tool says "try again later" instead of making people give up.
    for loi in [
        "ERROR: [Instagram] ABC: Instagram sent an empty media response. Check if this post is accessible...",
        "ERROR: [Instagram] Requested content is not available, rate-limit reached or login required",
    ]:
        r = mod.phan_loai_loi_yt_dlp(loi, False)
        assert isinstance(r, KetQuaNguonLoi)
        assert r.thu_lai_duoc, f"phải thử-lại-được: {loi}"
        assert not r.can_dang_nhap, "KHÔNG dùng câu 'cần đăng nhập' kiểu Facebook cho IG"


# ------------------------------------------------------------------ doiSoMetadataYtDlp - đối số đọc metadata


def test_doi_so_metadata_cho_nguyen_bo_chon_chung_khop_duong_tai() -> None:
    """chở NGUYÊN bộ chọn chung (gồm -S ưu tiên h264) - khớp đường tải"""
    # The metadata path and the download path are two separate yt-dlp calls; if the selectors drift it
    # declares the size of one format but sends the bytes of another: it already crashed the Zalo app.
    d = mod.doi_so_metadata_yt_dlp("https://x")
    assert " ".join(args_chon_format()) in " ".join(d), f"thiếu bộ chọn chung: {' '.join(args_chon_format())}"


def test_doi_so_metadata_url_dung_cuoi_sau_moi_co() -> None:
    """URL đứng CUỐI, sau mọi cờ"""
    d = mod.doi_so_metadata_yt_dlp("https://vt.tiktok.com/ABC/")
    assert d[-1] == "https://vt.tiktok.com/ABC/"
