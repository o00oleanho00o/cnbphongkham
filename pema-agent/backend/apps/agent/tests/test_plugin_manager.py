"""The plugin manager: stored choices and settings (secrets encrypted), a managed plugin that fails, other
processes following a change, installing from a folder, a zip or git with requirements, uninstalling, the
admin routes and the CLI."""

from __future__ import annotations

import io
import json
import shutil
import stat
import subprocess
import sys
import textwrap
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from agent_app.cli import main
from agent_app.gateway import GatewaySettings, create_app
from agent_app.model_settings import SecretKeyMissingError
from agent_app.plugins import PluginError
from agent_app.plugins.install import InstallError, PluginInstaller, Runner, run_command
from agent_app.plugins.manager import PluginManager, PluginNotFoundError
from agent_app.plugins.state import InMemoryPluginStateStore
from agent_app.profile import load_profile
from agent_app.runtime import PLUGIN_DIR_ENV, Runtime, build_runtime, plugin_roots
from agentcore import ToolContext

KEY = "b" * 64
TOKEN = "t" * 40
ADMIN = "a" * 40
ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN}"}

CFG_MANIFEST = """
name = "cfg"
version = "1.0.0"
[user_config.greeting]
default = "hi"
[user_config.count]
type = "integer"
[user_config.token]
sensitive = true
required = true
"""
CFG = """
import json

from pydantic import BaseModel

from agentcore import ToolOutput, ToolSpec


class Args(BaseModel):
    pass


def register(ctx):
    config = dict(ctx.config)

    async def run(args, tool_ctx):
        return ToolOutput(text=json.dumps(config, sort_keys=True))

    ctx.register_tool(ToolSpec(name="show_cfg", description="config", args_model=Args, handler=run))
"""
PING = """
from pydantic import BaseModel

from agentcore import ToolOutput, ToolSpec


class Args(BaseModel):
    pass


async def run(args, ctx):
    return ToolOutput(text="pong")


def register(ctx):
    ctx.register_tool(ToolSpec(name="ping", description="ping", args_model=Args, handler=run))
"""
BOOM = """
def register(ctx):
    raise RuntimeError("cannot start")
"""
USES_DEPS = """
from pydantic import BaseModel

from agentcore import ToolOutput, ToolSpec


class Args(BaseModel):
    pass


def register(ctx):
    import agent_test_tinylib

    async def run(args, tool_ctx):
        return ToolOutput(text=str(agent_test_tinylib.VALUE))

    ctx.register_tool(ToolSpec(name="tiny", description="tiny", args_model=Args, handler=run))
"""


@dataclass(frozen=True, slots=True)
class Setup:
    folder: Path
    installed: Path
    runtime: Runtime
    manager: PluginManager


