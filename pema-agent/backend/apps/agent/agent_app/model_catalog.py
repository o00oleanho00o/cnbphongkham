"""The models a provider offers, asked from its own API (``GET /models``) with the same SDK and base URL the
agent calls it with, so the dashboard can list them next to a free text field. Nothing is stored or logged;
the key is used for this one call.

A provider that needs no key to list (OpenRouter, a local Ollama) is asked with a placeholder key, because
the SDKs refuse to start without one.
"""

from __future__ import annotations

from typing import Final

import anthropic
import openai
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from agent_app.model_factory import ModelSettings
from agentcore import ModelError
from agentcore.harness.model.anthropic import classify_anthropic_error
from agentcore.harness.model.openai_compat import classify_openai_error

LIST_TIMEOUT_S: Final = 15.0
NO_KEY: Final = "none"
ANTHROPIC_PAGE: Final = 1000


async def list_models(settings: ModelSettings) -> list[str]:
    """Model ids of the provider, sorted; raises ``ModelError`` (``auth``, ``transient``...) on a refusal."""
    key = settings.api_key or NO_KEY
    base_url = settings.base_url or None
    if settings.provider == "anthropic":
        client = AsyncAnthropic(api_key=key, base_url=base_url, timeout=LIST_TIMEOUT_S, max_retries=0)
        try:
            page = await client.models.list(limit=ANTHROPIC_PAGE)
        except anthropic.APIError as err:
            raise classify_anthropic_error(err) from err
        finally:
            await client.close()
        return sorted({model.id for model in page.data})
    client_openai = AsyncOpenAI(api_key=key, base_url=base_url, timeout=LIST_TIMEOUT_S, max_retries=0)
    try:
        listing = await client_openai.models.list()
    except openai.APIError as err:
        raise classify_openai_error(err) from err
    finally:
        await client_openai.close()
    return sorted({model.id for model in listing.data})


__all__ = ["ModelError", "list_models"]
