# ported from: src/config/env.ts (the LLM and vision-sidecar part) + src/config/llm-provider-kind.ts
"""LLM and vision-sidecar settings read from the environment, under their ORIGINAL unprefixed names.

``Settings`` (``pema.config.env``, package A) holds the platform settings with the ``PEMA_`` prefix. The LLM
settings keep the names of zalo-agent (``LLM_PROVIDER``, ``LLM_BASE_URL``, ``LLM_MODEL``, ``LLM_API_KEY``,
``LLM_VISION_MODE``, ``VISION_SIDECAR_*``) because they are the DEFAULTS under the override a staff member
saves on the admin screen (``runtime_llm_settings``: DB override first, then these), and an operator who ran
zalo-agent already has them in an ``.env``. The 72 tuning parameters (``LLM_MAX_STEPS``,
``LLM_CONTEXT_WINDOW``, ``ZALO_IMAGE_QUALITY`` ...) are NOT here: their defaults and bounds live in
``tuning_specs`` and are read through ``get_tuning``.

Forced deviation: the zod ``envSchema`` becomes ``pydantic-settings``. As in the original, booting does NOT
require an LLM key, model or base URL (the dashboard must be reachable to enter them): a missing value is
reported when a turn needs it (``LoiCauHinhLlm``), not at start-up. ``LLM_BASE_URL`` and
``VISION_SIDECAR_BASE_URL`` set to an empty string mean "unset" (``emptyToUndefined``).

``LLM_PROVIDER_KINDS`` of ``llm-provider-kind.ts`` is ``pema_contracts.agents.LlmProviderKind``;
``la_goi_thang_hang`` is kept here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pema_contracts.agents import LlmProviderKind


def la_llm_provider_kind(gia_tri: object) -> bool:
    """``laLlmProviderKind``: is this value one of the supported providers."""
    return isinstance(gia_tri, str) and gia_tri in {kind.value for kind in LlmProviderKind}


def la_goi_thang_hang(provider: LlmProviderKind) -> bool:
    """``laGoiThangHang``: this provider calls the vendor DIRECTLY, not through a router proxy.

    Used to decide two things: whether a base URL is required (no: the SDK has the vendor endpoint) and
    whether to ask the router's ``/models`` for the vision ability (no: that is a router-specific API).
    """
    return provider in {LlmProviderKind.ANTHROPIC, LlmProviderKind.GOOGLE}


class LlmEnv(BaseSettings):
    """Defaults of the LLM settings (the layer under the DB override)."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore", case_sensitive=False)

    LLM_PROVIDER: LlmProviderKind = LlmProviderKind.OPENAI_COMPATIBLE
    LLM_BASE_URL: str | None = None
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    """Empty by design: guessing a default model would let a bot answer with one nobody chose (same rule as
    ``LLM_API_KEY``). A turn without a model raises ``LoiCauHinhLlm``."""

    LLM_VISION_MODE: Literal["auto", "on", "off"] = "auto"
    VISION_SIDECAR_BASE_URL: str | None = None
    VISION_SIDECAR_MODEL: str = ""
    VISION_SIDECAR_API_KEY: str = ""

    @field_validator("LLM_BASE_URL", "VISION_SIDECAR_BASE_URL", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        """``emptyToUndefined`` + ``startsWith("http")``."""
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        if isinstance(value, str) and not value.startswith("http"):
            raise ValueError("must start with http")
        return value


@lru_cache(maxsize=1)
def get_llm_env() -> LlmEnv:
    return LlmEnv()
