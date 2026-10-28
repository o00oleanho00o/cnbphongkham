"""The service: builds the FastAPI app and starts what runs beside it.

* ``/v1/plugins/zalo/...``: the admin routes of the old plugin (same paths and shapes), behind the staff SSO
  token;
* ``/v1/hooks/zalo/...``: the bot webhook and the bridge's events, each with its own secret check;
* ``/send``, ``/typing``, ``/health``: what the agent calls, signed with the connector key (``callback.py``);
* ``/v1/admin/ui`` and ``/ui/...``: the admin page the clinic web proxies (protocol, section 5);
* ``/ready``: open, for the container's health check (it reveals nothing).

In the lifespan: the service loop (accounts, bridge, friends), the pusher of the outbox to the agent and the
sender of accepted replies.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Final

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from .agent_client import AgentClient
from .auth import KeySet, StaffTokens, require_admin
from .bot.client import BotApiClient, tao_zalo_bot_client
from .callback import Sender, callback_router
from .config import Config, ConfigError
from .personal.client import BridgeClient
from .routes import account_routes, hook_routes
from .seal import Seal
from .service import ZaloService
from .store import Store

PRUNE_EVERY_S: Final = 3600.0
UI_ENTRY: Final = {"name": "zalo", "script": "/ui/client.js", "styles": []}

logger = logging.getLogger(__name__)


class _Ui(StaticFiles):
    """The built admin page; its entry script is never cached, so a new build shows at once."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path == "client.js":
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    config: Config | None = None,
    *,
    agent_transport: httpx.AsyncBaseTransport | None = None,
    jwks_transport: httpx.AsyncBaseTransport | None = None,
    bot_client: Callable[[str], BotApiClient] = tao_zalo_bot_client,
    bridge: BridgeClient | None = None,
) -> FastAPI:
    """The transports, the bot client and the bridge are only passed by something that runs the app against
    fakes (a script); the service itself passes none."""
    config = config or Config.from_env()
    store = Store(config.data_dir / "zalo.db")
    agent = AgentClient(
        store,
        agent_url=config.agent_url,
        callback_url=config.callback_url,
        connector=config.connector_name,
        key=config.connector_key,
        transport=agent_transport,
    )
    service = ZaloService(config, store, Seal(config.secret_key), agent, bot_client=bot_client, bridge=bridge)
    sender = Sender(config, service, store)
    keys = KeySet(config.crm_jwks_url, transport=jwks_transport) if config.crm_jwks_url else None
    tokens = StaffTokens(config.sso_issuer, config.sso_audience, config.crm_jwks_url, keys=keys)
    admin = Depends(require_admin(tokens))

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not config.connector_key:
            logger.error("CONNECTOR_KEY is not set: this service cannot talk to the agent (messages wait here)")
        if not config.crm_jwks_url:
            logger.error("CRM_JWKS_URL is not set: the admin routes answer 503")
        service.start()
        jobs = [
            asyncio.create_task(agent.run(), name="outbox pusher"),
            asyncio.create_task(sender.run(), name="reply sender"),
            asyncio.create_task(_prune_forever(sender), name="delivery prune"),
        ]
        try:
            yield
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            await service.close()
            await agent.close()
            store.close()

    app = FastAPI(title="Zalo connector", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(callback_router(config, sender))
    app.include_router(account_routes(service), prefix="/v1/plugins/zalo", dependencies=[admin])
    app.include_router(hook_routes(service), prefix="/v1/hooks/zalo")

    @app.get("/ready")
    async def ready() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/admin/ui", dependencies=[admin])
    async def admin_ui() -> dict[str, Any]:
        return UI_ENTRY

    if config.ui_dir.is_dir():
        app.mount("/ui", _Ui(directory=config.ui_dir), name="ui")
    else:
        logger.warning("the admin page is not built: %s is not a folder", config.ui_dir)

    @app.middleware("http")
    async def no_store(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/ui/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.state.service, app.state.agent, app.state.store, app.state.sender = service, agent, store, sender
    return app


async def _prune_forever(sender: Sender) -> None:
    while True:
        try:
            await sender.prune()
        except Exception as err:  # the next hour tries again
            logger.warning("old deliveries not pruned (%s)", type(err).__name__)
        await asyncio.sleep(PRUNE_EVERY_S)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every URL at INFO, and a Zalo Bot API URL carries the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        config = Config.from_env()
    except ConfigError as err:
        logger.error("cannot start: %s", err)
        sys.exit(2)
    uvicorn.run(create_app(config), host="0.0.0.0", port=config.port, log_level="info")  # noqa: S104
