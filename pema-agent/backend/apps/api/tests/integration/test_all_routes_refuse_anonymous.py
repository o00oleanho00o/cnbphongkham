"""Default deny: EVERY route of the wired application refuses an anonymous caller (package G, no TS source).

``test_admin_access_matrix`` proves 14 admin families with one GET each. This test walks the whole OpenAPI of
the real application (``create_app`` with its lifespan, the way production runs it) and calls every operation
with no session cookie and an empty JSON body. The only routes that may answer anything but 401 are the ones
that authenticate in another way, listed in ``PUBLIC``: the login, the two signed webhooks (they must still
refuse a call without the right secret or signature). A new route added without a guard fails this test.
"""

from __future__ import annotations

import pytest

from pema.composition.testing import LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]

PUBLIC: frozenset[tuple[str, str]] = frozenset(
    {
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/webhooks/zalo-bot/{account_id}"),
        ("post", "/api/v1/webhooks/zalo-bridge/{account_id}"),
        ("get", "/healthz"),
    }
)


def _concrete(path: str) -> str:
    out = path
    while "{" in out:
        start = out.index("{")
        out = out[:start] + "00000000-0000-0000-0000-000000000000" + out[out.index("}") + 1 :]
    return out


async def test_moi_route_tu_choi_nguoi_goi_an_danh_tru_dang_nhap_va_hai_webhook_co_chu_ky(
    make_loop: LoopFactory,
) -> None:
    """duyệt toàn bộ OpenAPI của app đã nối dây: không cookie thì 401, ngoại lệ chỉ là các cổng tự xác thực"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        spec = loop.app.openapi()
        leaked: list[str] = []
        checked = 0
        for path, operations in spec["paths"].items():
            for method in operations:
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                checked += 1
                response = await loop.http.request(method.upper(), _concrete(path), json={})
                if (method, path) in PUBLIC:
                    if response.status_code < 400 and path != "/healthz":
                        leaked.append(f"{method.upper()} {path} -> {response.status_code}")
                elif response.status_code != 401:
                    leaked.append(f"{method.upper()} {path} -> {response.status_code}")
        assert checked > 100, "the walk must cover the whole API"
        assert leaked == [], "routes that did not refuse an anonymous caller: " + "; ".join(leaked)
