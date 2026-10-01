"""Overview, token usage, agent traces and application logs (package D1 implements).

Port of overview-routes.ts, trace-routes.ts and log-routes.ts. Traces and ``history`` may contain
message text: ``admin.usage`` is a staff-only permission. Traces are read-only evidence (no edit, no
delete; retention is a periodic job). Paging is by cursor, never offset: these lists grow while you read.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Query

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import LogPage, OverviewOut, TraceTurnPage
from pema_contracts.conversation import TraceStepRow

router = admin_router("usage", "admin-usage")
traces_router = admin_router("traces", "admin-usage")
logs_router = admin_router("logs", "admin-usage")


@router.get("/overview", response_model=OverviewOut, summary="Accounts, usage per day and system info")
async def get_overview(days: Literal[7, 14, 30] = 7) -> OverviewOut:
    not_implemented()


@traces_router.get("", response_model=TraceTurnPage, summary="Recent turns of all threads")
async def list_traces(
    before: Annotated[
        int | None, Query(ge=1, description="Cursor: id of the last turn of the previous page.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> TraceTurnPage:
    not_implemented()


@traces_router.get("/turn/{turn_id}", response_model=list[TraceStepRow], summary="Steps of one turn")
async def get_turn_trace(turn_id: int) -> list[TraceStepRow]:
    not_implemented()


@traces_router.get(
    "/{account_id}/{thread_id}", response_model=TraceTurnPage, summary="Recent turns of one thread"
)
async def list_thread_traces(
    account_id: str,
    thread_id: str,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> TraceTurnPage:
    not_implemented()


@logs_router.get("/app", response_model=LogPage, summary="Application log lines (read-only, no PII)")
async def read_app_logs(
    level: Literal["trace", "debug", "info", "warn", "error", "fatal"] | None = None,
    scope: str | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    before: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> LogPage:
    not_implemented()
