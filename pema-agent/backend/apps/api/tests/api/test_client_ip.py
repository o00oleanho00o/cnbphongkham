# ported from: src/server/client-ip.test.ts
"""Test names are the snake_case English form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from pema.api import dashboard_auth
from pema.api.client_ip import parse_trusted_proxies, resolve_client_ip, rightmost_forwarded_for


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


PROXY = "10.20.30.40"
TRUSTED = parse_trusted_proxies(PROXY)


def test_resolve_client_ip_behind_a_proxy_uses_the_rightmost_entry_and_falls_back_to_the_socket() -> None:
    """khi có proxy lấy entry phải nhất; thiếu header thì rơi về socket"""
    request = _request({"X-Forwarded-For": "6.6.6.6, 198.51.100.7"}, client=(PROXY, 4000))
    assert resolve_client_ip(request, behind_proxy=True, trusted_proxies=TRUSTED) == "198.51.100.7"
    no_header = _request({}, client=(PROXY, 4000))
    assert resolve_client_ip(no_header, behind_proxy=True, trusted_proxies=TRUSTED) == PROXY


def test_resolve_client_ip_ignores_x_forwarded_for_from_a_peer_that_is_not_a_trusted_proxy() -> None:
    """Pema: XFF chỉ được tin khi chính peer socket là proxy tin cậy; host khác tự gửi XFF thì bị bỏ qua"""
    forged = _request({"X-Forwarded-For": "6.6.6.6"}, client=("203.0.113.50", 4000))
    assert resolve_client_ip(forged, behind_proxy=True, trusted_proxies=TRUSTED) == "203.0.113.50"


def test_resolve_client_ip_behind_proxy_with_an_empty_trusted_list_trusts_nobody() -> None:
    """Pema: bật cờ proxy mà không khai địa chỉ proxy thì không tin XFF của ai (fail closed)"""
    request = _request({"X-Forwarded-For": "6.6.6.6"}, client=(PROXY, 4000))
    assert resolve_client_ip(request, behind_proxy=True) == PROXY
    assert resolve_client_ip(request, behind_proxy=True, trusted_proxies=()) == PROXY


def test_resolve_client_ip_trusted_list_without_the_proxy_flag_still_ignores_x_forwarded_for() -> None:
    """Pema: danh sách tin cậy không tự bật việc đọc XFF; cờ proxy vẫn là công tắc chính"""
    request = _request({"X-Forwarded-For": "6.6.6.6"}, client=(PROXY, 4000))
    assert resolve_client_ip(request, behind_proxy=False, trusted_proxies=TRUSTED) == PROXY


def test_resolve_client_ip_walks_past_a_second_trusted_hop_to_the_first_untrusted_entry() -> None:
    """Pema: hai tầng proxy (CDN rồi Caddy): bỏ qua các entry là proxy tin cậy, lấy entry ngoài đầu tiên"""
    networks = parse_trusted_proxies("10.20.30.0/24, 2001:db8::/32")
    request = _request(
        {"X-Forwarded-For": "6.6.6.6, 198.51.100.7, 10.20.30.99"}, client=("10.20.30.40", 4000)
    )
    assert resolve_client_ip(request, behind_proxy=True, trusted_proxies=networks) == "198.51.100.7"
    v6 = _request({"X-Forwarded-For": "2001:db8::1, 192.0.2.9"}, client=("10.20.30.40", 4000))
    assert resolve_client_ip(v6, behind_proxy=True, trusted_proxies=networks) == "192.0.2.9"


def test_resolve_client_ip_a_garbage_entry_falls_back_to_the_proxy_socket_address() -> None:
    """Pema: entry không phải địa chỉ IP thì không dùng làm khóa rate-limit, rơi về địa chỉ socket"""
    request = _request({"X-Forwarded-For": "not-an-ip"}, client=(PROXY, 4000))
    assert resolve_client_ip(request, behind_proxy=True, trusted_proxies=TRUSTED) == PROXY


def test_parse_trusted_proxies_accepts_ips_and_cidrs_and_rejects_garbage() -> None:
    """Pema: danh sách tin cậy nhận IP/CIDR, dòng sai làm khởi động fail thay vì bị bỏ qua"""
    assert [str(n) for n in parse_trusted_proxies(" 10.0.0.1 , 172.29.80.0/24,, ")] == [
        "10.0.0.1/32",
        "172.29.80.0/24",
    ]
    assert parse_trusted_proxies("") == ()
    with pytest.raises(ValueError, match="does not appear to be"):
        parse_trusted_proxies("caddy")


def test_resolve_client_ip_without_a_socket_is_unknown() -> None:
    """app.request() trong unit test không có socket thật"""
    assert resolve_client_ip(_request({}, client=None), behind_proxy=False) == "unknown"


def _reload_auth_settings() -> None:
    dashboard_auth.get_auth_settings.cache_clear()
    dashboard_auth.get_trusted_proxies.cache_clear()


def test_dashboard_client_ip_reads_the_trusted_proxies_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pema: PEMA_DASHBOARD_BEHIND_PROXY + PEMA_TRUSTED_PROXIES quyết định có tin XFF hay không (cấu hình compose)"""
    forwarded = {"X-Forwarded-For": "6.6.6.6, 198.51.100.7"}
    try:
        monkeypatch.setenv("PEMA_DASHBOARD_BEHIND_PROXY", "true")
        monkeypatch.setenv("PEMA_TRUSTED_PROXIES", "")
        _reload_auth_settings()
        assert dashboard_auth.client_ip(_request(forwarded, client=(PROXY, 4000))) == PROXY

        monkeypatch.setenv("PEMA_TRUSTED_PROXIES", "172.29.80.2")
        _reload_auth_settings()
        from_caddy = _request(forwarded, client=("172.29.80.2", 4000))
        assert dashboard_auth.client_ip(from_caddy) == "198.51.100.7"
        from_frontend = _request(forwarded, client=("172.29.80.9", 4000))
        assert dashboard_auth.client_ip(from_frontend) == "172.29.80.9"

        monkeypatch.setenv("PEMA_DASHBOARD_BEHIND_PROXY", "false")
        _reload_auth_settings()
        assert dashboard_auth.client_ip(from_caddy) == "172.29.80.2"
    finally:
        monkeypatch.undo()
        _reload_auth_settings()
