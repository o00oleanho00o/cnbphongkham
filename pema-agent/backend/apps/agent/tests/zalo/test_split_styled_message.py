# ported from: src/zalo/split-styled-message.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Module thuần, import tĩnh được.

CÁCH KHẲNG ĐỊNH: luôn so ĐOẠN CHỮ mà span trỏ tới, không so con số. Ở bài cắt tin thì con số đúng/sai chỉ lộ ra
khi đem cắt thật - và đó chính là thứ Zalo làm với `textProperties`.
"""

from __future__ import annotations

import json

from plugins.zalo.format.markdown_to_zalo_styles import markdown_sang_style_zalo
from plugins.zalo.format.normalize_zalo_styles import ZaloStyle, ZaloTextStyle, make_style
from plugins.zalo.format.split_long_message import OVERFLOW_NOTE, SplitOptions
from plugins.zalo.format.split_styled_message import (
    NganSachByteOptions,
    TinCoDinhDang,
    chia_theo_ngan_sach_byte,
    dem_doan_bo_dinh_dang,
    so_byte_tin,
    split_styled_message,
)
from plugins.zalo.format.utf16_text import utf16_len, utf16_slice

Z = ZaloTextStyle


def tu_markdown(doc: str) -> TinCoDinhDang:
    ket = markdown_sang_style_zalo(doc)
    return TinCoDinhDang(text=ket.text, styles=ket.styles)


def cac_doan_to(tin: TinCoDinhDang) -> list[str]:
    """Mọi đoạn chữ được tô trong một tin, theo thứ tự (offsets are UTF-16 units)."""
    return [utf16_slice(tin.text, s.start, s.length) for s in tin.styles]


def test_split_styled_message_short_message_passes_whole_styles_unchanged() -> None:
    """tin ngắn: đi nguyên vẹn, style giữ y như cũ"""
    goc = tu_markdown("Giá **45.000đ** nhé")
    phan = split_styled_message(goc, SplitOptions(max_chars=2000, max_parts=5))
    assert len(phan) == 1
    assert phan[0].styles == goc.styles
    assert cac_doan_to(phan[0]) == ["45.000đ"]


def test_split_styled_message_no_style_keeps_the_old_splitting_behaviour() -> None:
    """không có style thì không đổi hành vi cắt cũ"""
    dai = "câu dài. " * 60
    phan = split_styled_message(TinCoDinhDang(text=dai, styles=[]), SplitOptions(max_chars=100, max_parts=10))
    assert len(phan) > 1
    for p in phan:
        assert p.styles == []


def test_split_styled_message_from_part_two_on_offsets_move_to_the_start_of_the_message_not_the_full_text() -> (
    None
):
    """ĐOẠN 2 TRỞ ĐI: mốc dời về đầu tin, không giữ mốc toàn văn"""
    # Đây là lỗi mặc định nếu quên dời mốc: span của đoạn sau vẫn mang số đếm từ đầu toàn văn nên Zalo tô nhầm
    # chỗ (hoặc bỏ vì vượt biên).
    goc = tu_markdown(f"{'x' * 90}\n\nPhần sau có **chữ đậm** ở đây")
    phan = split_styled_message(goc, SplitOptions(max_chars=100, max_parts=5))
    assert len(phan) >= 2, "phải cắt ra nhiều tin thì ca này mới có nghĩa"

    co_dam = [p for p in phan if len(p.styles) > 0]
    assert len(co_dam) == 1, "chỉ một đoạn chứa chữ đậm"
    assert cac_doan_to(co_dam[0]) == ["chữ đậm"]


def test_split_styled_message_a_span_crossing_the_cut_is_split_in_two_neither_lost_nor_overflowing() -> None:
    """SPAN VẮT QUA CHỖ CẮT bị chẻ đôi, không mất và không tràn"""
    # Bản tham chiếu không giải bài này (nó cắt cụt thay vì chẻ tin).
    dam = "ĐOẠN ĐẬM RẤT DÀI BỊ CẮT NGANG GIỮA CHỪNG"
    goc = tu_markdown(f"{'a ' * 45}**{dam}** đuôi")
    phan = split_styled_message(goc, SplitOptions(max_chars=100, max_parts=10))

    to_duoc = " ".join(d for p in phan for d in cac_doan_to(p))
    # Từng chữ của đoạn đậm phải còn nằm trong vùng được tô ở đâu đó
    for tu in dam.split(" "):
        assert tu in to_duoc, f'mất chữ "{tu}" khỏi vùng tô sau khi cắt'
    # Và không được tràn sang chữ ngoài đoạn đậm
    assert "đuôi" not in to_duoc, "vùng tô tràn sang chữ không thuộc đoạn đậm"
    assert "a a" not in to_duoc, "vùng tô tràn ngược lên chữ phía trước"


def test_split_styled_message_every_span_is_within_the_bounds_of_the_message_that_holds_it() -> None:
    """MỌI span đều nằm trong biên của chính tin chứa nó"""
    # Bất biến quan trọng nhất: zca-js gói thẳng start/len vào JSON, không ai kiểm hộ. Span vượt biên là dữ
    # liệu hỏng gửi lên máy chủ Zalo.
    doc = "\n".join(
        [
            "# Tiêu đề khá dài để chắc chắn bị đẩy qua ranh giới cắt",
            "Mở đầu **quan trọng** rồi *nghiêng* rồi ~~gạch~~ và `code`",
            *(f"- mục số {i} có **phần đậm {i}** nối dài thêm chữ" for i in range(12)),
        ]
    )
    goc = tu_markdown(doc)

    for max_chars in (60, 100, 137, 200, 512):
        phan = split_styled_message(goc, SplitOptions(max_chars=max_chars, max_parts=50))

        # Chống xanh RỖNG: mốc lệch làm `len` ra âm và span bị bỏ hết, lúc đó vòng kiểm biên bên dưới đúng
        # một cách vô nghĩa. Phải còn span để kiểm.
        tong_span = sum(len(p.styles) for p in phan)
        assert tong_span >= len(goc.styles), (
            f"maxChars={max_chars}: mất span sau khi cắt ({tong_span} < {len(goc.styles)})"
        )

        for i, p in enumerate(phan):
            for s in p.styles:
                assert s.start >= 0, f"maxChars={max_chars} tin {i}: start âm {s.start}"
                assert s.length > 0, f"maxChars={max_chars} tin {i}: span rỗng"
                assert s.start + s.length <= utf16_len(p.text), (
                    f"maxChars={max_chars} tin {i}: span vượt biên {s.start}+{s.length} > {utf16_len(p.text)}"
                )


def test_split_styled_message_painted_area_never_contains_leftover_markdown_characters() -> None:
    """vùng tô KHÔNG BAO GIỜ dính ký tự markdown còn sót"""
    # Nếu mốc lệch, biểu hiện thường thấy nhất là vùng tô trượt sang ký tự bên cạnh. Toàn văn đã sạch dấu
    # markdown nên chỉ cần soi vùng tô.
    doc = "\n".join(f"Dòng {i} có **đậm {i}** và *nghiêng {i}*" for i in range(20))
    goc = tu_markdown(doc)
    for p in split_styled_message(goc, SplitOptions(max_chars=90, max_parts=40)):
        for doan in cac_doan_to(p):
            assert "*" not in doan, f'vùng tô dính dấu sao: "{doan}"'


def test_split_styled_message_overflow_note_in_the_last_part_does_not_pick_up_styles_of_the_cut_away_text() -> (
    None
):
    """ghi chú 'còn nữa' ở đoạn cuối KHÔNG bị dính style của phần đã cắt bỏ"""
    # `phu_goc` sinh ra chính vì ca này: ghi chú là chữ THÊM VÀO, span thuộc phần bị cắt bỏ mà lấy độ dài text
    # làm phạm vi thì sẽ rơi trúng nó.
    doc = "\n".join(f"đoạn {i} **rất đậm {i}** dài dài" for i in range(40))
    goc = tu_markdown(doc)
    phan = split_styled_message(goc, SplitOptions(max_chars=120, max_parts=3))
    assert len(phan) == 3, "phải chạm trần số tin thì mới có ghi chú"

    cuoi = phan[2]
    vi_tri_ghi_chu = utf16_len(cuoi.text[: cuoi.text.index(OVERFLOW_NOTE)])
    assert vi_tri_ghi_chu > 0, "đoạn cuối phải có ghi chú còn nữa"

    # Bất biến THẬT: không span nào chạm vào vùng ghi chú. Chỉ kiểm "trong biên" là chưa đủ - lớp kẹp cuối giữ
    # biên đúng ngay cả khi span đã trượt vào ghi chú, nên phép phá `phu_goc` -> độ dài text lọt qua được.
    for s in cuoi.styles:
        assert s.start + s.length <= vi_tri_ghi_chu, (
            f'style tràn vào ghi chú "còn nữa": {s.start}+{s.length} > {vi_tri_ghi_chu}'
        )


def test_split_styled_message_keeps_the_indent_size_when_splitting_nested_lists_do_not_lose_a_level() -> None:
    """giữ nguyên indentSize khi chẻ - danh sách lồng không tụt cấp"""
    # `markdown_sang_style_zalo` không còn phát `Indent` (danh sách đi bằng chữ thường), nhưng bộ cắt vẫn phải
    # xử lý đúng span Indent do nơi khác đưa vào - nó là hàm dùng chung, không phải phần phụ của bộ dịch markdown.
    goc = TinCoDinhDang(
        text="cha\ncon lồng vào trong",
        styles=[make_style(4, 18, Z.INDENT, indent_size=1)],
    )
    phan = split_styled_message(goc, SplitOptions(max_chars=2000, max_parts=5))
    indent = next((s for s in phan[0].styles if s.style == Z.INDENT), None)
    assert indent is not None, "phải còn span Indent"
    assert isinstance(indent, ZaloStyle)
    assert indent.indent_size == 1


# ------------------------------------------------------------------ chia_theo_ngan_sach_byte


def tao_van_ban(so_dong: int) -> str:
    """Văn bản kiểu bot hay trả: tiêu đề + danh sách dày số liệu in đậm."""
    dong = ["## Kết quả đối chiếu **hôm nay**"]
    for i in range(1, so_dong + 1):
        dong.append(f"- Giải {i}: **{10000 + i}** so với vé **{20000 + i}** thì **không trúng**")
    return "\n".join(dong)


def test_chia_theo_ngan_sach_byte_every_message_is_under_the_byte_budget() -> None:
    """MỌI tin đều nằm dưới ngân sách byte"""
    # Bất biến gốc: Zalo trả mã 112 và bỏ cả tin khi chữ + định dạng cộng lại vượt trần. Đo thật: 2867 byte
    # gửi được, 3712 byte bị chối.
    goc = tu_markdown(tao_van_ban(40))
    assert so_byte_tin(goc) > 2800, "văn bản mẫu phải đủ nặng thì ca này mới có nghĩa"

    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=8, max_payload_bytes=2800)
    )
    for i, p in enumerate(phan):
        assert so_byte_tin(p) <= 2800, (
            f"tin {i} nặng {so_byte_tin(p)} byte, vượt trần 2800 - Zalo sẽ trả mã 112"
        )


def test_chia_theo_ngan_sach_byte_splits_smaller_rather_than_dropping_the_formatting() -> None:
    """cắt NHỎ HƠN chứ không vứt định dạng"""
    # Người dùng nhận thêm một tin thì vẫn đọc được; mất định dạng là mất đúng thứ vừa làm ra. Chỉ bỏ định dạng
    # khi co hết cỡ vẫn không lọt.
    goc = tu_markdown(tao_van_ban(40))
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=8, max_payload_bytes=2800)
    )

    assert len(phan) > 1, "phải cắt ra nhiều tin"
    co_style = sum(1 for p in phan if len(p.styles) > 0)
    assert co_style == len(phan), "không tin nào được phép mất định dạng ở ca này"


def test_chia_theo_ngan_sach_byte_uses_the_whole_allowed_message_quota_without_leaving_one_and_dropping_formatting() -> (
    None
):
    """DÙNG HẾT suất tin được phép, không chừa lại một suất rồi bỏ định dạng"""
    # Bản đầu chặn vòng co bằng `thu.length >= maxParts` - đo sai đại lượng. Chạm ĐÚNG trần số tin không phải
    # mất chữ, nhưng nó vẫn vứt kết quả tốt. Đo trên tin thật: bước co cho ra 5 tin, mọi tin dưới trần, không
    # hụt chữ, vậy mà chốt chặn nổ và giữ bản 3 tin có một tin 3754 byte -> bỏ định dạng. Người dùng nhận tin
    # đầu phẳng lì mà log không hề nhắc gì.
    # 60 dòng CỐ Ý: đo thật cho thấy văn bản nhẹ hơn không đi qua nhánh hỏng (chốt chặn cũ chỉ nổ khi vòng co
    # chạm đúng trần số tin). Fixture 38 dòng của bản đầu xanh với CẢ hai bản code - tức là không kiểm được gì.
    goc = tu_markdown(tao_van_ban(60))
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=5, max_payload_bytes=2800)
    )

    mat = [p for p in phan if len(p.styles) == 0]
    assert len(mat) == 0, f"{len(mat)}/{len(phan)} tin mất định dạng dù còn suất để cắt nhỏ hơn"


def test_chia_theo_ngan_sach_byte_shrinking_to_the_cap_still_keeps_all_the_text_no_trading_text_for_formatting() -> (
    None
):
    """co tới trần vẫn giữ ĐỦ CHỮ - không được đánh đổi chữ lấy định dạng"""
    # Vòng co dừng đúng lúc: cắt mịn hơn thì `trimEnd` ở ranh giới ăn vài ký tự trắng (chấp nhận được), nhưng
    # vứt cả đoạn văn thì không.
    goc = tu_markdown(tao_van_ban(38))
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=5, max_payload_bytes=2800)
    )

    da_giao = "".join(p.text for p in phan)
    assert OVERFLOW_NOTE not in da_giao, "không được vứt chữ kèm ghi chú 'còn nữa'"
    # Mỗi ranh giới cắt ăn nhiều nhất vài ký tự trắng
    assert len(da_giao) >= len(goc.text) - len(phan) * 3, (
        f"hụt {len(goc.text) - len(da_giao)} ký tự, quá mức trim ở ranh giới"
    )


def test_chia_theo_ngan_sach_byte_a_part_with_nothing_to_paint_is_not_flagged_as_lost_formatting() -> None:
    """đoạn KHÔNG CÓ GÌ ĐỂ TÔ không bị đánh dấu là mất định dạng"""
    # Báo động giả đã xảy ra thật: đoạn cuối câu trả lời chỉ là văn xuôi nên `styles` rỗng tự nhiên, mà nơi
    # gửi suy ra từ độ dài rồi kêu "đoạn quá nặng". Cờ `bo_dinh_dang` sinh ra chính vì ca này.
    goc = tu_markdown(f"## Tiêu đề **đậm**\n{'Đoạn văn xuôi dài không có dấu markdown nào cả. ' * 40}")
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=900, max_parts=5, max_payload_bytes=3250)
    )

    rong = [p for p in phan if len(p.styles) == 0]
    assert len(rong) > 0, "phải có đoạn không chứa chữ nào cần tô thì ca này mới có nghĩa"
    for p in rong:
        assert p.bo_dinh_dang is False, "đoạn vốn không có gì để tô KHÔNG phải là mất định dạng"


def test_chia_theo_ngan_sach_byte_a_part_that_really_lost_its_formatting_carries_the_flag() -> None:
    """đoạn THẬT SỰ bị bỏ định dạng thì có cờ để nơi gửi kêu lên"""
    goc = tu_markdown(tao_van_ban(60))
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=2, max_payload_bytes=1200)
    )

    bo = [p for p in phan if p.bo_dinh_dang]
    assert len(bo) > 0, "co hết cỡ vẫn vượt trần thì phải có đoạn bị bỏ định dạng"
    for p in bo:
        assert p.styles == [], "đã bỏ thì không được còn span nào"


def test_chia_theo_ngan_sach_byte_does_not_shred_a_message_that_is_already_light() -> None:
    """KHÔNG cắt vụn khi tin vốn đã nhẹ"""
    # Co trần vô cớ là bắt người ta đọc nhiều tin hơn cần thiết.
    goc = tu_markdown("Giá **45.000đ** nhé anh Hải")
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=5, max_payload_bytes=2800)
    )
    assert len(phan) == 1
    assert len(phan[0].styles) > 0


def test_chia_theo_ngan_sach_byte_hitting_the_message_count_cap_prefers_dropping_formatting_over_dropping_text() -> (
    None
):
    """chạm trần SỐ TIN thì thà bỏ định dạng còn hơn vứt chữ"""
    # Co tiếp là chữ bị cắt kèm ghi chú "còn nữa". Mất chữ tệ hơn mất định dạng.
    goc = tu_markdown(tao_van_ban(60))
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=2, max_payload_bytes=1200)
    )

    # Bất biến ĐÚNG: trần byte chỉ áp cho tin CÓ định dạng. Đã đo thật - cùng đoạn chữ 2321 byte, gửi trơn thì
    # được, kèm style thì bị chối. Nên tin nào vượt trần BẮT BUỘC phải rỗng style; còn chữ thì không được đụng
    # tới.
    for p in phan:
        assert so_byte_tin(p) <= 1200 or len(p.styles) == 0, (
            f"tin {so_byte_tin(p)} byte vượt trần mà VẪN mang {len(p.styles)} style"
        )
    assert len(phan) <= 2, "không được vượt trần số tin"


def test_chia_theo_ngan_sach_byte_vietnamese_text_is_counted_in_utf8_bytes_not_characters() -> None:
    """chữ tiếng Việt tính theo BYTE UTF-8, không theo số ký tự"""
    # Dấu tiếng Việt tốn 2-3 byte mỗi ký tự. Đếm ký tự thì tin tiếng Việt lọt trần trên giấy nhưng vẫn bị Zalo
    # chối.
    viet = TinCoDinhDang(text="Đường Nguyễn Huệ", styles=[])
    assert so_byte_tin(viet) > len(viet.text), "chuỗi có dấu phải nặng hơn số ký tự của nó"


def test_chia_theo_ngan_sach_byte_message_without_formatting_is_not_shrunk_the_cap_is_only_for_styled_messages() -> (
    None
):
    """tin KHÔNG có định dạng thì không bị co - trần này chỉ của tin có style"""
    # Đã đo: cùng đoạn chữ 2321 byte, không style thì gửi được, có style thì chối.
    dai = "câu dài không dấu markdown. " * 120
    phan = chia_theo_ngan_sach_byte(
        TinCoDinhDang(text=dai, styles=[]),
        NganSachByteOptions(max_chars=2000, max_parts=8, max_payload_bytes=2800),
    )
    theo_ky_tu = split_styled_message(
        TinCoDinhDang(text=dai, styles=[]), SplitOptions(max_chars=2000, max_parts=8)
    )
    assert len(phan) == len(theo_ky_tu), "không style thì phải cắt y như cũ"


# ------------------------------------------------------------------ dem_doan_bo_dinh_dang


def test_dem_doan_bo_dinh_dang_empty_styles_without_the_flag_do_not_count_as_lost_formatting() -> None:
    """đoạn styles rỗng mà KHÔNG có cờ thì không tính là mất định dạng"""
    # Đây đúng là báo động giả đã xảy ra thật: đoạn cuối câu trả lời chỉ là văn xuôi nên `styles` rỗng tự
    # nhiên, mà nơi gửi suy ra từ độ dài rồi kêu "đoạn quá nặng so với trần byte".
    assert (
        dem_doan_bo_dinh_dang(
            [
                TinCoDinhDang(text="có tô", styles=[make_style(0, 2, Z.BOLD)]),
                TinCoDinhDang(text="văn xuôi thuần", styles=[]),
            ]
        )
        == 0
    )


def test_dem_doan_bo_dinh_dang_counts_only_parts_with_the_flag() -> None:
    """chỉ đếm đoạn có cờ boDinhDang"""
    assert (
        dem_doan_bo_dinh_dang(
            [
                TinCoDinhDang(text="a", styles=[]),
                TinCoDinhDang(text="b", styles=[], bo_dinh_dang=True),
                TinCoDinhDang(text="c", styles=[], bo_dinh_dang=True),
            ]
        )
        == 2
    )


# ------------------------------------------------------------------ additions of the port (UTF-16, wire bytes)

EMOJI = "\U0001f600"


def test_so_byte_tin_measures_text_utf8_plus_the_compact_wire_json_of_the_styles() -> None:
    """(port) so_byte_tin = byte UTF-8 của chữ + JSON gọn dạng dây {"styles":[{start,len,st}]}"""
    tin = TinCoDinhDang(text=f"Đậm {EMOJI}", styles=[make_style(0, 4, Z.BOLD), make_style(5, 2, Z.BIG)])
    wire = '{"styles":[{"start":0,"len":4,"st":"b"},{"start":5,"len":2,"st":"f_18"}]}'
    assert json.loads(wire)["styles"][1]["len"] == 2
    assert so_byte_tin(tin) == len(f"Đậm {EMOJI}".encode()) + len(wire)
    # astral char: 4 UTF-8 bytes (and 2 UTF-16 units); "Đậm " is 4 + 1 chars, "Đ" and "ậ" are 2 and 3 bytes
    assert len(f"Đậm {EMOJI}".encode()) == 2 + 3 + 1 + 1 + 4
    # an indent span adds its extra key in the wire size
    indent = TinCoDinhDang(text="ab", styles=[make_style(0, 2, Z.INDENT, indent_size=2)])
    assert so_byte_tin(indent) == 2 + len('{"styles":[{"start":0,"len":2,"st":"ind_$","indentSize":2}]}')


def test_split_styled_message_spans_stay_exact_after_splitting_text_full_of_astral_characters() -> None:
    """(port) span đúng sau khi cắt tin đầy emoji ngoài BMP: mỗi lát cắt UTF-16 là đúng chữ đậm, không dính nửa cặp"""
    doc = "\n".join(f"{EMOJI} dòng {i} có **đậm {EMOJI} {i}** và {EMOJI}{EMOJI} hết" for i in range(30))
    goc = tu_markdown(doc)
    assert utf16_len(goc.text) > len(goc.text), "văn bản mẫu phải có ký tự ngoài BMP"

    for max_chars in (60, 99, 100, 101):
        phan = split_styled_message(goc, SplitOptions(max_chars=max_chars, max_parts=50))
        tong = 0
        for p in phan:
            assert utf16_len(p.text) <= max_chars
            for s in p.styles:
                assert s.start + s.length <= utf16_len(p.text)
                doan = utf16_slice(p.text, s.start, s.length)
                doan.encode("utf-8")  # raises on a lone surrogate: a span edge inside a pair
                assert doan.startswith("đậm"), doan
                assert doan.endswith(tuple("0123456789")), doan
                tong += 1
        assert tong == len(goc.styles), f"maxChars={max_chars}: mất hoặc thừa span"


def test_chia_theo_ngan_sach_byte_astral_text_keeps_every_message_under_the_budget() -> None:
    """(port) ngân sách byte đo đúng với emoji (4 byte UTF-8, 2 đơn vị UTF-16) và span vẫn nằm trong biên"""
    doc = "\n".join(f"- {EMOJI} Giải {i}: **{10000 + i}** {EMOJI} vé **{20000 + i}**" for i in range(60))
    goc = tu_markdown(doc)
    phan = chia_theo_ngan_sach_byte(
        goc, NganSachByteOptions(max_chars=2000, max_parts=8, max_payload_bytes=2800)
    )
    assert len(phan) > 1
    for p in phan:
        assert so_byte_tin(p) <= 2800
        for s in p.styles:
            assert s.start + s.length <= utf16_len(p.text)
            utf16_slice(p.text, s.start, s.length).encode("utf-8")
