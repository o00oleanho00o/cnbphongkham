"""The knowledge search with the judge (plugin ``jev``): what becomes of each chunk, what the judge is shown, that
it never makes a search fail, and the two plugins together: chunks judged by a fake TypeSafe, "Thử tìm" showing
what was kept and dropped, and ``kb_search`` telling the agent when nothing has evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import JudgeUnavailableError, PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore import InMemorySessionStore, InMemoryTracer, PromptBuilder, run_turn
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from plugins.knowledge.judging import NOT_ON, QUESTIONS, JudgePlan, judge_hits, reasons, state_of
from plugins.knowledge.models import Chunk, Hit
from tests.knowledge.test_embedding_plugin import ADMIN, ASKED, BASE, PIGMENT, PRICE, TOKEN

KEY = "ts-test-synthetic"
SECRET = "0f" * 32


class Judge:
    """A fake ``JudgeService``: answers by a word in the passage."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.states: list[str] = []

    def _score(self, body: str) -> float:
        return next((v for word, v in self.scores.items() if word in body), 0.01)

    async def ready(self) -> bool:
        return True

    async def ask(self, states: Any, questions: Any, *, timeout_s: float) -> list[dict[str, Any]]:
        assert questions == QUESTIONS
        self.states.extend(states)
        found = [self._score(s.split("):", 1)[1]) for s in states]  # the chunk's text, not its place
        return [{"ranks_top": {"type": "noul", "noul": rank}} for rank in found]


def _hit(chunk_id: str, body: str, **chunk: Any) -> Hit:
    made = Chunk(id=chunk_id, source_id="s1", ordinal=1, path="Bảng giá > Buổi lẻ", body=body, **chunk)
    return Hit(made, "Bảng giá", "D07", 1.0)


def _plan(service: Any, level: str = "medium") -> JudgePlan:
    return JudgePlan(service, level, 4.0)


@pytest.mark.parametrize(
    ("ranks", "level", "expected"),
    [
        ([0.9, 0.5, 0.1], "medium", ["kept", "kept", "weak"]),
        ([0.05, 0.02], "medium", ["no_evidence", "no_evidence"]),
        ([0.2, 0.1], "strict", ["no_evidence", "no_evidence"]),
        ([0.2, 0.1], "medium", ["kept", "kept"]),
        ([0.06], "loose", ["kept"]),
        ([0.06], "medium", ["no_evidence"]),
        ([0.5], "unknown", ["kept"]),
        ([], "medium", []),
    ],
)
def test_chunks_are_kept_weak_or_all_refused_by_how_the_best_one_scores(
    ranks: list[float], level: str, expected: list[str]
) -> None:
    assert reasons(ranks, level) == expected


def test_the_judge_reads_the_question_the_other_wordings_and_the_place_of_the_chunk() -> None:
    hit = _hit("a", "Một buổi laser 4.000.000")

    plain = state_of("giá laser", [], hit)
    wider = state_of("giá laser", ["chi phí laser nám", "bao nhiêu tiền"], hit)

    assert "Customer question: giá laser" in plain
    assert "document: Bảng giá; section: Bảng giá > Buổi lẻ" in plain
    assert plain.endswith("Một buổi laser 4.000.000")
    assert "Other ways" not in plain
    assert "Other ways the customer may have asked it: chi phí laser nám; bao nhiêu tiền" in wider


async def test_the_chunks_stay_ordered_by_the_judge_and_the_ones_far_below_the_best_are_dropped() -> None:
    judge = Judge({"giá": 0.95, "quy trình": 0.5, "xa": 0.05})
    hits = [_hit("a", "quy trình"), _hit("b", "giá"), _hit("c", "xa tít")]

    outcome = await judge_hits(_plan(judge), "hỏi?", [], hits)

    assert outcome.judged
    assert [h.chunk.id for h in outcome.kept] == ["b", "a"]
    assert [h.score for h in outcome.kept] == [0.95, 0.5]
    assert [v.reason for v in outcome.verdicts] == ["kept", "kept", "weak"]


async def test_nothing_is_handed_over_when_even_the_best_chunk_scores_under_the_floor() -> None:
    judge = Judge({"lạc": 0.04})

    outcome = await judge_hits(_plan(judge), "hỏi?", [], [_hit("x", "lạc đề"), _hit("y", "khác")])

    assert outcome.judged
    assert outcome.kept == ()
    assert {v.reason for v in outcome.verdicts} == {"no_evidence"}


class Down:
    async def ready(self) -> bool:
        return True

    async def ask(self, states: Any, questions: Any, *, timeout_s: float) -> list[dict[str, Any]]:
        raise JudgeUnavailableError("Chưa có khóa TypeSafe.")


class Odd(Down):
    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self._answers = answers

    async def ask(self, states: Any, questions: Any, *, timeout_s: float) -> list[dict[str, Any]]:
        return self._answers


@pytest.mark.parametrize(
    ("service", "words"),
    [
        (None, NOT_ON),
        (Down(), "Chưa có khóa TypeSafe"),
        (Odd([{"ranks_top": {}}, {"ranks_top": {}}]), "dữ liệu lạ"),
        (Odd([]), "thiếu kết quả"),
    ],
)
async def test_when_the_judge_cannot_judge_every_chunk_goes_on_as_the_search_ranked_it(
    service: Any, words: str
) -> None:
    hits = [_hit("a", "x"), _hit("b", "y")]

    outcome = await judge_hits(_plan(service), "hỏi?", [], hits)

    assert outcome.kept == tuple(hits)
    assert not outcome.judged
    assert outcome.note is not None
    assert words in outcome.note


