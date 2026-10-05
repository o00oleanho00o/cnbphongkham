# ported from: src/shared/temp-file-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``setupTestEnv`` (a throw-away data dir) is the ``data_dir`` fixture below: ``PEMA_DATA_DIR`` in ``tmp_path``
and a cleared ``get_settings`` cache.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from pema.config import env as env_module
from pema.shared import temp_file_store as store


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("PEMA_DATA_DIR", str(tmp_path))
    env_module.get_settings.cache_clear()
    yield tmp_path
    env_module.get_settings.cache_clear()


def tmp_dir(data_dir: Path) -> Path:
    return data_dir / "tmp"


# ------------------------------------------------------------------ temp-file-store


async def test_temp_file_store_writes_temp_file_then_deletes_after_use() -> None:
    """ghi file tạm rồi xóa sau khi dùng xong"""
    seen: list[Path] = []

    async def use(p: Path) -> str:
        seen.append(p)
        assert p.exists(), "file phải tồn tại trong lúc dùng"  # noqa: ASYNC240
        assert p.read_text(encoding="utf-8") == "noi dung"  # noqa: ASYNC240
        return "da-gui"

    result = await store.with_temp_file("bao-gia.pdf", b"noi dung", use)

    assert result == "da-gui"
    assert seen[0].exists() is False, "file phải bị xóa sau khi dùng"
    assert seen[0].name.endswith("-bao-gia.pdf"), "giữ tên gốc để người nhận đọc được"


async def test_temp_file_store_send_failure_still_deletes_file() -> None:
    """gửi lỗi thì vẫn xóa file (không để rác lại)"""
    seen: list[Path] = []

    async def use(p: Path) -> None:
        seen.append(p)
        raise RuntimeError("gửi thất bại")

    with pytest.raises(RuntimeError):
        await store.with_temp_file("x.zip", b"abc", use)
    assert seen[0].exists() is False


async def test_temp_file_store_file_name_takes_basename_only_does_not_escape_data_tmp(data_dir: Path) -> None:
    """tên file chỉ lấy basename - không thoát khỏi data/tmp"""
    seen: list[Path] = []

    async def use(p: Path) -> None:
        seen.append(p)

    await store.with_temp_file("../../thoat.txt", b"x", use)
    assert seen[0].parent == tmp_dir(data_dir)


async def test_temp_file_store_two_sends_with_same_file_name_do_not_overwrite_each_other() -> None:
    """2 lượt gửi cùng tên file không đè nhau"""
    paths: list[Path] = []
    both_in = asyncio.Event()

    async def hold(p: Path) -> None:
        paths.append(p)
        if len(paths) == 2:
            both_in.set()
        await both_in.wait()  # both files exist at the same moment: the original held them with a 20 ms timer

    await asyncio.gather(
        store.with_temp_file("cung-ten.pdf", b"a", hold),
        store.with_temp_file("cung-ten.pdf", b"b", hold),
    )
    assert paths[0] != paths[1]


def test_temp_file_store_cleanup_removes_old_orphan_files_keeps_new_ones(data_dir: Path) -> None:
    """cleanup xóa file mồ côi cũ, giữ file mới"""
    tmp_dir(data_dir).mkdir(parents=True, exist_ok=True)
    old_file = tmp_dir(data_dir) / "mo-coi.bin"
    new_file = tmp_dir(data_dir) / "vua-tao.bin"
    old_file.write_text("cu")
    new_file.write_text("moi")
    long_ago = time.time() - 8 * 60 * 60  # 8h
    os.utime(old_file, (long_ago, long_ago))

    removed = store.cleanup_orphan_temp_files()

    assert removed == 1
    assert old_file.exists() is False
    assert new_file.exists() is True


def test_temp_file_store_no_tmp_directory_yet_cleanup_returns_zero_without_throwing() -> None:
    """chưa có thư mục tmp thì cleanup trả 0, không throw"""
    assert store.cleanup_orphan_temp_files() == 0


# ------------------------------------------------------------------ chặn thoát thư mục tạm - cả hai hàm cùng một bất biến

# Tên file ở cả hai hàm đều đến từ chỗ ta không kiểm soát: model tự đặt tên cho `send_file` và hai tool tài liệu.
# `basename` là thứ duy nhất đứng giữa cái tên đó và một lời ghi đè file bất kỳ trên máy chủ.
TEN_XAU = "../../../etc/passwd"


