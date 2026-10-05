# ported from: src/agent/tools/schedule-task-tool-sql-error.test.ts
"""A test ISOLATED to one file - forces the outer ``except`` branch of ``schedule_task_tool`` with a
failure of
the infrastructure under the scheduler port.

Forced deviation: the original DROPped the ``scheduled_jobs`` table so that every statement raised a REAL
SQLite error ("no such table: scheduled_jobs"). Here the store is behind the async ``SchedulerPort``, so the
fake port raises an arbitrary exception for every call. The original also asserted that the sentence carried
the raw SQL message; the Python tool deliberately does NOT leak it (a Postgres driver error can carry query
parameters and rows, i.e. personal data) and gives the model the exception class name instead - the
assertions keep the spirit: a marked failure, readable by the model, never an exception into the agent loop.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pema.agent.tools.schedule_task_tool import create_schedule_task_tool
from pema.agent.tools.testing import FakeScheduler, make_tool_context, make_tool_deps
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result_test_helper import loi_cua_tool
from pema_contracts.channel import ChannelKind
from pema_contracts.scheduler import CreateScheduledJobInput, ScheduledJob
from pema_contracts.testing import make_inbound
from pema_contracts.tools import ToolContext

SECRET_DETAIL = "relation scheduled_jobs DETAIL Key (thread_id)=(secret-thread-123)"


class SchedulerDownError(RuntimeError):
    """Stands for a driver error (the table is gone)."""


class BrokenScheduler(FakeScheduler):
    """Every call that touches the store raises, like a dropped table."""

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> list[ScheduledJob]:
        raise SchedulerDownError(SECRET_DETAIL)

    async def get_job(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str
    ) -> ScheduledJob | None:
        raise SchedulerDownError(SECRET_DETAIL)

    async def create_job(self, job: CreateScheduledJobInput) -> ScheduledJob:
        raise SchedulerDownError(SECRET_DETAIL)


def make_ctx() -> ToolContext:
    message = make_inbound("", channel=ChannelKind.ZALO_PERSONAL, account_id="acc-test", thread_id="t-1")
    return make_tool_context(message=message)


def make_broken_deps() -> ToolDeps:
    scheduler = BrokenScheduler()
    return make_tool_deps(scheduler=scheduler, job_updater=scheduler)


async def run(ctx: ToolContext, args: dict[str, Any]) -> object:
    return await create_schedule_task_tool(ctx, make_broken_deps()).execute(args)


async def test_schedule_task_loi_ha_tang_action_list_dung_bang_da_mat_tra_ve_chuoi_loi_khong_throw() -> None:
    """action='list' đụng bảng đã mất: TRẢ VỀ chuỗi lỗi cho model đọc, KHÔNG throw ra agent loop"""
    # If the try/except of the tool were misplaced or missing, the ``await`` here would raise by itself and
    # this whole test would fail (no separate ``pytest.raises`` needed).
    result = await run(make_ctx(), {"action": "list"})

    # ``loi_cua_tool`` asserts two things at once: it did NOT raise into the agent loop (we reached this
    # line), and the failing branch is MARKED so the guard can count it.
    loi = loi_cua_tool(result)
    assert "thất bại" in loi.lower(), (
        "phải là câu lỗi đọc được cho model, không phải chuỗi rỗng hay JSON lỗi thô"
    )
    assert "SchedulerDownError" in loi, "phải nêu loại lỗi hạ tầng thật, không phải câu chung chung bịa ra"
    assert "secret-thread-123" not in loi, "không được lộ chi tiết nội bộ của driver ra cho model"


async def test_schedule_task_loi_ha_tang_action_create_cung_qua_dung_nhanh_catch() -> None:
    """action='create' cũng qua đúng nhánh catch (bước kiểm trùng/trần gọi list_jobs_for_thread trước khi
    ghi)"""
    result = await run(
        make_ctx(),
        {
            "action": "create",
            "name": "x",
            "kind": "message",
            "payload": "y",
            "schedule": {"kind": "every", "minutes": 30},
        },
    )

    loi = loi_cua_tool(result)
    assert "SchedulerDownError" in loi
    assert "secret-thread-123" not in loi
