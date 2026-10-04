# ported from: src/agent/trim-context-to-budget.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure function: needs no tuning provider and no env.
"""

from __future__ import annotations

import json
import re

from pema.agent.model_types import ModelMessage
from pema.agent.token_estimate import uoc_luong_token_tin_nhan
from pema.agent.trim_context_to_budget import cat_ngu_canh_theo_ngan_sach


def chu(n: int) -> str:
    return "a" * n


def tin_chu(n: int) -> ModelMessage:
    return {"role": "user", "content": chu(n)}


def tin_co_anh(so_anh: int, chu_dai: int = 20) -> ModelMessage:
    return {
        "role": "user",
        "content": [
            *[{"type": "file", "data": "base64...", "mediaType": "image/jpeg"} for _ in range(so_anh)],
            {"type": "text", "text": chu(chu_dai)},
        ],
    }


def _noi_dung_chuoi(tin: ModelMessage) -> str:
    content = tin["content"]
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


# --- catNguCanhTheoNganSach ----------------------------------------------------------------------------


def test_cat_ngu_canh_theo_ngan_sach_duoi_ngan_sach_thi_khong_dung_gi_tra_dung_mang_cu() -> None:
    """dưới ngân sách thì KHÔNG đụng gì - trả đúng mảng cũ"""
    ds = [tin_chu(100), tin_chu(100), tin_chu(100)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100_000, so_tin_bao_ve_cuoi=1)
    assert r.da_cat is None, "không cắt gì thì da_cat phải là None"
    assert r.tin_nhan is ds, "phải trả về CHÍNH mảng cũ, không sao chép thừa"


def test_cat_ngu_canh_theo_ngan_sach_tran_nho_hon_hoac_bang_0_coi_nhu_tat_tinh_nang_khong_cat() -> None:
    """trần <= 0 coi như tắt tính năng, không cắt"""
    ds = [tin_chu(100_000), tin_chu(100_000)]
    assert cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=0, so_tin_bao_ve_cuoi=1).da_cat is None


def test_cat_ngu_canh_theo_ngan_sach_vuot_vi_anh_thi_bo_anh_truoc_khong_bo_tin() -> None:
    """vượt vì ẢNH thì bỏ ảnh TRƯỚC, không bỏ tin"""
    # 3 images = 2100 tokens, the text is negligible
    ds = [tin_co_anh(3), tin_chu(50), tin_chu(50)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=200, so_tin_bao_ve_cuoi=1)
    assert r.da_cat is not None, "phải có cắt"
    assert r.da_cat.so_anh_bo == 3, "phải bỏ đủ 3 ảnh"
    assert r.da_cat.so_tin_bo == 0, "không được bỏ tin nào khi bỏ ảnh đã đủ"
    assert len(r.tin_nhan) == 3, "vẫn còn đủ 3 tin"


def test_cat_ngu_canh_theo_ngan_sach_bo_anh_van_giu_nguyen_phan_chu_cua_tin_do() -> None:
    """bỏ ảnh vẫn giữ nguyên phần CHỮ của tin đó"""
    ds = [tin_co_anh(2, 40), tin_chu(10)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100, so_tin_bao_ve_cuoi=1)
    text = _noi_dung_chuoi(r.tin_nhan[0])
    assert re.search(r"a{40}", text), "phần chữ của tin có ảnh phải còn nguyên"


def test_cat_ngu_canh_theo_ngan_sach_vuot_vi_chu_thi_bo_tin_cu_nhat_giu_tin_moi() -> None:
    """vượt vì CHỮ thì bỏ tin cũ nhất, giữ tin mới"""
    ds = [tin_chu(5000), tin_chu(5000), tin_chu(100)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=500, so_tin_bao_ve_cuoi=1)
    assert r.da_cat is not None
    assert r.da_cat.so_tin_bo > 0, "phải bỏ tin"
    # The last message (the current turn) must be the one left
    assert r.tin_nhan[-1]["content"] == chu(100)


def test_cat_ngu_canh_theo_ngan_sach_tuyet_doi_khong_cat_tin_cua_luot_hien_tai_ke_ca_khi_cat_het_van_vuot() -> (
    None
):
    """TUYỆT ĐỐI không cắt tin của lượt hiện tại, kể cả khi cắt hết vẫn vượt"""
    # The last message alone already exceeds the ceiling
    ds = [tin_chu(5000), tin_chu(5000), tin_chu(9000)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100, so_tin_bao_ve_cuoi=1)
    assert len(r.tin_nhan) == 1, "chỉ còn đúng vùng được bảo vệ"
    assert r.tin_nhan[0]["content"] == chu(9000), "và đó phải là tin của lượt hiện tại"
    assert uoc_luong_token_tin_nhan(r.tin_nhan) > 100, "vẫn vượt - đúng, thà tràn còn hơn gửi rỗng"


def test_cat_ngu_canh_theo_ngan_sach_bao_ve_nhieu_tin_cuoi_batch_anh_caption_zalo_gui_tach_tin() -> None:
    """bảo vệ nhiều tin cuối (batch ảnh + caption Zalo gửi tách tin)"""
    ds = [tin_chu(9000), tin_chu(9000), tin_chu(30), tin_chu(30), tin_chu(30)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100, so_tin_bao_ve_cuoi=3)
    assert len(r.tin_nhan) == 3, "3 tin cuối đều phải sống sót"


def test_cat_ngu_canh_theo_ngan_sach_khong_bao_gio_tra_mang_rong() -> None:
    """không bao giờ trả mảng rỗng"""
    ds = [tin_chu(9000), tin_chu(9000)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=1, so_tin_bao_ve_cuoi=1)
    assert len(r.tin_nhan) >= 1, "phải còn ít nhất tin của lượt hiện tại"


def test_cat_ngu_canh_theo_ngan_sach_tin_co_anh_ma_bo_het_anh_cung_khong_thanh_content_rong() -> None:
    """tin có ảnh mà bỏ hết ảnh cũng không thành content rỗng"""
    # A message with only an image, no text
    chi_anh: ModelMessage = {
        "role": "user",
        "content": [{"type": "file", "data": "x", "mediaType": "image/jpeg"}],
    }
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=[chi_anh, tin_chu(10)], tran_token=50, so_tin_bao_ve_cuoi=1)
    dau = r.tin_nhan[0]
    assert len(dau["content"]) > 0, "content rỗng bị provider từ chối"


def test_cat_ngu_canh_theo_ngan_sach_khong_cat_giua_mot_tin_khoi_noi_dung_ngoai_phai_nguyen_ven_hoac_mat_hang() -> (
    None
):
    """không cắt GIỮA một tin - khối <noi_dung_ngoai> phải nguyên vẹn hoặc mất hẳn"""
    co_khoi: ModelMessage = {
        "role": "user",
        "content": f'<noi_dung_ngoai nguon="x">{chu(8000)}</noi_dung_ngoai>',
    }
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=[co_khoi, tin_chu(20)], tran_token=100, so_tin_bao_ve_cuoi=1)
    for t in r.tin_nhan:
        s = _noi_dung_chuoi(t)
        mo = len(re.findall(r"<noi_dung_ngoai", s))
        dong = len(re.findall(r"</noi_dung_ngoai>", s))
        assert mo == dong, "số thẻ mở phải bằng số thẻ đóng - không được cắt hở khối"


def cap_tool(id_: str, co_dai: int) -> list[ModelMessage]:
    """A tool-call / tool-result pair in the SDK's shape."""
    return [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool-call",
                    "toolCallId": id_,
                    "toolName": "web_fetch",
                    "input": {"url": f"https://{id_}.vn"},
                }
            ],
        },
        {
            "role": "tool",
            "content": [
                {
                    "type": "tool-result",
                    "toolCallId": id_,
                    "toolName": "web_fetch",
                    "output": {"type": "text", "value": chu(co_dai)},
                }
            ],
        },
    ]


