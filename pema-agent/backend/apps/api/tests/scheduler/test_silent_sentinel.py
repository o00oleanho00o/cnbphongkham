# ported from: src/scheduler/silent-sentinel.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module: no DB, no env.
"""

from __future__ import annotations

from pema.scheduler.silent_sentinel import is_silent_response, la_dong_sentinel


def test_is_silent_response_whole_answer_is_only_silent_is_swallowed() -> None:
    """toàn bộ câu trả lời chỉ là [SILENT] thì nuốt"""
    assert is_silent_response("[SILENT]") is True
    assert is_silent_response("  [SILENT]  ") is True  # trim the extra whitespace
    assert is_silent_response("[silent]") is True  # case-insensitive


def test_is_silent_response_silent_alone_on_first_line_is_swallowed_other_content_lines_are_fine() -> None:
    """[SILENT] đứng riêng ở dòng ĐẦU thì nuốt, dòng khác có nội dung vẫn được"""
    assert is_silent_response("[SILENT]\n\nKhông có gì thêm.") is True


def test_is_silent_response_silent_alone_on_last_line_is_swallowed() -> None:
    """[SILENT] đứng riêng ở dòng CUỐI thì nuốt"""
    assert is_silent_response("2 tin mới đã lọc xong, không có gì đáng báo.\n\n[SILENT]") is True


def test_is_silent_response_starting_with_silent_followed_by_text_on_same_line_is_swallowed() -> None:
    """mở đầu bằng [SILENT] kèm chữ trên CÙNG dòng thì nuốt"""
    assert is_silent_response("[SILENT] Không có gì mới hôm nay.") is True


def test_is_silent_response_silent_in_the_middle_of_a_sentence_is_still_sent() -> None:
    """[SILENT] nằm GIỮA câu thì VẪN GỬI - không được nuốt nhầm câu trả lời thật"""
    assert is_silent_response("Mình định [SILENT] nhưng đây là tóm tắt hôm nay: giá vàng tăng nhẹ.") is False


def test_is_silent_response_a_middle_line_with_silent_but_not_first_or_last_is_still_sent() -> None:
    """dòng giữa có chữ [SILENT] nhưng không phải dòng đầu/cuối thì vẫn gửi"""
    text = "Tiêu đề báo cáo\n[SILENT] là từ khoá nội bộ, bỏ qua\nKết luận: ổn định."
    assert is_silent_response(text) is False


def test_is_silent_response_a_normal_real_answer_without_the_token_is_sent() -> None:
    """câu trả lời thật bình thường (không dính token) thì gửi"""
    assert is_silent_response("Hôm nay có 3 tin công nghệ đáng chú ý: ...") is False


def test_is_silent_response_empty_or_whitespace_is_not_silent_the_caller_handles_empty() -> None:
    """chuỗi rỗng hoặc chỉ khoảng trắng thì KHÔNG được coi là silent (để caller tự xử lý ca rỗng)"""
    assert is_silent_response("") is False
    assert is_silent_response("   \n  ") is False


def test_is_silent_response_a_word_containing_silent_without_brackets_is_not_swallowed() -> None:
    """từ chứa 'SILENT' nhưng không đúng token (không ngoặc) thì không nuốt"""
    assert is_silent_response("Silent retry đã thành công.") is False


def test_la_dong_sentinel_only_a_line_that_is_exactly_the_label_matches() -> None:
    """(không có test gốc riêng) la_dong_sentinel chỉ nhìn MỘT dòng, không phán cả câu trả lời"""
    assert la_dong_sentinel("[SILENT]") is True
    assert la_dong_sentinel("  [ silent ]  ") is True
    assert la_dong_sentinel("[SILENT] là nhãn nội bộ, dùng để bot im lặng ạ") is False
