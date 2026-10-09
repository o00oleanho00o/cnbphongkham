"""The plugins' browser files, served open at ``/ui/<plugin>/<path>`` while the plugin is enabled (code and
styles, never data: the data comes from the plugin's admin routes, behind a sign-in).

Only files inside the plugin's ``[ui] dir`` are served; an ``index.html`` (the dashboard, ``[ui] home``) is
never cached, Vite's hashed ``assets/`` are cached for a year.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.types import Receive, Scope, Send

from agent_app.plugins.manager import PluginManager
from agentcore.channels import valid_channel_name

UI_PREFIX: Final = "/ui"
CONTENT_TYPES: Final = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}
"""Fixed here: Windows can map ``.js`` to ``text/plain`` in its registry, which browsers refuse to run."""

logger = logging.getLogger(__name__)


class PluginUi:
    def __init__(self, plugins: PluginManager) -> None:
        self._plugins = plugins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        answer = await self._answer(Request(scope))
        await answer(scope, receive, send)

    async def _answer(self, request: Request) -> Response:
        if request.method not in ("GET", "HEAD"):
            return _error(405, "only GET")
        root: str = request.scope.get("root_path", "")
        path: str = request.scope["path"]
        name, _, rest = (path[len(root) :] if path.startswith(root) else path).lstrip("/").partition("/")
        if not valid_channel_name(name):
            return _error(404, "no such plugin")
        try:
            await self._plugins.refresh()
        except Exception:  # serve with the plugins as they are
            logger.warning("plugin refresh failed before a plugin file")
        found = self._plugins.host.ui(name)
        if found is None:
            return _error(404, "no such plugin or it has no browser files")
        folder, _ = found
        file = inside(folder, rest or "index.html")
        if file is None:
            if not folder.is_dir():
                return _error(404, f"the browser files of {name} are not built (pnpm build in its ui folder)")
            return _error(404, "no such file")
        cache = "public, max-age=31536000, immutable" if rest.startswith("assets/") else "no-cache"
        return FileResponse(
            file,
            media_type=CONTENT_TYPES.get(file.suffix.lower(), "application/octet-stream"),
            headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"},
        )


def inside(folder: Path, relative: str) -> Path | None:
    """The file ``relative`` names under ``folder``; None when it is not there or would leave the folder."""
    parts = relative.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        return None
    try:
        base = folder.resolve(strict=True)
        candidate = folder.joinpath(*parts).resolve(strict=True)
    except OSError:
        return None
    return candidate if candidate.is_relative_to(base) and candidate.is_file() else None


def _error(status: int, detail: str) -> Response:
    return JSONResponse({"detail": detail}, status_code=status)
