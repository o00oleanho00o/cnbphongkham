"""PII mask: phone (many shapes), CCCD/CMND, e-mail, address, birth date, name -> reference code, restore.

New tests (no zalo-agent original). All numbers, names, e-mails and addresses are fictional: the
phone numbers use real mobile prefixes only because the validator needs them; none is assigned to anyone
on purpose.
"""

from __future__ import annotations

import pytest

from pema.policy.pii import (
    HIDDEN,
    KnownName,
    MaskSession,
    MaskVault,
    PiiKind,
    extract_vn_phones,
    mask_pii,
    normalize_vn_phone,
)

PHONE_TEXTS = [
    ("SĐT em 0901234567 nhé", "0901234567"),
    ("sdt 0901234567", "0901234567"),
    ("sđt: 0901234567", "0901234567"),
    ("số điện thoại là 0901234567", "0901234567"),
    ("0901 234 567", "234 567"),
    ("090 123 4567", "123 4567"),
    ("090.123.4567", "123.4567"),
    ("090-123-4567", "123-4567"),
    ("(090) 123-4567", "123-4567"),
    ("0 9 0 1 2 3 4 5 6 7", "2 3 4 5 6 7"),
    ("+84901234567", "84901234567"),
    ("+84 90 123 4567", "123 4567"),
    ("+84 0901234567", "0901234567"),
    ("84901234567", "84901234567"),
    ("0084901234567", "0084901234567"),
    ("zalo 84 90 123 45 67", "123 45 67"),
    ("gọi em số 0912345678 nhé", "0912345678"),
    ("0359876543", "0359876543"),
    ("0587654321", "0587654321"),
    ("0765432198", "0765432198"),
    ("0834567891", "0834567891"),
    ("số bàn 02838123456", "02838123456"),
    ("028 3812 3456", "3812 3456"),
    ("không chín không một hai ba bốn năm sáu bảy", "hai ba bốn năm"),
    ("khong chin khong mot hai ba bon nam sau bay", "hai ba bon nam"),
    ("không chín không một hai ba bốn năm sáu bảy.", "hai ba bốn năm"),
    ("sdt 912345678", "912345678"),
    ("liên hệ: 0901.234.567 hoặc 0912-345-678", "0912-345-678"),
    ("sdt:0901234567,", "0901234567"),
    ("SDT0901234567", "0901234567"),
    ("dt 0901234567", "0901234567"),
    ("hotline 090 1234 567 giúp em", "1234 567"),
]


@pytest.mark.parametrize(("text", "secret"), PHONE_TEXTS)
def test_phone_numbers_are_masked(text: str, secret: str) -> None:
    """che SĐT mọi dạng: 0xxx, +84, 84, 0084, dấu cách/chấm/gạch, số bàn, đọc bằng chữ"""
    result = mask_pii(text)
    assert secret not in result.text
    assert "[SDT_1]" in result.text
    assert result.counts[PiiKind.PHONE] >= 1


def test_the_same_phone_gets_the_same_placeholder_and_a_different_one_a_new_number() -> None:
    """cùng một số điện thoại cùng một mã; số khác mã khác"""
    session = MaskSession()
    first = session.mask("gọi 0901234567 hoặc 0912345678").text
    second = session.mask("nhắc lại 090 123 4567").text
    assert first == "gọi [SDT_1] hoặc [SDT_2]"
    assert second == "nhắc lại [SDT_1]"


