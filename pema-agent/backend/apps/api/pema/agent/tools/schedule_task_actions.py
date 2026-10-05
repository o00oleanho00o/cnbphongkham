# ported from: src/agent/tools/schedule-task-actions.ts
"""Logic of the 4 actions of ``schedule_task``, split from ``schedule_task_tool`` (which keeps the
``FunctionTool`` wiring) so each file does one thing. The THREAD SCOPE ``(account_id, thread_id)`` is already
bound at the STORE LAYER (``SchedulerPort``: ``get_job`` / ``list_jobs_for_thread`` / ``delete_job`` take the
account and the thread) - the functions here only call the scoped function, they never re-write a WHERE
condition.

Forced deviations:

* the synchronous SQLite store (``createJob``, ``getJob`` ...) becomes the async ``SchedulerPort`` of the
  contracts plus the ``JobUpdater`` and ``ScheduleParser`` protocols of ``tool_deps``; so every action is
  ``async`` and takes ``(ctx, deps, ...)``;
* ``checkThreadJobCap`` (``scheduled-job-thread-cap.ts``, owned by package S) and ``senderTrustFrom``
  (``history-to-model-messages.ts``, package D1) are re-implemented locally below (a few pure lines each, same
  Vietnamese text) so the tools do not import another package. The cap runs over the job list this action has
  ALREADY fetched for the duplicate check instead of listing the thread a second time;
* NEW for the clinic (CONTRACTS-AI01 section 3): after the parse / duplicate / cap checks and before
  ``create_job`` the action asks ``PolicyHooks.check_job``. ``DENY`` is a failure; ``DOWNGRADE_TO_DRAFT``
  still creates the job but tells the model that it will only prepare a draft for staff. The scheduler (S)
  calls the same hook again at run time, on purpose.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pema.agent.tools.schedule_task_tool_schema import (
    CreateScheduleTaskInput,
    UpdateScheduleTaskInput,
)
from pema.agent.tools.tim_lich_hen_trung import tim_lich_hen_trung
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import KetQuaLoiTool, ket_qua_loi
from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_int
from pema.shared.current_datetime import get_date_time_parts
from pema_contracts.agents import Allowlist, AllowlistMode
from pema_contracts.channel import ThreadKind
from pema_contracts.policy import JobAction
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    JobKind,
    JobOrigin,
    ParsedSchedule,
    ScheduledJob,
    ScheduleKind,
)
from pema_contracts.tools import ToolContext

_CHUNG_CHUNG_TU_CHOI_JOB = (
    "Chính sách của kênh này không cho đặt lịch hẹn kiểu này. "
    "Nói thật với người dùng là bạn không tạo được lịch này."
)
_NHAC_HA_THANH_BAN_NHAP = (
    " LƯU Ý: lịch này chỉ soạn BẢN NHÁP cho nhân viên duyệt, KHÔNG tự gửi cho khách - "
    "nói rõ điều đó với người dùng, đừng hứa là tin sẽ tự đi."
)


def _sender_is_unverified(allowlist: Allowlist, sender_id: str) -> bool:
    """``senderTrustFrom(allowlist).isUnverified(senderId)``: only the ``list`` mode has the notion of a
    person
    outside the list. (The original also treated an ABSENT sender id as not unverified, since old messages
    stored before the ``sender_id`` column existed carry none; ``InboundMessage.sender_id`` is mandatory
    here.)"""
    if allowlist.mode is not AllowlistMode.LIST:
        return False
    return sender_id not in set(allowlist.user_ids)


def _is_allowed_to_create(ctx: ToolContext) -> bool:
    """Only a person in the allowlist can create a job - the FIRST of the 4 safety layers of the "An toàn"
    section (``thiet-ke-scheduler.md``): one cleverly written message is enough to spawn a recurring task
    nobody
    notices. Reuses the very condition the allowlist filter uses to decide "is this person in the list" - the
    allowlist rule is not written a second time elsewhere."""
    return not _sender_is_unverified(ctx.account.allowlist, ctx.message.sender_id)


def _thread_cap_reason(jobs: list[ScheduledJob]) -> str | None:
    """``checkThreadJobCap`` (package S): ``SCHEDULER_MAX_JOBS_PER_THREAD`` ENABLED jobs per thread - the
    job-spam guard. Returns the ROOT reason only, without the follow-up instruction: each caller has its own
    context to say "what to do next". ``None`` = under the cap."""
    max_jobs = get_tuning_int("SCHEDULER_MAX_JOBS_PER_THREAD")
    active_count = sum(1 for j in jobs if j.enabled)
    if active_count < max_jobs:
        return None
    return f"Cuộc trò chuyện này đã có đủ {max_jobs} lịch hẹn đang bật - đã chạm trần."


def _parse_iso_utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def describe_schedule(job: ScheduledJob) -> str:
    """Describe the schedule in words, read from the STORED ``next_run_at`` instead of re-deriving it from the
    original input: this is the most trustworthy source to read back to the user for confirmation, since it
    went through the very ``compute_next_run`` the store uses to decide when the job really runs - exactly the
    persona's advice "reading it back is the cheapest way to catch a misunderstanding"."""
    if not job.next_run_at:
        return "không còn lần chạy nào sắp tới"
    p = get_date_time_parts(bot_time_zone(), _parse_iso_utc(job.next_run_at))
    moc_ke = f"lần kế tiếp {p.time} ngày {p.date} (giờ Việt Nam)"
    if job.schedule_kind is ScheduleKind.ONCE:
        return f"chạy 1 lần lúc {p.time} ngày {p.date} (giờ Việt Nam)"
    if job.schedule_kind is ScheduleKind.EVERY:
        return f"lặp mỗi {job.every_minutes} phút, {moc_ke}"
    return f'theo lịch cron "{job.cron_expr}", {moc_ke}'