async def test_escape_guard_with_temp_file_keeps_file_in_temp_dir(data_dir: Path) -> None:
    """withTempFile giữ file trong thư mục tạm"""
    seen: list[Path] = []

    async def use(duong_dan: Path) -> None:
        seen.append(duong_dan)

    await store.with_temp_file(TEN_XAU, b"x", use)
    assert seen[0].parent == tmp_dir(data_dir), f"thoát ra ngoài: {seen[0]}"


async def test_escape_guard_with_named_temp_file_keeps_file_in_subdirectory_of_temp_dir(
    data_dir: Path,
) -> None:
    """withNamedTempFile giữ file trong thư mục con của thư mục tạm"""
    seen: list[Path] = []

    async def use(duong_dan: Path) -> None:
        seen.append(duong_dan)

    await store.with_named_temp_file(TEN_XAU, b"x", use)
    # Hàm này cố ý giữ NGUYÊN tên (để người nhận thấy đúng tên file), nên nó
    # đặt file trong một thư mục con random - thư mục con đó vẫn phải nằm trong
    # thư mục tạm.
    assert seen[0].parent.parent == tmp_dir(data_dir), f"thoát ra ngoài: {seen[0]}"
    assert seen[0].name == "passwd"


# ---- added: what the TypeScript suite did not cover ----


async def test_with_named_temp_file_keeps_name_and_removes_whole_directory(data_dir: Path) -> None:
    """giữ nguyên tên file và xóa cả thư mục con sau khi dùng"""
    seen: list[Path] = []

    async def use(p: Path) -> int:
        seen.append(p)
        return len(p.read_bytes())  # noqa: ASYNC240

    assert await store.with_named_temp_file("bao-gia.docx", b"noi dung", use) == 8
    assert seen[0].name == "bao-gia.docx"
    assert seen[0].parent.exists() is False
    assert list(tmp_dir(data_dir).iterdir()) == []


async def test_backslash_and_dot_names_cannot_escape_or_hit_the_directory(data_dir: Path) -> None:
    """tên có dấu gạch ngược hoặc '..' vẫn nằm trong thư mục tạm"""
    seen: list[Path] = []

    async def use(p: Path) -> None:
        seen.append(p)

    await store.with_named_temp_file("..\\..\\thoat.txt", b"x", use)
    await store.with_named_temp_file("..", b"x", use)
    await store.with_temp_file("a/b\\c.txt", b"x", use)
    assert seen[0].name == "thoat.txt"
    assert seen[1].name == "tep-tam"
    assert seen[2].name.endswith("-c.txt")
    for p in seen[:2]:
        assert p.parent.parent == tmp_dir(data_dir)
    assert seen[2].parent == tmp_dir(data_dir)


def test_cleanup_removes_old_orphan_directories_of_named_temp_files(data_dir: Path) -> None:
    """thư mục con mồ côi của withNamedTempFile được dọn cả cụm"""
    orphan = tmp_dir(data_dir) / "a1b2c3d4e5f6"
    orphan.mkdir(parents=True)
    (orphan / "bao-gia.docx").write_bytes(b"x")
    long_ago = time.time() - 8 * 60 * 60
    os.utime(orphan, (long_ago, long_ago))

    assert store.cleanup_orphan_temp_files() == 1
    assert orphan.exists() is False


def test_cleanup_uses_the_injected_clock_and_age(data_dir: Path) -> None:
    """đồng hồ và tuổi tối đa tiêm được: không cần chờ thật"""
    tmp_dir(data_dir).mkdir(parents=True)
    f = tmp_dir(data_dir) / "x.bin"
    f.write_text("x")
    mtime_ms = f.stat().st_mtime * 1000

    assert store.cleanup_orphan_temp_files(1000, now_ms=lambda: mtime_ms + 500) == 0
    assert f.exists()
    assert store.cleanup_orphan_temp_files(1000, now_ms=lambda: mtime_ms + 5000) == 1
    assert f.exists() is False


async def test_temp_file_cleanup_loop_runs_now_then_every_interval_and_swallows_errors() -> None:
    """vòng dọn: chạy ngay, lặp theo chu kỳ, lỗi bị nuốt và log"""
    calls: list[int] = []
    slept: list[float] = []

    def cleanup() -> int:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("lỗi dọn")
        return 3

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 3:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await store.temp_file_cleanup_loop(interval_seconds=86400, sleep=sleep, cleanup=cleanup)

    assert len(calls) == 3, "chạy ngay + mỗi chu kỳ, lỗi lượt 2 không làm chết vòng"
    assert slept == [86400, 86400, 86400]
