# ported from: src/zalo/zalo-image-variant.ts
"""Chọn CỠ ảnh trong payload Zalo trước khi đưa vào context model.

Zalo gửi kèm nhiều biến thể của cùng một ảnh (hd / href / oriUrl / normalUrl / thumb). Trước đây code lấy
``hd``
đầu tiên, tức bản to nhất: ảnh vé số thật đo được 977x2128 px, tốn ~2500 token MỖI LẦN vào context. Một lượt
agent 5 step x 4 ảnh (1 ảnh mới + 3 ảnh nạp lại từ history) = 20 lượt ảnh, chiếm ~80% hoá đơn token của
lượt đó.

Zalo đã resize sẵn ở phía họ nên chỉ cần đổi thứ tự ưu tiên - không cần thư viện resize.

Module thuần, không import env - caller truyền quality vào để test dễ.

Forced deviation: Node ``Buffer.readUInt32BE`` becomes ``struct``/``int.from_bytes`` (no dependency).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

type ImageQuality = Literal["thumb", "normal", "hd"]

# Các key ảnh trong content của tin nhắn Zalo, xếp từ nhỏ tới lớn
type VariantKey = Literal["thumb", "normalUrl", "href", "oriUrl", "hd"]

# Thứ tự thử theo từng mức chất lượng. Luôn có đủ đường lui tới hết danh sách vì payload Zalo không phải
# lúc nào
# cũng có đủ mọi biến thể.
#
# - normal (mặc định): đủ nét để đọc chữ số trên vé/hoá đơn, rẻ hơn hd nhiều
# - hd: giữ hành vi cũ, chỉ nên bật khi cần đọc chi tiết rất nhỏ
# - thumb: rẻ nhất nhưng thường mất chữ số - chỉ hợp khi chỉ cần "ảnh này là gì"
PREFERENCE: dict[str, tuple[VariantKey, ...]] = {
    "thumb": ("thumb", "normalUrl", "href", "oriUrl", "hd"),
    "normal": ("normalUrl", "href", "oriUrl", "hd", "thumb"),
    "hd": ("hd", "oriUrl", "href", "normalUrl", "thumb"),
}


@dataclass(frozen=True)
class PickedImage:
    url: str
    variant: VariantKey


def pick_image_variant(content: Mapping[str, object], quality: str) -> PickedImage | None:
    """Chọn URL ảnh theo mức chất lượng mong muốn. Trả ``None`` nếu content không có biến thể nào dùng
    được."""
    for key in PREFERENCE.get(quality, PREFERENCE["normal"]):
        value = content.get(key)
        if isinstance(value, str) and value.strip().startswith("http"):
            return PickedImage(url=value.strip(), variant=key)
    return None


def estimate_image_tokens(width: int, height: int) -> int:
    """Ước lượng token của 1 ảnh theo kích thước pixel. Công thức (w*h)/750 của Anthropic - các họ model khác
    tính theo ô 512px nhưng cùng bậc độ lớn, đủ để log ra và so sánh trước/sau khi đổi cỡ ảnh."""
    if width <= 0 or height <= 0:
        return 0
    # JS Math.round rounds half up; Python round() is banker's rounding.
    return int((width * height) / 750 + 0.5)


def read_image_size(data: bytes) -> tuple[int, int] | None:
    """Đọc kích thước JPEG/PNG từ vài byte đầu - chỉ để log, không giải mã ảnh. Trả ``(width, height)``.
    Không nhận dạng được thì trả ``None`` (log bỏ qua, không làm chết lượt)."""
    # PNG: signature 8 byte, IHDR width/height là 2 số 32-bit big-endian
    if len(data) > 24 and int.from_bytes(data[0:4], "big") == 0x89504E47:
        return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))

    # JPEG: quét tới marker SOF (0xC0-0xCF, trừ DHT/JPG/DAC) để lấy kích thước
    if len(data) > 4 and data[0] == 0xFF and data[1] == 0xD8:
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height = int.from_bytes(data[offset + 5 : offset + 7], "big")
                width = int.from_bytes(data[offset + 7 : offset + 9], "big")
                return (width, height)
            segment_length = int.from_bytes(data[offset + 2 : offset + 4], "big")
            if segment_length < 2:
                return None  # segment hỏng - dừng thay vì lặp vô hạn
            offset += 2 + segment_length

    return None
