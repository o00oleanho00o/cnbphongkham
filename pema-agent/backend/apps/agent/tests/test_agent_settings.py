"""Agent settings changed at runtime: resolution (database > profile), the agent following a change without a
restart, the tools switched on and off, the admin HTTP routes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent_app.agent_settings import (
    AgentSettings,
    InMemoryAgentSettingsStore,
    SettingsError,
    StoredAgentSettings,
    resolve_agent,
)
from agent_app.cases import CasesConfig
from agent_app.dispatcher import TokenBudget
from agent_app.follow_up import FollowUpConfig, FollowUps, InMemoryFollowUpStore
from agent_app.gateway import GatewaySettings, create_app
from agent_app.profile import Profile, load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import InMemorySessionStore

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"
TOKEN = "c" * 40
ADMIN_TOKEN = "d" * 40
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
PROFILE = Profile.model_validate(
    {
        "agent": {
            "name": "t",
            "timezone": "UTC",
            "tools": ["get_datetime"],
            "failure_reply": "Sorry.",
            "variables": {"clinic": "Pema", "hotline": "1800"},
        },
        "memory": {"enabled": True},
    }
).model_copy()


def _profile() -> Profile:
    agent = PROFILE.agent.model_copy(
        update={
            "system_prompt": "You work for Pema.",
            "rules": "Call 1800.",
            "persona_template": "You work for {{clinic}}.",
            "rules_template": "Call {{hotline}}.",
        }
    )
    return PROFILE.model_copy(update={"agent": agent})


def _runtime() -> Runtime:
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    runtime.live.host.contributions()  # the dev profile loads its plugins here
    return runtime


def test_nothing_stored_leaves_the_profile_as_it_is() -> None:
    profile = _profile()

    effective = resolve_agent(profile, None)

    assert effective.profile == profile
    assert effective.disabled_tools == frozenset()
    assert set(effective.sources.values()) == {"profile"}


def test_stored_fields_win_and_the_others_stay_with_the_profile() -> None:
    stored = StoredAgentSettings(timezone="Asia/Ho_Chi_Minh", memory_agent_chars=500, version=3)

    effective = resolve_agent(_profile(), stored)

    agent = effective.profile.agent
    assert (agent.timezone, agent.failure_reply) == ("Asia/Ho_Chi_Minh", "Sorry.")
    assert (effective.profile.memory.agent_chars, effective.profile.memory.enabled) == (500, True)
    assert effective.sources["timezone"] == "db"
    assert effective.sources["failure_reply"] == "profile"
    assert effective.version == 3


def test_a_changed_variable_fills_the_profiles_persona_again() -> None:
    effective = resolve_agent(_profile(), StoredAgentSettings(variables={"clinic": "Lotus"}))

    assert effective.profile.agent.system_prompt == "You work for Lotus."
    assert effective.profile.agent.rules == "Call 1800."


def test_a_stored_persona_names_variables_and_a_missing_one_is_an_error() -> None:
    stored = StoredAgentSettings(persona="Hello from {{clinic}}, call {{hotline}}.")
    assert resolve_agent(_profile(), stored).profile.agent.system_prompt == "Hello from Pema, call 1800."

    with pytest.raises(ValueError, match="no value for nobody"):
        resolve_agent(_profile(), StoredAgentSettings(persona="Hi {{nobody}}"))


def test_a_core_tool_follows_the_flag_then_the_profile() -> None:
    off = resolve_agent(_profile(), StoredAgentSettings(tools={"get_datetime": False}))
    assert off.profile.agent.tools == []
    assert off.disabled_tools == frozenset()  # core tools are not built at all

    bare = _profile().model_copy(update={"agent": _profile().agent.model_copy(update={"tools": []})})
    on = resolve_agent(bare, StoredAgentSettings(tools={"get_datetime": True}))
    assert on.profile.agent.tools == ["get_datetime"]


def test_a_plugin_tool_switched_off_is_listed_as_disabled() -> None:
    effective = resolve_agent(_profile(), StoredAgentSettings(tools={"kb_search": False, "kb_read": True}))

    assert effective.disabled_tools == frozenset({"kb_search"})


async def test_a_change_applies_to_the_next_agent_without_a_restart() -> None:
    runtime = _runtime()
    before = runtime.agent
    settings = runtime.agent_settings

    shown = await settings.update(
        {"failure_reply": "Try later.", "timezone": "Asia/Ho_Chi_Minh"}, by="an@admin"
    )

    assert runtime.agent is not before
    assert runtime.agent.profile.agent.failure_reply == "Try later."
    assert (shown["timezone"], shown["updated_by"], shown["version"]) == ("Asia/Ho_Chi_Minh", "an@admin", 1)
    assert shown["sources"]["failure_reply"] == "db"


async def test_clearing_gives_every_field_back_to_the_profile() -> None:
    runtime = _runtime()
    default = runtime.agent.profile.agent.failure_reply
    await runtime.agent_settings.update({"failure_reply": "Try later."})

    shown = await runtime.agent_settings.clear()

    assert runtime.agent.profile.agent.failure_reply == default
    assert shown["stored"] is False
    assert shown["version"] == 2


async def test_an_empty_change_keeps_what_is_stored() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")
    await settings.update({"failure_reply": "Later."})

    shown = await settings.update({})

    assert shown["failure_reply"] == "Later."
    assert shown["stored"] is True


async def test_the_follow_up_loop_is_off_until_an_admin_switches_it_on_for_channels() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")
    assert settings.effective.follow_up == FollowUpConfig(False, ())

    shown = await settings.update(
        {"follow_up_enabled": True, "follow_up_channels": ["zalo-a1", "zalo-a1", "zalo-b2"]}
    )

    assert settings.effective.follow_up == FollowUpConfig(True, ("zalo-a1", "zalo-b2"))
    assert (shown["follow_up_enabled"], shown["follow_up_channels"]) == (True, ["zalo-a1", "zalo-b2"])
    assert shown["sources"]["follow_up_enabled"] == "db"

    shown = await settings.update({"follow_up_enabled": None, "follow_up_channels": None})
    assert settings.effective.follow_up == FollowUpConfig(False, ())
    assert shown["stored"] is False


async def test_cases_are_off_until_switched_on_and_the_daily_cap_has_bounds() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")
    assert settings.effective.cases == CasesConfig(False, 2)

    shown = await settings.update({"cases_enabled": True, "proactive_per_person_per_day": 1})

    assert settings.effective.cases == CasesConfig(True, 1)
    assert (shown["cases_enabled"], shown["proactive_per_person_per_day"]) == (True, 1)
    assert shown["sources"]["cases_enabled"] == "db"
    for refused in (0, 21):
        with pytest.raises(SettingsError):
            await settings.update({"proactive_per_person_per_day": refused})
    await settings.update({"cases_enabled": None, "proactive_per_person_per_day": None})
    assert settings.effective.cases == CasesConfig(False, 2)


async def test_the_daily_token_budget_has_a_default_and_bounds() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")
    assert settings.effective.budget == TokenBudget()

    shown = await settings.update({"tokens_per_session_per_day": 50_000, "tokens_per_day": 1_000_000})

    assert settings.effective.budget == TokenBudget(50_000, 1_000_000)
    assert (shown["tokens_per_session_per_day"], shown["tokens_per_day"]) == (50_000, 1_000_000)
    assert shown["sources"]["tokens_per_day"] == "db"
    for name, refused in (("tokens_per_session_per_day", 9_999), ("tokens_per_day", 2_000_000_001)):
        with pytest.raises(SettingsError):
            await settings.update({name: refused})
    await settings.update({"tokens_per_session_per_day": None, "tokens_per_day": None})
    assert settings.effective.budget == TokenBudget()


@pytest.mark.parametrize("channels", [["Bad Name"], ["ok", ""], [f"c{n}" for n in range(21)]])
async def test_channels_the_loop_cannot_watch_are_refused(channels: list[str]) -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")

    with pytest.raises(SettingsError) as refused:
        await settings.update({"follow_up_channels": channels})

    assert refused.value.code == "invalid"


async def test_refused_values_store_nothing() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")
    for changes in (
        {"timezone": "Mars/Base"},
        {"memory_agent_chars": 5},
        {"persona": "Hi {{nobody}}"},
        {"variables": {"Bad Name": "x"}},
        {"variables": {"clinic": ""}},
    ):
        with pytest.raises(SettingsError) as refused:
            await settings.update(changes)
        assert refused.value.code == "invalid"

    assert (await settings.show())["stored"] is False


async def test_the_variables_and_text_come_back_as_the_admin_edits_them() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")

    shown = await settings.show()
    assert (shown["persona"], shown["variables"]["clinic"]) == ("You work for {{clinic}}.", "Pema")

    shown = await settings.update({"variables": {"clinic": "Lotus"}, "rules": "Be brief."})
    assert (shown["persona"], shown["rules"]) == ("You work for {{clinic}}.", "Be brief.")
    assert shown["variables"] == {"clinic": "Lotus", "hotline": "1800"}

    shown = await settings.update({"variables": None})
    assert shown["variables"]["clinic"] == "Pema"


async def test_a_tool_is_switched_off_and_back_and_the_agent_follows() -> None:
    runtime = _runtime()
    settings = runtime.agent_settings
    assert "get_datetime" in runtime.agent.tools.names()

    listed = await settings.set_tool("get_datetime", False)
    assert next(t for t in listed["tools"] if t["name"] == "get_datetime")["enabled"] is False
    assert "get_datetime" not in runtime.agent.tools.names()

    await settings.set_tool("get_datetime", None)
    assert "get_datetime" in runtime.agent.tools.names()


async def test_memory_is_one_flag_for_its_tool_and_its_prompt() -> None:
    runtime = _runtime()
    settings = runtime.agent_settings
    assert runtime.agent.memory is not None
    assert "memory" in runtime.agent.tools.names()

    await settings.set_tool("memory", False)

    assert runtime.agent.memory is None
    assert "memory" not in runtime.agent.tools.names()
    assert (await settings.show())["memory_enabled"] is False


async def test_a_tool_that_does_not_exist_is_refused() -> None:
    settings = AgentSettings(_profile(), InMemoryAgentSettingsStore(), tenant_id="t")

    with pytest.raises(SettingsError) as refused:
        await settings.set_tool("no_such_tool", True)

    assert refused.value.code == "unknown_tool"


async def test_a_plugin_tool_can_be_switched_off_while_its_plugin_is_on() -> None:
    runtime = _runtime()
    host = runtime.live.host
    plugin_tool = next((t for t in host.contributions().tools), None)
    if plugin_tool is None:
        pytest.skip("the dev profile loads no plugin tool")

    await runtime.agent_settings.set_tool(plugin_tool.name, False)

    assert plugin_tool.name not in runtime.agent.tools.names()
    listed = await runtime.agent_settings.tools()
    assert next(t for t in listed["tools"] if t["name"] == plugin_tool.name)["enabled"] is False


async def test_a_change_made_by_another_process_is_seen_within_the_refresh_interval() -> None:
    store = InMemoryAgentSettingsStore()
    now = [0.0]
    mine = AgentSettings(_profile(), store, tenant_id="t", refresh_s=5.0, clock=lambda: now[0])
    other = AgentSettings(_profile(), store, tenant_id="t")
    await mine.start()

    await other.update({"failure_reply": "From another process."})
    await mine.refresh()
    assert mine.effective.profile.agent.failure_reply == "Sorry."

    now[0] = 6.0
    await mine.refresh()
    assert mine.effective.profile.agent.failure_reply == "From another process."


# --- the admin routes ---


def _service() -> tuple[httpx.AsyncClient, Runtime]:
    runtime = _runtime()
    app = create_app(
        runtime.dispatcher(),
        GatewaySettings(token=TOKEN, admin_token=ADMIN_TOKEN),
        agent_settings=runtime.agent_settings,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent"), runtime


async def test_the_settings_routes_show_change_and_clear() -> None:
    client, runtime = _service()
    async with client:
        shown = await client.get("/v1/admin/settings", headers=ADMIN)
        changed = await client.patch(
            "/v1/admin/settings", headers=ADMIN, json={"failure_reply": "Later.", "memory_enabled": False}
        )
        refused = await client.patch("/v1/admin/settings", headers=ADMIN, json={"timezone": "Mars/Base"})
        unknown = await client.patch("/v1/admin/settings", headers=ADMIN, json={"surprise": 1})
        cleared = await client.delete("/v1/admin/settings", headers=ADMIN)

    assert shown.status_code == 200
    assert shown.json()["stored"] is False
    assert changed.status_code == 200
    assert (changed.json()["failure_reply"], changed.json()["memory_enabled"]) == ("Later.", False)
    assert (refused.status_code, refused.json()["error"]["kind"]) == (422, "invalid")
    assert unknown.status_code == 422
    assert cleared.json()["stored"] is False
    assert runtime.agent.profile.agent.failure_reply == shown.json()["failure_reply"]


async def test_the_tool_routes_list_and_switch() -> None:
    client, runtime = _service()
    async with client:
        listed = await client.get("/v1/admin/tools", headers=ADMIN)
        off = await client.put("/v1/admin/tools/get_datetime", headers=ADMIN, json={"enabled": False})
        missing = await client.put("/v1/admin/tools/no_such_tool", headers=ADMIN, json={"enabled": True})
        bad_body = await client.put("/v1/admin/tools/get_datetime", headers=ADMIN, json={})

    names = [tool["name"] for tool in listed.json()["tools"]]
    assert {"get_datetime", "memory"} <= set(names)
    assert off.status_code == 200
    assert "get_datetime" not in runtime.agent.tools.names()
    assert (missing.status_code, missing.json()["error"]["kind"]) == (404, "unknown_tool")
    assert bad_body.status_code == 422


async def test_the_settings_routes_need_the_admin_scope() -> None:
    client, _ = _service()
    async with client:
        chat = await client.get("/v1/admin/settings", headers={"Authorization": f"Bearer {TOKEN}"})
        nobody = await client.get("/v1/admin/tools")

    assert (chat.status_code, nobody.status_code) == (403, 401)


async def test_the_follow_up_fields_and_the_list_of_judged_conversations_are_served() -> None:
    runtime = _runtime()
    store = InMemoryFollowUpStore()
    loop = FollowUps(
        store, InMemorySessionStore(), lambda: runtime.agent.model, lambda: FollowUpConfig(), tenant_id="t"
    )
    app = create_app(
        runtime.dispatcher(),
        GatewaySettings(token=TOKEN, admin_token=ADMIN_TOKEN),
        agent_settings=runtime.agent_settings,
        follow_ups=loop,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as client:
        changed = await client.patch(
            "/v1/admin/settings",
            headers=ADMIN,
            json={"follow_up_enabled": True, "follow_up_channels": ["zalo-a1"]},
        )
        refused = await client.patch(
            "/v1/admin/settings", headers=ADMIN, json={"follow_up_channels": ["Bad Name"]}
        )
        listed = await client.get("/v1/admin/follow-ups", headers=ADMIN)
        chat = await client.get("/v1/admin/follow-ups", headers={"Authorization": f"Bearer {TOKEN}"})

    assert (changed.json()["follow_up_enabled"], changed.json()["follow_up_channels"]) == (True, ["zalo-a1"])
    assert refused.status_code == 422
    assert listed.json() == {"follow_ups": []}
    assert chat.status_code == 403
