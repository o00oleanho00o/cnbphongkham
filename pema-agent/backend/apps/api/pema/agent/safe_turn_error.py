# ported from: src/agent/provider-error-classifier.ts + failed-turn-trace.ts (how a failure is reported)
"""Turn ANY exception of a model call into the ONE exception the engine raises, ``AgentTurnError``.

The kind is classified here (``phan_loai_loi_provider``, the SDK-specific part) so a consumer reads only
``error.kind``. ``safe_message`` is the ``forLog(err, 300)`` of the original: the exception type, the HTTP
code and the first 300 characters of the message, never the request body (which carries the prompt, i.e.
patient text). The original exception stays in ``__cause__`` for the safe error serializer of the logger.
"""

from __future__ import annotations

from pema.agent.agent_step_observer import for_log
from pema.agent.provider_error_classifier import ma_http_cua, phan_loai_loi_provider
from pema_contracts.turn_errors import AgentTurnError


def to_turn_error(err: BaseException, *, turn_id: int | None = None) -> AgentTurnError:
    """Build the ``AgentTurnError`` for ``err`` (raise it ``from err``)."""
    code = ma_http_cua(err)
    http = f" http {code}" if code is not None else ""
    return AgentTurnError(
        phan_loai_loi_provider(err),
        f"{type(err).__name__}{http}: {for_log(str(err), 300)}",
        turn_id=turn_id,
    )
