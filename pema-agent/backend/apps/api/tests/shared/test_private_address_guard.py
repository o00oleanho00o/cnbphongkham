# ported from: src/shared/private-address-guard.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.shared.private_address_guard import hostname_to_address, is_public_address


def test_private_address_guard_allows_public_ipv4() -> None:
    """cho phép IPv4 public"""
    for ip in ["8.8.8.8", "1.1.1.1", "203.113.190.1", "13.107.42.14", "99.83.190.102"]:
        assert is_public_address(ip) is True, f"{ip} phải là public"


def test_private_address_guard_blocks_internal_loopback_metadata_cgnat_ipv4() -> None:
    """chặn IPv4 nội bộ, loopback, metadata cloud, CGNAT"""
    blocked = [
        "127.0.0.1",  # loopback - dashboard của chính bot
        "127.1.2.3",
        "0.0.0.0",  # noqa: S104
        "10.0.0.5",  # private
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # metadata AWS/GCP/Azure
        "100.64.0.1",  # CGNAT
        "198.18.0.1",  # benchmarking
        "192.0.2.1",  # documentation
        "224.0.0.1",  # multicast
        "255.255.255.255",
    ]
    for ip in blocked:
        assert is_public_address(ip) is False, f"{ip} phải bị chặn"


def test_private_address_guard_172_32_is_outside_private_range_so_stays_public() -> None:
    """172.32.x.x nằm NGOÀI dải private 172.16/12 nên vẫn public"""
    assert is_public_address("172.32.0.1") is True
    assert is_public_address("172.15.255.255") is True


def test_private_address_guard_allows_public_ipv6() -> None:
    """cho phép IPv6 public"""
    assert is_public_address("2606:4700:4700::1111") is True
    assert is_public_address("2001:4860:4860::8888") is True


def test_private_address_guard_blocks_ipv6_loopback_unique_local_link_local_multicast_documentation() -> None:
    """chặn IPv6 loopback, unique-local, link-local, multicast, documentation"""
    blocked = [
        "::1",  # loopback
        "::",  # unspecified
        "fc00::1",  # unique-local
        "fd12:3456::1",
        "fe80::1",  # link-local
        "fe80::1%eth0",  # có zone index
        "ff02::1",  # multicast
        "2001:db8::1",  # documentation
        "100::1",  # discard prefix
    ]
    for ip in blocked:
        assert is_public_address(ip) is False, f"{ip} phải bị chặn"


def test_private_address_guard_ipv4_mapped_and_nat64_judged_by_inner_ipv4() -> None:
    """IPv4-mapped và NAT64 bị xét theo IPv4 bên trong (không cho lách qua IPv6)"""
    assert is_public_address("::ffff:127.0.0.1") is False
    assert is_public_address("::ffff:169.254.169.254") is False
    assert is_public_address("::ffff:8.8.8.8") is True
    assert is_public_address("64:ff9b::127.0.0.1") is False
    assert is_public_address("64:ff9b::8.8.8.8") is True


def test_private_address_guard_non_ip_strings_are_not_trusted() -> None:
    """chuỗi không phải IP thì không tin (false)"""
    for value in ["", "localhost", "8.8.8", "8.8.8.8.8", "999.1.1.1", "vi-pham::gg::hai"]:
        assert is_public_address(value) is False, f'"{value}" phải bị coi là không hợp lệ'


def test_private_address_guard_hostname_to_address_strips_ipv6_brackets() -> None:
    """hostnameToAddress bỏ ngoặc vuông của IPv6 trong URL"""
    assert hostname_to_address("[::1]") == "::1"
    assert hostname_to_address("example.com") == "example.com"
    assert hostname_to_address("127.0.0.1") == "127.0.0.1"
