# ported from: src/images/image-rate-limit.ts
"""Trần số ảnh mỗi thread được vẽ trong 1 giờ.

Chặt hơn tool tạo file vì khác hẳn về giá: dựng .docx chỉ tốn CPU của chính
mình, còn mỗi lần vẽ ảnh là một lần TRẢ TIỀN cho provider và chiếm ~70 giây.
Bot đọc tin người lạ nên đây là hàng phòng thủ chính chống đốt quota.

No forced deviation: ``createHourlyRateLimit`` is ``pema.shared.hourly_rate_limit.create_hourly_rate_limit``;
the ceiling is read from the tuning provider on every call, as in the original.
"""

from __future__ import annotations

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.hourly_rate_limit import RateReasonInfo, create_hourly_rate_limit


def _build_reason(info: RateReasonInfo) -> str:
    return (
        f"Đã vẽ {info.used} ảnh trong 1 giờ qua (trần {info.limit}). "
        f"Thử lại sau khoảng {info.wait_minutes} phút. "
        "Trong lúc chờ vẫn có thể mô tả bằng lời cho người dùng hình dung."
    )


_limiter = create_hourly_rate_limit(
    limit=lambda: get_tuning_int("IMAGE_GEN_MAX_PER_HOUR"),
    build_reason=_build_reason,
)

check_image_rate_limit = _limiter.check

reset_image_rate_limit = _limiter.reset
"""Chỉ dùng cho test - xóa toàn bộ trạng thái đếm"""
