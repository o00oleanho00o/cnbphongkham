# ported from: src/server/overview-stats.ts
"""Số liệu thật cho trang Overview - không có gì là mock.

Placed in ``conversation/`` (PORT-MAP): it only counts rows of ``agent.threads``, ``agent.contacts``,
``agent.memories`` and ``agent.history``. ``UsageStore.get_account_stats`` (contract) serves the other "today"
counters (turns and tokens); this module keeps the original five counts and the system info.

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres (``clinic_id``, no RLS); the five ``SELECT
COUNT(*)`` statements (the original ran them one by one, with the table name interpolated into the SQL) are
ONE statement with five scalar subqueries and fixed table names; ``getSystemInfo`` reported
``process.version`` (Node) and the effective LLM settings. The LLM settings belong to package D1
(``runtime_llm_settings``), so they come in through the ``EffectiveLlm`` protocol; the runtime is the Python
version.

Mốc đầu ngày trước là ``strftime('%Y-%m-%dT00:00:00Z','now')`` nhúng thẳng trong SQL - tức 00:00 UTC = 07:00
sáng giờ VN, lệch cả hai chiều tùy giờ xem. Giờ nhận mốc qua THAM SỐ ràng buộc: caller tự tính bằng
``start_of_day_utc(bot_time_zone())`` (module này thuần, không tự biết timezone).
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import text

from pema.conversation.usage_store import parse_utc_instant
from pema.core.db import ClinicDatabase

_STARTED_AT = time.monotonic()

_COUNTS = text(
    """
    SELECT (SELECT COUNT(*) FROM agent.threads WHERE clinic_id = :clinic_id AND account_id = :account_id) AS
    threads, (SELECT COUNT(*) FROM agent.contacts WHERE clinic_id = :clinic_id AND account_id = :account_id)
    AS contacts, (SELECT COUNT(*) FROM agent.memories WHERE clinic_id = :clinic_id AND account_id =
    :account_id) AS memories, (SELECT COUNT(*) FROM agent.history WHERE clinic_id = :clinic_id AND
    account_id = :account_id) AS messages_total, (SELECT COUNT(*) FROM agent.history WHERE clinic_id =
    :clinic_id AND account_id = :account_id AND created_at >= :since) AS messages_today
    """
)


@dataclass(frozen=True)
class OverviewAccountStats:
    """``AccountStats`` of overview-stats.ts (named differently from the contract's ``AccountStats``)."""

    threads: int
    contacts: int
    memories: int
    messages_total: int
    messages_today: int


class OverviewStats:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_account_stats(
        self, clinic_id: UUID, account_id: str, start_of_today_utc: str
    ) -> OverviewAccountStats:
        """``start_of_today_utc``: mốc UTC ISO của đầu ngày hôm nay theo ``BOT_TIMEZONE`` - tính sẵn ở caller
        (route) rồi truyền xuống."""
        async with self._db.session() as session:
            row = (
                (
                    await session.execute(
                        _COUNTS,
                        {
                            "clinic_id": clinic_id,
                            "account_id": account_id,
                            "since": parse_utc_instant(start_of_today_utc),
                        },
                    )
                )
                .mappings()
                .one()
            )
        return OverviewAccountStats(
            threads=int(row["threads"]),
            contacts=int(row["contacts"]),
            memories=int(row["memories"]),
            messages_total=int(row["messages_total"]),
            messages_today=int(row["messages_today"]),
        )


class EffectiveLlm(Protocol):
    """The part of D1's effective LLM settings this page shows (``getEffectiveLlmSettings``)."""

    @property
    def provider(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def base_url(self) -> str: ...
    @property
    def api_key(self) -> str: ...
    @property
    def has_override(self) -> bool: ...


@dataclass(frozen=True)
class LlmSummary:
    provider: str
    model: str
    has_override: bool
    configured: bool
    """``daCauHinh``: đủ để GỌI ĐƯỢC model chưa (có key + model, và có base URL nếu cần).

    Cần cờ này vì từ khi ``.env`` chỉ còn một biến bắt buộc, bot khởi động BÌNH THƯỜNG khi chưa cấu hình gì -
    dashboard xanh, account online, mà mọi tin nhắn đều nhận câu báo lỗi. Cảnh báo duy nhất trước đây là một
    dòng ``logger.warn`` lúc boot, thứ mà người dùng dashboard không bao giờ đọc.
    """


@dataclass(frozen=True)
class SystemInfoDetail:
    uptime_seconds: int
    python_version: str
    llm: LlmSummary | None


def get_system_info(effective_llm: EffectiveLlm | None = None) -> SystemInfoDetail:
    llm = (
        LlmSummary(
            provider=effective_llm.provider,
            model=effective_llm.model,
            has_override=effective_llm.has_override,
            configured=bool(
                effective_llm.api_key
                and effective_llm.model
                and (effective_llm.provider != "openai-compatible" or effective_llm.base_url)
            ),
        )
        if effective_llm is not None
        else None
    )
    return SystemInfoDetail(
        uptime_seconds=int(time.monotonic() - _STARTED_AT),
        python_version=platform.python_version(),
        llm=llm,
    )
