# ported from: src/scheduler/run-scheduled-job.ts
"""One run of 1 scheduled job: build the input -> (agent if kind='agent') -> check [SILENT] -> guard before
sending -> send -> write history + run ledger.

NO retry at this layer: the agent loop already has 2 layers of retry (router glitch + the SDK ``maxRetries``).
A failed job writes run 'error' and stays quiet - it does NOT send "technical problem" like a message turn,
because nobody is sitting there waiting to be told (the goclaw rule: only a SUCCESSFUL output is delivered).

Forced deviations:

* ``resolveModel`` (the model seam of the test) disappears: the engine is injected (``AgentEngine``, a fake in
  the tests) and the scheduler never imports ``pema.agent``; a provider failure arrives as ``AgentTurnError``
  with the kind already classified (``phanLoaiLoiProvider`` stays inside the engine);
* the run id may be passed in (``RunScheduledJobOptions.run_id``): the tick opens the run in the SAME
  transaction as the claim of the occurrence, so a crash cannot leave a claimed job without a ``running`` row;
* a heartbeat keeps refreshing the ``running`` row while the run dispatches, so another worker can tell a long
  agent turn from a dead worker (``interrupt_stale_runs``);
* the order of ``run_message_job`` is "sanitise -> policy -> guard" (the original did "guard -> sanitise"): a
  text that fails sanitising no longer leaves a cap slot taken, and a text that is only HELD for review never
  touches the cap at all.

Clinic additions: ``check_job`` and ``on_outbound`` hooks, template resolution for ``kind: message`` under a
profile that only allows approved templates, marketing opt-out, review hold (see ``scheduled_job_send``), and
the policy-forced ``draft_only`` for ``kind: agent`` under ``patient_channel``.

Config errors: in the original the inner ``catch`` of ``runAgentJob`` swallowed EVERY error, including
``cau_hinh``, so the dedicated "bot not configured yet" branch of ``runScheduledJob`` could never be reached
and a ``once`` reminder lost its run slot after 3 ticks just because nobody had typed the API key yet. The
documented intent is the opposite ("keep the slot, restore ``next_run_at``, do not count it as a failed
send"), so here a CONFIG ``AgentTurnError`` is re-raised after the usage/trace bookkeeping and handled by the
outer branch."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.ports import ReplyTarget
from pema.scheduler.proactive_send_guard import ACCOUNT_NOT_RUNNING_REASON
from pema.scheduler.run_context import (
    RunContext,
    decide_job_at_run,
    default_time_zone_of,
    resolve_policy_context,
)
from pema.scheduler.scheduled_job_conclude import (
    conclude,
    conclude_blocked_not_run,
    conclude_delivery_failed,
)
from pema.scheduler.scheduled_job_prompt import build_synthetic_message, with_late_label
from pema.scheduler.scheduled_job_reply_target import JobSendTarget, make_job_target
from pema.scheduler.scheduled_job_send import route_outbound
from pema.scheduler.silent_sentinel import is_silent_response
from pema.shared.logger import create_logger
from pema.shared.turn_log_context import TurnLogContext, run_in_turn_log_context
from pema_contracts.agent_turn import (
    AgentTurnRequest,
    StepTrace,
    TokenUsage,
    TurnCallbacks,
    TurnSource,
)
from pema_contracts.agents import AccountConfig
from pema_contracts.policy import JobAction, OutboundOrigin, ScheduledJobPolicy
from pema_contracts.scheduler import JobKind, JobRunStatus, ScheduledJob
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind

log = create_logger("run-scheduled-job")


@dataclass(frozen=True)
class RunScheduledJobOptions:
    late: bool
    """True when ``decide_due_action`` returned 'run-late' (only happens with schedule_kind='once')."""
    scheduled_for: str
    """The ORIGINAL ``next_run_at`` (the instant the job SHOULD have run) - for the label "(nhắc trễ, lịch gốc
    HH:MM)" AND to restore it when blocked (see ``conclude_blocked_not_run``)."""
    now: datetime
    """The instant of THIS RUN - fixed at the start of the tick, shared by every cap bookkeeping of the run
    (take slot, refund slot, add count, right to announce the cap).

    MANDATORY, deliberately no default ``datetime.now()``: taking a slot and refunding it are a whole send
    apart (20 seconds ``SCHEDULER_SEND_GAP_MS``, minutes for an agent job). If each side reads the real clock,
    midnight in between takes the slot on day D and refunds it on day D+1 - day D keeps the slot forever. See
    the header of ``proactive_send_guard``."""
    run_id: int | None = None
    """The run already opened (by the claim transaction of the tick or a trial); ``None`` = open one."""
    trial: bool = False
    """A manual "Run now": its review item must not be the one the REAL occurrence will look up (see
    ``RunContext.review_key``)."""


