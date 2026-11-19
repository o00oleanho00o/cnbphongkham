"""The ``connectors`` plugin: the one door for external connectors (Zalo, Facebook, Telegram ...). A connector is a
separate service that gets a key on the admin page, registers its chat channels over the signed HTTP protocol of
``docs/CONNECTOR-PROTOCOL.md``, pushes what it hears and carries out the agent's replies. The plugin knows no chat
platform by name; what a channel's prompt rules and switched-off tools are comes from the connector's own
registration.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext

from .plugin import ConnectorsPlugin
from .routes import connector_admin_routes, connector_hook_routes


def register(ctx: PluginContext) -> None:
    plugin = ConnectorsPlugin(ctx)
    plugin.register()
    ctx.register_routes(connector_admin_routes(plugin))
    ctx.register_routes(connector_hook_routes(plugin), kind="hooks")
