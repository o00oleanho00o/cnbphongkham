"""The ``skills`` plugin: skills, rules and persona kept in the database, written on the pages and bound to
the whole agent, to a chat plugin (``zalo``) or to one account (a channel). Every change leaves a version to
go back to. Each question carries the rules, persona and skills index of its channel (``context_text``); the
tools ``skill_list``, ``skill_view`` and ``skill_search`` read them. It is the only place skills live: the
core keeps none. A profile that sets ``agent_writes`` also gets ``skill_write`` and ``skill_patch``. Its
tables come from ``migrations/`` (``agent db migrate-plugins``); without a database it keeps them in process
memory. See ``docs/PLAN-skills-studio.md`` and ``docs/PLAN-skills-single-store.md``. A chat with the agent's
model helps staff write items (``studio.py``).
"""

from __future__ import annotations

from agent_app.plugins import PluginContext

from .plugin import SkillsPlugin
from .routes import skills_routes
from .studio import Studio


def register(ctx: PluginContext) -> None:
    plugin = SkillsPlugin(ctx)
    plugin.register()
    ctx.register_routes(skills_routes(plugin, Studio(plugin, lambda: ctx.model)))