@asynccontextmanager
async def run_heartbeat(deps: SchedulerDeps, clinic_id: UUID, run_id: int) -> AsyncGenerator[None]:
    """Keep the ``running`` row alive while the run dispatches (see ``interrupt_stale_runs``)."""

    async def beat() -> None:
        while True:
            await asyncio.sleep(deps.heartbeat_seconds)
            try:
                await deps.runs.heartbeat(clinic_id, run_id)
            except Exception as err:  # a missed beat must not kill the run; recovery needs several in a row
                log.warning("Heartbeat của lượt chạy lỗi", run_id=run_id, err=err)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def run_scheduled_job(deps: SchedulerDeps, job: ScheduledJob, options: RunScheduledJobOptions) -> None:
    """Run 1 due job - NEVER raises: it is called NOT AWAITED from the tick loop (``scheduler_loop``, the
    lesson goclaw learned in blood), a broken promise here would have nobody to catch it."""
    try:
        run_id = options.run_id
        if run_id is None:
            run_id = await deps.runs.open_run(job.clinic_id, job.id, worker_id=deps.worker_id)
        async with run_heartbeat(deps, job.clinic_id, run_id):
            try:
                await _dispatch(deps, job, options, run_id)
            except Exception as err:
                message = err.safe_message if isinstance(err, AgentTurnError) else str(err)
                log.error("Lỗi không lường trước khi chạy job lịch hẹn", job_id=job.id, err=err)

                # The bot NOT CONFIGURED YET is its own state, not "a failed send".
                #
                # Since ``.env`` has only one required variable, the bot starts when the API key/model is not
                # entered yet - and in that state the engine raises on every turn. Going into
                # ``conclude_delivery_failed`` would add one ``delivery_attempts`` per tick, and at the third
                # a ``once`` job LOSES ITS RUN SLOT FOREVER - just because the user has not yet opened the
                # dashboard to type the key.
                #
                # The same rule as "account not running": keep the slot, restore ``next_run_at``, do not count
                # it as a failed send. The decided invariant: a reminder that never managed to be sent is
                # never counted as run.
                if isinstance(err, AgentTurnError) and err.kind is ProviderErrorKind.CONFIG:
                    await conclude_blocked_not_run(
                        deps,
                        job,
                        run_id,
                        "Bot chưa cấu hình xong LLM - chưa chạy được.",
                        options.scheduled_for,
                    )
                    return

                # OUTERMOST safety net - we do not know for sure what was sent when the error got here, treat
                # it as "not sent" (Finding 1): count it into delivery_attempts instead of ``mark_run`` at
                # once, to avoid killing the job over one unexpected passing error.
                await conclude_delivery_failed(deps, job, run_id, options.scheduled_for, message)
    except Exception as err:
        log.error("Không chốt được sổ chạy của job lịch hẹn", job_id=job.id, err=err)


