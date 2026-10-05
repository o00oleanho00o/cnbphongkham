# ported from: evals/eval-assert.test.ts
"""The ONLY test file of ``evals/`` that scores things, and it does NOT touch the network, needs no API key.

``run_eval`` is not a ``test_*`` file so ``pytest`` never reaches it: the "CI needs no network" constraint.

Why test it: ``cham_case`` is the easiest place to be wrong in the whole eval suite and it can NOT be checked
by the suite itself: a real model gives a different result each run so there is no reference. Wrong here and
every case is falsely green, and the reader of the table thinks the agent is doing well.

Test names are the snake_case form of ``describe - it``; the original Vietnamese title is the docstring.
"""

from __future__ import annotations

import re
from dataclasses import replace

from evals.eval_assert import QuanSat, ToolDaGoi, cham_case, phat_hien_luot_hong
from evals.eval_case_type import EvalCase, KiemTraDinhDang, KiemTraText, KiemTraToolArgs, MongDoi
from evals.eval_cases import EVAL_CASES
from evals.eval_formatting_view import DinhDangDaGui, SpanDaGui


def case_goc(mong_doi: MongDoi) -> EvalCase:
    return EvalCase(ten="thu", ly_do="case dựng tay để kiểm bộ chấm", tin_nhan="gì đó", mong_doi=mong_doi)


def qs(**over: object) -> QuanSat:
    return replace(QuanSat(), **over)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------------- goi_tool


def test_cham_case_goi_tool_goi_du_thi_dat() -> None:
    """chamCase - goiTool: gọi đủ thì đạt"""
    kq = cham_case(case_goc(MongDoi(goi_tool=["get_datetime"])), qs(tool_da_goi=["get_datetime"]))
    assert kq.dat is True


def test_cham_case_goi_tool_goi_them_tool_khac_van_dat_mong_doi_la_phai_co() -> None:
    """chamCase - goiTool: gọi THÊM tool khác vẫn đạt - mong đợi là 'phải có', không phải 'chỉ được có'"""
    kq = cham_case(
        case_goc(MongDoi(goi_tool=["get_datetime"])), qs(tool_da_goi=["web_search", "get_datetime"])
    )
    assert kq.dat is True


def test_cham_case_goi_tool_thieu_thi_hong_va_ly_do_phai_ke_ra_da_goi_nhung_gi() -> None:
    """chamCase - goiTool: thiếu thì hỏng, và lý do phải kể ra đã gọi những gì"""
    kq = cham_case(case_goc(MongDoi(goi_tool=["get_datetime"])), qs(tool_da_goi=["web_search"]))
    assert kq.dat is False
    assert re.search(r"get_datetime", kq.ly_do_hong[0])
    assert re.search(r"web_search", kq.ly_do_hong[0]), "phải in ra tool đã gọi để còn chẩn đoán"


def test_cham_case_goi_tool_khong_goi_tool_nao_thi_ly_do_noi_ro_khong_tool_nao() -> None:
    """chamCase - goiTool: không gọi tool nào thì lý do nói rõ 'không tool nào'"""
    kq = cham_case(case_goc(MongDoi(goi_tool=["web_search"])), qs())
    assert re.search(r"không tool nào", kq.ly_do_hong[0])


# ------------------------------------------------------------------------------------------ khong_goi_tool


def test_cham_case_khong_goi_tool_khong_goi_thi_dat() -> None:
    """chamCase - khongGoiTool: không gọi thì đạt"""
    assert cham_case(case_goc(MongDoi(khong_goi_tool=["create_image"])), qs()).dat is True


def test_cham_case_khong_goi_tool_goi_roi_thi_hong() -> None:
    """chamCase - khongGoiTool: gọi rồi thì hỏng"""
    kq = cham_case(case_goc(MongDoi(khong_goi_tool=["create_image"])), qs(tool_da_goi=["create_image"]))
    assert kq.dat is False
    assert re.search(r"create_image", kq.ly_do_hong[0])


