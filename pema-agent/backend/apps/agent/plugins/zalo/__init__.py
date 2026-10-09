"""The Zalo plugin: the agent on Zalo through a Zalo Bot, a personal account (QR login) or, later, an Official
Account. One package holds the accounts and their credentials, the admin routes the dashboard uses, the
channels and the tools, so enabling the plugin brings all of it and disabling it takes all of it away.

A port of zalo-agent (MIT; see NOTICE). Nothing of it lives in the agent core.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import httpx

from agent_app.plugins import PluginContext

from .bot.client import BotApiClient, tao_zalo_bot_client
from .personal.client import BridgeClient
from .plugin import ZaloPlugin
from .routes import account_routes, hook_routes


def register(ctx: PluginContext) -> None:
    # ``bot_transport``, ``bridge_transport`` and ``bridge_secret`` are not manifest settings: only code that
    # enables the plugin itself (tests, with a fake Zalo and a fake bridge) passes them.
    bot_client: Callable[[str], BotApiClient] = tao_zalo_bot_client
    transport = ctx.config.get("bot_transport")
    if isinstance(transport, httpx.AsyncBaseTransport):
        bot_client = functools.partial(tao_zalo_bot_client, transport=transport)
    bridge: BridgeClient | None = None
    bridge_transport, bridge_secret = ctx.config.get("bridge_transport"), ctx.config.get("bridge_secret")
    if isinstance(bridge_transport, httpx.AsyncBaseTransport) and isinstance(bridge_secret, str):
        bridge = BridgeClient("http://bridge", bridge_secret, transport=bridge_transport)
    plugin = ZaloPlugin(ctx, bot_client=bot_client, bridge=bridge)
    plugin.register()
    ctx.register_routes(account_routes(plugin))
    ctx.register_routes(hook_routes(plugin), kind="hooks")
