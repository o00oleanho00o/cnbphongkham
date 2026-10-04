# ported from: src/conversation/usage-store.ts
"""Token accounting per agent turn (table ``agent.usage``, the ``agent_turns`` table of zalo-agent).

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres (``clinic_id`` + RLS, ``timestamptz``). The
contract adds three methods that the original kept elsewhere: ``append_step`` / ``save_turn_trace`` (the trace
of ``agent-trace-store``, which owns the steps table here too) and ``get_account_stats`` (the "today" counters
of the overview page: threads, messages, turns and tokens; the counts of ``overview-stats.ts`` are in
``pema.conversation.overview_stats``).

Kept from the original: ``open_agent_turn`` runs BEFORE the turn so a failed turn keeps an id and its trace;
the daily grouping is done in application code with ``day_key_of`` in the REQUESTED zone, not in SQL by UTC
day (the SQL only bounds the scan with ``created_at >= since``; the 7-day window of the Overview page is a few
dozen rows). Postgres could group by ``AT TIME ZONE``, but a bad ``BOT_TIMEZONE`` must fall back to UTC like
the original (``zone_time`` does), and the same helper keeps both implementations in agreement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from pema.conversation.agent_trace_store import AgentTraceStore
from pema.core.db import ClinicDatabase
from pema.shared.zone_time import day_key_of, to_iso_z
from pema_contracts.agent_turn import StepTrace, TokenUsage, TurnSource
from pema_contracts.conversation import AccountStats, DailyUsage, ThreadUsageTotals

_OPEN = text(
    "INSERT INTO agent.usage (clinic_id, account_id, thread_id, source) "
    "VALUES (:clinic_id, :account_id, :thread_id, :source) RETURNING id"
)

_FINISH = text(
    """
    UPDATE agent.usage SET input_tokens = :input_tokens, output_tokens = :output_tokens, total_tokens =
    :total_tokens, steps = :steps WHERE clinic_id = :clinic_id AND id = :id
    """
)

_THREAD_TOTALS = text(
    """
    SELECT COUNT(*) AS turns, COALESCE(SUM(total_tokens), 0) AS total_tokens
    FROM agent.usage WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
    """
)

_DAILY_SINCE = text(
    """
    SELECT created_at, input_tokens, output_tokens
    FROM agent.usage
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND created_at >= :since
    ORDER BY created_at ASC
    """
)

_ACCOUNT_STATS = text(
    """
    SELECT (SELECT COUNT(*) FROM agent.threads WHERE clinic_id = :clinic_id AND account_id = :account_id) AS
    threads, (SELECT COUNT(*) FROM agent.history WHERE clinic_id = :clinic_id AND account_id = :account_id
    AND created_at >= :since) AS messages_today, (SELECT COUNT(*) FROM agent.usage WHERE clinic_id =
    :clinic_id AND account_id = :account_id AND created_at >= :since) AS turns_today, (SELECT
    COALESCE(SUM(total_tokens), 0) FROM agent.usage WHERE clinic_id = :clinic_id AND account_id =
    :account_id AND created_at >= :since) AS tokens_today
    """
)


def parse_utc_instant(value: str) -> datetime:
    """A UTC instant written as ISO 8601 (``2026-07-30T17:00:00.000Z``) or a bare date (``2000-01-01``, taken
    as 00:00 UTC) -> aware datetime. Naive input is read as UTC, never in the server zone."""
    text_value = value.strip()
    if text_value.endswith(("Z", "z")):
        text_value = text_value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class UsageStoreImpl:
    """``UsageStore`` of ``pema_contracts.conversation`` on ``agent.usage`` (+ trace in ``usage_steps``)."""

    def __init__(self, db: ClinicDatabase, traces: AgentTraceStore | None = None) -> None:
        self._db = db
        self._traces = traces or AgentTraceStore(db)

    async def open_agent_turn(
        self, clinic_id: UUID, account_id: str, thread_id: str, source: TurnSource = TurnSource.MESSAGE
    ) -> int:
        """Mở 1 lượt agent và lấy id NGAY, trước khi lượt chạy.

        Trước đây row chỉ được ghi SAU khi lượt xong, kéo theo hai lỗ:
        - Lượt ném lỗi không có id nên trace của các step đã chạy bị vứt: lượt chạy tốt 5 step rồi step 6 gặp
          500 là mất sạch phần chẩn đoán được.
        - Không có id thì log trong lượt không mang nổi correlation id, hai lượt liên tiếp cùng thread trộn
          vào nhau và chỉ phân biệt được bằng timestamp.

        Cột số đều có DEFAULT 0 nên row mở ra là hợp lệ ngay. Process bị kill giữa lượt để lại row 0 token
        không trace: trang Trace tự lọc (chỉ lượt CÓ step), Overview đếm thừa 1 lượt - chấp nhận được, đổi lấy
        việc lượt hỏng không còn vô hình.

        ``source`` mặc định 'message' để MỌI lời gọi hiện có không phải sửa gì cả - chỉ lượt do job lịch hẹn
        tự bắn mới cần truyền 'schedule'.
        """
        async with self._db.session(clinic_id) as session:
            row_id = (
                await session.execute(
                    _OPEN,
                    {
                        "clinic_id": clinic_id,
                        "account_id": account_id,
                        "thread_id": thread_id,
                        "source": source.value,
                    },
                )
            ).scalar_one()
        return int(row_id)

    async def finish_agent_turn(self, clinic_id: UUID, turn_id: int, usage: TokenUsage) -> None:
        """Chốt usage khi lượt xong - nguồn cho cột Context màn Sessions + thống kê chi phí. Lượt ném lỗi vẫn
        nên gọi (với số đo được tới lúc hỏng) để row không nằm lại ở 0."""
        async with self._db.session(clinic_id) as session:
            await session.execute(
                _FINISH,
                {
                    "clinic_id": clinic_id,
                    "id": turn_id,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "steps": usage.steps,
                },
            )

    async def append_step(self, clinic_id: UUID, turn_id: int, step: StepTrace) -> None:
        await self._traces.save_turn_trace(clinic_id, turn_id, [step])

    async def save_turn_trace(self, clinic_id: UUID, turn_id: int, steps: list[StepTrace]) -> None:
        """``saveTurnTrace``: INSERT of the whole trace of a turn, once per turn (the caller keeps a flag)."""
        await self._traces.save_turn_trace(clinic_id, turn_id, steps)

    async def get_thread_usage_totals(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> ThreadUsageTotals:
        async with self._db.session(clinic_id) as session:
            row = (
                (
                    await session.execute(
                        _THREAD_TOTALS,
                        {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id},
                    )
                )
                .mappings()
                .one()
            )
        return ThreadUsageTotals(turns=int(row["turns"]), total_tokens=int(row["total_tokens"]))

    async def get_account_stats(
        self, clinic_id: UUID, account_id: str, start_of_today_utc: str
    ) -> AccountStats:
        """ "Today" starts at ``start_of_today_utc`` (``start_of_day_utc(bot_time_zone())``): passed in as
        a parameter, never a UTC midnight hard-coded in SQL (that is 07:00 in Vietnam, wrong in both
        directions)."""
        async with self._db.session(clinic_id) as session:
            row = (
                (
                    await session.execute(
                        _ACCOUNT_STATS,
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
        return AccountStats(
            account_id=account_id,
            threads=int(row["threads"]),
            messages_today=int(row["messages_today"]),
            turns_today=int(row["turns_today"]),
            tokens_today=int(row["tokens_today"]),
        )

    async def get_daily_usage(
        self, clinic_id: UUID, account_id: str, since_utc_iso: str, time_zone: str
    ) -> list[DailyUsage]:
        """Thống kê theo ngày (theo ``time_zone``, không phải UTC) từ mốc ``since_utc_iso`` - cho trang
        Overview. ``since_utc_iso`` nên tính bằng ``start_of_day_utc`` lùi N ngày để không lọt mất giờ đầu
        ngày VN."""
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        _DAILY_SINCE,
                        {
                            "clinic_id": clinic_id,
                            "account_id": account_id,
                            "since": parse_utc_instant(since_utc_iso),
                        },
                    )
                )
                .mappings()
                .all()
            )

        by_day: dict[str, list[int]] = {}
        for r in rows:
            day = day_key_of(to_iso_z(r["created_at"]), time_zone)
            agg = by_day.setdefault(day, [0, 0, 0])
            agg[0] += 1
            agg[1] += int(r["input_tokens"])
            agg[2] += int(r["output_tokens"])

        # Giữ nguyên thứ tự DESC (mới nhất trước) như hành vi cũ của câu SQL.
        return [
            DailyUsage(day=day, turns=agg[0], input_tokens=agg[1], output_tokens=agg[2])
            for day, agg in sorted(by_day.items(), key=lambda item: item[0], reverse=True)
        ]
