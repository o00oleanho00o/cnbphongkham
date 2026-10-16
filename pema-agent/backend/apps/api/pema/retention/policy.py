"""The retention periods of one run: days per data group, ``0`` = keep forever (new module, no TS source).

The legal periods under Decree 13/2023 are the clinic owner's decision (SCOPE-AI01, decision 7), so this
module carries no number of its own: it reads ``Settings`` (``PEMA_RETENTION_*``). The API process (role
``be_app``) runs the one scope, ``clinic``; the agent service keeps its own data in its own database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pema.config.env import Settings


class Scope(StrEnum):
    """Which process runs a group. The value is also the scope written in the audit row."""

    CLINIC = "clinic"


@dataclass(frozen=True)
class RetentionPolicy:
    """Days per group (``0`` keeps the data forever) and the job's batching."""

    auth_session_days: int = 1
    batch_size: int = 500

    def __post_init__(self) -> None:
        if self.auth_session_days < 0:
            raise ValueError("auth_session_days must be 0 (keep forever) or a number of days")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")


def policy_from_settings(settings: Settings) -> RetentionPolicy:
    """The policy of ``Settings``."""
    return RetentionPolicy(
        auth_session_days=settings.retention_auth_session_days, batch_size=settings.retention_batch_size
    )
