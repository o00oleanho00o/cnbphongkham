# ported from: src/agent/tools/kb-pack-result.ts
"""Đóng gói danh sách đoạn ĐÃ ĐỊNH DẠNG (mỗi phần tử là một đoạn kèm nhãn nguồn, xem ``dinh_dang_doan`` ở
``kb_search_tool``) vào một ngân sách ký tự - THAM LAM, và KHÔNG cắt giữa đoạn.

Vì sao ĐÓNG GÓI TRƯỚC rồi mới BỌC (``wrap_untrusted_content``) ở caller: ngân sách ở đây chỉ tính phần NỘI
DUNG, không gồm phần vỏ (thẻ + ba dòng dặn dò). Cách cũ bọc trước rồi cắt cả khối đã bọc, nên trần bao gồm
luôn phần vỏ và không cách nào chừa chỗ cho nó - cắt tới đâu hay tới đó, có thể cắt ngay giữa MỘT ĐOẠN có
nhãn nguồn, giữa một câu, thậm chí giữa một CON SỐ (giá tiền, số ngày) - với một kho tri thức toàn dữ liệu
kiểu đó, một mẩu câu cụt vừa vô dụng vừa dễ bị model đọc/trích lại sai.

Đoạn KHÔNG VỪA bị BỎ HẲN, không cắt giữa chừng - TRỪ đoạn ĐẦU TIÊN: nếu ngay cả nó cũng không vừa (ngân sách
quá nhỏ so với một đoạn), thà một đoạn cụt còn hơn trả về rỗng, nên cắt nó ở ranh giới khoảng trắng gần nhất
(không cắt giữa từ) rồi ghi rõ đã rút gọn.

Bỏ hẳn đoạn (dù ở nhánh "đã có ít nhất một đoạn trọn vẹn" hay nhánh "đoạn ĐẦU TIÊN bị cắt mà vẫn còn đoạn
khác phía sau") LUÔN kèm một dòng báo "còn N đoạn nữa không đủ chỗ" (Important a, vòng rà soát lần 1 + lần
3): thiếu dòng này thì model KHÔNG PHÂN BIỆT được "đã đọc hết top-k" với "bị cắt bớt vì hết ngân sách" - đúng
thứ dễ đẻ ra câu trả lời tự tin từ một kho tri thức đọc thiếu mà không tự biết. Vòng rà soát lần 3 phát hiện
nhánh "cắt đoạn đầu" ban đầu VẪN thiếu dấu vết này khi còn đoạn khác chưa từng được xét.

BẤT BIẾN CỨNG (vòng rà soát lần 3, sửa từ "mềm"): kết quả trả về KHÔNG BAO GIỜ dài hơn
``ngan_sach_noi_dung``. Bản trước trừ ngân sách cho câu báo SAU khi đã đóng gói xong (nối thêm rồi mới xong) -
quét thật 31 cỡ đoạn x 201 mức trần đo được 396 tổ hợp vượt trần. Bản này trừ TRƯỚC: dành sẵn chỗ cho câu
báo DÀI NHẤT có thể cần dùng (``nhan_dai_nhat``, tính đúng ca xấu nhất - đoạn đầu bị cắt VÀ còn N đoạn khác -
CẢ HAI câu báo xuất hiện cùng lúc) rồi mới đóng gói trong phần ngân sách còn lại. Xem chứng minh + test quét
trong ``test_kb_pack_result``.

PHẠM VI của bất biến đó - đọc kỹ trước khi dựa vào: nó nói về ĐẦU RA CỦA HÀM NÀY so với
``ngan_sach_noi_dung`` NÓ ĐƯỢC ĐƯA, KHÔNG nói gì về chuỗi CUỐI CÙNG mà ``kb_search_tool`` gửi cho model. Chuỗi
cuối cùng còn đi qua ``wrap_untrusted_content`` sau đó, và có thời gian bước bọc đó LÀM DÀI RA thêm 13,8%
(chuỗi thay thế dài hơn chuỗi bị thay - đã sửa ở ``DANG_KHU``). Hai vòng rà soát đã chứng minh một mệnh đề
ĐÚNG nhưng không phải mệnh đề cần: phép quét 6.000+ tổ hợp dưới đây chỉ đo hàm này, còn thứ trần
``KB_MAX_RESULT_CHARS`` thật sự phải chặn là chuỗi cuối cùng - ca đó đo ở ``test_kb_search_tool``, không phải
ở đây.

Bất biến cũng KHÔNG áp cho ngân sách nhỏ hơn câu báo (~70 ký tự): sàn ``max(1, ...)`` ưu tiên "trả về thứ gì
đó" hơn là giữ trần. Ca đó không tới được từ dashboard/.env vì ``KB_MAX_RESULT_CHARS`` đã có sàn 2000.

Hàm THUẦN - không env, không DB, không log - cùng mẫu với ``trim_context_to_budget``.

Forced deviation: none beyond naming; lengths are code points (Python) instead of UTF-16 units (JS), the
invariant is stated in the same unit on both sides.
"""

