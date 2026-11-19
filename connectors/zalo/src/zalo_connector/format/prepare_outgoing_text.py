# ported from: src/zalo/prepare-outgoing-text.ts
"""Chọn đường làm sạch / dịch định dạng theo cấu hình `ZALO_RICH_TEXT_ENABLED`.

Gom vào một chỗ vì có BA nơi phải chọn cùng một đường (lượt chat, lịch hẹn gửi payload, lịch hẹn gửi câu của
agent). Rải phép kiểm cấu hình ra ba chỗ là mời gọi ca lệch pha: nơi này giữ dấu markdown còn nơi kia đã xóa,
và tin theo lịch hiện nguyên ký tự `**` trong khi tin chat thì không.

Hai bước CỐ Ý tách rời chứ không gộp một hàm: giữa chúng, đường lịch hẹn còn chèn các bước riêng (chặn thì
không gửi, chốt run, đếm trần ngày) và bước dịch phải nằm sát lúc gửi để chữ ghi vào history đúng bằng chữ
người dùng thấy.

Forced deviation: ``getTuning("ZALO_RICH_TEXT_ENABLED")`` is the ``rich_text`` argument (the plugin's
``rich_text`` setting). ``dinh_dang_neu_bat`` returns a ``KetQuaDinhDang`` whose spans are UTF-16 offsets into
its text.
"""

from __future__ import annotations

from .markdown_to_zalo_styles import KetQuaDinhDang, markdown_sang_style_zalo
from .sanitize_reply_text import (
    KetQuaLamSach,
    lam_sach_giu_dinh_dang,
    lam_sach_tra_loi,
)


def lam_sach_theo_cau_hinh(text: str, *, rich_text: bool) -> KetQuaLamSach:
    """Bước 1: lá chắn (rò prompt, `[SILENT]`) - có xóa markdown hay không tùy cấu hình."""
    return lam_sach_giu_dinh_dang(text) if rich_text else lam_sach_tra_loi(text)


def dinh_dang_neu_bat(text: str, *, rich_text: bool) -> KetQuaDinhDang:
    """Bước 2: dịch markdown thành `TextStyle` của Zalo; tắt cấu hình thì trả chữ y nguyên."""
    if not rich_text:
        return KetQuaDinhDang(text=text, styles=[])
    return markdown_sang_style_zalo(text)
