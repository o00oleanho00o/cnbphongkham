# ported from: src/zalo/reconnect-planner.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Planner THUẦN. Đây là lưới đỡ cho ca thật 2026-08-25 (đổi mật khẩu -> phiên chết -> bão reconnect vô tận).
"""

from __future__ import annotations

from pema.channels.zalo_personal.reconnect_planner import KeHoachKetNoiLai


def _planner() -> KeHoachKetNoiLai:
    # Opts nhỏ, dễ đọc số: nối >= 100ms là đứng; backoff 10 -> 20 -> 40...; trần 100; nghi sau 3 lần.
    return KeHoachKetNoiLai(on_dinh_ms=100, co_so_ms=10, tran_ms=100, nguong_nghi_ngo=3)


def test_ke_hoach_ket_noi_lai_ket_noi_dung_roi_dong_reset_backoff_ve_co_so() -> None:
    """kết nối ĐỨNG (>= onDinhMs) rồi đóng -> reset: backoff về cơ số, không nghi phiên chết"""
    k = _planner()
    k.danh_dau_ket_noi(0)
    r = k.danh_dau_dong(200, 0)  # nối 200ms >= 100 -> đứng
    assert r.on_dinh is True
    assert r.delay_ms == 10, "đứng -> soLan reset 0 -> backoff = cơ số"
    assert r.chop_tat_lien_tiep == 0
    assert r.nghi_ngo_phien_chet is False


def test_ke_hoach_ket_noi_lai_noi_dung_bang_on_dinh_ms_van_tinh_la_dung() -> None:
    """nối đúng BẰNG onDinhMs vẫn tính là đứng (>=)"""
    k = _planner()
    k.danh_dau_ket_noi(0)
    assert k.danh_dau_dong(100, 0).on_dinh is True


def test_ke_hoach_ket_noi_lai_chop_tat_lien_tiep_backoff_tang_gap_doi() -> None:
    """chớp-tắt liên tiếp -> backoff TĂNG gấp đôi mỗi lần"""
    k = _planner()
    # Không danh_dau_ket_noi -> mỗi lần đóng đều là chớp-tắt
    assert k.danh_dau_dong(1, 0).delay_ms == 10  # 10 * 2^0
    assert k.danh_dau_dong(2, 0).delay_ms == 20  # 10 * 2^1
    assert k.danh_dau_dong(3, 0).delay_ms == 40  # 10 * 2^2


def test_ke_hoach_ket_noi_lai_backoff_bi_chan_o_tran() -> None:
    """backoff bị CHẶN ở trần"""
    k = _planner()
    ds = [k.danh_dau_dong(t, 0).delay_ms for t in (1, 2, 3, 4, 5, 6)]
    # 10, 20, 40, 80, rồi 160/320 bị chặn về trần 100
    assert ds == [10, 20, 40, 80, 100, 100]


def test_ke_hoach_ket_noi_lai_du_nguong_chop_tat_lien_tiep_nghi_ngo_phien_chet() -> None:
    """đủ ngưỡng chớp-tắt LIÊN TIẾP -> nghiNgoPhienChet, trước đó thì chưa"""
    k = _planner()  # ngưỡng 3
    assert k.danh_dau_dong(1, 0).nghi_ngo_phien_chet is False  # 1
    assert k.danh_dau_dong(2, 0).nghi_ngo_phien_chet is False  # 2
    r3 = k.danh_dau_dong(3, 0)
    assert r3.chop_tat_lien_tiep == 3
    assert r3.nghi_ngo_phien_chet is True  # >= 3


def test_ke_hoach_ket_noi_lai_mot_lan_ket_noi_dung_xen_giua_reset_ca_chuoi() -> None:
    """một lần kết-nối-ĐỨNG xen giữa -> RESET cả chuỗi chớp-tắt lẫn backoff"""
    k = _planner()
    k.danh_dau_dong(1, 0)  # chớp 1, soLan->1
    k.danh_dau_dong(2, 0)  # chớp 2, soLan->2
    # kết nối đứng rồi rớt
    k.danh_dau_ket_noi(1000)
    r_on = k.danh_dau_dong(1200, 0)
    assert r_on.on_dinh is True
    assert r_on.chop_tat_lien_tiep == 0, "đứng phải quên chuỗi chớp-tắt"
    assert r_on.delay_ms == 10, "soLan reset -> backoff cơ số"
    # chớp-tắt tiếp -> chuỗi đếm lại từ 1; backoff leo lên 20 vì lần rớt-lành vừa rồi đã tiêu rung 0
    # (soLan->1). Flap ngay sau khi vừa hồi phục thì giãn nhanh hơn một nấc - an toàn hơn, không phải lỗi.
    r = k.danh_dau_dong(1300, 0)
    assert r.chop_tat_lien_tiep == 1
    assert r.delay_ms == 20


def test_ke_hoach_ket_noi_lai_dong_khi_chua_tung_ket_noi_tinh_la_chop_tat() -> None:
    """đóng khi CHƯA từng kết nối -> tính là chớp-tắt (onDinh false)"""
    k = _planner()
    assert k.danh_dau_dong(999_999, 0).on_dinh is False


def test_ke_hoach_ket_noi_lai_hai_lan_dong_lien_tiep_lan_2_khong_tinh_nham_la_dung() -> None:
    """hai lần đóng LIÊN TIẾP không có kết nối xen giữa -> lần 2 KHÔNG tính nhầm là đứng"""
    k = _planner()
    k.danh_dau_ket_noi(0)
    assert k.danh_dau_dong(200, 0).on_dinh is True  # đứng, tiêu ketNoiLuc
    # lần đóng kế tiếp mà không danh_dau_ket_noi lại -> phải là chớp-tắt
    assert k.danh_dau_dong(999_999, 0).on_dinh is False, "ketNoiLuc đã tiêu, không được tính lại theo mốc cũ"


def test_ke_hoach_ket_noi_lai_jitter_duoc_cong_vao_delay() -> None:
    """jitter được cộng vào delay"""
    k = _planner()
    assert k.danh_dau_dong(1, 7).delay_ms == 17  # 10 + 7


def test_ke_hoach_ket_noi_lai_bao_phien_chet_moi_lan_noi_ngan_van_tinh_chop_tat() -> None:
    """BÃO PHIÊN CHẾT: mỗi lần nối NGẮN (dù đã danhDauKetNoi) vẫn tính chớp-tắt -> backoff LEO + cảnh báo re-login

    Lưới đỡ CỐT LÕI cho ca 2026-08-25 và cho chính bản sửa ``>= onDinhMs``. Bug gốc coi MỌI kết nối (kể cả
    2ms) là đứng -> reset backoff -> bão không bao giờ lùi, không bao giờ cảnh báo.
    """
    k = _planner()  # onDinhMs 100, coSo 10, trần 100, ngưỡng 3
    delays: list[int] = []
    flag_at = -1
    for i in range(4):
        k.danh_dau_ket_noi(i * 1000)  # listener báo "đã kết nối"...
        r = k.danh_dau_dong(i * 1000 + 2, 0)  # ...rồi rớt sau 2ms = phiên chết
        delays.append(r.delay_ms)
        assert r.on_dinh is False, "nối 2ms KHÔNG được tính là đứng"
        if r.nghi_ngo_phien_chet and flag_at < 0:
            flag_at = i + 1
    assert delays == [10, 20, 40, 80], "backoff phải LEO dù mỗi lần đều có danhDauKetNoi"
    assert flag_at == 3, "chạm ngưỡng nghi phiên chết ở flap thứ 3"


def test_ke_hoach_ket_noi_lai_danh_dau_ket_noi_goi_nhieu_lan_so_voi_moc_moi_nhat() -> None:
    """danhDauKetNoi gọi nhiều lần -> so với mốc MỚI NHẤT"""
    k = _planner()
    k.danh_dau_ket_noi(0)
    k.danh_dau_ket_noi(1000)  # onConnected bắn lại -> mốc mới
    # đóng lúc 1050: so mốc mới (1000) là 50ms < 100 -> chớp-tắt. Nếu lấy mốc cũ (0) thì 1050 >= 100 -> nhầm.
    assert k.danh_dau_dong(1050, 0).on_dinh is False, "phải so với danhDauKetNoi mới nhất"


def test_ke_hoach_ket_noi_lai_nghi_ngo_phien_chet_giu_true_o_cac_flap_sau_nguong() -> None:
    """nghiNgoPhienChet GIỮ true ở các flap SAU khi đã vượt ngưỡng"""
    k = _planner()  # ngưỡng 3
    k.danh_dau_dong(1, 0)
    k.danh_dau_dong(2, 0)
    assert k.danh_dau_dong(3, 0).nghi_ngo_phien_chet is True  # đúng ngưỡng
    assert k.danh_dau_dong(4, 0).nghi_ngo_phien_chet is True  # sau ngưỡng vẫn true
    assert k.danh_dau_dong(5, 0).nghi_ngo_phien_chet is True


def test_ke_hoach_ket_noi_lai_ket_noi_dung_xen_giua_tat_co_nghi_phien_chet_dang_bat() -> None:
    """kết nối ĐỨNG xen giữa -> TẮT cờ nghi phiên chết đang bật"""
    k = _planner()  # ngưỡng 3
    k.danh_dau_dong(1, 0)
    k.danh_dau_dong(2, 0)
    assert k.danh_dau_dong(3, 0).nghi_ngo_phien_chet is True  # đã bật cờ
    k.danh_dau_ket_noi(1000)
    r = k.danh_dau_dong(1200, 0)  # nối 200ms >= 100 -> đứng
    assert r.nghi_ngo_phien_chet is False, "đứng phải tắt cờ nghi"
    assert r.chop_tat_lien_tiep == 0
