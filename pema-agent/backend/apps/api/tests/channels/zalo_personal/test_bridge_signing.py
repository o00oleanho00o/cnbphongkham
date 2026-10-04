"""HMAC signing of the bridge protocol (new module, no zalo-agent original).

The Node side (``backend/bridges/zalo-personal/src/auth.ts``) implements the same rule; the fixed vector below is
asserted by ``auth.test.ts`` as well, so the two sides cannot drift apart silently.
"""

from __future__ import annotations

import hashlib
import hmac

from pema.channels.zalo_personal.bridge_signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    compute_signature,
    signed_headers,
    verify_signature,
)

SECRET = "synthetic-bridge-secret-0123456789"
BODY = b'{"type":"message"}'


def headers(timestamp: int, body: bytes = BODY, secret: str = SECRET) -> dict[str, str]:
    return {TIMESTAMP_HEADER: str(timestamp), SIGNATURE_HEADER: compute_signature(secret, timestamp, body)}


def test_compute_signature_la_hmac_sha256_cua_timestamp_cham_body() -> None:
    expected = hmac.new(SECRET.encode(), b"1700000000." + BODY, hashlib.sha256).hexdigest()
    assert compute_signature(SECRET, 1_700_000_000, BODY) == expected


def test_compute_signature_vector_co_dinh_giua_python_va_node() -> None:
    assert compute_signature("secret", 1_700_000_000, b"") == (
        hmac.new(b"secret", b"1700000000.", hashlib.sha256).hexdigest()
    )


def test_verify_signature_chu_ky_hop_le() -> None:
    assert verify_signature(SECRET, headers(1_700_000_000), BODY, now=lambda: 1_700_000_100)


def test_verify_signature_ten_header_khong_phan_biet_hoa_thuong() -> None:
    upper = {
        "X-Pema-Timestamp": "1700000000",
        "X-Pema-Signature": compute_signature(SECRET, 1_700_000_000, BODY),
    }
    assert verify_signature(SECRET, upper, BODY, now=lambda: 1_700_000_000)


def test_verify_signature_sai_chu_ky_bi_tu_choi() -> None:
    bad = headers(1_700_000_000, secret="another-secret-0123456789")
    assert not verify_signature(SECRET, bad, BODY, now=lambda: 1_700_000_000)


def test_verify_signature_body_bi_sua_bi_tu_choi() -> None:
    assert not verify_signature(SECRET, headers(1_700_000_000), BODY + b" ", now=lambda: 1_700_000_000)


def test_verify_signature_timestamp_cu_qua_5_phut_bi_tu_choi() -> None:
    assert not verify_signature(SECRET, headers(1_700_000_000), BODY, now=lambda: 1_700_000_301)
    assert verify_signature(SECRET, headers(1_700_000_000), BODY, now=lambda: 1_700_000_300)


def test_verify_signature_timestamp_tuong_lai_xa_bi_tu_choi() -> None:
    assert not verify_signature(SECRET, headers(1_700_001_000), BODY, now=lambda: 1_700_000_000)


def test_verify_signature_thieu_header_hoac_timestamp_khong_phai_so_bi_tu_choi() -> None:
    assert not verify_signature(SECRET, {}, BODY)
    assert not verify_signature(SECRET, {TIMESTAMP_HEADER: "abc", SIGNATURE_HEADER: "00"}, BODY)
    assert not verify_signature(SECRET, {SIGNATURE_HEADER: "00"}, BODY)


def test_verify_signature_secret_rong_khong_bao_gio_hop_le() -> None:
    assert not verify_signature("", headers(1_700_000_000, secret=""), BODY, now=lambda: 1_700_000_000)


def test_signed_headers_xac_thuc_duoc_boi_verify_signature() -> None:
    produced = signed_headers(SECRET, BODY, now=lambda: 1_700_000_000.0)
    assert verify_signature(SECRET, produced, BODY, now=lambda: 1_700_000_000)
