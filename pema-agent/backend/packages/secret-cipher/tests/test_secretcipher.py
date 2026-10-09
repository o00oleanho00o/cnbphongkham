"""The shared secret cipher: round trip, wire format and a payload written by the Node original."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from secretcipher import IV_BYTES, TAG_BYTES, decrypt_with, encrypt_with, mask_secret

KEY = "a" * 64
NODE_IV = bytes(IV_BYTES)


def test_round_trip_and_wire_format() -> None:
    sealed = encrypt_with(KEY, "sk-synthetic-secret")
    raw = base64.b64decode(sealed)

    assert len(raw) == IV_BYTES + TAG_BYTES + len("sk-synthetic-secret")
    assert decrypt_with(KEY, sealed) == "sk-synthetic-secret"
    assert encrypt_with(KEY, "same") != encrypt_with(KEY, "same")


def test_a_payload_in_node_order_is_read() -> None:
    sealed = AESGCM(bytes.fromhex(KEY)).encrypt(NODE_IV, b"sk-node", None)
    node_payload = base64.b64encode(NODE_IV + sealed[-TAG_BYTES:] + sealed[:-TAG_BYTES]).decode()

    assert decrypt_with(KEY, node_payload) == "sk-node"


def test_a_wrong_key_a_tampered_payload_and_a_short_key_are_refused() -> None:
    sealed = encrypt_with(KEY, "secret")
    raw = bytearray(base64.b64decode(sealed))
    raw[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        decrypt_with("b" * 64, sealed)
    with pytest.raises(InvalidTag):
        decrypt_with(KEY, base64.b64encode(bytes(raw)).decode())
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_with("abcd", "x")


def test_a_masked_secret_names_the_key_without_revealing_it() -> None:
    assert mask_secret("sk-abcdefghijklmnop") == "sk-ab...mnop"
    assert mask_secret("short") == "***"
    assert mask_secret("") == "chưa cấu hình"
