"""Plugins managed at runtime: an admin enables, disables, configures, installs and removes them; the choice
is stored per (tenant, agent) and every process of the agent follows it.

What runs is reconciled with what is stored: a stored row decides for its plugin, otherwise the profile's
``[plugins] enabled`` does. A managed plugin that fails to load is switched off and the error is stored; the
service keeps running. Each process looks for changes at most every ``refresh_s`` (before a turn), so one
made through another process applies within a few seconds. Installed plugins live in ``AGENT_PLUGIN_DIR``,
which every process of the agent must share.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, Literal, cast

from cryptography.exceptions import InvalidTag

from agent_app.live import LiveAgent
from agent_app.model_settings import SECRET_KEY_ENV, SecretKeyMissingError
from agent_app.plugins.install import PluginInstaller, Staged
from agent_app.plugins.manifest import (
    ConfigField,
    Discovery,
    PluginError,
    PluginOrigin,
    PluginSource,
    discover,
)
from agent_app.plugins.state import PluginState, PluginStateStore
from agent_app.profile import Profile
from secretcipher import decrypt_with, encrypt_with, mask_secret

REFRESH_S: Final = 5.0
MAX_STRING_SETTING: Final = 4000
MAX_ERROR_CHARS: Final = 4000

SettingSource = Literal["admin", "profile", "default"]
Roots = Callable[[], list[tuple[PluginOrigin, Path]]]

logger = logging.getLogger(__name__)


class PluginNotFoundError(PluginError):
    pass


class PluginManager:
    def __init__(
        self,
        live: LiveAgent,
        store: PluginStateStore,
        *,
        profile: Profile,
        roots: Roots,
        tenant_id: str,
        secret_key: str | None,
        installer: PluginInstaller | None = None,
        refresh_s: float = REFRESH_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._live = live
        self._store = store
        self._profile = profile
        self._roots = roots
        self._tenant_id = tenant_id
        self._secret_key = secret_key
        self._installer = installer
        self._refresh_s = refresh_s
        self._clock = clock
        self._lock = asyncio.Lock()
        self._checked = -math.inf
        self._seen: str | None = None
        self._broken: Mapping[str, str] = {}
        # Profile plugins enabled at start count as applied without a stored row.
        self._applied = {name: _fingerprint(None) for name in live.host.enabled()}

    @property
    def can_install(self) -> bool:
        return self._installer is not None

    async def start(self) -> None:
        await self.refresh(force=True)

    async def refresh(self, *, force: bool = False) -> None:
        """Applies stored changes made since the last look (at most every ``refresh_s`` unless forced)."""
        if not force and self._clock() - self._checked < self._refresh_s:
            return
        async with self._lock:
            seen = await self._store.fingerprint(self._tenant_id)
            if force or seen != self._seen:
                await self._reconcile()
                self._seen = await self._store.fingerprint(self._tenant_id)
            self._checked = self._clock()

    # --- reading ---

    async def list(self) -> dict[str, Any]:
        rows = {row.name: row for row in await self._store.list(self._tenant_id)}
        sources = self._live.host.sources
        return {
            "plugins": [self._describe(source, rows.get(name)) for name, source in sorted(sources.items())],
            "broken": dict(self._broken),
            "can_install": self.can_install,
        }

    async def show(self, name: str) -> dict[str, Any]:
        return self._describe(self._source(name), await self._store.get(self._tenant_id, name))

    # --- changing ---

    async def enable(self, name: str, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Stores the plugin as enabled (with any setting changes) and loads it; a load error switches it
        off again, is stored and raised."""
        return await self._change(name, settings or {}, enabled=True)

    async def disable(self, name: str) -> dict[str, Any]:
        return await self._change(name, {}, enabled=False)

    async def configure(self, name: str, settings: Mapping[str, Any]) -> dict[str, Any]:
        """Changes settings: a value sets one, None gives it back to the profile or the default; for a
        sensitive one "" keeps the stored value. An enabled plugin is reloaded with them."""
        return await self._change(name, settings, enabled=None)

    async def install_folder(self, path: Path, *, enable: bool = False) -> dict[str, Any]:
        installer = self._need_installer()
        return await self._install(lambda: installer.stage_folder(path), enable=enable)

    async def install_zip(self, data: bytes, *, enable: bool = False) -> dict[str, Any]:
        installer = self._need_installer()
        return await self._install(lambda: installer.stage_zip(data), enable=enable)

    async def install_git(self, url: str, ref: str | None = None, *, enable: bool = False) -> dict[str, Any]:
        installer = self._need_installer()
        return await self._install(lambda: installer.stage_git(url, ref), enable=enable)

    async def uninstall(self, name: str) -> None:
        installer = self._need_installer()
        async with self._lock:
            source = self._source(name)
            if source.origin != "installed":
                raise PluginError(name, f"a {source.origin} plugin cannot be uninstalled; disable it instead")
            self._unload(name)
            await asyncio.to_thread(installer.uninstall, name)
            await self._store.delete(self._tenant_id, name)
            self._rediscover()
            self._seen = await self._store.fingerprint(self._tenant_id)
        logger.info("plugin %s uninstalled", name)

    # --- internals ---

    async def _change(
        self, name: str, settings: Mapping[str, Any], *, enabled: bool | None
    ) -> dict[str, Any]:
        async with self._lock:
            source = self._source(name)
            row = await self._store.get(self._tenant_id, name) or PluginState(
                name, enabled=name in self._profile.plugins.enabled
            )
            row = self._with_settings(source, row, settings)
            row = replace(row, enabled=row.enabled if enabled is None else enabled, error=None)
            await self._store.save(self._tenant_id, row)
            error = await self._apply(source, row, reload=bool(settings))
            self._seen = await self._store.fingerprint(self._tenant_id)
            stored = await self._store.get(self._tenant_id, name)
        logger.info("plugin %s %s", name, "enabled" if self._is_loaded(name) else "disabled")
        if error is not None:
            raise error
        return self._describe(source, stored)

    async def _install(self, stage: Callable[[], Staged], *, enable: bool) -> dict[str, Any]:
        installer = self._need_installer()
        async with self._lock:
            staged = await asyncio.to_thread(stage)
            name = staged.manifest.name
            try:
                known = self._live.host.sources.get(name)
                if known is not None and known.origin != "installed":
                    raise PluginError(name, f"a {known.origin} plugin has this name")
                await asyncio.to_thread(installer.install_requirements, staged)
            except BaseException:
                installer.discard(staged)
                raise
            self._unload(name)
            await asyncio.to_thread(installer.commit, staged)
            row = await self._store.get(self._tenant_id, name) or PluginState(name)
            row = replace(row, enabled=row.enabled or enable, install=staged.install, error=None)
            await self._store.save(self._tenant_id, row)
            self._rediscover()
            source = self._source(name)
            error = await self._apply(source, row, reload=True)
            self._seen = await self._store.fingerprint(self._tenant_id)
            stored = await self._store.get(self._tenant_id, name)
        logger.info("plugin %s %s installed (%s)", name, staged.manifest.version, staged.install["kind"])
        shown = self._describe(source, stored)
        if error is not None:
            shown["error"] = str(error)
        return shown

    async def _reconcile(self) -> None:
        self._rediscover()
        rows = {row.name: row for row in await self._store.list(self._tenant_id)}
        sources = self._live.host.sources
        for name in [n for n in self._live.host.enabled() if n not in sources]:
            self._unload(name)
        for name, source in sorted(sources.items()):
            await self._apply(source, rows.get(name), reload=False)

    async def _apply(
        self, source: PluginSource, row: PluginState | None, *, reload: bool
    ) -> PluginError | None:
        """Loads or unloads the plugin as stored; a load error is stored (the plugin switched off) and
        returned."""
        name = source.name
        want = row.enabled if row is not None else name in self._profile.plugins.enabled
        key = _fingerprint(row)
        if self._is_loaded(name) and (not want or reload or self._applied.get(name) != key):
            self._unload(name)
        if not want or self._is_loaded(name):
            return None
        try:
            self._live.enable(name, self._config(source, row))
        except PluginError as err:
            logger.warning("plugin %s switched off: %s", name, err)
            failed = replace(row or PluginState(name), enabled=False, error=str(err)[:MAX_ERROR_CHARS])
            await self._store.save(self._tenant_id, failed)
            return err
        self._applied[name] = key
        return None

    def _unload(self, name: str) -> None:
        self._live.disable(name)
        self._applied.pop(name, None)

    def _is_loaded(self, name: str) -> bool:
        return name in self._live.host.enabled()

    def _rediscover(self) -> None:
        found: Discovery = discover(self._roots())
        self._live.host.set_sources(found.plugins)
        self._broken = found.broken

    def _source(self, name: str) -> PluginSource:
        source = self._live.host.sources.get(name)
        if source is None:
            reason = self._broken.get(name)
            raise PluginNotFoundError(name, reason or "not found")
        return source

    def _need_installer(self) -> PluginInstaller:
        if self._installer is None:
            raise PluginError("install", "set AGENT_PLUGIN_DIR to the folder installed plugins live in")
        return self._installer

    def _config(self, source: PluginSource, row: PluginState | None) -> dict[str, Any]:
        config = {**self._profile.plugins.config(source.name)}
        if row is not None:
            config.update(row.config)
            config.update(self._secrets(source.name, row))
        return config

    def _secrets(self, name: str, row: PluginState) -> dict[str, Any]:
        if row.secrets_enc is None:
            return {}
        if self._secret_key is None:
            raise PluginError(name, f"its stored secret settings need {SECRET_KEY_ENV}")
        try:
            return cast(dict[str, Any], json.loads(decrypt_with(self._secret_key, row.secrets_enc)))
        except (InvalidTag, ValueError) as err:
            raise PluginError(
                name, f"its stored secret settings do not decrypt (was {SECRET_KEY_ENV} changed?)"
            ) from err

    def _with_settings(
        self, source: PluginSource, row: PluginState, changes: Mapping[str, Any]
    ) -> PluginState:
        if not changes:
            return row
        fields = source.manifest.user_config
        unknown = sorted(key for key in changes if key not in fields)
        if unknown:
            raise PluginError(source.name, f"unknown setting(s): {', '.join(unknown)}")
        config = dict(row.config)
        secrets: dict[str, Any] | None = None
        for key, value in changes.items():
            spec = fields[key]
            if spec.sensitive:
                if value == "":
                    continue
                secrets = self._secrets(source.name, row) if secrets is None else secrets
                if value is None:
                    secrets.pop(key, None)
                else:
                    secrets[key] = _checked(source.name, key, spec, value)
            elif value is None:
                config.pop(key, None)
            else:
                config[key] = _checked(source.name, key, spec, value)
        if secrets is None:
            return replace(row, config=config)
        if not secrets:
            return replace(row, config=config, secrets_enc=None)
        if self._secret_key is None:
            raise SecretKeyMissingError(f"set {SECRET_KEY_ENV} (64 hex characters) to store a secret setting")
        return replace(row, config=config, secrets_enc=encrypt_with(self._secret_key, json.dumps(secrets)))

    def _describe(self, source: PluginSource, row: PluginState | None) -> dict[str, Any]:
        manifest = source.manifest
        status = next(s for s in self._live.host.status() if s.name == source.name)
        profile_config = self._profile.plugins.config(source.name)
        secrets: dict[str, Any] = {}
        secrets_unreadable = False
        if row is not None:
            try:
                secrets = self._secrets(source.name, row)
            except PluginError:
                secrets_unreadable = True
        settings: list[dict[str, Any]] = []
        for key, spec in manifest.user_config.items():
            value, origin = _setting(key, spec, row, secrets, profile_config)
            shown: Any = value
            if spec.sensitive and value is not None:
                shown = mask_secret(str(value))
            settings.append(
                {
                    "key": key,
                    "type": spec.type,
                    "title": spec.title,
                    "description": spec.description,
                    "required": spec.required,
                    "sensitive": spec.sensitive,
                    "default": None if spec.sensitive else spec.default,
                    "value": shown,
                    "source": origin,
                }
            )
        return {
            "name": source.name,
            "version": manifest.version,
            "description": manifest.description,
            "origin": source.origin,
            "enabled": status.enabled,
            "managed_by": "admin"
            if row is not None
            else ("profile" if source.name in self._profile.plugins.enabled else None),
            "error": row.error if row is not None else None,
            "install": dict(row.install) if row is not None and row.install is not None else None,
            "tools": list(status.tools),
            "sections": list(status.sections),
            "hooks": list(status.hooks),
            "requires": list(manifest.requires),
            "requires_env": list(manifest.requires_env),
            "settings": settings,
            "secrets_unreadable": secrets_unreadable,
        }


def _setting(
    key: str,
    spec: ConfigField,
    row: PluginState | None,
    secrets: Mapping[str, Any],
    profile_config: Mapping[str, Any],
) -> tuple[Any, SettingSource | None]:
    if key in secrets:
        return secrets[key], "admin"
    if row is not None and key in row.config:
        return row.config[key], "admin"
    if key in profile_config:
        return profile_config[key], "profile"
    if spec.default is not None:
        return spec.default, "default"
    return None, None


def _checked(plugin: str, key: str, spec: ConfigField, value: Any) -> Any:
    ok = {
        "string": isinstance(value, str) and len(value) <= MAX_STRING_SETTING,
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[spec.type]
    if not ok:
        raise PluginError(plugin, f"setting {key} must be a {spec.type}")
    return value


def _fingerprint(row: PluginState | None) -> str:
    """What a loaded plugin was loaded with; a stored change to it means a reload."""
    if row is None:
        return ""
    data = {"config": dict(row.config), "secrets": row.secrets_enc, "install": row.install}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest()
