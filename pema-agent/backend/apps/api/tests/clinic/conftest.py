"""Fixtures of the clinic tests. They live in ``pema.api.clinic_testing`` (shared with ``tests/api``)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.agent_gateway_auth import reset_agent_gateway_limits
from pema.api.clinic_testing import (
    admin,
    app,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    world,
)
from pema.api.gateway_testing import KEY, Save, Signer, person, public
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.env import get_settings

__all__ = [
    "admin",
    "app",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "pg_url",
    "world",
]


@pytest.fixture
def gateway_on(monkeypatch: pytest.MonkeyPatch, jwt_env: None) -> Iterator[None]:
    monkeypatch.setenv("PEMA_AGENT_GATEWAY_PUBLIC_KEYS", public(KEY))
    get_settings.cache_clear()
    reset_agent_gateway_limits()
    yield
    get_settings.cache_clear()
    reset_agent_gateway_limits()


@pytest_asyncio.fixture
async def agent(app: FastAPI, gateway_on: None, world: SeedResult) -> AsyncIterator[httpx.AsyncClient]:
    """The agent's client, on the seeded clinic (three doctors)."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", auth=Signer()) as http:
        yield http


@pytest.fixture
def saved(agent: httpx.AsyncClient) -> Save:
    """A person with a saved contact; returns their path."""

    async def make(
        name: str = "Khách thử (mẫu)", phone: str = "0912 000 111", consent: bool | None = None
    ) -> str:
        path = person()
        response = await agent.put(
            path, json={"full_name": name, "phone": phone, "messages_consent": consent}
        )
        assert response.status_code == 200, response.text
        return path

    return make
