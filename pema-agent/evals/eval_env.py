# ported from: evals/eval-env.ts
"""Build the environment of the eval suite: TEMPORARY settings but the REAL LLM configuration.

``setupTestEnv`` of the original deliberately forced ``LLM_PROVIDER=anthropic`` / ``LLM_API_KEY=test-key`` so
``pnpm test`` runs the same on every machine. The eval suite needs the opposite: a temporary DB so the real
``data/zalo-agent.db`` is untouched, but a model that can really be called, so it reads the real configuration
and passes it back as overrides.

The LLM configuration is read by the EXACT production rule: the DB (dashboard) over the environment, see
``read_real_llm_settings``. The DB read there is the REAL one (read-only) while the agent turns run on
in-memory settings.

Forced deviations: the temporary SQLite DIRECTORY has no counterpart (the settings snapshot is in memory and
the evals use fakes for every store, so there is nothing to clean up on disk); the overrides go into
``os.environ`` of the eval process, which is where ``get_llm_env`` and ``get_tuning`` read them, and the
returned ``restore`` puts the previous values back. ``process.loadEnvFile()`` is done by ``LlmEnv`` itself
(``env_file=".env"``).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from evals.read_real_llm_settings import SettingsLoader, doc_llm_tu_db_that
from evals.read_real_search_settings import TraCuuThat, doc_tra_cuu_tu_db_that
from pema.config import env as env_module
from pema.config.env_llm import get_llm_env


@dataclass(frozen=True)
class CauHinhLlm:
    provider: str
    model: str
    base_url: str | None = None
    tu_db: list[str] = field(default_factory=list[str])
    """Which fields came from the DB (dashboard) instead of the environment: printed so the person knows."""


@dataclass(frozen=True)
class KetQuaDungEnv:
    ok: bool
    loi: str = ""
    llm: CauHinhLlm | None = None
    tra_cuu: TraCuuThat | None = None
    restore: Callable[[], None] | None = None
    """Puts ``os.environ`` back as it was before ``dung_eval_env`` (call it in a ``finally``)."""


# Overrides applied on top of the real LLM configuration, with the reason of each (all from the original):
EVAL_TUNING_OVERRIDES: dict[str, str] = {
    # An eval turn waits for nothing: drop the send delay and the message-merge debounce
    "SEND_DELAY_MIN_MS": "0",
    "SEND_DELAY_MAX_MS": "0",
    # The trace is the DATA SOURCE of the evals (the tools called are read from it), not an optional
    # diagnostic: turned off, every assertion about tools is blind
    "AGENT_TRACE_ENABLED": "true",
    # The OUTPUT token ceiling must match production. ``setupTestEnv`` set 2048 to suit the fake model, but an
    # eval run with that number measures another system: 2048 tokens is enough to cut a long answer in the
    # middle, exactly the kind of case the persona says "MUST present in full". Worse, that combination breaks
    # the repo's own cross rule (``DOCUMENT_MAX_CHARS/4 > LLM_MAX_OUTPUT_TOKENS*0.7``), so the settings page
    # would refuse to save it: an eval must not run with a configuration the dashboard forbids.
    "LLM_MAX_OUTPUT_TOKENS": "16384",
    # A MUCH shorter turn ceiling than the default (15 minutes): the evals run by hand and in sequence, and
    # one hanging case means waiting for the whole suite. 3 minutes is still plenty for the heaviest turn here
    # (search then summarise), because the time-expensive tools such as drawing are off in the case set.
    "LLM_TURN_TIMEOUT_MS": "180000",
}


def _clear_caches() -> None:
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()


async def dung_eval_env(
    loader: SettingsLoader | None = None, encryption_key: str | None = None
) -> KetQuaDungEnv:
    # The DB OVERRIDES the environment: EXACTLY the production rule. Reading the environment alone measures a
    # different system from the one running: a model configured through the dashboard lives in the DB, while
    # the environment is only a fallback layer and often keeps an old value.
    db = await doc_llm_tu_db_that(loader, encryption_key)
    # Read the search settings from the same real source BEFORE anything else is changed
    tra_cuu = await doc_tra_cuu_tu_db_that(loader, encryption_key)
    env = get_llm_env()
    provider = db.provider or env.LLM_PROVIDER.value
    model = db.model or env.LLM_MODEL
    api_key = db.api_key or env.LLM_API_KEY
    base_url = db.base_url or env.LLM_BASE_URL or ""

    # Missing means STOP, not a half run: running on with a fake key makes every case red for a network error,
    # and the reader of the table thinks the agent is broken.
    if not api_key:
        return KetQuaDungEnv(
            ok=False,
            loi=(
                "Thiếu API key cho LLM. Bộ eval gọi MODEL THẬT nên bắt buộc phải có khóa thật -\n"
                "  nhập ở trang Providers trên dashboard, hoặc đặt LLM_API_KEY trong môi trường.\n"
                "  (Ollama chạy local không kiểm key: đặt một chuỗi bất kỳ, ví dụ LLM_API_KEY=ollama.)\n"
                "  (pytest thì không cần - nó chạy model giả.)"
            ),
        )
    if not model:
        return KetQuaDungEnv(ok=False, loi="Thiếu LLM_MODEL trong môi trường")
    if provider == "openai-compatible" and not base_url:
        return KetQuaDungEnv(ok=False, loi="LLM_PROVIDER=openai-compatible thì phải có LLM_BASE_URL")

    overrides = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "LLM_API_KEY": api_key,
        **({"LLM_BASE_URL": base_url} if base_url else {}),
        **EVAL_TUNING_OVERRIDES,
    }
    before = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    _clear_caches()

    def restore() -> None:
        for k, v in before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _clear_caches()

    return KetQuaDungEnv(
        ok=True,
        llm=CauHinhLlm(provider=provider, model=model, base_url=base_url or None, tu_db=db.tu_db),
        tra_cuu=tra_cuu,
        restore=restore,
    )