# ---------------------------------------------------------------------------------------------- kiem_tra_text


def test_cham_case_kiem_tra_text_dat_thi_thoi_khong_dat_thi_kem_mo_ta_de_nguoi_doc_hieu_vi_sao() -> None:
    """chamCase - kiemTraText: đạt thì thôi, không đạt thì kèm mô tả để người đọc hiểu vì sao"""
    mong_doi = MongDoi(kiem_tra_text=KiemTraText(mo_ta="không chứa hai dấu sao", dat=lambda t: "**" not in t))
    assert cham_case(case_goc(mong_doi), qs(tra_loi="bình thường")).dat is True

    kq = cham_case(case_goc(mong_doi), qs(tra_loi="**đậm**"))
    assert kq.dat is False
    assert re.search(r"không chứa hai dấu sao", kq.ly_do_hong[0])


# ------------------------------------------------------------------------------------------------ luot nem loi


def test_cham_case_luot_nem_loi_provider_chet_thi_hong_khong_phai_khong_goi_tool_nao_nen_dat() -> None:
    """chamCase - lượt ném lỗi: provider chết thì HỎNG, không phải 'không gọi tool nào nên đạt'

    The most dangerous false green: a ``khong_goi_tool`` case would be green exactly when the system is broken,
    because the turn died before it could call any tool."""
    kq = cham_case(
        case_goc(MongDoi(khong_goi_tool=["create_image"])), qs(loi_chay="HTTP 503 Upstream unavailable")
    )
    assert kq.dat is False
    assert re.search(r"503", kq.ly_do_hong[0])


def test_cham_case_luot_nem_loi_nem_loi_thi_dung_luon_khong_cham_tiep_cac_mong_doi_khac() -> None:
    """chamCase - lượt ném lỗi: ném lỗi thì dừng luôn, không chấm tiếp các mong đợi khác"""
    kq = cham_case(
        case_goc(
            MongDoi(
                goi_tool=["a"],
                khong_goi_tool=["b"],
                kiem_tra_text=KiemTraText(mo_ta="x", dat=lambda _t: False),
            )
        ),
        qs(loi_chay="chết"),
    )
    assert len(kq.ly_do_hong) == 1, "một lý do là đủ, thêm nữa chỉ gây nhiễu"


# ------------------------------------------------------------------------------------- phat_hien_luot_hong

CAU_LOI = [
    "Mình đang gặp trục trặc kỹ thuật nên chưa trả lời được tin này, bạn nhắn lại giúp mình sau ít phút nhé.",
    "Phần kết nối của mình đang có vấn đề về cấu hình, mình đã báo lại cho chủ bot. Bạn nhắn lại sau nhé.",
]


def test_phat_hien_luot_hong_cau_bao_loi_he_thong_bi_nhan_ra_la_luot_hong() -> None:
    """phatHienLuotHong - lỗi bắt được ở LẦN CHẠY THẬT ĐẦU TIÊN: câu báo lỗi hệ thống bị nhận ra là lượt hỏng"""
    for cau in CAU_LOI:
        assert phat_hien_luot_hong(tokens=0, tra_loi=cau, cau_loi_he_thong=CAU_LOI)


def test_phat_hien_luot_hong_cau_bao_loi_voi_token_khac_0_van_la_luot_hong_nhanh_rieng() -> None:
    """phatHienLuotHong: câu báo lỗi với token KHÁC 0 vẫn là lượt hỏng - nhánh riêng, không nhờ vế 0 token

    The review round caught this: all three cases passed ``tokens=0`` so the second clause caught them, and
    deleting the error-sentence branch entirely still left 16/16 green. The branch is NOT redundant: the
    prompt-leak guard fires AFTER the real tokens were recorded, so the case it exists for is ``tokens > 0``."""
    assert phat_hien_luot_hong(tokens=5000, tra_loi=CAU_LOI[0], cau_loi_he_thong=CAU_LOI), (
        "token > 0 mà bot trả câu báo lỗi hệ thống thì vẫn là lượt hỏng"
    )


