"""HTTP gateway: a trusted backend (the clinic) sends user messages and gets the agent's replies; admins
change the model and the plugins.

Every caller sends a bearer token; the gate (``Gate``) turns it into a ``Principal`` with scopes (``chat``,
``admin``: see ``agent_app.auth``). The tokens come from the plugins that register an authenticator (the
``web`` plugin: dashboard logins and API keys); tests and embedders may also give fixed tokens in
``GatewaySettings``. Nothing is read from the environment. Failed attempts are limited per address.

The caller names the person speaking (``user_id``) and optionally the conversation; the session is derived
from them on the server, so a reply always belongs to the conversation it came from. Every message is stored
before it runs and a ``message_id`` sent twice runs once. A reply not ready within ``wait_s`` is answered with
202 and can be fetched from ``/v1/ingress/{id}``.

Plugins add their own routes: ``/v1/plugins/<plugin>/...`` for admins, ``/v1/hooks/<plugin>/...`` open to the
platforms that call back (the plugin checks their signature; calls are limited per address), and their browser
files under ``/ui/<plugin>/`` (``agent_app.plugin_ui``); ``/`` leads to the dashboard plugin's page.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text as sql
from starlette.types import ASGIApp, Receive, Scope, Send

from agent_app.activity import Activity
from agent_app.auth import ADMIN, CHAT, Authenticator, Principal
from agent_app.channel_hub import ChannelHub
from agent_app.dispatcher import Dispatcher, StreamObserver
from agent_app.ingress import IngressRecord
from agent_app.model_factory import Provider
from agent_app.model_settings import ModelAdmin, SecretKeyMissingError
from agent_app.plugin_ui import UI_PREFIX, PluginUi, inside
from agent_app.plugins.install import MAX_ZIP_BYTES
from agent_app.plugins.jobs import JobRunner
from agent_app.plugins.manager import PluginManager, PluginNotFoundError
from agent_app.plugins.manifest import PluginError
from agent_app.storage import AgentDatabase
from agentcore import ReasoningEffort, ToolUseBlock
from agentcore.channels import InboundMessage, valid_channel_name
from agentcore.harness.model.reasoning import OpenAIDialect

CHANNEL: Final = "http"
ADMIN_FAILURES_PER_WINDOW: Final = 5
ADMIN_FAILURE_WINDOW_S: Final = 60.0
HOOK_CALLS_PER_WINDOW: Final = 120
HOOK_WINDOW_S: Final = 60.0
PLUGIN_ROUTES: Final = "/v1/plugins"
PLUGIN_HOOKS: Final = "/v1/hooks"

logger = logging.getLogger(__name__)
MIN_TOKEN_CHARS: Final = 32
MAX_BODY_BYTES: Final = 64 * 1024
ZIP_INSTALL_PATH: Final = "/v1/admin/plugins/install/zip"
DEFAULT_WAIT_S: Final = 60.0
HEARTBEAT_S: Final = 15.0
ERROR_STATUS: Final[dict[str, int]] = {
    "rate_limit": 429,
    "transient": 503,
    "empty_response": 503,
    "context_overflow": 502,
    "auth": 502,
    "config": 502,
}


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    token: str | None = None
    """A fixed token for the chat routes, given in code (tests, an embedding service); never from the
    environment."""
    wait_s: float = DEFAULT_WAIT_S
    admin_token: str | None = None
    """A fixed token for every route; must differ from ``token``."""

    def __post_init__(self) -> None:
        for name, value in (("token", self.token), ("admin_token", self.admin_token)):
            if value is not None and len(value) < MIN_TOKEN_CHARS:
                raise ValueError(f"{name} must have at least {MIN_TOKEN_CHARS} characters")
        if self.token and self.admin_token and hmac.compare_digest(self.admin_token, self.token):
            raise ValueError("admin_token must differ from token")


class WindowLimiter:
    """Refuses a client after ``limit`` counted events (failed logins, calls) within ``window_s``, until the
    window moves on."""

    def __init__(
        self, limit: int = ADMIN_FAILURES_PER_WINDOW, window_s: float = ADMIN_FAILURE_WINDOW_S
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._events: dict[str, deque[float]] = {}

    def blocked(self, client: str, now: float) -> bool:
        events = self._events.get(client)
        if events is None:
            return False
        while events and now - events[0] >= self._window_s:
            events.popleft()
        if not events:
            del self._events[client]
            return False
        return len(events) >= self._limit

    def count(self, client: str, now: float) -> None:
        self._events.setdefault(client, deque()).append(now)


Guard = Callable[[Request], Awaitable[Response | None]]
"""Answers a request before the route does (a refused token, too many calls), or lets it through (None)."""


class Gate:
    """Admits a request when its bearer token belongs to a caller with the route's scope; the caller is then
    in ``request.state.principal``. Wrong tokens count against the address: after a few in a minute it is
    refused for a while, valid token or not."""

    def __init__(
        self, settings: GatewaySettings, authenticators: Callable[[], Sequence[Authenticator]]
    ) -> None:
        self._fixed: list[tuple[bytes, Principal]] = []
        if settings.token:
            self._fixed.append((settings.token.encode("utf-8"), Principal("service", frozenset({CHAT}))))
        if settings.admin_token:
            admin = Principal("admin", frozenset({CHAT, ADMIN}))
            self._fixed.append((settings.admin_token.encode("utf-8"), admin))
        self._authenticators = authenticators
        self._failures = WindowLimiter()

    async def principal(self, authorization: str | None) -> Principal | None:
        scheme, _, token = (authorization or "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None
        given = token.encode("utf-8")
        for wanted, principal in self._fixed:
            if hmac.compare_digest(given, wanted):
                return principal
        for authenticate in self._authenticators():
            found = await authenticate(token)
            if found is not None:
                return found
        return None

    async def admit(self, request: Request, scope: str) -> tuple[int, str] | None:
        """None when admitted, else the status and the reason."""
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if self._failures.blocked(client, now):
            return 429, "too many failed attempts; try again later"
        try:
            principal = await self.principal(request.headers.get("authorization"))
        except Exception:  # a store behind an authenticator is down: not the caller's fault
            logger.exception("a token could not be checked")
            return 503, "the token cannot be checked now; try again"
        if principal is None:
            self._failures.count(client, now)
            return 401, "a valid bearer token is required"
        if scope not in principal.scopes:
            return 403, f"this token may not use the {scope} routes"
        request.state.principal = principal
        return None

    def dependency(self, scope: str) -> Callable[[Request], Awaitable[None]]:
        async def check(request: Request) -> None:
            refused = await self.admit(request, scope)
            if refused is not None:
                status, detail = refused
                raise HTTPException(status, detail=detail, headers=_challenge(status))

        return check

    def guard(self, scope: str) -> Guard:
        async def check(request: Request) -> Response | None:
            refused = await self.admit(request, scope)
            if refused is None:
                return None
            status, detail = refused
            return JSONResponse({"detail": detail}, status_code=status, headers=_challenge(status))

        return check


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(_Body):
    message_id: str = Field(min_length=1, max_length=200)
    """The caller's id of this message; sending it again returns the first answer instead of a new run."""
    user_id: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=300)
    """Omitted for a one-to-one chat: the conversation is the user's."""
    text: str = Field(min_length=1, max_length=8000)


