# ported from: src/agent/llm-provider.ts
"""Choose and build the model for a turn: agent override -> runtime settings (admin screen) -> environment.

Called every agent turn, so a change from the UI takes effect at once.

* ``openai-compatible``: OpenAI-compatible endpoint (Ollama, llama-server, vLLM, LiteLLM, OpenRouter, a
  router)
  through the base URL;
* ``anthropic``: direct call to the Anthropic API;
* ``google``: direct call to the Gemini API.

The API key and base URL ALWAYS come from the shared configuration (a per-agent key does not exist yet).

Forced deviation (Vercel AI SDK -> own loop): ``resolveLanguageModel`` returned an SDK ``LanguageModel``; here
it returns a ``pema.agent.model_types.ChatModel`` built by one of the three adapters of
``pema.agent.providers``. ``createSanitizingFetch`` (router JSON with a ``data: [DONE]`` tail) is not wired:
the adapters always stream (see ``openai_compatible``), the bug was about non-streaming responses; the port of
the sanitizer itself is ``llm_response_sanitizer``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pema.agent.cache_session_id import cache_session_headers
from pema.agent.llm_config_error import LoiCauHinhLlm
from pema.agent.model_types import ChatModel, ProviderOptions
from pema.agent.providers.anthropic_adapter import AnthropicModel
from pema.agent.providers.gemini_adapter import GeminiModel, base_url_cho_google
from pema.agent.providers.openai_compatible import OpenAICompatibleModel
from pema.agent.reasoning_options import reasoning_provider_options
from pema.config.runtime_llm_settings import get_effective_llm_settings
from pema.config.runtime_tuning_settings import get_tuning, get_tuning_bool
from pema.shared.logger import create_logger
from pema_contracts.agents import LlmProviderKind, ReasoningEffort

log = create_logger("llm-provider")

_KEY_UNREADABLE = (
    "Không giải mã được LLM API key đã lưu - khóa mã hóa (PEMA_SECRET_ENCRYPTION_KEY) có thể đã đổi so với "
    "lúc lưu. Nhập lại key ở trang Providers, và kiểm tra cả phiên đăng nhập Zalo."
)
_KEY_MISSING = (
    "Chưa cấu hình LLM API key - nhập ở trang Providers trên dashboard (hoặc LLM_API_KEY trong .env)"
)
_BASE_URL_MISSING = (
    "Chưa cấu hình base URL cho provider openai-compatible - nhập ở trang Providers trên dashboard"
)

__all__ = [
    "ModelOverride",
    "ModelOverrideLike",
    "ProviderModel",
    "ThreadSession",
    "base_url_cho_google",
    "doi_provider_an_toan",
    "model_hieu_luc",
    "resolve_language_model",
    "resolve_reasoning_effort",
    "resolve_reasoning_options",
]


class ModelOverrideLike(Protocol):
    """What an override must expose; an ``AgentProfile`` already does."""

    @property
    def model_provider(self) -> LlmProviderKind | None: ...

    @property
    def model_name(self) -> str | None: ...

    @property
    def reasoning_effort(self) -> ReasoningEffort | None: ...


@dataclass(frozen=True)
class ModelOverride:
    model_provider: LlmProviderKind | None = None
    model_name: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    """The agent's own thinking level; None = follow the shared default."""


@dataclass(frozen=True)
class ProviderModel:
    provider: LlmProviderKind
    model: str


@dataclass(frozen=True)
class ThreadSession:
    """The thread being processed, used to build a STABLE session header so a router can switch prompt caching
    on. Omitted (summariser, connection test): a one-shot call has no prefix to reuse, so no header."""

    account_id: str
    thread_id: str
    context_epoch: int = 0


def doi_provider_an_toan(base: ProviderModel, override: ModelOverrideLike | None = None) -> ProviderModel:
    """API-key leak guard: accept a provider override ONLY when it equals the shared provider.

    ``api_key`` and ``base_url`` always come from the shared configuration (a per-agent key does not exist).
    So
    an agent declaring ``model_provider="anthropic"`` while the shared configuration is a router would make
    the
    router's key go out as the ``x-api-key`` header to ``api.anthropic.com``: it leaks a credential to a third
    party AND silences the bot with a 401.

    Blocked HERE and not only in the UI or at the API edge, because this is the one place every path goes
    through: a mismatching record already in the DB (hand-edited earlier), a new route that forgot to check,
    or
    a configuration load error that left the select box unlocked.

    ``model_name`` is dropped too when the provider is refused: the name was chosen FOR the other provider
    (``claude-opus-5`` for Anthropic) and sent to a router it earns a 400. Falling back to the shared
    configuration entirely is the state that runs.
    """
    wanted = override.model_provider if override is not None else None
    if wanted is not None and wanted != base.provider:
        log.error(
            "agent declares a provider different from the shared configuration but has no key of its own: "
            "override IGNORED so the key is not sent to the wrong party; fix it on the Agents page",
            agent_provider=wanted.value,
            shared_provider=base.provider.value,
        )
        return ProviderModel(base.provider, base.model)
    name = override.model_name if override is not None else None
    return ProviderModel(wanted or base.provider, name or base.model)


