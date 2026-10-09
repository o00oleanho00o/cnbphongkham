"""Model settings an admin changes at runtime (dashboard or ``agent model``): stored per (tenant, agent),
resolved field by field as database > profile, applied to the next model call without a restart.

The API key is stored only in the database, encrypted with the service's secret key (AES-256-GCM, package
``secretcipher``; the key file lives in the service's home folder, see ``agent_app.home``), and never leaves
the service: reads show it masked. A stored key that no longer decrypts (the key file was replaced) is
reported as broken and no key is used.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Literal, cast

from cryptography.exceptions import InvalidTag
from sqlalchemy import text as sql

from agent_app.model_factory import ModelSettings, Provider, client_for, resolve_model_settings
from agent_app.profile import Profile
from agent_app.storage import AgentDatabase, retrying
from agentcore import (
    AssistantResult,
    LlmRequest,
    Message,
    ModelClient,
    ModelError,
    ReasoningEffort,
    StreamSink,
)
from agentcore.harness.model.reasoning import OpenAIDialect
from secretcipher import decrypt_with, encrypt_with, mask_secret

SECRET_KEY_ENV: Final = "AGENT_SECRET_ENCRYPTION_KEY"  # noqa: S105 - a setting's name, not a key
"""The service setting holding the secret key; the CLI fills it from the home folder, not the environment."""
REFRESH_S: Final = 5.0
TEST_TIMEOUT_S: Final = 30.0
SETTING_FIELDS: Final = ("provider", "model", "base_url", "reasoning", "dialect")
NO_SECRET_KEY: Final = "the service has no secret key (agent serve creates one in its home folder)"  # noqa: S105

FieldSource = Literal["db", "profile", "unset"]
ClientFactory = Callable[[ModelSettings], ModelClient]

logger = logging.getLogger(__name__)


class SecretKeyMissingError(RuntimeError):
    """A secret cannot be stored or read without the service's secret key."""


@dataclass(frozen=True, slots=True)
class StoredModelSettings:
    """What an admin stored; None leaves the field to the profile."""

    provider: Provider | None = None
    model: str | None = None
    base_url: str | None = None
    reasoning: ReasoningEffort | None = None
    dialect: OpenAIDialect | None = None
    api_key_enc: str | None = None
    version: int = 0

    @property
    def empty(self) -> bool:
        return all(getattr(self, name) is None for name in (*SETTING_FIELDS, "api_key_enc"))


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    settings: ModelSettings
    sources: Mapping[str, FieldSource]
    api_key_broken: bool
    version: int


def resolve_effective(
    profile: Profile, stored: StoredModelSettings | None, secret_key: str | None
) -> ResolvedModel:
    base = resolve_model_settings(profile)
    stored = stored or StoredModelSettings()
    sources: dict[str, FieldSource] = {}
    changes: dict[str, Any] = {}
    for name in SETTING_FIELDS:
        value = getattr(stored, name)
        if value is not None:
            changes[name] = value
            sources[name] = "db"
        else:
            sources[name] = "profile"
    api_key, broken = _api_key(stored, secret_key)
    sources["api_key"] = "db" if api_key else "unset"
    settings = replace(base, api_key=api_key, **changes)
    return ResolvedModel(settings=settings, sources=sources, api_key_broken=broken, version=stored.version)


def _api_key(stored: StoredModelSettings, secret_key: str | None) -> tuple[str, bool]:
    if stored.api_key_enc is None:
        return "", False
    if secret_key is None:
        logger.warning("a stored API key cannot be read: %s", NO_SECRET_KEY)
        return "", True
    try:
        return decrypt_with(secret_key, stored.api_key_enc), False
    except (InvalidTag, ValueError):
        logger.warning("the stored API key does not decrypt (was the secret key file replaced?)")
        return "", True


class InMemoryModelSettingsStore:
    def __init__(self) -> None:
        self._rows: dict[str, StoredModelSettings] = {}

    async def get(self, tenant_id: str) -> StoredModelSettings | None:
        return self._rows.get(tenant_id)

    async def version(self, tenant_id: str) -> int:
        row = self._rows.get(tenant_id)
        return 0 if row is None else row.version

    async def save(self, tenant_id: str, settings: StoredModelSettings) -> StoredModelSettings:
        saved = replace(settings, version=await self.version(tenant_id) + 1)
        self._rows[tenant_id] = saved
        return saved


