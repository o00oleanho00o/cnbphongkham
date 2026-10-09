"""Plugins: manifests, discovery and the host that loads them (see ``agent_app.plugins.host``)."""

from __future__ import annotations

from agent_app.plugins.host import (
    Contributions,
    Disposer,
    PluginContext,
    PluginHost,
    PluginJob,
    PluginStatus,
    RouteKind,
)
from agent_app.plugins.manifest import (
    PLUGIN_API,
    ConfigField,
    Discovery,
    PluginError,
    PluginManifest,
    PluginOrigin,
    PluginSource,
    discover,
    read_manifest,
)
from agent_app.plugins.records import PluginStorage, StorageFor

__all__ = [
    "PLUGIN_API",
    "ConfigField",
    "Contributions",
    "Discovery",
    "Disposer",
    "PluginContext",
    "PluginError",
    "PluginHost",
    "PluginJob",
    "PluginManifest",
    "PluginOrigin",
    "PluginSource",
    "PluginStatus",
    "PluginStorage",
    "RouteKind",
    "StorageFor",
    "discover",
    "read_manifest",
]