def _write_plugin(root: Path, name: str, code: str, manifest: str | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(textwrap.dedent(manifest or f'name = "{name}"\n'), encoding="utf-8")
    (folder / "__init__.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return folder


def _setup(
    tmp_path: Path,
    *,
    enabled: str = "",
    runner: Runner = run_command,
    store: InMemoryPluginStateStore | None = None,
    secret_key: str | None = KEY,
    name: str = "agent",
) -> Setup:
    folder = tmp_path / name
    (folder / "plugins").mkdir(parents=True)
    (folder / "agent.toml").write_text(
        f'[agent]\nname = "t"\nsystem_prompt = "p"\n\n[plugins]\nenabled = [{enabled}]\n', encoding="utf-8"
    )
    installed = tmp_path / "installed"
    env = {PLUGIN_DIR_ENV: str(installed)}
    profile = load_profile(folder)
    runtime = build_runtime(profile, fake=True, env=env, db=None)
    manager = PluginManager(
        runtime.live,
        store or InMemoryPluginStateStore(),
        profile=profile,
        roots=lambda: plugin_roots(profile, env),
        tenant_id="default",
        secret_key=secret_key,
        installer=PluginInstaller(installed, runner=runner, allow_local_git=True),
        refresh_s=0,
    )
    return Setup(folder, installed, runtime, manager)


async def _call(runtime: Runtime, tool: str) -> str:
    spec = runtime.agent.tools.get(tool)
    assert spec is not None, f"{tool} is not offered"
    output = await spec.handler(spec.args_model(), ToolContext("s"))
    return output.text


def _zip(files: dict[str, str], *, links: Iterable[str] = ()) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for name in links:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


def _leftovers(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.name.startswith(".")) if root.exists() else []


# --- settings and secrets ---


async def test_enable_with_settings_keeps_the_secret_encrypted_and_hands_it_to_the_plugin(
    tmp_path: Path,
) -> None:
    store = InMemoryPluginStateStore()
    setup = _setup(tmp_path, store=store)
    _write_plugin(setup.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    await setup.manager.start()

    shown = await setup.manager.enable("cfg", {"token": "s3cret-token-value", "count": 2})

    assert (shown["enabled"], shown["managed_by"], shown["error"]) == (True, "admin", None)
    settings = {s["key"]: s for s in shown["settings"]}
    assert (settings["greeting"]["value"], settings["greeting"]["source"]) == ("hi", "default")
    assert (settings["count"]["value"], settings["count"]["source"]) == (2, "admin")
    assert settings["token"]["value"] != "s3cret-token-value"
    assert settings["token"]["default"] is None
    row = await store.get("default", "cfg")
    assert row is not None
    assert row.secrets_enc is not None
    assert "s3cret" not in row.secrets_enc
    assert "token" not in row.config
    assert json.loads(await _call(setup.runtime, "show_cfg")) == {
        "count": 2,
        "greeting": "hi",
        "token": "s3cret-token-value",
    }


async def test_settings_are_checked_against_the_manifest(tmp_path: Path) -> None:
    setup = _setup(tmp_path)
    _write_plugin(setup.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    keyless = _setup(tmp_path / "k", secret_key=None)
    _write_plugin(keyless.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    await setup.manager.start()
    await keyless.manager.start()

    with pytest.raises(PluginError, match="unknown setting"):
        await setup.manager.configure("cfg", {"colour": "red"})
    with pytest.raises(PluginError, match="setting count must be a integer"):
        await setup.manager.configure("cfg", {"count": True})
    with pytest.raises(PluginError, match="setting greeting must be a string"):
        await setup.manager.configure("cfg", {"greeting": 3})
    with pytest.raises(SecretKeyMissingError):
        await keyless.manager.configure("cfg", {"token": "x"})
    with pytest.raises(PluginNotFoundError):
        await setup.manager.enable("nope")


async def test_new_settings_reload_an_enabled_plugin_and_an_empty_secret_keeps_the_stored_one(
    tmp_path: Path,
) -> None:
    setup = _setup(tmp_path)
    _write_plugin(setup.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    await setup.manager.start()
    await setup.manager.enable("cfg", {"token": "first-token-123"})

    await setup.manager.configure("cfg", {"greeting": "yo", "token": ""})
    changed = json.loads(await _call(setup.runtime, "show_cfg"))
    await setup.manager.configure("cfg", {"greeting": None})
    back = json.loads(await _call(setup.runtime, "show_cfg"))

    assert changed == {"greeting": "yo", "token": "first-token-123"}
    assert back == {"greeting": "hi", "token": "first-token-123"}


async def test_a_managed_plugin_that_fails_is_switched_off_with_its_error_and_the_service_runs_on(
    tmp_path: Path,
) -> None:
    setup = _setup(tmp_path)
    _write_plugin(setup.folder / "plugins", "boom", BOOM)
    _write_plugin(setup.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    await setup.manager.start()

    with pytest.raises(PluginError, match="RuntimeError: cannot start"):
        await setup.manager.enable("boom")
    with pytest.raises(PluginError, match="missing setting"):
        await setup.manager.enable("cfg")
    boom = await setup.manager.show("boom")

    assert (boom["enabled"], boom["managed_by"]) == (False, "admin")
    assert "cannot start" in boom["error"]
    assert setup.runtime.plugins.enabled() == []
    assert setup.runtime.agent.tools.names() == []


# --- the stored choice wins, and every process follows it ---


async def test_a_stored_choice_overrides_the_profile_and_another_process_follows_it(tmp_path: Path) -> None:
    store = InMemoryPluginStateStore()
    one = _setup(tmp_path, enabled='"calculate"', store=store, name="one")
    two = _setup(tmp_path, enabled='"calculate"', store=store, name="two")
    await one.manager.start()
    await two.manager.start()

    await one.manager.disable("calculate")
    await two.manager.refresh()
    off = two.runtime.agent.tools.get("calculate")
    await one.manager.enable("calculate", {"precision": 2})
    await two.manager.refresh()

    assert off is None
    spec = two.runtime.agent.tools.get("calculate")
    assert spec is not None
    output = await spec.handler(spec.args_model.model_validate({"expression": "1/3"}), ToolContext("s"))
    assert output.text == "0.33"


async def test_refresh_reads_the_store_at_most_every_refresh_interval(tmp_path: Path) -> None:
    class CountingStore(InMemoryPluginStateStore):
        def __init__(self) -> None:
            super().__init__()
            self.reads = 0

        async def fingerprint(self, tenant_id: str) -> str:
            self.reads += 1
            return await super().fingerprint(tenant_id)

    now = [100.0]
    setup = _setup(tmp_path)
    profile = load_profile(setup.folder)
    store = CountingStore()
    manager = PluginManager(
        setup.runtime.live,
        store,
        profile=profile,
        roots=lambda: plugin_roots(profile, {}),
        tenant_id="default",
        secret_key=KEY,
        refresh_s=5.0,
        clock=lambda: now[0],
    )
    await manager.start()
    reads = store.reads

    await manager.refresh()
    now[0] += 6
    await manager.refresh()

    assert store.reads == reads + 1


# --- installing ---


async def test_install_from_a_folder_enable_and_upgrade(tmp_path: Path) -> None:
    setup = _setup(tmp_path)
    source = _write_plugin(tmp_path / "src", "ping", PING, 'name = "ping"\nversion = "1.0.0"\n')
    await setup.manager.start()

    first = await setup.manager.install_folder(source, enable=True)
    (source / "plugin.toml").write_text('name = "ping"\nversion = "2.0.0"\n', encoding="utf-8")
    second = await setup.manager.install_folder(source)

    assert (first["origin"], first["enabled"], first["install"]["kind"]) == ("installed", True, "folder")
    assert (second["version"], second["enabled"], second["install"]["version"]) == ("2.0.0", True, "2.0.0")
    assert await _call(setup.runtime, "ping") == "pong"
    assert (setup.installed / "ping" / "plugin.toml").is_file()
    assert _leftovers(setup.installed) == []


async def test_install_from_a_zip_with_a_top_folder(tmp_path: Path) -> None:
    setup = _setup(tmp_path)
    await setup.manager.start()
    data = _zip({"ping-main/plugin.toml": 'name = "ping"\n', "ping-main/__init__.py": textwrap.dedent(PING)})

    shown = await setup.manager.install_zip(data, enable=True)

    assert shown["install"]["kind"] == "zip"
    assert shown["install"]["ref"].startswith("sha256:")
    assert await _call(setup.runtime, "ping") == "pong"


@pytest.mark.parametrize(
    ("files", "links", "error"),
    [
        ({"../evil.py": "x", "plugin.toml": 'name = "e"\n'}, (), "leaves the plugin folder"),
        ({"/abs.py": "x", "plugin.toml": 'name = "e"\n'}, (), "leaves the plugin folder"),
        ({"plugin.toml": 'name = "e"\n', "__init__.py": ""}, ("link",), "is a link"),
        ({"readme.md": "no manifest"}, (), "no plugin.toml"),
        ({"plugin.toml": 'name = "e"\napi = 9\n', "__init__.py": ""}, (), "plugin API 9"),
        ({"plugin.toml": 'name = "e"\n'}, (), "entry file __init__.py is missing"),
    ],
)
async def test_a_bad_zip_is_refused_and_leaves_nothing(
    tmp_path: Path, files: dict[str, str], links: tuple[str, ...], error: str
) -> None:
    setup = _setup(tmp_path)

    with pytest.raises(InstallError, match=error):
        await setup.manager.install_zip(_zip(files, links=links))
    assert _leftovers(setup.installed) == []


async def test_a_zip_that_unpacks_too_large_or_is_not_a_zip_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path)
    monkeypatch.setattr("agent_app.plugins.install.MAX_UNPACKED_BYTES", 1000)
    big = _zip({"plugin.toml": 'name = "big"\n', "__init__.py": "x" * 5000})

    with pytest.raises(InstallError, match="unpacks to more than 1000 bytes"):
        await setup.manager.install_zip(big)
    with pytest.raises(InstallError, match="not a zip file"):
        await setup.manager.install_zip(b"plain text")
    assert _leftovers(setup.installed) == []


async def test_requirements_go_into_the_plugins_own_folder_and_onto_the_path_while_enabled(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_pip(command: Sequence[str], timeout_s: float) -> str:
        commands.append(list(command))
        target = Path(command[list(command).index("--target") + 1])
        target.mkdir(parents=True)
        (target / "agent_test_tinylib.py").write_text("VALUE = 42\n", encoding="utf-8")
        return ""

    setup = _setup(tmp_path, runner=fake_pip)
    source = _write_plugin(
        tmp_path / "src", "tiny", USES_DEPS, 'name = "tiny"\nrequires = ["tinylib==1.0"]\n'
    )
    deps = str(setup.installed / "tiny" / ".deps")
    try:
        await setup.manager.install_folder(source, enable=True)
        on_path = deps in sys.path
        value = await _call(setup.runtime, "tiny")
        await setup.manager.disable("tiny")
    finally:
        sys.modules.pop("agent_test_tinylib", None)

    assert commands[0][-3:] == ["--target", commands[0][-2], "tinylib==1.0"]
    assert (on_path, value, deps in sys.path) == (True, "42", False)


@pytest.mark.parametrize(
    "requirement", ["-e .", "pkg @ https://example.com/x.whl", "git+https://x/y", "a; rm"]
)
async def test_requirements_must_be_plain_package_specs(tmp_path: Path, requirement: str) -> None:
    setup = _setup(tmp_path, runner=lambda command, timeout_s: "")
    source = _write_plugin(tmp_path / "src", "r", PING, f'name = "r"\nrequires = ["{requirement}"]\n')

    with pytest.raises(InstallError, match="plain package specs"):
        await setup.manager.install_folder(source)
    assert not (setup.installed / "r").exists()


async def test_install_refuses_a_bundled_name_and_uninstall_refuses_a_bundled_plugin(tmp_path: Path) -> None:
    setup = _setup(tmp_path)
    source = _write_plugin(tmp_path / "src", "calculate", PING, 'name = "calculate"\n')
    await setup.manager.start()

    with pytest.raises(PluginError, match="a bundled plugin has this name"):
        await setup.manager.install_folder(source)
    with pytest.raises(PluginError, match="cannot be uninstalled"):
        await setup.manager.uninstall("calculate")
    assert _leftovers(setup.installed) == []


async def test_uninstall_removes_the_folder_and_the_stored_state(tmp_path: Path) -> None:
    store = InMemoryPluginStateStore()
    setup = _setup(tmp_path, store=store)
    source = _write_plugin(tmp_path / "src", "ping", PING)
    await setup.manager.install_folder(source, enable=True)

    await setup.manager.uninstall("ping")

    assert not (setup.installed / "ping").exists()
    assert await store.get("default", "ping") is None
    assert setup.runtime.agent.tools.get("ping") is None
    with pytest.raises(PluginNotFoundError):
        await setup.manager.show("ping")


async def test_without_a_plugin_folder_nothing_can_be_installed(tmp_path: Path) -> None:
    path = tmp_path / "plain.toml"
    path.write_text('[agent]\nname = "t"\n', encoding="utf-8")
    runtime = build_runtime(load_profile(path), fake=True, env={}, db=None)

    with pytest.raises(PluginError, match="no folder for installed plugins"):
        await runtime.plugin_manager.install_zip(b"")


def test_git_urls_and_refs_are_checked(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path / "installed", runner=lambda command, timeout_s: "")

    for url, error in (
        ("http://example.com/p.git", "https://"),
        ("https://user:secret@example.com/p.git", "credentials"),
        ("--upload-pack=touch /tmp/x", "not a git URL"),
        ("file:///srv/repo", "https://"),
        (str(tmp_path), "https://"),
        ("ext::sh -c touch% /tmp/x", "https://"),
    ):
        with pytest.raises(InstallError, match=error):
            installer.stage_git(url)
    with pytest.raises(InstallError, match="git ref"):
        installer.stage_git("https://example.com/p.git", "--upload-pack=x")
    with pytest.raises(InstallError, match="git ref"):
        installer.stage_git("https://example.com/p.git", "a/../../b")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_install_from_a_git_repository_records_the_commit_and_drops_git_data(tmp_path: Path) -> None:
    repo = _write_plugin(tmp_path, "repo", PING, 'name = "ping"\nversion = "3.1.0"\n')
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(repo)], check=True)  # noqa: S603, S607
    subprocess.run([*git, "add", "."], check=True)  # noqa: S603
    subprocess.run([*git, "commit", "-q", "-m", "first"], check=True)  # noqa: S603
    commit = subprocess.run(  # noqa: S603
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    installer = PluginInstaller(tmp_path / "installed", allow_local_git=True)

    staged = installer.stage_git(str(repo), "main")
    target = installer.commit(staged)

    assert (staged.manifest.name, staged.install["commit"], staged.install["git_ref"]) == (
        "ping",
        commit,
        "main",
    )
    assert (target / "plugin.toml").is_file()
    assert not (target / ".git").exists()


# --- admin routes and the CLI ---


async def test_admin_plugin_routes(tmp_path: Path) -> None:
    setup = _setup(tmp_path, enabled='"calculate"')
    _write_plugin(setup.folder / "plugins", "cfg", CFG, CFG_MANIFEST)
    await setup.manager.start()
    app = create_app(
        setup.runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=setup.manager
    )
    padding = "".join(f"{i:08x}" for i in range(20_000))  # incompressible enough to pass 64 KB zipped
    data = _zip({"plugin.toml": 'name = "ping"\n', "__init__.py": textwrap.dedent(PING), "pad.txt": padding})

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as client:
        chat_token = await client.get("/v1/admin/plugins", headers={"Authorization": f"Bearer {TOKEN}"})
        listed = await client.get("/v1/admin/plugins", headers=ADMIN_AUTH)
        missing = await client.post("/v1/admin/plugins/nope/enable", headers=ADMIN_AUTH)
        bad = await client.post(
            "/v1/admin/plugins/cfg/enable", headers=ADMIN_AUTH, json={"settings": {"count": "x"}}
        )
        enabled = await client.post(
            "/v1/admin/plugins/cfg/enable", headers=ADMIN_AUTH, json={"settings": {"token": "tok-12345678"}}
        )
        patched = await client.patch(
            "/v1/admin/plugins/cfg/settings", headers=ADMIN_AUTH, json={"settings": {"greeting": "yo"}}
        )
        disabled = await client.post("/v1/admin/plugins/calculate/disable", headers=ADMIN_AUTH)
        uploaded = await client.post(
            "/v1/admin/plugins/install/zip?enable=true",
            headers={**ADMIN_AUTH, "Content-Type": "application/zip"},
            content=data,
        )
        removed = await client.delete("/v1/admin/plugins/ping", headers=ADMIN_AUTH)

    assert chat_token.status_code == 403
    assert listed.status_code == 200
    assert {p["name"] for p in listed.json()["plugins"]} >= {"calculate", "cfg"}
    assert missing.status_code == 404
    assert (bad.status_code, bad.json()["error"]["kind"]) == (422, "plugin_error")
    assert (enabled.status_code, enabled.json()["enabled"]) == (200, True)
    assert "tok-12345678" not in enabled.text
    assert {s["key"]: s["value"] for s in patched.json()["settings"]}["greeting"] == "yo"
    assert (disabled.status_code, disabled.json()["enabled"], disabled.json()["managed_by"]) == (
        200,
        False,
        "admin",
    )
    assert len(data) > 64 * 1024
    assert (uploaded.status_code, uploaded.json()["enabled"]) == (200, True)
    assert removed.json() == {"uninstalled": "ping"}
    assert setup.runtime.agent.tools.get("calculate") is None


def test_plugin_changes_need_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AGENT_DATABASE_URL", raising=False)

    assert main(["plugins", "enable", "calculate", "--profile", str(tmp_path)]) == 2
    assert "plugin choices are stored in the database" in capsys.readouterr().out
