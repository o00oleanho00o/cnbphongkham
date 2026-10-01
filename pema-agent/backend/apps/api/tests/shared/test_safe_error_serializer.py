# ported from: src/shared/safe-error-serializer.test.ts
"""The default serializer copies every attribute, so an SDK ``APICallError`` drags ``requestBodyValues``
(system prompt + conversation + base64 images) into the log file. In the clinic that is patient text:
this test keeps the fence standing."""

from __future__ import annotations

import json
from typing import Any

from pema.shared.safe_error_serializer import serialize_error_safely


class ApiCallErrorFake(Exception):  # noqa: N818 - mirrors the SDK class name shape
    """Same shape as the SDK error: own attributes assigned in the constructor."""

    def __init__(self, image_base64: str) -> None:
        super().__init__("Too Many Requests")
        self.name = "AI_APICallError"
        self.url = "https://llm.example.test/v1/chat/completions"
        self.status_code = 429
        self.request_body_values = {
            "messages": [
                {"role": "system", "content": "Ban la tro ly AI... [TOAN BO SYSTEM PROMPT]"},
                {"role": "user", "content": [{"image_url": f"data:image/jpeg;base64,{image_base64}"}]},
            ]
        }
        self.response_body = '{"error":"quota exceeded"}'


IMAGE = "iVBORw0KGgo" + "A" * 500


def test_does_not_log_request_body_values_the_leak_path() -> None:
    """KHÔNG ghi requestBodyValues - đường rò system prompt và ảnh base64"""
    out = serialize_error_safely(ApiCallErrorFake(IMAGE))
    assert "request_body_values" not in out
    text = json.dumps(out)
    assert IMAGE[:50] not in text, "base64 image must not leak"
    assert "TOAN BO SYSTEM PROMPT" not in text, "system prompt must not leak"


def test_does_not_log_response_body() -> None:
    """KHÔNG ghi responseBody"""
    assert "response_body" not in serialize_error_safely(ApiCallErrorFake(IMAGE))


def test_still_keeps_everything_needed_to_diagnose() -> None:
    """VẪN giữ đủ thứ để chẩn đoán"""
    out = serialize_error_safely(ApiCallErrorFake(IMAGE))
    assert out["message"] == "Too Many Requests"
    assert out["status_code"] == 429
    assert "llm.example.test" in str(out["url"])
    assert out["type"] == "ApiCallErrorFake"
    assert "stack" in out


def test_real_size_images_do_not_bloat_the_log_line() -> None:
    """ảnh Zalo cỡ thật không làm phình dòng log"""
    huge = "A" * 400_000
    safe = json.dumps(serialize_error_safely(ApiCallErrorFake(huge)))
    assert len(safe) < 4000, f"log line must stay small, was {len(safe)} chars"
    assert "AAAAAAAAAA" not in safe, "no fragment of the image"


def test_message_is_taken_even_when_it_is_not_an_own_attribute() -> None:
    """lấy được message dù nó là non-enumerable"""
    assert serialize_error_safely(Exception("mạng rớt"))["message"] == "mạng rớt"


def test_keeps_code_errno_syscall_of_os_errors() -> None:
    """giữ code/errno/syscall của lỗi Node - cần khi lỗi đọc ghi file"""
    err = Exception("ENOENT")
    err.code = "ENOENT"  # type: ignore[attr-defined]
    err.errno = -4058  # type: ignore[attr-defined]
    err.syscall = "open"  # type: ignore[attr-defined]
    out = serialize_error_safely(err)
    assert out["code"] == "ENOENT"
    assert out["syscall"] == "open"


def test_follows_the_cause_chain_but_the_cause_is_filtered_too() -> None:
    """theo được chuỗi cause nhưng cause cũng bị lọc"""
    original = ApiCallErrorFake("XYZ" * 50)
    wrapper = Exception("bọc ngoài")
    wrapper.__cause__ = original
    out = serialize_error_safely(wrapper)
    cause: dict[str, Any] = out["cause"]
    assert cause["status_code"] == 429
    assert "request_body_values" not in cause


def test_a_self_referencing_cause_does_not_hang() -> None:
    """cause tự tham chiếu không làm treo"""
    err = Exception("a")
    err.__cause__ = err
    assert serialize_error_safely(err)["message"] == "a"


def test_non_error_values_still_produce_something_readable() -> None:
    """giá trị không phải Error vẫn ra được thứ đọc được"""
    assert serialize_error_safely("chuỗi trần")["message"] == "chuỗi trần"
    assert serialize_error_safely(None)["message"] == "None"


def test_overlong_stack_is_cut() -> None:
    """stack quá dài bị cắt"""
    err = ValueError("x" * 5000)
    out = serialize_error_safely(err)
    assert len(str(out["stack"])) < 2100


def test_code_and_message_of_a_channel_error_are_not_filtered_out() -> None:
    """ZaloApiError giữ nguyên message và code - không bị lọc oan"""
    err = Exception("Không gửi được tin")
    err.code = 118  # type: ignore[attr-defined]
    out = serialize_error_safely(err)
    assert out["message"] == "Không gửi được tin"
    assert out["code"] == 118
