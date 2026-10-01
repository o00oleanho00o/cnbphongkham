# ported from: src/conversation/media-store.ts
"""Images received from a thread, kept on a LOCAL VOLUME with a configurable root.

Decision of the project owner (2026-10-01, temporary): files and images live on a local volume; object storage
comes later. The root is ``PEMA_MEDIA_DIR`` if set, else ``<PEMA_DATA_DIR>/media`` (``Settings.data_dir``,
default ``.local/data``, git-ignored). Nothing under it is ever committed. A later object-storage backend
replaces this class only: the rest of the system sees ``rel_path`` strings (stored in ``agent.history.images``
and ``agent.image_descriptions``) and the five methods below.

Forced deviations from the original:

* the original had one ``data/media`` directory; with several clinics each one gets its own subdirectory:
  ``<root>/<clinic_id>/media/<account>/<thread>/<msgId>-<index>.<ext>``. ``rel_path`` is unchanged
  (``media/<account>/<thread>/<file>``, relative to the clinic directory), so rows written by the stores
  stay valid when the backend changes;
* file I/O is synchronous and runs in ``asyncio.to_thread`` so it never blocks the event loop;
* the downloader is INJECTED (``ImageDownloader``), there is no default: ``shared/download-image.ts``
  belongs to package D4 (SSRF-guarded download, 8 MB cap) and the composition root passes it in. The
  original already injected it in tests;
* the size/token-estimate log of ``readImageSize`` + ``estimateImageTokens`` (``zalo-image-variant.ts``, not
  ours) becomes an optional ``describe_image`` hook; without it only the kilobytes are logged;
* the log never carries a path: a path holds account and thread ids and the original logged it at info
  level. Ids are kept (they are not PII), the file name is not logged.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from pema.config.env import get_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.daily_task_schedule import start_daily_task
from pema.shared.logger import create_logger

_log = create_logger("media-store")

_EXT_BY_MEDIA_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
_MEDIA_TYPE_BY_EXT = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

_UNSAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_segment(value: str) -> str:
    """Zalo id là số nhưng không tin tưởng: chỉ giữ ký tự an toàn cho tên file."""
    return _UNSAFE_SEGMENT.sub("_", value) or "x"


def resolve_media_root() -> Path:
    """``PEMA_MEDIA_DIR`` or ``<data_dir>/media``: the volume that holds every clinic's images."""
    configured = os.environ.get("PEMA_MEDIA_DIR")
    return Path(configured) if configured else get_settings().data_dir / "media"


@dataclass
class PersistableImage:
    url: str
    local_path: str | None = None


@dataclass
class PersistableMessage:
    thread_id: str
    msg_id: str
    images: list[PersistableImage] = field(default_factory=list[PersistableImage])


@dataclass(frozen=True)
class DownloadedImage:
    """Shape returned by D4's ``download_image``: raw bytes and the response media type."""

    data: bytes
    media_type: str


@dataclass(frozen=True)
class StoredImage:
    base64: str
    media_type: str


ImageDownloader = Callable[[str], Awaitable[DownloadedImage | None]]
ImageDescriber = Callable[[bytes], Mapping[str, object] | None]


def image_paths_of(images: list[PersistableImage]) -> list[str]:
    """Đường dẫn các ảnh đã lưu thành công của 1 tin - để ghi vào cột images."""
    return [i.local_path for i in images if i.local_path]


