# Original has no dedicated unit test for secret-cipher-core (it is covered by decrypt-failure.test.ts, which
# belongs to D1 together with runtime-llm-settings). These tests pin the contract the other packages rely on.
from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from cryptography.exceptions import InvalidTag

from pema.config import env as env_module
from pema.config.secret_cipher import SecretKeyMissingError, decrypt_secret, encrypt_secret
from pema.config.secret_cipher_core import IV_BYTES, TAG_BYTES, decrypt_with, encrypt_with, mask_secret

KEY_A = "a" * 64
KEY_B = "b" * 64


def test_round_trip_and_wire_format() -> None:
    sealed = encrypt_with(KEY_A, "sk-synthetic-secret")
    raw = base64.b64decode(sealed)
    assert len(raw) == IV_BYTES + TAG_BYTES + len("sk-synthetic-secret")
    assert decrypt_with(KEY_A, sealed) == "sk-synthetic-secret"


def test_each_encryption_uses_a_fresh_iv() -> None:
    assert encrypt_with(KEY_A, "same") != encrypt_with(KEY_A, "same")


def test_wrong_key_and_tampering_are_detected() -> None:
    sealed = encrypt_with(KEY_A, "secret")
    with pytest.raises(InvalidTag):
        decrypt_with(KEY_B, sealed)
    raw = bytearray(base64.b64decode(sealed))
    raw[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_with(KEY_A, base64.b64encode(bytes(raw)).decode())


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_with("abcd", "x")


def test_mask_secret_shows_which_key_but_not_the_key() -> None:
    assert mask_secret("") == "chưa cấu hình"
    assert mask_secret("short") == "***"
    assert mask_secret("sk-abcdefghijklmnop") == "sk-ab...mnop"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", KEY_A)
    env_module.get_settings.cache_clear()
    yield
    env_module.get_settings.cache_clear()


@pytest.mark.usefixtures("configured")
def test_settings_wired_cipher_round_trips() -> None:
    assert decrypt_secret(encrypt_secret("bot-token-synthetic")) == "bot-token-synthetic"


def test_missing_key_raises_a_named_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEMA_SECRET_ENCRYPTION_KEY", raising=False)
    env_module.get_settings.cache_clear()
    try:
        with pytest.raises(SecretKeyMissingError):
            encrypt_secret("x")
    finally:
        env_module.get_settings.cache_clear()
