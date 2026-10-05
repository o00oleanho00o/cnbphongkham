# ported from: evals/eval-formatting-view.test.ts
"""Pure module. It is the piece that lets the evals SEE formatting, so it must be right itself: cutting ``chu``
wrong in one place makes every assertion built on it lie while staying green.

Test names are the snake_case form of ``describe - it``; the original Vietnamese title is the docstring.
"""

from __future__ import annotations

from evals.eval_formatting_view import (
    KIEU,
    SentMessage,
    SpanDaGui,
    ZaloStyle,
    dem_kieu,
    doan_theo_kieu,
    dung_goc_nhin_dinh_dang,
    utf16_index,
)


def test_dung_goc_nhin_dinh_dang_cat_dung_doan_chu_ma_moi_span_phu() -> None:
    """dungGocNhinDinhDang: cắt ĐÚNG đoạn chữ mà mỗi span phủ

    "There are 5 bold spans" is almost meaningless; "the bold span covers exactly this text" is what the reader
    feels. ``start`` is DIFFERENT from 0 on purpose: with start = 0, ``slice(start, len)`` and
    ``slice(start, start + len)`` give the same result and the case would be an empty green."""
    msg = "Bot có thể: Tra cứu web: tin tức"
    nhan = "Tra cứu web:"
    dd = dung_goc_nhin_dinh_dang(
        [SentMessage(msg=msg, styles=[ZaloStyle(start=utf16_index(msg, nhan), len=len(nhan), st="b")])]
    )
    assert dd.span == [SpanDaGui(st="b", chu=nhan, tin=1)]


def test_dung_goc_nhin_dinh_dang_danh_so_tin_dung_khi_cau_tra_loi_bi_cat_nhieu_tin() -> None:
    """dungGocNhinDinhDang: đánh số tin ĐÚNG khi câu trả lời bị cắt nhiều tin"""
    dd = dung_goc_nhin_dinh_dang(
        [
            SentMessage(msg="một", styles=[ZaloStyle(start=0, len=3, st="b")]),
            SentMessage(msg="hai", styles=[ZaloStyle(start=0, len=3, st="i")]),
        ]
    )
    assert [s.tin for s in dd.span] == [1, 2]
    assert dd.so_tin == 2


def test_dung_goc_nhin_dinh_dang_tin_khong_co_styles_khong_sinh_span_nao() -> None:
    """dungGocNhinDinhDang: tin KHÔNG có styles không sinh span nào"""
    dd = dung_goc_nhin_dinh_dang([SentMessage(msg="chữ trơn"), SentMessage(msg="cũng trơn", styles=[])])
    assert dd.span == []
    assert dd.so_tin == 2


def test_dung_goc_nhin_dinh_dang_dau_tieng_viet_va_emoji_khong_lam_lech_lat_cat() -> None:
    """dungGocNhinDinhDang: dấu tiếng Việt và emoji không làm lệch lát cắt

    ``start``/``len`` are UTF-16 units; an emoji is a surrogate pair = 2 units. Python indexes code points, so
    this is the case that would break a naive port: slicing by code points would shift every span after the
    first emoji."""
    msg = "🔥 Giá 45.000đ"
    gia = "45.000đ"
    # in UTF-16 the flame is 2 units, so the price starts at 2 + len(" Giá ") = 7 and is NOT at code point 7
    start = utf16_index(msg, gia)
    assert start == 7
    assert msg.index(gia) == 6, "the code-point index differs from the UTF-16 one: the trap of this case"
    dd = dung_goc_nhin_dinh_dang(
        [SentMessage(msg=msg, styles=[ZaloStyle(start=start, len=len(gia), st="b")])]
    )
    assert dd.span[0].chu == "45.000đ"


def test_dung_goc_nhin_dinh_dang_nhieu_emoji_lien_tiep_van_cat_dung() -> None:
    """dungGocNhinDinhDang: (thêm ở bản port) hai emoji liền nhau rồi mới tới nhãn in đậm"""
    msg = "🔥🔥 Nhãn: nội dung"
    nhan = "Nhãn:"
    dd = dung_goc_nhin_dinh_dang(
        [SentMessage(msg=msg, styles=[ZaloStyle(start=utf16_index(msg, nhan), len=len(nhan), st="b")])]
    )
    assert dd.span[0].chu == nhan


def test_doan_theo_kieu_va_dem_kieu_loc_dung_theo_ma_style() -> None:
    """doanTheoKieu và demKieu lọc đúng theo mã style"""
    dd = dung_goc_nhin_dinh_dang(
        [
            SentMessage(
                msg="Nhãn cam và chữ đậm",
                styles=[ZaloStyle(start=0, len=8, st=KIEU.cam), ZaloStyle(start=13, len=6, st=KIEU.dam)],
            )
        ]
    )
    assert doan_theo_kieu(dd, KIEU.cam) == ["Nhãn cam"]
    assert dem_kieu(dd, KIEU.dam) == 1
    assert dem_kieu(dd, KIEU.xanh) == 0