async def test_no_chunks_means_no_request() -> None:
    judge = Judge({})

    outcome = await judge_hits(_plan(judge), "hỏi?", [], [])

    assert outcome.kept == ()
    assert judge.states == []


class Typesafe:
    """A fake TypeSafe for the two plugins together: the price chunk states the fact, the pigment one does not."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.seen.append(body)
        state: str = body["state"]
        rank = 0.9 if "4.000.000" in state else 0.02
        if "xe ô tô" in state:
            rank = 0.01
        answers = {name: {"type": "noul", "noul": rank} for name in body["questions"]}
        return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": 100}})


def _runtime(tmp_path: Path, typesafe: Typesafe) -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\ntimezone = "Asia/Ho_Chi_Minh"\n\n'
        '[plugins]\nenabled = ["knowledge", "jev"]\n',
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": SECRET}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("knowledge", {})
    host.enable("jev", {"transport": typesafe.transport})
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(
        runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://agent",
        headers={"Authorization": f"Bearer {ADMIN}"},
    )


async def _add(client: httpx.AsyncClient, docs: dict[str, str]) -> None:
    inputs = [
        {"key": name, "name": name, "kind": "file", "size": len(text), "text": text}
        for name, text in docs.items()
    ]
    preview = (await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})).json()
    items = [
        {"key": i["key"], "title": i["meta"]["title"], "doc_code": i["meta"]["doc_code"]}
        for i in preview["items"]
    ]
    await client.post(f"{BASE}/sources/confirm", json={"preview_id": preview["preview_id"], "items": items})


async def _debug(client: httpx.AsyncClient, question: str) -> dict[str, Any]:
    found = await client.post(f"{BASE}/search/debug", json={"question": question, "as_of": "2026-10-12"})
    return {stage["id"]: stage for stage in found.json()["stages"]}


async def test_try_search_shows_what_the_judge_kept_and_dropped_and_the_agent_gets_only_the_kept(
    tmp_path: Path,
) -> None:
    typesafe = Typesafe()
    runtime = _runtime(tmp_path, typesafe)
    async with _client(runtime) as client:
        await _add(client, {"nam.md": PIGMENT, "gia.md": PRICE})
        off = await _debug(client, "laser nám giá")
        await client.patch("/v1/plugins/jev/settings", json={"api_key": KEY})
        switched = await client.patch(f"{BASE}/settings", json={"judging": {"enabled": True}})
        on = await _debug(client, "laser nám giá")
        refused = await client.patch(f"{BASE}/settings", json={"judging": {"level": "x"}})

    assert "judge" not in off
    assert switched.json()["judging"] == {"enabled": True, "level": "medium"}
    assert [c["doc_code"] for c in on["judge"]["candidates"]] == ["D07"]
    assert {c["doc_code"] for c in on["judge_dropped"]["candidates"]} == {"D03"}  # both chunks of D03
    assert [c["doc_code"] for c in on["final"]["candidates"]] == ["D07"]
    assert on["judge"]["candidates"][0]["score"] == 0.9
    assert refused.status_code == 422
    sent = typesafe.seen[0]
    assert "Customer question: laser nám giá" in sent["state"]
    assert set(sent["questions"]) == set(QUESTIONS)
    runtime.close()


async def test_without_a_key_the_search_goes_on_unjudged_and_says_why(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, Typesafe())
    async with _client(runtime) as client:
        await _add(client, {"nam.md": PIGMENT, "gia.md": PRICE})
        await client.patch(f"{BASE}/settings", json={"judging": {"enabled": True}})
        stages = await _debug(client, "laser nám giá")

    assert stages["judge"]["skipped"] is True
    assert "Chưa có khóa" in stages["judge"]["note"]
    assert {c["doc_code"] for c in stages["final"]["candidates"]} == {"D03", "D07"}
    runtime.close()


async def test_kb_search_tells_the_agent_when_no_chunk_has_evidence_and_records_the_gap(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, Typesafe())
    async with _client(runtime) as client:
        await _add(client, {"nam.md": PIGMENT, "gia.md": PRICE})
        await client.patch("/v1/plugins/jev/settings", json={"api_key": KEY})
        await client.patch(f"{BASE}/settings", json={"judging": {"enabled": True}})
        agent = runtime.live.current()
        tracer = InMemoryTracer()

        async def ask(query: str) -> Any:
            tracer.traces.clear()
            await run_turn(
                session_id="s1",
                user_text=query,
                prompt=PromptBuilder.fixed("sys"),
                model=ScriptedModel([calls(tool_call("kb_search", {"query": query})), reply("ok")]),
                tools=agent.tools,
                store=InMemorySessionStore(),
                tracer=tracer,
                clock=lambda: ASKED,
            )
            return tracer.traces[0].events[1]

        good = await ask("laser nám giá")
        none = await ask("laser nám xe ô tô")
        gaps = (await client.get(f"{BASE}/gaps")).json()

    assert good.detail["tool"]["doc_ids"] == ["D07"]
    assert good.detail["tool"]["judged"] is True
    assert good.detail["tool"]["judge_dropped"] == 2  # the two chunks of the pigment document
    assert none.detail["tool"]["returned"] == 0
    assert [g["question"] for g in gaps] == ["laser nám xe ô tô"]
    runtime.close()
