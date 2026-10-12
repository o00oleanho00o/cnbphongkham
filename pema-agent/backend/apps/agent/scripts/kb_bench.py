"""Retrieval bench of the knowledge store: what keyword search, vector search and both (vector first) find.

Loads the Markdown documents of a folder into an in-memory store the way the pages do (YAML heads read),
embeds the chunks with the real embedding service, asks every question of a JSON-lines file and says in how
many the right document is in the first 1, 3 and 6 results. Runs outside Docker, never touches a database.

    cd pema-agent/backend/apps/agent
    uv run python scripts/kb_bench.py --docs "E:/Desktop/data test/AgentRAG_Pema_Demo/01_NAP_EMBEDDING" \
        --questions scripts/kb_bench_pema.jsonl --modes keyword,vector,hybrid --sweep 0.25,0.30,0.35,0.40,0.45

The key is read from the environment variable BEEKNOEE_API_KEY and is never printed or written; without it
only the keyword mode runs. A questions file holds one object per line:
{"set": "A", "q": ..., "expect": [doc codes]}.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins.knowledge.embedder import Embedder
from plugins.knowledge.embedding import EmbeddingClient, EmbeddingConfig, EmbeddingError
from plugins.knowledge.ingest import Ingest
from plugins.knowledge.models import ConfirmItem, Hit, PreviewInput
from plugins.knowledge.search import PER_DOCUMENT, Searcher, VectorPlan
from plugins.knowledge.store import InMemoryKnowledgeStore

BASE_URL: Final = "https://platform.beeknoee.com/api/v1"
MODEL: Final = "qwen/qwen3-embedding-8b"
QUERY_PREFIX: Final = (
    "Instruct: Given a question from a skin clinic's customer, retrieve the passages of the clinic's "
    "documents that answer it\nQuery: "
)
RESULTS: Final = 6
CHAR_BUDGET: Final = 6000
CANDIDATES: Final = 40
WAIT_S: Final = 30.0
MODES: Final = ("keyword", "vector", "hybrid")


@dataclass(frozen=True, slots=True)
class Question:
    group: str
    text: str
    expect: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Outcome:
    question: Question
    codes: tuple[str, ...]
    """Document codes of the final chunks, best first (a code repeats for each chunk of that document)."""
    ms: float

    def rank(self) -> int | None:
        """1-based position of the first right document among the distinct documents, or None."""
        distinct = list(dict.fromkeys(self.codes))
        found = [i for i, code in enumerate(distinct, start=1) if code in self.question.expect]
        return found[0] if found else None

    def within(self, count: int) -> bool:
        return any(code in self.question.expect for code in self.codes[:count])


def read_questions(path: Path) -> list[Question]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [Question(row["set"], row["q"], tuple(row["expect"])) for row in rows]


def read_documents(folder: Path) -> list[PreviewInput]:
    return [
        PreviewInput(key=f.name, name=f.name, kind="file", size=f.stat().st_size, text=f.read_text("utf-8"))
        for f in sorted(folder.glob("*.md"))
    ]


def write_report(path: str, report: object, args: argparse.Namespace) -> None:
    public = {key: value for key, value in vars(args).items() if "key" not in key}
    Path(path).write_text(json.dumps({"report": report, "args": public}, indent=2), "utf-8")


def say(text: str) -> None:
    # bytes, so a Windows console in cp1252 does not choke on Vietnamese
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.flush()


async def load_documents(store: InMemoryKnowledgeStore, inputs: Sequence[PreviewInput]) -> int:
    """Adds every document as a source (their YAML heads give code, title and dates)."""
    ingest = Ingest(store)
    preview = await ingest.preview(inputs, benchmark=False)
    items = [
        ConfirmItem(
            key=item["key"],
            title=item["meta"]["title"] or item["name"],
            doc_code=item["meta"]["doc_code"],
            lifecycle=item["meta"]["lifecycle"] or "active",
            effective_from=item["meta"]["effective_from"],
            effective_to=item["meta"]["effective_to"],
        )
        for item in preview["items"]
    ]
    result = await ingest.confirm(preview["preview_id"], items, [], benchmark=False)
    return len(result["created"])


def final_chunks(hits: Sequence[Hit]) -> list[Hit]:
    """What the agent would be handed from a list of hits: at most PER_DOCUMENT chunks per document, then
    RESULTS chunks within the character budget."""
    seen: dict[str, int] = {}
    kept: list[Hit] = []
    used = 0
    for hit in hits:
        if seen.get(hit.chunk.source_id, 0) >= PER_DOCUMENT:
            continue
        if len(kept) >= RESULTS or (kept and used + len(hit.chunk.body) > CHAR_BUDGET):
            break
        seen[hit.chunk.source_id] = seen.get(hit.chunk.source_id, 0) + 1
        kept.append(hit)
        used += len(hit.chunk.body)
    return kept


class Bench:
    def __init__(self, store: InMemoryKnowledgeStore, config: EmbeddingConfig, as_of: date) -> None:
        self.store = store
        self.config = config
        self.as_of = as_of
        self.client = EmbeddingClient()
        self.searcher = Searcher(store)

    def embedder(self) -> Embedder:
        """A new embedder per mode, so one mode's cached question vectors do not speed up the next."""

        async def read() -> EmbeddingConfig:
            return self.config

        return Embedder(self.store, self.client, read, logger=logging.getLogger("kb_bench"))

    async def embed_chunks(self) -> int:
        embedder = self.embedder()
        total = await self.store.missing_count(self.config.space)
        while await embedder.step():
            left = await self.store.missing_count(self.config.space)
            say(f"  embedded {total - left}/{total} chunks")
        return total

    async def ask(self, mode: str, question: Question, embedder: Embedder, min_similarity: float) -> Outcome:
        loop = asyncio.get_running_loop()
        started = loop.time()
        if mode == "vector":
            vector, space = await embedder.query_vector(question.text, WAIT_S)
            found = await self.store.vector_search(space, vector, self.as_of, CANDIDATES, min_similarity)
            hits = final_chunks(found)
        else:
            plan = None if mode == "keyword" else VectorPlan(min_similarity, WAIT_S, embedder.query_vector)
            result = await self.searcher.search(
                question.text, self.as_of, results=RESULTS, char_budget=CHAR_BUDGET, services=[], vector=plan
            )
            if plan is not None and not result.vector_used:
                raise RuntimeError(f"the vector branch failed: {result.vector_note}")
            hits = list(result.final)
        codes = tuple(hit.doc_code or hit.chunk.source_id for hit in hits)
        return Outcome(question, codes, (loop.time() - started) * 1000)

    async def run(self, mode: str, questions: Sequence[Question], min_similarity: float) -> list[Outcome]:
        embedder = self.embedder()
        return [await self.ask(mode, question, embedder, min_similarity) for question in questions]


