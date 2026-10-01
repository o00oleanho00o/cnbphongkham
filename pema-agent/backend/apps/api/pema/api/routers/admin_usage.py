# ported from: src/server/routes/overview-routes.ts, trace-routes.ts, log-routes.ts
"""Overview, token usage, agent traces and application logs (package D1).

Traces and ``history`` may contain message text: ``admin.usage`` is a staff-only permission (checked by the
router that mounts this one). Traces are read-only evidence (no edit, no delete; retention is a periodic job).
Paging is by cursor, never offset: these lists grow while you read.

Wiring that package G does: every dependency below is a seam with a default that fails loudly or reads
nothing. Override ``provide_clinic_id`` (clinic of the session), ``provide_accounts`` (``AccountStore``),
``provide_usage`` (``UsageStore``), ``provide_traces`` (``TraceReader``, implemented by package D2's trace
store over ``agent.usage`` / ``agent.usage_steps``: ``UsageStore`` has no "list recent turns" method),
``provide_channels`` (``ChannelRegistry``, for ``online``) and ``provide_log_source`` (where ``bot.log`` is
and whether file logging is on).

Forced deviation: the original read the stats of EVERY account with a separate query. ``UsageStore`` is per
account, so the overview issues one call per account, concurrently (a clinic has a handful of accounts).
"""

from __future__ import annotations

import asyncio
import platform
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BeforeValidator

from pema.api.deps import admin_router
from pema.config.runtime_settings_store import set_settings_clinic
from pema.config.runtime_tuning_settings import bot_time_zone
from pema.shared.log_cursor import doc_con_tro
from pema.shared.log_file_lines import LOG_LEVELS
from pema.shared.read_log_file import ReadLogsOptions, read_recent_logs
from pema.shared.zone_time import start_of_day_utc, today_key
from pema_contracts.admin_agent import (
    AccountOverview,
    AccountUsage,
    LogEntry,
    LogPage,
    OverviewOut,
    SystemInfo,
    TraceTurnPage,
    TraceTurnRow,
)
from pema_contracts.agents import AccountStore
from pema_contracts.channel import ChannelRegistry
from pema_contracts.conversation import AccountStats, TraceStepRow, UsageStore
from pema_contracts.errors import DomainError, ErrorCode

router = admin_router("usage", "admin-usage")
traces_router = admin_router("traces", "admin-usage")
logs_router = admin_router("logs", "admin-usage")

ONE_DAY = timedelta(days=1)

MAX_TURNS = 50
"""Most turns returned per call: a policy of ours, enough to look back over the last few days."""

VERSION = "0.1.0"


class TraceReader(Protocol):
    """Read side of the trace store (package D2: ``agent_trace_store``): ``getRecentTurnsAllThreads``,
    ``getRecentTurns`` and ``getTurnTrace`` of the original. Rows are newest first (id descending)."""

    async def list_recent_turns(
        self,
        clinic_id: UUID,
        *,
        before: int | None,
        limit: int,
        account_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[TraceTurnRow]: ...

    async def get_turn_steps(self, clinic_id: UUID, turn_id: int) -> list[TraceStepRow]: ...


@dataclass(frozen=True)
class LogSource:
    log_dir: Path
    enabled: bool


def _not_wired(what: str) -> DomainError:
    return DomainError(ErrorCode.NOT_IMPLEMENTED, f"Chức năng chưa được nối với {what}.")


async def provide_clinic_id() -> UUID:
    raise _not_wired("phiên đăng nhập")


async def provide_accounts() -> AccountStore:
    raise _not_wired("kho tài khoản")


async def provide_usage() -> UsageStore:
    raise _not_wired("kho mức dùng")


async def provide_traces() -> TraceReader:
    raise _not_wired("kho trace")


async def provide_channels() -> ChannelRegistry:
    raise _not_wired("danh sách kênh đang chạy")


async def provide_log_source() -> LogSource:
    return LogSource(log_dir=Path(".local/data/logs"), enabled=False)


ClinicId = Annotated[UUID, Depends(provide_clinic_id)]
Accounts = Annotated[AccountStore, Depends(provide_accounts)]
Usage = Annotated[UsageStore, Depends(provide_usage)]
Traces = Annotated[TraceReader, Depends(provide_traces)]
Channels = Annotated[ChannelRegistry, Depends(provide_channels)]
LogSourceDep = Annotated[LogSource, Depends(provide_log_source)]

_STARTED = time.monotonic()


# ----------------------------------------------------------------------------------------------- overview


def _days_from_query(raw: object) -> object:
    """A query string arrives as text and pydantic does not turn "14" into the literal 14 by itself; anything
    that is not an integer stays as it is and is rejected by the ``Literal`` (422)."""
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw)
    return raw


