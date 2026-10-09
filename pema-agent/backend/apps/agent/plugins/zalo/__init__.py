"""The Zalo plugin: the agent on Zalo through a Zalo Bot, a personal account (QR login) or, later, an Official
Account. One package holds the accounts and their credentials, the admin routes the dashboard uses, the
channels and the tools, so enabling the plugin brings all of it and disabling it takes all of it away.

A port of zalo-agent (MIT; see NOTICE). Nothing of it lives in the agent core.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext

from .accounts import AccountStore
from .routes import account_routes


def register(ctx: PluginContext) -> None:
    store = AccountStore(ctx.storage, encrypt=ctx.encrypt, decrypt=ctx.decrypt)
    ctx.register_routes(account_routes(store, running=lambda _account_id: False))