class ResetRequest(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=300)


class ModelSettingsPatch(_Body):
    """Only the fields sent change: a value sets it, null gives it back to the environment or the profile.
    ``api_key``: "" keeps the stored key, null removes it."""

    provider: Provider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=500, pattern=r"^https?://")
    reasoning: ReasoningEffort | None = None
    dialect: OpenAIDialect | None = None
    api_key: str | None = Field(default=None, max_length=500)


class ModelListBody(_Body):
    """What the person typed but has not saved yet; a missing or empty field uses the stored value."""

    provider: Provider | None = None
    base_url: str | None = Field(default=None, max_length=500, pattern=r"^https?://")
    api_key: str | None = Field(default=None, max_length=500)


class PluginSettingsBody(_Body):
    """A value sets a setting, null gives it back to the profile or the default; for a sensitive one ""
    keeps the stored value."""

    settings: dict[str, Any] = Field(default_factory=dict[str, Any], max_length=100)


class InstallBody(_Body):
    source: Literal["folder", "git"]
    path: str | None = Field(default=None, min_length=1, max_length=1000)
    """A folder on the agent's server (``folder``)."""
    url: str | None = Field(default=None, min_length=1, max_length=500)
    ref: str | None = Field(default=None, min_length=1, max_length=100)
    """Branch or tag (``git``); the default branch when left out."""
    enable: bool = False


