"""The ``knowledge`` plugin (the knowledge store, "Kho tri thức"): the documents the agent looks things up
in.

Documents (Markdown or text, with an optional YAML head) are added from the pages "Kho tri thức", cut into
chunks at their headings and searched by keyword and by meaning (``kb_search``, ``kb_read``): a background job
embeds the chunks through an OpenAI-compatible service, and a search ranks the vector hits first and the
keyword hits after them, falling back to keywords alone while that service is off, slow or failing. Every
channel uses the same store. Its tables come
from ``migrations/`` (``agent db migrate-plugins``); without a database it keeps them in process memory. See
``docs/PLAN-knowledge-plugin.md``, ``docs/PLAN-knowledge-ui.md`` and ``docs/PLAN-knowledge-embedding.md``.
"""

from __future__ import annotations

import httpx

from agent_app.plugins import PluginContext

from .embedding import EmbeddingClient
from .plugin import KnowledgePlugin
from .routes import knowledge_routes


def register(ctx: PluginContext) -> None:
    # ``embedding_transport`` is not a manifest setting: tests hand in an httpx transport faking the service
    transport = ctx.config.get("embedding_transport")
    client = EmbeddingClient(transport=transport if isinstance(transport, httpx.AsyncBaseTransport) else None)
    plugin = KnowledgePlugin(ctx, client=client)
    plugin.register()
    ctx.register_routes(knowledge_routes(plugin))
