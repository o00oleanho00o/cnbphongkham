# ported from: src/scheduler/scheduled-job-thread-cap.ts
"""Cap ``SCHEDULER_MAX_JOBS_PER_THREAD`` of ENABLED jobs per thread - the layer that blocks job spam (section
7 "Safety" of the original design note). Shared by BOTH ways of creating a job: the ``schedule_task`` tool and
the admin route - before, each place copied this count + comparison itself, and the two copies sooner or later
diverged; a divergence here means one of the two creation paths ESCAPES the cap.

Returns only the ROOT REASON, no hint about what to do next - each caller has a different context to say
"what next" (the tool suggests action='list'/'cancel', the dashboard has no such concept).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.scheduler.scheduled_job_store import ScheduledJobStore


@dataclass(frozen=True)
class ThreadJobCapResult:
    ok: bool
    reason: str = ""


async def check_thread_job_cap(
    store: ScheduledJobStore, clinic_id: UUID, account_id: str, thread_id: str
) -> ThreadJobCapResult:
    max_jobs = get_tuning_int("SCHEDULER_MAX_JOBS_PER_THREAD")
    jobs = await store.list_jobs_for_thread(clinic_id, account_id, thread_id)
    active_count = sum(1 for j in jobs if j.enabled)
    if active_count < max_jobs:
        return ThreadJobCapResult(ok=True)
    return ThreadJobCapResult(
        ok=False, reason=f"Cuộc trò chuyện này đã có đủ {max_jobs} lịch hẹn đang bật - đã chạm trần."
    )
