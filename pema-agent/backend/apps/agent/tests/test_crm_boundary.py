"""The agent never reaches the clinic's CRM (.claude/rules/agent-crm-boundary.md). T4 reads the clinic profile:
the only address of the API it may hold is where the public keys are. T1 needs ``PEMA_TEST_DATABASE_URL``."""

from __future__ import annotations

from pathlib import Path

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
