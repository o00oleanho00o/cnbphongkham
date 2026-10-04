# ported from: src/conversation/thread-summarizer.ts (``chayTomTat``)
"""The real ``pema_contracts.agent_turn.TextGenerator``: one single-shot completion (no tools) over the
configured provider. Used by the thread summariser (package D2: ``pema.conversation.thread_summarizer``
receives it through the ``TextGenerator`` seam) and anywhere a plain prompt-to-text call is needed.

What the original did and is kept:

* ``resolveLanguageModel()`` WITHOUT a thread: a one-shot call has no prefix to reuse, so no session header;
  WITHOUT reasoning options: light work, no thinking tokens to burn;
* ``streamText`` through ``chayStream`` and not ``generateText``: every LLM call of the project streams on the
  wire (the 100 s first-byte limit of the proxy, see ``stream_text_result``);
* ``maxRetries: 1`` (one retry of a retryable error, not the 2 of an agent turn), ``maxOutputTokens: 1024``;
* ``truncated`` = the model hit ``max_output_tokens`` (``finish_reason`` "length"): the summariser must NOT
  store a cut summary.

How to wire it (package G): ``ProviderTextGenerator()`` needs no argument in production. It reads the LLM
settings of the installation (the ``runtime_settings_store`` snapshot). Tests pass a ``resolve_model``
returning a fake model.

The only exception it raises is ``AgentTurnError`` (the kind classified, the provider exception in
``__cause__``), like the engine, so the caller never imports an SDK type.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pema.agent.llm_provider import ModelOverrideLike, ThreadSession, resolve_language_model
from pema.agent.model_types import ChatModel
from pema.agent.safe_turn_error import to_turn_error
from pema.agent.stream_text_result import chay_stream
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import GeneratedText
from pema_contracts.turn_errors import AgentTurnError

log = create_logger("text-generator")

DEFAULT_MAX_OUTPUT_TOKENS = 1024
"""``maxOutputTokens: 1024`` of ``chayTomTat``."""


def _default_resolver(override: ModelOverrideLike | None, thread: ThreadSession | None) -> ChatModel:
    return resolve_language_model(override, thread)


class ProviderTextGenerator:
    def __init__(
        self,
        *,
        resolve_model: Callable[[ModelOverrideLike | None, ThreadSession | None], ChatModel] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_initial_delay_s: float = 2.0,
    ) -> None:
        self._resolve: Callable[[ModelOverrideLike | None, ThreadSession | None], ChatModel] = (
            resolve_model or _default_resolver
        )
        self._sleep = sleep
        self._retry_initial_delay_s = retry_initial_delay_s

    async def generate_text(self, prompt: str, *, max_output_tokens: int | None = None) -> GeneratedText:
        try:
            result = await chay_stream(
                model=self._resolve(None, None),
                system="",
                messages=[{"role": "user", "content": prompt}],
                max_output_tokens=max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
                max_retries=1,
                timeout_s=get_tuning_int("LLM_TURN_TIMEOUT_MS") / 1000,
                sleep=self._sleep,
                retry_initial_delay_s=self._retry_initial_delay_s,
                on_attempt_error=lambda err: log.warning("model call failed while generating text", err=err),
            )
        except AgentTurnError:
            raise
        except Exception as err:
            raise to_turn_error(err) from err
        return GeneratedText(text=result.text, truncated=result.finish_reason == "length")