def summary(outcomes: Sequence[Outcome]) -> dict[str, float]:
    count = len(outcomes) or 1
    ranks = [o.rank() for o in outcomes]
    return {
        "n": len(outcomes),
        "top1": sum(1 for o in outcomes if o.within(1)),
        "top3": sum(1 for o in outcomes if o.within(3)),
        "top6": sum(1 for o in outcomes if o.within(RESULTS)),
        "mrr": sum(1 / r for r in ranks if r) / count,
        "median_ms": statistics.median(o.ms for o in outcomes) if outcomes else 0.0,
    }


def show(label: str, group: str, outcomes: Sequence[Outcome]) -> dict[str, float]:
    data = summary([o for o in outcomes if group == "ALL" or o.question.group == group])
    n = int(data["n"])
    say(
        f"{label:<22} {group:<4} top1 {int(data['top1']):>2}/{n}  top3 {int(data['top3']):>2}/{n}  "
        f"top6 {int(data['top6']):>2}/{n}  MRR {data['mrr']:.3f}  median {data['median_ms']:>6.0f} ms"
    )
    return data


def misses(outcomes: Sequence[Outcome]) -> None:
    for o in outcomes:
        if not o.within(3):
            got = list(dict.fromkeys(o.codes))[:4]
            want = list(o.question.expect)
            say(f"    miss top3 [{o.question.group}] {o.question.text!r} want {want} got {got}")


def config_from(args: argparse.Namespace) -> EmbeddingConfig:
    return EmbeddingConfig(
        base_url=args.base_url,
        model=args.model,
        dimensions=args.dimensions,
        query_prefix=QUERY_PREFIX,
        document_prefix="",
        api_key=os.environ.get("BEEKNOEE_API_KEY", ""),
    )


async def main(args: argparse.Namespace) -> int:
    store = InMemoryKnowledgeStore()
    added = await load_documents(store, read_documents(Path(args.docs)))
    questions = read_questions(Path(args.questions))
    bench = Bench(store, config_from(args), date.fromisoformat(args.as_of))
    modes = [m for m in args.modes.split(",") if m in MODES]
    chunks = await store.missing_count(bench.config.space)
    say(f"{added} documents, {chunks} chunks, {len(questions)} questions, as of {args.as_of}")
    if not bench.config.ready and modes != ["keyword"]:
        say("BEEKNOEE_API_KEY is not set: running the keyword mode only")
        modes = ["keyword"]
    if any(m != "keyword" for m in modes):
        try:
            await bench.embed_chunks()
        except EmbeddingError as err:
            say(f"embedding failed: {err.message}")
            return 1
    report: dict[str, dict[str, dict[str, float]]] = {}
    for mode in modes:
        outcomes = await bench.run(mode, questions, args.min_similarity)
        label = mode if mode == "keyword" else f"{mode} (>= {args.min_similarity:g})"
        report[mode] = {group: show(label, group, outcomes) for group in ("A", "B", "ALL")}
        misses(outcomes)
    thresholds = [float(x) for x in args.sweep.split(",") if x.strip()] if "hybrid" in modes else []
    for threshold in thresholds:
        outcomes = await bench.run("hybrid", questions, threshold)
        for group in ("A", "B"):
            show(f"hybrid sweep {threshold:g}", group, outcomes)
    if args.json:
        write_report(args.json, report, args)
    return 0


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--docs", required=True, help="folder of .md documents")
    parser.add_argument("--questions", required=True, help="JSON-lines file of questions")
    parser.add_argument("--as-of", default="2026-10-12", help="the day the questions are asked on")
    parser.add_argument("--modes", default="keyword,vector,hybrid")
    parser.add_argument("--min-similarity", type=float, default=0.35)
    parser.add_argument("--sweep", default="", help="comma-separated thresholds to try in hybrid mode")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--json", default="", help="write the numbers to this file")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse())))
