"""The knowledge plugin with a fake embedding service: the key kept sealed, the connection test, the job that
embeds the chunks, the status strip, and a question found by meaning through the page "Thử tìm" and through the
agent's ``kb_search`` (whose trace says whether the vector branch was used)."""

from __future__ import annotations

import asyncio
import contextlib
import textwrap
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from agent_app.gateway import GatewaySettings, create_app
from agent_app.plugins import PluginHost, discover
from agent_app.profile import load_profile
from agent_app.runtime import BUNDLED_PLUGINS, Runtime, build_runtime
from agentcore import InMemorySessionStore, InMemoryTracer, PromptBuilder, run_turn
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from tests.knowledge.fake_embedding import (
    BASE_URL,
    DIMENSIONS,
    KEY,
    embeddings_transport,
    status_transport,
)

TOKEN = "t" * 40
ADMIN = "a" * 40
SEALING = "0f" * 32
BASE = "/v1/plugins/knowledge"
ASKED = datetime(2026, 10, 12, 3, 0, tzinfo=UTC)

PIGMENT = textwrap.dedent("""
    ---
    doc_id: D03
    title: Cẩm nang nám
    status: active
    ---
    # Cẩm nang
    ## Nám là gì
    Nám là tình trạng tăng sắc tố, cần bác sĩ khám và đánh giá trước khi điều trị.
    ## Bác sĩ quyết định
    Chỉ bác sĩ mới kết luận loại nám sau khi thăm khám trực tiếp.
""").lstrip()
PRICE = textwrap.dedent("""
    ---
    doc_id: D07
    title: Bảng giá
    status: active
    ---
    # Bảng giá
    ## Buổi lẻ
    Một buổi laser có giá 4.000.000 đồng, đã gồm thăm khám.
""").lstrip()


def _runtime(tmp_path: Path, transport: httpx.MockTransport | None) -> tuple[Runtime, PluginHost]:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\ntimezone = "Asia/Ho_Chi_Minh"\n\n'
        '[plugins]\nenabled = ["knowledge"]\n',
        encoding="utf-8",
    )
    env = {"AGENT_SECRET_ENCRYPTION_KEY": SEALING}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    config: dict[str, Any] = {
        "embedding_base_url": BASE_URL,
        "embedding_model": "fake",
        "embedding_dimensions": DIMENSIONS,
        "embedding_query_prefix": "",
        "vector_min_similarity": 0.5,
        "embedding_idle_s": 0.01,
    }
    if transport is not None:
        config["embedding_transport"] = transport
    host.enable("knowledge", config)
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


async def _save_key(client: httpx.AsyncClient, key: str = KEY) -> httpx.Response:
    return await client.patch(f"{BASE}/settings", json={"embedding": {"api_key": key}})


async def _waiting(client: httpx.AsyncClient) -> int:
    settings = (await client.get(f"{BASE}/settings")).json()
    return int(settings["embedding"]["chunks_without_vector"])


