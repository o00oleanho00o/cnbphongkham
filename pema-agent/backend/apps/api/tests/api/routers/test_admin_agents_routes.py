# ported from: src/server/routes/agent-routes.ts
"""``agent-routes.ts`` has no test file in the original. These tests (new, same style) pin what its comments
promise: the default agent always exists, ids are kebab-case and unique, the context window cannot slip below the
cross-check with the output cap, unknown tools are refused at the edge, an agent in use cannot be deleted; plus what
this port adds: the permission guard and the rule that LOOSENING the policy profile needs ``admin.policy``.
"""

from __future__ import annotations

import pytest

from pema.api.routers.admin_stores_testing import ADMIN_AGENTS_AND_POLICY, API, Harness

pytestmark = pytest.mark.db


async def _create(h: Harness, agent_id: str = "tu-van", **extra: object):
    body = {"id": agent_id, "name": "Tư Vấn", "icon": "💼", "persona": "Bạn là tư vấn viên", **extra}
    return await h.client.post(f"{API}/agents", json=body, headers=h.headers())


async def test_agents_list_always_contains_the_default_agent_for_the_ui_to_attach_accounts(
    h: Harness,
) -> None:
    """ensureDefaultAgent: UI luôn có ít nhất agent mặc định để gắn account"""
    res = await h.client.get(f"{API}/agents", headers=h.headers())
    assert res.status_code == 200
    agents = res.json()
    assert [(a["id"], a["is_default"]) for a in agents] == [("tro-ly-mac-dinh", True)]
    assert agents[0]["policy_profile"] == "patient_channel"
    assert agents[0]["account_count"] == 2, "the harness clinic has two accounts on the default agent"


async def test_agents_create_returns_201_with_the_safe_default_profile(h: Harness) -> None:
    """tạo agent: 201, hồ sơ mặc định là patient_channel"""
    res = await _create(h)
    assert res.status_code == 201
    body = res.json()
    assert (body["id"], body["name"], body["icon"], body["policy_profile"]) == (
        "tu-van",
        "Tư Vấn",
        "💼",
        "patient_channel",
    )
    assert h.audits[-1][:3] == ("agent.create", "agent", "tu-van")


async def test_agents_create_with_an_existing_id_is_a_409(h: Harness) -> None:
    """Agent id đã tồn tại thì 409"""
    assert (await _create(h)).status_code == 201
    res = await _create(h)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "invalid_state"


@pytest.mark.parametrize("bad_id", ["Tư Vấn", "-bat-dau-gach", "co khoang trang", "UPPER"])
async def test_agents_create_with_a_non_kebab_case_id_is_rejected(h: Harness, bad_id: str) -> None:
    """id phải là kebab-case"""
    res = await _create(h, bad_id)
    assert res.status_code == 422


