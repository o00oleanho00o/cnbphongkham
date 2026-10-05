"""Red-flag detector: bleeding, fever, pus, dyspnoea; diacritics, no diacritics, abbreviations, typos.

New tests (no zalo-agent original). Every sentence is fictional. The positive table is the part that
protects patients (a miss is the expensive error); the negative table is what keeps the doctor from
being flooded by everyday Vietnamese ("sốt ruột", "đội mũ", "màu cam").
"""

from __future__ import annotations

import pytest

from pema.policy.redflags import (
    BLEEDING,
    DYSPNEA,
    FEVER,
    PROVISIONAL_CATEGORIES,
    PUS,
    REQUIRED_CATEGORIES,
    SEVERE_ALLERGY,
    VASCULAR_VISION,
    catalog,
    detect_red_flags,
    detect_red_flags_in_batch,
)

BLEEDING_TEXTS = [
    "Em bị chảy máu nhiều sau khi laser",
    "chảy máu không ngừng bác sĩ ơi",
    "chay mau",
    "chay mau nhieu qua",
    "CHẢY MÁU RỒI",
    "chayyy maauu",
    "ch.ảy m.áu",
    "chảy máu ra bông",
    "rỉ máu ở chỗ tiêm",
    "ri mau o cho tiem",
    "vết thương cứ ra máu",
    "vet thuong ra mau",
    "máu chảy không cầm được",
    "mau chay khong ngung",
    "không cầm được máu",
    "khong cam duoc mau",
    "băng thấm máu hết rồi",
    "bang tham mau het roi",
    "chảy máu cam",
    "xuất huyết dưới da",
    "xuat huyet",
    "ho ra máu",
    "mất máu nhiều",
    "chảy mầu",  # wrong tone: màu for máu
    "chảy mấu",
    "vết thương có máu",
    "vet thuong co mau",
    "da mới nặn mụn bị máu",
]

FEVER_TEXTS = [
    "em bị sốt",
    "bi sot cao",
    "sốt cao từ đêm qua",
    "sot 39 do",
    "sốt 38.5 độ",
    "sốt 38,5",
    "nhiệt độ 39 độ C",
    "nhiet do la 38.2",
    "đo được 38 độ",
    "37.8 độ sau khi tiêm",
    "đo thấy 40°C",
    "38*",
    "S0T cao",
    "sốtt",
    "SỐT",
    "nóng người từ chiều",
    "nguoi nong ran",
    "cả người nóng",
    "ớn lạnh run người",
    "on lanh",
    "run lạnh từ sáng",
    "rét run",
    "lên cơn sốt",
    "phát sốt",
    "chưa hết sốt",
    "vẫn chưa hết sốt",
    "không hết sốt",
    "sốt xuất huyết",
]

PUS_TEXTS = [
    "vết thương mưng mủ",
    "vet thuong mung mu",
    "mưng mũ",  # wrong tone
    "mung mu",
    "chảy mủ ở chỗ nặn",
    "chay mu",
    "có mủ vàng",
    "co mu vang",
    "ra mủ",
    "bị mủ ở vết tiêm",
    "mủ xanh",
    "mu duc",
    "nốt mụn đọng mủ",
    "mụn có mu o vet thuong",  # no tone mark on a short word: context decides
    "vết thương nhiễm trùng",
    "nhiem trung roi",
    "nhiễm khuẩn",
    "áp xe",
    "ap xe duoi da",
    "sưng nóng đỏ đau",
    "sung nong do dau",
    "sưng tấy",
    "chảy dịch vàng",
    "dịch đục",
    "vết thương có mùi hôi",
    "mui thoi o vet thuong",
]

DYSPNEA_TEXTS = [
    "em khó thở",
    "kho tho",
    "khó thở quá",
    "KHÓ THỞ",
    "khoooo thở",
    "khó thờ",  # typo
    "kho thơ",  # typo
    "thở khó",
    "khong tho duoc",
    "không thở được",
    "k thở được",
    "ko thở nổi",
    "hok thở đc nữa",
    "kg tho dc",
    "thở không nổi",
    "tho khong noi",
    "thở dốc",
    "thở gấp",
    "thở hổn hển",
    "thở khò khè",
    "hụt hơi",
    "nghẹt thở",
    "ngạt thở",
    "ngộp thở",
    "nghẹn họng",
    "khó nuốt",
    "tức ngực",
    "nặng ngực",
    "đau ngực",
    "dau that nguc",
]


@pytest.mark.parametrize("text", BLEEDING_TEXTS)
def test_bleeding_is_flagged(text: str) -> None:
    """chảy máu và các biến thể (có dấu, không dấu, sai dấu, kéo dài chữ) bị gắn cờ"""
    assert BLEEDING in detect_red_flags(text).flags


