# ported from: src/config/parse-disabled-tools.ts
"""Đọc cột ``disabled_tools`` (JSON array key tool) một cách phòng thủ.

Dùng chung cho CẢ ``accounts`` lẫn ``agents`` - hai bảng cùng lưu danh sách TẮT và cùng giao nhau khi dựng
bộ tool cho một lượt (xem ``list_available`` của registry, D4). Hai bản sao của hàm này là mời gọi drift, mà
drift ở đây nghĩa là một bảng lọc chặt còn bảng kia cho lọt.

Hỏng thì trả mảng RỖNG (= không tắt gì) chứ không ném: cột hỏng không được phép làm chết cả lượt trả lời.

Nói thẳng cái giá của lựa chọn đó: đây là fail-OPEN. Cột ``accounts`` hỏng thì chính lớp chính sách mất tác
dụng, cột ``agents`` hỏng thì lớp năng lực mất - không có chuyện "lớp còn lại đỡ cho", vì hai lớp dùng chung
hàm này. Chấp nhận được vì cột chỉ hỏng khi ai đó sửa DB tay (mọi đường ghi đều đi qua một mảng đã lọc bằng
``TOOL_KEYS`` ở biên API), và vì ``runs_in_scheduled_turn`` cùng ``available()`` vẫn chặn độc lập với cột
này.

Deviation: the column is ``jsonb`` in Postgres, so the driver already hands over a ``list``; a JSON string
is still accepted (the original input type). In ``patient_channel`` the profile's own tool filter
(``PolicyHooks.filter_tool_keys``) runs AFTER this and does not depend on the column, which closes the
fail-open open gap the original describes for that profile."""

from __future__ import annotations

import json


def parse_disabled_tools(raw: object) -> list[str]:
    parsed: object = raw
    if isinstance(raw, str | bytes | bytearray):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(parsed, list):
        return []
    items: list[object] = list(parsed)  # pyright: ignore[reportUnknownArgumentType]
    return [v for v in items if isinstance(v, str)]