def test_phat_hien_luot_hong_0_token_la_luot_hong_du_cau_tra_loi_trong_binh_thuong() -> None:
    """phatHienLuotHong: 0 token là lượt hỏng dù câu trả lời trông bình thường"""
    assert phat_hien_luot_hong(tokens=0, tra_loi="Hôm nay thứ tư ạ", cau_loi_he_thong=CAU_LOI), (
        "0 token nghĩa là chưa từng gọi được tới model"
    )


def test_phat_hien_luot_hong_luot_chay_that_thi_khong_bi_bao_hong() -> None:
    """phatHienLuotHong: lượt chạy thật thì KHÔNG bị báo hỏng"""
    assert phat_hien_luot_hong(tokens=1234, tra_loi="Hôm nay thứ tư ạ", cau_loi_he_thong=CAU_LOI) is None


def test_phat_hien_luot_hong_ba_case_tung_xanh_gia_luc_router_chet_gio_deu_hong() -> None:
    """phatHienLuotHong: ba case từng XANH GIẢ lúc router chết giờ đều HỎNG

    A rebuild of the very first real run: the router answered 404 for a missing credential, the processor
    swallowed the error and sent the error sentence, and 3 of 5 cases reported PASS: green exactly when the
    system was broken."""
    cau_bao_loi = CAU_LOI[0]
    hong = phat_hien_luot_hong(tokens=0, tra_loi=cau_bao_loi, cau_loi_he_thong=CAU_LOI)
    assert hong

    ba_case = [
        MongDoi(khong_goi_tool=["get_datetime", "web_search"]),  # khong-tra-thua
        MongDoi(  # cong-cu-hep
            khong_goi_tool=["create_image"],
            kiem_tra_text=KiemTraText(mo_ta="dài hơn 10 ký tự", dat=lambda t: len(t.strip()) >= 10),
        ),
        MongDoi(  # dinh-dang
            kiem_tra_text=KiemTraText(mo_ta="không markdown", dat=lambda t: "**" not in t)
        ),
    ]
    for mong_doi in ba_case:
        khong_co_guard = cham_case(case_goc(mong_doi), qs(tra_loi=cau_bao_loi))
        assert khong_co_guard.dat is True, "dựng lại đúng ca xanh giả - không có guard thì nó ĐẠT"

        co_guard = cham_case(case_goc(mong_doi), qs(tra_loi=cau_bao_loi, loi_chay=hong))
        assert co_guard.dat is False, "có guard thì phải HỎNG"


# ------------------------------------------------------------------------------------------ case rong


def test_cham_case_case_rong_mong_doi_case_khong_khai_mong_doi_nao_bi_coi_la_hong_khong_phai_dat() -> None:
    """chamCase - case rỗng mong đợi: case không khai mong đợi nào bị coi là HỎNG, không phải đạt

    A case that is always green only makes the result table look fuller than it is."""
    kq = cham_case(case_goc(MongDoi()), qs())
    assert kq.dat is False
    assert re.search(r"vô nghĩa", kq.ly_do_hong[0])


# --------------------------------------------------------------------------------------------- bo case that


def test_bo_case_that_moi_case_deu_co_ly_do_ton_tai_va_it_nhat_mot_mong_doi() -> None:
    """bộ case thật: mọi case đều có lý do tồn tại và ít nhất một mong đợi"""
    assert len(EVAL_CASES) > 0
    for c in EVAL_CASES:
        assert len(c.ly_do.strip()) >= 40, f'case "{c.ten}" thiếu lý do tử tế'
        assert len(c.tin_nhan.strip()) > 0, f'case "{c.ten}" không có tin nhắn'
        kq = cham_case(c, qs(tra_loi=""))
        assert all("vô nghĩa" not in ly for ly in kq.ly_do_hong), f'case "{c.ten}" không khai mong đợi nào'


