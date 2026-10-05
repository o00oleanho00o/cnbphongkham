# ported from: src/shared/read-log-file.test.ts
"""Pure module: it takes the directory, touches no environment, so the test runs it directly.

Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring. Forced
difference: the files are named like ``TimedRotatingFileHandler`` names them (``bot.log`` current,
``bot.log.<day>`` rotated) and the lines are the ones of ``pema.shared.logger`` (ISO ``time``, level NAME); the
parser maps them to the pino shape the assertions use.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pema.shared.read_log_file import ReadLogsOptions, read_recent_logs

NOW_MS = 1_785_000_000_000


def dong(level: str, scope: str, msg: str, time_ms: int = NOW_MS, **fields: object) -> str:
    """The logger writes one JSON per line; ``time`` is ISO 8601 and ``level`` the lowercase NAME."""
    stamp = datetime.fromtimestamp(time_ms / 1000, UTC).isoformat(timespec="milliseconds")
    return json.dumps(
        {"time": stamp, "level": level, "scope": scope, "msg": msg, **fields}, ensure_ascii=False
    )


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    # Two files as the daily rotation leaves them: the rotated day and the current one
    (tmp_path / "bot.log.2026-07-27").write_text(
        "\n".join(
            [dong("info", "cu", "hôm qua", NOW_MS - 2000), dong("error", "cu", "lỗi hôm qua", NOW_MS - 1000)]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "bot.log").write_text(
        "\n".join(
            [
                dong("debug", "agent-loop", "chi tiết step", NOW_MS + 1000),
                dong("info", "message-turn", "xử lý lượt", NOW_MS + 2000),
                dong("warning", "vision-sidecar", "sidecar chậm", NOW_MS + 3000),
                dong("error", "account-manager", "mất kết nối", NOW_MS + 4000),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_read_recent_logs_doc_duoc_moi_file_trong_thu_muc_moi_nhat_dung_dau(log_dir: Path) -> None:
    """đọc được mọi file trong thư mục, MỚI NHẤT ĐỨNG ĐẦU"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100))
    assert len(r.entries) == 6
    assert r.entries[0].msg == "mất kết nối", "dòng cuối của file mới nhất phải đứng đầu"


def test_read_recent_logs_loc_theo_muc_chi_lay_tu_muc_do_tro_len(log_dir: Path) -> None:
    """lọc theo mức: chỉ lấy từ mức đó trở lên"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100, min_level=40))
    assert sorted(e.msg for e in r.entries) == sorted(["lỗi hôm qua", "mất kết nối", "sidecar chậm"])


def test_read_recent_logs_loc_theo_scope(log_dir: Path) -> None:
    """lọc theo scope"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100, scope="agent-loop"))
    assert len(r.entries) == 1
    assert r.entries[0].msg == "chi tiết step"


def test_read_recent_logs_tim_theo_chu_trong_noi_dung_dong_log(log_dir: Path) -> None:
    """tìm theo chữ trong nội dung dòng log"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100, search="sidecar"))
    assert len(r.entries) == 1
    assert r.entries[0].scope == "vision-sidecar"


def test_read_recent_logs_limit_cat_bot_nhung_van_giu_dong_moi_nhat(log_dir: Path) -> None:
    """limit cắt bớt nhưng vẫn giữ dòng MỚI NHẤT"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=2))
    assert len(r.entries) == 2
    assert r.entries[0].msg == "mất kết nối"


def test_read_recent_logs_liet_ke_cac_scope_dang_co_de_dashboard_dung_o_loc(log_dir: Path) -> None:
    """liệt kê các scope đang có - để dashboard dựng ô lọc"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100))
    assert "agent-loop" in r.scopes
    assert "account-manager" in r.scopes
    assert r.scopes == sorted(r.scopes), "scope phải sắp xếp cho dễ nhìn"


def test_read_recent_logs_giu_nguyen_cac_truong_phu_de_doc_ngu_canh(log_dir: Path) -> None:
    """giữ nguyên các trường phụ để đọc ngữ cảnh"""
    (log_dir / "bot.log.2026-07-29").write_text(
        dong("info", "x", "m", NOW_MS, thread_id="t-9", steps=3) + "\n", encoding="utf-8"
    )
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=10, scope="x"))
    assert r.entries[0].fields["thread_id"] == "t-9"
    assert r.entries[0].fields["steps"] == 3


# ------------------------------------------------------------------ read enough, do not swallow a week of log


def test_read_recent_logs_chi_doc_du_dung_du_dong_o_file_moi_nhat_thi_dung_khong_mo_file_cu(
    log_dir: Path,
) -> None:
    """đủ dòng ở file mới nhất thì DỪNG, không mở file cũ"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=1))
    assert len(r.entries) == 1
    assert r.files_read == 1, "mở cả file cũ là đọc thừa cả tuần log mỗi lần vào trang"


def test_read_recent_logs_chi_doc_du_dung_thieu_dong_thi_moi_lan_nguoc_sang_file_cu_hon(
    log_dir: Path,
) -> None:
    """thiếu dòng thì mới lần ngược sang file cũ hơn"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100))
    assert r.files_read == 2
    assert len(r.entries) == 6


def test_read_recent_logs_chi_doc_du_dung_loc_chat_khong_khop_gi_o_file_moi_van_lan_nguoc_tim_tiep(
    log_dir: Path,
) -> None:
    """lọc chặt (không khớp gì ở file mới) vẫn lần ngược tìm tiếp"""
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=10, scope="cu"))
    assert len(r.entries) == 2, "phải tìm được ở file cũ"
    assert r.files_read == 2


# ----------------------------------------------------------------- a failure must not kill the page


def test_read_recent_logs_hong_hoc_thu_muc_chua_ton_tai_tra_rong_khong_throw(log_dir: Path) -> None:
    """thư mục chưa tồn tại trả rỗng, không throw"""
    r = read_recent_logs(log_dir / "khong-co", ReadLogsOptions(limit=10))
    assert r.entries == []
    assert r.scopes == []


def test_read_recent_logs_hong_hoc_dong_json_hong_bi_bo_qua_cac_dong_khac_van_doc_duoc(log_dir: Path) -> None:
    """dòng JSON hỏng bị bỏ qua, các dòng khác vẫn đọc được"""
    (log_dir / "bot.log.2026-07-30").write_text(
        f"khong-phai-json\n{dong('info', 'ok', 'van doc duoc')}\n", encoding="utf-8"
    )
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100, scope="ok"))
    assert len(r.entries) == 1


def test_read_recent_logs_hong_hoc_bo_qua_file_khong_phai_log(log_dir: Path) -> None:
    """bỏ qua file không phải .log"""
    (log_dir / "ghi-chu.txt").write_text(dong("info", "khong-nen-doc", "x") + "\n", encoding="utf-8")
    r = read_recent_logs(log_dir, ReadLogsOptions(limit=100))
    assert "khong-nen-doc" not in r.scopes


def test_read_recent_logs_pino_shape_numeric_level_and_epoch_time_are_read_too(tmp_path: Path) -> None:
    """dòng kiểu pino (level số, time epoch ms) vẫn đọc được - log cũ của bản gốc"""
    (tmp_path / "bot.2026-07-28.1.log").write_text(
        json.dumps({"level": 50, "time": NOW_MS, "scope": "old", "msg": "pino"}) + "\n", encoding="utf-8"
    )
    r = read_recent_logs(tmp_path, ReadLogsOptions(limit=10))
    assert [(e.level, e.time) for e in r.entries] == [(50, NOW_MS)]