_GET = sql(
    "SELECT provider, model, base_url, reasoning, dialect, api_key_enc, version "
    "FROM agent_rt.agent_model_settings WHERE tenant_id = :tenant_id AND agent = :agent"
)
_VERSION = sql(
    "SELECT version FROM agent_rt.agent_model_settings WHERE tenant_id = :tenant_id AND agent = :agent"
)
_SAVE = sql(
    "INSERT INTO agent_rt.agent_model_settings (tenant_id, agent, provider, model, base_url, reasoning, "
    "dialect, api_key_enc) VALUES (:tenant_id, :agent, :provider, :model, :base_url, :reasoning, :dialect, "
    ":api_key_enc) ON CONFLICT (tenant_id, agent) DO UPDATE SET provider = EXCLUDED.provider, "
    "model = EXCLUDED.model, base_url = EXCLUDED.base_url, reasoning = EXCLUDED.reasoning, "
    "dialect = EXCLUDED.dialect, "
    "api_key_enc = EXCLUDED.api_key_enc, version = agent_rt.agent_model_settings.version + 1, "
    "updated_at = now() RETURNING version"
)


class PostgresModelSettingsStore:
    """A clear keeps the row with every field NULL, so the version never goes back to a value a running
    service may have cached."""

    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    async def get(self, tenant_id: str) -> StoredModelSettings | None:
        async def work() -> StoredModelSettings | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_GET, {"tenant_id": tenant_id, "agent": self._agent})).one_or_none()
            if row is None:
                return None
            return StoredModelSettings(
                provider=row.provider,
                model=row.model,
                base_url=row.base_url,
                reasoning=row.reasoning,
                dialect=row.dialect,
                api_key_enc=row.api_key_enc,
                version=row.version,
            )

        return await retrying("load model settings", work)

    async def version(self, tenant_id: str) -> int:
        async def work() -> int:
            async with self._engine.connect() as conn:
                found = await conn.execute(_VERSION, {"tenant_id": tenant_id, "agent": self._agent})
                return found.scalar_one_or_none() or 0

        return await retrying("model settings version", work)

    async def save(self, tenant_id: str, settings: StoredModelSettings) -> StoredModelSettings:
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            **{name: getattr(settings, name) for name in (*SETTING_FIELDS, "api_key_enc")},
        }

        async def work() -> StoredModelSettings:
            async with self._engine.begin() as conn:
                version = (await conn.execute(_SAVE, params)).scalar_one()
            return replace(settings, version=version)

        return await retrying("save model settings", work)


ModelSettingsStore = InMemoryModelSettingsStore | PostgresModelSettingsStore