def test_bo_case_that_ten_case_khong_trung_nhau() -> None:
    """bộ case thật: tên case không trùng nhau"""
    ten = [c.ten for c in EVAL_CASES]
    assert len(set(ten)) == len(ten)


def test_bo_case_that_co_dung_17_kich_ban_goc_cua_zalo_agent() -> None:
    """bộ case thật: (thêm ở bản port) đủ 17 kịch bản gốc, đúng tên và đúng thứ tự nhóm"""
    assert [c.ten for c in EVAL_CASES] == [
        "gio-chinh-xac",
        "ngay-co-san",
        "tin-tuc-phai-mo-bai",
        "tra-cuu",
        "khong-tra-thua",
        "cong-cu-hep",
        "hoi-lai-khi-thieu",
        "khong-hoi-van",
        "hoi-gop-mot-lan",
        "dinh-dang",
        "dan-vao-thi-hoi-lai",
        "danh-sach-de-luot-mat",
        "luat-thang-lich-su-cu",
        "tro-chuyen-thi-dung-trang-tri",
        "thu-moi-khi-duoc-nho",
        "nho-chu-dong",
        "dinh-chinh-thi-sua",
    ]


# ---------------------------------------------------------------------------------------- kiem_tra_dinh_dang


def _dd(span: list[tuple[str, str]]) -> DinhDangDaGui:
    return DinhDangDaGui(span=[SpanDaGui(st=st, chu=chu, tin=1) for st, chu in span], so_tin=1)


CASE_DINH_DANG = case_goc(
    MongDoi(
        kiem_tra_dinh_dang=KiemTraDinhDang(
            mo_ta="phải có ít nhất 2 chỗ in đậm",
            dat=lambda d: sum(1 for s in d.span if s.st == "b") >= 2,
        )
    )
)


def test_cham_case_kiem_tra_dinh_dang_du_dinh_dang_thi_dat() -> None:
    """chamCase - kiemTraDinhDang: đủ định dạng thì đạt"""
    kq = cham_case(CASE_DINH_DANG, qs(dinh_dang=_dd([("b", "Tra cứu web"), ("b", "Đọc ảnh")])))
    assert kq.dat is True


def test_cham_case_kiem_tra_dinh_dang_thieu_dinh_dang_thi_hong() -> None:
    """chamCase - kiemTraDinhDang: thiếu định dạng thì HỎNG"""
    kq = cham_case(CASE_DINH_DANG, qs(dinh_dang=_dd([("b", "chỉ một chỗ")])))
    assert kq.dat is False
    assert re.search(r"Định dạng không đạt", " ".join(kq.ly_do_hong))


def test_cham_case_kiem_tra_dinh_dang_khong_co_du_lieu_dinh_dang_thi_cham_hong_tuyet_doi_khong_bo_qua() -> (
    None
):
    """chamCase - kiemTraDinhDang: KHÔNG có dữ liệu định dạng thì chấm HỎNG, tuyệt đối không bỏ qua

    Skipping silently is exactly the false green this suite exists to stop: a case claiming to measure
    formatting while measuring nothing, then reporting PASS."""
    kq = cham_case(CASE_DINH_DANG, qs())
    assert kq.dat is False
    assert re.search(r"không cung cấp", " ".join(kq.ly_do_hong))


# ------------------------------------------------------------------------------------- goi_tool_it_nhat
# ``goi_tool`` compares sets so it only answers "was it called". Reading ONE article versus THREE is the
# difference between a digest with its own source per item and one with a single shared source line: exactly
# what the user complained about on 06/08/2026.


def test_cham_case_goi_tool_it_nhat_du_so_lan_thi_dat() -> None:
    """chamCase - goiToolItNhat: đủ số lần thì đạt"""
    kq = cham_case(
        case_goc(MongDoi(goi_tool_it_nhat={"web_fetch": 2})),
        qs(tool_da_goi=["web_search", "web_fetch", "web_fetch"]),
    )
    assert kq.dat is True


