"""The knowledge plugin end to end, without a database: documents added through its admin routes (preview,
confirm), found by the page "Thử tìm" and by the agent's ``kb_search`` (whose numbers reach the turn trace),
the version in force on the day asked, the questions it had nothing for, and the table of contents every
question carries."""

from __future__ import annotations

import asyncio
import contextlib
import textwrap
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from agent_app.gateway import GatewaySettings, create_app
from agent_app.profile import load_profile
from agent_app.runtime import Runtime, build_runtime
from agentcore import InMemorySessionStore, InMemoryTracer, PromptBuilder, TurnInfo, run_turn
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from agentcore.prompt.sections import StepInfo

TOKEN = "t" * 40
ADMIN = "a" * 40
BASE = "/v1/plugins/knowledge"
ASKED = datetime(2026, 10, 12, 3, 0, tzinfo=UTC)


def _doc(code: str, title: str, body: str, **head: str) -> str:
    fields = {"doc_id": code, "title": title, "status": "active", "audience": "patient", **head}
    lines = "\n".join(f"{key}: {value}" for key, value in fields.items())
    return f"---\n{lines}\n---\n{textwrap.dedent(body).strip()}\n"


PRICES = _doc(
    "D07",
    "Bảng giá hiện hành",
    """
    # Bảng giá
    ## Điều trị nám
    ### Buổi lẻ
    Một buổi laser điều trị nám có giá 4.000.000 đồng, đã gồm thăm khám và chăm sóc sau buổi.
    ### Gói 10 buổi
    Gói 10 buổi điều trị nám có giá 25.000.000 đồng, dùng trong 12 tháng.
    """,
    effective_from="2026-10-01",
)
OLD_PRICES = _doc(
    "D07-V1",
    "Bảng giá cũ",
    """
    # Bảng giá cũ
    ## Điều trị nám
    Một buổi laser điều trị nám có giá 3.500.000 đồng theo bảng giá cũ của phòng khám.
    """,
    effective_from="2026-01-01",
    effective_to="2026-09-30",
)
BOOKING = _doc(
    "D12",
    "Đặt lịch",
    """
    # Đặt lịch
    ## Đặt cọc
    Buổi lẻ cần đặt cọc 500.000 đồng khi đặt lịch; hủy trước 24 giờ được hoàn cọc đầy đủ.
    """,
)


def _runtime(tmp_path: Path, settings: str = "") -> Runtime:
    folder = tmp_path / "agent"
    folder.mkdir()
    (folder / "agent.toml").write_text(
        '[agent]\nname = "t"\nsystem_prompt = "p"\ntimezone = "Asia/Ho_Chi_Minh"\n\n'
        f'[plugins]\nenabled = ["knowledge"]\n\n[plugins.knowledge]\n{settings}',
        encoding="utf-8",
    )
    return build_runtime(load_profile(folder), fake=True, env={}, db=None)


def _client(runtime: Runtime) -> httpx.AsyncClient:
    app = create_app(
        runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=ADMIN), plugins=runtime.plugin_manager
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://agent",
        headers={"Authorization": f"Bearer {ADMIN}"},
    )


async def _add(client: httpx.AsyncClient, docs: dict[str, str]) -> dict[str, Any]:
    inputs = [
        {"key": name, "name": name, "kind": "file", "size": len(text), "text": text}
        for name, text in docs.items()
    ]
    preview = (await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})).json()
    items = [
        {
            "key": item["key"],
            "title": item["meta"]["title"],
            "doc_code": item["meta"]["doc_code"],
            "lifecycle": item["meta"]["lifecycle"] or "active",
            "effective_from": item["meta"]["effective_from"],
            "effective_to": item["meta"]["effective_to"],
        }
        for item in preview["items"]
    ]
    confirmed = await client.post(
        f"{BASE}/sources/confirm", json={"preview_id": preview["preview_id"], "items": items}
    )
    return confirmed.json()


async def test_documents_added_through_the_routes_are_listed_with_their_chunks(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        added = await _add(client, {"d07.md": PRICES, "d12.md": BOOKING})
        listing = (await client.get(f"{BASE}/sources")).json()

    assert added["skipped"] == []
    assert sorted(s["doc_code"] for s in listing["items"]) == ["D07", "D12"]
    assert listing["summary"]["ready"] == 2
    assert listing["summary"]["chunks"] == sum(s["chunk_count"] for s in listing["items"])
    runtime.close()


async def test_a_pdf_is_refused_with_a_sentence_and_the_rest_goes_on(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    inputs = [
        {"key": "a", "name": "cam-nang.pdf", "kind": "file", "size": 10, "base64": "JVBERi0="},
        {"key": "b", "name": "d12.md", "kind": "file", "size": len(BOOKING), "text": BOOKING},
    ]
    async with _client(runtime) as client:
        preview = (await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})).json()

    errors = [item["error"] for item in preview["items"]]
    assert ".md" in (errors[0] or "")
    assert errors[1] is None
    runtime.close()


