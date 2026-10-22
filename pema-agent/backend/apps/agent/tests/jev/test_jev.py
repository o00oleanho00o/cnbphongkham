"""The jev plugin against a fake TypeSafe: what it sends, the answers it hands back in order, that the key stays
sealed, the sentence each failure becomes, the day's allowance, and the service as another plugin finds it."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from plugin_kit import JUDGE, JudgeService, JudgeUnavailableError
from plugins.jev.client import ENDPOINT
from secretcipher import encrypt_with

KEY = "ts-test-synthetic"
SECRET = "0f" * 32
TOKEN = "t" * 40
ADMIN = "a" * 40
BASE = "/v1/plugins/jev"
QUESTIONS = {"is_price": {"type": "noul", "instructions": "Does the text state a price?"}}


class Fake:
    """A fake TypeSafe: records the requests, answers each question, can be slow or fail by status."""

    def __init__(
        self, *, tokens: int = 100, noul: float = 0.9, delay: float = 0.0, codes: list[int] | None = None
    ) -> None:
        self.seen: list[dict[str, Any]] = []
        self.peak = 0
        self._flying = 0
        self._tokens = tokens
        self._noul = noul
        self._delay = delay
        self._codes = codes or []
        self.transport = httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.seen.append({"url": str(request.url), "auth": request.headers["authorization"], "body": body})
        self._flying += 1
        self.peak = max(self.peak, self._flying)
        try:
            await asyncio.sleep(self._delay)
        finally:
            self._flying -= 1
        if self._codes:
            return httpx.Response(self._codes.pop(0), text="no")
        answers = {name: {"type": "noul", "noul": self._noul} for name in body["questions"]}
        usage = {"input_tokens": self._tokens, "output_tokens": 3}
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": answers, "usage": usage})


def _host(fake: Fake, **config: Any) -> PluginHost:
    env = {"AGENT_SECRET_ENCRYPTION_KEY": SECRET}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("jev", {"transport": fake.transport, **config})
    return host


async def _with_key(host: PluginHost, **settings: Any) -> JudgeService:
    storage = host.storage("jev")
    await storage.put("api_key", encrypt_with(SECRET, KEY))
    if settings:
        await storage.put("settings", settings)
    service = host.use(JUDGE, JudgeService)
    assert service is not None
    return service


async def test_it_sends_one_request_per_state_with_the_key_and_answers_in_order() -> None:
    fake = Fake()
    service = await _with_key(_host(fake))

    answers = await service.ask([{"text": "một"}, {"text": "hai"}, {"text": "ba"}], QUESTIONS, timeout_s=5)

    assert len(answers) == 3
    assert all(a["is_price"]["noul"] == 0.9 for a in answers)
    assert sorted(r["body"]["state"]["text"] for r in fake.seen) == ["ba", "hai", "một"]
    first = fake.seen[0]
    assert first["url"] == ENDPOINT
    assert first["auth"] == f"Bearer {KEY}"
    assert first["body"]["model"] == "jev-latest"
    assert first["body"]["questions"] == QUESTIONS


async def test_the_answers_follow_the_states_whatever_order_the_requests_finish_in() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content)["state"]["text"]
        await asyncio.sleep(0.05 if text == "chậm" else 0.0)
        noul = 0.1 if text == "chậm" else 0.8
        return httpx.Response(
            200, json={"answers": {"is_price": {"type": "noul", "noul": noul}}, "usage": {}}
        )

    fake = Fake()
    fake.transport = httpx.MockTransport(handle)
    service = await _with_key(_host(fake))

    answers = await service.ask([{"text": "chậm"}, {"text": "nhanh"}], QUESTIONS, timeout_s=5)

    assert [a["is_price"]["noul"] for a in answers] == [0.1, 0.8]


async def test_requests_run_together_but_never_more_than_the_setting_allows() -> None:
    fake = Fake(delay=0.02)
    service = await _with_key(_host(fake, concurrency=3))

    await service.ask([{"i": i} for i in range(12)], QUESTIONS, timeout_s=5)

    assert fake.peak == 3


async def test_without_a_key_nothing_is_sent() -> None:
    fake = Fake()
    service = _host(fake).use(JUDGE, JudgeService)
    assert service is not None

    assert await service.ready() is False
    with pytest.raises(JudgeUnavailableError, match="Chưa có khóa"):
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)
    assert fake.seen == []


@pytest.mark.parametrize(
    ("code", "words"), [(401, "Khóa TypeSafe sai"), (500, "lỗi hoặc quá tải"), (422, "từ chối")]
)
async def test_a_failure_is_a_sentence_that_never_holds_the_key(code: int, words: str) -> None:
    host = _host(Fake(codes=[code]))
    service = await _with_key(host)

    with pytest.raises(JudgeUnavailableError, match=words) as failed:
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)

    assert KEY not in failed.value.message
    usage = await host.storage("jev").get("usage")
    assert usage is not None
    assert sum(day["errors"] for day in usage.values()) == 1


async def test_a_request_cut_off_or_limited_is_asked_once_more_and_a_second_refusal_is_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("plugins.jev.client.RETRY_AFTER_S", 0)
    again = Fake(codes=[499])
    service = await _with_key(_host(again))
    answers = await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)
    assert answers[0]["is_price"]["noul"] == 0.9
    assert len(again.seen) == 2

    stuck = Fake(codes=[529, 529])
    other = await _with_key(_host(stuck))
    with pytest.raises(JudgeUnavailableError, match="quá tải"):
        await other.ask([{"text": "x"}], QUESTIONS, timeout_s=5)
    assert len(stuck.seen) == 2


async def test_a_slow_service_is_given_up_on_at_the_time_asked() -> None:
    service = await _with_key(_host(Fake(delay=1.0)))

    with pytest.raises(JudgeUnavailableError, match="kịp"):
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=0.05)


async def test_an_answer_missing_a_question_is_not_trusted() -> None:
    fake = Fake()
    fake.transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"answers": {}}))
    service = await _with_key(_host(fake))

    with pytest.raises(JudgeUnavailableError, match="không đọc được"):
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)


async def test_a_probability_outside_zero_to_one_is_not_trusted() -> None:
    service = await _with_key(_host(Fake(noul=1.7)))

    with pytest.raises(JudgeUnavailableError, match="không đọc được"):
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)


async def test_each_day_counts_calls_and_tokens_and_the_allowance_stops_the_next_call() -> None:
    fake = Fake(tokens=100)
    host = _host(fake)
    service = await _with_key(host, daily_token_cap=250)

    await service.ask([{"i": 1}, {"i": 2}], QUESTIONS, timeout_s=5)
    assert await service.ready() is True
    await service.ask([{"i": 3}], QUESTIONS, timeout_s=5)
    assert await service.ready() is False
    with pytest.raises(JudgeUnavailableError, match="hết hạn mức"):
        await service.ask([{"i": 4}], QUESTIONS, timeout_s=5)

    usage = await host.storage("jev").get("usage")
    assert usage is not None
    (today,) = usage.values()
    assert today == {"calls": 3, "tokens": 300, "errors": 0}
    assert len(fake.seen) == 3


async def test_an_allowance_of_zero_means_no_limit() -> None:
    service = await _with_key(_host(Fake(tokens=1_000_000)), daily_token_cap=0)

    for _ in range(3):
        await service.ask([{"text": "x"}], QUESTIONS, timeout_s=5)

    assert await service.ready() is True


async def test_the_service_is_gone_while_the_plugin_is_disabled() -> None:
    host = _host(Fake())
    assert host.use(JUDGE, JudgeService) is not None

    host.disable("jev")

    assert host.use(JUDGE, JudgeService) is None


def _runtime(tmp_path: Path, fake: Fake) -> tuple[Runtime, PluginHost]:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\ntimezone = "Asia/Ho_Chi_Minh"\n\n[plugins]\nenabled = ["jev"]\n',
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": SECRET}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("jev", {"transport": fake.transport})
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host), host


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(
        runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://agent",
        headers={"Authorization": f"Bearer {ADMIN}"},
    )


async def test_the_key_is_kept_sealed_never_sent_back_and_an_empty_one_removes_it(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, Fake())
    async with _client(runtime) as client:
        before = (await client.get(f"{BASE}/settings")).json()
        saved = await client.patch(f"{BASE}/settings", json={"api_key": KEY, "daily_token_cap": 500_000})
        after = (await client.get(f"{BASE}/settings")).json()
        sealed = await host.storage("jev").get("api_key")
        removed = await client.patch(f"{BASE}/settings", json={"api_key": ""})

    assert before["model"] == "jev-latest"
    assert before["daily_token_cap"] == 2_000_000
    assert before["has_key"] is False
    assert saved.status_code == 200
    assert after["has_key"] is True
    assert after["daily_token_cap"] == 500_000
    assert KEY not in saved.text
    assert isinstance(sealed, str)
    assert KEY not in sealed
    assert KEY not in str(await host.storage("jev").get("settings"))
    assert removed.json()["has_key"] is False
    assert await host.storage("jev").get("api_key") is None
    runtime.close()


async def test_a_wrong_setting_is_refused(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path, Fake())
    async with _client(runtime) as client:
        for patch in ({"daily_token_cap": -1}, {"api_key": "short"}, {"model": "Bad Model!"}, {"other": 1}):
            refused = await client.patch(f"{BASE}/settings", json=patch)
            assert refused.status_code == 422, patch
    runtime.close()


async def test_the_connection_test_says_whether_the_key_works_and_the_usage_shows_what_it_cost(
    tmp_path: Path,
) -> None:
    runtime, _ = _runtime(tmp_path, Fake(tokens=120))
    async with _client(runtime) as client:
        without = (await client.post(f"{BASE}/test")).json()
        await client.patch(f"{BASE}/settings", json={"api_key": KEY})
        tested = (await client.post(f"{BASE}/test")).json()
        usage = (await client.get(f"{BASE}/usage")).json()

    assert without["ok"] is False
    assert "Chưa có khóa" in without["message"]
    assert tested["ok"] is True
    assert usage["used_today"] == 120
    assert usage["daily_token_cap"] == 2_000_000
    assert usage["days"][0]["calls"] == 1
    assert usage["days"][0]["usd"] == pytest.approx(120 * 42 / 1_000_000_000, abs=1e-8)
    runtime.close()
