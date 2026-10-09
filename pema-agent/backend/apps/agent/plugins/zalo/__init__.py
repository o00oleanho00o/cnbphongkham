"""The Zalo plugin: the agent on Zalo through a Zalo Bot, a personal account (QR login) or, later, an Official
Account. One package holds the accounts and their credentials, the admin routes the dashboard uses, the
channels and the tools, so enabling the plugin brings all of it and disabling it takes all of it away.

A port of zalo-agent (MIT; see NOTICE). Nothing of it lives in the agent core.
"""

from __future__ import annotations

import functools

import httpx

from agent_app.plugins import PluginContext

from .bot.client import tao_zalo_bot_client
from .plugin import ZaloPlugin
from .routes import account_routes, hook_routes


def register(ctx: PluginContext) -> None:
    # ``bot_transport`` is not a manifest setting: only code that enables the plugin itself (tests, with a
    # fake Zalo) passes an httpx transport.
    transport = ctx.config.get("bot_transport")
    if isinstance(transport, httpx.AsyncBaseTransport):
        plugin = ZaloPlugin(ctx, bot_client=functools.partial(tao_zalo_bot_client, transport=transport))
    else:
        plugin = ZaloPlugin(ctx)
    plugin.register()
    ctx.register_routes(account_routes(plugin))
    ctx.register_routes(hook_routes(plugin), kind="hooks")