def test_cham_case_goi_tool_it_nhat_goi_nhieu_hon_van_dat_day_la_san_khong_phai_tran() -> None:
    """chamCase - goiToolItNhat: gọi NHIỀU HƠN vẫn đạt - đây là sàn, không phải trần"""
    kq = cham_case(
        case_goc(MongDoi(goi_tool_it_nhat={"web_fetch": 2})),
        qs(tool_da_goi=["web_fetch", "web_fetch", "web_fetch"]),
    )
    assert kq.dat is True


def test_cham_case_goi_tool_it_nhat_thieu_mot_lan_la_hong_day_la_cho_goi_tool_mu() -> None:
    """chamCase - goiToolItNhat: THIẾU một lần là hỏng - đây là chỗ goiTool mù"""
    kq = cham_case(
        case_goc(MongDoi(goi_tool_it_nhat={"web_fetch": 2})),
        qs(tool_da_goi=["web_search", "web_fetch"]),
    )
    assert kq.dat is False
    assert re.search(r"ít nhất 2 lần, thực tế 1 lần", " ".join(kq.ly_do_hong))


def test_cham_case_goi_tool_it_nhat_khong_goi_lan_nao_cung_hong() -> None:
    """chamCase - goiToolItNhat: không gọi lần nào cũng hỏng"""
    kq = cham_case(case_goc(MongDoi(goi_tool_it_nhat={"web_fetch": 1})), qs(tool_da_goi=["web_search"]))
    assert kq.dat is False


def test_cham_case_goi_tool_it_nhat_case_chi_khai_goi_tool_it_nhat_van_la_case_co_mong_doi() -> None:
    """chamCase - goiToolItNhat: case CHỈ khai goiToolItNhat vẫn là case có mong đợi - không bị coi là rỗng

    Forgetting to relax the "empty case" guard would report a valid case as meaningless."""
    kq = cham_case(case_goc(MongDoi(goi_tool_it_nhat={"web_fetch": 1})), qs(tool_da_goi=["web_fetch"]))
    assert kq.dat is True
    assert len(kq.ly_do_hong) == 0


# ------------------------------------------------------------------------------------ kiem_tra_tool_args
# (Not in the original test file, which left ``kiemTraToolArgs`` untested: its two memory cases depend on it.)


def test_cham_case_kiem_tra_tool_args_dat_khi_co_it_nhat_mot_loi_goi_dung() -> None:
    """chamCase - kiemTraToolArgs: đạt khi CÓ ÍT NHẤT MỘT lời gọi đúng (thêm ở bản port)"""
    mong_doi = MongDoi(
        goi_tool=["save_memory"],
        kiem_tra_tool_args=KiemTraToolArgs(
            tool="save_memory", mo_ta="action sua", dat=lambda i: '"action":"sua"' in i
        ),
    )
    goi = [
        ToolDaGoi(name="save_memory", input='{"action":"them"}'),
        ToolDaGoi(name="save_memory", input='{"action":"sua"}'),
    ]
    kq = cham_case(
        case_goc(mong_doi), qs(tool_da_goi=["save_memory", "save_memory"], tool_da_goi_kem_args=goi)
    )
    assert kq.dat is True

    sai = cham_case(case_goc(mong_doi), qs(tool_da_goi=["save_memory"], tool_da_goi_kem_args=goi[:1]))
    assert sai.dat is False
    assert re.search(r"đã gọi với", " ".join(sai.ly_do_hong))


def test_cham_case_kiem_tra_tool_args_khong_goi_tool_do_lan_nao_thi_hong() -> None:
    """chamCase - kiemTraToolArgs: không gọi tool đó lần nào thì hỏng (thêm ở bản port)"""
    mong_doi = MongDoi(kiem_tra_tool_args=KiemTraToolArgs(tool="save_memory", mo_ta="x", dat=lambda _i: True))
    kq = cham_case(case_goc(mong_doi), qs())
    assert kq.dat is False
    assert re.search(r"không gọi lần nào", " ".join(kq.ly_do_hong))
