# ported from: src/agent/tool-loop-guard.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module: no env, no DB.

``ket_qua_loi`` of ``tools/tool-failure-result.ts`` belongs to package D4 and is not on this branch; the
local helper builds the same ``{"ok": False, "loi": <text>}`` shape that ``la_ket_qua_loi`` recognises.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from pema.agent.model_types import RawStep, StepContentPart, ToolResultPart
from pema.agent.tool_loop_guard import (
    NguongGuard,
    ToolLoopGuard,
    canh_bao_tu,
    chu_ky_lenh_goi,
    nguong_theo_tran_step,
)

NGUONG = NguongGuard(chan_loi_giong_het=5, chan_cung_tool_loi=8, chan_khong_tien_trien=5)


def la_tool_chi_doc(t: str) -> bool:
    """Only ``web_search`` and ``web_fetch`` are read tools in the tests below."""
    return t in ("web_search", "web_fetch")


@pytest.fixture
def guard() -> ToolLoopGuard:
    return ToolLoopGuard(NGUONG, la_tool_chi_doc)


def ket_qua_loi(thong_diep: str) -> dict[str, Any]:
    return {"ok": False, "loi": thong_diep}


def buoc_loi(tool_name: str, input_: object) -> RawStep:
    """A step with only a FAILED tool: the failure sits in ``content``, NOT in ``tool_results``."""
    return RawStep(
        content=[StepContentPart(type="tool-error", tool_name=tool_name, input=input_)], tool_results=[]
    )


def buoc_xong(tool_name: str, input_: object, output: object) -> RawStep:
    """A step whose tool ran to completion and returned a result."""
    return RawStep(
        content=[StepContentPart(type="text")],
        tool_results=[ToolResultPart(tool_name=tool_name, input=input_, output=output)],
    )


# --- chuKyLenhGoi --------------------------------------------------------------------------------------


def test_chu_ky_lenh_goi_cung_tham_so_nhung_khac_thu_tu_khoa_van_ra_mot_chu_ky() -> None:
    """cùng tham số nhưng khác THỨ TỰ khóa vẫn ra một chữ ký"""
    assert chu_ky_lenh_goi("web_fetch", {"url": "https://a.test", "timeout": 5}) == chu_ky_lenh_goi(
        "web_fetch", {"timeout": 5, "url": "https://a.test"}
    )


def test_chu_ky_lenh_goi_sap_khoa_o_moi_cap_khong_chi_cap_ngoai_cung() -> None:
    """sắp khóa ở MỌI cấp, không chỉ cấp ngoài cùng"""
    assert chu_ky_lenh_goi("t", {"a": {"x": 1, "y": 2}}) == chu_ky_lenh_goi("t", {"a": {"y": 2, "x": 1}})


def test_chu_ky_lenh_goi_khac_tham_so_thi_khac_chu_ky_khac_tool_cung_khac() -> None:
    """khác tham số thì khác chữ ký; khác tool cũng khác"""
    assert chu_ky_lenh_goi("t", {"url": "a"}) != chu_ky_lenh_goi("t", {"url": "b"})
    assert chu_ky_lenh_goi("t1", {"url": "a"}) != chu_ky_lenh_goi("t2", {"url": "a"})


def test_chu_ky_lenh_goi_khong_giu_tham_so_tho_chu_ky_khong_chua_noi_dung_nguoi_dung() -> None:
    """KHÔNG giữ tham số thô - chữ ký không chứa nội dung người dùng"""
    ck = chu_ky_lenh_goi("web_fetch", {"url": "https://bi-mat.test/tai-lieu-rieng"})
    assert "bi-mat" not in ck, f"chữ ký lộ tham số: {ck}"
    assert "tai-lieu-rieng" not in ck


def test_chu_ky_lenh_goi_tham_so_rong_undefined_khong_phai_object_khong_lam_vo() -> None:
    """tham số rỗng / undefined / không phải object không làm vỡ"""
    assert chu_ky_lenh_goi("t", None) == chu_ky_lenh_goi("t", {})
    assert len(chu_ky_lenh_goi("t", "chuoi")) > 0
    assert len(chu_ky_lenh_goi("t", 123)) > 0
    assert len(chu_ky_lenh_goi("t", None)) > 0


# --- ToolLoopGuard - lỗi giống hệt ---------------------------------------------------------------------


