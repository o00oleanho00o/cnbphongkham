"""The agent never reaches the clinic's CRM (.claude/rules/agent-crm-boundary.md). T4 reads the clinic profile:
the only address of the API it may hold is where the public keys are. T1 reads the rights of ``agent_rt_app`` on
the server of ``PEMA_TEST_DATABASE_URL`` (read only: the role belongs to the whole cluster). T5: a tool that
fetches a URL cannot land on this host or the private network of the stack (the CRM API among them), however the
address is written, resolved or reached through a redirect; the DNS is a table and the network a mock."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy import text as sql

from agent_app.db_roles import RUNTIME_ROLE, SCHEMA
from agent_app.profile import load_profile
from agentcore.harness.tools.builtin.netguard import FetchError, fetch

CLINIC = Path(__file__).resolve().parents[1] / "agents" / "clinic"
API_HOST = "api:8000"


def test_the_clinic_profile_holds_no_way_into_the_api_but_its_public_keys() -> None:
    profile = load_profile(CLINIC)

    found = {
        f"{plugin}.{key}": value
        for plugin in profile.plugins.enabled
        for key, value in profile.plugins.config(plugin).items()
        if isinstance(value, str) and API_HOST in value
    }

    # only where the CRM's public keys are: SSO tokens (sso) and events (crm) are checked with them
    assert sorted(found) == ["crm.events_jwks_url", "sso.jwks_url"]
    assert all(url.endswith("/.well-known/jwks.json") for url in found.values())


def test_the_crm_plugin_reaches_the_crm_only_through_crm_signer_and_holds_no_secret() -> None:
    """docs/PLAN-crm-plugin.md 4: the plugin calls crm-signer, which holds the key; nothing in the profile looks
    like a key or a password."""
    profile = load_profile(CLINIC)

    assert profile.plugins.config("crm")["base_url"].startswith("http://crm-signer:")
    values = [
        value
        for plugin in profile.plugins.enabled
        for value in profile.plugins.config(plugin).values()
        if isinstance(value, str)
    ]
    assert not [v for v in values if re.search(r"[A-Za-z0-9+/_=-]{32,}", v)]
    assert not [v for v in values if re.search(r"(?i)(secret|password|token|api[_-]?key)=", v)]


CRM_DATABASE = "pema"
AGENT_DATABASE = "pema_agent"


@pytest.mark.db
def test_the_agents_role_cannot_connect_to_the_crm_database_nor_use_another_schema() -> None:
    """T1 (L1): CONNECT on its own database only, no USAGE on schemas but its own, no way across databases"""
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if (
                conn.execute(sql("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first()
                is None
            ):
                pytest.skip(f"{RUNTIME_ROLE} does not exist on this server")
            reachable = set(
                conn.execute(
                    sql(
                        "SELECT datname FROM pg_database WHERE datallowconn "
                        "AND has_database_privilege(:r, datname, 'CONNECT')"
                    ),
                    {"r": RUNTIME_ROLE},
                )
                .scalars()
                .all()
            )
            own = conn.execute(sql("SELECT current_database()")).scalar_one()
            schemas = (
                conn.execute(
                    sql(
                        "SELECT nspname FROM pg_namespace WHERE has_schema_privilege(:r, oid, 'USAGE') "
                        r"AND nspname NOT LIKE 'pg\_%' AND nspname <> 'information_schema'"
                    ),
                    {"r": RUNTIME_ROLE},
                )
                .scalars()
                .all()
            )
            bridges = conn.execute(
                sql("SELECT extname FROM pg_extension WHERE extname IN ('dblink', 'postgres_fdw')")
            ).all()
    finally:
        engine.dispose()

    assert CRM_DATABASE not in reachable, f"{RUNTIME_ROLE} may connect to the CRM database {CRM_DATABASE}"
    assert reachable <= {own, AGENT_DATABASE}, f"{RUNTIME_ROLE} may connect to {sorted(reachable)}"
    assert set(schemas) <= {SCHEMA, "public"}
    assert bridges == []


# --- T5 (L6): fetching a URL never reaches the stack's own network ---

# the names of the compose stack and what the network answers for them
DOCKER_DNS = {
    "localhost": ["127.0.0.1", "::1"],
    "api": ["172.18.0.4"],
    "db": ["172.18.0.2"],
    "postgres": ["172.18.0.2"],
    "redis": ["172.18.0.3"],
    "agent": ["172.18.0.5"],
    "frontend": ["172.18.0.6"],
    "rebind.example": ["127.0.0.1"],
    "metadata.example": ["169.254.169.254"],
    "dual.example": ["10.0.0.9", "192.168.1.9"],
    "site.example": ["93.184.216.34"],
}
INTERNAL_URLS = [
    "http://localhost/",
    "http://localhost:8000/api/v1/.well-known/jwks.json",
    "http://127.0.0.1/",
    "http://127.1.2.3:8088/v1/admin/model",
    "http://0.0.0.0:8000/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:7f00:1]/",
    "http://[fe80::1]/",
    "http://[fd00::1]/",
    "http://10.0.0.5/",
    "http://172.16.0.1/",
    "http://172.31.255.255/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://api:8000/api/v1/.well-known/jwks.json",
    "http://api:8000/",
    "http://db:5432/",
    "http://postgres:5432/",
    "http://redis:6379/",
    "http://agent:8088/v1/admin/model",
    "http://frontend:3000/",
    "http://rebind.example/",
    "http://metadata.example/latest/meta-data/",
    "http://dual.example/",
]


def _page(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="reached")


async def _docker_dns(host: str, port: int) -> list[str]:
    return DOCKER_DNS[host]


async def _fetch_through_mock(url: str, handler: Callable[[httpx.Request], httpx.Response] = _page) -> str:
    page = await fetch(url, resolver=_docker_dns, transport=httpx.MockTransport(handler))
    return page.data.decode()


@pytest.mark.parametrize("url", INTERNAL_URLS)
async def test_a_url_into_the_hosts_or_stacks_own_network_is_refused(url: str) -> None:
    """T5 (L6)"""
    reached: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return _page(request)

    with pytest.raises(FetchError) as refused:
        await _fetch_through_mock(url, spy)

    assert refused.value.kind == "blocked"
    assert reached == [], f"the request to {url} went out"


@pytest.mark.parametrize("url", INTERNAL_URLS)
async def test_a_redirect_from_a_public_site_into_it_is_refused_too(url: str) -> None:
    """T5 (L6)"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "site.example":
            return httpx.Response(302, headers={"location": url})
        raise AssertionError(f"the redirect to {url} went out")

    with pytest.raises(FetchError) as refused:
        await _fetch_through_mock("https://site.example/start", handler)

    assert refused.value.kind == "blocked"


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://site.example/x", "gopher://site.example/", "dict://site.example/"]
)
async def test_a_url_that_is_not_http_is_refused(url: str) -> None:
    """T5 (L6)"""
    with pytest.raises(FetchError) as refused:
        await _fetch_through_mock(url)

    assert refused.value.kind == "scheme"


async def test_a_public_site_is_still_reachable() -> None:
    """T5 (L6): the guard refuses the stack's network, not the web"""
    assert await _fetch_through_mock("https://site.example/") == "reached"


@pytest.mark.parametrize("url", ["http://localhost/", "http://localhost:8000/", "http://127.0.0.1:8000/"])
async def test_the_systems_own_resolver_gives_no_way_to_localhost(url: str) -> None:
    """T5 (L6): with the real DNS lookup (no network is needed to resolve localhost) and the real transport"""
    reached: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return _page(request)

    with pytest.raises(FetchError):
        await fetch(url, transport=httpx.MockTransport(spy))

    assert reached == []


async def test_the_real_transport_never_connects_to_a_blocked_address() -> None:
    """T5 (L6): no transport given, so the pinned connection pool is the one in use; a port nobody listens on
    would answer 'network', a blocked address must be 'blocked' before any connection is tried"""
    outcomes: dict[str, str] = {}
    for url in ("http://127.0.0.1:9/", "http://[::1]:9/", "http://localhost:9/"):
        with pytest.raises(FetchError) as refused:
            await fetch(url)
        outcomes[url] = refused.value.kind

    assert set(outcomes.values()) == {"blocked"}
