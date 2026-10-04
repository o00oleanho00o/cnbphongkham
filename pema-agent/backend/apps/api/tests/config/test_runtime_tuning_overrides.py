# ported from: src/config/runtime-tuning-settings.test.ts
"""Overrides set from the dashboard win over ``.env`` and must be READ AGAIN on every call: a cache here goes back
to the old problem (a restart is needed to see a change). A's contract tests of the same module live in
``test_runtime_tuning_settings.py``; this file is the D1 half: the DB-backed provider, ``list_tuning``,
``validate_tuning`` (cross rules) and the writes.

Forced differences: the DB is the in-memory snapshot of one clinic; ``setTuning`` is async; the machine RAM of the
video rule is a seam (``memory_probe``). Test names are the snake_case form of ``describe_it``.
"""

from __future__ import annotations

import pytest

from pema.config import runtime_tuning_settings as tuning
from pema.config.runtime_tuning_settings import (
    get_tuning,
    install_tuning_provider,
    kiem_ram_video,
    list_tuning,
    reset_tuning,
    set_tuning,
    validate_tuning,
)
from pema.config.testing_settings import SettingsEnv
from pema_contracts.testing import FAKE_CLINIC_ID


@pytest.fixture(autouse=True)
def env(settings_env: SettingsEnv) -> SettingsEnv:
    settings_env.monkeypatch.setenv("LLM_MAX_STEPS", "8")
    settings_env.monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")
    install_tuning_provider(settings_env.snapshot)
    return settings_env


async def set_raw(env: SettingsEnv, key: str, value: str) -> None:
    await env.snapshot.set(FAKE_CLINIC_ID, "tuning_" + key, value)


async def test_get_tuning_db_de_env_chua_dat_gi_thi_lay_gia_tri_trong_env() -> None:
    """chưa đặt gì thì lấy giá trị trong .env"""
    assert get_tuning("LLM_MAX_STEPS") == 8


async def test_get_tuning_db_de_env_dat_roi_thi_lay_gia_tri_moi_ngay_khong_can_khoi_dong_lai() -> None:
    """đặt rồi thì lấy giá trị mới NGAY, không cần khởi động lại"""
    await set_tuning(FAKE_CLINIC_ID, "LLM_MAX_STEPS", 12)
    assert get_tuning("LLM_MAX_STEPS") == 12, "đọc lại phải thấy ngay - cache là hỏng cả mục đích"


async def test_get_tuning_db_de_env_null_xoa_de_quay_ve_env() -> None:
    """null = xóa đè, quay về .env"""
    await set_tuning(FAKE_CLINIC_ID, "LLM_MAX_STEPS", 12)
    await set_tuning(FAKE_CLINIC_ID, "LLM_MAX_STEPS", None)
    assert get_tuning("LLM_MAX_STEPS") == 8


async def test_get_tuning_db_de_env_gia_tri_ngoai_khoang_cho_phep_bi_bo_qua_thay_vi_lam_chet_bot(
    env: SettingsEnv,
) -> None:
    """giá trị ngoài khoảng cho phép bị bỏ qua thay vì làm chết bot"""
    await set_raw(env, "LLM_MAX_STEPS", "9999")
    assert get_tuning("LLM_MAX_STEPS") == 8, "sửa tay trong DB không được phá bot"


async def test_get_tuning_db_de_env_gia_tri_khong_phai_so_cung_roi_ve_env(env: SettingsEnv) -> None:
    """giá trị không phải số cũng rơi về .env"""
    await set_raw(env, "LLM_MAX_STEPS", "tam")
    assert get_tuning("LLM_MAX_STEPS") == 8


async def test_get_tuning_db_de_env_kieu_bat_tat_doc_dung() -> None:
    """kiểu bật/tắt đọc đúng"""
    await set_tuning(FAKE_CLINIC_ID, "AGENT_TRACE_ENABLED", False)
    assert get_tuning("AGENT_TRACE_ENABLED") is False
    await set_tuning(FAKE_CLINIC_ID, "AGENT_TRACE_ENABLED", True)
    assert get_tuning("AGENT_TRACE_ENABLED") is True