def test_tool_loop_guard_loi_giong_het_4_lan_loi_giong_het_thi_chua_chan_lan_5_moi_chan(
    guard: ToolLoopGuard,
) -> None:
    """4 lần lỗi giống hệt thì chưa chặn, lần 5 mới chặn"""
    b = buoc_loi("web_fetch", {"url": "https://hong.test"})
    for i in range(1, 5):
        assert guard.ghi_nhan(b).muc != "chan", f"lần {i} không được chặn"
        assert guard.da_chan() is False
    q = guard.ghi_nhan(b)
    assert q.muc == "chan"
    assert q.ma == "loi-giong-het"
    assert q.so_lan == 5
    assert guard.da_chan() is True


def test_tool_loop_guard_loi_giong_het_canh_bao_tu_lan_thu_2_truoc_khi_chan(guard: ToolLoopGuard) -> None:
    """cảnh báo từ lần thứ 2, trước khi chặn"""
    b = buoc_loi("web_fetch", {"url": "x"})
    assert guard.ghi_nhan(b).muc == "cho-qua", "lần đầu lỗi là chuyện thường"
    assert guard.ghi_nhan(b).muc == "canh-bao"


def test_tool_loop_guard_loi_giong_het_quyet_dinh_chan_la_dinh_step_sau_van_bao_da_chan(
    guard: ToolLoopGuard,
) -> None:
    """quyết định chặn là DÍNH - step sau vẫn báo đã chặn"""
    b = buoc_loi("web_fetch", {"url": "x"})
    for _ in range(5):
        guard.ghi_nhan(b)
    assert guard.da_chan() is True
    guard.ghi_nhan(buoc_xong("get_datetime", {}, "ok"))
    assert guard.da_chan() is True, "một step thành công không gỡ được lệnh chặn"


def test_tool_loop_guard_loi_giong_het_loi_voi_tham_so_khac_nhau_khong_don_vao_bo_dem_giong_het(
    guard: ToolLoopGuard,
) -> None:
    """lỗi với THAM SỐ KHÁC nhau không dồn vào bộ đếm giống hệt"""
    for i in range(5):
        guard.ghi_nhan(buoc_loi("web_fetch", {"url": f"https://khac-{i}.test"}))
    # Assert the STATE, not only the code. The first version compared ``ly_do_chan()?.ma !=
    # "loi-giong-het"`` - and then ``ly_do_chan()`` was null so the left side was ``undefined``, and the
    # sentence was green even when the counters were merged completely wrong.
    assert guard.da_chan() is False, "5 URL khác nhau chưa chạm ngưỡng nào"

    # And prove the same-parameters counter really still has room. Use ANOTHER TOOL for this part: the 5
    # failures just now already loaded 5 into web_fetch's same-tool counter, so 3 more would be blocked by
    # THAT counter (threshold 8) and not the same-parameters one - measuring on web_fetch measures the
    # wrong counter.
    b = buoc_loi("web_search", {"q": "một câu duy nhất"})
    for i in range(1, 5):
        assert guard.ghi_nhan(b).muc != "chan", f"lần {i} với tham số mới chưa được chặn"
    assert guard.ghi_nhan(b).ma == "loi-giong-het"


# --- ToolLoopGuard - cùng tool lỗi nhiều lần -----------------------------------------------------------


def test_tool_loop_guard_cung_tool_loi_8_lan_loi_cung_tool_khac_tham_so_thi_chan(
    guard: ToolLoopGuard,
) -> None:
    """8 lần lỗi cùng tool khác tham số thì chặn"""
    for i in range(1, 8):
        guard.ghi_nhan(buoc_loi("web_fetch", {"url": f"https://k{i}.test"}))
    assert guard.da_chan() is False, "7 lần chưa chặn"
    q = guard.ghi_nhan(buoc_loi("web_fetch", {"url": "https://k8.test"}))
    assert q.muc == "chan"
    assert q.ma == "cung-tool-loi"


def test_tool_loop_guard_cung_tool_loi_hai_tool_khac_nhau_dem_rieng_khong_cong_don(
    guard: ToolLoopGuard,
) -> None:
    """hai tool khác nhau đếm riêng, không cộng dồn"""
    for i in range(7):
        guard.ghi_nhan(buoc_loi("web_fetch", {"url": f"a{i}"}))
        guard.ghi_nhan(buoc_loi("web_search", {"q": f"b{i}"}))
    assert guard.da_chan() is False, "mỗi tool mới 7 lần, chưa tool nào chạm 8"


