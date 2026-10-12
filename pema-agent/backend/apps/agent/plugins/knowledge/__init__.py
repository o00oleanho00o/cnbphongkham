"""The ``knowledge`` plugin (the knowledge store, "Kho tri thức"): the documents the agent looks things up in.

Only its browser half exists so far (``ui/``, built against the mock agent of the clinic web); the server half
(sources, chunks, search, the ``kb_search`` tool) follows the steps of ``docs/PLAN-knowledge-plugin.md``. Until then
the plugin registers nothing.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext


def register(ctx: PluginContext) -> None:
    """Nothing to add yet."""
