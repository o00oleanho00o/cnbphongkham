# ported from: src/agent/failed-turn-trace.ts (+ LoaiLoiProvider of provider-error-classifier.ts)
"""How a failed agent turn is reported across package boundaries.

In zalo-agent the turn processor (``zalo/message-turn-processor.ts``) and the scheduler
(``scheduler/run-scheduled-job.ts``) import ``phanLoaiLoiProvider`` and ``traceLuotHong`` from ``agent/``.
Here the channel pipeline (C2) and the scheduler (S) cannot import the agent engine (D1), so the two small
pure pieces they need live in this leaf package:

* ``ProviderErrorKind``: the values of ``LoaiLoiProvider``;
* ``AgentTurnError``: the ONLY exception ``AgentEngine.run_turn`` raises. D1 classifies the provider
  exception INSIDE the engine (the SDK-specific ``phan_loai_loi_provider`` stays in ``pema.agent``) and
  attaches the kind, so consumers never see an SDK type and read only ``error.kind``;
* ``failed_turn_step``: ``traceLuotHong``, the synthetic trace row of a turn that died before running any
  step.

Pure module: only ``pema_contracts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pema_contracts.agent_turn import StepTrace


class ProviderErrorKind(StrEnum):
    """``LoaiLoiProvider``: every kind is treated differently (retrying the wrong kind HARMS: a wrong key
    retried twice is just three times slower, an exhausted quota hit again may be throttled harder)."""

    CONFIG = "cau_hinh"
    """OUR configuration is incomplete (no API key / model / base URL); the provider was never called.
    Retrying or waiting is useless. Distinct from ``AUTH`` (key entered but rejected): fixed in another
    place and the message to the user differs."""
    RATE_LIMIT = "rate_limit"
    """429: quota or throttling. Waiting then retrying helps."""
    CONTEXT_OVERFLOW = "context_overflow"
    """Input exceeds the context window. Cutting then retrying helps."""
    AUTH = "auth"
    """401/403: wrong key or no permission. Retrying is useless."""
    TRANSIENT = "transient"
    """5xx, network blip, timeout. Retrying helps (the SDK ``maxRetries`` already does it)."""
    UNKNOWN = "unknown"
    """Not recognised. Treated like ``TRANSIENT`` (fail safe) but logged separately so it can be added."""


class AgentTurnError(Exception):
    """Raised by ``AgentEngine.run_turn`` for EVERY failure of a turn. ``safe_message`` is already trimmed to
    ids and codes (no request body, no patient text): the equivalent of ``forLog(err, 300)``."""

    def __init__(self, kind: ProviderErrorKind, safe_message: str, *, turn_id: int | None = None) -> None:
        super().__init__(f"{kind.value}: {safe_message}")
        self.kind = kind
        self.safe_message = safe_message
        self.turn_id = turn_id


@dataclass(frozen=True)
class ProviderErrorReason:
    kind: Literal["loi-provider"] = "loi-provider"
    error_kind: str = ""
    message: str = ""


@dataclass(frozen=True)
class GuardBlockReason:
    kind: Literal["guard-chan"] = "guard-chan"
    code: str = ""
    message: str = ""


@dataclass(frozen=True)
class PromptLeakReason:
    kind: Literal["chan-ro-prompt"] = "chan-ro-prompt"


type FailedTurnReason = ProviderErrorReason | GuardBlockReason | PromptLeakReason

_DESCRIPTION = {
    "loi-provider": "Lượt dừng vì lỗi từ nhà cung cấp",
    "guard-chan": "Lượt dừng vì bộ chặn vòng lặp công cụ",
    "chan-ro-prompt": "Câu trả lời bị chặn vì lộ chỉ dẫn nội bộ - KHÔNG gửi cho người dùng",
}


def failed_turn_step(reason: FailedTurnReason, attempt: int = 1) -> StepTrace:
    """A SYNTHETIC trace row for a turn that failed before running any step (``traceLuotHong``).

    Why: the trace list joins to the steps table so a turn without a trace never appears (clicking would
    show nothing). A turn that dies on the very first call (wrong key, router 404, not configured: the most
    common failure of a fresh install) has no step and would vanish from the Trace page while the Sessions
    drawer still showed it: two screens, two truths. The cure is to give the failed turn a real trace row.
    Also used for the two non-throwing cases: the loop guard stopped it, and the answer was blocked for
    leaking the system prompt.

    ``finish_reason`` carries a machine-readable code (``error:auth``, ``blocked:guard``, ...) because the
    trace card already shows that field as a chip.
    """
    if isinstance(reason, ProviderErrorReason):
        return StepTrace(
            step_number=0,
            attempt=attempt,
            text=f"{_DESCRIPTION['loi-provider']} ({reason.error_kind}): {reason.message}",
            finish_reason=f"error:{reason.error_kind}",
        )
    if isinstance(reason, GuardBlockReason):
        return StepTrace(
            step_number=0,
            attempt=attempt,
            text=f"{_DESCRIPTION['guard-chan']}: {reason.message}",
            finish_reason=f"blocked:{reason.code}",
        )
    return StepTrace(
        step_number=0,
        attempt=attempt,
        text=_DESCRIPTION["chan-ro-prompt"],
        finish_reason="blocked:prompt-leak",
    )
