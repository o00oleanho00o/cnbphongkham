# ported from: src/agent/reasoning-options.ts
"""Turn "thinking" on for the agent turn: ONE place decides the thinking parameters for every call path,
mapped to the provider in effect (the ``resolve_reasoning_config`` chokepoint of Hermes).

Why it exists: without thinking the model reads 50k tokens of web page in one skimming pass (pipe-separated
number tables, matching each lottery ticket tail...), all of which need step-by-step thought. In the
lottery-check case the data WAS in the context (51k input tokens) and the model still concluded "could not
fetch the table": a missing thinking step, not missing data.

Forced deviation: the Vercel ``providerOptions`` structure (``{provider: {key: json}}``) is kept as a plain
dict (``ProviderOptions``) because it is what the adapters in ``pema.agent.providers`` read.

Pure module (no env) so tests need no setup.
"""

from __future__ import annotations

from typing import Any, Literal

from pema.agent.model_types import ProviderOptions
from pema_contracts.agents import LlmProviderKind, ReasoningEffort

ROUTER_PROVIDER_OPTIONS_KEY = "llmRouter"
"""Same as the ``name`` the original passed to ``createOpenAICompatible``. MUST be camelCase: the SDK converts
the provider name to camelCase and compares, and a kebab-case key printed a deprecation warning on EVERY
request. Here the OpenAI-compatible adapter reads exactly this key; a mismatch silently drops the options."""


def muc_nghi_cua_google(effort: ReasoningEffort) -> Literal["minimal", "low", "medium", "high"]:
    """Gemini has only 4 thinking levels: minimal / low / medium / high.

    "off" becomes "minimal" and the parameter is NOT dropped: Gemini 3 cannot switch thinking off entirely,
    and omitting the parameter lets the model choose, exactly what "off" wants to avoid. "xhigh" drops to
    "high" (no higher level); silently lowering the level beats sending an unknown value and eating a 400 for
    the whole turn.
    """
    if effort is ReasoningEffort.OFF:
        return "minimal"
    if effort is ReasoningEffort.XHIGH:
        return "high"
    return effort.value  # type: ignore[return-value]  # low | medium | high by exclusion above


def reasoning_provider_options(provider: LlmProviderKind, effort: ReasoningEffort) -> ProviderOptions | None:
    """``providerOptions`` for the agent turn by provider + effort.

    * openai-compatible: the standard OpenAI ``reasoning_effort`` (a router passes it on upstream). "off"
      omits the parameter (every router has its own "off" value; omitting is the safest).
    * anthropic direct: adaptive thinking + effort (Claude 4.6+/5); "off" disables thinking explicitly.
    * google: ``thinkingConfig.thinkingLevel``.
    """
    if provider is LlmProviderKind.ANTHROPIC:
        if effort is ReasoningEffort.OFF:
            return {"anthropic": {"thinking": {"type": "disabled"}}}
        extra: dict[str, Any] = {"thinking": {"type": "adaptive"}, "effort": effort.value}
        return {"anthropic": extra}

    if provider is LlmProviderKind.GOOGLE:
        return {"google": {"thinkingConfig": {"thinkingLevel": muc_nghi_cua_google(effort)}}}

    if effort is ReasoningEffort.OFF:
        return None
    return {ROUTER_PROVIDER_OPTIONS_KEY: {"reasoningEffort": effort.value}}
