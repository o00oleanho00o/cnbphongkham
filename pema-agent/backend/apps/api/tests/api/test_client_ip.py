# ported from: src/server/client-ip.test.ts
"""Test names are the snake_case English form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from starlette.requests import Request

from pema.api.client_ip import resolve_client_ip, rightmost_forwarded_for


def _request(headers: dict[str, str], client: tuple[str, int] | None = ("203.0.113.50", 4000)) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
    }
    return Request(scope)


def test_rightmost_forwarded_for_takes_the_rightmost_entry_written_by_the_proxy_not_forged_by_the_client() -> (
    None
):
    """lấy entry phải nhất - đó là entry do proxy ghi, không phải client bịa"""
    # Caddy/Nginx APPEND the client ip to the end of an existing chain
    assert rightmost_forwarded_for("1.1.1.1, 203.0.113.9") == "203.0.113.9"
    # a client forging XFF to dodge the rate limit puts the fake part on the left: it is ignored
    assert rightmost_forwarded_for("forged-value, 8.8.8.8, 203.0.113.9") == "203.0.113.9"


def test_rightmost_forwarded_for_single_entry_is_taken_as_is() -> None:
    """một entry duy nhất thì lấy chính nó"""
    assert rightmost_forwarded_for("203.0.113.9") == "203.0.113.9"


def test_rightmost_forwarded_for_empty_missing_or_only_commas_returns_none_so_the_socket_ip_is_used() -> None:
    """header rỗng/thiếu/toàn dấu phẩy trả None để rơi về IP socket"""
    assert rightmost_forwarded_for(None) is None
    assert rightmost_forwarded_for("") is None
    assert rightmost_forwarded_for(" , , ") is None


def test_rightmost_forwarded_for_strips_whitespace_around_the_entry() -> None:
    """bỏ khoảng trắng quanh entry"""
    assert rightmost_forwarded_for("1.1.1.1,   203.0.113.9   ") == "203.0.113.9"


def test_resolve_client_ip_ignores_x_forwarded_for_when_no_proxy_is_configured() -> None:
    """không cấu hình proxy thì chỉ tin địa chỉ socket (XFF do client gửi được)"""
    request = _request({"X-Forwarded-For": "6.6.6.6"})
    assert resolve_client_ip(request, behind_proxy=False) == "203.0.113.50"


def test_resolve_client_ip_behind_a_proxy_uses_the_rightmost_entry_and_falls_back_to_the_socket() -> None:
    """khi có proxy lấy entry phải nhất; thiếu header thì rơi về socket"""
    assert (
        resolve_client_ip(_request({"X-Forwarded-For": "6.6.6.6, 198.51.100.7"}), behind_proxy=True)
        == "198.51.100.7"
    )
    assert resolve_client_ip(_request({}), behind_proxy=True) == "203.0.113.50"


def test_resolve_client_ip_without_a_socket_is_unknown() -> None:
    """app.request() trong unit test không có socket thật"""
    assert resolve_client_ip(_request({}, client=None), behind_proxy=False) == "unknown"
