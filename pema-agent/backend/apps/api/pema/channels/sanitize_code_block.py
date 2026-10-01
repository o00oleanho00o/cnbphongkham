# ported from: src/zalo/sanitize-code-block.ts
"""Tách và trả lại KHỐI CODE cho `sanitize_reply_text.py`.

Tách file vì hai lý do, không phải để cho gọn: file kia đã vượt ngưỡng 200 dòng của repo, và phần này là
mối quan tâm riêng - nó KHÔNG dọn định dạng mà làm ngược lại, BẢO VỆ một vùng khỏi mọi bước dọn.

Module THUẦN: 0 import ngoài chuẩn. Forced deviations: JS ``\\s`` is the ECMAScript whitespace set and
``\\d`` is ``[0-9]``; ``replace(/\\s+$/, "")`` (quadratic on a long whitespace run) is ``trimEnd``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pema.channels.utf16_text import js_trim_end

# Ký tự thay chỗ cho khối code trong lúc xử lý.
#
# Dùng ký tự NUL: model không sinh ra nó, và không biểu thức nào trong file này đụng tới. Nhờ vậy nội dung
# bên trong khối code đi qua các bước markdown mà không bị đụng - trước đây `boKhoiCode` gỡ hàng rào NGAY nên
# `# Tính tổng` trong đoạn Python bị `boTieuDe` cắt mất dấu thăng và code trả về sai cú pháp.
MOC_KHOI = "\u0000"


@dataclass(frozen=True)
class KhoiDaTach:
    than: str
    khoi: list[str]


# Nhiều dòng: nhãn ngôn ngữ (```` ```js ````) chỉ hợp lệ khi có xuống dòng NGAY SAU nó. Bắt buộc `\n` là
# vế chữa lỗi nuốt trắng: bản đầu để `[^\n`]*\n?` nên với fence cùng dòng, phần đó ăn luôn cả thân, nhóm
# bắt rỗng, và ``Chạy ```pnpm dev``` là xong`` ra thành `Chạy  là xong`.
#
# Bắt buộc `\n` cũng khử luôn nhánh bậc hai: `[^\n`]*` không vượt được dòng đầu nên không còn đường
# backtrack chồng lên `[\s\S]*?`.
#
# Nhãn ngôn ngữ KHÔNG có `[ \t]*` dẫn đầu, và hai lượng từ còn lại đều kẹp trần. Bản trước viết
# `[ \t]*[A-Za-z0-9+#._-]*[ \t]*` - HAI lượng từ trên cùng lớp `[ \t]` ngăn nhau bởi một lớp có thể rỗng,
# đúng thứ mà luật số 2 ở đầu `sanitize_reply_text.py` cấm. Đo thật `"```" + " ".repeat(n) + "x"`: 20.000
# dấu cách mất 209ms, 80.000 mất 3,3 giây, 200.000 mất **20,5 giây** - đủ treo cả tiến trình. Sau khi vá:
# 200.000 còn 1ms. Nhãn thật (```` ```js ````) không bao giờ có khoảng trắng dẫn nên bỏ vế đó không mất gì.
_NHIEU_DONG_RE = re.compile(r"```[A-Za-z0-9+#._-]{0,32}[ \t]{0,32}\r?\n([\s\S]*?)```")
_CUNG_DONG_RE = re.compile(r"```([^`\n]+)```")
_MOC_RE = re.compile(f"{MOC_KHOI}([0-9]+){MOC_KHOI}")


def tach_khoi_code(text: str, da_sua: list[str]) -> KhoiDaTach:
    """Tách khối code ra khỏi thân, thay bằng mốc.

    Hai dạng, tách hẳn hai biểu thức:

      - Nhiều dòng: nhãn ngôn ngữ chỉ hợp lệ khi có xuống dòng NGAY SAU nó (xem trên).
      - Cùng dòng: giữ nguyên nội dung, chỉ bỏ hàng rào.
    """
    khoi: list[str] = []

    def giu(than: str) -> str:
        khoi.append(than)
        return f"{MOC_KHOI}{len(khoi) - 1}{MOC_KHOI}"

    than = _NHIEU_DONG_RE.sub(lambda m: giu(js_trim_end(m.group(1))), text)
    than = _CUNG_DONG_RE.sub(lambda m: giu(m.group(1)), than)

    if len(khoi) > 0:
        da_sua.append("khối code")
    return KhoiDaTach(than=than, khoi=khoi)


def tra_khoi_code_ve(text: str, khoi: list[str]) -> str:
    """Trả nội dung khối code về đúng chỗ, sau khi mọi bước markdown đã chạy xong."""
    if len(khoi) == 0:
        return text

    def tra(match: re.Match[str]) -> str:
        so = match.group(1)
        # `Number(i)` of an absurdly long digit run is a huge float in JS (never an index); `int` of one
        # would hit Python's digit limit, so anything over 9 digits is "no such block" up front.
        i = int(so) if len(so) <= 9 else len(khoi)
        return khoi[i] if i < len(khoi) else match.group(0)

    return _MOC_RE.sub(tra, text)
