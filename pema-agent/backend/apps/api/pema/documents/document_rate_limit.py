# ported from: src/documents/document-rate-limit.ts
"""Ceiling on how many files each thread may create in 1 hour. The bot reads messages from strangers, and
building a file is the most CPU-hungry thing in an agent turn - without a ceiling one person spamming
"export a file" pins the whole process.

The counting + memory clean-up lives in ``pema.shared.hourly_rate_limit`` (shared with the image tool); only
the ceiling and the file tool's own sentence stay here.

No forced deviation: ``checkDocumentRateLimit`` / ``resetDocumentRateLimit`` were the bound methods of the
module-level limiter; they stay module-level functions over one module-level ``HourlyRateLimit``. The state is
per process, as in the original. ``now`` is epoch MILLISECONDS like ``Date.now()``.
"""

from __future__ import annotations

from typing import Final

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.hourly_rate_limit import (
    HourlyRateLimit,
    RateCheck,
    RateReasonInfo,
    create_hourly_rate_limit,
)

__all__ = ["RateCheck", "check_document_rate_limit", "reset_document_rate_limit"]


def _build_reason(info: RateReasonInfo) -> str:
    return (
        f"Đã tạo {info.used} file trong 1 giờ qua (trần {info.limit}). "
        f"Thử lại sau khoảng {info.wait_minutes} phút, hoặc trả lời trực tiếp trong chat thay vì gửi file."
    )


_limiter: Final[HourlyRateLimit] = create_hourly_rate_limit(
    limit=lambda: get_tuning_int("DOCUMENT_MAX_PER_HOUR"),
    build_reason=_build_reason,
)


def check_document_rate_limit(key: str, now: float | None = None) -> RateCheck:
    """If a slot is left, RECORD this use and return ok. ``key`` is usually ``account_id:thread_id``."""
    return _limiter.check(key, now)


def reset_document_rate_limit() -> None:
    """Tests only: clear the whole counting state."""
    _limiter.reset()