async def _dispatch(
    deps: SchedulerDeps, job: ScheduledJob, options: RunScheduledJobOptions, run_id: int
) -> None:
    time_zone = default_time_zone_of(job)
    # Account NOT RUNNING -> stop RIGHT AWAY - before even opening an agent turn, to avoid spending tokens on
    # a turn that surely cannot send anything. ``scheduler_loop`` already checked this BEFORE
    # clear-before-dispatch so this branch is now only a safety net for the rare case (the account dropped its
    # session while the job was queued for dispatch). Blocking here does NOT ``mark_run`` - the job never
    # really ran.
    #
    # ONE path for BOTH channels: ``make_job_target`` reads the channel of the account and builds the matching
    # send path.
    account = await deps.accounts.get_account(job.clinic_id, job.account_id)
    dest = make_job_target(deps.channels, job)

    if account is None or dest is None:
        await conclude_blocked_not_run(deps, job, run_id, ACCOUNT_NOT_RUNNING_REASON, options.scheduled_for)
        return

    policy = await resolve_policy_context(deps, job, account, isolated=job.kind is JobKind.AGENT)
    cap = await deps.guard.effective_cap(policy, deps.hooks)
    decision = await decide_job_at_run(deps, policy, job, time_zone, options.now)
    if decision.action is JobAction.DENY:
        await conclude(
            deps,
            job,
            run_id,
            FinishRunParams(
                status=JobRunStatus.SKIPPED,
                detail=decision.reason or "Chính sách không cho phép chạy lịch hẹn này.",
            ),
        )
        return

    rc = RunContext(
        job=job,
        account=account,
        policy=policy,
        cap=cap,
        time_zone=time_zone,
        scheduled_for=options.scheduled_for,
        now=options.now,
        run_id=run_id,
        late=options.late,
        draft_only=decision.action is JobAction.DOWNGRADE_TO_DRAFT,
        policy_reason=decision.reason,
        review_key=f"{job.id}@{options.scheduled_for}" + (f"#trial{run_id}" if options.trial else ""),
    )

    if job.kind is JobKind.MESSAGE:
        await _run_message_job(deps, rc, dest.target)
        return
    await _run_agent_job(deps, rc, account, dest)


async def _run_message_job(deps: SchedulerDeps, rc: RunContext, target: ReplyTarget) -> None:
    """kind='message': 0 token, sends the payload verbatim - never touches the LLM (under a profile that only
    allows approved templates the payload is the TEMPLATE KEY and the text sent is the doctor-approved
    body)."""
    job = rc.job
    source_text = job.payload
    template_key: str | None = None

    if rc.policy.profile.scheduled_jobs is not ScheduledJobPolicy.ANY:  # clinic
        template = await deps.templates.get_template(job.clinic_id, job.payload.strip())
        if template is None:
            await conclude_blocked_not_run(
                deps,
                job,
                rc.run_id,
                "Mẫu tin chưa được bác sĩ duyệt hoặc không tồn tại - chưa gửi.",
                rc.scheduled_for,
            )
            return
        if template.marketing and rc.policy.profile.marketing_opt_out_blocks_marketing and job.patient_id:
            patient = await deps.patients.get_patient_ref(job.clinic_id, job.patient_id)
            if patient is not None and patient.marketing_opt_out:
                await conclude(
                    deps,
                    job,
                    rc.run_id,
                    FinishRunParams(
                        status=JobRunStatus.SKIPPED,
                        detail="Bệnh nhân từ chối tin tiếp thị - không gửi.",
                    ),
                )
                return
        source_text = template.body
        template_key = template.template_key

    # ``payload`` is text the MODEL wrote when setting the schedule (through the ``schedule_task`` tool), and
    # the scheduling turn may well have read web content or a stranger's message. Sending it verbatim at the
    # due time means it has to pass the sanitising layer like every other text of the model.
    #
    # NEVER fall back to the RAW text when the filter fires. The earlier version wrote ``sach.chan ?
    # job.payload : sach.text || job.payload`` - i.e. exactly when the guard detected a system prompt leak it
    # sent THAT very string to Zalo, turning this path into the only way in the repo to push
    # system-prompt-like text out.
    #
    # Following the ``redact_sensitive_text`` of Hermes (``cron/scheduler.py``): "Redact secrets from both
    # stdout and stderr BEFORE ANY RETURN PATH", and when the filter itself breaks they return ``"[REDACTED -
    # redaction failed]"`` and never the original string. Equivalent here: blocked means DO NOT SEND.
    #
    # Not sending DIFFERS from killing the schedule: ``conclude_blocked_not_run`` keeps the run slot and
    # restores ``next_run_at`` for a ``once`` job, so the user edits the content and the schedule continues -
    # the invariant "a reminder that never managed to be sent is never counted as run".
    clean = deps.outbound.sanitize_for_config(source_text)
    if clean.chan or not clean.text.strip():
        log.error(
            "Nội dung lịch hẹn không qua được lớp làm sạch - KHÔNG gửi", job_id=job.id, blocked=clean.chan
        )
        await conclude_blocked_not_run(
            deps,
            job,
            rc.run_id,
            (
                "Nội dung lịch hẹn có dấu hiệu lộ chỉ dẫn nội bộ - đã chặn, chưa gửi."
                if clean.chan
                else "Nội dung lịch hẹn rỗng sau khi làm sạch - chưa gửi."
            ),
            rc.scheduled_for,
        )
        return
    if clean.da_sua:
        log.warning("Đã làm sạch payload lịch hẹn trước khi gửi", job_id=job.id, fixes=list(clean.da_sua))

    text = with_late_label(clean.text, rc.scheduled_for, rc.time_zone) if rc.late else clean.text
    await route_outbound(deps, rc, target, text, OutboundOrigin.SCHEDULED_MESSAGE, template_key=template_key)