@router.get("/overview", response_model=OverviewOut, summary="Accounts, usage per day and system info")
async def get_overview(
    clinic_id: ClinicId,
    accounts_store: Accounts,
    usage: Usage,
    channels: Channels,
    days: Annotated[Literal[7, 14, 30], BeforeValidator(_days_from_query)] = 7,
) -> OverviewOut:
    """The overview page: accounts (DB + online state) + usage per day. Every "today" is computed in
    ``BOT_TIMEZONE`` (not the UTC day nor the browser's time): ``today_key`` + ``timezone`` come back with the
    answer so the frontend uses them as is instead of deriving the day from the browser's clock, which drifts
    from the bot's local time. ``days`` is only 7, 14 or 30 (the DTO enforces it): ``?days=100000`` would scan
    the whole turns table and fold it in memory.
    """
    set_settings_clinic(clinic_id)
    zone = bot_time_zone()
    stored = await accounts_store.list_accounts(clinic_id)
    accounts = [
        AccountOverview(
            id=a.id,
            label=a.label,
            enabled=a.enabled,
            online=channels.get_running(clinic_id, a.id) is not None,
        )
        for a in stored
    ]
    start_of_today = start_of_day_utc(zone)
    # Start of the local day, going back N days: NOT "N*24 hours ago" (that cuts a local day in the middle and
    # leaves the oldest day of the chart a few hours short).
    since = start_of_day_utc(zone, datetime.now(UTC) - days * ONE_DAY)

    daily = await asyncio.gather(*(usage.get_daily_usage(clinic_id, a.id, since, zone) for a in accounts))
    stats: list[AccountStats] = list(
        await asyncio.gather(*(usage.get_account_stats(clinic_id, a.id, start_of_today) for a in accounts))
    )
    return OverviewOut(
        accounts=accounts,
        usage_by_account=[
            AccountUsage(account_id=a.id, daily=d) for a, d in zip(accounts, daily, strict=True)
        ],
        stats_by_account=stats,
        system=SystemInfo(
            version=VERSION,
            uptime_seconds=int(time.monotonic() - _STARTED),
            python=platform.python_version(),
        ),
        today_key=today_key(zone),
        timezone=zone,
        days=days,
    )


# ------------------------------------------------------------------------------------------------ traces


def _page(rows: list[TraceTurnRow], limit: int) -> TraceTurnPage:
    """Take ONE extra turn to know whether more data lies behind, without a COUNT on a table being scanned in
    full; trim the extra before returning."""
    more = len(rows) > limit
    turns = rows[:limit]
    return TraceTurnPage(turns=turns, next_cursor=turns[-1].id if more and turns else None)


@traces_router.get("", response_model=TraceTurnPage, summary="Recent turns of all threads")
async def list_traces(
    clinic_id: ClinicId,
    traces: Traces,
    before: Annotated[
        int | None, Query(ge=1, description="Cursor: id of the last turn of the previous page.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_TURNS)] = MAX_TURNS,
) -> TraceTurnPage:
    rows = await traces.list_recent_turns(clinic_id, before=before, limit=limit + 1)
    return _page(rows, limit)


@traces_router.get("/turn/{turn_id}", response_model=list[TraceStepRow], summary="Steps of one turn")
async def get_turn_trace(turn_id: int, clinic_id: ClinicId, traces: Traces) -> list[TraceStepRow]:
    # Stop before touching the DB: a junk id in a prepared statement is a hard-to-read error
    if turn_id <= 0:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "turn_id phải là số nguyên dương")
    return await traces.get_turn_steps(clinic_id, turn_id)


@traces_router.get(
    "/{account_id}/{thread_id}", response_model=TraceTurnPage, summary="Recent turns of one thread"
)
async def list_thread_traces(
    account_id: str,
    thread_id: str,
    clinic_id: ClinicId,
    traces: Traces,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_TURNS)] = MAX_TURNS,
) -> TraceTurnPage:
    rows = await traces.list_recent_turns(
        clinic_id, before=before, limit=limit + 1, account_id=account_id, thread_id=thread_id
    )
    return _page(rows, limit)


# -------------------------------------------------------------------------------------------------- logs

_LEVEL_NAME: dict[int, Literal["trace", "debug", "info", "warn", "error", "fatal"]] = {
    10: "trace",
    20: "debug",
    30: "info",
    40: "warn",
    50: "error",
    60: "fatal",
}


def _level_name(level: int) -> Literal["trace", "debug", "info", "warn", "error", "fatal"]:
    """The pino number to its label; an odd number lands on the nearest lower level."""
    known = [n for n in _LEVEL_NAME if n <= level]
    return _LEVEL_NAME[max(known)] if known else "trace"


@logs_router.get("/app", response_model=LogPage, summary="Application log lines (read-only, no PII)")
async def read_app_logs(
    source: LogSourceDep,
    level: Literal["trace", "debug", "info", "warn", "error", "fatal"] | None = None,
    scope: str | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    before: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> LogPage:
    if not source.enabled:
        return LogPage(
            entries=[],
            disabled=True,
            hint="Ghi log ra file đang tắt: bật PEMA_LOG_FILE_ENABLED để xem log ở trang này.",
        )
    cursor = doc_con_tro(before) if before is not None else None
    if before is not None and cursor is None:
        # A broken cursor must NOT fall back to the first page: the client would append the same lines for
        # ever
        return LogPage(entries=[])
    result = await asyncio.to_thread(
        read_recent_logs,
        source.log_dir,
        ReadLogsOptions(
            limit=limit,
            min_level=LOG_LEVELS[level] if level else None,
            scope=scope,
            search=search,
            before=cursor,
        ),
    )
    return LogPage(
        entries=[
            LogEntry(
                time=datetime.fromtimestamp(e.time / 1000, UTC),
                level=_level_name(e.level),
                scope=e.scope,
                message=e.msg,
                fields=e.fields or None,
            )
            for e in result.entries
        ],
        scopes=result.scopes,
        next_cursor=result.next_cursor,
    )
