# ported from: src/shared/read-log-file-paging.test.ts
"""Pagination of the Logs page. Split from ``test_read_log_file`` because this set needs its own data: many
lines in the SAME millisecond, exactly what broke a cursor carrying only the timestamp.

The rule to keep in every test below: paging through every page gives EXACTLY the list read in one go, with
nothing lost and nothing repeated. Test names are the snake_case form of ``describe_it``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pema.shared.log_cursor import ConTroLog, doc_con_tro
from pema.shared.read_log_file import ReadLogsOptions, read_recent_logs

BASE_MS = 1_700_000_000_000


def dong(time_ms: int, msg: str, level: str = "info", scope: str = "test") -> str:
    stamp = datetime.fromtimestamp(time_ms / 1000, UTC).isoformat(timespec="milliseconds")
    return json.dumps({"time": stamp, "level": level, "scope": scope, "msg": msg})


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    # 20 lines, the timestamps DELIBERATELY equal in clusters of 4: like the bot firing a whole cluster of log
    # in one millisecond when it is busy.
    lines = [dong(BASE_MS + i // 4, f"dong-{i}") for i in range(20)]
    (tmp_path / "bot.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def lat_het_trang(directory: Path, limit: int, search: str | None = None) -> list[str]:
    """Page through with the cursor, returning the msg list in the order read."""
    out: list[str] = []
    cursor: str | None = None
    for _round in range(50):
        r = read_recent_logs(
            directory,
            ReadLogsOptions(limit=limit, search=search, before=doc_con_tro(cursor) if cursor else None),
        )
        out.extend(e.msg for e in r.entries)
        if r.next_cursor is None:
            return out
        cursor = r.next_cursor
    raise AssertionError("lật quá 50 trang - con trỏ không tiến")


def test_phan_trang_log_doc_mot_lan_moi_nhat_truoc(log_dir: Path) -> None:
    """đọc một lần: mới nhất trước"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100))
    assert len(r.entries) == 20
    assert r.entries[0].msg == "dong-19"
    assert r.entries[19].msg == "dong-0"
    assert r.next_cursor is None, "hết log thì nextCursor phải null"


def test_phan_trang_log_lat_tung_trang_ra_dung_danh_sach_doc_mot_lan_khong_sot_khong_lap(
    log_dir: Path,
) -> None:
    """lật từng trang ra ĐÚNG danh sách đọc một lần - không sót, không lặp"""
    mot_lan = [e.msg for e in read_recent_logs(log_dir, ReadLogsOptions(limit=100)).entries]
    # Several page sizes, among them sizes that CUT ACROSS the same-millisecond cluster (cluster of 4)
    for limit in (1, 2, 3, 5, 7, 19, 20):
        assert lat_het_trang(log_dir, limit) == mot_lan, f"cỡ trang {limit}"


def test_phan_trang_log_co_trang_3_cat_ngang_cum_4_dong_cung_mili_giay_ma_van_dung(log_dir: Path) -> None:
    """cỡ trang 3 cắt ngang cụm 4 dòng cùng mili giây mà vẫn đúng

    The case that broke the version carrying only the timestamp: ``<`` loses lines, ``<=`` repeats them. Size 3
    guarantees the boundary falls in the middle of a cluster.
    """
    ra = lat_het_trang(log_dir, 3)
    assert len(ra) == 20
    assert len(set(ra)) == 20, "có dòng bị lặp"


def test_phan_trang_log_next_cursor_null_o_trang_cuoi_khac_null_khi_con_dong(log_dir: Path) -> None:
    """nextCursor null ở trang cuối, khác null khi còn dòng"""
    t1 = read_recent_logs(log_dir, ReadLogsOptions(limit=5))
    assert t1.next_cursor, "còn 15 dòng mà báo hết"
    t4 = read_recent_logs(log_dir, ReadLogsOptions(limit=20))
    assert t4.next_cursor is None


def test_phan_trang_log_con_tro_di_cung_bo_loc_lat_trang_trong_tap_da_loc_van_du(log_dir: Path) -> None:
    """con trỏ đi cùng BỘ LỌC: lật trang trong tập đã lọc vẫn đủ"""
    # matches dong-1 and dong-10..19 = 11 lines
    mot_lan = [e.msg for e in read_recent_logs(log_dir, ReadLogsOptions(limit=100, search="dong-1")).entries]
    assert len(mot_lan) == 11
    for limit in (1, 2, 4, 11):
        assert lat_het_trang(log_dir, limit, "dong-1") == mot_lan, f"cỡ trang {limit}"


@pytest.mark.parametrize("rac", ["", "abc", "12", ".5", "1700000000000.", "-1.0", "1.5.9", "1e3.0"])
def test_phan_trang_log_con_tro_hong_doc_con_tro_tra_none_khong_roi_ve_trang_dau(rac: str) -> None:
    """con trỏ hỏng -> docConTro trả null, KHÔNG rơi về trang đầu

    Hermes' rule (``list_sessions``): an unknown cursor must give an empty page and not the first page, or the
    client keeps appending copies for ever.
    """
    assert doc_con_tro(rac) is None, f'"{rac}" phải bị từ chối'


def test_phan_trang_log_con_tro_hop_le_duoc_doc() -> None:
    """con trỏ đúng dạng được đọc"""
    assert doc_con_tro("1700000000000.3") == ConTroLog(time=1_700_000_000_000, da_lay=3)


def test_phan_trang_log_thu_muc_log_khong_ton_tai_thi_tra_rong_kem_next_cursor_none(tmp_path: Path) -> None:
    """thư mục log không tồn tại thì trả rỗng kèm nextCursor null"""
    r = read_recent_logs(tmp_path / "khong-co", ReadLogsOptions(limit=10))
    assert r.entries == []
    assert r.next_cursor is None
