# ported from: src/video/video-rate-limit.ts
"""Ceiling on how many videos EACH PERSON may download in 1 hour.

Counted per thread, not for the whole bot: one person spamming links blocks only that person, other
conversations keep working. Same counting as the file-building tool and the image-drawing tool
(``create_hourly_rate_limit``).

WHY IT IS NEEDED, besides resource cost: sending videos in bulk from a PERSONAL Zalo account is a very clear
spam signal, and the biggest risk of this feature is not an overloaded VPS but LOSING THE ACCOUNT. The ceiling
here reduces that risk, it is not to save bandwidth: bandwidth measured is not the bottleneck anyway.

No forced deviation: the module-level limiter is a process-local counter exactly as in the original; the
exports keep their names in snake_case (``checkVideoRateLimit`` -> ``check_video_rate_limit`` ...).
"""

from __future__ import annotations

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.hourly_rate_limit import RateCheck, RateReasonInfo, create_hourly_rate_limit

__all__ = ["RateCheck", "check_video_rate_limit", "hoan_suat_video", "reset_video_rate_limit"]


def _build_reason(info: RateReasonInfo) -> str:
    return (
        f"Đã tải {info.used} video trong 1 giờ qua (trần {info.limit}). "
        f"Thử lại sau khoảng {info.wait_minutes} phút."
    )


_limiter = create_hourly_rate_limit(
    limit=lambda: get_tuning_int("VIDEO_MAX_PER_HOUR"), build_reason=_build_reason
)

check_video_rate_limit = _limiter.check

hoan_suat_video = _limiter.hoan_suat
"""Give the slot back when the video was NOT sent.

This ceiling counts videos ALREADY SENT, not attempts. If the source is down and the slot is still charged,
the user is locked out for an hour over attempts that got them nothing."""

reset_video_rate_limit = _limiter.reset
"""Tests only: clear the whole counting state."""
