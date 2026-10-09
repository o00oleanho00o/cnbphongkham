"""Plugin manifests (``plugin.toml`` or ``plugin.yaml``) and where plugins are found.

The manifest is read leniently: only ``name`` is required and unknown keys are ignored, so a plugin written
for a later version still loads. ``user_config`` describes the settings a plugin takes, enough for a form to
be drawn from it; a ``sensitive`` field holds a secret.
"""

from __future__ import annotations

import logging
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PLUGIN_API: Final = 1
TOML_MANIFEST: Final = "plugin.toml"
YAML_MANIFESTS: Final = ("plugin.yaml", "plugin.yml")
NAME_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

PluginOrigin = Literal["bundled", "agent", "installed"]

logger = logging.getLogger(__name__)


class PluginError(ValueError):
    """A plugin cannot be found, read or loaded; the message names it."""

    def __init__(self, plugin: str, message: str) -> None:
        super().__init__(f"plugin {plugin}: {message}")
        self.plugin = plugin


class ConfigField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["string", "number", "integer", "boolean"] = "string"
    title: str = ""
    description: str = ""
    default: Any = None
    required: bool = False
    sensitive: bool = False
    """A secret: stored encrypted and never shown in full."""


class UiSpec(BaseModel):
    """The plugin's browser half: built files the gateway serves, open, at ``/ui/<plugin>/``."""

    model_config = ConfigDict(extra="ignore")

    dir: str = "ui/dist"
    entry: str | None = None
    """A script in ``dir`` the dashboard loads once signed in; it adds the plugin's pages."""
    styles: list[str] = Field(default_factory=list[str])
    home: bool = False
    """Its ``index.html`` is the dashboard itself: ``/`` leads there."""

    @field_validator("dir", "entry")
    @classmethod
    def _relative(cls, value: str | None) -> str | None:
        if value is not None:
            _check_relative(value)
        return value

    @field_validator("styles")
    @classmethod
    def _relatives(cls, value: list[str]) -> list[str]:
        for item in value:
            _check_relative(item)
        return value


def _check_relative(path: str) -> None:
    parts = path.replace("\\", "/").split("/")
    if not path or path.startswith(("/", "\\")) or ":" in path or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"{path!r} must be a plain path inside the plugin's folder")


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: str = "0.0.0"
    description: str = ""
    api: int = PLUGIN_API
    entry: str = "__init__.py"
    requires_env: list[str] = Field(default_factory=list[str])
    """Environment variables the plugin reads through ``ctx.secret``; nothing else is visible to it."""
    requires: list[str] = Field(default_factory=list[str])
    """Python packages (pip requirement strings) the plugin needs."""
    user_config: dict[str, ConfigField] = Field(default_factory=dict[str, ConfigField])
    ui: UiSpec | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not NAME_PATTERN.match(value):
            raise ValueError("use a-z, 0-9, '_' or '-' (at most 64 characters)")
        return value

    def defaults(self) -> dict[str, Any]:
        return {key: field.default for key, field in self.user_config.items() if field.default is not None}


@dataclass(frozen=True, slots=True)
class PluginSource:
    manifest: PluginManifest
    folder: Path
    origin: PluginOrigin

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def entry_path(self) -> Path:
        return self.folder / self.manifest.entry


@dataclass(frozen=True, slots=True)
class Discovery:
    plugins: Mapping[str, PluginSource]
    broken: Mapping[str, str]
    """Folder name -> why its manifest could not be read."""


def read_manifest(folder: Path) -> PluginManifest | None:
    """The folder's manifest, None when it has none; TOML wins when both exist."""
    data: Any
    toml_file = folder / TOML_MANIFEST
    yaml_file = next((folder / name for name in YAML_MANIFESTS if (folder / name).is_file()), None)
    if toml_file.is_file():
        if yaml_file is not None:
            logger.warning("%s has both %s and %s; using the TOML one", folder, TOML_MANIFEST, yaml_file.name)
        with toml_file.open("rb") as handle:
            data = tomllib.load(handle)
    elif yaml_file is not None:
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    else:
        return None
    if not isinstance(data, dict):
        raise ValueError("the manifest must be a table of keys")
    return PluginManifest.model_validate(data)


def discover(roots: Iterable[tuple[PluginOrigin, Path]]) -> Discovery:
    """Every plugin folder under the roots (one level deep). A name found twice is an error: which one would
    run must never depend on the order of folders."""
    plugins: dict[str, PluginSource] = {}
    broken: dict[str, str] = {}
    for origin, root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            try:
                manifest = read_manifest(folder)
            except (OSError, ValueError, ValidationError, tomllib.TOMLDecodeError, yaml.YAMLError) as err:
                broken[folder.name] = f"{folder}: {_reason(err)}"
                continue
            if manifest is None:
                continue
            if manifest.api != PLUGIN_API:
                broken[manifest.name] = (
                    f"{folder}: plugin API {manifest.api}, this service speaks {PLUGIN_API}"
                )
                continue
            known = plugins.get(manifest.name)
            if known is not None:
                raise PluginError(manifest.name, f"found twice: {known.folder} and {folder}")
            plugins[manifest.name] = PluginSource(manifest, folder, origin)
    return Discovery(plugins, broken)


def _reason(err: Exception) -> str:
    if isinstance(err, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors(include_url=False)
        )
    return f"{type(err).__name__}: {err}"
