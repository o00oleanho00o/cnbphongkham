# ported from: src/agent/cache-session-id.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, no environment needed."""

from __future__ import annotations

import re

from pema.agent.cache_session_id import CACHE_SESSION_HEADER, cache_session_headers, cache_session_id

# ---- cacheSessionId -----------------------------------------------------------------------------------


def test_cache_session_id_on_dinh_cung_thread_luon_ra_cung_khoa() -> None:
    """ỔN ĐỊNH: cùng thread luôn ra cùng khóa - đây là điều kiện để cache trúng"""
    first = cache_session_id("acc-chinh", "1234567890123456789")
    second = cache_session_id("acc-chinh", "1234567890123456789")
    assert first == second


def test_cache_session_id_khac_thread_hoac_khac_account_thi_khac_khoa() -> None:
    """khác thread hoặc khác account thì khác khóa - không lẫn cache giữa các cuộc chat"""
    a = cache_session_id("acc-chinh", "thread-1")
    assert a != cache_session_id("acc-chinh", "thread-2")
    assert a != cache_session_id("acc-hai", "thread-1")


def test_cache_session_id_khong_ro_thread_id_that_ra_header() -> None:
    """không rò thread id thật ra header (thread id là định danh người dùng)"""
    thread_id = "1234567890123456789"
    key = cache_session_id("acc-chinh", thread_id)
    assert thread_id not in key, "khóa không được chứa thread id nguyên văn"
    assert "acc-chinh" not in key, "khóa không được chứa account id nguyên văn"


def test_cache_session_id_khoa_du_ngan_va_chi_chua_ky_tu_an_toan_cho_http_header() -> None:
    """khóa đủ ngắn và chỉ chứa ký tự an toàn cho HTTP header"""
    key = cache_session_id("acc-chinh", "thread-1")
    assert re.fullmatch(r"zalo-agent-[0-9a-f]{32}", key)
    assert len(key) < 64


def test_cache_session_id_ghep_chuoi_khong_bi_nhap_nhang_ranh_gioi_account_thread() -> None:
    """ghép chuỗi không bị nhập nhằng ranh giới account/thread"""
    # "a:bc" and "ab:c" must differ, otherwise 2 different threads share one cache
    assert cache_session_id("a", "bc") != cache_session_id("ab", "c")


# ---- cacheSessionHeaders ------------------------------------------------------------------------------


def test_cache_session_headers_bat_thi_tra_dung_header_router_doc() -> None:
    """bật thì trả đúng header router đọc"""
    headers = cache_session_headers(True, "acc-chinh", "thread-1")
    assert list(headers.keys()) == [CACHE_SESSION_HEADER]
    assert headers[CACHE_SESSION_HEADER] == cache_session_id("acc-chinh", "thread-1")


def test_cache_session_headers_tat_thi_tra_object_rong_de_caller_spread_thang_khong_can_if() -> None:
    """tắt thì trả object rỗng để caller spread thẳng, không cần if"""
    assert cache_session_headers(False, "acc-chinh", "thread-1") == {}


def test_cache_session_headers_thieu_account_id_thread_id_thi_khong_gui_header_rac() -> None:
    """thiếu accountId/threadId thì không gửi header rác"""
    assert cache_session_headers(True, "", "thread-1") == {}
    assert cache_session_headers(True, "acc-chinh", "") == {}


def test_cache_session_headers_ten_header_khop_session_header_keys_cua_9router() -> None:
    """tên header khớp SESSION_HEADER_KEYS của 9Router - lệch là cache im lặng không chạy"""
    assert CACHE_SESSION_HEADER == "x-session-id"


# ---- cacheSessionId - epoch sau khi xóa ngữ cảnh ------------------------------------------------------
# Epoch is the number of times the thread context was wiped. It is inside the hash so that every wipe opens
# a NEW SESSION with the router - the same way goclaw calls ``ResetCLISession`` after /reset and Hermes
# rotates ``session_id``. Without it a wipe still sends the old key, and the router keeps the cached prefix
# of the conversation that was just deleted.


def test_epoch_epoch_khac_nhau_thi_khoa_khac_nhau() -> None:
    """epoch khác nhau thì khóa khác nhau"""
    truoc = cache_session_id("acc", "th", 0)
    sau = cache_session_id("acc", "th", 1)
    assert truoc != sau, "xóa ngữ cảnh xong phải là phiên mới"


def test_epoch_khong_truyen_epoch_thi_giu_nguyen_khoa_cu_thread_chua_tung_xoa_khong_mat_cache() -> None:
    """KHÔNG truyền epoch thì giữ nguyên khóa cũ - thread chưa từng xóa không mất cache"""
    assert cache_session_id("acc", "th") == cache_session_id("acc", "th", 0)


def test_epoch_cung_epoch_thi_van_on_dinh_trong_mot_phien_cache_phai_trung() -> None:
    """cùng epoch thì vẫn ổn định - trong một phiên cache phải trúng"""
    assert cache_session_id("acc", "th", 3) == cache_session_id("acc", "th", 3)


def test_epoch_epoch_khong_lan_sang_phan_account_thread() -> None:
    """epoch không lẫn sang phần account/thread"""
    # Sloppy joining ("acc:th" + "1" versus "acc:th1" + "") makes two different threads produce the same
    # key, i.e. one person's cache flows to another
    assert cache_session_id("acc", "th", 1) != cache_session_id("acc", "th1", 0)


def test_epoch_header_cung_doi_theo_epoch_khong_chi_ham_bam() -> None:
    """header cũng đổi theo epoch, không chỉ hàm băm"""
    h0 = cache_session_headers(True, "acc", "th", 0)[CACHE_SESSION_HEADER]
    h1 = cache_session_headers(True, "acc", "th", 1)[CACHE_SESSION_HEADER]
    assert h0 != h1, "quên truyền epoch xuống header là vá nửa vời"
