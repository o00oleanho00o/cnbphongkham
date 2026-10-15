"""Plugins: manifests and discovery, the host (enable, disable, cleanup), the agent rebuilt around them, the
start-up rules and ``agent plugins list``."""

from __future__ import annotations

import io
import json
import sys
import textwrap
from pathlib import Path

import pytest

from agent_app.assembly import build_agent
from agent_app.cli import main
from agent_app.plugins import (
    Contributions,
    PluginError,
    PluginHost,
    discover,
    read_manifest,
)
from agent_app.profile import Profile, load_profile
from agent_app.runtime import build_runtime, start_plugins
from agentcore import InMemorySessionStore, SessionSection, ToolResultBlock, run_turn
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from agentcore.memory import MemoryKey

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"

PING = """
from pydantic import BaseModel

from agentcore import ToolOutput, ToolSpec


class Args(BaseModel):
    pass


async def run(args, ctx):
    return ToolOutput(text="pong")


def register(ctx):
    ctx.register_tool(
        ToolSpec(
            name=ctx.config.get("tool", "ping"), description="ping", args_model=Args, handler=run, read_only=True
        )
    )
"""

FULL = """
from pydantic import BaseModel

from agentcore import SessionSection, ToolOutput, ToolSpec
from agentcore.harness.hooks import PostToolHook


class Args(BaseModel):
    pass


async def run(args, ctx):
    return ToolOutput(text="pong")


async def seen(use, spec, result, ctx):
    LOG.append(f"hook:{use.name}")
    return result


def register(ctx):
    global LOG
    LOG = ctx.config["log"]
    ctx.on_disable(lambda: LOG.append("cleaned"))
    ctx.register_tool(ToolSpec(name="ping", description="ping", args_model=Args, handler=run, read_only=True))
    ctx.register_prompt_section(SessionSection("full", lambda env, data: "FULL SECTION"))
    ctx.register_hook(PostToolHook("full_seen", seen))
    if ctx.config.get("fail"):
        raise RuntimeError("register failed on purpose")
"""

SECRETS = """
def register(ctx):
    try:
        ctx.secret("HOME")
    except ValueError:
        pass
    else:
        raise RuntimeError("HOME was readable")
    ctx.config["log"].append(ctx.secret("PING_KEY"))
"""