# --- ToolLoopGuard - tool đọc không tiến triển ---------------------------------------------------------


def test_tool_loop_guard_khong_tien_trien_tool_doc_tra_cung_ket_qua_5_lan_thi_chan(
    guard: ToolLoopGuard,
) -> None:
    """tool ĐỌC trả cùng kết quả 5 lần thì chặn"""
    b = buoc_xong("web_search", {"q": "giá vàng"}, "kết quả y hệt")
    for _ in range(1, 5):
        assert guard.ghi_nhan(b).muc != "chan"
    q = guard.ghi_nhan(b)
    assert q.muc == "chan"
    assert q.ma == "khong-tien-trien"


def test_tool_loop_guard_khong_tien_trien_tool_ghi_tra_cung_ket_qua_5_lan_thi_khong_chan_ghi_lap_la_hop_le(
    guard: ToolLoopGuard,
) -> None:
    """tool GHI trả cùng kết quả 5 lần thì KHÔNG chặn - ghi lặp là hợp lệ"""
    b = buoc_xong("send_file", {"path": "a.pdf"}, "đã gửi")
    for _ in range(6):
        guard.ghi_nhan(b)
    assert guard.da_chan() is False, "gửi 2 file giống nhau là chuyện bình thường"


def test_tool_loop_guard_khong_tien_trien_ket_qua_doi_thi_dem_ve_1_khong_tich_luy(
    guard: ToolLoopGuard,
) -> None:
    """kết quả ĐỔI thì đếm về 1, không tích lũy"""
    args = {"q": "tin mới"}
    for _ in range(4):
        guard.ghi_nhan(buoc_xong("web_search", args, "kết quả cũ"))
    guard.ghi_nhan(buoc_xong("web_search", args, "KẾT QUẢ MỚI"))
    assert guard.da_chan() is False, "có tiến triển thì đếm phải reset"
    for _ in range(3):
        guard.ghi_nhan(buoc_xong("web_search", args, "KẾT QUẢ MỚI"))
    assert guard.da_chan() is False, "mới 4 lần với kết quả mới"


def test_tool_loop_guard_khong_tien_trien_cung_tool_nhung_tham_so_khac_thi_dem_rieng(
    guard: ToolLoopGuard,
) -> None:
    """cùng tool nhưng tham số khác thì đếm riêng"""
    for _ in range(4):
        guard.ghi_nhan(buoc_xong("web_search", {"q": "a"}, "kq"))
    for _ in range(4):
        guard.ghi_nhan(buoc_xong("web_search", {"q": "b"}, "kq"))
    assert guard.da_chan() is False


# --- ToolLoopGuard - nguồn dữ liệu và vòng đời ---------------------------------------------------------


def test_tool_loop_guard_nguon_du_lieu_loi_nam_o_content_tool_error_van_duoc_dem_du_tool_results_rong(
    guard: ToolLoopGuard,
) -> None:
    """lỗi nằm ở content[tool-error] vẫn được đếm dù toolResults RỖNG

    The easiest case to miss: a tool that throws never lands in ``tool_results``. Reading only
    ``tool_results`` makes the guard completely blind to real errors.
    """
    b = RawStep(
        tool_results=[],
        content=[StepContentPart(type="tool-error", tool_name="web_fetch", input={"url": "x"})],
    )
    for _ in range(5):
        guard.ghi_nhan(b)
    assert guard.da_chan() is True


def test_tool_loop_guard_nguon_du_lieu_step_khong_co_tool_nao_khong_lam_vo(guard: ToolLoopGuard) -> None:
    """step không có tool nào không làm vỡ"""
    assert guard.ghi_nhan(RawStep()).muc == "cho-qua"
    assert guard.ghi_nhan(RawStep(content=[StepContentPart(type="text")], tool_results=[])).muc == "cho-qua"


