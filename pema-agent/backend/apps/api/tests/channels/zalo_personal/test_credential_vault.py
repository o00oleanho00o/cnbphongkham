"""The Zalo credential is stored encrypted and is never readable from the account store alone (new module; port of the
intent of ``zalo-credential-store.ts``: cookie = full account access, so AES-256-GCM at rest)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.config import secret_cipher
from pema.config.env import get_settings
from pema.config.secret_cipher import SecretKeyMissingError
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAccountStore

CREDENTIAL = {
    "cookie": [{"key": "synthetic", "value": "synthetic-cookie"}],
    "imei": "imei-1",
    "userAgent": "ua",
}


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "0123456789abcdef" * 4)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_credential_duoc_ma_hoa_that_truoc_khi_vao_store(key: None) -> None:
    accounts = InMemoryAccountStore()
    vault = CredentialVault(accounts)

    await vault.save_credentials(FAKE_CLINIC_ID, "acc-1", CREDENTIAL)

    stored = accounts.credentials[(FAKE_CLINIC_ID, "acc-1")]
    assert stored is not None
    assert "synthetic-cookie" not in stored, "store không bao giờ giữ cookie ở dạng rõ"
    assert "imei-1" not in stored
    assert secret_cipher.decrypt_secret(stored).count("synthetic-cookie") == 1


async def test_credential_doc_lai_dung_nhu_da_luu(key: None) -> None:
    vault = CredentialVault(InMemoryAccountStore())
    await vault.save_credentials(FAKE_CLINIC_ID, "acc-1", CREDENTIAL)
    assert await vault.load_credentials(FAKE_CLINIC_ID, "acc-1") == CREDENTIAL
    assert await vault.has_credentials(FAKE_CLINIC_ID, "acc-1") is True


async def test_chua_co_credential_thi_load_tra_none_va_has_la_false(key: None) -> None:
    vault = CredentialVault(InMemoryAccountStore())
    assert await vault.load_credentials(FAKE_CLINIC_ID, "acc-1") is None
    assert await vault.has_credentials(FAKE_CLINIC_ID, "acc-1") is False


async def test_xoa_credential_khi_xoa_account(key: None) -> None:
    vault = CredentialVault(InMemoryAccountStore())
    await vault.save_credentials(FAKE_CLINIC_ID, "acc-1", CREDENTIAL)
    await vault.delete_credentials(FAKE_CLINIC_ID, "acc-1")
    assert await vault.has_credentials(FAKE_CLINIC_ID, "acc-1") is False


async def test_thieu_khoa_ma_hoa_thi_khong_luu_gi_ca_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEMA_SECRET_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    try:
        accounts = InMemoryAccountStore()
        with pytest.raises(SecretKeyMissingError):
            await CredentialVault(accounts).save_credentials(FAKE_CLINIC_ID, "acc-1", CREDENTIAL)
        assert accounts.credentials == {}
    finally:
        get_settings.cache_clear()


async def test_ban_ma_hong_thi_load_bao_loi_khong_tra_du_lieu_rac(key: None) -> None:
    accounts = InMemoryAccountStore()
    accounts.credentials[(FAKE_CLINIC_ID, "acc-1")] = "not-a-ciphertext"
    with pytest.raises(Exception, match=r".+"):
        await CredentialVault(accounts).load_credentials(FAKE_CLINIC_ID, "acc-1")