async def _run_agent_job(
    deps: SchedulerDeps, rc: RunContext, account: AccountConfig, dest: JobSendTarget
) -> None:
    """kind='agent': an ISOLATED agent turn (``isolated=True``) and only then decide to send or stay quiet."""
    job = rc.job
    target = dest.target
    synthetic = build_synthetic_message(job, rc.now, deps.wrap_untrusted, account.channel)
    trace: list[StepTrace] = []
    turn_id = await deps.usage.open_agent_turn(
        job.clinic_id, job.account_id, job.thread_id, TurnSource.SCHEDULE
    )
    # Marks that the REAL usage (``result.usage``) was ALREADY closed - if the ``except`` below catches an
    # error raised AFTER that point, it must NOT call ``finish_agent_turn``/``save_turn_trace`` a second time:
    # the second call would use a fake {0,0,0} usage, OVERWRITING the real tokens just written, and the second
    # ``save_turn_trace`` would INSERT THE SAME ``usage_steps`` rows again (Item 4, round 3).
    turn_finished = False

    async def body() -> None:
        nonlocal turn_finished
        try:
            # ``tools`` get no channel API here: ``isolated=True`` plus the channel's ``blocked_tools`` decide
            # which tools exist in a scheduled turn (package D4 owns that guard and its test).
            result = await deps.engine.run_turn(
                AgentTurnRequest(
                    clinic_id=job.clinic_id,
                    account_id=job.account_id,
                    batch=[synthetic],
                    isolated=True,
                    source=TurnSource.SCHEDULE,
                    scheduled_job_id=job.id,
                ),
                TurnCallbacks(trace=trace),
            )
            await deps.usage.finish_agent_turn(job.clinic_id, turn_id, result.usage)
            if trace:
                await deps.usage.save_turn_trace(job.clinic_id, turn_id, trace)
            turn_finished = True

            if result.handed_off:  # clinic: a policy hook stopped the turn before the model
                await conclude(
                    deps,
                    job,
                    rc.run_id,
                    FinishRunParams(
                        status=JobRunStatus.SKIPPED,
                        turn_id=turn_id,
                        detail=result.hand_off_reason or "Chính sách chuyển lượt này cho người xử lý.",
                    ),
                )
                return

            text = result.text.strip()
            if not text or is_silent_response(text):
                await conclude(
                    deps,
                    job,
                    rc.run_id,
                    FinishRunParams(
                        status=JobRunStatus.SILENT,
                        turn_id=turn_id,
                        detail=(
                            "Agent trả [SILENT] - không có gì mới để báo."
                            if text
                            else "Agent không trả nội dung."
                        ),
                    ),
                )
                return

            # Sanitise AFTER the [SILENT] branch above: running first lets the filter drop the very label that
            # branch relies on to decide silence, and a "nothing new" job would message every morning exactly
            # what it was born to avoid.
            clean = deps.outbound.sanitize_for_config(text)
            if clean.chan:
                # A scheduled turn does NOT send an error sentence (a failed job stays quiet - the rule of the
                # ``except`` branch below), but it must close the run as 'error' for the dashboard.
                #
                # DELIBERATELY ``conclude`` (with ``mark_run``) and not ``conclude_blocked_not_run``, although
                # this spends the run slot of a ``once`` job. Reason: a prompt leak is NOT a passing glitch
                # like an account dropping its session - the job's own payload leads the model there, so the
                # next turn will almost surely leak again. ``conclude_blocked_not_run`` restores
                # ``next_run_at`` to the old instant, which is already past - a ``once`` job would be due
                # again at the very next tick and loop forever. Better to close with an error once and let
                # the user see it on the dashboard and fix the payload.
                log.error("Chặn câu trả lời rò system prompt", job_id=job.id)
                await conclude(
                    deps,
                    job,
                    rc.run_id,
                    FinishRunParams(
                        status=JobRunStatus.ERROR,
                        turn_id=turn_id,
                        detail="Câu trả lời rò system prompt - đã chặn.",
                    ),
                )
                return
            if clean.da_sua:
                log.warning(
                    "Đã làm sạch câu trả lời của job trước khi gửi", job_id=job.id, fixes=list(clean.da_sua)
                )
            if not clean.text.strip():
                await conclude(
                    deps,
                    job,
                    rc.run_id,
                    FinishRunParams(
                        status=JobRunStatus.SILENT,
                        turn_id=turn_id,
                        detail="Không còn nội dung sau khi làm sạch.",
                    ),
                )
                return

            # The "late reminder" label is attached AFTER sanitising: it is OUR text, not the model's, so
            # there is nothing to filter, and it must not slip through the filter either.
            final_text = (
                with_late_label(clean.text, rc.scheduled_for, rc.time_zone) if rc.late else clean.text
            )
            await route_outbound(
                deps, rc, target, final_text, OutboundOrigin.SCHEDULED_AGENT, turn_id=turn_id
            )
        except Exception as err:
            # A turn that threw (provider down, timeout...) still has to close the tokens already spent + save
            # the trace of the steps that ALREADY ran - the same habit as ``message-turn-processor``. The only
            # difference: do NOT send "technical problem" - a failed job stays quiet.
            # Close with usage {0,0,0} ONLY when the real one was never closed (``turn_finished`` false) - the
            # agent loop throwing BEFORE it returns a result is the ONLY case left after ``send_and_conclude``
            # takes care of all its own bookkeeping (Item 2, round 3: it no longer throws after sending).
            if not turn_finished:
                await deps.usage.finish_agent_turn(job.clinic_id, turn_id, TokenUsage(steps=len(trace)))
                if trace:
                    await deps.usage.save_turn_trace(job.clinic_id, turn_id, trace)
            if isinstance(err, AgentTurnError) and err.kind is ProviderErrorKind.CONFIG:
                raise  # not configured yet: the outer branch keeps the slot (see the module docstring)
            # Surely "nothing was sent" - count it into delivery_attempts (Finding 1) instead of mark_run at
            # once.
            error_message = err.safe_message if isinstance(err, AgentTurnError) else str(err)
            await conclude_delivery_failed(deps, job, rc.run_id, rc.scheduled_for, error_message, turn_id)

    await run_in_turn_log_context(
        TurnLogContext(account_id=job.account_id, thread_id=job.thread_id, turn_id=turn_id), body
    )
