# ported from: src/agent/tool-call-signature.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, needs no env.

The focus of this file is the INVARIANT "must not throw". The function runs in ``onStepFinish`` and the
``notify()`` of ai@7.0.37 calls the callback in an EMPTY ``catch {}``: a throw does not turn red anywhere,
it silently switches off the guard and the trace from that step on. So every case below is checked with an
explicit "does not raise", not by eye.

Deviation of the translation: the JS ``bigint`` case uses very large Python ints (no separate type), and
``Map``/``Set`` become Python ``dict``/``set``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from pema.agent.tool_call_signature import bam_ngan, chu_ky_lenh_goi, chuan_hoa_json

# --- chuanHoaJson - không được ném với đầu vào lạ ------------------------------------------------------


def test_chuan_hoa_json_khong_duoc_nem_voi_dau_vao_la_bigint_phai_tu_xu_ly() -> None:
    """bigint: JSON.stringify ném TypeError thẳng, phải tự xử"""
    chuan_hoa_json({"so_lon": 10**30})
    assert chuan_hoa_json({"n": 10**30 + 1}) != chuan_hoa_json({"n": 10**30 + 2}), (
        "hai bigint khác phải khác chữ ký"
    )


def test_chuan_hoa_json_khong_duoc_nem_voi_dau_vao_la_tham_chieu_vong_de_quy_khong_day_se_tran_stack() -> (
    None
):
    """tham chiếu vòng: đệ quy không đáy sẽ tràn stack"""
    a: dict[str, Any] = {"ten": "a"}
    a["chin_no"] = a
    chuan_hoa_json(a)

    x: dict[str, Any] = {}
    y: dict[str, Any] = {"x": x}
    x["y"] = y
    chuan_hoa_json(x)


def test_chuan_hoa_json_khong_duoc_nem_voi_dau_vao_la_mang_long_vong_cung_khong_tran() -> None:
    """mảng lồng vòng cũng không tràn"""
    m: list[Any] = [1, 2]
    m.append(m)
    chuan_hoa_json(m)


@pytest.mark.parametrize(
    "v",
    [lambda: 1, object(), None, float("nan"), float("inf"), -0.0],
    ids=["function", "object", "undefined", "nan", "infinity", "minus-zero"],
)
def test_chuan_hoa_json_khong_duoc_nem_voi_dau_vao_la_ham_symbol_undefined_nan_infinity(v: object) -> None:
    """hàm, symbol, undefined, NaN, Infinity, -0"""
    chuan_hoa_json({"v": v})


# --- chuanHoaJson - object KHÔNG THUẦN không được đụng chữ ký nhau -------------------------------------


def test_chuan_hoa_json_object_khong_thuan_hai_date_khac_nhau_cho_hai_chu_ky_khac_nhau() -> None:
    """hai Date khác nhau cho hai chữ ký khác nhau

    ``Object.entries(new Date())`` returns an EMPTY array, so the first version hashed every Date to the
    string "{}": two completely different calls counted as the same and the guard blocked wrongly. A Date
    goes through ``toJSON`` so it keeps its timestamp.
    """
    a = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
    b = datetime(2026, 8, 2, 11, 0, tzinfo=UTC)
    assert chuan_hoa_json({"khi": a}) != chuan_hoa_json({"khi": b})
    assert chu_ky_lenh_goi("t", {"khi": a}) != chu_ky_lenh_goi("t", {"khi": b})


def test_chuan_hoa_json_object_khong_thuan_cung_mot_moc_thoi_gian_thi_van_ra_cung_chu_ky() -> None:
    """cùng một mốc thời gian thì vẫn ra cùng chữ ký"""
    assert chuan_hoa_json({"khi": datetime(2026, 8, 2, 10, 0, tzinfo=UTC)}) == chuan_hoa_json(
        {"khi": datetime(2026, 8, 2, 10, 0, tzinfo=UTC)}
    )


def test_chuan_hoa_json_object_khong_thuan_date_khong_bi_lan_voi_object_rong() -> None:
    """Date KHÔNG bị lẫn với object rỗng"""
    assert chuan_hoa_json(datetime(2026, 8, 2, 10, 0, tzinfo=UTC)) != chuan_hoa_json({})


def test_chuan_hoa_json_object_khong_thuan_map_set_khong_nem_du_khong_phan_biet_duoc_noi_dung() -> None:
    """Map/Set không ném (dù không phân biệt được nội dung)"""
    chuan_hoa_json({"m": {"a": 1}, "s": {1}})


def test_chuan_hoa_json_object_khong_thuan_object_tao_bang_object_create_null_van_doc_duoc_khoa() -> None:
    """object tạo bằng Object.create(null) vẫn đọc được khóa"""
    o: dict[str, Any] = {}
    o["b"] = 2
    o["a"] = 1
    assert chuan_hoa_json(o) == '{"a":1,"b":2}'


# --- chuanHoaJson - hành vi chuẩn hóa vẫn giữ nguyên ---------------------------------------------------


def test_chuan_hoa_json_hanh_vi_chuan_hoa_sap_khoa_o_moi_cap() -> None:
    """sắp khóa ở mọi cấp"""
    assert chuan_hoa_json({"b": 1, "a": {"d": 4, "c": 3}}) == '{"a":{"c":3,"d":4},"b":1}'


def test_chuan_hoa_json_hanh_vi_chuan_hoa_mang_giu_nguyen_thu_tu_1_2_khac_2_1() -> None:
    """mảng giữ nguyên THỨ TỰ - [1,2] khác [2,1]"""
    assert chuan_hoa_json([1, 2]) != chuan_hoa_json([2, 1])


def test_chuan_hoa_json_hanh_vi_chuan_hoa_cung_object_xuat_hien_hai_lan_o_hai_nhanh_song_song_la_hop_le() -> (
    None
):
    """cùng object xuất hiện hai lần ở hai nhánh SONG SONG là hợp lệ, không phải vòng"""
    dung = {"a": 1}
    assert chuan_hoa_json({"x": dung, "y": dung}) == '{"x":{"a":1},"y":{"a":1}}'


# --- bamNgan -------------------------------------------------------------------------------------------


def test_bam_ngan_16_ky_tu_hex_on_dinh_giua_cac_lan_goi() -> None:
    """16 ký tự hex, ổn định giữa các lần gọi"""
    h = bam_ngan("abc")
    assert len(h) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", h)
    assert h == bam_ngan("abc")
    assert h != bam_ngan("abd")
