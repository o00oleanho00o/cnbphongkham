"""The wired app (``StaffSessionMiddleware`` enforcing) must let a gateway call reach the route, which verifies the
short token of crm-signer itself; every other route under /api/v1 still needs the staff cookie. The route tests
of the gateway use a bare app where the middleware does not enforce, so they cannot see this."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from pema.composition.auth_bridge import StaffSessionMiddleware
from pema.config.env import get_settings


async def _reached(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("reached")


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """The middleware reads the settings; a cached copy would leak into the tests that set the environment."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _wired() -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/v1/agent-gateway/free-slots", _reached),
            Route("/api/v1/patients", _reached),
        ]
    )
    app.add_middleware(StaffSessionMiddleware, db=lambda: None, enforce=lambda: True)  # type: ignore[arg-type]
    return app


@pytest.mark.parametrize(
    ("path", "status"),
    [("/api/v1/agent-gateway/free-slots", 200), ("/api/v1/patients", 401)],
)
async def test_only_the_gateway_skips_the_staff_cookie(path: str, status: int) -> None:
    transport = httpx.ASGITransport(app=_wired())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(path)).status_code == status