def create_app(
    dispatcher: Dispatcher,
    settings: GatewaySettings,
    *,
    db: AgentDatabase | None = None,
    admin: ModelAdmin | None = None,
    plugins: PluginManager | None = None,
    channels: ChannelHub | None = None,
    jobs: JobRunner | None = None,
    activity: Activity | None = None,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        background = [asyncio.create_task(dispatcher.run_sweeper(), name="ingress sweeper")]
        if channels is not None:
            background.append(asyncio.create_task(channels.run(), name="channel hub"))
        if jobs is not None:
            background.append(asyncio.create_task(jobs.run(), name="plugin jobs"))
        try:
            yield
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            await dispatcher.close()
            if channels is not None:
                await channels.close()
            if jobs is not None:
                await jobs.close()

    app = FastAPI(title="agent gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    host = plugins.host if plugins is not None else None
    gate = Gate(settings, lambda: host.contributions().authenticators if host is not None else ())
    authorized = Depends(gate.dependency(CHAT))

    @app.middleware("http")
    async def limit_body(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        limit = MAX_ZIP_BYTES if request.url.path == ZIP_INSTALL_PATH else MAX_BODY_BYTES
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return _error(413, "too_large", f"the body may have at most {limit} bytes")
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> Response:
        if db is not None:
            try:
                async with db.engine.connect() as conn:
                    await conn.execute(sql("SELECT 1"))
            except Exception:  # not ready is the answer, whatever the cause
                return _error(503, "not_ready", "the database is not reachable")
        return JSONResponse({"status": "ready"})

    @app.post("/v1/chat", dependencies=[authorized])
    async def chat(body: ChatRequest) -> Response:
        record, _ = await dispatcher.accept(_inbound(body))
        record = await dispatcher.wait(record.id, settings.wait_s)
        return _answer(record)

    @app.post("/v1/chat/stream", dependencies=[authorized])
    async def chat_stream(body: ChatRequest) -> StreamingResponse:
        observer = StreamObserver()
        record, created = await dispatcher.accept(_inbound(body), observer=observer)
        return StreamingResponse(
            _stream(dispatcher, observer, record, duplicate=not created),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/ingress/{ingress_id}", dependencies=[authorized])
    async def ingress(ingress_id: int) -> Response:
        record = await dispatcher.ingress.get(dispatcher.tenant_id, ingress_id)
        if record is None:
            return _error(404, "not_found", "no such message")
        return JSONResponse(_status(record))

    @app.post("/v1/conversations/reset", dependencies=[authorized])
    async def reset(body: ResetRequest) -> dict[str, str]:
        session_id = await dispatcher.reset(CHANNEL, body.conversation_id or body.user_id)
        return {"session_id": session_id}

    if (admin, plugins, channels, jobs) != (None, None, None, None):
        _add_admin_routes(app, gate, admin, plugins, channels, jobs)
        profile = dispatcher.agent.profile
        _add_activity_routes(
            app,
            Depends(gate.dependency(ADMIN)),
            activity
            or Activity(
                db, agent=profile.agent.name, tenant_id=dispatcher.tenant_id, timezone=profile.agent.timezone
            ),
        )
    if plugins is not None:
        hits = WindowLimiter(HOOK_CALLS_PER_WINDOW, HOOK_WINDOW_S)

        async def hook_guard(request: Request) -> Response | None:
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            if hits.blocked(client, now):
                return _error(429, "rate_limited", "too many calls; slow down")
            hits.count(client, now)
            return None

        app.mount(PLUGIN_HOOKS, PluginRoutes(plugins, "hooks", hook_guard))
        app.mount(UI_PREFIX, PluginUi(plugins))
        manager = plugins

        @app.get("/", include_in_schema=False)
        async def home() -> Response:
            name = manager.host.home()
            if name is None:
                return _error(404, "not_found", "no dashboard: the web plugin is off")
            # Relative, so the service also works behind a proxy that adds a path prefix.
            return RedirectResponse(f"{UI_PREFIX.lstrip('/')}/{name}/", status_code=307)

    @app.get("/v1/sessions/{session_id}", dependencies=[authorized])
    async def session(session_id: str) -> Response:
        messages = await dispatcher.store.load(dispatcher.tenant_id, session_id)
        if not messages:
            return _error(404, "not_found", "no such session")
        return JSONResponse(
            {
                "session_id": session_id,
                "messages": [
                    {
                        "role": m.role,
                        "text": m.text(),
                        "tools": [b.name for b in m.blocks if isinstance(b, ToolUseBlock)],
                    }
                    for m in messages
                ],
            }
        )

    return app


def _challenge(status: int) -> dict[str, str] | None:
    return {"WWW-Authenticate": "Bearer"} if status == 401 else None


class PluginRoutes:
    """Hands a request under its mount point to the routes the plugin named next in the path registered;
    ``guard`` may answer first (a refused token, too many calls)."""

    def __init__(self, plugins: PluginManager, kind: Literal["admin", "hooks"], guard: Guard) -> None:
        self._plugins = plugins
        self._kind: Literal["admin", "hooks"] = kind
        self._guard = guard

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        refusal = await self._guard(Request(scope))
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        root: str = scope.get("root_path", "")
        path: str = scope["path"]
        name = (path[len(root) :] if path.startswith(root) else path).lstrip("/").partition("/")[0]
        target: ASGIApp | None = None
        if valid_channel_name(name):
            try:
                await self._plugins.refresh()
            except Exception:  # serve with the plugins as they are
                logger.warning("plugin refresh failed before a plugin route")
            target = self._plugins.host.routes(name, self._kind)
        if target is None:
            await _error(404, "not_found", "no such plugin route")(scope, receive, send)
            return
        await target({**scope, "root_path": f"{root}/{name}"}, receive, send)


def _add_activity_routes(app: FastAPI, authorized: Any, activity: Activity) -> None:
    """What the agent did: chat sessions (read, delete), the trace of each turn, the usage per day."""

    @app.get("/v1/admin/sessions", dependencies=[authorized])
    async def list_sessions(channel: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        return (await activity.sessions(channel=channel or None, search=q, page=page)).to_json()

    @app.get("/v1/admin/sessions/{session_id}", dependencies=[authorized])
    async def show_session(session_id: str) -> Response:
        found = await activity.session(session_id)
        if found is None:
            return _error(404, "not_found", "no such session")
        return JSONResponse(found)

    @app.delete("/v1/admin/sessions/{session_id}", dependencies=[authorized])
    async def delete_session(session_id: str) -> Response:
        if not await activity.delete_session(session_id):
            return _error(404, "not_found", "no such session")
        return JSONResponse({"deleted": session_id})

    @app.get("/v1/admin/traces", dependencies=[authorized])
    async def list_turns(
        channel: str = "", session_id: str = "", errors_only: bool = False, page: int = 0
    ) -> dict[str, Any]:
        turns = await activity.turns(
            channel=channel or None, session_id=session_id or None, errors_only=errors_only, page=page
        )
        return turns.to_json()

    @app.get("/v1/admin/traces/{turn_id}", dependencies=[authorized])
    async def show_turn(turn_id: str) -> Response:
        try:
            UUID(turn_id)
        except ValueError:
            return _error(404, "not_found", "no such turn")
        found = await activity.turn(turn_id)
        if found is None:
            return _error(404, "not_found", "no such turn")
        return JSONResponse(found)

    @app.get("/v1/admin/usage", dependencies=[authorized])
    async def usage(days: int = 14) -> dict[str, Any]:
        return await activity.usage(days)


def _add_admin_routes(
    app: FastAPI,
    gate: Gate,
    admin: ModelAdmin | None,
    plugins: PluginManager | None,
    channels: ChannelHub | None = None,
    jobs: JobRunner | None = None,
) -> None:
    """Model settings (read with the key masked, change, clear, test), the plugin manager, the plugins' own
    admin routes, and the state of channels and plugin jobs."""
    authorized = Depends(gate.dependency(ADMIN))
    if plugins is not None:
        _add_plugin_routes(app, plugins, authorized)
        app.mount(PLUGIN_ROUTES, PluginRoutes(plugins, "admin", gate.guard(ADMIN)))
        host = plugins.host

        @app.get("/v1/admin/ui", dependencies=[authorized])
        async def plugin_scripts() -> dict[str, Any]:
            """The scripts (and styles) the dashboard loads to add the enabled plugins' pages."""
            scripts: list[dict[str, Any]] = []
            for name in host.enabled():
                found = host.ui(name)
                if found is None or found[1].entry is None or inside(found[0], found[1].entry) is None:
                    continue
                folder, spec = found
                scripts.append(
                    {
                        "name": name,
                        "script": f"{UI_PREFIX}/{name}/{spec.entry}",
                        "styles": [f"{UI_PREFIX}/{name}/{s}" for s in spec.styles if inside(folder, s)],
                    }
                )
            return {"home": host.home(), "plugins": scripts}

    if jobs is not None:
        runner = jobs

        @app.get("/v1/admin/jobs", dependencies=[authorized])
        async def list_jobs() -> dict[str, Any]:
            return {"jobs": runner.status()}

    if channels is not None:
        hub = channels

        @app.get("/v1/admin/channels", dependencies=[authorized])
        async def list_channels() -> dict[str, Any]:
            return {"channels": hub.status()}

    if admin is None:
        return

    @app.get("/v1/admin/model", dependencies=[authorized])
    async def show_model() -> dict[str, Any]:
        return await admin.show()

    @app.patch("/v1/admin/model", dependencies=[authorized])
    async def change_model(body: ModelSettingsPatch) -> Response:
        try:
            shown = await admin.update({name: getattr(body, name) for name in body.model_fields_set})
        except SecretKeyMissingError as err:
            return _error(409, "no_encryption_key", str(err))
        return JSONResponse(shown)

    @app.delete("/v1/admin/model", dependencies=[authorized])
    async def clear_model() -> dict[str, Any]:
        return await admin.clear()

    @app.post("/v1/admin/model/list", dependencies=[authorized])
    async def list_provider_models(body: ModelListBody) -> Response:
        """The models the provider offers, for the list next to the model field; 502 with the error kind
        when the provider refuses (a wrong key, no listing endpoint)."""
        outcome = await admin.list_models(body.model_dump(exclude_none=True))
        return JSONResponse(outcome, status_code=200 if outcome["ok"] else 502)

    @app.post("/v1/admin/model/test", dependencies=[authorized])
    async def test_model() -> Response:
        outcome = await admin.test()
        return JSONResponse(outcome, status_code=200 if outcome["ok"] else 502)


def _add_plugin_routes(app: FastAPI, plugins: PluginManager, authorized: Any) -> None:
    """List, enable, disable, configure, install (folder, git, zip upload) and uninstall plugins."""

    @app.get("/v1/admin/plugins", dependencies=[authorized])
    async def list_plugins() -> Response:
        return await _plugin_call(_refreshed(plugins, plugins.list))

    @app.get("/v1/admin/plugins/{name}", dependencies=[authorized])
    async def show_plugin(name: str) -> Response:
        return await _plugin_call(_refreshed(plugins, lambda: plugins.show(name)))

    @app.post("/v1/admin/plugins/install", dependencies=[authorized])
    async def install_plugin(body: InstallBody) -> Response:
        if body.source == "folder":
            if body.path is None:
                return _error(422, "invalid", "give the folder's path")
            return await _plugin_call(plugins.install_folder(Path(body.path), enable=body.enable))
        if body.url is None:
            return _error(422, "invalid", "give the repository's url")
        return await _plugin_call(plugins.install_git(body.url, body.ref, enable=body.enable))

    @app.post(ZIP_INSTALL_PATH, dependencies=[authorized])
    async def install_zip(request: Request, enable: bool = False) -> Response:
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_ZIP_BYTES:
                return _error(413, "too_large", f"the zip may have at most {MAX_ZIP_BYTES} bytes")
        return await _plugin_call(plugins.install_zip(bytes(data), enable=enable))

    @app.post("/v1/admin/plugins/{name}/enable", dependencies=[authorized])
    async def enable_plugin(name: str, body: PluginSettingsBody | None = None) -> Response:
        return await _plugin_call(plugins.enable(name, body.settings if body else None))

    @app.post("/v1/admin/plugins/{name}/disable", dependencies=[authorized])
    async def disable_plugin(name: str) -> Response:
        return await _plugin_call(plugins.disable(name))

    @app.patch("/v1/admin/plugins/{name}/settings", dependencies=[authorized])
    async def configure_plugin(name: str, body: PluginSettingsBody) -> Response:
        return await _plugin_call(plugins.configure(name, body.settings))

    @app.delete("/v1/admin/plugins/{name}", dependencies=[authorized])
    async def uninstall_plugin(name: str) -> Response:
        async def work() -> dict[str, Any]:
            await plugins.uninstall(name)
            return {"uninstalled": name}

        return await _plugin_call(work())


async def _refreshed(plugins: PluginManager, read: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    await plugins.refresh()
    return await read()


async def _plugin_call(work: Awaitable[dict[str, Any]]) -> Response:
    try:
        return JSONResponse(await work)
    except PluginNotFoundError as err:
        return _error(404, "not_found", str(err))
    except SecretKeyMissingError as err:
        return _error(409, "no_encryption_key", str(err))
    except PluginError as err:
        return _error(422, "plugin_error", str(err))


def _inbound(body: ChatRequest) -> InboundMessage:
    return InboundMessage(
        channel=CHANNEL,
        conversation_id=body.conversation_id or body.user_id,
        user_id=body.user_id,
        message_id=body.message_id,
        text=body.text,
    )


def _status(record: IngressRecord) -> dict[str, Any]:
    status: dict[str, Any] = {
        "ingress_id": record.id,
        "session_id": record.session_id,
        "status": record.status,
        "attempts": record.attempts,
    }
    if record.reply is not None:
        status["reply"] = record.reply.to_json()
    if record.error_kind is not None:
        status["error_kind"] = record.error_kind
    if record.delivery is not None:
        status["delivery"] = {
            "status": record.delivery,
            "attempts": record.delivery_attempts,
            "parts_sent": record.delivered_parts,
            "error": record.delivery_error,
        }
    return status


def _answer(record: IngressRecord) -> Response:
    if record.status == "done" and record.reply is not None:
        return JSONResponse(
            {"ingress_id": record.id, "session_id": record.session_id, **record.reply.to_json()}
        )
    if not record.finished:
        return JSONResponse(
            {"ingress_id": record.id, "session_id": record.session_id, "status": record.status},
            status_code=202,
            headers={"Location": f"/v1/ingress/{record.id}"},
        )
    kind = record.error_kind or "unknown"
    return _error(ERROR_STATUS.get(kind, 500), kind, "the agent could not answer this message", record.id)


def _error(status: int, kind: str, message: str, ingress_id: int | None = None) -> JSONResponse:
    error: dict[str, Any] = {"kind": kind, "message": message}
    if ingress_id is not None:
        error["ingress_id"] = ingress_id
    return JSONResponse({"error": error}, status_code=status)


def _sse(data: dict[str, Any]) -> str:
    event = data.get("event", "message")
    payload = {key: value for key, value in data.items() if key != "event"}
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream(
    dispatcher: Dispatcher, observer: StreamObserver, record: IngressRecord, *, duplicate: bool
) -> AsyncGenerator[str]:
    """Live events of the run, then ``done`` or ``error``. A client that goes away does not stop the run;
    a run finished by another process is reported once its record is final."""
    yield _sse(
        {
            "event": "accepted",
            "ingress_id": record.id,
            "session_id": record.session_id,
            "duplicate": duplicate,
        }
    )
    try:
        while not record.finished:
            try:
                event = await asyncio.wait_for(observer.events.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                yield ": ping\n\n"
                record = await dispatcher.wait(record.id, 0)
                continue
            if event is None:
                record = await dispatcher.wait(record.id, 0)
                break
            yield _sse(event)
        if record.status == "done" and record.reply is not None:
            yield _sse({"event": "done", "ingress_id": record.id, **record.reply.to_json()})
        else:
            yield _sse({"event": "error", "ingress_id": record.id, "kind": record.error_kind or "unknown"})
    finally:
        dispatcher.unwatch(record.id)
