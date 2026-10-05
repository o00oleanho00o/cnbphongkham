# ported from: src/conversation/media-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

No database needed: the media store only touches the local volume. ``tmp_path`` plays ``dataDir``; the layout
has one subdirectory per clinic (``<root>/<clinic_id>/media/...``), ``rel_path`` is unchanged. The downloader is
injected exactly as in the original tests.
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.conversation.media_store import (
    DownloadedImage,
    MediaStore,
    PersistableImage,
    PersistableMessage,
    image_paths_of,
    resolve_media_root,
    sanitize_segment,
)

# 1x1 PNG hợp lệ - đủ cho test lưu/đọc, không cần ảnh thật
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

CLINIC = uuid.UUID("00000000-0000-0000-0000-00000000c001")


def _download_ok(media_type: str = "image/png"):
    """Downloader giả: tiêm vào persist_batch_images nên test không chạm mạng thật."""

    async def download(url: str) -> DownloadedImage | None:
        return DownloadedImage(data=PNG_BYTES, media_type=media_type)

    return download


async def _download_fail(url: str) -> DownloadedImage | None:
    return None


@pytest.fixture(autouse=True)
def _tuning() -> None:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(StaticTuningProvider({"MEDIA_RETENTION_DAYS": 7}))


def _msg(thread_id: str, msg_id: str, url: str) -> PersistableMessage:
    return PersistableMessage(thread_id=thread_id, msg_id=msg_id, images=[PersistableImage(url=url)])


async def test_media_store_persist_image_saves_the_file_in_place_sets_local_path_and_loads_base64_back(
    tmp_path: Path,
) -> None:
    """persist ảnh: lưu file đúng chỗ, gắn localPath, load lại được base64"""
    store = MediaStore(tmp_path, downloader=_download_ok())
    msg = _msg("t-1", "m-100", "https://z.example/a.png")

    await store.persist_batch_images(CLINIC, "acc-1", [msg])

    assert msg.images[0].local_path == "media/acc-1/t-1/m-100-0.png"
    assert (tmp_path / str(CLINIC) / "media/acc-1/t-1/m-100-0.png").exists()

    loaded = await store.load_stored_image(CLINIC, msg.images[0].local_path or "")
    assert loaded is not None
    assert loaded.media_type == "image/png"
    assert loaded.base64 == base64.b64encode(PNG_BYTES).decode("ascii")


async def test_media_store_download_failure_sets_no_local_path_and_does_not_raise(tmp_path: Path) -> None:
    """tải lỗi thì không gắn localPath và không throw"""
    store = MediaStore(tmp_path, downloader=_download_fail)
    msg = _msg("t-1", "m-404", "https://z.example/die.png")

    await store.persist_batch_images(CLINIC, "acc-1", [msg])

    assert msg.images[0].local_path is None
    assert image_paths_of(msg.images) == []


async def test_media_store_a_raising_downloader_does_not_block_the_reply_path(tmp_path: Path) -> None:
    """(thêm) downloader ném lỗi: không bao giờ reject để caller fire-and-forget được"""

    async def boom(url: str) -> DownloadedImage | None:
        raise OSError("mạng đứt")

    store = MediaStore(tmp_path, downloader=boom)
    msg = _msg("t-1", "m-boom", "https://z.example/x.png")
    await store.persist_batch_images(CLINIC, "acc-1", [msg])
    assert msg.images[0].local_path is None


async def test_media_store_ids_with_odd_characters_are_sanitised_out_of_the_path(tmp_path: Path) -> None:
    """id chứa ký tự lạ bị sanitize khỏi đường dẫn"""
    store = MediaStore(tmp_path, downloader=_download_ok("image/jpeg"))
    msg = _msg("../thoat", "a/b:c", "https://z.example/x.jpg")

    await store.persist_batch_images(CLINIC, "acc-1", [msg])

    assert msg.images[0].local_path == "media/acc-1/___thoat/a_b_c-0.jpg"
    assert sanitize_segment("") == "x"


