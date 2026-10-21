"""Plugins: manifests, discovery and the host that loads them (see ``agent_app.plugins.host``)."""

from __future__ import annotations

from agent_app.plugins.host import (
    Contributions,
    DatabaseAccess,
    Disposer,
    PluginContext,
    PluginDatabase,
    PluginHost,
    PluginJob,
    PluginStatus,
    Proactive,
    ProactiveSent,
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
from agent_app.plugins.services import (
    EMBEDDINGS,
    JUDGE,
    EmbeddingService,
    EmbeddingUnavailableError,
    JudgeService,
    JudgeUnavailableError,
)

__all__ = [
    "EMBEDDINGS",
    "JUDGE",
    "PLUGIN_API",
    "ConfigField",
    "Contributions",
    "DatabaseAccess",
    "Discovery",
    "Disposer",
    "EmbeddingService",
    "EmbeddingUnavailableError",
    "JudgeService",
    "JudgeUnavailableError",
    "PluginContext",
    "PluginDatabase",
    "PluginError",
    "PluginHost",
    "PluginJob",
    "PluginManifest",
    "PluginOrigin",
    "PluginSource",
    "PluginStatus",
    "PluginStorage",
    "Proactive",
    "ProactiveSent",
    "RouteKind",
    "StorageFor",
    "discover",
    "read_manifest",
]
