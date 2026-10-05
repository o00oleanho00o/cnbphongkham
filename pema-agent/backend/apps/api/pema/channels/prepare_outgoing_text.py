# ported from: src/zalo/prepare-outgoing-text.ts
"""Chọn đường làm sạch / dịch định dạng theo cấu hình `ZALO_RICH_TEXT_ENABLED`.

Gom vào một chỗ vì có BA nơi phải chọn cùng một đường (lượt chat, lịch hẹn gửi payload, lịch hẹn gửi câu của
agent). Rải phép kiểm cấu hình ra ba chỗ là mời gọi ca lệch pha: nơi này giữ dấu markdown còn nơi kia đã xóa,
và tin theo lịch hiện nguyên ký tự `**` trong khi tin chat thì không.

Hai bước CỐ Ý tách rời chứ không gộp một hàm: giữa chúng, đường lịch hẹn còn chèn các bước riêng (chặn thì
không gửi, chốt run, đếm trần ngày) và bước dịch phải nằm sát lúc gửi để chữ ghi vào history đúng bằng chữ
người dùng thấy.

Forced deviation: ``getTuning`` is ``pema.config.runtime_tuning_settings.get_tuning`` (the tuning provider
replaces the SQLite-backed settings); the original has no test file, this port adds
``tests/channels/test_prepare_outgoing_text.py``. ``dinh_dang_neu_bat`` returns a ``KetQuaDinhDang`` whose
spans are UTF-16 offsets into its text.
"""

from __future__ import annotations

from pema.channels.markdown_to_zalo_styles import KetQuaDinhDang, markdown_sang_style_zalo
from pema.channels.sanitize_reply_text import (
    KetQuaLamSach,
    lam_sach_giu_dinh_dang,
    lam_sach_tra_loi,
)
from pema.config.runtime_tuning_settings import get_tuning


def lam_sach_theo_cau_hinh(text: str) -> KetQuaLamSach:
    """Bước 1: lá chắn (rò prompt, `[SILENT]`) - có xóa markdown hay không tùy cấu hình."""
    return lam_sach_giu_dinh_dang(text) if get_tuning("ZALO_RICH_TEXT_ENABLED") else lam_sach_tra_loi(text)


def dinh_dang_neu_bat(text: str) -> KetQuaDinhDang:
    """Bước 2: dịch markdown thành `TextStyle` của Zalo; tắt cấu hình thì trả chữ y nguyên."""
    if not get_tuning("ZALO_RICH_TEXT_ENABLED"):
        return KetQuaDinhDang(text=text, styles=[])
    return markdown_sang_style_zalo(text)
