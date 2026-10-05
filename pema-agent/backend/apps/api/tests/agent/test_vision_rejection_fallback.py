# ported from: src/agent/vision-rejection-fallback.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module: it touches no env or DB, so no fixture is needed.
"""

from __future__ import annotations

from pema.agent.providers.errors import ProviderCallError
from pema.agent.vision_rejection_fallback import has_image_parts, is_image_rejection_error


def api_error(status_code: int) -> ProviderCallError:
    return ProviderCallError(f"HTTP {status_code}", status_code=status_code, response_body="")


def test_is_image_rejection_error_400_413_415_422_true() -> None:
    """400/413/415/422 (từ chối nội dung) -> true"""
    for status in (400, 413, 415, 422):
        assert is_image_rejection_error(api_error(status)) is True, f"HTTP {status}"


def test_is_image_rejection_error_401_403_429_5xx_false_no_pointless_retry() -> None:
    """401/403 (sai key), 429 (quota), 5xx (tạm thời) -> false, không retry oan"""
    for status in (401, 403, 429, 500, 503):
        assert is_image_rejection_error(api_error(status)) is False, f"HTTP {status}"


def test_is_image_rejection_error_plain_error_false() -> None:
    """lỗi thường (không phải APICallError) -> false"""
    assert is_image_rejection_error(Exception("mạng đứt")) is False
    assert is_image_rejection_error(None) is False


def test_is_image_rejection_error_duck_typed_sdk_error_counts() -> None:
    """(Python) a raw SDK-style exception with `status_code` or `response.status_code` is read too"""

    class SdkError(Exception):
        status_code = 400

    class Response:
        status_code = 422

    class WithResponse(Exception):  # noqa: N818 - a stand-in for an SDK error
        response = Response()

    assert is_image_rejection_error(SdkError("x")) is True
    assert is_image_rejection_error(WithResponse("x")) is True
    assert is_image_rejection_error({"status_code": 400}) is False, "only an exception counts"


def test_has_image_parts_detects_image_part_in_array_content_ignores_plain_text() -> None:
    """phát hiện part ảnh trong content mảng, bỏ qua text thuần"""
    assert (
        has_image_parts(
            [
                {"role": "user", "content": "chào"},
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "data": "abc", "mediaType": "image/jpeg"},
                        {"type": "text", "text": "dò vé"},
                    ],
                },
            ]
        )
        is True
    )
    assert (
        has_image_parts(
            [
                {"role": "user", "content": "chào"},
                {"role": "user", "content": [{"type": "text", "text": "chỉ chữ"}]},
            ]
        )
        is False
    )