# --- catNguCanhTheoNganSach - KHÔNG để lại tool-result mồ côi ------------------------------------------


def test_cat_ngu_canh_theo_ngan_sach_khong_de_lai_tool_result_mo_coi_cat_giua_mot_cap_tool_thi_bo_luon_phan_tool_result_le_o_dau() -> (
    None
):
    """cắt giữa một cặp tool thì bỏ luôn phần tool-result lẻ ở đầu

    The cut loop goes by INDEX and does not know that assistant(tool-call) must be followed by
    tool(tool-result). Stopping right after dropping an assistant leaves an array that opens with a
    tool-result without its call -> the provider answers 400 and the wrap-up turn dies after burning all
    its steps.
    """
    ds: list[ModelMessage] = [
        tin_chu(40_000),
        *cap_tool("c1", 100_000),
        *cap_tool("c2", 100_000),
        tin_chu(50),
    ]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=40_000, so_tin_bao_ve_cuoi=1, co_anh="normal")
    assert r.tin_nhan[0]["role"] != "tool", f"tool-result mồ côi dẫn đầu: {r.tin_nhan[0]['role']}"


def test_cat_ngu_canh_theo_ngan_sach_khong_de_lai_tool_result_mo_coi_mang_chi_con_tool_result_sau_khi_cat_thi_khong_tra_mang_mo_dau_bang_tool() -> (
    None
):
    """mảng CHỈ còn tool-result sau khi cắt thì không trả mảng mở đầu bằng tool"""
    ds: list[ModelMessage] = [tin_chu(80_000), *cap_tool("c1", 200_000)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=1_000, so_tin_bao_ve_cuoi=1, co_anh="normal")
    # ``tinNhan[0]?.role`` of the original: an EMPTY array passes (``undefined`` is not "tool"). That is what
    # this case really yields: the protected last message is the tool-result itself, and the orphan-tool
    # rule then removes it too. The "never an empty array" invariant is therefore not absolute when the
    # protected zone is a lone tool message (the real caller's last message is a user message). Kept
    # faithful to the original and reported as a finding.
    vai_tro_dau = r.tin_nhan[0]["role"] if r.tin_nhan else None
    assert vai_tro_dau != "tool"