@contextlib.asynccontextmanager
async def _job(host: PluginHost) -> AsyncGenerator[None]:
    """Runs the plugin's job "embed" for the length of the block."""
    (job,) = [j for j in host.contributions().jobs if j.key == "knowledge/embed"]
    task = asyncio.create_task(job.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _until(check: Any) -> None:
    async with asyncio.timeout(5):
        while not await check():  # noqa: ASYNC110 - the job moves this state on its own
            await asyncio.sleep(0.01)


async def _embed_all(host: PluginHost, client: httpx.AsyncClient) -> None:
    async with _job(host):
        await _until(lambda: _is_zero(client))


async def _is_zero(client: httpx.AsyncClient) -> bool:
    return await _waiting(client) == 0


async def test_the_key_is_kept_sealed_and_never_sent_back(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        before = (await client.get(f"{BASE}/settings")).json()
        saved = await _save_key(client)
        after = (await client.get(f"{BASE}/settings")).json()
        record = await host.storage("knowledge").get("embedding_api_key")

    assert before["embedding"]["has_key"] is False
    assert saved.status_code == 200
    assert after["embedding"]["has_key"] is True
    assert KEY not in saved.text
    assert KEY not in str(after)
    assert isinstance(record, str)
    assert KEY not in record
    stored = await host.storage("knowledge").get("settings")
    assert KEY not in str(stored)
    assert "has_key" not in str(stored)
    runtime.close()


async def test_an_empty_key_removes_it(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        await _save_key(client)
        removed = await _save_key(client, "")
        after = (await client.get(f"{BASE}/settings")).json()

    assert removed.status_code == 200
    assert after["embedding"]["has_key"] is False
    assert await host.storage("knowledge").get("embedding_api_key") is None
    runtime.close()


async def test_a_wrong_setting_is_refused_with_a_sentence(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        for patch in (
            {"base_url": "ftp://x"},
            {"dimensions": 4},
            {"dimensions": 99999},
            {"model": ""},
            {"api_key": "short"},
        ):
            refused = await client.patch(f"{BASE}/settings", json={"embedding": patch})
            assert refused.status_code == 422, patch
    runtime.close()


async def test_the_connection_test_reports_dimensions_and_norm(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        await _save_key(client)
        tested = (await client.post(f"{BASE}/settings/test-embedding")).json()

    assert tested["ok"] is True
    assert tested["dimensions"] == DIMENSIONS
    assert tested["normalised"] is True
    assert tested["message"] == "Kết nối tốt"
    runtime.close()


async def test_the_connection_test_says_what_went_wrong(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path, status_transport(401))
    async with _client(runtime) as client:
        no_key = (await client.post(f"{BASE}/settings/test-embedding")).json()
        await _save_key(client)
        wrong = (await client.post(f"{BASE}/settings/test-embedding")).json()

    assert no_key["ok"] is False
    assert "Chưa cài" in no_key["message"]
    assert wrong["ok"] is False
    assert wrong["message"] == "Khóa API sai hoặc hết hạn."
    assert KEY not in str(wrong)
    runtime.close()


async def test_the_job_embeds_every_chunk_once(tmp_path: Path) -> None:
    sent: list[list[str]] = []
    runtime, host = _runtime(tmp_path, embeddings_transport(sent))
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT, "d07.md": PRICE})
        await _save_key(client)
        assert await _waiting(client) == 3

        await _embed_all(host, client)
        first = [text for batch in sent for text in batch]
        listing = (await client.get(f"{BASE}/sources")).json()
        await _embed_all(host, client)

    assert len(first) == 3
    assert [text for batch in sent for text in batch] == first
    assert listing["summary"]["embedded_percent"] == 100
    assert [s["progress"]["embedded"] for s in listing["items"]] == [
        s["progress"]["chunks"] for s in listing["items"]
    ]
    runtime.close()


async def test_cutting_a_source_again_with_the_same_text_needs_no_new_vectors(tmp_path: Path) -> None:
    sent: list[list[str]] = []
    runtime, host = _runtime(tmp_path, embeddings_transport(sent))
    async with _client(runtime) as client:
        await _add(client, {"d07.md": PRICE})
        await _save_key(client)
        await _embed_all(host, client)
        source_id = (await client.get(f"{BASE}/sources")).json()["items"][0]["id"]
        before = len(sent)

        await client.post(f"{BASE}/sources/{source_id}/reindex")
        waiting = await _waiting(client)
        await _embed_all(host, client)

    assert waiting == 0
    assert len(sent) == before
    runtime.close()


async def test_changing_the_model_makes_every_chunk_wait_again(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT})
        await _save_key(client)
        await _embed_all(host, client)

        await client.patch(f"{BASE}/settings", json={"embedding": {"model": "another"}})

        assert await _waiting(client) == 2
    runtime.close()


async def test_a_question_is_found_by_meaning_on_the_page_and_through_kb_search(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, embeddings_transport([]))
    question = "da bị sạm nâu từng mảng"
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT, "d07.md": PRICE})
        await _save_key(client)
        await _embed_all(host, client)

        debug = (
            await client.post(f"{BASE}/search/debug", json={"question": question, "as_of": "2026-10-12"})
        ).json()
        agent = runtime.live.current()
        tracer = InMemoryTracer()
        await run_turn(
            session_id="s1",
            user_text=question,
            prompt=PromptBuilder.fixed("sys"),
            model=ScriptedModel([calls(tool_call("kb_search", {"query": question})), reply("ok")]),
            tools=agent.tools,
            store=InMemorySessionStore(),
            tracer=tracer,
            clock=lambda: ASKED,
        )

    stages = {stage["id"]: stage for stage in debug["stages"]}
    assert stages["keyword"]["candidates"] == []
    assert stages["vector"]["skipped"] is False
    assert next(c["doc_code"] for c in stages["vector"]["candidates"]) == "D03"
    assert stages["fused"]["skipped"] is False
    assert stages["final"]["candidates"][0]["doc_code"] == "D03"
    (trace,) = tracer.traces
    detail = trace.events[1].detail["tool"]
    assert detail["vector_used"] is True
    assert detail["vector_candidates"] >= 1
    assert detail["keyword_candidates"] == 0
    assert detail["doc_ids"][0] == "D03"
    assert question not in str(detail)
    runtime.close()