async def test_media_store_load_stored_image_refuses_paths_that_escape_the_media_directory(
    tmp_path: Path,
) -> None:
    """loadStoredImage chặn đường dẫn thoát khỏi data/media"""
    (tmp_path / str(CLINIC)).mkdir(parents=True)
    (tmp_path / str(CLINIC) / "secret.db").write_bytes(b"secret")
    (tmp_path / "other-clinic-file.png").write_bytes(PNG_BYTES)
    store = MediaStore(tmp_path)

    assert await store.load_stored_image(CLINIC, "../zalo-agent.db") is None
    assert await store.load_stored_image(CLINIC, "media/../secret.db") is None
    assert await store.load_stored_image(CLINIC, "../other-clinic-file.png") is None
    assert await store.load_stored_image(CLINIC, "media") is None


async def test_media_store_images_of_one_clinic_cannot_be_read_with_another_clinics_id(
    tmp_path: Path,
) -> None:
    """(thêm) mỗi phòng khám một thư mục: cùng rel_path nhưng khác clinic_id thì không đọc được"""
    store = MediaStore(tmp_path, downloader=_download_ok())
    msg = _msg("t-1", "m-1", "https://z.example/a.png")
    await store.persist_batch_images(CLINIC, "acc-1", [msg])
    rel = msg.images[0].local_path or ""

    assert await store.load_stored_image(CLINIC, rel) is not None
    assert await store.load_stored_image(uuid.UUID(int=2), rel) is None


async def test_media_store_missing_file_after_cleanup_returns_none_instead_of_raising(tmp_path: Path) -> None:
    """file không tồn tại (đã bị dọn) trả null thay vì throw"""
    store = MediaStore(tmp_path)
    assert await store.load_stored_image(CLINIC, "media/acc-1/t-1/khong-co-0.jpg") is None


async def test_media_store_cleanup_removes_expired_files_keeps_new_ones_and_removes_empty_directories(
    tmp_path: Path,
) -> None:
    """cleanup xóa file quá hạn, giữ file mới, gỡ thư mục rỗng"""
    store = MediaStore(tmp_path, downloader=_download_ok())
    old_msg = _msg("t-old", "m-old", "https://z.example/o.png")
    new_msg = _msg("t-new", "m-new", "https://z.example/n.png")
    await store.persist_batch_images(CLINIC, "acc-2", [old_msg, new_msg])

    # Giả lập file cũ 8 ngày (quá MEDIA_RETENTION_DAYS=7)
    old_abs = tmp_path / str(CLINIC) / (old_msg.images[0].local_path or "")
    eight_days_ago = time.time() - 8 * 24 * 60 * 60
    os.utime(old_abs, (eight_days_ago, eight_days_ago))

    removed = await store.cleanup_expired_media()

    assert removed >= 1
    assert not old_abs.exists()
    assert not old_abs.parent.exists(), "thư mục rỗng phải bị gỡ"
    assert (tmp_path / str(CLINIC) / (new_msg.images[0].local_path or "")).exists()


async def test_media_store_cleanup_on_a_missing_root_removes_nothing(tmp_path: Path) -> None:
    """(thêm) chưa nhận ảnh nào (thư mục gốc chưa tồn tại) thì dọn là no-op"""
    assert await MediaStore(tmp_path / "chua-co").cleanup_expired_media() == 0


async def test_media_store_delete_thread_media_returns_the_rel_paths_of_exactly_that_thread(
    tmp_path: Path,
) -> None:
    """(thêm) xóa ảnh của một thread trả đúng danh sách rel_path, thread khác còn nguyên"""
    store = MediaStore(tmp_path, downloader=_download_ok())
    mine = _msg("t-1", "m-1", "https://z.example/a.png")
    other = _msg("t-2", "m-2", "https://z.example/b.png")
    await store.persist_batch_images(CLINIC, "acc-1", [mine, other])

    assert await store.delete_thread_media(CLINIC, "acc-1", "t-1") == ["media/acc-1/t-1/m-1-0.png"]
    assert await store.load_stored_image(CLINIC, other.images[0].local_path or "") is not None
    assert await store.delete_thread_media(CLINIC, "acc-1", "t-1") == []


async def test_media_store_root_is_configurable_through_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(thêm) đường dẫn volume cấu hình được qua PEMA_MEDIA_DIR"""
    monkeypatch.setenv("PEMA_MEDIA_DIR", str(tmp_path / "volume"))
    assert resolve_media_root() == tmp_path / "volume"
    assert MediaStore().root == (tmp_path / "volume").resolve()