def model_hieu_luc(override: ModelOverrideLike | None = None) -> ProviderModel:
    """The provider + model that REALLY run, after the unsafe override was dropped.

    Everything that needs "which model is running" must call this instead of reading
    ``override.model_provider or base.provider`` itself: that is how four places once drifted apart.
    """
    base = get_effective_llm_settings()
    return doi_provider_an_toan(ProviderModel(base.provider, base.model), override)


def resolve_reasoning_effort(override: ModelOverrideLike | None = None) -> ReasoningEffort:
    """Effective thinking level: the agent's own wins over the default of the settings page."""
    if override is not None and override.reasoning_effort is not None:
        return override.reasoning_effort
    return ReasoningEffort(str(get_tuning("LLM_REASONING_EFFORT")))


def resolve_reasoning_options(override: ModelOverrideLike | None = None) -> ProviderOptions | None:
    """``providerOptions`` that switch thinking on for the agent turn, by the provider IN EFFECT (agent
    override over runtime settings over environment: the same order as ``resolve_language_model`` so the model
    and the options never disagree).

    Goes through ``doi_provider_an_toan`` and NOT the raw override: with an agent that declares a mismatching
    provider the override is ignored in ``resolve_language_model`` and the model runs on the shared provider.
    Reading the raw override here would build options for the namespace of the provider that is NOT running,
    the real provider would ignore them silently and reasoning would be off while the UI still shows a level.
    The summariser and the connection test do not pass these options: light work, no thinking tokens to burn.
    """
    provider = model_hieu_luc(override).provider
    return reasoning_provider_options(provider, resolve_reasoning_effort(override))


def resolve_language_model(
    override: ModelOverrideLike | None = None,
    thread: ThreadSession | None = None,
    *,
    http_client: object | None = None,
) -> ChatModel:
    base = get_effective_llm_settings()
    chosen = doi_provider_an_toan(ProviderModel(base.provider, base.model), override)
    if not base.api_key:
        # A key IN the DB that fails to decrypt is a different thing from "never entered": saying the wrong
        # thing sends the user to re-enter the key when the root cause is that the encryption key changed, and
        # then the Zalo cookies are broken too.
        raise LoiCauHinhLlm("api_key", _KEY_UNREADABLE if base.api_key_hong else _KEY_MISSING)
    # Same rule as the key: a missing model is reported HERE, not at boot. Without this branch the provider
    # would receive an empty model and the user a baffling HTTP error instead of a sentence saying what to do.
    if not chosen.model:
        raise LoiCauHinhLlm(
            "model",
            "Chưa cấu hình model - nhập ở trang Providers trên dashboard (hoặc LLM_MODEL trong .env)",
        )

    headers = (
        cache_session_headers(
            get_tuning_bool("LLM_CACHE_SESSION_ENABLED"),
            thread.account_id,
            thread.thread_id,
            thread.context_epoch,
        )
        if thread is not None
        else {}
    )

    if chosen.provider is LlmProviderKind.OPENAI_COMPATIBLE:
        if not base.base_url:
            raise LoiCauHinhLlm("base_url", _BASE_URL_MISSING)
        return OpenAICompatibleModel(
            base_url=base.base_url,
            api_key=base.api_key,
            model=chosen.model,
            headers=headers,
            http_client=http_client,
        )
    if chosen.provider is LlmProviderKind.ANTHROPIC:
        # A direct call makes the session header meaningless (no router reads it), but sending it is harmless
        # and keeps the two branches uniform.
        return AnthropicModel(
            api_key=base.api_key, model=chosen.model, headers=headers, http_client=http_client
        )
    # google: see gemini_adapter for why it must NOT go through the OpenAI shim. An empty base URL lets the
    # SDK
    # use the vendor endpoint; see ``base_url_cho_google``.
    return GeminiModel(api_key=base.api_key, model=chosen.model, base_url=base.base_url, headers=headers)
