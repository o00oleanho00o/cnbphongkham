# ported from: src/agent/provider-error-classifier.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module - needs no tuning provider and no settings.

Python-side replacements of the SDK-specific cases: ``APICallError`` is ``ProviderCallError``; the
``RetryError`` wrapper of the Vercel SDK has no Python twin, so the "unwrap" cases use the two shapes the
classifier reads instead (a retry wrapper exposing ``last_error``, and an exception raised ``from`` the provider
error).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from typing import ClassVar

from pema.agent.llm_config_error import LoiCauHinhLlm
from pema.agent.provider_error_classifier import (
    giay_cho_lai,
    ma_http_cua,
    nen_thu_lai,
    phan_loai_loi_provider,
)
from pema.agent.providers.errors import ProviderCallError
from pema.agent.vision_rejection_fallback import is_image_rejection_error
from pema_contracts.turn_errors import ProviderErrorKind

# Module thuần - không cần setupTestEnv, không cần import động


def loi_api(status_code: int, message: str, headers: dict[str, str] | None = None) -> ProviderCallError:
    return ProviderCallError(
        message,
        status_code=status_code,
        response_headers=headers,
        response_body=message,
        url="https://router.test/v1/chat/completions",
    )


class RetryWrapper(Exception):  # noqa: N818 - mirrors the SDK wrapper
    """A retry wrapper in the shape of ``RetryError``: no status code of its own, the last error inside."""

    def __init__(self, message: str, last_error: object | None) -> None:
        super().__init__(message)
        self.last_error = last_error


def boc(goc: BaseException) -> Exception:
    """The loop's own wrapping: a plain exception raised FROM the provider error."""
    wrapped = RuntimeError("Failed after 3 attempts.")
    wrapped.__cause__ = goc
    return wrapped


# --- phanLoaiLoiProvider - theo mã HTTP ------------------------------------------------------------------


def test_phan_loai_loi_provider_theo_ma_http_429_la_het_quota_bi_siet_nhip() -> None:
    """429 là hết quota / bị siết nhịp"""
    assert phan_loai_loi_provider(loi_api(429, "Rate limit exceeded")) == "rate_limit"


def test_phan_loai_loi_provider_theo_ma_http_401_va_403_la_sai_khoa_hoac_thieu_quyen() -> None:
    """401 và 403 là sai khóa hoặc thiếu quyền"""
    assert phan_loai_loi_provider(loi_api(401, "Invalid API key")) == "auth"
    assert phan_loai_loi_provider(loi_api(403, "Forbidden")) == "auth"


def test_phan_loai_loi_provider_theo_ma_http_5xx_la_loi_tam() -> None:
    """5xx là lỗi tạm"""
    assert phan_loai_loi_provider(loi_api(500, "Internal error")) == "transient"
    assert phan_loai_loi_provider(loi_api(503, "Upstream unavailable")) == "transient"


def test_phan_loai_loi_provider_theo_ma_http_400_khong_kem_dau_hieu_tran_context_la_unknown() -> None:
    """400 KHÔNG kèm dấu hiệu tràn context thì là unknown, không phải context_overflow"""
    assert phan_loai_loi_provider(loi_api(400, "Invalid value for 'temperature'")) == "unknown"


# --- phanLoaiLoiProvider - tràn context ------------------------------------------------------------------


def test_phan_loai_loi_provider_tran_context_nhan_ra_qua_thong_bao_vi_provider_nao_cung_tra_400_chung() -> (
    None
):
    """nhận ra qua thông báo, vì provider nào cũng trả 400 chung"""
    for msg in (
        "This model's maximum context length is 128000 tokens",
        "prompt is too long: 210000 tokens",
        "Request exceeds the maximum allowed tokens",
        "Please reduce the length of the messages",
        "input exceeds context window",
    ):
        assert phan_loai_loi_provider(loi_api(400, msg)) == "context_overflow", msg


def test_phan_loai_loi_provider_tran_context_chu_too_long_trong_loi_5xx_khong_bi_bat_nham() -> None:
    """chữ 'too long' trong lỗi 5xx KHÔNG bị bắt nhầm

    Gateway trả trang HTML 502 có chữ "too long" trong nội dung - cắt ngữ cảnh rồi thử lại là chữa nhầm bệnh.
    """
    assert phan_loai_loi_provider(loi_api(502, "Gateway timeout, request too long")) == "transient"


