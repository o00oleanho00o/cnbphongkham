"""The ``follow_up`` plugin: writes once more, at the right time, to a customer whose one-to-one chat went
quiet, or leaves them alone (docs/PLAN-case-loop.md 7). It declares the case ``follow_up`` the agent's case
engine runs (``case.py``); the rules are pure code (``rules.py``). It reads the chat through
``ctx.chat_history``, judges with Jev (the service ``judge``) when it is on and sure, else with the chat
model, and sends only through the engine, so its messages count in the daily cap every case shares. No
table, tool or route of its own; its cases are listed at ``/v1/admin/cases``.
"""

from __future__ import annotations

from agent_app.plugins import PluginContext
from plugin_kit import JUDGE, JudgeService

from .case import FollowUps, FollowUpSettings, follow_up_case


def register(ctx: PluginContext) -> None:
    follow_ups = FollowUps(
        lambda: ctx.cases,
        ctx.chat_history,
        lambda: ctx.model,
        lambda: ctx.use(JUDGE, JudgeService),
        FollowUpSettings.of(ctx.config),
    )
    ctx.register_case(follow_up_case(follow_ups))
    ctx.on_message(follow_ups.heard)
