# ported from: src/scheduler/scheduled-job-reply-target.ts
"""The send path of ONE scheduled job, on the RIGHT channel of the account.

Why a separate factory instead of every place building it by itself: THREE places need a ``ReplyTarget`` for a
job (the main send path ``run_scheduled_job``, the daily cap notice ``scheduled_job_cap_guard``, and any path
added later). Three hand-written copies are three chances to forget a field - the reasoning already written in
the docstring of ``duongGuiZcaJs``.

The earlier version of the original called ``getRunningAccountApi`` in all three places and built the zca-js
path by hand, hard-locking the scheduler to the personal channel. That was the REAL reason schedules did not
run on the bot channel - not that the Bot API lacked the ability to send proactively (measured: 10 messages in
416 ms, not blocked). The second place (``cap-guard``) failed SILENTLY: a bot that reached the daily cap told
nobody.

Forced deviation: ``KenhLuot`` is ``ChannelPort`` and ``getRunningAccountKenh`` is ``ChannelRegistry``
(package A). The ``api`` field of the original ``DichGuiJob`` disappears: ``ToolContext`` carries the channel
(``api: null`` was already the bot case; the guard "every tool that needs the personal API is in the
channel's ``blocked_tools``" lives in package D4).
"""

from __future__ import annotations

from dataclasses import dataclass

from pema.scheduler.ports import ReplyTarget
from pema_contracts.channel import ChannelPort, ChannelRegistry
from pema_contracts.scheduler import ScheduledJob, thread_kind_of


@dataclass(frozen=True)
class JobSendTarget:
    """``DichGuiJob``."""

    target: ReplyTarget
    channel: ChannelPort
    """The channel of the turn, returned HERE instead of letting the caller ask the registry a second time:
    two lookups are two chances to read two different states if the account is stopped in between (an agent
    turn runs for minutes), and then the target would point to the old channel."""


def make_job_target(channels: ChannelRegistry, job: ScheduledJob) -> JobSendTarget | None:
    """``taoDichGuiChoJob``. ``None`` when the account is NOT RUNNING (not logged in, off, stopped). The
    caller handles it exactly as before: ``conclude_blocked_not_run`` - keep the run slot, restore
    ``next_run_at``, retry next tick.

    This function NEVER raises: ``scheduled_job_cap_guard`` calls it from the NOT-AWAITED path of the tick.
    It only reads a dict in memory and builds an object.

    There is NO ``quote``: a scheduled job answers no message at all (the rule already written in the
    ``ReplyTarget`` docstring), and the original factory did not set one either."""
    channel = channels.get_running(job.clinic_id, job.account_id)
    if channel is None:
        return None
    return JobSendTarget(
        channel=channel,
        target=ReplyTarget(
            clinic_id=job.clinic_id,
            account_id=job.account_id,
            thread_id=job.thread_id,
            thread_kind=thread_kind_of(job.thread_type),
            thread_key=f"{job.account_id}:{job.thread_id}",
            channel=channel,
        ),
    )