async def test_the_search_trial_finds_the_price_in_force_on_the_day_asked(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        await _add(client, {"d07.md": PRICES, "old.md": OLD_PRICES, "d12.md": BOOKING})
        today = (
            await client.post(
                f"{BASE}/search/debug",
                json={"question": "trị nám buổi lẻ giá bao nhiêu", "as_of": "2026-10-12"},
            )
        ).json()
        before = (
            await client.post(
                f"{BASE}/search/debug",
                json={"question": "trị nám buổi lẻ giá bao nhiêu", "as_of": "2026-09-15"},
            )
        ).json()

    def codes(view: dict[str, Any]) -> list[str]:
        final = next(stage for stage in view["stages"] if stage["id"] == "final")
        return [c["doc_code"] for c in final["candidates"]]

    assert codes(today)[0] == "D07"
    assert "D07-V1" not in codes(today)
    assert codes(before)[0] == "D07-V1"
    assert "D07" not in codes(before)
    runtime.close()


async def test_kb_search_hands_the_agent_the_chunks_and_traces_which_documents(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        await _add(client, {"d07.md": PRICES, "d12.md": BOOKING})
    agent = runtime.live.current()
    tracer = InMemoryTracer()

    await run_turn(
        session_id="s1",
        user_text="Trị nám một buổi bao nhiêu tiền?",
        prompt=PromptBuilder.fixed("sys"),
        model=ScriptedModel(
            [calls(tool_call("kb_search", {"query": "giá trị nám buổi lẻ"}, call_id="c1")), reply("4 triệu")]
        ),
        tools=agent.tools,
        store=InMemorySessionStore(),
        tracer=tracer,
        clock=lambda: ASKED,
    )

    (trace,) = tracer.traces
    tool = trace.events[1]
    assert tool.name == "kb_search"
    assert tool.detail["tool"]["doc_ids"][0] == "D07"
    assert tool.detail["tool"]["as_of"] == "2026-10-12"
    runtime.close()


async def test_a_question_with_no_document_is_recorded_as_a_gap(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        await _add(client, {"d12.md": BOOKING})
        agent = runtime.live.current()
        await run_turn(
            session_id="s1",
            user_text="Có bãi gửi xe ô tô không?",
            prompt=PromptBuilder.fixed("sys"),
            model=ScriptedModel(
                [calls(tool_call("kb_search", {"query": "bãi gửi xe ô tô"})), reply("chưa có")]
            ),
            tools=agent.tools,
            store=InMemorySessionStore(),
            clock=lambda: ASKED,
        )
        gaps = (await client.get(f"{BASE}/gaps")).json()

    assert [g["question"] for g in gaps] == ["bãi gửi xe ô tô"]
    runtime.close()


async def test_the_agent_is_told_how_to_use_the_store(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    agent = runtime.live.current()

    system = await agent.prompt.system(InMemorySessionStore(), "default", "s1")

    assert "kb_search" in agent.tools.names()
    assert "## Kho tri thức" in system
    runtime.close()


CARE = _doc(
    "D05", "Chăm sóc sau điều trị", "# Chăm sóc\nTránh nắng và dùng kem chống nắng 7 ngày sau buổi laser."
)


@contextlib.asynccontextmanager
async def _catalog_job(runtime: Runtime) -> AsyncGenerator[None]:
    """Runs the plugin's job "catalog" for the length of the block."""
    (job,) = [j for j in runtime.plugins.contributions().jobs if j.key == "knowledge/catalog"]
    task = asyncio.create_task(job.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _turn_context(runtime: Runtime) -> str:
    turn = runtime.live.current().prompt.start_turn(TurnInfo(now=ASKED))
    return turn.context(StepInfo(step=1, max_steps=6)) or ""


async def _until_context(runtime: Runtime, check: Callable[[str], bool]) -> str:
    async with asyncio.timeout(5):
        while not check(context := _turn_context(runtime)):  # noqa: ASYNC110 - the job moves this on its own
            await asyncio.sleep(0.01)
    return context


async def test_every_question_carries_a_table_of_the_documents_in_force(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client, _catalog_job(runtime):
        await _add(client, {"d05.md": CARE, "d12.md": BOOKING, "old.md": OLD_PRICES})
        context = await _until_context(runtime, lambda text: "D12" in text)
        care = next(
            s for s in (await client.get(f"{BASE}/sources")).json()["items"] if s["doc_code"] == "D05"
        )
        await client.delete(f"{BASE}/sources/{care['id']}")
        after = await _until_context(runtime, lambda text: "D05" not in text)

    assert "## Mục lục kho tri thức" in context
    assert "- D05: Chăm sóc sau điều trị\n- D12: Đặt lịch" in context
    assert "D07-V1" not in context  # its prices ended before the day asked
    assert "- D12: Đặt lịch" in after
    runtime.close()


async def test_a_store_larger_than_the_limit_gets_no_table_rather_than_half_of_one(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "catalog_max_docs = 1\n")
    async with _client(runtime) as client, _catalog_job(runtime):
        await _add(client, {"d05.md": CARE})
        one = await _until_context(runtime, lambda text: "D05" in text)
        await _add(client, {"d12.md": BOOKING})
        two = await _until_context(runtime, lambda text: "Mục lục" not in text)

    assert "- D05: Chăm sóc sau điều trị" in one
    assert "D05" not in two
    runtime.close()


NEXT_PRICES = _doc(
    "D07",
    "Bảng giá năm sau",
    """
    # Bảng giá
    ## Điều trị nám
    Một buổi laser điều trị nám có giá 4.800.000 đồng theo bảng giá mới của phòng khám.
    """,
    effective_from="2099-01-01",
)


async def test_a_version_that_starts_later_leaves_the_current_one_in_force_until_then(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    async with _client(runtime) as client:
        await _add(client, {"d07.md": PRICES})
        await _add(client, {"d07-next.md": NEXT_PRICES})
        found = (
            await client.post(
                f"{BASE}/search/debug", json={"question": "trị nám một buổi giá", "as_of": "2026-10-12"}
            )
        ).json()
        agent = runtime.live.current()
        tracer = InMemoryTracer()
        await run_turn(
            session_id="s1",
            user_text="Bảng giá trị nám?",
            prompt=PromptBuilder.fixed("sys"),
            model=ScriptedModel([calls(tool_call("kb_read", {"doc_code": "D07"})), reply("ok")]),
            tools=agent.tools,
            store=InMemorySessionStore(),
            tracer=tracer,
            clock=lambda: ASKED,
        )
        listing = (await client.get(f"{BASE}/sources")).json()

    final = next(stage for stage in found["stages"] if stage["id"] == "final")
    assert final["candidates"][0]["source_title"] == "Bảng giá hiện hành"
    old = next(s for s in listing["items"] if s["title"] == "Bảng giá hiện hành")
    (trace,) = tracer.traces
    assert trace.events[1].detail["tool"]["source_id"] == old["id"]
    assert old["lifecycle"] == "active"
    assert old["effective_to"] == "2098-12-31"
    runtime.close()


async def test_confirming_the_same_preview_twice_adds_the_source_once(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    inputs = [{"key": "b", "name": "d12.md", "kind": "file", "size": len(BOOKING), "text": BOOKING}]
    async with _client(runtime) as client:
        preview = (await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})).json()
        body = {"preview_id": preview["preview_id"], "items": [{"key": "b", "title": "Đặt lịch"}]}
        first = (await client.post(f"{BASE}/sources/confirm", json=body)).json()
        again = (await client.post(f"{BASE}/sources/confirm", json=body)).json()
        listing = (await client.get(f"{BASE}/sources")).json()

    assert again["created"] == first["created"]
    assert len(listing["items"]) == 1
    runtime.close()


async def test_a_file_too_long_is_refused_alone(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    long_text = "x" * 2_000_001
    inputs = [
        {"key": "a", "name": "long.txt", "kind": "file", "size": len(long_text), "text": long_text},
        {"key": "b", "name": "d12.md", "kind": "file", "size": len(BOOKING), "text": BOOKING},
    ]
    async with _client(runtime) as client:
        preview = await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})

    errors = [item["error"] for item in preview.json()["items"]]
    assert preview.status_code == 200
    assert errors[0] is not None
    assert errors[1] is None
    runtime.close()


async def test_its_admin_routes_take_documents_larger_than_the_usual_body_limit(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    big = _doc("BIG", "Tài liệu dài", "# Dài\n\n" + "Nội dung chăm sóc da sau điều trị. " * 4000)
    inputs = [{"key": "big", "name": "big.md", "kind": "file", "size": len(big), "text": big}]
    async with _client(runtime) as client:
        preview = await client.post(f"{BASE}/sources/preview", json={"inputs": inputs})
        elsewhere = await client.post("/v1/admin/model/list", content=b"x" * (100 * 1024))

    assert preview.status_code == 200
    assert elsewhere.status_code == 413
    runtime.close()
