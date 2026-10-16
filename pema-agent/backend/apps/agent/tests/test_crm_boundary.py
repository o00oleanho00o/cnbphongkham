"""The agent never reaches the clinic's CRM (.claude/rules/agent-crm-boundary.md). T4 reads the clinic profile:
the only address of the API it may hold is where the public keys are. T1 reads the rights of ``agent_rt_app`` on
the server of ``PEMA_TEST_DATABASE_URL`` (read only: the role belongs to the whole cluster)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text as sql

from agent_app.db_roles import RUNTIME_ROLE, SCHEMA
from agent_app.profile import load_profile

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

    assert list(found) == ["sso.jwks_url"]
    assert found["sso.jwks_url"].endswith("/.well-known/jwks.json")


CRM_DATABASE = "pema"


@pytest.mark.db
def test_the_agents_role_cannot_connect_to_the_crm_database_nor_use_another_schema() -> None:
    """T1 (L1): no CONNECT on the clinic's database, no USAGE on schemas but its own, no way across databases"""
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
            crm_connect = conn.execute(
                sql(
                    "SELECT has_database_privilege(:r, datname, 'CONNECT') FROM pg_database WHERE datname = :db"
                ),
                {"r": RUNTIME_ROLE, "db": CRM_DATABASE},
            ).scalar_one_or_none()
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

    assert crm_connect is not True, f"{RUNTIME_ROLE} may connect to the CRM database {CRM_DATABASE}"
    assert set(schemas) <= {SCHEMA, "public"}
    assert bridges == []
