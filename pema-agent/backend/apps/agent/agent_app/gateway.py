"""HTTP gateway: a trusted backend (the clinic) sends user messages and gets the agent's replies.

The caller authenticates with a bearer service token. It names the person speaking (``user_id``) and
optionally the conversation; the session is derived from them on the server, so a reply always belongs to the
conversation it came from. Every message is stored before it runs and a ``message_id`` sent twice runs once.
A reply not ready within ``wait_s`` is answered with 202 and can be fetched from ``/v1/ingress/{id}``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import time
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text as sql

from agent_app.dispatcher import Dispatcher, StreamObserver
from agent_app.ingress import IngressRecord
from agent_app.model_factory import Provider
from agent_app.model_settings import ModelAdmin, SecretKeyMissingError
from agent_app.plugins.install import MAX_ZIP_BYTES
from agent_app.plugins.manager import PluginManager, PluginNotFoundError
from agent_app.plugins.manifest import PluginError
from agent_app.storage import AgentDatabase
from agentcore import ReasoningEffort, ToolUseBlock
from agentcore.channels import InboundMessage
from agentcore.harness.model.reasoning import OpenAIDialect

CHANNEL: Final = "http"
TOKEN_ENV: Final = "AGENT_GATEWAY_TOKEN"  # noqa: S105 - the name of the variable, not a token
ADMIN_TOKEN_ENV: Final = "AGENT_ADMIN_TOKEN"  # noqa: S105 - the name of the variable, not a token
ADMIN_FAILURES_PER_WINDOW: Final = 5
ADMIN_FAILURE_WINDOW_S: Final = 60.0
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
    token: str
    wait_s: float = DEFAULT_WAIT_S
    admin_token: str | None = None
    """Enables ``/v1/admin/*``; must differ from ``token`` so the chat caller cannot change the model."""

    def __post_init__(self) -> None:
        if len(self.token) < MIN_TOKEN_CHARS:
            raise ValueError(f"{TOKEN_ENV} must have at least {MIN_TOKEN_CHARS} characters")
        if self.admin_token is not None:
            if len(self.admin_token) < MIN_TOKEN_CHARS:
                raise ValueError(f"{ADMIN_TOKEN_ENV} must have at least {MIN_TOKEN_CHARS} characters")
            if hmac.compare_digest(self.admin_token, self.token):
                raise ValueError(f"{ADMIN_TOKEN_ENV} must differ from {TOKEN_ENV}")


class FailureLimiter:
    """Refuses a client after ``limit`` failed logins within ``window_s``, until the window moves on."""

    def __init__(
        self, limit: int = ADMIN_FAILURES_PER_WINDOW, window_s: float = ADMIN_FAILURE_WINDOW_S
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._failures: dict[str, deque[float]] = {}

    def blocked(self, client: str, now: float) -> bool:
        failures = self._failures.get(client)
        if failures is None:
            return False
        while failures and now - failures[0] >= self._window_s:
            failures.popleft()
        if not failures:
            del self._failures[client]
            return False
        return len(failures) >= self._limit

    def failed(self, client: str, now: float) -> None:
        self._failures.setdefault(client, deque()).append(now)


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
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        sweeper = asyncio.create_task(dispatcher.run_sweeper(), name="ingress sweeper")
        try:
            yield
        finally:
            sweeper.cancel()
            await asyncio.gather(sweeper, return_exceptions=True)
            await dispatcher.close()

    app = FastAPI(title="agent gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    authorized = Depends(_bearer(settings.token))

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

    if settings.admin_token is not None and (admin is not None or plugins is not None):
        _add_admin_routes(app, settings.admin_token, admin, plugins)

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


def _bearer(expected: str) -> Callable[[str | None], Awaitable[None]]:
    wanted = expected.encode("utf-8")

    async def check(authorization: str | None = Header(default=None)) -> None:
        if not _token_matches(authorization, wanted):
            raise HTTPException(
                401, detail="a valid bearer token is required", headers={"WWW-Authenticate": "Bearer"}
            )

    return check


def _token_matches(authorization: str | None, wanted: bytes) -> bool:
    scheme, _, token = (authorization or "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode("utf-8"), wanted)


def _add_admin_routes(
    app: FastAPI, token: str, admin: ModelAdmin | None, plugins: PluginManager | None
) -> None:
    """Model settings, as zalo-agent's dashboard has them: read (key masked), change, clear, test; and the
    plugin manager."""
    wanted = token.encode("utf-8")
    limiter = FailureLimiter()

    async def check(request: Request, authorization: str | None = Header(default=None)) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if limiter.blocked(client, now):
            raise HTTPException(429, detail="too many failed attempts; try again later")
        if not _token_matches(authorization, wanted):
            limiter.failed(client, now)
            raise HTTPException(
                401, detail="a valid admin token is required", headers={"WWW-Authenticate": "Bearer"}
            )

    authorized = Depends(check)
    if plugins is not None:
        _add_plugin_routes(app, plugins, authorized)
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