async def test_get_tuning_db_de_env_kieu_chon_gia_tri_la_roi_ve_env(env: SettingsEnv) -> None:
    """kiểu chọn: giá trị lạ rơi về .env"""
    await set_raw(env, "LLM_REASONING_EFFORT", "sieu-cao")
    assert get_tuning("LLM_REASONING_EFFORT") == "medium"
    await set_tuning(FAKE_CLINIC_ID, "LLM_REASONING_EFFORT", "high")
    assert get_tuning("LLM_REASONING_EFFORT") == "high"


async def test_get_tuning_db_de_env_list_tuning_noi_ro_o_nao_dang_lay_tu_env() -> None:
    """listTuning nói rõ ô nào đang lấy từ .env"""
    await set_tuning(FAKE_CLINIC_ID, "LLM_MAX_STEPS", 5)
    items = {item.key: item for item in list_tuning()}
    assert items["LLM_MAX_STEPS"].from_env is False
    assert items["LLM_MAX_STEPS"].value == 5
    assert items["LLM_MAX_STEPS"].mac_dinh == 8
    assert items["WEB_FETCH_MAX_CHARS"].from_env is True
    assert len(items) == 72


async def test_reset_tuning_removes_every_override() -> None:
    """reset xóa mọi override"""
    await set_tuning(FAKE_CLINIC_ID, "LLM_MAX_STEPS", 5)
    await set_tuning(FAKE_CLINIC_ID, "AGENT_TRACE_ENABLED", False)
    await reset_tuning(FAKE_CLINIC_ID)
    assert get_tuning("LLM_MAX_STEPS") == 8
    assert get_tuning("AGENT_TRACE_ENABLED") is True


async def test_set_tuning_unknown_key_is_refused() -> None:
    """key lạ bị từ chối, không ghi rác vào DB"""
    with pytest.raises(tuning.UnknownTuningKeyError):
        await set_tuning(FAKE_CLINIC_ID, "NOT_A_KEY", 1)


# Constraints BETWEEN parameters. Nobody sees by looking at two separate inputs that setting the turn ceiling
# below the image ceiling kills a valid image turn.


async def test_validate_tuning_tran_luot_phai_lon_hon_tran_ve_anh() -> None:
    """trần lượt phải lớn hơn trần vẽ ảnh"""
    loi = validate_tuning({"LLM_TURN_TIMEOUT_MS": 300_000, "IMAGE_GEN_TIMEOUT_MS": 600_000})
    # Check the exact message instead of counting: other rules run on the same values
    assert any("lớn hơn trần thời gian mỗi ảnh" in item for item in loi)


async def test_validate_tuning_kiem_duoc_ca_khi_chi_sua_mot_o_o_kia_lay_gia_tri_hien_tai() -> None:
    """kiểm được cả khi chỉ sửa MỘT ô - ô kia lấy giá trị hiện tại"""
    await set_tuning(FAKE_CLINIC_ID, "IMAGE_GEN_TIMEOUT_MS", 600_000)
    loi = validate_tuning({"LLM_TURN_TIMEOUT_MS": 120_000})
    assert len(loi) > 0, "chỉ gửi 1 ô vẫn phải bắt được"


async def test_validate_tuning_thoi_gian_im_lang_phai_nho_hon_tran_moi_anh() -> None:
    """thời gian im lặng phải nhỏ hơn trần mỗi ảnh"""
    loi = validate_tuning({"IMAGE_GEN_STALL_MS": 300_000, "IMAGE_GEN_TIMEOUT_MS": 100_000})
    assert any("im lặng" in item for item in loi)


async def test_validate_tuning_gian_nhip_gui_toi_thieu_khong_duoc_lon_hon_toi_da() -> None:
    """giãn nhịp gửi tối thiểu không được lớn hơn tối đa"""
    loi = validate_tuning({"SEND_DELAY_MIN_MS": 5000, "SEND_DELAY_MAX_MS": 1000})
    assert any("tối thiểu" in item for item in loi)


async def test_validate_tuning_tran_ky_tu_tai_lieu_qua_lon_so_voi_tran_token_thi_chan() -> None:
    """trần ký tự tài liệu quá lớn so với trần token thì chặn"""
    loi = validate_tuning({"DOCUMENT_MAX_CHARS": 400_000, "LLM_MAX_OUTPUT_TOKENS": 16_384})
    assert any("tài liệu" in item for item in loi)