class DynamicModel:
    """The agent's model client. Before a call it checks the stored settings' version (at most every
    ``refresh_s``) and rebuilds the client when they changed. A request that leaves the reasoning effort to
    the default gets the configured one; an explicit one (the summariser asks for ``off``) is kept."""

    def __init__(
        self,
        profile: Profile,
        store: ModelSettingsStore,
        *,
        tenant_id: str,
        secret_key: str | None,
        factory: ClientFactory = client_for,
        refresh_s: float = REFRESH_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._profile = profile
        self._store = store
        self._tenant_id = tenant_id
        self._secret_key = secret_key
        self._factory = factory
        self._refresh_s = refresh_s
        self._clock = clock
        self._checked = -math.inf
        self._resolved: ResolvedModel | None = None
        self._client: ModelClient | None = None
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        if self._resolved is not None:
            return self._resolved.settings.model
        return resolve_model_settings(self._profile).model

    def invalidate(self) -> None:
        self._checked = -math.inf

    async def current(self) -> ResolvedModel:
        async with self._lock:
            if self._resolved is not None and self._clock() - self._checked < self._refresh_s:
                return self._resolved
            version = await self._store.version(self._tenant_id)
            if self._resolved is None or version != self._resolved.version:
                stored = await self._store.get(self._tenant_id)
                resolved = resolve_effective(self._profile, stored, self._secret_key)
                if self._resolved is not None:
                    logger.info("model settings version %d in effect", resolved.version)
                self._resolved, self._client = resolved, None
            self._checked = self._clock()
            return self._resolved

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        resolved = await self.current()
        if self._client is None:
            self._client = self._factory(resolved.settings)
        if request.reasoning is None and resolved.settings.reasoning is not None:
            request = request.model_copy(update={"reasoning": resolved.settings.reasoning})
        return await self._client.complete(request, sink=sink)


class ModelAdmin:
    """What the admin endpoints and ``agent model`` do: show, change, clear and test the model settings."""

    def __init__(
        self,
        profile: Profile,
        store: ModelSettingsStore,
        *,
        tenant_id: str,
        secret_key: str | None,
        dynamic: DynamicModel | None = None,
        factory: ClientFactory = client_for,
    ) -> None:
        self._profile = profile
        self._store = store
        self._tenant_id = tenant_id
        self._secret_key = secret_key
        self._dynamic = dynamic
        self._factory = factory

    async def resolved(self) -> ResolvedModel:
        stored = await self._store.get(self._tenant_id)
        return resolve_effective(self._profile, stored, self._secret_key)

    async def show(self) -> dict[str, Any]:
        stored = await self._store.get(self._tenant_id)
        resolved = resolve_effective(self._profile, stored, self._secret_key)
        settings = resolved.settings
        return {
            "provider": settings.provider,
            "model": settings.model,
            "base_url": settings.base_url,
            "reasoning": settings.reasoning,
            "dialect": settings.dialect,
            "api_key": mask_secret(settings.api_key),
            "api_key_broken": resolved.api_key_broken,
            "sources": dict(resolved.sources),
            "stored": stored is not None and not stored.empty,
            "version": resolved.version,
        }

    async def update(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        """``changes`` holds only the fields to change: a value sets it, None clears it (back to the profile).
        ``api_key``: a non-empty value is stored encrypted, "" keeps the stored one, None removes it."""
        current = await self._store.get(self._tenant_id) or StoredModelSettings()
        updates: dict[str, Any] = {name: changes[name] for name in SETTING_FIELDS if name in changes}
        if "api_key" in changes:
            key = cast(str | None, changes["api_key"])
            if key is None:
                updates["api_key_enc"] = None
            elif key:
                if self._secret_key is None:
                    raise SecretKeyMissingError(NO_SECRET_KEY)
                updates["api_key_enc"] = encrypt_with(self._secret_key, key)
        await self._save(replace(current, **updates), [*updates])
        return await self.show()

    async def clear(self) -> dict[str, Any]:
        current = await self._store.get(self._tenant_id) or StoredModelSettings()
        await self._save(StoredModelSettings(version=current.version), ["all"])
        return await self.show()

    async def test(self) -> dict[str, Any]:
        """One tiny call with the effective settings and reasoning off; never stores anything."""
        resolved = await self.resolved()
        request = LlmRequest(
            system="Reply with the single word OK.",
            messages=[Message.user("ping")],
            max_output_tokens=16,
            reasoning="off",
        )
        started = time.perf_counter()
        try:
            client = self._factory(resolved.settings)
            await asyncio.wait_for(client.complete(request), timeout=TEST_TIMEOUT_S)
        except ModelError as err:
            return {"ok": False, "model": resolved.settings.model, "error_kind": err.kind}
        except TimeoutError:
            return {"ok": False, "model": resolved.settings.model, "error_kind": "timeout"}
        latency_ms = round((time.perf_counter() - started) * 1000)
        return {"ok": True, "model": resolved.settings.model, "latency_ms": latency_ms}

    async def _save(self, settings: StoredModelSettings, changed: list[str]) -> None:
        saved = await self._store.save(self._tenant_id, settings)
        # Names only: values (above all the key) never reach the log.
        logger.info("model settings changed (version %d): %s", saved.version, ", ".join(changed) or "nothing")
        if self._dynamic is not None:
            self._dynamic.invalidate()
