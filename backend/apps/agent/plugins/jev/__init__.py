"""The ``jev`` plugin: Jev (TypeSafe), a small model that answers typed yes/no, choice and score
questions with probabilities, given to the other plugins as the service ``judge``
(``agent_app.plugins.JudgeService``). The knowledge store uses it to rank and filter what a search finds.
This plugin holds the key (sealed), the model and the token allowance of the day, and keeps what each day
used; it registers no tool and no hook. See ``docs/PLAN-jev-plugin.md``.
"""

from __future__ import annotations

import httpx

from agent_app.plugins import PluginContext
from plugin_kit import JUDGE

from .client import JevClient
from .plugin import JevPlugin
from .routes import jev_routes
from .service import SharedJudge


def register(ctx: PluginContext) -> None:
    # ``transport`` is not a manifest setting: tests hand in an httpx transport faking TypeSafe
    transport = ctx.config.get("transport")
    client = JevClient(transport=transport if isinstance(transport, httpx.AsyncBaseTransport) else None)
    plugin = JevPlugin(ctx, client=client)
    ctx.register_routes(jev_routes(plugin))
    ctx.provide(JUDGE, SharedJudge(plugin))