def test_tool_loop_guard_nguon_du_lieu_dat_lai_xoa_sach_ca_bo_dem_lan_lenh_chan(guard: ToolLoopGuard) -> None:
    """datLai xóa sạch cả bộ đếm lẫn lệnh chặn"""
    b = buoc_loi("web_fetch", {"url": "x"})
    for _ in range(5):
        guard.ghi_nhan(b)
    assert guard.da_chan() is True

    guard.dat_lai()
    assert guard.da_chan() is False
    assert guard.ly_do_chan() is None
    assert guard.ghi_nhan(b).muc == "cho-qua", "đếm phải về 0, không phải tiếp tục từ 5"


def test_tool_loop_guard_nguon_du_lieu_luot_binh_thuong_khong_bao_gio_dinh(guard: ToolLoopGuard) -> None:
    """lượt bình thường (mỗi tool một lần, không lỗi) không bao giờ dính"""
    guard.ghi_nhan(buoc_xong("get_datetime", {}, "2026-08-02"))
    guard.ghi_nhan(buoc_xong("web_search", {"q": "giá vàng"}, "kq A"))
    guard.ghi_nhan(buoc_xong("web_fetch", {"url": "https://a.test"}, "nội dung A"))
    guard.ghi_nhan(buoc_xong("web_fetch", {"url": "https://b.test"}, "nội dung B"))
    assert guard.da_chan() is False


def test_tool_loop_guard_nguon_du_lieu_mot_step_co_nhieu_tool_thi_tra_quyet_dinh_nghiem_trong_nhat() -> None:
    """một step có NHIỀU tool thì trả quyết định nghiêm trọng nhất

    The step must hold TWO parts producing decisions of different levels to measure the choice of the
    heavier one. The first version paired a failed part with ``get_datetime`` (a WRITE tool, always passes)
    so there was only one candidate - green even if the function picked the last element at random.
    """
    g = ToolLoopGuard(
        NguongGuard(chan_loi_giong_het=2, chan_cung_tool_loi=8, chan_khong_tien_trien=2), la_tool_chi_doc
    )

    # Load one failure first so the next recording of web_fetch reaches the block threshold
    g.ghi_nhan(buoc_loi("web_fetch", {"url": "x"}))

    q = g.ghi_nhan(
        RawStep(
            # The order deliberately puts the LIGHT part before the HEAVY one: taking the first element is exposed
            content=[StepContentPart(type="text")],
            tool_results=[
                ToolResultPart(tool_name="web_search", input={"q": "a"}, output="kq"),
                ToolResultPart(
                    tool_name="web_fetch", input={"url": "x"}, output={"ok": False, "loi": "hỏng"}
                ),
            ],
        )
    )
    assert q.muc == "chan", "phần chặn phải thắng phần cho-qua dù đứng sau"
    assert q.tool == "web_fetch"

    # The other direction: a warning must beat pass-through
    g2 = ToolLoopGuard(
        NguongGuard(chan_loi_giong_het=4, chan_cung_tool_loi=8, chan_khong_tien_trien=5), la_tool_chi_doc
    )
    g2.ghi_nhan(buoc_loi("web_fetch", {"url": "y"}))
    q2 = g2.ghi_nhan(
        RawStep(
            tool_results=[
                ToolResultPart(tool_name="get_datetime", input={}, output="ok"),
                ToolResultPart(
                    tool_name="web_fetch", input={"url": "y"}, output={"ok": False, "loi": "hỏng"}
                ),
            ]
        )
    )
    assert q2.muc == "canh-bao"


# --- ToolLoopGuard - kết quả ĐÁNH DẤU HỎNG được đếm như lỗi --------------------------------------------
# This is the MAIN class of error of the repo, not a rare case: no tool throws (every failure branch is
# ``ket_qua_loi(...)``), so if the guard only counted ``content[tool-error]`` two of the three counters
# would be dead code.


def buoc_hong(tool_name: str, input_: object, cau: str = "hỏng") -> RawStep:
    return buoc_xong(tool_name, input_, ket_qua_loi(cau))


def test_tool_loop_guard_ket_qua_danh_dau_hong_8_url_khac_nhau_cung_hong_thi_chan_ca_dat_nhat_truoc_day_guard_cam(
    guard: ToolLoopGuard,
) -> None:
    """8 URL KHÁC NHAU cùng hỏng thì chặn - ca đắt nhất, trước đây guard câm"""
    for i in range(1, 8):
        guard.ghi_nhan(buoc_hong("web_fetch", {"url": f"https://hong-{i}.test"}))
    assert guard.da_chan() is False, "7 lần chưa chạm ngưỡng 8"
    q = guard.ghi_nhan(buoc_hong("web_fetch", {"url": "https://hong-8.test"}))
    assert q.muc == "chan"
    assert q.ma == "cung-tool-loi"