from __future__ import annotations

KB_PACK_SEPARATOR = "\n\n---\n\n"

DANH_DAU_RUT_GON = "\n[...đoạn này đã rút gọn]"


def danh_dau_con_thieu(so_doan: int) -> str:
    return f"\n\n[...còn {so_doan} đoạn nữa không đủ chỗ]"


def cat_o_khoang_trang(s: str, gioi_han: int) -> str:
    """Cắt ``s`` về tối đa ``gioi_han`` ký tự, lùi về khoảng trắng gần nhất để không cắt giữa từ. Không có
    khoảng trắng nào trong giới hạn (một "từ" dài hơn cả ngân sách) thì đành cắt cứng - vẫn tốt hơn không trả
    gì. Giữ tối thiểu 1 ký tự để luôn có gì đó khác rỗng."""
    cho = max(1, gioi_han)
    if len(s) <= cho:
        return s
    da_cat = s[:cho]
    vi_tri = da_cat.rfind(" ")
    return da_cat[:vi_tri] if vi_tri > 0 else da_cat


def dong_goi_theo_ngan_sach(doan_da_dinh_dang: list[str], ngan_sach_noi_dung: int) -> str:
    """``doan_da_dinh_dang``: mỗi phần tử là MỘT đoạn hoàn chỉnh (đã kèm nhãn nguồn).
    ``ngan_sach_noi_dung``: số ký tự tối đa cho phần NỘI DUNG (không gồm vỏ) - caller tự trừ phần vỏ ra khỏi
    trần tổng trước khi gọi hàm này."""
    # Dành sẵn chỗ cho câu báo DÀI NHẤT có thể cần dùng - TRƯỚC khi đóng gói, không phải sau (xem docstring
    # đầu file). ``len(doan_da_dinh_dang)`` là chặn trên an toàn cho N trong "còn N đoạn nữa" (N luôn <= tổng
    # số đoạn).
    nhan_dai_nhat = len(DANH_DAU_RUT_GON) + len(danh_dau_con_thieu(len(doan_da_dinh_dang)))
    ngan_sach_thuc = max(1, ngan_sach_noi_dung - nhan_dai_nhat)

    ket_qua = ""
    for i, doan in enumerate(doan_da_dinh_dang):
        ung = f"{ket_qua}{KB_PACK_SEPARATOR}{doan}" if ket_qua else doan
        if len(ung) <= ngan_sach_thuc:
            ket_qua = ung
            continue

        # con_lai = đoạn hiện tại (vừa thất bại) + mọi đoạn phía sau chưa xét tới.
        con_lai = len(doan_da_dinh_dang) - i
        if ket_qua == "":
            # Đoạn ĐẦU TIÊN đã không vừa - cắt nó thay vì trả về rỗng hoàn toàn.
            cho_noi_dung = max(1, ngan_sach_thuc - len(DANH_DAU_RUT_GON))
            ket_qua = cat_o_khoang_trang(doan, cho_noi_dung) + DANH_DAU_RUT_GON
            # Đoạn đầu bị cắt KHÔNG có nghĩa nó là đoạn DUY NHẤT - còn đoạn khác phía sau (chưa từng được
            # thử, vì vòng lặp ``break`` ngay dưới) thì phải báo luôn, không thì model tưởng "đoạn cụt này"
            # là toàn bộ kết quả.
            if con_lai > 1:
                ket_qua += danh_dau_con_thieu(con_lai - 1)
        else:
            # Đã có ít nhất một đoạn trọn vẹn - đoạn NÀY và mọi đoạn còn lại đều bị bỏ hẳn.
            ket_qua += danh_dau_con_thieu(con_lai)
        # Ngân sách đã hết: các đoạn còn lại bị BỎ HẲN, không cắt giữa chừng - đây chính là điểm khác cách cũ.
        break
    return ket_qua
