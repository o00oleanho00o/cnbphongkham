# ported from: src/knowledge/kb-file-store.test.ts
"""``kb_file_store`` does not depend on the database; the data directory is a ``tmp_path``."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pema.knowledge import kb_file_store as file_store


def test_kb_file_store_saves_by_the_generated_id_never_the_name_the_user_picked(tmp_path: Path) -> None:
    """lưu theo id sinh ra, KHÔNG dùng tên người dùng đặt làm đường dẫn"""
    p = file_store.luu_file("src-1", "pdf", b"%PDF-x", data_dir=tmp_path)
    assert re.fullmatch(r"kb/src-1\.pdf", p)
    assert (tmp_path / p).read_bytes() == b"%PDF-x"


def test_kb_file_store_a_traversal_style_name_creates_no_file_outside_the_data_dir(tmp_path: Path) -> None:
    """tên file kiểu vượt thư mục không tạo được file ngoài dataDir"""
    p = file_store.luu_file("../../../etc/passwd", "txt", b"x", data_dir=tmp_path)
    assert ".." not in p, f"đường dẫn thoát ra: {p}"
    # The file must sit EXACTLY under <data_dir>/kb, not leak out
    tuyet_doi = (tmp_path / p).resolve()
    assert (tmp_path / "kb").resolve() in tuyet_doi.parents


def test_kb_file_store_deleting_the_source_deletes_the_file_on_disk(tmp_path: Path) -> None:
    """xóa nguồn thì file trên đĩa cũng mất"""
    p = file_store.luu_file("src-2", "txt", b"x", data_dir=tmp_path)
    assert (tmp_path / p).exists(), "chưa xóa mà file đã không có thì test vô nghĩa"
    file_store.xoa_file(p, data_dir=tmp_path)
    assert not (tmp_path / p).exists()


def test_kb_file_store_deleting_a_missing_file_does_not_raise_idempotent(tmp_path: Path) -> None:
    """xóa file không tồn tại không ném lỗi (idempotent)"""
    file_store.xoa_file("kb/khong-ton-tai.txt", data_dir=tmp_path)


def test_kb_file_store_deleting_an_empty_path_does_nothing(tmp_path: Path) -> None:
    """xóa đường dẫn rỗng (nguồn gõ tay, chưa từng ghi file) không làm gì"""
    file_store.xoa_file("", data_dir=tmp_path)


def test_kb_file_store_read_refuses_a_path_that_escapes_the_kb_folder(tmp_path: Path) -> None:
    """(thêm) đọc/xóa không đi ra ngoài thư mục kb"""
    (tmp_path / "bi-mat.txt").write_bytes(b"x")
    with pytest.raises(ValueError, match="ngoài thư mục"):
        file_store.doc_file("kb/../bi-mat.txt", data_dir=tmp_path)
    file_store.xoa_file("kb/../bi-mat.txt", data_dir=tmp_path)
    assert (tmp_path / "bi-mat.txt").exists()
    p = file_store.luu_file("ok", "txt", b"abc", data_dir=tmp_path)
    assert file_store.doc_file(p, data_dir=tmp_path) == b"abc"
