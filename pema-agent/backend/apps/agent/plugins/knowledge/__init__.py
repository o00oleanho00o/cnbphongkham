"""The ``knowledge`` plugin (the knowledge store, "Kho tri thức"): the documents the agent looks things up
in.

Documents (Markdown or text, with an optional YAML head) are added from the pages "Kho tri thức", cut into
chunks at their headings and searched by keyword (``kb_search``, ``kb_read``). Every channel uses the same
store. Its tables come from ``migrations/`` (``agent db migrate-plugins``); without a database it keeps them
in process memory. See ``docs/PLAN-knowledge-plugin.md`` and ``docs/PLAN-knowledge-ui.md``.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext

from .plugin import KnowledgePlugin
from .routes import knowledge_routes


def register(ctx: PluginContext) -> None:
    plugin = KnowledgePlugin(ctx)
    plugin.register()
    ctx.register_routes(knowledge_routes(plugin))