@pytest.mark.parametrize(
    "text",
    [
        "hẹn thứ 7 ngày 20/09/2026 lúc 10:30",
        "gói trị nám giá 1.500.000 đồng",
        "tổng 150.000.000 đồng",
        "tiêm 5 cc nước muối",
        "mã đơn 12345",
        "sau 3 buổi, mỗi buổi cách 14 ngày",
        "em 30 tuổi nặng 52 kg",
        "lúc 14h30 chiều nay",
        "đơn DN-1042 đã duyệt",
        "2026-09-20T09:00:00+07:00",
        "0123456789",  # not a Vietnamese mobile prefix
        "1900 1234",
        "",
    ],
)
def test_ordinary_numbers_are_left_alone(text: str) -> None:
    """ngày giờ, tiền, số lượng, mã đơn không bị che nhầm thành SĐT"""
    assert mask_pii(text).text == text


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("cccd 079203123456", "079203123456"),
        ("CCCD: 079 203 123 456", "079 203 123 456"),
        ("079203123456", "079203123456"),
        ("số căn cước công dân của em là 001201987654", "001201987654"),
        ("cmnd 123456789", "123456789"),
        ("CMND số 123456789 của em", "123456789"),
        ("chứng minh nhân dân 123 456 789", "123 456 789"),
        ("123456789 là cmnd của em", "123456789"),
        ("số định danh 079203123456", "079203123456"),
    ],
)
def test_national_ids_are_masked(text: str, secret: str) -> None:
    """che CCCD 12 số và CMND 9 số (khi có từ khóa), không dấu cách hay có dấu cách"""
    result = mask_pii(text)
    assert secret not in result.text
    assert "[CCCD_1]" in result.text


def test_a_nine_digit_number_without_a_keyword_is_not_taken_for_an_id() -> None:
    """số 9 chữ số không có từ khóa không bị coi là CMND (tránh che nhầm mã đơn)"""
    assert mask_pii("mã giao dịch 123456789 ạ").text == "mã giao dịch 123456789 ạ"


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("mail em abc.def@gmail.com ạ", "abc.def@gmail.com"),
        ("EMAIL: Nguyen.Van_A+spa@Example.co.uk", "Nguyen.Van_A+spa@Example.co.uk"),
        ("abc.def at gmail dot com", "abc.def at gmail dot com"),
        ("abc(at)gmail.com", "abc(at)gmail.com"),
        ("abc a còng gmail chấm com", "abc a còng gmail chấm com"),
        ("lien he: test_01@mail.vn.", "test_01@mail.vn"),
    ],
)
def test_emails_are_masked(text: str, secret: str) -> None:
    """che e-mail, kể cả viết lách "at/dot", "a còng/chấm\""""
    result = mask_pii(text)
    assert secret not in result.text
    assert "[EMAIL_1]" in result.text


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("em ở số 12 ngõ 5 đường Lê Lợi, phường Bến Nghé, quận 1", "Lê Lợi"),
        ("so 12 ngo 5 duong le loi", "le loi"),
        ("nhà 45/7 hẻm 12 Nguyễn Trãi p5 q3", "Nguyễn Trãi"),
        ("12A đường Hai Bà Trưng", "Hai Bà Trưng"),
        ("số nhà 8 phố Huế", "phố Huế"),
        ("địa chỉ nhà em là 8 đường Hai Bà Trưng quận 3", "Hai Bà Trưng"),
        ("địa chỉ: chung cư Sunrise tòa A tầng 12 phòng 1203", "Sunrise"),
        ("tòa A2 tầng 15", "A2"),
        ("căn hộ 1203 block B", "1203"),
        ("số 15 ấp 3 xã Tân Thạnh", "Tân Thạnh"),
        ("đường Lê Lợi số 12", "Lê Lợi"),
        ("giao hàng đến 99 khu phố 4, phường 7", "khu phố 4"),
    ],
)
def test_specific_addresses_are_masked(text: str, secret: str) -> None:
    """che địa chỉ cụ thể: số nhà + đường/ngõ/hẻm, tòa/tầng/phòng, kèm phường quận"""
    result = mask_pii(text)
    assert secret not in result.text
    assert "[DIACHI_1]" in result.text


