"""The ``conversations`` plugin: keeps the conversations the agent's chat channels hear, from any
platform, both sides (customer and staff) and the agent's replies, in the database. Off for every channel
until it is switched on in the settings; a conversation can be left out, and old messages can be deleted
after a number of days. It is the data the scenario search of ``docs/PLAN-skills-studio.md`` (GĐ4) draws
on. Its tables come from ``migrations/`` (``agent db migrate-plugins``); without a database it keeps them
in process memory.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext

from .plugin import ConversationsPlugin
from .routes import conversations_routes


def register(ctx: PluginContext) -> None:
    plugin = ConversationsPlugin(ctx)
    plugin.register()
    ctx.register_routes(conversations_routes(plugin))
