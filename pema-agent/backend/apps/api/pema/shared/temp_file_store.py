# ported from: src/shared/temp-file-store.ts
"""File tạm cho việc gửi file tải từ URL. Nguyên tắc: file được xóa ngay sau khi gửi xong (kể cả khi gửi
lỗi) - ``<data_dir>/tmp`` không phải nơi lưu trữ. Sweep định kỳ chỉ để quét file bị bỏ lại khi process chết
giữa lượt gửi.

Forced deviations from the TypeScript original:

* ``dataDir`` of ``env.ts`` -> ``pema.config.env.get_settings().data_dir``, read at CALL time (not at
  import) so a test or a changed ``PEMA_DATA_DIR`` takes effect without re-importing.
* ``startTempFileCleanupSchedule()`` called ``startDailyTask`` of ``src/shared/daily-task-schedule.ts``, which
  belongs to package D2 (``pema.shared.daily_task_schedule``). This module does NOT import it: it exposes the
  cleanup as the plain function ``cleanup_orphan_temp_files`` and the coroutine ``temp_file_cleanup_loop()``
  (run now, then every 24 h, errors swallowed and logged). The ``workers`` module wires it later with
  ``asyncio.create_task(temp_file_cleanup_loop())`` and cancels the task on shutdown (the equivalent of
  ``unref()``).
* ``Buffer`` -> ``bytes``; the callback receives a ``pathlib.Path``. File I/O stays synchronous as in the
  original (the files are small and written once).
* ``path.basename`` -> ``_basename``: it also treats a backslash as a separator, because the model-chosen name
  must not escape the temp directory on any platform. A name that reduces to ``""``, ``"."`` or ``".."`` is
  replaced by ``"tep-tam"`` (the original would try to write over the directory and fail).
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from pema.config.env import get_settings
from pema.shared.logger import create_logger

log = create_logger("temp-file-store")

ORPHAN_AGE_MS = 6 * 60 * 60 * 1000
"""File tạm sống lâu hơn mức này = chắc chắn mồ côi (lượt gửi bình thường tính bằng giây)."""

_ONE_DAY_SECONDS = 24 * 60 * 60


def temp_dir() -> Path:
    """``<data_dir>/tmp``."""
    return get_settings().data_dir / "tmp"


def _basename(file_name: str) -> str:
    name = file_name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name if name not in ("", ".", "..") else "tep-tam"


def _write_private(file_path: Path, data: bytes) -> None:
    """``writeFileSync(path, data, { mode: 0o600 })``. ``O_EXCL``: never write through an existing file or
    symlink."""
    fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


async def with_temp_file[T](file_name: str, data: bytes, use: Callable[[Path], Awaitable[T]]) -> T:
    """Ghi bytes ra file tạm, chạy ``use(file_path)`` rồi xóa file trong ``finally``. Tên file có tiền tố
    random để 2 lượt gửi cùng lúc không đè nhau."""
    directory = temp_dir()
    directory.mkdir(parents=True, exist_ok=True)
    prefix = secrets.token_hex(6)
    file_path = directory / f"{prefix}-{_basename(file_name)}"
    _write_private(file_path, data)

    try:
        return await use(file_path)
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError as err:
            log.debug("Không xóa được file tạm - sweep định kỳ sẽ dọn", err=err)


async def with_named_temp_file[T](file_name: str, data: bytes, use: Callable[[Path], Awaitable[T]]) -> T:
    """Như ``with_temp_file`` nhưng GIỮ NGUYÊN tên file: phần random nằm ở thư mục con chứ không phải tiền tố
    tên. Dùng cho file bot tự dựng (.docx/.xlsx) vì người nhận nhìn thấy tên này - "bao-gia.docx" đọc được,
    "a1b2c3-bao-gia.docx" thì không."""
    directory = temp_dir() / secrets.token_hex(6)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / _basename(file_name)
    _write_private(file_path, data)

    try:
        return await use(file_path)
    finally:
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass
        except OSError as err:
            log.debug("Không xóa được thư mục tạm - sweep định kỳ sẽ dọn", err=err)


def _now_ms() -> float:
    return time.time() * 1000


def cleanup_orphan_temp_files(
    max_age_ms: float = ORPHAN_AGE_MS, *, now_ms: Callable[[], float] = _now_ms
) -> int:
    """Xóa file tạm mồ côi. Trả về số file đã xóa. ``now_ms`` is the clock (epoch milliseconds)."""
    cutoff = now_ms() - max_age_ms
    directory = temp_dir()
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0  # chưa gửi file nào từ URL

    removed = 0
    for entry in entries:
        # Thư mục con là của with_named_temp_file - dọn cả cụm, không bỏ sót
        is_dir = entry.is_dir(follow_symlinks=False)
        if not (entry.is_file(follow_symlinks=False) or is_dir):
            continue
        try:
            if entry.stat(follow_symlinks=False).st_mtime * 1000 >= cutoff:
                continue
            if is_dir:
                shutil.rmtree(entry.path)
            else:
                os.unlink(entry.path)
            removed += 1
        except OSError as err:
            log.debug("Không dọn được file tạm - bỏ qua", err=err)
    return removed


async def temp_file_cleanup_loop(
    *,
    interval_seconds: float = _ONE_DAY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    cleanup: Callable[[], int] = cleanup_orphan_temp_files,
) -> None:
    """``startTempFileCleanupSchedule``: dọn ngay lúc gọi + lặp lại mỗi 24h - bắt file mồ côi sau khi process
    bị kill. Lỗi bị nuốt và log (một tác vụ dọn dẹp hỏng không được làm chết worker). Runs until cancelled;
    ``sleep`` and ``cleanup`` are injectable so a test needs no real waiting."""
    while True:
        try:
            removed = cleanup()
            if removed > 0:
                log.info("Đã dọn file tạm mồ côi", removed=removed)
        except Exception as err:
            log.error("Tác vụ định kỳ lỗi - bỏ qua lượt này", label="temp-file-cleanup", err=err)
        await sleep(interval_seconds)