def test_tool_loop_guard_ket_qua_danh_dau_hong_cung_mot_tham_so_hong_5_lan_vao_bo_dem_giong_het_khong_phai_khong_tien_trien(
    guard: ToolLoopGuard,
) -> None:
    """CÙNG một tham số hỏng 5 lần thì vào bộ đếm giống-hệt, KHÔNG phải không-tiến-triển

    Misclassifying here is not just an ugly label: the diagnosis of "khong-tien-trien" is "returned the
    same result, calling more brings nothing new" - read as if the page were alive and merely dull, while
    it is dying.
    """
    b = buoc_hong("web_fetch", {"url": "https://chet.test"})
    for _ in range(5):
        guard.ghi_nhan(b)
    ly = guard.ly_do_chan()
    assert ly is not None
    assert ly.ma == "loi-giong-het"
    assert re.search(r"lỗi 5 lần", ly.thong_diep)


def test_tool_loop_guard_ket_qua_danh_dau_hong_web_search_rong_8_tu_khoa_khac_nhau_cung_chan(
    guard: ToolLoopGuard,
) -> None:
    """web_search rỗng 8 từ khóa khác nhau cũng chặn"""
    for i in range(1, 9):
        guard.ghi_nhan(buoc_hong("web_search", {"q": f"từ khóa {i}"}, "Không tìm thấy kết quả nào"))
    ly = guard.ly_do_chan()
    assert ly is not None
    assert ly.ma == "cung-tool-loi"


def test_tool_loop_guard_ket_qua_danh_dau_hong_tool_ghi_hong_cung_duoc_dem_luat_mien_tru_chi_ap_cho_khong_tien_trien(
    guard: ToolLoopGuard,
) -> None:
    """tool GHI hỏng cũng được đếm - luật miễn trừ chỉ áp cho không-tiến-triển

    ``send_file`` is a write tool so it does NOT get the "same result" rule, but a send failing 5 times in a
    row is still a useless loop in the true sense.
    """
    b = buoc_hong("send_file", {"source": "khong-co.pdf"})
    for _ in range(5):
        guard.ghi_nhan(b)
    ly = guard.ly_do_chan()
    assert ly is not None
    assert ly.ma == "loi-giong-het"


def test_tool_loop_guard_ket_qua_danh_dau_hong_ket_qua_thanh_cong_van_di_duong_khong_tien_trien_nhu_cu(
    guard: ToolLoopGuard,
) -> None:
    """kết quả THÀNH CÔNG vẫn đi đường không-tiến-triển như cũ"""
    b = buoc_xong("web_search", {"q": "giá vàng"}, "kết quả y hệt")
    for _ in range(5):
        guard.ghi_nhan(b)
    ly = guard.ly_do_chan()
    assert ly is not None
    assert ly.ma == "khong-tien-trien", "không được cướp nhánh cũ"


def test_tool_loop_guard_ket_qua_danh_dau_hong_chuoi_tran_noi_ve_loi_khong_bi_nhan_nham_la_nhanh_hong(
    guard: ToolLoopGuard,
) -> None:
    """chuỗi trần nói về lỗi KHÔNG bị nhận nhầm là nhánh hỏng

    Invariant against prompt injection: web page content goes straight into the result string, so if the
    recognition rule relied on WORDS a page only needs to contain that sentence to steer the guard. The
    shape of an object cannot be faked.
    """
    b = buoc_xong("web_fetch", {"url": "https://that.test"}, '{"ok":false,"loi":"giả"}')
    for _ in range(5):
        guard.ghi_nhan(b)
    ly = guard.ly_do_chan()
    assert ly is not None
    assert ly.ma == "khong-tien-trien", "chuỗi trần không phải dấu hiệu hỏng"