async def test_without_a_key_search_is_keyword_only_and_says_so(tmp_path: Path) -> None:
    sent: list[list[str]] = []
    runtime, _ = _runtime(tmp_path, embeddings_transport(sent))
    async with _client(runtime) as client:
        await _add(client, {"d07.md": PRICE})
        debug = (
            await client.post(
                f"{BASE}/search/debug", json={"question": "một buổi giá bao nhiêu", "as_of": "2026-10-12"}
            )
        ).json()
        status = (await client.get(f"{BASE}/status")).json()

    stages = {stage["id"]: stage for stage in debug["stages"]}
    assert stages["vector"]["skipped"] is True
    assert stages["fused"]["skipped"] is True
    assert stages["final"]["candidates"][0]["doc_code"] == "D07"
    assert sent == []
    assert status["embedding_connected"] is False
    assert "chưa kết nối" in status["warnings"][0]
    runtime.close()


async def test_the_status_strip_follows_the_job(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, embeddings_transport([]))
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT})
        off = (await client.get(f"{BASE}/status")).json()
        await _save_key(client)
        working = (await client.get(f"{BASE}/status")).json()
        await _embed_all(host, client)
        ok = (await client.get(f"{BASE}/status")).json()

    assert (off["embedding_connected"], off["queue"]) == (False, 0)
    assert working["embedding_connected"] is True
    assert working["queue"] == 2
    assert working["warnings"] == ["Đang nhúng: còn 2 đoạn chưa có vector."]
    assert (ok["queue"], ok["warnings"], ok["embedding_model"]) == (0, [], "fake")
    runtime.close()


async def test_the_status_strip_shows_a_failing_service(tmp_path: Path) -> None:
    runtime, host = _runtime(tmp_path, status_transport(500))
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT})
        await _save_key(client)
        async with _job(host):
            await _until(lambda: _is_failing(client))
        status = (await client.get(f"{BASE}/status")).json()

    assert "Embedding đang lỗi" in status["warnings"][0]
    assert "HTTP 500" in status["warnings"][0]
    runtime.close()


async def _is_failing(client: httpx.AsyncClient) -> bool:
    warnings = (await client.get(f"{BASE}/status")).json()["warnings"]
    return bool(warnings) and warnings[0].startswith("Embedding đang lỗi")


async def test_reembedding_clears_the_space_and_counts_the_queue(tmp_path: Path) -> None:
    sent: list[list[str]] = []
    runtime, host = _runtime(tmp_path, embeddings_transport(sent))
    async with _client(runtime) as client:
        await _add(client, {"d03.md": PIGMENT})
        not_connected = await client.post(f"{BASE}/settings/reembed")
        await _save_key(client)
        await _embed_all(host, client)
        first = len([text for batch in sent for text in batch])

        queued = (await client.post(f"{BASE}/settings/reembed")).json()
        await _embed_all(host, client)

    assert not_connected.status_code == 409
    assert queued == {"queued": 2}
    assert len([text for batch in sent for text in batch]) == first + 2
    runtime.close()