def test_phan_loai_loi_provider_tran_context_gateway_nem_loi_khong_kem_ma_van_nhan_ra_duoc() -> None:
    """gateway ném lỗi không kèm mã vẫn nhận ra được"""
    assert phan_loai_loi_provider(Exception("context length exceeded")) == "context_overflow"


# --- phanLoaiLoiProvider - lỗi mạng ----------------------------------------------------------------------


def test_phan_loai_loi_provider_loi_mang_cac_ma_loi_socket_quen_thuoc_la_transient() -> None:
    """các mã lỗi socket quen thuộc là transient"""
    for msg in (
        "connect ECONNREFUSED 127.0.0.1:443",
        "read ECONNRESET",
        "getaddrinfo ENOTFOUND router.test",
        "socket hang up",
        "The operation was aborted",
    ):
        assert phan_loai_loi_provider(Exception(msg)) == "transient", msg


def test_phan_loai_loi_provider_loi_mang_doc_ca_cause_loi_mang_that_thuong_bi_boc() -> None:
    """đọc cả `cause` - lỗi mạng thật thường bị bọc trong TypeError: fetch failed

    The REAL shape of undici: the outer message only says "fetch failed", the error code sits in the cause.
    Not reading the cause misses exactly the most frequent case. Python: the ``__cause__`` chain.
    """
    wrapped = Exception("fetch failed")
    wrapped.__cause__ = Exception("connect ECONNREFUSED 10.0.0.1:443")
    assert phan_loai_loi_provider(wrapped) == "transient"


def test_phan_loai_loi_provider_loi_mang_python_timeout_va_connection_error_la_transient() -> None:
    """(Python) TimeoutError / ConnectionError, also deep in the cause chain, are network signs"""
    assert phan_loai_loi_provider(TimeoutError()) == "transient"
    assert phan_loai_loi_provider(ConnectionRefusedError()) == "transient"
    assert phan_loai_loi_provider(boc(ConnectionResetError())) == "transient"

    class ConnectError(Exception):
        """Same NAME as the httpx transport error: read by name, no SDK import."""

    assert phan_loai_loi_provider(ConnectError("")) == "transient"


# --- bóc lớp bọc RetryError - hình dạng THẬT của lỗi retry được ------------------------------------------
# Đo trên ai@7.0.37: SDK tự retry 429 và 5xx (3 lần gọi) rồi ném RetryError, KHÔNG ném APICallError.
# RetryError không có statusCode, nên thiếu bước bóc là bộ phân loại mù hoàn toàn với đúng hai loại hay gặp.


def test_boc_lop_boc_retry_error_429_bi_boc_van_ra_rate_limit() -> None:
    """429 bị bọc vẫn ra rate_limit"""
    wrapped = RetryWrapper("Failed after 3 attempts.", loi_api(429, "Rate limit"))
    assert phan_loai_loi_provider(wrapped) == "rate_limit"
    assert phan_loai_loi_provider(boc(loi_api(429, "Rate limit"))) == "rate_limit"


def test_boc_lop_boc_retry_error_500_bi_boc_van_ra_transient() -> None:
    """500 bị bọc vẫn ra transient"""
    assert phan_loai_loi_provider(RetryWrapper("Failed", loi_api(500, "Internal"))) == "transient"
    assert phan_loai_loi_provider(boc(loi_api(500, "Internal"))) == "transient"


def test_boc_lop_boc_retry_error_ma_http_cua_doc_duoc_ma_qua_lop_boc() -> None:
    """maHttpCua đọc được mã qua lớp bọc"""
    assert ma_http_cua(RetryWrapper("x", loi_api(429, "x"))) == 429
    assert ma_http_cua(boc(loi_api(429, "x"))) == 429


def test_boc_lop_boc_retry_error_giay_cho_lai_doc_duoc_retry_after_qua_lop_boc() -> None:
    """giayChoLai đọc được Retry-After qua lớp bọc"""
    assert giay_cho_lai(RetryWrapper("x", loi_api(429, "x", {"retry-after": "7"}))) == 7
    assert giay_cho_lai(boc(loi_api(429, "x", {"retry-after": "7"}))) == 7


def test_boc_lop_boc_retry_error_rong_khong_co_last_error_khong_lam_vo() -> None:
    """RetryError rỗng (không có lastError) không làm vỡ"""
    rong = RetryWrapper("x", None)
    assert phan_loai_loi_provider(rong) == "unknown"


# --- phanLoaiLoiProvider - đầu vào lạ không được làm vỡ --------------------------------------------------