async def test_validate_tuning_tran_context_qua_thap_so_voi_tran_token_viet_ra_thi_chan() -> None:
    """trần context quá thấp so với trần token viết ra thì chặn

    The bot only uses 70% of the context ceiling; the other 30% must hold what the model writes. A context
    ceiling at the minimum 4,000 with output at 16,384 is a self-contradicting configuration: the reserve is
    already eaten by the output.
    """
    loi = validate_tuning({"LLM_CONTEXT_WINDOW": 4_000, "LLM_MAX_OUTPUT_TOKENS": 16_384})
    assert any("viết ra" in item for item in loi), f"phải chặn, nhận: {loi}"


async def test_validate_tuning_mac_dinh_128000_voi_16384_thi_hop_le_doi_chung() -> None:
    """mặc định 128.000 với 16.384 thì hợp lệ - đối chứng cho ca trên"""
    assert validate_tuning({"LLM_CONTEXT_WINDOW": 128_000, "LLM_MAX_OUTPUT_TOKENS": 16_384}) == []


async def test_validate_tuning_bo_mac_dinh_khi_phat_hanh_hop_le_khong_tu_chan_chinh_minh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bộ mặc định KHI PHÁT HÀNH hợp lệ - không tự chặn chính mình"""
    monkeypatch.setattr(tuning, "memory_probe", lambda: 0.0)  # the video rule is not under test here
    assert (
        validate_tuning(
            {
                "LLM_TURN_TIMEOUT_MS": 900_000,
                "IMAGE_GEN_TIMEOUT_MS": 600_000,
                "IMAGE_GEN_STALL_MS": 90_000,
                "SEND_DELAY_MIN_MS": 800,
                "SEND_DELAY_MAX_MS": 2500,
                "DOCUMENT_MAX_CHARS": 20_000,
                "LLM_MAX_OUTPUT_TOKENS": 16_384,
            }
        )
        == []
    )


async def test_validate_tuning_tran_token_thap_ma_tran_tai_lieu_cao_thi_chan() -> None:
    """trần token thấp mà trần tài liệu cao thì chặn - đúng ca môi trường test đang dính"""
    loi = validate_tuning({"DOCUMENT_MAX_CHARS": 20_000, "LLM_MAX_OUTPUT_TOKENS": 2048})
    assert any("tài liệu" in item for item in loi), "2048 token không viết nổi 20.000 ký tự"


# kb: the result ceiling must hold the number of chunks x the chunk length (I2)


async def test_validate_tuning_kb_dashboard_tu_choi_to_hop_ma_tran_nho_hon_tong_doan_se_lay() -> None:
    """dashboard từ chối tổ hợp mà trần nhỏ hơn tổng đoạn sẽ lấy"""
    loi = validate_tuning({"KB_TOP_K": 20, "KB_CHUNK_CHARS": 1600, "KB_MAX_RESULT_CHARS": 4000})
    assert len(loi) > 0, "tổ hợp này làm phần lớn đoạn bị vứt lặng lẽ mà không ai báo"


async def test_validate_tuning_kb_ha_tran_ket_qua_duoi_muc_can_cung_bi_chan_du_chi_sua_mot_o() -> None:
    """hạ KB_MAX_RESULT_CHARS xuống dưới mức cần cho cấu hình HIỆN CÓ cũng bị chặn dù chỉ sửa một ô"""
    assert len(validate_tuning({"KB_MAX_RESULT_CHARS": 600})) > 0


async def test_validate_tuning_kb_to_hop_co_du_cho_thi_khong_bi_chan_doi_chung() -> None:
    """tổ hợp có đủ chỗ thì KHÔNG bị chặn - đối chứng cho ca trên

    Real formula: ``KB_TOP_K * (KB_CHUNK_CHARS*(1+overlap%/100) + 150) + 520``; the overlap is not passed so the
    default 10% applies: 3*(1000*1.1+150)+520 = 4270 <= 4500.
    """
    assert validate_tuning({"KB_TOP_K": 3, "KB_CHUNK_CHARS": 1000, "KB_MAX_RESULT_CHARS": 4500}) == []


async def test_validate_tuning_kb_chong_lan_cao_day_noi_dung_that_vuot_tran() -> None:
    """chồng lấn cao đẩy nội dung thật vượt trần dù KB_CHUNK_CHARS trông có vẻ vừa (Important 3, vòng rà soát lần 3)

    The case the reviewer measured: topK=10, chunk=1200, overlap 50% -> the real content per chunk reaches 1800
    (1200*1.5). The rule WITHOUT overlap asks 13,920 so a ceiling of 15,000 would pass; the rule WITH overlap
    asks 20,020 so the same 15,000 must be blocked.
    """
    loi = validate_tuning(
        {
            "KB_TOP_K": 10,
            "KB_CHUNK_CHARS": 1200,
            "KB_CHUNK_OVERLAP_PERCENT": 50,
            "KB_MAX_RESULT_CHARS": 15_000,
        }
    )
    assert len(loi) > 0


async def test_validate_tuning_kb_mac_dinh_phat_hanh_cua_chinh_repo_thoa_rang_buoc_cheo() -> None:
    """mặc định PHÁT HÀNH của chính repo (env.ts) THỎA ràng buộc chéo

    The most important regression guard of the phase: a self-contradicting default is the root bug of I2
    (KB_TOP_K=5 and =20 once gave IDENTICAL results because the default ceiling was too small). It reads the
    REAL defaults (``tuning_default``), not literals, so a future change of one default that forgets the other
    is caught.
    """
    keys = ("KB_TOP_K", "KB_CHUNK_CHARS", "KB_MAX_RESULT_CHARS")
    assert validate_tuning({key: tuning.tuning_default(key) for key in keys}) == []


# video: size x parallel runs must fit the RAM of the server. The bytes of a video live in RAM, not on disk.
# Two sliders look valid separately but multiply to 2000 MB x 8 = 16 GB.

RAM_2GB = 2048


async def test_kiem_ram_video_mac_dinh_100_mb_x_2_luot_lot_tren_vps_2_gb() -> None:
    """mặc định 100 MB x 2 lượt lọt trên VPS 2 GB"""
    assert kiem_ram_video(100, 2, RAM_2GB) is None


async def test_kiem_ram_video_kich_tran_ca_hai_thanh_truot_thi_chan() -> None:
    """kịch trần cả hai thanh trượt thì CHẶN"""
    message = kiem_ram_video(2000, 8, RAM_2GB)
    assert message, "2000 MB x 8 lượt = 16 GB, phải chặn"
    assert "16600 MB" in message, "phải nói con số đỉnh để người dùng biết hạ bao nhiêu"
    assert "512 MB" in message, "và nói mức an toàn của máy này"


async def test_kiem_ram_video_cong_ca_ram_cua_tien_trinh_tai_khong_chi_co_video() -> None:
    """CỘNG cả RAM của tiến trình tải, không chỉ cỡ video

    Each yt-dlp process takes ~75 MB FIXED whatever the video size. Ignoring it under-estimates, and here
    under-estimating means the server runs out of memory.
    """
    assert kiem_ram_video(50, 4, RAM_2GB) is None, "4 x (50+75) = 500, lọt dưới 512"
    assert kiem_ram_video(60, 4, RAM_2GB), "4 x (60+75) = 540 > 512, phải chặn"


async def test_kiem_ram_video_may_nhieu_ram_hon_thi_cho_phep_cau_hinh_lon_hon() -> None:
    """máy nhiều RAM hơn thì cho phép cấu hình lớn hơn"""
    assert kiem_ram_video(500, 4, 4096), "trên 4 GB thì 2300 MB là quá"
    assert kiem_ram_video(500, 4, 32768) is None, "trên 32 GB thì vẫn còn dư"


@pytest.mark.parametrize("key", ["VIDEO_MAX_SIZE_MB", "VIDEO_MAX_CONCURRENT"])
async def test_kiem_ram_video_luat_cheo_co_noi_vao_validate_tuning_cho_ca_hai_o(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """luật chéo có nối vào validateTuning cho CẢ HAI ô

    Editing one field of the pair must still be checked against the other, or changing the parallel runs without
    touching the size bypasses the rule.
    """
    monkeypatch.setattr(tuning, "memory_probe", lambda: float(RAM_2GB))
    sau = {"VIDEO_MAX_SIZE_MB": 2000, "VIDEO_MAX_CONCURRENT": 8}
    loi = validate_tuning(sau)
    assert any("bộ nhớ lúc cao điểm" in item for item in loi), f"đổi {key} phải kích hoạt luật"
