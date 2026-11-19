"""Answer bench of the agent (docs/PLAN-rag-graph.md, step 16): does the agent's REPLY hold the right facts, and
does it invent numbers?

Runs the agent of profile ``agents/rag`` in this process (no database, no Docker) with a real model, loads the
demo documents through the knowledge store's own routes, asks every question in a new chat (a follow-up asks its
turns in one chat) and scores each reply by code:

* facts: the expected value of each fact code (the demo's registry) is in the reply;
* invented: numbers of the reply that no document, the question nor today's date holds;
* set C (the documents do not answer): the reply names no number;
* set G (greetings): the reply does not say it has no information;
* cost: model calls, tokens and seconds of the turn (its trace).

    cd backend/apps/agent
    RAG_BENCH_API_KEY=... uv run python scripts/rag_bench.py --graph off \
        --docs "E:/Desktop/data test/AgentRAG_Pema_Demo/01_NAP_EMBEDDING" \
        --registry "E:/Desktop/data test/AgentRAG_Pema_Demo/04_DAP_AN_VA_CHAM_DIEM/REGISTRY_DU_KIEN_PEMA.md" \
        --model deepseek-chat --base-url https://api.deepseek.com --json off.json

The model key is read from RAG_BENCH_API_KEY, the embedding key (optional; keyword search without it) from
BEEKNOEE_API_KEY; neither is printed or written. Documents are loaded without their end date, so a promotion that
ended still answers (the questions were written for 2026-10-12). Costs money: one run is about 50 turns.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_app.cli import _service_env  # pyright: ignore[reportPrivateUsage]
from agent_app.gateway import GatewaySettings, create_app
from agent_app.model_factory import ModelSettings, client_for
from agent_app.proactive import DispatcherOutbox
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime
from plugins.knowledge.answer_graph import day_text, drafted_numbers, numbers

HERE = Path(__file__).parent
PORT = 8195
KB = "/v1/plugins/knowledge"
NO_INFO = ("chua co thong tin", "khong co thong tin", "chua co du lieu")
ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def read_registry(path: Path) -> dict[str, str]:
    return dict(re.findall(r"^\| `([^`]+)` \| `([^`]*)` \|", path.read_text("utf-8"), re.MULTILINE))


def fact_held(reply: str, value: str) -> bool | None:
    """None when the value cannot be checked from text (a true/false of the registry)."""
    if value in ("true", "false"):
        return None
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value) in numbers(reply)
    return fold(value) in fold(reply)


async def start(args: argparse.Namespace, home: Path) -> tuple[Any, uvicorn.Server, asyncio.Task[None]]:
    runtime = build_runtime(load_profile(Path("agents/rag")), fake=True, env=_service_env(home), db=None)
    model = client_for(
        ModelSettings(
            provider=args.provider,
            model=args.model,
            api_key=os.environ.get("RAG_BENCH_API_KEY", ""),
            base_url=args.base_url or None,
            timeout_s=120,
            reasoning=None,
        )
    )
    runtime.live.use_model(model)
    runtime.live.host.use_model(model)
    await runtime.start()
    dispatcher = runtime.dispatcher()
    runtime.plugins.use_proactive(DispatcherOutbox(dispatcher))
    runtime.plugins.use_history(dispatcher.history)
    app = create_app(
        dispatcher,
        GatewaySettings(),
        db=None,
        admin=runtime.model_admin,
        plugins=runtime.plugin_manager,
        channels=runtime.channel_hub(dispatcher),
        jobs=runtime.job_runner(),
        agent_settings=runtime.agent_settings,
        cases=runtime.cases,
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.1)
    return runtime, server, serving


async def load(http: httpx.AsyncClient, folder: Path, args: argparse.Namespace) -> None:
    files = sorted(folder.glob("*.md"))
    inputs = [
        {"key": f.name, "name": f.name, "kind": "file", "size": f.stat().st_size, "text": f.read_text("utf-8")}
        for f in files
    ]
    preview = (await http.post(f"{KB}/sources/preview", json={"inputs": inputs})).raise_for_status().json()
    items = [
        {
            "key": item["key"],
            "title": item["meta"]["title"] or item["name"],
            "doc_code": item["meta"]["doc_code"],
            "lifecycle": item["meta"]["lifecycle"] or "active",
            "effective_from": item["meta"]["effective_from"],
            "effective_to": None,
        }
        for item in preview["items"]
    ]
    body = {"preview_id": preview["preview_id"], "items": items}
    (await http.post(f"{KB}/sources/confirm", json=body)).raise_for_status()
    for source in (await http.get(f"{KB}/sources")).json()["items"]:
        if source.get("status") != "approved":
            await http.post(f"{KB}/sources/{source['id']}/approve")
    patch: dict[str, Any] = {"answer": {"graph": args.graph}}
    if os.environ.get("BEEKNOEE_API_KEY"):
        patch["embedding"] = {
            "base_url": args.embedding_url,
            "model": args.embedding_model,
            "api_key": os.environ["BEEKNOEE_API_KEY"],
        }
    (await http.patch(f"{KB}/settings", json=patch)).raise_for_status()


async def ask(http: httpx.AsyncClient, runtime: Any, user: str, turns: list[str]) -> tuple[str, dict[str, float]]:
    cost = {"calls": 0.0, "tokens": 0.0, "seconds": 0.0}
    reply = ""
    for index, text in enumerate(turns):
        body = {"message_id": f"{user}-{index}", "user_id": user, "text": text}
        answer = (await http.post("/v1/chat", json=body, timeout=600)).json()
        reply = str(answer.get("text") or "")
        trace = runtime.tracer.traces[-1]
        cost["calls"] += trace.steps
        cost["tokens"] += trace.usage.input_tokens + trace.usage.output_tokens
        cost["seconds"] += trace.duration_s
    return reply, cost


def score(item: dict[str, Any], reply: str, cost: dict[str, float], registry: dict[str, str], held: set[float]) -> dict[str, Any]:
    turns = item.get("turns") or [item["q"]]
    known = held | numbers(" ".join(turns)) | numbers(day_text(datetime.now(UTC), ZONE))
    checks = [fact_held(reply, registry[code]) for code in item.get("facts", []) if code in registry]
    graded = [c for c in checks if c is not None]
    invented = [raw for raw, value in drafted_numbers(reply) if value not in known]
    return {
        "set": item["set"],
        "q": " / ".join(turns),
        "reply": reply,
        "facts": len(graded),
        "facts_right": sum(graded),
        "invented": invented,
        "refused": not drafted_numbers(reply),
        "no_info": any(word in fold(reply) for word in NO_INFO),
        **cost,
    }


def table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in sorted({r["set"] for r in rows}):
        group = [r for r in rows if r["set"] == name]
        line = {
            "questions": len(group),
            "facts_right": f"{sum(r['facts_right'] for r in group)}/{sum(r['facts'] for r in group)}",
            "replies_inventing": sum(1 for r in group if r["invented"]),
            "median_calls": statistics.median(r["calls"] for r in group),
            "median_s": round(statistics.median(r["seconds"] for r in group), 1),
            "tokens": int(sum(r["tokens"] for r in group)),
        }
        if name == "C":
            line["refused"] = sum(1 for r in group if r["refused"])
        if name == "G":
            line["said_no_info"] = sum(1 for r in group if r["no_info"])
        out[name] = line
    return out


async def main(args: argparse.Namespace) -> int:
    if not os.environ.get("RAG_BENCH_API_KEY"):
        print("set RAG_BENCH_API_KEY to the model's key", file=sys.stderr)
        return 2
    registry = read_registry(Path(args.registry))
    items = read_jsonl(Path(args.questions)) + read_jsonl(Path(args.extra))
    items = items[: args.limit] if args.limit else items
    held = numbers(" ".join(f.read_text("utf-8") for f in sorted(Path(args.docs).glob("*.md"))))
    with tempfile.TemporaryDirectory() as home:
        runtime, server, serving = await start(args, Path(home))
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=60) as http:
                login = await http.post("/v1/hooks/web/setup", json={"email": "bench@example.com", "password": "rag-bench-only-1234"})
                http.headers["Authorization"] = "Bearer " + str(login.raise_for_status().json()["token"])
                await load(http, Path(args.docs), args)
                rows = []
                for number, item in enumerate(items, start=1):
                    began = time.perf_counter()
                    reply, cost = await ask(http, runtime, f"bench-{number}", item.get("turns") or [item["q"]])
                    row = score(item, reply, cost, registry, held)
                    rows.append(row)
                    print(f"{number:>3} {row['set']} facts {row['facts_right']}/{row['facts']} invented {row['invented']} "
                          f"calls {int(row['calls'])} {time.perf_counter() - began:.1f}s  {row['q'][:50]}")
        finally:
            server.should_exit = True
            await serving
            runtime.close()
    summary = table(rows)
    print(json.dumps({"graph": args.graph, "model": args.model, "sets": summary}, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(
            json.dumps({"graph": args.graph, "model": args.model, "sets": summary, "rows": rows}, ensure_ascii=False, indent=2),
            "utf-8",
        )
    return 0


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs", required=True, help="folder of the demo's .md documents")
    parser.add_argument("--registry", required=True, help="the demo's REGISTRY_DU_KIEN_PEMA.md")
    parser.add_argument("--questions", default=str(HERE / "kb_bench_pema.jsonl"))
    parser.add_argument("--extra", default=str(HERE / "rag_bench_extra.jsonl"), help="follow-ups (F), greetings (G)")
    parser.add_argument("--graph", choices=("off", "on"), default="off", help="the checked answer flow")
    parser.add_argument("--provider", choices=("openai-compatible", "anthropic"), default="openai-compatible")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--embedding-url", default="https://platform.beeknoee.com/api/v1")
    parser.add_argument("--embedding-model", default="qwen/qwen3-embedding-8b")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions (a quick try)")
    parser.add_argument("--json", default="", help="write the numbers and every reply to this file")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse())))