class MediaStore:
    """Images of the threads on a local volume (``persistBatchImages``, ``loadStoredImage``, ...)."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        downloader: ImageDownloader | None = None,
        describe_image: ImageDescriber | None = None,
    ) -> None:
        self._root = (root or resolve_media_root()).resolve()
        self._downloader = downloader
        self._describe_image = describe_image

    @property
    def root(self) -> Path:
        return self._root

    def _clinic_dir(self, clinic_id: UUID) -> Path:
        return self._root / str(clinic_id)

    def _media_dir(self, clinic_id: UUID) -> Path:
        return self._clinic_dir(clinic_id) / "media"

    async def persist_batch_images(
        self, clinic_id: UUID, account_id: str, messages: list[PersistableMessage]
    ) -> None:
        """Tải ảnh của cả batch về volume, gắn ``local_path`` vào từng ảnh tải thành công. Ảnh lỗi (URL chết,
        quá 8MB, IP nội bộ...) chỉ log debug - không được chặn đường trả lời. Không bao giờ raise để caller
        fire-and-forget được. The downloader is injected (see module docstring)."""
        download = self._downloader
        if download is None:
            _log.warning("Chưa cấu hình trình tải ảnh - bỏ qua lưu ảnh", account_id=account_id)
            return
        for msg in messages:
            for index, image in enumerate(msg.images):
                try:
                    downloaded = await download(image.url)
                    if downloaded is None:
                        continue
                    ext = _EXT_BY_MEDIA_TYPE.get(downloaded.media_type.split(";")[0].strip(), "jpg")
                    rel_path = "/".join(
                        [
                            "media",
                            sanitize_segment(account_id),
                            sanitize_segment(msg.thread_id),
                            f"{sanitize_segment(msg.msg_id)}-{index}.{ext}",
                        ]
                    )
                    abs_path = self._clinic_dir(clinic_id) / rel_path
                    await asyncio.to_thread(_write_file, abs_path, downloaded.data)
                    image.local_path = rel_path

                    # Ảnh là khoản token đắt nhất mỗi lượt - log kích thước thật + ước lượng token để đo được
                    # ngay khi đổi ZALO_IMAGE_QUALITY, khỏi đoán.
                    extra = dict(self._describe_image(downloaded.data) or {}) if self._describe_image else {}
                    _log.info(
                        "Đã lưu ảnh nhận được",
                        account_id=account_id,
                        kb=round(len(downloaded.data) / 1024),
                        **extra,
                    )
                except Exception as err:
                    _log.debug("Không lưu được ảnh - bỏ qua", account_id=account_id, err=err)

    async def delete_thread_media(self, clinic_id: UUID, account_id: str, thread_id: str) -> list[str]:
        """Xóa toàn bộ ảnh đã tải của MỘT thread, trả về danh sách ``rel_path`` vừa xóa
        (``xoaMediaCuaThread``).

        Trả danh sách chứ không trả số lượng vì ``image_descriptions`` khóa theo ``rel_path`` và KHÔNG có cột
        account/thread - đây là đường duy nhất biết được mô tả nào thuộc thread nào. Nên phải liệt kê TRƯỚC
        khi xóa thư mục; đảo thứ tự là mất dấu và mô tả ảnh nằm lại vĩnh viễn.

        Dùng đúng ``sanitize_segment`` của đường ghi, không tự ghép tay: lệch một phép chuẩn hóa là xóa nhầm
        thư mục khác hoặc không xóa gì mà vẫn báo thành công.
        """
        return await asyncio.to_thread(
            self._delete_thread_media_sync,
            clinic_id,
            sanitize_segment(account_id),
            sanitize_segment(thread_id),
        )

    def _delete_thread_media_sync(self, clinic_id: UUID, account: str, thread: str) -> list[str]:
        thread_dir = self._media_dir(clinic_id) / account / thread
        try:
            names = [e.name for e in os.scandir(thread_dir) if e.is_file()]
        except OSError:
            # Thread chưa từng có ảnh thì không có thư mục - không phải lỗi.
            return []

        rel_paths = ["/".join(["media", account, thread, n]) for n in names]
        try:
            shutil.rmtree(thread_dir)
        except OSError as err:
            # Xóa file hỏng (file đang mở, quyền) KHÔNG được làm hỏng cả lượt xóa: phần trong DB mới là thứ
            # quyết định bot còn nhớ gì.
            _log.warning(
                "Không xóa được thư mục ảnh của thread", err=err, account_id=account, thread_id=thread
            )
        return rel_paths

    async def load_stored_image(self, clinic_id: UUID, rel_path: str) -> StoredImage | None:
        """Đọc ảnh đã lưu theo đường dẫn tương đối trong DB. File mất (đã bị dọn theo
        ``MEDIA_RETENTION_DAYS``) hoặc đường dẫn thoát khỏi thư mục media của phòng khám đều trả ``None``."""
        return await asyncio.to_thread(self._load_stored_image_sync, clinic_id, rel_path)

    def _load_stored_image_sync(self, clinic_id: UUID, rel_path: str) -> StoredImage | None:
        try:
            media_dir = self._media_dir(clinic_id).resolve()
            abs_path = (self._clinic_dir(clinic_id) / rel_path).resolve()
            if not abs_path.is_relative_to(media_dir) or abs_path == media_dir:
                return None
            data = abs_path.read_bytes()
        except (OSError, ValueError):
            return None
        ext = abs_path.suffix.lstrip(".").lower()
        return StoredImage(
            base64=base64.b64encode(data).decode("ascii"),
            media_type=_MEDIA_TYPE_BY_EXT.get(ext, "image/jpeg"),
        )

    async def cleanup_expired_media(self, now: float | None = None) -> int:
        """Xóa file media cũ hơn ``MEDIA_RETENTION_DAYS`` + gỡ thư mục rỗng, ở mọi phòng khám. Trả về số file
        đã xóa."""
        cutoff = (now if now is not None else time.time()) - get_tuning_int("MEDIA_RETENTION_DAYS") * 86400
        return await asyncio.to_thread(self._cleanup_sync, cutoff)

    def _cleanup_sync(self, cutoff: float) -> int:
        removed = 0
        try:
            clinic_dirs = [e.path for e in os.scandir(self._root) if e.is_dir()]
        except OSError:
            return 0  # thư mục chưa tồn tại (chưa nhận ảnh nào)
        for clinic_dir in clinic_dirs:
            removed += _remove_expired_in(Path(clinic_dir) / "media", cutoff)
        return removed


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _remove_expired_in(directory: Path, cutoff: float) -> int:
    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0
    for entry in entries:
        full = Path(entry.path)
        try:
            if entry.is_dir():
                removed += _remove_expired_in(full, cutoff)
                if not any(full.iterdir()):
                    full.rmdir()
            elif full.stat().st_mtime < cutoff:
                full.unlink()
                removed += 1
        except OSError as err:
            _log.debug("Không dọn được file media - bỏ qua", err=err)
    return removed


async def _cleanup_everything(
    *,
    media: MediaStore,
    list_clinic_ids: Callable[[], Awaitable[list[UUID]]],
    prune_image_descriptions: Callable[[UUID, int], Awaitable[int]],
    prune_traces: Callable[[UUID], Awaitable[int]],
) -> None:
    removed = await media.cleanup_expired_media()
    pruned_descriptions = 0
    pruned_traces = 0
    for clinic_id in await list_clinic_ids():
        # Mô tả ảnh của sidecar dọn cùng nhịp: quá hạn thì cả pixel lẫn mô tả cùng đi.
        pruned_descriptions += await prune_image_descriptions(
            clinic_id, get_tuning_int("MEDIA_RETENTION_DAYS")
        )
        # Trace step agent dọn cùng nhịp - bảng phình nhanh nhất trong DB.
        pruned_traces += await prune_traces(clinic_id)
    if removed > 0 or pruned_descriptions > 0 or pruned_traces > 0:
        _log.info(
            "Đã dọn file media + mô tả ảnh + trace hết hạn",
            removed=removed,
            pruned_descriptions=pruned_descriptions,
            pruned_traces=pruned_traces,
        )


def start_media_cleanup_schedule(
    *,
    media: MediaStore,
    list_clinic_ids: Callable[[], Awaitable[list[UUID]]],
    prune_image_descriptions: Callable[[UUID, int], Awaitable[int]],
    prune_traces: Callable[[UUID], Awaitable[int]],
    interval_seconds: float = 24 * 60 * 60.0,
) -> asyncio.Task[None]:
    """Dọn ngay lúc gọi + lặp lại mỗi 24h. The per-clinic work is injected
    (``ClinicDatabase.list_active_clinic_ids``,
    ``ImageDescriptionStoreImpl.prune_expired_image_descriptions``, ``AgentTraceStore.prune_old_traces``)
    so this module needs no database import."""

    async def task() -> None:
        await _cleanup_everything(
            media=media,
            list_clinic_ids=list_clinic_ids,
            prune_image_descriptions=prune_image_descriptions,
            prune_traces=prune_traces,
        )

    return start_daily_task("media-cleanup", task, interval_seconds=interval_seconds)
