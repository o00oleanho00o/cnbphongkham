"""Stand-ins the conversations tests share: the plugin context, and an embedding service with vectors anyone can
work out by hand (the concept axes of the knowledge tests)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from agent_app.plugins import EmbeddingUnavailableError
from agent_app.plugins.records import InMemoryPluginRecords
from tests.knowledge.fake_embedding import concept_vector

SPACE = "0123456789abcdef"


class FakeCtx:
    """Just enough of ``PluginContext`` for the plugin to register itself, keep its settings and find a service."""

    database = None
    logger = logging.getLogger("conversations-test")

    def __init__(self, embeddings: FakeEmbeddings | None = None) -> None:
        self.storage = InMemoryPluginRecords().storage("conversations")
        self.handlers: list[Any] = []
        self.jobs: dict[str, Any] = {}
        self.tools: dict[str, Any] = {}
        self.hooks: list[Any] = []
        self.embeddings = embeddings

    def on_message(self, handler: Any) -> None:
        self.handlers.append(handler)

    def register_job(self, name: str, run: Any) -> None:
        self.jobs[name] = run

    def register_tool(self, spec: Any) -> None:
        self.tools[spec.name] = spec

    def register_hook(self, hook: Any) -> None:
        self.hooks.append(hook)

    def channel_plugin(self, channel: str) -> str | None:
        return {"zalo-a": "zalo", "zalo-b": "zalo", "other-a": "other"}.get(channel)

    def use(self, name: str, kind: type) -> Any:
        return self.embeddings if name == "embeddings" else None


class FakeEmbeddings:
    """An ``EmbeddingService`` over the concept vectors; it can be switched off or made to fail."""

    def __init__(self) -> None:
        self.connected = True
        self.failing = False
        self.queries: list[str] = []
        self.documents: list[str] = []

    async def space(self) -> str | None:
        return SPACE if self.connected else None

    async def embed_documents(
        self, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], str]:
        if self.failing:
            raise EmbeddingUnavailableError("Dịch vụ embedding lỗi (HTTP 500).")
        self.documents.extend(texts)
        return [concept_vector(t) for t in texts], SPACE

    async def embed_query(self, text: str, *, timeout_s: float) -> tuple[list[float], str]:
        if self.failing:
            raise EmbeddingUnavailableError("Dịch vụ embedding lỗi (HTTP 500).")
        self.queries.append(text)
        return concept_vector(text), SPACE
