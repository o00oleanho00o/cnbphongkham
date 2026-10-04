# ported from: src/images/image-retry-policy.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Trọng tâm: ranh giới giữa "gọi lại là được" và "gọi lại chỉ tốn thêm thời
gian". Nới rộng nhánh đúng thì bot đợi thêm 1-3 phút cho một lỗi vô phương;
thu hẹp thì mất chính ca đã xảy ra thật trên Zalo ngày 2026-08-05.
"""

from __future__ import annotations

from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh, la_chu_ve_hut_anh, la_loi_ve_hut_anh


def test_la_loi_ve_hut_anh_recognises_errors_classified_by_ourselves_without_text_matching() -> None:
    """lỗi do CHÍNH MÌNH phân loại thì nhận ra, không cần dò chữ"""
    assert la_loi_ve_hut_anh(LoiVeHutAnh("Provider không trả về ảnh (stream rỗng)")) is True


def test_la_loi_ve_hut_anh_recognises_the_exact_sentence_the_router_sent_on_real_zalo() -> None:
    """nhận đúng câu router đã bắn ra trên Zalo thật"""
    # Chép nguyên văn từ log turnId 166 - câu này là nhánh bắt tất của
    # 9router, phần "Plus/Pro required" chỉ là suy đoán của nó
    that = ImageGenError("Codex did not return an image. Account may not be entitled (Plus/Pro required).")
    assert la_loi_ve_hut_anh(that) is True


def test_la_loi_ve_hut_anh_does_not_depend_on_the_account_guess_part() -> None:
    """KHÔNG bám vào phần suy đoán về tài khoản - router đổi câu đó thì vẫn phải khớp"""
    assert la_chu_ve_hut_anh("Codex did not return an image.") is True
    assert la_chu_ve_hut_anh("upstream did not return an image after 3 attempts") is True


def test_la_loi_ve_hut_anh_does_not_retry_a_timeout() -> None:
    """quá hạn thì KHÔNG gọi lại - lần hai tiêu thêm trọn một trần thời gian nữa"""
    assert la_loi_ve_hut_anh(ImageGenError("Vẽ ảnh quá lâu (hơn 600 giây) nên đã dừng")) is False


def test_la_loi_ve_hut_anh_does_not_retry_a_lost_signal() -> None:
    """mất tín hiệu thì KHÔNG gọi lại - provider đang treo, gọi lại cũng treo"""
    assert la_loi_ve_hut_anh(ImageGenError("Mất tín hiệu từ nhà cung cấp (im lặng quá 90 giây)")) is False


def test_la_loi_ve_hut_anh_does_not_retry_a_bad_key_or_exhausted_quota() -> None:
    """sai key / hết quota thì KHÔNG gọi lại - lần sau y hệt lần trước"""
    assert la_loi_ve_hut_anh(ImageGenError("API key required for remote API access")) is False
    assert la_loi_ve_hut_anh(ImageGenError("HTTP 429: rate limit exceeded")) is False
    assert (
        la_loi_ve_hut_anh(ImageGenError("Tool vẽ ảnh chưa cấu hình đủ base URL + model + API key")) is False
    )


def test_la_loi_ve_hut_anh_a_proxy_error_page_is_not_this_case() -> None:
    """trang lỗi của proxy KHÔNG phải ca này - đó là hạ tầng, không phải model đổi ý"""
    assert la_loi_ve_hut_anh(ImageGenError("Provider không trả về ảnh (Content-Type: text/html)")) is False


def test_la_loi_ve_hut_anh_does_not_mistake_a_non_error() -> None:
    """thứ không phải Error thì không nhận nhầm"""
    assert la_loi_ve_hut_anh("did not return an image") is False
    assert la_loi_ve_hut_anh(None) is False