@pytest.mark.parametrize(
    "text",
    [
        "địa chỉ phòng khám ở đâu ạ?",
        "địa chỉ của phòng khám là gì",
        "phòng khám ở Hà Nội hay TP.HCM",
        "em ở TP.HCM",
        "em đang ở quận 1",
        "tầng 2 có thang máy không",
        "tăng 2 lần liều",
        "phòng khám có phòng chờ không",
    ],
)
def test_clinic_questions_and_coarse_places_are_not_masked_as_addresses(text: str) -> None:
    """câu hỏi về địa chỉ phòng khám và tên thành phố/quận đơn thuần không bị che"""
    assert mask_pii(text).text == text


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("sinh ngày 12/05/1990", "12/05/1990"),
        ("ngày sinh: 12-05-1990", "12-05-1990"),
        ("DOB 12.05.1990", "12.05.1990"),
        ("em sinh ngày 3 tháng 7 năm 1988", "3 tháng 7 năm 1988"),
        ("sinh 01/02/95", "01/02/95"),
    ],
)
def test_birth_dates_are_masked_but_appointment_dates_are_not(text: str, secret: str) -> None:
    """che ngày sinh khi có từ khóa; ngày hẹn khám giữ nguyên"""
    result = mask_pii(text)
    assert secret not in result.text
    assert "[NGAYSINH_1]" in result.text
    assert mask_pii("hẹn khám ngày 12/05/2026").text == "hẹn khám ngày 12/05/2026"


# ----------------------------------------------------------------------------------- names
def test_known_patient_name_becomes_the_patient_code() -> None:
    """tên bệnh nhân đã xác minh được thay bằng mã tham chiếu [KH_P025]"""
    known = [KnownName("Nguyễn Thị Hoa", "P025")]
    assert mask_pii("Chào chị Hoa, em là Nguyễn Thị Hoa", known).text == "Chào chị [KH_P025], em là [KH_P025]"
    assert mask_pii("nguyen thi hoa dat lich", known).text == "[KH_P025] dat lich"
    assert mask_pii("NGUYỄN THỊ HOA", known).text == "[KH_P025]"


def test_a_common_noun_that_is_not_preceded_by_a_title_is_not_a_name() -> None:
    """chữ "hoa" đứng một mình (không có chị/anh/em đằng trước) không bị che"""
    known = [KnownName("Nguyễn Thị Hoa", "P025")]
    assert mask_pii("em muốn mua hoa tặng mẹ", known).text == "em muốn mua hoa tặng mẹ"


def test_too_short_known_name_is_ignored() -> None:
    """tên quá ngắn ("A") bị bỏ qua, nếu không sẽ che mọi chữ a"""
    assert mask_pii("a ơi cho em hỏi a", [KnownName("A")]).text == "a ơi cho em hỏi a"


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("tên em là Nguyễn Thị Hoa ạ", "Nguyễn Thị Hoa"),
        ("Tên mình là Trần Văn Bình", "Trần Văn Bình"),
        ("em là Phạm Minh Anh, 30 tuổi", "Phạm Minh Anh"),
        ("tôi là Lê Quốc Dũng", "Lê Quốc Dũng"),
        ("tôi tên là Lan", "Lan"),
        ("tên là Hoàng", "Hoàng"),
    ],
)
def test_introduced_names_become_person_placeholders(text: str, name: str) -> None:
    """tên tự giới thiệu ("tên em là ...", "em là ...") được thay bằng [NGUOI_n]"""
    result = mask_pii(text)
    assert name not in result.text
    assert "[NGUOI_1]" in result.text


@pytest.mark.parametrize("text", ["em là khách cũ", "mình là người mới", "em là bệnh nhân", "tôi là ai"])
def test_ordinary_sentences_with_la_are_not_names(text: str) -> None:
    """câu thường có "em là ..." không bị che nhầm thành tên"""
    assert mask_pii(text).text == text


def test_one_known_name_in_two_forms_is_one_placeholder() -> None:
    """ "chị Hoa" và "Nguyễn Thị Hoa" là một người, một mã"""
    session = MaskSession()
    session.add_known_name(KnownName("Nguyễn Thị Hoa"))
    text = session.mask("Nguyễn Thị Hoa hỏi, chị Hoa nhắn tiếp").text
    assert text == "[NGUOI_1] hỏi, chị [NGUOI_1] nhắn tiếp"