@pytest.mark.parametrize("text", FEVER_TEXTS)
def test_fever_is_flagged(text: str) -> None:
    """sốt và các biến thể (nhiệt độ, ớn lạnh, viết hoa/lẫn số 0) bị gắn cờ"""
    assert FEVER in detect_red_flags(text).flags


@pytest.mark.parametrize("text", PUS_TEXTS)
def test_pus_is_flagged(text: str) -> None:
    """mưng mủ, mủ và các biến thể (nhiễm trùng, áp xe, sưng nóng đỏ đau) bị gắn cờ"""
    assert PUS in detect_red_flags(text).flags


@pytest.mark.parametrize("text", DYSPNEA_TEXTS)
def test_dyspnea_is_flagged(text: str) -> None:
    """khó thở và các biến thể (viết tắt, không dấu, thở dốc, tức ngực) bị gắn cờ"""
    assert DYSPNEA in detect_red_flags(text).flags


@pytest.mark.parametrize(
    "text",
    [
        "em không sốt, không chảy máu, vết thương khô rồi ạ",
        "không bị sốt",
        "không sốt",
        "hết sốt rồi ạ",
        "em hết sốt hôm qua",
        "không chảy máu",
        "không bị chảy máu nhiều",
        "chưa thấy chảy máu",
        "không có mủ",
        "không thấy mưng mủ",
        "không bị khó thở",
        "không khó thở",
        "không nhiễm trùng",
        "không đau ngực",
    ],
)
def test_negation_directly_before_the_keyword_suppresses_the_hit(text: str) -> None:
    """phủ định ngay trước từ khóa ("không sốt", "hết sốt") không gọi bác sĩ"""
    result = detect_red_flags(text)
    assert not result.triggered
    assert result.suppressed, "the negated hit is still reported for logs and evals"


@pytest.mark.parametrize(
    "text",
    [
        "không sốt nhưng chảy máu nhiều",
        "không chảy máu mà sốt cao",
        "chưa hết sốt",
        "không hết sốt",
        "vẫn chưa hết sốt",
        "không thở được",  # an inherently negative rule is never negated
        "không thở nổi",
        "ko thở được nữa",
        "em không sốt, nhưng khó thở",
    ],
)
def test_negation_never_hides_a_flag_that_is_still_present(text: str) -> None:
    """phủ định không được che cờ vẫn còn: "chưa hết sốt", "không thở được", "không sốt nhưng chảy máu\""""
    assert detect_red_flags(text).triggered


@pytest.mark.parametrize(
    "text",
    [
        "em sốt ruột quá bác sĩ ơi",
        "sot ruot qua",
        "em đội mũ che nắng",
        "doi mu khi ra nang",
        "mua mu moi",
        "con sot lai it thuoc",
        "còn sót lại một ít kem",
        "da em có màu cam",
        "tông màu cam đẹp",
        "ra màu nhiều quá",
        "xốt mayonnaise",
        "sốt dẻo",
        "em rửa mặt bằng nước 40 độ",
        "ngoài trời 40 độ",
        "phòng 28 độ C",
        "đặt lịch thứ 7 được không ạ",
        "kiểm tra giúp em lịch hẹn",
        "bác sĩ ơi em muốn hỏi giá",
        "cảm ơn bác sĩ nhiều",
        "da em hơi đỏ và nóng rát sau laser",
        "mụn ẩn nhiều quá",
        "xin giá gói trị nám",
        "",
        "   ",
    ],
)
def test_everyday_words_do_not_flood_the_doctor(text: str) -> None:
    """những từ đời thường (sốt ruột, mũ, màu cam, nước 40 độ) không bị gắn cờ nhầm"""
    assert not detect_red_flags(text).triggered


def test_flags_are_distinct_categories_most_urgent_first() -> None:
    """kết quả trả mã nhóm không trùng, nhóm khẩn nhất đứng đầu"""
    result = detect_red_flags("em khó thở, chảy máu và sốt cao, vết thương mưng mủ")
    assert result.flags == (DYSPNEA, BLEEDING, FEVER, PUS)


def test_batch_with_one_red_flag_message_triggers() -> None:
    """một tin cờ đỏ trong cả lô là đủ gọi bác sĩ"""
    batch = ["chào bác sĩ", "em muốn đặt lịch", "à mà em đang sốt cao"]
    assert detect_red_flags_in_batch(batch).flags == (FEVER,)


def test_batch_of_ordinary_messages_does_not_trigger() -> None:
    """lô tin bình thường không gọi bác sĩ"""
    assert not detect_red_flags_in_batch(["chào", "giá laser bao nhiêu", "cảm ơn"]).triggered


