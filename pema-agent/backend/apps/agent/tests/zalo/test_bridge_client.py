"""The signed HTTP client of the Zalo bridge, against a fake bridge that checks bodies like its zod schemas."""

from __future__ import annotations

import json

import httpx

from plugins.zalo.personal.client import BridgeClient

CREDENTIAL = {"cookie": [{"key": "zpw_sek", "value": "mau"}], "imei": "imei-mau", "userAgent": "UA mau"}


def _bridge(seen: list[dict[str, object]]) -> httpx.MockTransport:
    """Answers ``start`` like the bridge: 400 when ``kill_switch.reason`` is there but not a string."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        kill = body.get("kill_switch", {})
        if "reason" in kill and not isinstance(kill["reason"], str):
            return httpx.Response(
                400, json={"ok": False, "error": {"kind": "bad_request", "message": "reason"}}
            )
        return httpx.Response(200, json={"ok": True, "own_id": "uid-mau"})

    return httpx.MockTransport(answer)


async def test_start_sends_a_kill_switch_body_the_bridge_accepts() -> None:
    seen: list[dict[str, object]] = []
    client = BridgeClient("http://bridge.local", "secret", transport=_bridge(seen))

    own_id = await client.start_account("acc-1", CREDENTIAL)

    await client.aclose()
    assert own_id == "uid-mau"
    assert seen[0]["kill_switch"] == {"on": False, "scope": "proactive"}