# --------------------------------------------------------------------------- combined / overlaps
def test_every_kind_in_one_message() -> None:
    """một tin có đủ SĐT, CCCD, e-mail, địa chỉ, ngày sinh, tên: tất cả bị che, câu hỏi còn nguyên"""
    text = (
        "Em là Nguyễn Thị Hoa, sinh ngày 12/05/1990, sdt 0901234567, cccd 079203123456, "
        "mail hoa.test@gmail.com, ở số 12 ngõ 5 đường Lê Lợi quận 1. Cho em hỏi giá laser nhé"
    )
    masked = mask_pii(text, [KnownName("Nguyễn Thị Hoa", "P025")]).text
    for secret in (
        "Nguyễn Thị Hoa",
        "12/05/1990",
        "0901234567",
        "079203123456",
        "hoa.test@gmail.com",
        "Lê Lợi",
    ):
        assert secret not in masked
    assert masked.endswith("Cho em hỏi giá laser nhé")
    for label in ("KH_P025", "NGAYSINH_1", "SDT_1", "CCCD_1", "EMAIL_1", "DIACHI_1"):
        assert label in masked


def test_masking_is_idempotent() -> None:
    """che lần hai trên văn bản đã che không đổi gì"""
    session = MaskSession()
    once = session.mask("sdt 0901234567, mail a.b@c.vn").text
    assert session.mask(once).text == once


def test_text_without_pii_is_returned_unchanged() -> None:
    """văn bản không có PII được trả nguyên văn"""
    text = "Cho em hỏi laser CO2 trị sẹo rỗ có đau không ạ, giá thế nào?"
    result = mask_pii(text)
    assert result.text == text
    assert not result.changed


def test_decomposed_unicode_input_is_masked_in_nfc_form() -> None:
    """chữ Unicode tổ hợp vẫn được che; kết quả là dạng NFC"""
    import unicodedata

    text = unicodedata.normalize("NFD", "địa chỉ nhà em là 8 đường Hai Bà Trưng")
    masked = mask_pii(text).text
    assert "Hai Bà Trưng" not in masked
    assert unicodedata.is_normalized("NFC", masked)


# ---------------------------------------------------------------------------------- restore
def test_restore_puts_back_names_only() -> None:
    """khôi phục chỉ trả lại TÊN; SĐT/CCCD/e-mail/địa chỉ/ngày sinh luôn thành [đã ẩn]"""
    session = MaskSession()
    session.add_known_name(KnownName("Nguyễn Thị Hoa", "P025"))
    session.mask("Em là Phạm Minh Anh, chị Hoa đây, sdt 0901234567, mail a@b.vn, ở 8 đường Hai Bà Trưng")
    restored = session.restore("Chào [KH_P025] và [NGUOI_1], em gọi [SDT_1], gửi [EMAIL_1] tới [DIACHI_1]")
    assert restored == f"Chào Nguyễn Thị Hoa và Phạm Minh Anh, em gọi {HIDDEN}, gửi {HIDDEN} tới {HIDDEN}"


def test_restore_tolerates_the_forms_a_model_writes() -> None:
    """mô hình viết [kh_p025], KH_P025, [ NGUOI_1 ] vẫn khôi phục đúng"""
    session = MaskSession()
    session.add_known_name(KnownName("Nguyễn Thị Hoa", "P025"))
    session.mask("tên em là Phạm Minh Anh")
    out = session.restore("[kh_p025] / KH_P025 / [ NGUOI_1 ]")
    assert out == "Nguyễn Thị Hoa / Nguyễn Thị Hoa / Phạm Minh Anh"


def test_restore_hides_placeholders_the_model_invented() -> None:
    """mã giữ chỗ mô hình tự bịa hoặc của người khác không được khôi phục"""
    session = MaskSession()
    session.add_known_name(KnownName("Nguyễn Thị Hoa", "P025"))
    out = session.restore("[KH_P999] [NGUOI_7] [SDT_9] KH_P998")
    assert out == f"{HIDDEN} {HIDDEN} {HIDDEN} {HIDDEN}"


