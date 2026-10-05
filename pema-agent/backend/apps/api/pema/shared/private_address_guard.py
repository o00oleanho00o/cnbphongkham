# ported from: src/shared/private-address-guard.ts
"""Phân loại địa chỉ IP "public" (được phép tải) vs "nội bộ" (phải chặn).

Vì sao cần: tool ``send_file`` nhận URL do LLM quyết, mà LLM đọc tin nhắn của người lạ. Một tin soạn khéo
(prompt injection) có thể bảo bot tải ``http://127.0.0.1:3900/api/...`` hay endpoint metadata của cloud
(``169.254.169.254``) rồi gửi nội dung ra chat. Chỉ cho phép IP public là cách chặn cả họ lỗi này thay vì đi
vá từng URL.

Forced deviations from the TypeScript original:

* ``node:net`` ``isIPv4`` / ``isIPv6`` -> the stdlib ``ipaddress`` module, used ONLY as the "is this string a
  valid address" gate. The classification itself is the original hand-written byte logic, unchanged, so every
  original case (zone index, ``::ffff:a.b.c.d``, NAT64) behaves the same.
* ``Uint8Array`` -> ``bytes``. The JS ``>>> 0`` (unsigned 32-bit) trick is replaced by an explicit 32-bit
  mask; the original reasoning is kept in the comment at ``_build_blocked_v4``.
* Regex digit classes are written ``[0-9]`` (not ``\\d``): in Python ``\\d`` also matches non-ASCII digits,
  which would be a way to smuggle a lookalike octet past the parser.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _Cidr4:
    base: int
    mask: int


_BLOCKED_V4_CIDRS = (
    "0.0.0.0/8",  # this-network
    "10.0.0.0/8",  # private (RFC1918)
    "100.64.0.0/10",  # CGNAT
    "127.0.0.0/8",  # loopback
    "169.254.0.0/16",  # link-local - metadata cloud (AWS/GCP/Azure)
    "172.16.0.0/12",  # private (RFC1918)
    "192.0.0.0/24",  # IETF protocol assignments
    "192.0.2.0/24",  # documentation
    "192.168.0.0/16",  # private (RFC1918)
    "198.18.0.0/15",  # benchmarking
    "198.51.100.0/24",  # documentation
    "203.0.113.0/24",  # documentation
    "224.0.0.0/4",  # multicast
    "240.0.0.0/4",  # reserved + broadcast 255.255.255.255
)
"""Dải IPv4 không bao giờ được tải: nội bộ, loopback, metadata, tài liệu, multicast."""

_OCTET = re.compile(r"[0-9]{1,3}")
_V6_GROUP = re.compile(r"[0-9a-fA-F]{1,4}")


def _ipv4_to_int(address: str) -> int | None:
    parts = address.split(".")
    if len(parts) != 4:
        return None
    value = 0
    for part in parts:
        if not _OCTET.fullmatch(part):
            return None
        octet = int(part)
        if octet > 255:
            return None
        value = value * 256 + octet
    return value


def _build_blocked_v4() -> list[_Cidr4]:
    # The original masks both mask and base with ``>>> 0`` because JS bit operators return a SIGNED int32
    # (172.16/12, 192.168/16, 169.254/16 would turn negative and never match the unsigned value in
    # is_public_v4 -> the guard leaks silently). Python ints are unbounded, so the explicit 32-bit mask below
    # is the equivalent.
    result: list[_Cidr4] = []
    for cidr in _BLOCKED_V4_CIDRS:
        ip, bits = cidr.split("/")
        prefix = int(bits)
        mask = 0 if prefix == 0 else (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        base = (_ipv4_to_int(ip) or 0) & mask
        result.append(_Cidr4(base=base, mask=mask))
    return result


_BLOCKED_V4 = _build_blocked_v4()


def _is_ipv4(address: str) -> bool:
    try:
        ipaddress.IPv4Address(address)
    except ValueError:
        return False
    return True


def _is_ipv6(address: str) -> bool:
    try:
        ipaddress.IPv6Address(address)
    except ValueError:
        return False
    return True


def is_ip(address: str) -> bool:
    """``net.isIP(address) !== 0``."""
    return _is_ipv4(address) or _is_ipv6(address)


def _ipv6_to_bytes(address: str) -> bytes | None:
    """Bung IPv6 (kể cả dạng rút gọn "::" và dạng lai "::ffff:1.2.3.4") thành 16 byte."""
    text = address.split("%", 1)[0]  # bỏ zone index kiểu fe80::1%eth0
    trailing_v4: list[int] = []

    # Dạng lai có phần IPv4 ở cuối: tách 4 byte cuối, thay bằng 2 group giữ chỗ
    if "." in text:
        colon = text.rfind(":")
        if colon < 0:
            return None
        value = _ipv4_to_int(text[colon + 1 :])
        if value is None:
            return None
        trailing_v4 = [(value >> 24) & 255, (value >> 16) & 255, (value >> 8) & 255, value & 255]
        text = f"{text[:colon]}:0:0"

    halves = text.split("::")
    if len(halves) > 2:
        return None

    def to_groups(part: str | None) -> list[str]:
        return part.split(":") if part else []

    head = to_groups(halves[0])
    tail = to_groups(halves[1]) if len(halves) == 2 else []
    missing = 8 - len(head) - len(tail)
    if missing < 0:
        return None
    if len(halves) == 1 and missing != 0:
        return None  # không rút gọn thì phải đủ 8 group

    groups = [*head, *(["0"] * (missing if len(halves) == 2 else 0)), *tail]
    out = bytearray()
    for group in groups:
        if not _V6_GROUP.fullmatch(group):
            return None
        value = int(group, 16)
        out.extend((value >> 8, value & 255))
    if len(out) != 16:
        return None

    if len(trailing_v4) == 4:
        out[12:16] = bytes(trailing_v4)
    return bytes(out)


def _starts_with_bytes(data: bytes, prefix: list[int]) -> bool:
    return all(index < len(data) and data[index] == value for index, value in enumerate(prefix))


def _is_public_v6(address: str) -> bool:
    data = _ipv6_to_bytes(address)
    if data is None:
        return False

    # IPv4-mapped (::ffff:0:0/96) và NAT64 (64:ff9b::/96): xét theo IPv4 bên trong,
    # nếu không thì "::ffff:127.0.0.1" lọt qua mọi luật IPv6 bên dưới
    mapped_v4 = _starts_with_bytes(data, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xFF, 0xFF])
    nat64 = _starts_with_bytes(data, [0, 0x64, 0xFF, 0x9B, 0, 0, 0, 0, 0, 0, 0, 0])
    if mapped_v4 or nat64:
        return _is_public_v4(".".join(str(b) for b in data[12:]))

    if all(b == 0 for b in data):
        return False  # :: unspecified
    if _starts_with_bytes(data, [0] * 15 + [1]):
        return False  # ::1
    if (data[0] & 0xFE) == 0xFC:
        return False  # fc00::/7 unique-local
    if data[0] == 0xFE and (data[1] & 0xC0) == 0x80:
        return False  # fe80::/10 link-local
    if data[0] == 0xFF:
        return False  # ff00::/8 multicast
    if _starts_with_bytes(data, [0x20, 0x01, 0x0D, 0xB8]):
        return False  # 2001:db8::/32 documentation
    # 100::/64 discard
    return not _starts_with_bytes(data, [0x01, 0, 0, 0, 0, 0, 0, 0])


def _is_public_v4(address: str) -> bool:
    value = _ipv4_to_int(address)
    if value is None:
        return False
    return not any((value & cidr.mask) == cidr.base for cidr in _BLOCKED_V4)


def is_public_address(address: str) -> bool:
    """true = IP public, tải được. Không phải IP hợp lệ cũng trả false (không tin)."""
    if _is_ipv4(address):
        return _is_public_v4(address)
    if _is_ipv6(address):
        return _is_public_v6(address)
    return False


def hostname_to_address(hostname: str) -> str:
    """Bỏ ngoặc vuông của IPv6 trong URL: ``new URL("http://[::1]/").hostname`` trả về "[::1]", để nguyên thì
    ``net.isIP`` không nhận ra là IP và guard bị lọt."""
    if hostname.startswith("[") and hostname.endswith("]"):
        return hostname[1:-1]
    return hostname
