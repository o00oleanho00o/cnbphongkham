"""The retention periods of one run: days per data group, ``0`` = keep forever (new module, no TS source).

The legal periods under Decree 13/2023 are the clinic owner's decision (SCOPE-AI01, decision 7), so this
module carries no number of its own: it reads ``Settings`` (``PEMA_RETENTION_*``) and, for the two groups
that already had a tuning key before this job existed (trace and media), falls back to that key when the
setting is unset, so a value saved on the dashboard (``AGENT_TRACE_RETENTION_DAYS``,
``MEDIA_RETENTION_DAYS``) keeps working.

The groups are named by what they are, not by table, and each belongs to ONE scope: the scope is the process
that may run it. ``agent`` runs in the worker (role ``agent_worker``: ``agent.*`` and the media files),
``clinic`` runs in the API process (role ``be_app``: ``clinic.*``). The worker has no privilege on
``clinic.*`` and keeps none (ARCH-AI01 section 3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pema.config.env import Settings

TRACE_TUNING_KEY = "AGENT_TRACE_RETENTION_DAYS"
MEDIA_TUNING_KEY = "MEDIA_RETENTION_DAYS"


class Scope(StrEnum):
    """Which process runs a group. The value is also the scope written in the audit row."""

    AGENT = "agent"
    CLINIC = "clinic"


@dataclass(frozen=True)
class RetentionPolicy:
    """Days per group (``0`` keeps the data forever) and the job's batching."""

    history_days: int = 0
    memory_days: int = 0
    message_days: int = 0
    usage_days: int = 0
    trace_days: int = 7
    media_days: int = 7
    job_run_days: int = 30
    auth_session_days: int = 1
    link_code_days: int = 7
    link_attempt_days: int = 30
    batch_size: int = 500

    def __post_init__(self) -> None:
        for name in (
            "history_days",
            "memory_days",
            "message_days",
            "usage_days",
            "trace_days",
            "media_days",
            "job_run_days",
            "auth_session_days",
            "link_code_days",
            "link_attempt_days",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be 0 (keep forever) or a number of days")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")


def policy_from_settings(settings: Settings, tuning_int: Callable[[str], int]) -> RetentionPolicy:
    """The policy of ``Settings``; ``tuning_int`` reads a tuning key (``get_tuning_int`` in production)."""
    trace = settings.retention_trace_days
    media = settings.retention_media_days
    return RetentionPolicy(
        history_days=settings.retention_history_days,
        memory_days=settings.retention_memory_days,
        message_days=settings.retention_message_days,
        usage_days=settings.retention_usage_days,
        trace_days=trace if trace is not None else tuning_int(TRACE_TUNING_KEY),
        media_days=media if media is not None else tuning_int(MEDIA_TUNING_KEY),
        job_run_days=settings.retention_job_run_days,
        auth_session_days=settings.retention_auth_session_days,
        link_code_days=settings.retention_link_code_days,
        link_attempt_days=settings.retention_link_attempt_days,
        batch_size=settings.retention_batch_size,
    )
