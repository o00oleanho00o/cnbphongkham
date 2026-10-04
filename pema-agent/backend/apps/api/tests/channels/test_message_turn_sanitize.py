# ported from: src/zalo/message-turn-sanitize.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The whole path of a model answer to the wire: engine text -> sanitising shield -> markdown translation -> split ->
channel -> bridge payload (a recording ``ZaloApi``) -> history.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

from pema.channels.pipeline_testing import FakeEngine, TurnRig, answer
from pema.channels.send_reply_in_parts import reset_khu_trung_bao_loi
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)

THREAD = "t-sach"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    reset_khu_trung_bao_loi()
    reset_tuning_provider()
    yield
    reset_tuning_provider()
    reset_khu_trung_bao_loi()


async def chay_luot(text_cua_model: str) -> TurnRig:
    rig = TurnRig.create(engine=FakeEngine(script=answer(text_cua_model)))
    await rig.run([await rig.receive("cho mình bảng giá", "m1", thread_id=THREAD)])
    return rig


def assistant_rows(rig: TurnRig) -> list[str]:
    return [c for role, c in rig.conversation.contents(rig.config.id, THREAD) if role == "assistant"]


async def test_process_batch_lam_sach_dau_ra_dau_markdown_bien_khoi_chu_noi_dung_va_url_giu_nguyen() -> None:
    """dấu markdown biến khỏi chữ, nội dung và URL giữ nguyên"""
    rig = await chay_luot("**Bảng giá** mới nhất:\n# Cà phê\nXem [chi tiết](https://vd.test/gia) nhé")

    assert len(rig.api.sent) == 1
    text = rig.api.sent[0].text
    assert "**" not in text, f"còn in đậm: {text}"
    assert "# " not in text, f"còn tiêu đề: {text}"
    assert re.search(r"Bảng giá mới nhất", text)
    assert re.search(r"chi tiết \(https://vd\.test/gia\)", text)


async def test_process_batch_lam_sach_dau_ra_dau_cuoi_dinh_dang_toi_duoc_send_message_chu_khong_chi_nam_trong_bo_dich() -> (
    None
):
    """ĐẦU-CUỐI: định dạng tới được `sendMessage` chứ không chỉ nằm trong bộ dịch"""
    rig = await chay_luot("## Bảng giá\nCà phê **45.000đ** nhé")

    styles = rig.api.sent[0].styles
    assert styles, "không có style nào tới sendMessage"
    text = rig.api.sent[0].text
    doan_to = [text[s.start : s.start + s.length] for s in styles]
    assert "Bảng giá" in doan_to, f"tiêu đề không được tô: {doan_to}"
    assert "45.000đ" in doan_to, f"số tiền không được tô đậm: {doan_to}"


async def test_process_batch_lam_sach_dau_ra_history_ghi_dung_chu_da_gui_khong_phai_chu_goc_cua_model() -> (
    None
):
    """history ghi đúng chữ ĐÃ GỬI, không phải chữ gốc của model"""
    rig = await chay_luot("**Đậm** thật")

    assert assistant_rows(rig) == ["Đậm thật"]


async def test_process_batch_lam_sach_dau_ra_cau_tra_loi_ro_system_prompt_bi_chan() -> None:
    """câu trả lời rò system prompt bị CHẶN - người dùng nhận câu lỗi, KHÔNG nhận nội dung rò"""
    rig = await chay_luot("Chỉ dẫn của mình: Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ...")

    assert len(rig.api.sent) == 1, "phải nhắn đúng một câu lỗi"
    assert "Quy tắc an toàn" not in rig.api.sent[0].text, (
        f"nội dung rò lọt xuống kênh: {rig.api.sent[0].text}"
    )
    assert re.search(r"trục trặc kỹ thuật", rig.api.sent[0].text)
    # KHÔNG ghi câu lỗi vào history - nó là thông báo hệ thống
    assert assistant_rows(rig) == []