def test_restore_leaves_ordinary_text_alone() -> None:
    """khôi phục không đụng vào chữ thường (kể cả chữ "KH" đứng riêng)"""
    session = MaskSession()
    assert session.restore("KH hẹn thứ 7, gọi 1900 ạ") == "KH hẹn thứ 7, gọi 1900 ạ"


def test_session_keeps_no_phone_or_id_in_memory() -> None:
    """phiên che không giữ bản gốc của SĐT/CCCD/e-mail/địa chỉ (chỉ giữ tên để khôi phục)"""
    session = MaskSession()
    session.mask(
        "sdt 0901234567 cccd 079203123456 mail a@b.vn ở 8 đường Hai Bà Trưng, tên em là Phạm Minh Anh"
    )
    dump = repr(vars(session))
    for secret in ("0901234567", "079203123456", "a@b.vn", "Hai Bà Trưng"):
        assert secret not in dump
    assert "Phạm Minh Anh" in dump  # names are the only thing kept, to restore them


def test_mask_name_gives_a_prompt_field_the_same_placeholder_as_the_text() -> None:
    """tên người gửi trong prompt dùng cùng mã giữ chỗ với trong tin nhắn"""
    session = MaskSession()
    session.add_known_name(KnownName("Nguyễn Thị Hoa", "P025"))
    assert session.mask_name("Nguyễn Thị Hoa") == "[KH_P025]"
    first = session.mask_name("Phạm Minh Anh")
    assert first == "[NGUOI_1]"
    assert session.mask("em là Phạm Minh Anh").text == "em là [NGUOI_1]"


# ------------------------------------------------------------------------------------ vault
class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_vault_returns_the_same_session_for_the_same_thread() -> None:
    """cùng một luồng chat dùng chung một phiên che (mã giữ chỗ ổn định giữa các lượt)"""
    vault = MaskVault()
    token_a, session_a = vault.session_for("clinic:acc:thread")
    token_b, session_b = vault.session_for("clinic:acc:thread")
    token_c, _ = vault.session_for("clinic:acc:other")
    assert token_a == token_b != token_c
    assert session_a is session_b
    assert vault.get(token_a) is session_a
    assert vault.get(None) is None
    assert vault.get("nope") is None


def test_vault_expires_sessions_after_the_ttl() -> None:
    """phiên hết hạn sau TTL: tên không nằm lại trong bộ nhớ mãi mãi"""
    clock = _Clock()
    vault = MaskVault(ttl_seconds=60, clock=clock)
    token, _ = vault.session_for("k")
    clock.now = 59
    assert vault.get(token) is not None
    clock.now = 59 + 61
    assert vault.get(token) is None
    assert len(vault) == 0


def test_vault_is_bounded() -> None:
    """kho phiên có trần số lượng; phiên cũ nhất bị bỏ trước"""
    vault = MaskVault(max_sessions=3)
    tokens = [vault.session_for(f"k{i}")[0] for i in range(5)]
    assert len(vault) == 3
    assert vault.get(tokens[0]) is None
    assert vault.get(tokens[-1]) is not None


# -------------------------------------------------------------------------- phone helpers
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0901234567", "0901234567"),
        ("090 123 4567", "0901234567"),
        ("+84901234567", "0901234567"),
        ("+84 0901234567", "0901234567"),
        ("84901234567", "0901234567"),
        ("0084901234567", "0901234567"),
        ("028 3812 3456", "02838123456"),
        ("0123456789", None),
        ("12345", None),
        ("", None),
        ("abc", None),
    ],
)
def test_normalize_vn_phone(raw: str, expected: str | None) -> None:
    """chuẩn hóa SĐT về dạng 0xxxxxxxxx; chuỗi không phải SĐT trả None"""
    assert normalize_vn_phone(raw) == expected


def test_extract_vn_phones_returns_distinct_valid_numbers_in_order() -> None:
    """lấy các SĐT hợp lệ không trùng theo thứ tự xuất hiện; số sai bị bỏ"""
    text = "gọi 0912345678 hoặc +84 90 123 4567, nhắc lại 0912 345 678, sdt cũ 12345678"
    assert extract_vn_phones(text) == ["0912345678", "0901234567"]