async def test_agents_patch_edits_persona_and_model_override_and_a_null_clears_it(h: Harness) -> None:
    """sửa persona + model override; clear_model_override đưa về cấu hình chung"""
    await _create(h)
    res = await h.client.patch(
        f"{API}/agents/tu-van",
        json={
            "persona": "Bạn là tư vấn viên khóa học",
            "model_provider": "anthropic",
            "model_name": "m",
            "max_steps": 4,
        },
        headers=h.headers(),
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["persona"], body["model_provider"], body["max_steps"]) == (
        "Bạn là tư vấn viên khóa học",
        "anthropic",
        4,
    )

    cleared = await h.client.patch(
        f"{API}/agents/tu-van", json={"clear_model_override": True}, headers=h.headers()
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert (body["model_provider"], body["model_name"], body["max_steps"]) == (None, None, None)
    assert body["persona"] == "Bạn là tư vấn viên khóa học", "chỉ xóa override, giữ persona"


async def test_agents_patch_of_a_missing_agent_is_404(h: Harness) -> None:
    """Agent không tồn tại thì 404"""
    res = await h.client.patch(f"{API}/agents/khong-co", json={"name": "x"}, headers=h.headers())
    assert res.status_code == 404


async def test_agents_patch_context_window_too_low_for_the_output_cap_is_refused(h: Harness) -> None:
    """ràng buộc chéo: 4.000 với LLM_MAX_OUTPUT_TOKENS mặc định 16.384 là lọt qua trước đây, nay phải bị từ chối"""
    await _create(h)
    res = await h.client.patch(f"{API}/agents/tu-van", json={"context_window": 4000}, headers=h.headers())
    assert res.status_code == 422
    assert "Trần ngữ cảnh" in res.json()["error"]["message"]

    ok = await h.client.patch(f"{API}/agents/tu-van", json={"context_window": 64000}, headers=h.headers())
    assert ok.status_code == 200
    assert ok.json()["context_window"] == 64000


@pytest.mark.parametrize(
    "patch",
    [{"max_steps": 31}, {"context_window": 3000}, {"context_window": 2_000_001}],
)
async def test_agents_patch_out_of_range_values_of_the_original_schema_are_refused(
    h: Harness, patch: dict[str, int]
) -> None:
    """biên của zod schema gốc: maxSteps 1..30, contextWindow 4.000..2.000.000"""
    await _create(h)
    res = await h.client.patch(f"{API}/agents/tu-van", json=patch, headers=h.headers())
    assert res.status_code == 422


async def test_agents_patch_unknown_tool_key_is_refused_at_the_edge(h: Harness) -> None:
    """chặn key tool lạ ngay ở biên bằng danh mục tool"""
    await _create(h)
    bad = await h.client.patch(
        f"{API}/agents/tu-van", json={"disabled_tools": ["web_search", "khong-co-tool"]}, headers=h.headers()
    )
    assert bad.status_code == 422
    assert "khong-co-tool" in bad.json()["error"]["message"]

    good = await h.client.patch(
        f"{API}/agents/tu-van",
        json={"disabled_tools": ["web_search", "create_image", "appointment.book"]},
        headers=h.headers(),
    )
    assert good.status_code == 200
    assert good.json()["disabled_tools"] == ["web_search", "create_image", "appointment.book"]


async def test_agents_delete_refused_while_an_account_uses_it_then_allowed(h: Harness) -> None:
    """không xóa được agent đang có account dùng; xóa được khi không ai dùng"""
    await _create(h)
    await h.stores.accounts.update_account(h.env.clinic_id, "acc-1", {"agent_id": "tu-van"})

    refused = await h.client.delete(f"{API}/agents/tu-van", headers=h.headers())
    assert refused.status_code == 409
    assert "account dùng" in refused.json()["error"]["message"]
    listed = (await h.client.get(f"{API}/agents", headers=h.headers())).json()
    assert {a["id"]: a["account_count"] for a in listed}["tu-van"] == 1

    await h.stores.accounts.update_account(h.env.clinic_id, "acc-1", {"agent_id": "tro-ly-mac-dinh"})
    assert (await h.client.delete(f"{API}/agents/tu-van", headers=h.headers())).status_code == 204
    assert (await h.client.delete(f"{API}/agents/tu-van", headers=h.headers())).status_code == 404


async def test_agents_delete_of_the_default_agent_is_refused(h: Harness) -> None:
    """không xóa được agent mặc định"""
    default = (await h.client.get(f"{API}/agents", headers=h.headers())).json()[0]["id"]
    res = await h.client.delete(f"{API}/agents/{default}", headers=h.headers())
    assert res.status_code == 409


async def test_agents_every_route_needs_a_session_and_the_admin_agents_permission(h: Harness) -> None:
    """(thêm) không đăng nhập 401; thiếu quyền admin.agents 403 - kể cả với route chỉ đọc"""
    for method, path in (
        ("GET", "/agents"),
        ("POST", "/agents"),
        ("PATCH", "/agents/x"),
        ("DELETE", "/agents/x"),
    ):
        anonymous = await h.client.request(
            method, f"{API}{path}", json={"id": "x", "name": "x"} if method != "GET" else None
        )
        assert anonymous.status_code == 401, (method, path)
        forbidden = await h.client.request(
            method,
            f"{API}{path}",
            headers=h.headers("patient.read"),
            json={"id": "x", "name": "x"} if method != "GET" else None,
        )
        assert forbidden.status_code == 403, (method, path)


# ----------------------------------------------------------------- policy_profile: loosening needs admin.policy


async def test_agents_creating_a_staff_assistant_agent_needs_the_policy_permission(h: Harness) -> None:
    """(thêm) tạo agent staff_assistant (nới an toàn) cần thêm quyền admin.policy"""
    refused = await _create(h, policy_profile="staff_assistant")
    assert refused.status_code == 403
    assert await h.stores.agents.get_agent(h.env.clinic_id, "tu-van") is None

    allowed = await h.client.post(
        f"{API}/agents",
        json={"id": "tu-van", "name": "T", "policy_profile": "staff_assistant"},
        headers=h.headers(ADMIN_AGENTS_AND_POLICY),
    )
    assert allowed.status_code == 201
    assert allowed.json()["policy_profile"] == "staff_assistant"


async def test_agents_loosening_the_profile_needs_the_policy_permission_tightening_does_not(
    h: Harness,
) -> None:
    """(thêm) đổi sang staff_assistant cần admin.policy; đổi ngược về patient_channel (siết) thì không"""
    await _create(h)
    refused = await h.client.patch(
        f"{API}/agents/tu-van", json={"policy_profile": "staff_assistant"}, headers=h.headers()
    )
    assert refused.status_code == 403
    still = await h.stores.agents.get_agent(h.env.clinic_id, "tu-van")
    assert still is not None
    assert still.policy_profile.value == "patient_channel"

    loosened = await h.client.patch(
        f"{API}/agents/tu-van",
        json={"policy_profile": "staff_assistant"},
        headers=h.headers(ADMIN_AGENTS_AND_POLICY),
    )
    assert loosened.status_code == 200
    assert h.audits[-1][3]["loosens_policy"] is True

    tightened = await h.client.patch(
        f"{API}/agents/tu-van", json={"policy_profile": "patient_channel"}, headers=h.headers()
    )
    assert tightened.status_code == 200
    assert tightened.json()["policy_profile"] == "patient_channel"

    other_field = await h.client.patch(f"{API}/agents/tu-van", json={"name": "Đổi tên"}, headers=h.headers())
    assert other_field.status_code == 200, "sửa trường khác không đụng tới hồ sơ thì không cần admin.policy"