def test_phan_loai_loi_provider_dau_vao_la_null_undefined_chuoi_so_object_rong() -> None:
    """null, undefined, chuỗi, số, object rỗng"""
    odd: list[object] = [None, "", 123, {}, [], True]
    for x in odd:
        phan_loai_loi_provider(x)  # must not raise
    assert phan_loai_loi_provider(None) == "unknown"
    assert phan_loai_loi_provider(None) == ProviderErrorKind.UNKNOWN


def test_phan_loai_loi_provider_dau_vao_la_chuoi_thuan_van_do_duoc_noi_dung() -> None:
    """chuỗi thuần vẫn dò được nội dung"""
    assert phan_loai_loi_provider("ECONNRESET") == "transient"
    assert phan_loai_loi_provider("maximum context length exceeded") == "context_overflow"


def test_phan_loai_loi_provider_dau_vao_la_object_tu_che_co_status_code_van_doc_duoc() -> None:
    """object tự chế có statusCode vẫn đọc được"""
    assert phan_loai_loi_provider({"statusCode": 429, "message": "slow down"}) == "rate_limit"
    assert phan_loai_loi_provider({"status": 401, "message": "nope"}) == "auth"
    assert phan_loai_loi_provider(SimpleNamespace(status_code=429, message="slow down")) == "rate_limit"
    assert phan_loai_loi_provider(SimpleNamespace(status=401, message="nope")) == "auth"


# --- KHÔNG được giẫm chân bộ phân loại lỗi ảnh -----------------------------------------------------------


def test_khong_dam_chan_bo_phan_loai_loi_anh_loi_tu_choi_anh_400_van_duoc_nhan_ra() -> None:
    """lỗi từ chối ảnh (400) vẫn được isImageRejectionError nhận ra

    Bất biến sống còn: nhánh fallback ảnh phải được kiểm TRƯỚC trong agent-loop. Lỗi ảnh cũng là 400, nếu để
    bộ phân loại mới chạy trước thì nó ra "unknown" và nhánh bỏ pixel không bao giờ chạy.
    """
    loi_anh = loi_api(400, "Invalid image content")
    assert is_image_rejection_error(loi_anh) is True
    assert phan_loai_loi_provider(loi_anh) == "unknown", "bộ mới KHÔNG nhận ra lỗi ảnh - đúng như thiết kế"


def test_khong_dam_chan_bo_phan_loai_loi_anh_401_va_429_khong_bi_nhanh_anh_bat() -> None:
    """401 và 429 không bị nhánh ảnh bắt, nên hai bộ không tranh nhau"""
    assert is_image_rejection_error(loi_api(401, "x")) is False
    assert is_image_rejection_error(loi_api(429, "x")) is False


# --- nenThuLai -------------------------------------------------------------------------------------------


def test_nen_thu_lai_chi_auth_la_khong_thu_lai_thu_lai_sai_khoa_chi_cham_gap_ba_roi_van_hong() -> None:
    """chỉ auth là KHÔNG thử lại - thử lại sai khóa chỉ chậm gấp ba rồi vẫn hỏng"""
    assert nen_thu_lai(ProviderErrorKind.AUTH) is False
    for loai in (
        ProviderErrorKind.RATE_LIMIT,
        ProviderErrorKind.CONTEXT_OVERFLOW,
        ProviderErrorKind.TRANSIENT,
        ProviderErrorKind.UNKNOWN,
    ):
        assert nen_thu_lai(loai) is True, loai


# --- giayChoLai ------------------------------------------------------------------------------------------


def test_giay_cho_lai_doc_retry_after_dang_so_giay() -> None:
    """đọc Retry-After dạng số giây"""
    assert giay_cho_lai(loi_api(429, "x", {"retry-after": "12"})) == 12


def test_giay_cho_lai_doc_retry_after_dang_moc_thoi_gian_http() -> None:
    """đọc Retry-After dạng mốc thời gian HTTP"""
    sau_5s = format_datetime(datetime.now(UTC) + timedelta(seconds=5), usegmt=True)
    g = giay_cho_lai(loi_api(429, "x", {"retry-after": sau_5s}))
    assert g is not None
    assert 4 <= g <= 6, f"mong 4-6 giây, nhận {g}"


def test_giay_cho_lai_ke_tran_60_giay_cho_lau_hon_la_luot_da_cham_tran_thoi_gian_va_khoa_thread() -> None:
    """kẹp trần 60 giây - chờ lâu hơn là lượt đã chạm trần thời gian và khóa thread"""
    assert giay_cho_lai(loi_api(429, "x", {"retry-after": "3600"})) == 60