def _plugin(root: Path, name: str, code: str = PING, manifest: str | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(manifest or f'name = "{name}"\n', encoding="utf-8")
    (folder / "__init__.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return folder


def _host(root: Path, env: dict[str, str] | None = None) -> PluginHost:
    return PluginHost(discover([("agent", root)]).plugins, env or {})


def _agent_folder(tmp_path: Path, plugins: str = "") -> Path:
    folder = tmp_path / "agent"
    folder.mkdir(parents=True)
    (folder / "agent.toml").write_text(
        f'[agent]\nname = "t"\nsystem_prompt = "p"\n{plugins}', encoding="utf-8"
    )
    return folder


# --- manifests and discovery ---


def test_manifests_are_read_from_toml_or_yaml_and_unknown_keys_are_ignored(tmp_path: Path) -> None:
    toml_dir = _plugin(
        tmp_path,
        "a",
        manifest='name = "a"\nversion = "2.0.0"\nfuture_key = 1\n[user_config.level]\ntype = "integer"\ndefault = 3\n',
    )
    yaml_dir = tmp_path / "b"
    yaml_dir.mkdir()
    (yaml_dir / "plugin.yaml").write_text(
        "name: b\ndescription: from yaml\nlater: [1, 2]\n", encoding="utf-8"
    )
    (toml_dir / "plugin.yml").write_text("name: other\n", encoding="utf-8")

    from_toml, from_yaml = read_manifest(toml_dir), read_manifest(yaml_dir)

    assert from_toml is not None
    assert from_yaml is not None
    assert (from_toml.name, from_toml.version, from_toml.defaults()) == ("a", "2.0.0", {"level": 3})
    assert (from_yaml.name, from_yaml.description) == ("b", "from yaml")
    assert read_manifest(tmp_path) is None


def test_discovery_lists_broken_manifests_and_refuses_a_name_found_twice(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _plugin(root, "good")
    _plugin(root, "badname", manifest='name = "Bad Name"\n')
    _plugin(root, "future", manifest='name = "future"\napi = 2\n')
    _plugin(root, "garbled", manifest="name = \n")
    _plugin(root, "_hidden", manifest="not even toml")

    found = discover([("agent", root), ("installed", tmp_path / "missing")])

    assert list(found.plugins) == ["good"]
    assert sorted(found.broken) == ["badname", "future", "garbled"]
    assert "plugin API 2" in found.broken["future"]
    other = tmp_path / "other"
    _plugin(other, "good")
    with pytest.raises(PluginError, match="found twice"):
        discover([("agent", root), ("installed", other)])


# --- the host ---


def test_enable_needs_the_listed_env_and_required_settings_and_reveals_only_listed_secrets(
    tmp_path: Path,
) -> None:
    manifest = 'name = "s"\nrequires_env = ["PING_KEY"]\n[user_config.log]\nrequired = true\n'
    _plugin(tmp_path, "s", SECRETS, manifest)
    log: list[str] = []

    with pytest.raises(PluginError, match="PING_KEY"):
        _host(tmp_path).enable("s", {"log": log})
    with pytest.raises(PluginError, match="missing setting"):
        _host(tmp_path, {"PING_KEY": "k1"}).enable("s")
    with pytest.raises(PluginError, match="not found"):
        _host(tmp_path).enable("nope")
    _host(tmp_path, {"PING_KEY": "k1", "HOME": "/home/x"}).enable("s", {"log": log})

    assert log == ["k1"]


def test_a_failing_register_leaves_nothing_behind(tmp_path: Path) -> None:
    _plugin(tmp_path, "full", FULL)
    host = _host(tmp_path)
    log: list[str] = []

    with pytest.raises(PluginError, match="RuntimeError: register failed on purpose"):
        host.enable("full", {"log": log, "fail": True})

    assert host.contributions() == Contributions()
    assert host.enabled() == []
    assert log == ["cleaned"]
    assert not [name for name in sys.modules if name.startswith("agent_plugin_full")]


def test_disable_undoes_every_registration(tmp_path: Path) -> None:
    _plugin(tmp_path, "full", FULL)
    host = _host(tmp_path)
    log: list[str] = []
    host.enable("full", {"log": log})
    added = host.contributions()
    version = host.version

    (status,) = host.status()
    host.disable("full")

    assert (
        [t.name for t in added.tools],
        [s.name for s in added.sections],
        [h.name for h in added.hooks],
    ) == (
        ["ping"],
        ["full"],
        ["full_seen"],
    )
    assert (status.enabled, status.tools, status.origin) == (True, ("ping",), "agent")
    assert host.contributions() == Contributions()
    assert log == ["cleaned"]
    assert host.version > version
    assert not [name for name in sys.modules if name.startswith("agent_plugin_full")]


def test_two_plugins_cannot_register_the_same_tool(tmp_path: Path) -> None:
    _plugin(tmp_path, "one")
    _plugin(tmp_path, "two")
    host = _host(tmp_path)
    host.enable("one")

    with pytest.raises(PluginError, match="tool ping already comes from one"):
        host.enable("two")
    assert host.enabled() == ["one"]


def test_a_plugin_with_a_yaml_manifest_loads(tmp_path: Path) -> None:
    folder = tmp_path / "yam"
    folder.mkdir()
    (folder / "plugin.yaml").write_text(
        "name: yam\nuser_config:\n  tool:\n    default: yaml_ping\n", encoding="utf-8"
    )
    (folder / "__init__.py").write_text(textwrap.dedent(PING), encoding="utf-8")
    host = _host(tmp_path)

    host.enable("yam")

    assert [t.name for t in host.contributions().tools] == ["yaml_ping"]


# --- the agent around the plugins ---


def test_plugin_sections_follow_the_profiles_unless_the_profile_places_them() -> None:
    extra = SessionSection("extra", lambda env, data: "EXTRA")
    plugins = Contributions(sections=(extra,))

    def system(sections: list[str]) -> str:
        profile = Profile.model_validate(
            {"agent": {"name": "t", "system_prompt": "PERSONA"}, "prompt": {"sections": sections}}
        )
        return build_agent(profile, fake=True, env={}, plugins=plugins).prompt.render_system()

    after, before = system(["identity"]), system(["extra", "identity"])

    assert after.index("PERSONA") < after.index("EXTRA")
    assert before.index("EXTRA") < before.index("PERSONA")


async def test_a_plugin_tool_section_and_hook_work_in_a_real_turn(tmp_path: Path) -> None:
    folder = _agent_folder(tmp_path)
    _plugin(folder / "plugins", "full", FULL)
    log: list[str] = []
    profile = load_profile(folder)
    host = start_plugins(profile, {})
    host.enable("full", {"log": log})
    runtime = build_runtime(profile, fake=True, env={}, db=None, plugins=host)
    model = ScriptedModel([calls(tool_call("ping", {})), reply("pong")])
    runtime.live.use_model(model)
    agent = runtime.agent

    result = await run_turn(
        session_id="s",
        user_text="ping?",
        prompt=agent.prompt,
        model=agent.model,
        tools=agent.tools,
        store=InMemorySessionStore(),
        policy=agent.policy,
        hooks=agent.hooks,
    )

    results = [b for m in result.new_messages for b in m.blocks if isinstance(b, ToolResultBlock)]
    assert [(r.name, r.content) for r in results] == [("ping", "pong")]
    assert log == ["hook:ping"]
    assert "FULL SECTION" in model.requests[0].system
    assert {t.name for t in model.requests[0].tools} >= {"ping"}
    runtime.close()
    assert log == ["hook:ping", "cleaned"]


async def test_enabling_and_disabling_while_running_changes_the_next_turn_and_keeps_memory(
    tmp_path: Path,
) -> None:
    folder = _agent_folder(tmp_path, "\n[memory]\nenabled = true\n")
    _plugin(folder / "plugins", "ping")
    _plugin(folder / "plugins", "clash", manifest='name = "clash"\n[user_config.tool]\ndefault = "memory"\n')
    runtime = build_runtime(load_profile(folder), fake=True, env={}, db=None)
    dispatcher = runtime.dispatcher()
    key = MemoryKey("default", "t", "agent")
    memory = runtime.agent.memory
    assert memory is not None
    await memory.add(key, "kept")

    runtime.live.enable("ping")
    with_ping = dispatcher.agent.tools.names()
    with pytest.raises(PluginError, match="plugin clash: Tool already registered: memory"):
        runtime.live.enable("clash")
    runtime.live.disable("ping")
    without = dispatcher.agent

    assert "ping" in with_ping
    assert "ping" not in without.tools.names()
    assert runtime.plugins.enabled() == []
    assert without.memory is not None
    assert await without.memory.notes(key) == ["kept"]
    await dispatcher.close()


def test_a_listed_plugin_that_cannot_load_stops_the_start(tmp_path: Path) -> None:
    missing = load_profile(_agent_folder(tmp_path, '\n[plugins]\nenabled = ["nope"]\n'))
    broken_folder = tmp_path / "b"
    broken_folder.mkdir()
    (broken_folder / "agent.toml").write_text(
        '[agent]\nname = "t"\n\n[plugins]\nenabled = ["future"]\n', encoding="utf-8"
    )
    _plugin(broken_folder / "plugins", "future", manifest='name = "future"\napi = 2\n')
    bad_config = load_profile(_agent_folder(tmp_path / "c", '\n[plugins]\nenabled = ["web"]\nweb = 3\n'))

    with pytest.raises(PluginError, match="plugin nope: not found"):
        build_runtime(missing, fake=True, env={}, db=None)
    with pytest.raises(PluginError, match=r"plugin future: .*plugin API 2"):
        build_runtime(load_profile(broken_folder), fake=True, env={}, db=None)
    with pytest.raises(ValueError, match=r"\[plugins.web\] must be a table"):
        build_runtime(bad_config, fake=True, env={}, db=None)
    assert main(["chat", "--profile", str(missing.folder), "--fake"]) == 2


def test_the_plugins_list_command_shows_what_the_dev_agent_loads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.delenv("AGENT_DATABASE_URL", raising=False)

    assert main(["plugins", "list", "--profile", str(DEV_PROFILE)]) == 0
    shown = json.loads(capsys.readouterr().out)

    (web,) = [p for p in shown["plugins"] if p["name"] == "web"]
    assert (web["enabled"], web["managed_by"]) == (True, "profile")
    assert [(s["key"], s["default"]) for s in web["settings"]] == [("token_hours", 12)]
    assert shown["broken"] == {}