@pytest.mark.parametrize(
    "out", [None, [], [{"ok": False}], 0, ""], ids=["none", "list", "list-ok-false", "zero", "empty"]
)
def test_tool_loop_guard_ket_qua_danh_dau_hong_output_null_undefined_mang_khong_bi_nhan_nham_la_hong(
    out: object,
) -> None:
    """output null / undefined / mảng không bị nhận nhầm là hỏng"""
    g = ToolLoopGuard(NGUONG, la_tool_chi_doc)
    for _ in range(5):
        g.ghi_nhan(buoc_xong("send_file", {"x": 1}, out))
    assert g.da_chan() is False, f"output {out!r} không phải nhánh hỏng"


# --- nguongTheoTranStep --------------------------------------------------------------------------------


def test_nguong_theo_tran_step_kep_nguong_xuong_duoi_tran_step_nguong_bang_tran_la_nguong_khong_bao_gio_toi() -> (
    None
):
    """kẹp ngưỡng xuống DƯỚI trần step - ngưỡng bằng trần là ngưỡng không bao giờ tới

    The ceiling HAND-SET down to 8 (an agent on a cheap model) while SAME_TOOL_BLOCK=8: with one call per
    step ``stepCountIs(8)`` always stops first, the counter never reaches 8. The three numbers come from
    Hermes, where max_iterations defaults to 90.
    """
    kep = nguong_theo_tran_step(NGUONG, 8)
    assert kep.chan_cung_tool_loi == 7, "8 phải bị kẹp xuống dưới trần"
    assert kep.chan_loi_giong_het == 5, "5 đã dưới trần thì giữ nguyên"
    assert kep.chan_khong_tien_trien == 5


def test_nguong_theo_tran_step_voi_tran_mac_dinh_10_thi_khong_so_nao_bi_kep_ca_ba_tu_no_duoc() -> None:
    """với trần MẶC ĐỊNH 10 thì không số nào bị kẹp - cả ba tự nổ được

    Since 06/08/2026 the default ceiling is 10, so the threshold 8 already sits below it. This test is the
    alarm if someone lowers the default back to 8 forgetting that the threshold 8 then turns into a dead
    threshold again.
    """
    assert nguong_theo_tran_step(NGUONG, 10) == NGUONG


def test_nguong_theo_tran_step_tran_step_rong_thi_giu_nguyen_dung_ba_so_cua_hermes() -> None:
    """trần step rộng thì giữ nguyên đúng ba số của Hermes"""
    assert nguong_theo_tran_step(NGUONG, 30) == NGUONG


def test_nguong_theo_tran_step_san_2_tran_step_qua_thap_cung_khong_kep_xuong_1() -> None:
    """sàn 2 - trần step quá thấp cũng không kẹp xuống 1 (chặn ngay lần lỗi đầu là quá tay)"""
    kep = nguong_theo_tran_step(NGUONG, 1)
    assert kep.chan_loi_giong_het == 2
    assert kep.chan_cung_tool_loi == 2
    assert kep.chan_khong_tien_trien == 2


def test_nguong_theo_tran_step_nguong_da_kep_that_su_no_duoc_trong_pham_vi_tran_step() -> None:
    """ngưỡng đã kẹp thật sự nổ được trong phạm vi trần step

    The MOST IMPORTANT test of the group: a clamp that still cannot fire is pointless.
    """
    tran_step = 8
    g = ToolLoopGuard(nguong_theo_tran_step(NGUONG, tran_step), la_tool_chi_doc)
    step = 0
    while step < tran_step and not g.da_chan():
        step += 1
        g.ghi_nhan(buoc_xong("web_fetch", {"url": f"https://k{step}.test"}, ket_qua_loi("hỏng")))
    assert g.da_chan() is True, "phải chặn được TRƯỚC khi đốt hết trần step"
    assert step < tran_step, f"chặn ở step {step}, phải nhỏ hơn trần {tran_step}"


# --- canhBaoTu -----------------------------------------------------------------------------------------


def test_canh_bao_tu_bang_nua_nguong_chan() -> None:
    """bằng nửa ngưỡng chặn"""
    assert canh_bao_tu(8) == 4
    assert canh_bao_tu(5) == 2


def test_canh_bao_tu_khong_bao_gio_nho_hon_2_loi_mot_lan_chua_phai_vong_lap() -> None:
    """không bao giờ nhỏ hơn 2 - lỗi MỘT lần chưa phải vòng lặp"""
    assert canh_bao_tu(1) == 2
    assert canh_bao_tu(2) == 2
    assert canh_bao_tu(3) == 2
