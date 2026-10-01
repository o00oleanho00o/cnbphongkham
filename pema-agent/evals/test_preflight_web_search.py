# ported from: evals/preflight-web-search.test.ts
"""The precondition check born from an hour lost on 06/08/2026: DuckDuckGo returned 0 results, the research case
went red with the reason "did not call web_fetch", and it nearly led to the wrong conclusion that the persona
rule just edited made the model worse.

Test names are the snake_case form of ``describe - it``; the original Vietnamese title is the docstring.
"""

from __future__ import annotations

import re

from evals.eval_case_type import EvalCase, MongDoi
from evals.preflight_web_search import can_tra_cuu_web, kiem_tra_tien_de_tra_cuu


def case_voi(mong_doi: MongDoi) -> EvalCase:
    return EvalCase(ten="x", ly_do="x", tin_nhan="x", mong_doi=mong_doi)


def test_can_tra_cuu_web_nhan_ra_case_phu_thuoc_tra_cuu_qua_goi_tool() -> None:
    """canTraCuuWeb: nhận ra case phụ thuộc tra cứu qua goiTool"""
    assert can_tra_cuu_web(case_voi(MongDoi(goi_tool=["web_search"]))) is True
    assert can_tra_cuu_web(case_voi(MongDoi(goi_tool=["web_fetch"]))) is True


def test_can_tra_cuu_web_nhan_ra_ca_khi_chi_khai_o_goi_tool_it_nhat_bo_sot_la_tien_de_khong_chay() -> None:
    """canTraCuuWeb: nhận ra cả khi chỉ khai ở goiToolItNhat - bỏ sót là tiền đề không chạy"""
    assert can_tra_cuu_web(case_voi(MongDoi(goi_tool_it_nhat={"web_fetch": 2}))) is True


def test_can_tra_cuu_web_case_khong_dung_tra_cuu_thi_khong_bat_cho_tien_de() -> None:
    """canTraCuuWeb: case KHÔNG dùng tra cứu thì không bắt chờ tiền đề"""
    assert can_tra_cuu_web(case_voi(MongDoi(goi_tool=["get_datetime"]))) is False
    assert can_tra_cuu_web(case_voi(MongDoi(khong_goi_tool=["web_search"]))) is False


async def test_kiem_tra_tien_de_tra_cuu_co_ket_qua_thi_cho_chay_tiep() -> None:
    """kiemTraTienDeTraCuu: có kết quả thì cho chạy tiếp"""

    async def tim(_q: str) -> int:
        return 5

    r = await kiem_tra_tien_de_tra_cuu(tim, "brave")
    assert r.ok is True


async def test_kiem_tra_tien_de_tra_cuu_mot_truy_van_rong_chua_du_ket_luan_truy_van_xau_la_chuyen_thuong() -> (
    None
):
    """kiemTraTienDeTraCuu: MỘT truy vấn rỗng chưa đủ kết luận - truy vấn xấu là chuyện thường"""
    lan = 0

    async def tim(_q: str) -> int:
        nonlocal lan
        lan += 1
        return 0 if lan == 1 else 3

    r = await kiem_tra_tien_de_tra_cuu(tim, "brave")
    assert r.ok is True, "một lần rỗng mà đã dừng cả bộ eval là quá tay"


async def test_kiem_tra_tien_de_tra_cuu_moi_truy_van_rong_dung_va_cau_loi_phai_chi_dung_benh() -> None:
    """kiemTraTienDeTraCuu: MỌI truy vấn rỗng -> dừng, và câu lỗi phải chỉ đúng bệnh"""

    async def tim(_q: str) -> int:
        return 0

    r = await kiem_tra_tien_de_tra_cuu(tim, "duckduckgo")
    assert r.ok is False
    assert re.search(r"duckduckgo", r.loi), "phải nói rõ nhà cung cấp nào đang hỏng"
    assert re.search(r"web_fetch", r.loi), "phải cảnh báo trước cái chẩn đoán sai mà người đọc sắp mắc"


async def test_kiem_tra_tien_de_tra_cuu_ham_tim_kiem_nem_cung_tinh_la_rong_loi_mang_khong_duoc_lam_sap_runner() -> (
    None
):
    """kiemTraTienDeTraCuu: hàm tìm kiếm NÉM cũng tính là rỗng - lỗi mạng không được làm sập cả runner"""

    async def tim(_q: str) -> int:
        raise ConnectionResetError("ECONNRESET")

    r = await kiem_tra_tien_de_tra_cuu(tim, "brave")
    assert r.ok is False