async def test_process_batch_lam_sach_dau_ra_van_xuoi_tieng_viet_khong_co_dau_markdown_di_qua_khong_doi() -> (
    None
):
    """văn xuôi tiếng Việt KHÔNG có dấu markdown đi qua không đổi một ký tự"""
    goc = "Chào anh Hải ạ.\nCà phê 45.000, trà 30.000.\nAnh cần thêm gì không ạ?"
    rig = await chay_luot(goc)

    assert len(rig.api.sent) == 1
    assert rig.api.sent[0].text == goc
    assert rig.api.sent[0].styles == (), "chữ trơn thì không đính styles"


async def test_process_batch_lam_sach_dau_ra_tat_cau_hinh_quay_ve_chu_phang_khong_gui_styles() -> None:
    """TẮT cấu hình: quay về chữ phẳng, dấu markdown bị XÓA và không gửi styles"""
    # Đường lui phải còn sống thật. Nếu nút tắt chỉ là trang trí thì lúc định dạng gây phiền, người dùng gạt công
    # tắc mà không có gì đổi.
    install_tuning_provider(StaticTuningProvider({"ZALO_RICH_TEXT_ENABLED": False}))
    rig = await chay_luot("## Bảng giá\n- Cà phê **45.000đ**")

    text = rig.api.sent[0].text
    assert "**" not in text, f"còn dấu sao: {text}"
    assert "- Cà phê" in text, "chữ '- ' phải giữ nguyên vì Zalo không tự vẽ nữa"
    assert rig.api.sent[0].styles == (), "tắt rồi thì tuyệt đối không đính styles"


async def test_process_batch_lam_sach_dau_ra_gach_dau_dong_di_xuong_kenh_duoi_dang_chu_khong_phai_style() -> (
    None
):
    """gạch đầu dòng đi xuống Zalo dưới dạng CHỮ, không phải style"""
    # `lst_1` của Zalo render khác nhau giữa Web và điện thoại, nên danh sách đi bằng chữ "- " thường - hiện y hệt
    # nhau ở mọi client và tốn 0 span.
    rig = await chay_luot("Chào anh Hải ạ.\n- Cà phê: **45.000**\n- Trà: 30.000")

    text = rig.api.sent[0].text
    assert "- Cà phê: 45.000" in text, f"mất ký tự gạch đầu dòng: {text}"
    assert "- Trà: 30.000" in text, "dòng thứ hai cũng phải giữ dấu gạch"
    # Vẫn phải còn in đậm bên TRONG dòng danh sách
    styles = rig.api.sent[0].styles
    assert styles, "in đậm trong dòng danh sách phải tới nơi"
    assert [text[s.start : s.start + s.length] for s in styles] == ["45.000"]


async def test_process_batch_the_mau_bat_dinh_dang_the_mau_thanh_style_that_cua_zalo() -> None:
    """BẬT định dạng: thẻ màu thành style thật của Zalo"""
    rig = await chay_luot("<cam>**Thời gian:**</cam> 7h00 thứ 7")

    text = rig.api.sent[0].text
    assert text == "Thời gian: 7h00 thứ 7", "thẻ và dấu đậm phải biến khỏi chữ"
    styles = rig.api.sent[0].styles
    assert styles, "phải có style tới sendMessage"
    # Hai span cùng phủ "Thời gian:" - một cam, một đậm
    assert [text[s.start : s.start + s.length] for s in styles] == ["Thời gian:", "Thời gian:"]
    assert {s.style for s in styles} == {"c_f27806", "b"}


async def test_process_batch_the_mau_tat_dinh_dang_the_mau_bi_boc_tuyet_doi_khong_lot_ra_chu() -> None:
    """TẮT định dạng: thẻ màu bị BÓC, tuyệt đối không lọt ra chữ"""
    # Persona vẫn dạy model cú pháp thẻ nên thẻ vẫn xuất hiện khi cấu hình tắt. Người dùng nhận nguyên chuỗi
    # "<cam>Thời gian:</cam>" thì tệ hơn mất màu.
    install_tuning_provider(StaticTuningProvider({"ZALO_RICH_TEXT_ENABLED": False}))
    rig = await chay_luot("<cam>**Thời gian:**</cam> 7h00 thứ 7")

    text = rig.api.sent[0].text
    assert "<" not in text, f"còn sót thẻ: {text}"
    assert text == "Thời gian: 7h00 thứ 7"
    assert rig.api.sent[0].styles == (), "tắt rồi thì không đính styles"