def test_decomposed_unicode_is_matched() -> None:
    """chữ Unicode dạng tổ hợp (NFD) vẫn khớp như dạng dựng sẵn"""
    import unicodedata

    assert FEVER in detect_red_flags(unicodedata.normalize("NFD", "em bị sốt cao")).flags


def test_result_never_carries_message_text() -> None:
    """kết quả chỉ chứa mã quy tắc và nhóm, không chứa nội dung tin nhắn"""
    secret = "chảy máu tại số 12 đường Lê Lợi"
    result = detect_red_flags(secret)
    rendered = repr(result)
    assert "Lê Lợi" not in rendered
    assert "12" not in rendered


def test_the_four_required_categories_and_the_provisional_ones_are_declared() -> None:
    """bốn nhóm bắt buộc theo PLAN mục 5; hai nhóm bổ sung ghi rõ là tạm, chờ bác sĩ duyệt"""
    assert set(REQUIRED_CATEGORIES) == {BLEEDING, FEVER, PUS, DYSPNEA}
    assert set(PROVISIONAL_CATEGORIES) == {SEVERE_ALLERGY, VASCULAR_VISION}
    entries = {entry.category: entry for entry in catalog()}
    assert set(entries) == set(REQUIRED_CATEGORIES) | set(PROVISIONAL_CATEGORIES)
    assert all(entries[c].labels for c in entries)
    assert all(entries[c].provisional for c in PROVISIONAL_CATEGORIES)
    assert not any(entries[c].provisional for c in REQUIRED_CATEGORIES)


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("môi sưng to, phù mặt", SEVERE_ALLERGY),
        ("sốc phản vệ", SEVERE_ALLERGY),
        ("em bị ngất xỉu", SEVERE_ALLERGY),
        ("da chuyển tím tái sau tiêm", VASCULAR_VISION),
        ("nhìn mờ đột ngột", VASCULAR_VISION),
        ("đau dữ dội sau khi tiêm", VASCULAR_VISION),
        ("hoại tử", VASCULAR_VISION),
    ],
)
def test_provisional_categories_are_flagged(text: str, category: str) -> None:
    """hai nhóm bổ sung (dị ứng nặng, mạch máu/thị lực) được gắn cờ"""
    assert category in detect_red_flags(text).flags


# ------------------------------------------------------------------ package G (SECURITY-REVIEW-AI01 SEC-02)
@pytest.mark.parametrize(
    "texts",
    [
        ["em bị chảy", "máu"],
        ["chay", "mau nhieu"],
        ["Dạ em thấy khó", "thở quá"],
        ["em bị", "sốt"],
    ],
)
def test_a_sign_split_over_two_messages_of_one_batch_is_flagged(texts: list[str]) -> None:
    """dấu hiệu bị tách làm hai tin trong cùng lượt vẫn bị bắt (mô hình đọc hai dòng liền nhau)"""
    assert detect_red_flags_in_batch(texts).triggered


@pytest.mark.parametrize(
    "text",
    [
        "ｃｈａｙ ｍａｕ",  # full-width letters
        "chảy​ máu",  # zero width space next to a real space
        "chảy ​máu",
        "ch​ảy m‍áu",
        "chảy máu",  # no-break space
        "chảy　máu",  # ideographic space
        "k​hó thở",
        "em bị 𝐬ốt",  # mathematical bold letter
    ],
)
def test_unicode_tricks_do_not_hide_a_red_flag(text: str) -> None:
    """chữ toàn chiều rộng, ký tự vô hình, khoảng trắng lạ không che được cờ đỏ"""
    assert detect_red_flags(text).triggered


@pytest.mark.parametrize(
    "text",
    ["bớt chảy máu rồi nhưng vẫn còn", "bớt sốt nhưng vẫn mệt", "bot chay mau"],
)
def test_less_is_not_gone_so_it_does_not_suppress_a_flag(text: str) -> None:
    """ "bớt" nghĩa là còn, không phải hết: không được coi là phủ định"""
    assert detect_red_flags(text).triggered


@pytest.mark.parametrize(
    "text",
    [
        "there is bleeding from the wound",
        "I have a fever since last night",
        "the wound is infected and full of pus",
        "I can't breathe",
        "short of breath after the injection",
        "difficulty breathing",
    ],
)
def test_english_messages_are_flagged(text: str) -> None:
    """bệnh nhân viết tiếng Anh vẫn được bắt cờ đỏ"""
    assert detect_red_flags(text).triggered


def test_ordinary_text_still_passes_after_the_hardening() -> None:
    """tin bình thường vẫn không bị bắt oan sau khi siết"""
    batch = ["chào bác sĩ", "em muốn đặt lịch", "sốt ruột quá", "màu cam"]
    assert not detect_red_flags_in_batch(batch).triggered
