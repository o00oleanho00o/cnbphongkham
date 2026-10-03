# new tests (package U, step U3: storage port, signed upload paths, consult draft template)
"""The pieces of the photo flow that need no database: the local-volume storage, the signed path and the file
signatures, and the template of the consult draft. Synthetic bytes only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pema.clinic.actions.consult_notes import DRAFT_CLOSING, compose_draft
from pema.clinic.media_signing import (
    UPLOAD_TTL_SECONDS,
    expiry_for,
    matches_signature,
    sign_upload,
    verify_upload,
)
from pema.clinic.media_storage import (
    InMemoryMediaStorage,
    LocalVolumeMediaStorage,
    MediaStorageError,
    check_key,
)

SECRET = b"synthetic-secret-with-enough-length-0123456789"
NOW = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)


async def test_local_volume_storage_round_trips_and_deletes(tmp_path: Path) -> None:
    storage = LocalVolumeMediaStorage(tmp_path / "clinic-media")
    key = "patients/abc-123/def-456"
    assert not await storage.exists(key)
    await storage.put(key, b"bytes")
    assert await storage.exists(key)
    assert await storage.get(key) == b"bytes"
    await storage.delete(key)
    await storage.delete(key)  # a missing object is not an error
    with pytest.raises(MediaStorageError):
        await storage.get(key)
    assert list((tmp_path / "clinic-media").rglob("*.part")) == []


@pytest.mark.parametrize(
    "key",
    ["../etc/passwd", "/abs/path", "patients/../x", "Patients/UPPER", "a//b", "", "a" * 300, "patients/x y"],
)
def test_a_key_that_could_leave_the_root_is_refused(key: str) -> None:
    with pytest.raises(MediaStorageError):
        check_key(key)


async def test_the_memory_storage_has_the_same_contract() -> None:
    storage = InMemoryMediaStorage()
    await storage.put("patients/a/b", b"x")
    assert await storage.get("patients/a/b") == b"x"
    with pytest.raises(MediaStorageError):
        await storage.get("patients/a/missing")


def test_a_signed_path_is_bound_to_the_photo_the_size_the_type_and_the_time() -> None:
    expires = expiry_for(NOW)
    assert expires == int(NOW.timestamp()) + UPLOAD_TTL_SECONDS
    signature = sign_upload(SECRET, "m-1", expires, 100, "image/png")
    assert verify_upload(SECRET, "m-1", expires, 100, "image/png", signature, NOW)
    assert not verify_upload(SECRET, "m-2", expires, 100, "image/png", signature, NOW)
    assert not verify_upload(SECRET, "m-1", expires, 101, "image/png", signature, NOW)
    assert not verify_upload(SECRET, "m-1", expires, 100, "image/jpeg", signature, NOW)
    assert not verify_upload(
        b"another-secret-of-the-same-length-000000", "m-1", expires, 100, "image/png", signature, NOW
    )
    assert not verify_upload(
        SECRET, "m-1", expires, 100, "image/png", signature, NOW + timedelta(seconds=UPLOAD_TTL_SECONDS + 1)
    )
    assert verify_upload(
        SECRET, "m-1", expires, 100, "image/png", signature, NOW + timedelta(seconds=UPLOAD_TTL_SECONDS)
    )


def test_file_signatures_are_checked_against_the_declared_type() -> None:
    jpeg = b"\xff\xd8\xff\xe0" + b"x" * 12
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 8
    webp = b"RIFF" + b"\x10\x00\x00\x00" + b"WEBP" + b"x" * 4
    assert matches_signature("image/jpeg", jpeg)
    assert matches_signature("image/png", png)
    assert matches_signature("image/webp", webp)
    assert not matches_signature("image/png", jpeg)
    assert not matches_signature("image/jpeg", webp)
    assert not matches_signature("image/gif", b"GIF89a" + b"x" * 10)
    assert not matches_signature("image/webp", b"RIFF")


def test_the_consult_draft_is_the_typed_points_plus_the_fixed_closing_of_the_old_web() -> None:
    draft = compose_draft("  Da ổn hơn, đỏ giảm.  ", "20/09/2026")
    assert draft == f"Bản nháp ghi chú · 20/09/2026: Da ổn hơn, đỏ giảm. {DRAFT_CLOSING}"