def test_giay_cho_lai_khong_co_header_header_rac_hay_loi_khong_phai_api_call_error_thi_tra_none() -> None:
    """không có header, header rác, hay lỗi không phải APICallError thì trả undefined"""
    assert giay_cho_lai(loi_api(429, "x")) is None
    assert giay_cho_lai(loi_api(429, "x", {"retry-after": "khong-phai-so"})) is None
    assert giay_cho_lai(Exception("x")) is None
    assert giay_cho_lai(None) is None


def test_giay_cho_lai_moc_thoi_gian_da_qua_thi_tra_0_khong_tra_so_am() -> None:
    """mốc thời gian đã qua thì trả 0, không trả số âm"""
    truoc = format_datetime(datetime.now(UTC) - timedelta(seconds=60), usegmt=True)
    assert giay_cho_lai(loi_api(429, "x", {"retry-after": truoc})) == 0


def test_giay_cho_lai_doc_ca_response_headers_cua_loi_sdk_khong_phan_biet_hoa_thuong() -> None:
    """(Python) a raw SDK exception with `response.headers` (any case) is read too"""

    class Response:
        status_code = 429
        headers: ClassVar[dict[str, str]] = {"Retry-After": "9"}

    class SdkError(Exception):
        response = Response()

    assert giay_cho_lai(SdkError("x")) == 9
    assert phan_loai_loi_provider(SdkError("x")) == "rate_limit"


# --- maHttpCua -------------------------------------------------------------------------------------------


def test_ma_http_cua_doc_tu_api_call_error_va_tu_object_tu_che_khong_co_thi_none() -> None:
    """đọc từ APICallError và từ object tự chế; không có thì undefined"""
    assert ma_http_cua(loi_api(418, "x")) == 418
    assert ma_http_cua({"status": 500}) == 500
    assert ma_http_cua(Exception("x")) is None
    assert ma_http_cua("chuoi") is None


# --- cau_hinh - CHÍNH MÌNH chưa cấu hình xong ------------------------------------------------------------


def test_cau_hinh_loi_cau_hinh_llm_ra_cau_hinh_khong_phai_unknown() -> None:
    """LoiCauHinhLlm ra 'cau_hinh', KHÔNG phải 'unknown'

    Rơi vào `unknown` thì `cauLoiTheoLoai` trả câu "bạn nhắn lại sau ít phút" - nói dối, vì chưa nhập cấu hình
    thì chờ bao lâu cũng không tự hết. Và trạng thái này KHÔNG hiếm nữa từ khi .env chỉ còn một biến bắt buộc:
    bot khởi động được khi chưa cấu hình gì, nên MỌI tin nhắn đều đi qua đây.
    """
    for loai in ("api_key", "model", "base_url"):
        err = LoiCauHinhLlm(loai, "Chưa cấu hình gì đó")
        assert phan_loai_loi_provider(err) == "cau_hinh", loai
        assert phan_loai_loi_provider(err) == ProviderErrorKind.CONFIG


def test_cau_hinh_khong_thu_lai_thu_lai_chi_cham_gap_ba_roi_van_hong() -> None:
    """KHÔNG thử lại - thử lại chỉ chậm gấp ba rồi vẫn hỏng"""
    assert nen_thu_lai(ProviderErrorKind.CONFIG) is False


def test_cau_hinh_nhan_dien_qua_hinh_dang_song_sot_khi_co_hai_ban_sao_module() -> None:
    """nhận diện qua HÌNH DẠNG, sống sót khi có hai bản sao module

    A bare ``isinstance`` breaks when a dynamic reload loads two copies of the module.
    """
    assert LoiCauHinhLlm.is_instance(SimpleNamespace(name="LoiCauHinhLlm")) is True
    assert LoiCauHinhLlm.is_instance(Exception("x")) is False
    assert LoiCauHinhLlm.is_instance(None) is False
    assert phan_loai_loi_provider(SimpleNamespace(name="LoiCauHinhLlm")) == "cau_hinh"


def test_cau_hinh_loi_thuong_co_cung_chu_van_ra_unknown_khong_do_cau_chu() -> None:
    """lỗi thường có cùng CHỮ vẫn ra unknown - không dò câu chữ

    Nếu ai đó chữa bằng cách dò chuỗi "Chưa cấu hình" thì ca này đỏ.
    """
    assert phan_loai_loi_provider(Exception("Chưa cấu hình LLM API key")) == "unknown"
