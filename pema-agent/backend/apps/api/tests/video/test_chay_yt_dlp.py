# ported from: src/video/chay-yt-dlp.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The yt-dlp process layer is shared by the metadata path and the download path, so it is the only place that
needs to guard three things:

1. The ALLOW-LIST of environment variables (secrets must NOT flow into the process that parses a stranger's
   content).
2. Recognising the MISSING TOOL case, in BOTH shapes.
3. The hardening flags are always present.

About (2): the earlier version caught only ``ENOENT``. MEASURED with a missing module the error code is 1,
NOT "ENOENT", i.e. the real Docker case (python3 present, module missing) fell into the generic branch and the
model got "the video may be private" while the disease is in the Dockerfile.
"""

from __future__ import annotations

import pytest

from pema.video import chay_yt_dlp as mod


@pytest.fixture(autouse=True)
def _ytdlp_khong_ton_tai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YTDLP_PATH", "yt-dlp-chac-chan-khong-ton-tai-tren-may-nay")


# ------------------------------------------------------------------ nhận diện ca THIẾU CÔNG CỤ


def test_nhan_dien_ca_thieu_cong_cu_thieu_chinh_binary_enoent() -> None:
    """thiếu chính binary (ENOENT)"""
    assert mod.la_loi_thieu_cong_cu("ENOENT", "") is True


def test_nhan_dien_ca_thieu_cong_cu_co_python_nhung_thieu_module() -> None:
    """có python nhưng THIẾU MODULE - stderr thật, mã thoát 1 chứ không ENOENT"""
    # The string below is copied verbatim from a real measurement. This is the case Docker will meet (broken
    # pip install, changed base image, a package removed by mistake).
    stderr = "C:\\Python314\\python.exe: No module named yt_dlp"
    assert mod.la_loi_thieu_cong_cu(1, stderr) is True, "bỏ lọt ca này là đổ oan cho video"


def test_nhan_dien_ca_thieu_cong_cu_bat_ca_bien_the_gach_ngang_va_nhay() -> None:
    """bắt cả biến thể gạch ngang và nháy của thông điệp Python"""
    for s in [
        "/usr/bin/python3: No module named yt-dlp",
        "python3: No module named 'yt_dlp'",
        'python: No module named "yt_dlp"',
        "PYTHON3: NO MODULE NAMED YT_DLP",
    ]:
        assert mod.la_loi_thieu_cong_cu(1, s) is True, f"phải nhận ra: {s}"


def test_nhan_dien_ca_thieu_cong_cu_loi_that_cua_video_khong_bi_nhan_nham() -> None:
    """lỗi THẬT của video KHÔNG bị nhận nhầm thành thiếu công cụ"""
    for s in [
        "ERROR: [TikTok] 123: Video not available",
        "ERROR: [facebook] 456: Cannot parse data",
        "ERROR: [generic] Unable to extract universal data for rehydration",
        "ERROR: This video is private",
    ]:
        assert mod.la_loi_thieu_cong_cu(1, s) is False, f"không được nhận nhầm: {s}"


# ------------------------------------------------------------------ danh sách CHO PHÉP biến môi trường


def test_danh_sach_cho_phep_env_khong_cho_bi_mat_sang_tien_trinh_con(monkeypatch: pytest.MonkeyPatch) -> None:
    """KHÔNG chở bí mật sang tiến trình con"""
    # This process parses the content of a URL sent by a stranger. Anything it writes (debug log, crash
    # report) can carry variables along.
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", "bi-mat-khong-duoc-lo")
    monkeypatch.setenv("LLM_API_KEY", "sk-bi-mat")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/db")
    ra = mod.env_toi_thieu()
    for ten in ["CREDENTIALS_ENCRYPTION_KEY", "LLM_API_KEY", "DATABASE_URL"]:
        assert ten not in ra, f"{ten} KHÔNG được lọt sang tiến trình con"


def test_danh_sach_cho_phep_env_khong_cho_pythonpath_pythonstartup(monkeypatch: pytest.MonkeyPatch) -> None:
    """KHÔNG chở PYTHONPATH / PYTHONSTARTUP - hai biến nạp mã Python"""
    monkeypatch.setenv("PYTHONPATH", "/duong/dan/ke-tan-cong")
    monkeypatch.setenv("PYTHONSTARTUP", "/duong/dan/doc.py")
    ra = mod.env_toi_thieu()
    assert "PYTHONPATH" not in ra, "PYTHONPATH nạp module tùy ý vào tiến trình"
    assert "PYTHONSTARTUP" not in ra


def test_danh_sach_cho_phep_env_bien_moi_tu_dong_nam_ngoai(monkeypatch: pytest.MonkeyPatch) -> None:
    """biến mới thêm vào process.env tự động nằm NGOÀI - đó là điểm của danh sách cho phép"""
    monkeypatch.setenv("MOT_BI_MAT_MOI_TINH_NAM_2027", "x")
    assert "MOT_BI_MAT_MOI_TINH_NAM_2027" not in mod.env_toi_thieu()


def test_danh_sach_cho_phep_env_van_cho_du_thu_yt_dlp_can_chay(monkeypatch: pytest.MonkeyPatch) -> None:
    """VẪN chở đủ thứ yt-dlp cần chạy"""
    monkeypatch.setenv("PATH", "/usr/bin")
    ra = mod.env_toi_thieu()
    assert ra["PYTHONIOENCODING"] == "utf-8", "thiếu là Python trên Windows ném khi in tiêu đề có dấu"
    # PATH is the only variable certain to exist on every system: check it passes through.
    assert "PATH" in ra or "Path" in ra, "không có PATH thì không tìm nổi python"


def test_danh_sach_cho_phep_env_cho_bien_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """chở biến proxy - VPS siết egress thì thiếu nhóm này là yt-dlp không ra được mạng"""
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.noi-bo:3128")
    monkeypatch.setenv("NO_PROXY", "localhost")
    ra = mod.env_toi_thieu()
    assert ra["HTTPS_PROXY"] == "http://proxy.noi-bo:3128"
    assert ra["NO_PROXY"] == "localhost"


# ------------------------------------------------------------------ dungLoiGoi


def test_dung_loi_goi_co_an_toan_luon_co_mat() -> None:
    """`--ignore-config` và `--no-plugin-dirs` LUÔN có mặt"""
    # Without ``--ignore-config`` a ``yt-dlp.conf`` can set ``--exec``, i.e. run an arbitrary command
    # (measured both ways). ``--no-plugin-dirs`` blocks plugins, which are Python code in this process.
    lenh = mod.dung_loi_goi(["--dump-single-json", "https://x"])
    assert "--ignore-config" in lenh.doi_so, "thiếu là mở đường chạy lệnh tùy ý"
    assert "--no-plugin-dirs" in lenh.doi_so, "thiếu là mở đường nạp mã Python"


def test_dung_loi_goi_hai_co_dung_truoc_doi_so_cua_caller() -> None:
    """hai cờ đó đứng TRƯỚC đối số của caller"""
    lenh = mod.dung_loi_goi(["--dump-single-json", "https://x"])
    i_co = lenh.doi_so.index("--ignore-config")
    i_cua_caller = lenh.doi_so.index("--dump-single-json")
    assert i_cua_caller > i_co >= 0, f"thứ tự sai: {' '.join(lenh.doi_so)}"


def test_dung_loi_goi_doi_so_cua_caller_duoc_giu_nguyen_dung_thu_tu() -> None:
    """đối số của caller được giữ nguyên, đúng thứ tự"""
    lenh = mod.dung_loi_goi(["-f", "bv*+ba", "https://x"])
    assert lenh.doi_so[-3:] == ["-f", "bv*+ba", "https://x"]


def test_dung_loi_goi_env_la_env_da_loc_khong_phai_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """env đưa vào tiến trình là env ĐÃ LỌC, KHÔNG phải process.env"""
    # The most important case of this file: ``env_toi_thieu`` is tested hard as a function, but whether it is
    # USED was not measured before.
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", "bi-mat-khong-duoc-lo")
    monkeypatch.setenv("LLM_API_KEY", "sk-bi-mat")
    lenh = mod.dung_loi_goi(["--version"])
    assert "CREDENTIALS_ENCRYPTION_KEY" not in lenh.env, "khóa giải mã cookie Zalo bị lộ"
    assert "LLM_API_KEY" not in lenh.env
    assert lenh.env["PYTHONIOENCODING"] == "utf-8", "vẫn phải là env do env_toi_thieu dựng"


def test_dung_loi_goi_khong_co_yt_dlp_path_chay_python_m_yt_dlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """YTDLP_PATH trống thì chạy `<PYTHON_PATH> -m yt_dlp`, PYTHON_PATH trống thì lùi về `python`"""
    monkeypatch.setenv("YTDLP_PATH", "  ")
    monkeypatch.setenv("PYTHON_PATH", "")
    lenh = mod.dung_loi_goi(["--version"])
    assert lenh.file == "python"
    assert lenh.doi_so[:2] == ["-m", "yt_dlp"]
    monkeypatch.setenv("PYTHON_PATH", "/opt/py/bin/python3")
    assert mod.dung_loi_goi([]).file == "/opt/py/bin/python3"


# ------------------------------------------------------------------ stdout NHỊ PHÂN


def test_stdout_nhi_phan_dung_loi_goi_co_o_dash_va_tran_buffer_rong() -> None:
    """dựng lời gọi có `-o -` và trần buffer rộng cho video"""
    # ``-o -`` makes yt-dlp write the video straight to stdout, so bytes go from the network into RAM and
    # never touch the disk: exactly what the user asked for (they worry about download-delete cycles
    # grinding the SSD, not about bandwidth).
    lenh = mod.dung_loi_goi(["-o", "-", "https://x"])
    assert "-o" in lenh.doi_so
    assert lenh.doi_so[lenh.doi_so.index("-o") + 1] == "-"


def test_stdout_nhi_phan_co_an_toan_van_dung_truoc_ke_ca_o_duong_tai() -> None:
    """cờ siết bảo mật VẪN đứng trước, kể cả ở đường tải"""
    # The download path also runs a yt-dlp process, so it needs exactly the same hardening: no shortcut.
    lenh = mod.dung_loi_goi(["-o", "-", "https://x"])
    assert "--ignore-config" in lenh.doi_so
    assert "--no-plugin-dirs" in lenh.doi_so
    assert lenh.doi_so.index("--ignore-config") < lenh.doi_so.index("-o")


def test_stdout_nhi_phan_bat_encoding_buffer_khi_lay_stdout_nhi_phan() -> None:
    """BẬT `encoding: buffer` khi lấy stdout nhị phân"""
    # Without it the byte stream is forced to a UTF-8 string and the file received does not open: a SILENT
    # failure, since everything else runs as usual.
    tc = mod.tuy_chon_exec(1000, {}, mod.TuyChonChay(nhi_phan=True, tran_stdout=50))
    assert tc.encoding == "buffer"
    assert tc.max_buffer == 50, "tải video cần trần buffer rộng hơn mặc định"


def test_stdout_nhi_phan_khong_bat_khi_doc_metadata() -> None:
    """KHÔNG bật khi đọc metadata - JSON thì đọc thành chữ mới dùng được"""
    tc = mod.tuy_chon_exec(1000, {}, mod.TuyChonChay())
    assert tc.encoding is None
    assert tc.max_buffer > 0, "vẫn phải có trần buffer"


def test_stdout_nhi_phan_env_van_la_env_da_loc_o_duong_tai(monkeypatch: pytest.MonkeyPatch) -> None:
    """env vẫn là env ĐÃ LỌC ở đường tải"""
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", "bi-mat")
    assert "CREDENTIALS_ENCRYPTION_KEY" not in mod.dung_loi_goi(["-o", "-"]).env


# ------------------------------------------------------------------ chayYtDlp (binary không tồn tại)


async def test_chay_yt_dlp_chay_that_voi_binary_khong_ton_tai_bao_dung_benh() -> None:
    """báo ĐÚNG BỆNH kèm cờ loiCauHinh, KHÔNG đổ cho video"""
    ket = await mod.chay_yt_dlp(["--version"], 20_000)

    assert ket.ok is False
    assert ket.loi_cau_hinh is True, "thiếu cờ này là tool nói 'video có thể ở chế độ riêng tư'"
    assert "yt-dlp" in ket.loi, "câu lỗi phải gọi tên thứ cần cài"