def _thread_type_of(ctx: ToolContext) -> int:
    """zca-js ``ThreadType``: 0 = direct, 1 = group (the int the store keeps)."""
    return 1 if ctx.message.thread_kind is ThreadKind.GROUP else 0


async def do_create(ctx: ToolContext, deps: ToolDeps, input: CreateScheduleTaskInput) -> str | KetQuaLoiTool:
    if not _is_allowed_to_create(ctx):
        return ket_qua_loi(
            "Chỉ người trong danh sách được phép (allowlist) mới đặt được lịch hẹn. "
            "Nói thật với người dùng là bạn không tạo được lịch này."
        )

    parsed = deps.schedule_parser.parse_schedule(
        input.schedule,
        time_zone=bot_time_zone(),
        min_interval_minutes=get_tuning_int("SCHEDULER_MIN_INTERVAL_MINUTES"),
    )
    if not parsed.ok or parsed.schedule is None:
        return ket_qua_loi(parsed.error)
    schedule: ParsedSchedule = parsed.schedule
    kind = JobKind(input.kind)

    # DEDUPE even BEFORE the job/thread cap - on purpose. An exact duplicate call adds NO job, so blocking it
    # with "cap reached" reports the wrong thing: the user only wants to know whether the schedule is set yet,
    # and would receive a sentence telling them to cancel an old schedule. In return ``parse_schedule`` has to
    # run one step earlier - it is pure, without side effects.
    #
    # Why it is needed: the model does NOT see the tool calls of the previous turn in the history, so it
    # "checks whether the schedule is set" by calling create again. See ``tim_lich_hen_trung`` for the real
    # case and the measurements.
    jobs = await deps.scheduler.list_jobs_for_thread(ctx.clinic_id, ctx.account.id, ctx.message.thread_id)
    trung = tim_lich_hen_trung(jobs=jobs, name=input.name, kind=kind, schedule=schedule)
    if trung.trung_khit is not None:
        j = trung.trung_khit
        # A bare string, NOT ``ket_qua_loi``: the state the user wants ALREADY exists, so this is a success,
        # not a failure. It says plainly "not created again" so the model does not tell the user it just
        # set one
        # more schedule.
        return (
            f'Lịch này ĐÃ CÓ SẴN, không tạo thêm bản trùng: "{j.name}" (id: {j.id}) - '
            f"{describe_schedule(j)}. "
            "Nói với người dùng là lịch đã được đặt từ trước và vẫn còn hiệu lực - "
            "ĐỪNG nói bạn vừa đặt thêm một lịch mới."
        )

    cap_reason = _thread_cap_reason(jobs)
    if cap_reason is not None:
        return ket_qua_loi(
            f"{cap_reason} Gọi action='list' rồi hủy bớt lịch cũ (action='cancel') trước khi đặt lịch mới."
        )

    job_input = CreateScheduledJobInput(
        clinic_id=ctx.clinic_id,
        account_id=ctx.account.id,
        thread_id=ctx.message.thread_id,
        thread_type=_thread_type_of(ctx),
        name=input.name,
        kind=kind,
        payload=input.payload,
        schedule=schedule,
        created_by=ctx.message.sender_id,
        origin=JobOrigin.AGENT_TOOL,
    )

    # Policy gate of the clinic profile (e.g. ``patient_channel`` refuses or downgrades an ``agent`` job). The
    # scheduler asks the same hook again when the job runs.
    decision = await deps.policy.check_job(ctx.policy, job_input)
    if decision.action is JobAction.DENY:
        return ket_qua_loi(decision.reason or _CHUNG_CHUNG_TU_CHOI_JOB)

    job = await deps.scheduler.create_job(job_input)

    # The same run schedule but a DIFFERENT name is still created - a person can perfectly book two different
    # things at the same hour. Only SAY it to the model: it is the safety net for when the name comparison
    # slips
    # (the model names it off by one word), and also information the user deserves to hear.
    nhac_cung_lich = ""
    if trung.cung_lich:
        ten_cac_lich = ", ".join(f'"{j.name}"' for j in trung.cung_lich)
        nhac_cung_lich = (
            f" LƯU Ý: cuộc trò chuyện này đã có {len(trung.cung_lich)} lịch khác chạy cùng nhịp/mốc giờ đó"
            f" ({ten_cac_lich}) - nói cho người dùng biết để họ tự quyết có trùng ý không."
        )
    nhac_ban_nhap = _NHAC_HA_THANH_BAN_NHAP if decision.action is JobAction.DOWNGRADE_TO_DRAFT else ""

    return (
        f'Đã tạo lịch "{job.name}" (id: {job.id}) - {describe_schedule(job)}. '
        f"Đọc lại mốc giờ này cho người dùng nghe để họ xác nhận đúng ý.{nhac_cung_lich}{nhac_ban_nhap}"
    )