def test_cat_ngu_canh_theo_ngan_sach_khong_de_lai_tool_result_mo_coi_mang_khong_co_tin_tool_nao_thi_khong_dung_gi() -> (
    None
):
    """mảng không có tin tool nào thì không đụng gì (đường buildTurnMessages)"""
    ds = [tin_chu(100_000), tin_chu(100_000), tin_chu(50)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=20_000, so_tin_bao_ve_cuoi=1, co_anh="normal")
    assert len(r.tin_nhan) > 0
    assert r.tin_nhan[-1] is ds[-1], "tin cuối phải còn nguyên"


# --- catNguCanhTheoNganSach - kẹp soTinBaoVeCuoi tối thiểu 1 -------------------------------------------


def test_cat_ngu_canh_theo_ngan_sach_kep_so_tin_bao_ve_cuoi_truyen_0_thi_van_giu_tin_cuoi_khong_bao_gio_tra_mang_rong() -> (
    None
):
    """truyền 0 thì VẪN giữ tin cuối - không bao giờ trả mảng rỗng

    The docstring says this is why the ``max(1, ...)`` clamp exists, but no test ever passed 0: drop the
    clamp and 10/10 stayed green.
    """
    ds = [tin_chu(100_000), tin_chu(100_000), tin_chu(100_000)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100, so_tin_bao_ve_cuoi=0, co_anh="normal")
    assert len(r.tin_nhan) == 1, "phải còn đúng tin cuối"
    assert r.tin_nhan[0] is ds[-1]


def test_cat_ngu_canh_theo_ngan_sach_kep_so_tin_bao_ve_cuoi_truyen_so_am_cung_vay() -> None:
    """truyền số ÂM cũng vậy"""
    ds = [tin_chu(100_000), tin_chu(100_000)]
    r = cat_ngu_canh_theo_ngan_sach(tin_nhan=ds, tran_token=100, so_tin_bao_ve_cuoi=-5, co_anh="normal")
    assert len(r.tin_nhan) == 1
