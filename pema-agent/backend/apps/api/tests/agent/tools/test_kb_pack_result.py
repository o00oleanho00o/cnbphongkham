# ported from: src/agent/tools/kb-pack-result.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Test đơn vị cho ``dong_goi_theo_ngan_sach`` - module chưa có test trực tiếp nào trước vòng rà soát lần 3 (chỉ
được kiểm gián tiếp qua ``test_kb_search_tool``, vốn không đủ để phủ hết 3 nhánh + biên).
"""

from __future__ import annotations

import re

from pema.agent.tools.kb_pack_result import KB_PACK_SEPARATOR, dong_goi_theo_ngan_sach


def doan_co_do(i: int, do_dai: int) -> str:
    """Đoạn dài đúng ``do_dai`` ký tự, tiền tố số để phân biệt từng đoạn khi kiểm nội dung."""
    nhan = f"D{i}_"
    return nhan + "x" * max(0, do_dai - len(nhan))


# ------------------------------------------------------------------------------- ba nhánh


def test_ba_nhanh_du_cho_tat_ca_doan_noi_nguyen_ven_khong_nhan_nao() -> None:
    """đủ chỗ cho TẤT CẢ đoạn: nối nguyên vẹn, không nhãn nào"""
    doan = [doan_co_do(0, 50), doan_co_do(1, 50), doan_co_do(2, 50)]
    kq = dong_goi_theo_ngan_sach(doan, 10_000)
    assert kq == KB_PACK_SEPARATOR.join(doan)


def test_ba_nhanh_bo_doan_du_cho_mot_phan_phan_con_lai_bi_bo_han_kem_nhan_dung_so() -> None:
    """bỏ đoạn: đủ chỗ cho MỘT PHẦN, phần còn lại bị bỏ hẳn kèm nhãn ĐÚNG SỐ"""
    # 5 đoạn 1000 ký tự - chọn trần để CHỈ 2 đoạn đầu vừa (2*1000+7=2007), đoạn thứ 3 chắc chắn không vừa
    # (2007+7+1000=3014). Biên 200 ký tự đủ để hấp thụ phần ngân sách bị ``dong_goi_theo_ngan_sach`` tự trừ
    # trước cho câu báo (luôn dưới 100 ký tự với 5 đoạn), không cần biết chính xác số đó.
    doan = [doan_co_do(i, 1000) for i in range(5)]
    kq = dong_goi_theo_ngan_sach(doan, 2207)
    assert doan[0] in kq, "phải còn đoạn 0"
    assert doan[1] in kq, "phải còn đoạn 1"
    assert doan[2] not in kq, "đoạn 2 phải bị bỏ hẳn, không cắt cụt"
    assert doan[3] not in kq
    assert doan[4] not in kq, "đoạn 3, 4 cũng bị bỏ hẳn"
    assert re.search("còn 3 đoạn nữa không đủ chỗ", kq), f"phải báo ĐÚNG 3 đoạn còn lại, thực tế: {kq!r}"


def test_ba_nhanh_cat_doan_dau_ngay_ca_doan_dau_cung_khong_vua_cat_o_khoang_trang_khong_tra_rong() -> None:
    """cắt đoạn đầu: ngay cả đoạn đầu cũng không vừa - cắt ở ranh giới khoảng trắng, không trả rỗng"""
    doan = [doan_co_do(0, 5000)]
    kq = dong_goi_theo_ngan_sach(doan, 500)
    assert len(kq) > 0, "không được trả rỗng"
    assert re.search("đã rút gọn", kq), "phải ghi rõ đã rút gọn"
    assert doan[0] not in kq, "không được chứa nguyên văn đoạn gốc (phải bị cắt thật)"
    # Chốt BIÊN ``con_lai > 1`` (khoảng trống vòng rà soát cuối): đoạn đầu bị cắt mà KHÔNG còn đoạn nào phía sau
    # thì TUYỆT ĐỐI không được báo "còn N đoạn". Đổi ``con_lai > 1`` thành ``con_lai >= 1`` (lệch một) - model
    # sẽ đọc "còn 0 đoạn nữa không đủ chỗ", vừa sai vừa khó hiểu.
    assert not re.search(r"còn \d+ đoạn", kq), f"chỉ có ĐÚNG 1 đoạn, không được báo còn đoạn nào: {kq!r}"


def test_ba_nhanh_cat_doan_dau_va_con_doan_khac_phia_sau_phai_bao_ca_hai() -> None:
    """cắt đoạn đầu VÀ còn đoạn khác phía sau: PHẢI báo cả hai (Important 1, vòng rà soát lần 3)"""
    # 3 đoạn đều rất dài (5000 ký tự) - ngay cả đoạn ĐẦU cũng không vừa trần 500, nên nhánh "cắt đoạn đầu" chạy
    # - nhưng còn 2 đoạn khác (đoạn 1, 2) CHƯA TỪNG được xét vì vòng lặp ``break`` ngay sau đó. Trước bản vá,
    # nhánh này chỉ có "đã rút gọn" mà không hề nói còn đoạn khác - model tưởng đây là toàn bộ kết quả.
    doan = [doan_co_do(0, 5000), doan_co_do(1, 5000), doan_co_do(2, 5000)]
    kq = dong_goi_theo_ngan_sach(doan, 500)
    assert re.search("đã rút gọn", kq), "đoạn đầu phải được ghi nhận đã cắt"
    assert re.search("còn 2 đoạn nữa không đủ chỗ", kq), f"phải báo còn ĐÚNG 2 đoạn (1 và 2), thực tế: {kq!r}"


# --------------------------------------------------- chiều ÂM: đủ chỗ thì KHÔNG được có nhãn nào


def test_chieu_am_khong_nhan_con_n_doan_khi_moi_doan_deu_vua() -> None:
    """không nhãn 'còn N đoạn' khi mọi đoạn đều vừa"""
    doan = [doan_co_do(0, 30), doan_co_do(1, 30)]
    kq = dong_goi_theo_ngan_sach(doan, 5000)
    assert not re.search(r"còn \d+ đoạn", kq)


def test_chieu_am_khong_nhan_da_rut_gon_khi_moi_doan_deu_vua() -> None:
    """không nhãn 'đã rút gọn' khi mọi đoạn đều vừa"""
    doan = [doan_co_do(0, 30), doan_co_do(1, 30)]
    kq = dong_goi_theo_ngan_sach(doan, 5000)
    assert not re.search("đã rút gọn", kq)


# --------------------------------------------------- bất biến CỨNG: không bao giờ vượt ngân sách xin


def test_bat_bien_cung_quet_31_co_doan_x_201_muc_tran_luon_khong_vuot_ngan_sach() -> None:
    """quét 31 cỡ đoạn x 201 mức trần (đúng quy mô người rà soát đã đo) - luôn len(kq) <= nganSachNoiDung"""
    # Trần bắt đầu từ 300 - đủ cao hơn hẳn phần ngân sách hàm TỰ TRỪ TRƯỚC cho câu báo (luôn dưới 100 ký tự với 6
    # đoạn), khớp dải trần THẬT bot dùng (KB_MAX_RESULT_CHARS min 2000 trừ vỏ tối đa ~513 = sàn thật 1487, ở đây
    # quét rộng hơn cho chắc). KHÔNG quét xuống ca cực đoan trần < ~70 ký tự (nhỏ hơn cả câu báo) - ca đó không
    # tới được từ ``.env``/dashboard vì KB_MAX_RESULT_CHARS đã có sàn 2000 ở cả schema lẫn tuning_specs.
    so_doan = 6
    so_to_hop = 0
    for do_dai_doan in range(20, 621, 20):
        doan = [doan_co_do(i, do_dai_doan) for i in range(so_doan)]
        for tran in range(300, 2301, 10):
            kq = dong_goi_theo_ngan_sach(doan, tran)
            so_to_hop += 1
            assert len(kq) <= tran, (
                f"do_dai_doan={do_dai_doan} tran={tran} -> dài {len(kq)} (vượt {len(kq) - tran})"
            )
    assert so_to_hop > 6000, f"phải quét đủ nhiều tổ hợp, thực tế {so_to_hop}"