async def do_list(ctx: ToolContext, deps: ToolDeps) -> str:
    jobs = await deps.scheduler.list_jobs_for_thread(ctx.clinic_id, ctx.account.id, ctx.message.thread_id)
    if not jobs:
        return "Cuộc trò chuyện này chưa có lịch hẹn nào."

    return "\n".join(
        f'- id: {j.id} | "{j.name}" | {j.kind.value} | {"đang bật" if j.enabled else "đã tắt"}'
        f" | {describe_schedule(j)}"
        for j in jobs
    )


async def do_cancel(ctx: ToolContext, deps: ToolDeps, id: str) -> str | KetQuaLoiTool:
    job = await deps.scheduler.get_job(ctx.clinic_id, ctx.account.id, ctx.message.thread_id, id)
    if job is None:
        return ket_qua_loi(
            f'Không tìm thấy lịch hẹn id "{id}" trong cuộc trò chuyện này. '
            "Gọi action='list' để lấy đúng id trước khi hủy."
        )
    await deps.scheduler.delete_job(ctx.clinic_id, ctx.account.id, ctx.message.thread_id, id)
    return f'Đã hủy lịch "{job.name}" (id: {job.id}).'


async def do_update(ctx: ToolContext, deps: ToolDeps, input: UpdateScheduleTaskInput) -> str | KetQuaLoiTool:
    existing = await deps.scheduler.get_job(ctx.clinic_id, ctx.account.id, ctx.message.thread_id, input.id)
    if existing is None:
        return ket_qua_loi(
            f'Không tìm thấy lịch hẹn id "{input.id}" trong cuộc trò chuyện này. '
            "Gọi action='list' để lấy đúng id trước khi sửa."
        )

    schedule: ParsedSchedule | None = None
    if input.schedule is not None:
        parsed = deps.schedule_parser.parse_schedule(
            input.schedule,
            time_zone=bot_time_zone(),
            min_interval_minutes=get_tuning_int("SCHEDULER_MIN_INTERVAL_MINUTES"),
        )
        if not parsed.ok or parsed.schedule is None:
            return ket_qua_loi(parsed.error)
        schedule = parsed.schedule

    updated = await deps.job_updater.update_job(
        ctx.clinic_id,
        ctx.account.id,
        ctx.message.thread_id,
        input.id,
        name=input.name,
        payload=input.payload,
        schedule=schedule,
    )
    if updated is None:
        return ket_qua_loi(
            f'Không tìm thấy lịch hẹn id "{input.id}" trong cuộc trò chuyện này. '
            "Gọi action='list' để lấy đúng id trước khi sửa."
        )
    return (
        f'Đã cập nhật lịch "{updated.name}" (id: {updated.id}) - {describe_schedule(updated)}. '
        "Đọc lại mốc giờ này cho người dùng nghe để họ xác nhận đúng ý."
    )
