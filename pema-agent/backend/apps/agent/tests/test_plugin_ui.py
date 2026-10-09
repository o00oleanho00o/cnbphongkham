"""Plugins' browser files: served open while the plugin is enabled, only from its ``[ui] dir``, with fixed
content types; ``/`` leads to the dashboard plugin; ``/v1/admin/ui`` lists the scripts to load."""

from __future__ import annotations

import textwrap
from pathlib import Path

import httpx
import pytest

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugin_ui import inside
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime

ADMIN = "a" * 40
AUTH = {"Authorization": f"Bearer {ADMIN}"}


def _plugin(root: Path, name: str, ui: str, files: dict[str, str]) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(f'name = "{name}"\n{textwrap.dedent(ui)}', encoding="utf-8")
    (folder / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    for relative, text in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _runtime(tmp_path: Path) -> Runtime:
    folder = tmp_path / "agent"
    plugins = folder / "plugins"
    _plugin(
        plugins,
        "shell",
        """
        [ui]
        home = true
        """,
        {"ui/dist/index.html": "<html>shell</html>", "ui/dist/assets/app-1a2b.js": "console.log(1)"},
    )
    _plugin(
        plugins,
        "extra",
        """
        [ui]
        entry = "client.js"
        styles = ["client.css", "missing.css"]
        """,
        {"ui/dist/client.js": "register()", "ui/dist/client.css": "a{}"},
    )
    _plugin(plugins, "unbuilt", '[ui]\nentry = "client.js"\n', {})
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\n\n[plugins]\nenabled = ["shell", "extra", "unbuilt"]\n',
        encoding="utf-8",
    )
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(runtime.dispatcher(), GatewaySettings(admin_token=ADMIN), plugins=runtime.plugin_manager)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def test_the_dashboard_and_plugin_files_are_served_with_fixed_types_and_caching(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        root = await client.get("/")
        page = await client.get("/ui/shell/")
        asset = await client.get("/ui/shell/assets/app-1a2b.js")
        script = await client.get("/ui/extra/client.js")
        unbuilt = await client.get("/ui/unbuilt/client.js")
        posted = await client.post("/ui/shell/")
        unknown = await client.get("/ui/nobody/")

    assert (root.status_code, root.headers["location"]) == (307, "ui/shell/")
    assert (page.text, page.headers["content-type"], page.headers["cache-control"]) == (
        "<html>shell</html>",
        "text/html; charset=utf-8",
        "no-cache",
    )
    assert asset.headers["content-type"] == "text/javascript; charset=utf-8"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert (script.text, script.headers["x-content-type-options"]) == ("register()", "nosniff")
    assert "not built" in unbuilt.json()["detail"]
    assert (posted.status_code, unknown.status_code) == (405, 404)
    runtime.close()


async def test_the_dashboard_lists_the_scripts_of_enabled_plugins_to_admins_only(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        anonymous = await client.get("/v1/admin/ui")
        listed = (await client.get("/v1/admin/ui", headers=AUTH)).json()
        await client.post("/v1/admin/plugins/extra/disable", headers=AUTH)
        after = (await client.get("/v1/admin/ui", headers=AUTH)).json()
        gone = await client.get("/ui/extra/client.js")

    assert anonymous.status_code == 401
    assert listed == {
        "home": "shell",
        "plugins": [{"name": "extra", "script": "/ui/extra/client.js", "styles": ["/ui/extra/client.css"]}],
    }
    assert (after["plugins"], gone.status_code) == ([], 404)
    runtime.close()


@pytest.mark.parametrize(
    "relative", ["../plugin.toml", "a/../../x", "..\\plugin.toml", "C:/x", "", "assets/"]
)
def test_nothing_outside_the_folder_is_ever_served(tmp_path: Path, relative: str) -> None:
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (tmp_path / "plugin.toml").write_text("secret", encoding="utf-8")

    assert inside(folder, relative) is None


async def test_an_encoded_escape_is_refused(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        escaped = await client.get("/ui/shell/..%2F..%2Fplugin.toml")

    assert escaped.status_code == 404
    runtime.close()
