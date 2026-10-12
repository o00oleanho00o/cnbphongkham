# Plan: embedding + hybrid search (BM25 + vector + RRF) for the `knowledge` plugin (2026-10-12)

Author: tech lead. Builder: a coding agent (Claude in Copilot) or a developer. Read sections 0–3 before changing
any line. Follow the steps of section 6 in order, one commit per step, and run the checks listed at the end of
each step. If the plan is wrong or missing something: stop, write the question in section 12, and do not change
a decision of section 2 on your own.

Related docs (read only when needed): `docs/PLAN-knowledge-plugin.md` (§0, §3.5, §5, §19),
`docs/PLAN-step0-core.md` (tool rule), `docs/HANDOFF-agent-v2.md` (status).

User-facing strings stay in **Vietnamese** exactly as written here (UI text, error sentences, warnings). Code,
comments, docstrings, commit messages: English.

---

## 0. Repo rules (mandatory, no exceptions)

1. **No AI attribution in git**: no `Co-Authored-By: Claude…`, no "Generated with…", no mention of AI/Claude/
   Copilot as an author in commits, PRs or comments. This overrides any default reminder of the tool.
2. **Never write an API key to a file** (code, tests, docs, `.env`, logs, commits). The Beeknoee key only enters
   through the UI (Kho tri thức → Cài đặt → Embedding → "Khóa API") or through the environment variable
   `BEEKNOEE_API_KEY` when running the bench script locally. Tests use fake keys like `"sk-test-synthetic"`.
3. **Never use `git stash`** in this repo (the user keeps old stashes of other branches). Never push unless the
   user asks.
4. **Docker: allowed**, including `docker compose up -d --build`, `build`, `restart`, `stop`, `start`, `ps`,
   `logs`, `exec`, `docker exec … psql`. **Forbidden without the user's explicit OK**: anything that deletes —
   `docker rm`, `docker rmi`, `docker volume rm`, `docker network rm`, `docker compose down -v` (and `down`
   with `--rmi`), `docker compose rm`, any `prune` (`system/image/container/volume/builder prune`, `-a`), and
   SQL that drops or truncates the `pema` database's data.
5. **Run the tests the change touches**, not the whole suite (`.claude/rules/testing.md`). Scope `ruff` and
   `pyright` to the changed paths. Postgres tests (`-m db`) run with `PEMA_TEST_DATABASE_URL` pointing at the
   **throwaway DB** `agent_activity_test`, NEVER at `pema` (the tests drop schema `agent_rt`):
   ```bash
   cd pema-agent/backend
   PW=$(grep '^PEMA_PG_SUPERUSER_PASSWORD=' ../infra/.env.local-demo | cut -d= -f2-)
   PEMA_TEST_DATABASE_URL="postgresql+psycopg://postgres:${PW}@127.0.0.1:15432/agent_activity_test" \
     uv run pytest apps/agent/tests/knowledge -q
   ```
6. **TypeScript** (`plugins/knowledge/ui`): no `switch`, no `let`/`var`, no `for`/`while`/`forEach` loops
   (`forEach` only for side effects), no nested ternaries, no `any`, few `as` (with a comment why), no array
   mutation. **Python**: match the neighbouring files (dataclasses `frozen=True, slots=True`, short English
   docstrings).
7. **Synthetic data** in tests. Never log customer questions or document text; log only lengths, counts, error
   kinds.
8. A **visible** change on the plugin pages (text, label) needs an entry under "Pending" in
   `.claude/skills/pema-web-design/web-design-changes.md` in the same commit (follow the existing "Kho tri thức"
   entries).
9. Comments explain *why*, at the density of the surrounding file. No leftover `print`/debug code. TODOs carry an
   issue number.

---

## 1. Context: what exists (checked on branch `feat/knowledge-ui`, commit `3f5d9605`)

Plugin `backend/apps/agent/plugins/knowledge/` (enabled in profile `agents/clinic`):

| File | Current role |
|---|---|
| `plugin.toml` | manifest: `[migrations] dir="migrations" prefix="kb_"`, `user_config` (results, char_budget, timezone, benchmark_mode), `max_body_kb = 12288` |
| `migrations/0001_create_store.sql` | tables `kb_source`, `kb_chunk` (has `embedded boolean`, `terms tsvector`), `kb_service`, `kb_event`, `kb_gap`. **Never edit this file** (checksummed; an edit stops `agent db migrate-plugins`) |
| `text.py` | accent folding (`fold`), keywords (`terms`, `query_terms`), YAML head (`split_head`), chunking (`chunk` → `Piece(path, text)`; `path` is the heading trail "H2 > H3", **without the document title**), `content_hash` (sha256 of the **stripped** text) |
| `models.py` | `Source`, `Chunk(id, source_id, ordinal, path, body, services, kind, embedded)`, `Hit(chunk, source_title, doc_code, score)`, pydantic route bodies |
| `store.py` | `KnowledgeStore` (Protocol), `InMemoryKnowledgeStore` (pure-Python BM25), `PostgresKnowledgeStore` (SQL via `text()`, `to_tsquery('simple', …)` + `ts_rank_cd`); `in_use()` = ready + active + in force on the date |
| `ingest.py` | preview/confirm, `make_chunks(source_id, pieces, services)`, `rechunk` |
| `search.py` | `Searcher.search()` = keyword → service boost → ≤ 3 chunks per document → char budget; `tool_text`, `tool_detail` (trace), `debug_view` (page "Thử tìm"; vector stage is `skipped`) |
| `plugin.py` | `KnowledgePlugin`: settings (in `ctx.storage["settings"]`), tools `kb_search`/`kb_read`, prompt section, gaps; `MAX_CHAR_BUDGET = 8000` |
| `routes.py` | all admin routes; `/status`, `/settings/test-embedding`, `/settings/reembed` are **stubs** ("embedding not used") |
| `ui/src/**` | the Kho tri thức pages. Cài đặt → Embedding is **already complete**: base URL, model, dimensions, `query_prefix`, `document_prefix`, key box (sends `api_key`, never shown back), buttons "Kiểm tra kết nối" and "Nhúng lại toàn bộ". "Thử tìm" already renders stages `understand`, `keyword`, `vector`, `fused`, `reranked`, `final` |

What the core (`agent_app`) gives a plugin: `ctx.database` (async engine + `tenant_id`, `agent`), `ctx.storage`
(JSON records: `get`, `put`, `delete`, `list` — `agent_app/plugins/records.py`), `ctx.encrypt()/ctx.decrypt()`
(sealed with the service key `AGENT_SECRET_ENCRYPTION_KEY`; `decrypt` raises `PluginError` when the key changed),
`ctx.register_job(name, run)` (background job, runs only under `agent serve`, restarted when it fails, cancelled
when the plugin is disabled), `ctx.on_disable(sync_callback)`, `ctx.logger`. `user_config` types: `string`,
`number`, `integer`, `boolean` (`agent_app/plugins/manifest.py`). `httpx` is already a dependency.

Infra: Postgres image `pgvector/pgvector:pg17`; extension `vector` **0.8.7 is installed in schema `public`** (by
a clinic API migration). Plugin migrations run with `SET LOCAL search_path TO agent_rt` as the owner role
(`postgres` in compose) → SQL files must write **`public.vector`**. The runtime role `agent_rt_app` has search
path `"$user", public`, so runtime queries see the type; still write `OPERATOR(public.<=>)` to be safe.

Current numbers (keyword only, 22 Pema docs, 15 questions): right document at top 1: 6/15, top 3: 14/15, top 6:
14/15.

Real Beeknoee check (2026-10-12, user's key, `qwen/qwen3-embedding-8b`):
- `POST https://platform.beeknoee.com/api/v1/embeddings` (`/v1/embeddings` works too), OpenAI shape.
- No `dimensions` → 4096 dims. `dimensions: 1024` → 1024 dims, normalised (norm 1.000).
- "laser nám bao nhiêu tiền một lần" ranks the price chunk #1: with the Instruct prefix 0.65, without 0.61,
  typed without accents 0.64; unrelated chunks 0.29–0.37.
- **Latency 1.5–4.4 s per call.** One transient JSON error on `/api/v1` (one retry fixed it).

---

## 2. Decisions (fixed; do not change while building)

| # | Decision | Why |
|---|---|---|
| D1 | Default provider: Beeknoee, OpenAI-compatible, `https://platform.beeknoee.com/api/v1`, model `qwen/qwen3-embedding-8b`, **1024 dims**, cosine | user's choice 2026-10-12; generic client, so a provider change is a settings change |
| D2 | **A vector belongs to a text, not to a chunk row**: new table `kb_embedding(space, text_hash, vector)`; `kb_chunk` gains `embed_text`, `embed_hash`. Re-cutting a source with unchanged text needs **no** new vectors | `rechunk` and `add_source` delete and re-insert chunk rows every time |
| D3 | **Vector space** `space` = `sha256("{model}\|{dimensions}\|{document_prefix}").hexdigest()[:16]`. A new model, dimension count or document prefix = a new space; spaces never mix | never compare vectors of two models |
| D4 | Column `vector public.vector` **without a dimension**, **no HNSW index** now: exact scan over a few hundred/thousand chunks takes milliseconds | dimension changes need no migration; HNSW needs fixed dims. > 20,000 chunks: see section 11 |
| D5 | Text embedded for a chunk: `embed_text = f"{source_title}\n{path}\n\n{body}"`. At send time `document_prefix` (default empty) goes in front | the chunk carries "bảng giá", "chăm sóc sau laser" context; `path` alone lacks the title |
| D6 | Questions are sent with `query_prefix`, default Qwen3-style: `"Instruct: Given a question from a skin clinic's customer, retrieve the passages of the clinic's documents that answer it\nQuery: "` | measured: wider margin with the instruction |
| D7 | Merge with **RRF** (k = 60): `score = Σ 1/(60 + rank)` over the keyword list (≤ 40) and the vector list (≤ 40, cosine similarity ≥ threshold). Then the existing steps unchanged: service boost, ≤ 3 chunks per document, char budget | standard; no score calibration between branches |
| D8 | **When vectors are off, failing or too slow, results must be exactly today's** (keyword only, BM25 scores, no RRF) | never degrade what runs now; regression test required |
| D9 | The question is embedded **in parallel** with the keyword search; wait at most `vector_timeout_s` (default 6 s); on timeout drop the vector branch for that search and record why in the trace | Beeknoee latency 1.5–4.4 s |
| D10 | Query-vector cache **in process memory only** (LRU 512, key `(space, query_prefix, stripped question)`). Customer questions are never stored in the DB | privacy; repeated questions skip 2–4 s |
| D11 | Chunks are embedded by the plugin's **background job** `embed` (batches of 16), never blocking ingest: a new source is searchable by keyword at once, by vector seconds–minutes later | ingest does not depend on an outside service |
| D12 | API key stored **sealed** (`ctx.encrypt`) in `ctx.storage` under its own record `embedding_api_key`, **not** inside the `settings` JSON. The API only returns `has_key: bool` | same as Zalo's secrets |
| D13 | The vector threshold reuses the existing setting `search.min_score` ("Điểm tối thiểu", 0–1) = **minimum cosine similarity**, default **0.35** (measured: wrong chunks 0.29–0.37, right ≥ 0.6). Tune only with the bench (step 5) | no new UI field |
| D14 | Calling Beeknoee is **plugin infrastructure, not a tool** → not covered by `allow_internet = false` (that rule forbids *tools* looking things up online). Privacy: customer questions are sent to Beeknoee to be embedded; masking phone/ID numbers is **off for the demo** (user's call) and must be on before real patients | consistent with PLAN-step0-core.md §0.2b |
| D15 | Only chunks of sources with `processing = 'ready' AND lifecycle = 'active'` are embedded (including future-dated ones) | drafts/expired/superseded are never searched; don't pay for them |
| D16 | Not in this plan: rerank, LLM labelling, masking, HNSW, several agent processes | section 11 |

---

## 3. Architecture after the change

```
                 ┌──────────────── kb_search(query) ────────────────┐
                 │                                                   │
   query_terms ──┤  (in parallel)                                    │
                 │  store.search(terms)          embedder.query(q)   │  ← LRU cache, 6 s timeout
                 │      ≤40 BM25 hits           store.vector_search  │  ← cosine ≥ min_score, ≤40
                 │            └────────── fuse (RRF k=60) ──────────┘│  ← vectors off/failing: skip this
                 │              → service boost → ≤3 per document → char budget
                 └──────────────── tool_text + tool_detail(trace) ──┘

   background job "embed" (every 5 s, woken at once by new sources / settings changes):
     store.missing_vectors(space, 16) → EmbeddingClient.embed(document_prefix + embed_text) → store.save_vectors
     hourly: store.drop_stale_vectors(space)
```

New files: `embedding.py` (HTTP client, config, errors), `embedder.py` (job, query cache, status), `fusion.py`
(pure RRF), `migrations/0002_vectors.sql`, `scripts/kb_bench.py` + `scripts/kb_bench_pema.jsonl`, new tests.
Changed: `models.py`, `store.py`, `ingest.py`, `search.py`, `plugin.py`, `routes.py`, `plugin.toml`,
`__init__.py`, a few UI files.

---

## 4. Data: migration `0002_vectors.sql`

Create `backend/apps/agent/plugins/knowledge/migrations/0002_vectors.sql` (verbatim; change it only if Postgres
rejects it, and only before it has ever run anywhere):

```sql
-- Vectors for the knowledge store. A vector belongs to a text, not to a chunk row: chunks are deleted and
-- inserted again whenever a source is re-cut, and their text (so their vector) usually stays the same.
-- `space` names the model, dimensions and document prefix a vector was made with (sha256, 16 hex).
-- The vector type lives in schema public (pgvector); this file runs with search_path agent_rt.

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

ALTER TABLE kb_chunk ADD COLUMN embed_text text NOT NULL DEFAULT '';
ALTER TABLE kb_chunk ADD COLUMN embed_hash text NOT NULL DEFAULT '';

-- chunks stored before this file: the same text as plugins/knowledge/text.py embed_text_of() builds
UPDATE kb_chunk c
SET embed_text = s.title || E'\n' || c.path || E'\n\n' || c.body
FROM kb_source s
WHERE s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id;

UPDATE kb_chunk SET embed_hash = encode(sha256(convert_to(embed_text, 'UTF8')), 'hex');

ALTER TABLE kb_chunk DROP COLUMN embedded;

CREATE INDEX kb_chunk_embed ON kb_chunk (tenant_id, agent, embed_hash);

CREATE TABLE kb_embedding (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    space text NOT NULL CHECK (space ~ '^[0-9a-f]{16}$'),
    text_hash text NOT NULL CHECK (text_hash ~ '^[0-9a-f]{64}$'),
    vector public.vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, space, text_hash)
);
```

Notes:
- `migrate-plugins` grants SELECT/INSERT/UPDATE/DELETE on `kb_embedding` to `agent_rt_app` by itself (prefix
  `kb_`). No core change.
- Python **must** match the SQL: `embed_text_of(title, path, body) -> f"{title}\n{path}\n\n{body}"`,
  `text_hash(t) = hashlib.sha256(t.encode("utf-8")).hexdigest()`. A Postgres test compares both (step 2).
- After the migration a chunk has no `embedded` column: "has a vector" is **computed on read** (LEFT JOIN
  `kb_embedding` on the current `space`).
- `kb_source.progress.embedded` (jsonb) is no longer the truth: routes take per-source counts from
  `vector_counts(space)`. Keep writing 0 into the jsonb, stop reading it.

---

## 5. Module design

### 5.1 `embedding.py` (new): config, client, errors

```python
EMBED_BATCH: Final = 16          # texts per call
EMBED_MAX_CHARS: Final = 8000    # a text is cut to this before it is sent (Qwen3 takes ~32k tokens)
TEST_TEXT: Final = "Kiểm tra kết nối: bảng giá điều trị nám"

ErrorKind = Literal["config", "auth", "not_found", "rate_limit", "server", "timeout", "network", "bad_response",
                    "dimensions"]

@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    base_url: str
    model: str
    dimensions: int
    query_prefix: str
    document_prefix: str
    api_key: str = field(repr=False)          # never in repr/logs
    key_broken: bool = False                  # a stored key that no longer decrypts

    @property
    def ready(self) -> bool: ...              # base_url, model, api_key non-empty and not key_broken
    @property
    def space(self) -> str: ...               # sha256(f"{model}|{dimensions}|{document_prefix}").hexdigest()[:16]
    @property
    def endpoint(self) -> str: ...            # see "URL" below

class EmbeddingError(Exception):
    def __init__(self, kind: ErrorKind, message: str) -> None: ...   # message: Vietnamese, for a person
    kind: ErrorKind
    transient: bool                            # True for rate_limit, server, timeout, network, bad_response

@dataclass(frozen=True, slots=True)
class Probe:
    dimensions: int        # length the provider returned, before any cut
    norm: float            # L2 norm the provider returned
    ms: float

class EmbeddingClient:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None,
                 timer: Callable[[], float] = time.perf_counter) -> None: ...
    async def embed(self, config: EmbeddingConfig, texts: Sequence[str], *, timeout_s: float) -> list[list[float]]: ...
    async def probe(self, config: EmbeddingConfig, *, timeout_s: float = 15.0) -> Probe: ...
```

Required behaviour:
- **URL**: `base_url.rstrip("/")`; if it already ends with `/embeddings` use it as is, else append
  `/embeddings` (`…/api/v1` → `…/api/v1/embeddings`; `…/v1/` → `…/v1/embeddings`).
- **Request**: `POST`, `Authorization: Bearer <key>`, JSON body `{"model": model, "input": [...], "dimensions":
  dimensions, "encoding_format": "float"}`. Each text cut to `EMBED_MAX_CHARS`. 1 to `EMBED_BATCH` texts (more →
  `ValueError`; the caller batches).
- **Response**: `data` sorted by `index`; vector count must equal text count, else `bad_response`. Each vector:
  longer than `dimensions` → cut `[:dimensions]` (Qwen3 is Matryoshka-trained) and renormalise; shorter →
  `dimensions` error; always L2-normalise (norm 0 → `bad_response`); every element a finite number.
- **Errors → Vietnamese sentences** (never copy more than 200 chars of the provider's body, never the key):
  - not `ready` → `config` "Chưa cài địa chỉ, model hoặc khóa API cho embedding." (`key_broken` → "Khóa API đã
    lưu không giải mã được (khóa bí mật của agent đã đổi). Nhập lại khóa.")
  - 401/403 → `auth` "Khóa API sai hoặc hết hạn."
  - 404 → `not_found` "Sai địa chỉ hoặc tên model."
  - 400/422 whose body mentions "dimension" → `dimensions` "Model không nhận số chiều {n}."; other 400/422 →
    `bad_response`.
  - 429 → `rate_limit` "Dịch vụ embedding đang giới hạn lượt gọi, thử lại sau."
  - 5xx → `server` "Dịch vụ embedding lỗi (HTTP {code})."
  - `httpx.TimeoutException` → `timeout` "Quá {timeout_s:g} giây không trả lời."
  - other `httpx.TransportError` → `network` "Không kết nối được tới {host}."
  - bad JSON / no `data` → `bad_response` "Dịch vụ trả về dữ liệu không đọc được."
- **One `httpx.AsyncClient` per call** (`async with httpx.AsyncClient(transport=self._transport,
  follow_redirects=False) as http:`). No long-lived client: `ctx.on_disable` takes only a sync callback, so it
  cannot close an async client, and each call already takes 1.5–4 s. (Zalo also opens its clients inside its run
  loop and closes them in `finally`, see `plugins/zalo/bot/channel.py`.)
- Logging: only `logger.info("embedded %d texts in %.0f ms", n, ms)` and error kinds; never texts, never the key.

### 5.2 `fusion.py` (new): pure RRF

```python
RRF_K: Final = 60

def fuse(ranked: Sequence[Sequence[Hit]], k: int = RRF_K) -> list[Hit]:
    """Reciprocal rank fusion: each chunk scores the sum of 1/(k + rank) over the lists it is in (rank from 1).
    The Hit kept for a chunk is its first appearance (keyword list first); its score becomes the RRF score.
    Ties: the order of first appearance."""
```
No async, no I/O, own tests (section 7).

### 5.3 `text.py`: add

```python
def embed_text_of(title: str, path: str, body: str) -> str:
    """What a chunk is embedded as: its document's title, its headings and its text (the SQL of
    migrations/0002_vectors.sql builds the same string for chunks stored before it)."""
    return f"{title}\n{path}\n\n{body}"

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```
**Do not reuse `content_hash`**: it strips the text before hashing, the migration's SQL does not.

### 5.4 `models.py`

- `Chunk`: add `embed_text: str = ""` and a property `embed_hash` (`text_hash(embed_text)`, `""` when
  `embed_text` is empty). Keep the field `embedded: bool = False`, now **filled on read** by the store. `shown()`
  keeps its shape (the UI reads `embedded`).
- `Hit` unchanged. `Hit.score` means: BM25 (keyword branch), cosine similarity 0–1 (vector branch), RRF (after
  fusion).

### 5.5 `ingest.py`

- `make_chunks(source_id, title, pieces, services)`: new `title` parameter, fills
  `embed_text=embed_text_of(title, piece.path, piece.text)`. Update every caller (`_add`, `rechunk`,
  `tests/knowledge/test_knowledge_db.py`). `rechunk` uses `source.title` (route `split` passes `new_source`, whose
  title is already the new one).
- `Ingest.__init__(..., on_change: Callable[[], None] = lambda: None)`; call it after a source is added or
  re-cut, so the plugin wakes the embed job.

### 5.6 `store.py`

Add to `KnowledgeStore` (Protocol) and to **both** stores:

```python
async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]: ...
    # (embed_hash, embed_text) of distinct texts of chunks of ready + active sources with no vector in `space`
async def missing_count(self, space: str) -> int: ...
    # chunks (not distinct texts) of ready + active sources with no vector in `space`
async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None: ...
    # ON CONFLICT DO NOTHING
async def vector_search(self, space: str, vector: Sequence[float], as_of: date, limit: int,
                        min_similarity: float) -> list[Hit]: ...
    # Hit.score = cosine similarity (1 - distance); same source filters as search(); best first
async def vector_counts(self, space: str) -> dict[str, int]: ...
    # source_id -> number of its chunks that have a vector in `space`
async def clear_vectors(self, space: str) -> int: ...
    # deletes every vector of this tenant/agent in `space`; returns rows deleted
async def drop_stale_vectors(self, space: str) -> int: ...
    # deletes vectors of other spaces, and vectors in `space` that no chunk refers to any more
```
and change:
```python
async def chunks(self, source_id: str, q: str, page: int, page_size: int, space: str | None) -> tuple[list[Chunk], int]
    # each Chunk.embedded = it has a vector in `space` (False when space is None)
```

**Postgres** (same style as now: `text()` + `bindparam`, every statement scoped by `tenant_id = :tenant_id AND
agent = :agent`):
- Pass a vector as the string `"[0.0123,-0.04,…]"` (`"[" + ",".join(repr(float(x)) for x in v) + "]"`) with
  `CAST(:vector AS public.vector)`. Do not add the `pgvector` Python package.
- `_INSERT_CHUNK`: drop `embedded`, add `embed_text`, `embed_hash`.
- `_CHUNKS`: `LEFT JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent AND e.space =
  :space AND e.text_hash = c.embed_hash`, select `(e.text_hash IS NOT NULL) AS embedded`. `space` None → pass
  `''` (matches nothing).
- `_SEARCH` (keyword): remove `c.embedded`; select `false AS embedded` and `c.embed_text`.
- `_VECTOR_SEARCH`:
  ```sql
  SELECT c.id, c.source_id, c.ordinal, c.path, c.body, c.services, c.kind, c.embed_text, true AS embedded,
         s.title, s.doc_code,
         1 - (e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) AS score
  FROM agent_rt.kb_chunk c
  JOIN agent_rt.kb_source s ON s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id
  JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent
       AND e.space = :space AND e.text_hash = c.embed_hash
  WHERE c.tenant_id = :tenant_id AND c.agent = :agent
    AND s.processing = 'ready' AND s.lifecycle = 'active'
    AND (s.effective_from IS NULL OR s.effective_from <= :as_of)
    AND (s.effective_to IS NULL OR s.effective_to >= :as_of)
    AND 1 - (e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) >= :min_similarity
  ORDER BY e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector), c.id
  LIMIT :limit
  ```
- `_MISSING_VECTORS`:
  ```sql
  SELECT DISTINCT ON (c.embed_hash) c.embed_hash, c.embed_text
  FROM agent_rt.kb_chunk c
  JOIN agent_rt.kb_source s ON s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id
  WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.embed_hash <> ''
    AND s.processing = 'ready' AND s.lifecycle = 'active'
    AND NOT EXISTS (SELECT 1 FROM agent_rt.kb_embedding e WHERE e.tenant_id = c.tenant_id
                    AND e.agent = c.agent AND e.space = :space AND e.text_hash = c.embed_hash)
  ORDER BY c.embed_hash
  LIMIT :limit
  ```
- `_MISSING_COUNT`: same filter, `SELECT count(*)` (chunks, not distinct).
- `_SAVE_VECTOR`: `INSERT … (tenant_id, agent, space, text_hash, vector) VALUES (…, CAST(:vector AS
  public.vector)) ON CONFLICT DO NOTHING`, executemany (list of dicts) in **one** transaction.
- `_VECTOR_COUNTS`: `SELECT c.source_id, count(*) FROM kb_chunk c JOIN kb_embedding e ON … AND e.space = :space
  AND e.text_hash = c.embed_hash WHERE <scope> GROUP BY c.source_id`.
- `_CLEAR_VECTORS`: `DELETE FROM agent_rt.kb_embedding WHERE <scope> AND space = :space`.
- `_DROP_STALE`: `DELETE FROM agent_rt.kb_embedding e WHERE <scope> AND (e.space <> :space OR NOT EXISTS (SELECT
  1 FROM agent_rt.kb_chunk c WHERE c.tenant_id = e.tenant_id AND c.agent = e.agent AND c.embed_hash =
  e.text_hash))`.
- `rowcount` read as the existing `delete` methods do.

**In-memory**: `self._vectors: dict[tuple[str, str], tuple[float, ...]]` keyed `(space, text_hash)`. Cosine = dot
product (vectors are normalised), a pure `_cosine(a, b)` with `math.fsum`. `vector_search` filters with
`in_use()` exactly like `search`. Used by tests and the bench script.

### 5.7 `embedder.py` (new): job, query cache, status

```python
IDLE_S: Final = 5.0
NOT_READY_S: Final = 30.0
BACKOFF_S: Final = (5.0, 15.0, 60.0, 300.0)
STOP_S: Final = 300.0             # config/auth/not_found/dimensions: wait for a settings change (or 5 min)
CLEANUP_EVERY_S: Final = 3600.0
QUERY_CACHE: Final = 512
DOCUMENT_TIMEOUT_S: Final = 60.0

State = Literal["off", "working", "ok", "error"]

@dataclass(frozen=True, slots=True)
class EmbedStatus:
    state: State
    message: str | None        # Vietnamese sentence for the page, None when all is well
    missing: int               # chunks with no vector in the current space
    model: str | None
    last_ok_at: datetime | None

class Embedder:
    def __init__(self, store: KnowledgeStore, client: EmbeddingClient,
                 config: Callable[[], Awaitable[EmbeddingConfig]], *,
                 clock: Callable[[], datetime] = ..., idle_s: float = IDLE_S,
                 logger: logging.Logger) -> None: ...
    def wake(self) -> None: ...                          # sets an asyncio.Event
    async def step(self) -> bool: ...                    # one batch; True when it embedded something
    async def run(self) -> None: ...                     # the job: loop of step() with waits; never returns
    async def query_vector(self, question: str, timeout_s: float) -> tuple[list[float], str]: ...
        # (vector, space); a cache hit returns at once; raises EmbeddingError / TimeoutError
    async def status(self) -> EmbedStatus: ...
```

`step()`:
1. `config = await self._config()`. Not `ready` → state `off` (message "Embedding chưa kết nối: đang tìm bằng
   từ khóa." or the broken-key sentence), return False.
2. `items = await store.missing_vectors(config.space, EMBED_BATCH)`; empty → state `ok`, return False.
3. `vectors = await client.embed(config, [config.document_prefix + text for _, text in items],
   timeout_s=DOCUMENT_TIMEOUT_S)`. A `transient` error → **retry once at once**; still failing → raise.
4. `await store.save_vectors(config.space, list(zip(hashes, vectors)))`; state `working` (some still missing)
   or `ok`; `last_ok_at = clock()`; return True.

`run()` (never returns; let `CancelledError` through):
- `step()` True → continue at once (still `await asyncio.sleep(0)`).
- False → wait `idle_s` (`NOT_READY_S` when `off`) **or** until `wake()`, whichever is first.
- Transient `EmbeddingError` → state `error` + message, wait per `BACKOFF_S` (growing, reset after a success).
  Non-transient → `error`, wait `STOP_S` or until `wake()`.
- Any other exception (bug, DB) → `logger.exception`, state `error` "Lỗi khi nhúng, xem log agent.", wait per
  `BACKOFF_S`.
- Every `CLEANUP_EVERY_S`: `drop_stale_vectors(space)` (only when `ready`).
- A config change (`space` differs from last time) resets the backoff.
- Docstring note: the job runs only under `agent serve`; under `agent chat` existing vectors are used and new
  chunks are searched by keyword only. Accepted.

`query_vector`: `collections.OrderedDict` cache keyed `(space, query_prefix, question.strip())`, LRU 512; miss →
`asyncio.wait_for(client.embed(config, [query_prefix + question], timeout_s=timeout_s), timeout_s)`; **no**
retry (latency). Config not `ready` → `EmbeddingError("config", …)`.

`status()`: in-memory state + `missing_count(space)` (when `ready`) + `model`.

### 5.8 `search.py`

```python
@dataclass(frozen=True, slots=True)
class VectorPlan:
    min_similarity: float
    timeout_s: float
    embed: Callable[[str, float], Awaitable[tuple[list[float], str]]]   # Embedder.query_vector

@dataclass(frozen=True, slots=True)
class SearchResult:
    question: str
    folded: str
    terms: tuple[str, ...]
    services: tuple[str, ...]
    as_of: date
    candidates: tuple[Hit, ...]          # keyword list (name kept: routes/tests read it)
    vector: tuple[Hit, ...]              # vector list, empty when not used
    fused: tuple[Hit, ...]               # after RRF; equals candidates when no fusion happened
    final: tuple[Hit, ...]
    keyword_ms: float
    vector_ms: float                     # embed + vector SQL, 0 when not used
    vector_note: str | None              # why the vector branch was skipped or failed (Vietnamese), else None
    total_ms: float

    @property
    def vector_used(self) -> bool: return self.vector_note is None
```

`Searcher.search(question, as_of, *, results, char_budget, services, vector: VectorPlan | None = None)`:
1. `named`, `wanted` as now.
2. Run in parallel (`asyncio.TaskGroup` or `gather`): `store.search(wanted, as_of, CANDIDATES)` and, when
   `vector` is given, the vector branch: `vec, space = await vector.embed(question, vector.timeout_s)` then
   `store.vector_search(space, vec, as_of, CANDIDATES, vector.min_similarity)`. Catch `EmbeddingError` →
   `vector_note = err.message`; `TimeoutError` → `vector_note = f"Nhúng câu hỏi quá {timeout:g} giây: lượt này
   chỉ tìm bằng từ khóa."`. `vector is None` → `vector_note = "Embedding chưa bật: chỉ tìm bằng từ khóa."`.
3. `ranked = fuse([candidates, vector_hits])` when `vector_used` **and** `vector_hits` is non-empty; otherwise
   `ranked = candidates` (BM25 scores kept — D8). A vector branch that ran but found nothing above the threshold
   keeps `vector_note = None`.
4. Service boost → `_spread` → `_packed` as now.
5. Gaps: `plugin._search_tool` still records a gap when `final` is empty.

`tool_text`: format unchanged. `tool_detail` adds `"keyword_candidates"`, `"vector_candidates"`,
`"vector_used"`, `"vector_ms"` (rounded), `"vector_skip"` (`None` or a short code `"off" | "timeout" | "error"` —
no long sentences in the trace), `"top_similarity"` (best vector similarity, 4 decimals, 0 if none). Keep the
existing keys (`doc_ids`, `as_of`, `returned`, …): measurement reads them.

`debug_view`: real `vector` stage (ms; note "N đoạn gần nghĩa, độ giống ≥ {min}" or `vector_note`; `skipped =
not vector_used`; candidates scored by similarity); new `fused` stage ("Gộp RRF (k = 60)", skipped when no
fusion) between `vector` and `final`. Replace the constant `NO_VECTOR` with the sentences of item 2.

### 5.9 `plugin.py`

- `default_settings(config)`: group `embedding` defaults come from the new `user_config` keys (5.11);
  `search.min_score` defaults to `float(config.get("vector_min_similarity", 0.35))`.
- `async embedding_config() -> EmbeddingConfig`: `settings()["embedding"]` + key: `sealed = await
  ctx.storage.get("embedding_api_key")`; if present `ctx.decrypt(sealed)`; `PluginError` → `api_key=""`,
  `key_broken=True`.
- `save_settings(patch)` with `api_key` in group `embedding`:
  - `""` → `await ctx.storage.delete("embedding_api_key")`.
  - otherwise `strip()`, length 8–500, then `ctx.storage.put("embedding_api_key", ctx.encrypt(key))`.
  - `has_key` in the response = a sealed record exists (computed on read, **never stored** in the JSON).
  - `PluginError` from `encrypt` (no service key) → route answers 409 "Agent chưa có khóa bí mật để mã hóa
    (chạy bằng agent serve)."
  - after saving group `embedding` → `self.embedder.wake()`.
- Server-side checks for group `embedding` (in `routes._checked_settings`): `base_url` empty or
  `^https?://\S+$` ≤ 500 chars; `model` 1–200; `dimensions` int 32–4096; `query_prefix`/`document_prefix` ≤ 500.
  Wrong → 422 with a Vietnamese sentence like the existing checks.
- Construction: `KnowledgePlugin.__init__(ctx, *, store=None, clock=…, client: EmbeddingClient | None = None)`;
  `self.client = client or EmbeddingClient()`; `self.embedder = Embedder(self.store, self.client,
  self.embedding_config, clock=clock, idle_s=float(ctx.config.get("embedding_idle_s", IDLE_S)),
  logger=ctx.logger)`; `self.ingest = Ingest(..., on_change=self.embedder.wake)`.
- `register()`: add `ctx.register_job("embed", self.embedder.run)`. No `on_disable` needed (no long-lived client;
  the core cancels the job).
- `_search_tool`: build `VectorPlan(min_similarity=settings["search"]["min_score"],
  timeout_s=float(ctx.config.get("vector_timeout_s", 6.0)), embed=self.embedder.query_vector)` **only when**
  `(await self.embedding_config()).ready`, else `None`.
- `kb_read` unchanged.

### 5.10 `routes.py`

| Route | After |
|---|---|
| `GET /status` | `{"embedding_connected": status.state in ("ok", "working"), "embedding_model": status.model, "queue": status.missing, "warnings": _warnings(status)}` |
| `GET /sources` | `summary.embedded_percent` from `vector_counts(space)`; each returned source has the real `embedded`; `warnings = _warnings(status)` (only when there are sources) |
| `GET /sources/{id}` | real `embedded` |
| `GET /sources/{id}/chunks` | pass `space` (None when not `ready`) |
| `GET /settings` | real `embedding.has_key`; `embedding.chunks_without_vector = status.missing` (0 when not `ready`; the page already warns "not connected") |
| `PATCH /settings` | `api_key` handling (5.9), value checks, wake the job |
| `POST /settings/test-embedding` | `probe(config)` → `{"ok": true, "dimensions": probe.dimensions, "normalised": abs(probe.norm - 1) < 0.01, "ms": round(probe.ms), "message": "Kết nối tốt"}`; `EmbeddingError` → `{"ok": false, "dimensions": null, "normalised": null, "ms": null, "message": err.message}` (HTTP 200) |
| `POST /settings/reembed` | `clear_vectors(space)`; `queued = missing_count(space)`; `wake()`; return `{"queued": queued}`. Not `ready` → 409 "Chưa kết nối embedding." |
| `POST /search/debug` | pass a `VectorPlan` like `kb_search` |

`_warnings(status)`: `off` → `["Embedding chưa kết nối: đang tìm bằng từ khóa."]` (or the broken-key
sentence); `error` → `[f"Embedding đang lỗi: {message} Các đoạn chưa có vector chỉ được tìm bằng từ khóa."]`;
`working` with `missing > 0` → `[f"Đang nhúng: còn {missing} đoạn chưa có vector."]`; `ok` → `[]`. Remove the old
constant `KEYWORD_ONLY` if unused.

### 5.11 `plugin.toml`

Bump `version = "0.3.0"`. Add `user_config` keys (same style as the existing ones):

| Key | Type | Default | Description |
|---|---|---|---|
| `embedding_base_url` | string | `"https://platform.beeknoee.com/api/v1"` | OpenAI-compatible base URL of the embedding service |
| `embedding_model` | string | `"qwen/qwen3-embedding-8b"` | Embedding model |
| `embedding_dimensions` | integer | `1024` | Dimensions asked for (vectors are cut and normalised to this) |
| `embedding_query_prefix` | string | the D6 instruction (TOML string with `\n`) | Put before a question when it is embedded |
| `embedding_document_prefix` | string | `""` | Put before a chunk when it is embedded |
| `vector_min_similarity` | number | `0.35` | Least cosine similarity a vector candidate needs |
| `vector_timeout_s` | number | `6.0` | Seconds a search waits for the question's vector |

Read with `float(ctx.config.get(...))` / `int(...)` as `default_settings` does now. Test-only config keys
(`embedding_transport`, `embedding_idle_s`) are **not** declared in the manifest (same as Zalo's
`bot_transport`).

### 5.12 UI (`plugins/knowledge/ui/src`), small

1. `settings/settings-logic.ts` `reembedWarning`: new sentence "Mọi đoạn của kho sẽ được nhúng lại bằng
   {model}. Việc chạy nền và tốn phí gọi embedding; trong lúc đó các đoạn chưa có vector mới chỉ được tìm bằng
   từ khóa." (D2/D3: old vectors are not used meanwhile).
2. `settings/search-section.tsx`: hint of "Điểm tối thiểu" → "Độ giống tối thiểu (0 đến 1) của kết quả tìm theo
   nghĩa; mặc định 0,35".
3. `try/try-logic.ts`: `SCORE_LABEL.vector` "khoảng cách" → "độ giống" (the server sends similarity, higher is
   better).
4. Update the matching tests (`settings-logic.test.ts`, try-logic tests if any); run `pnpm exec tsc --noEmit -p .`
   and `pnpm exec vitest run` in `plugins/knowledge/ui`.
5. Add a "Pending" entry to `.claude/skills/pema-web-design/web-design-changes.md`:
   `### 2026-10-1x · change · Kho tri thức: embedding thật (Cài đặt, Thử tìm, cảnh báo)` listing the 3 changed
   sentences, the new warnings above the sources table and the "Gộp RRF" stage. "Web canvas target: none (no
   canvas frame for the agent pages)".
6. Web mock (`pema-agent/frontend/mock/knowledge/*`): **optional**; if touched, only make `dev:mock` return a
   `fused` stage. Do not touch the frontend's `src/**`.

---

## 6. Steps (one commit each; English messages like `feat(agent): …`; NO attribution)

Work on a new branch `feat/knowledge-embedding` created from `feat/knowledge-ui`.

### Step 1: embedding client + RRF (no DB, no behaviour change)
- Create `embedding.py`, `fusion.py`; add `embed_text_of`/`text_hash` to `text.py`.
- New tests `tests/knowledge/test_embedding.py`, `tests/knowledge/test_fusion.py` (section 7).
- Check: `uv run pytest apps/agent/tests/knowledge/test_embedding.py apps/agent/tests/knowledge/test_fusion.py -q`;
  `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` on the changed files.
- Commit: `feat(agent): knowledge embedding client (OpenAI-compatible, cut and normalise to the set dimensions, errors a person can read) and reciprocal rank fusion`

### Step 2: migration + store
- `migrations/0002_vectors.sql`; change `models.py`, `store.py` (both stores), `ingest.py` (`make_chunks` takes
  `title`, `on_change`).
- Fix old tests that call `make_chunks` / `chunks(...)`.
- New in-memory and Postgres tests (section 7).
- Check: knowledge tests (non-db) + db tests on the throwaway DB (command in 0.5) + ruff/pyright.
- Commit: `feat(agent): knowledge vectors keyed by text and vector space (kb_embedding), cosine search in force on the day asked`

### Step 3: embedder (job, cache, status) + wiring into plugin/routes/search
- `embedder.py`; change `search.py`, `plugin.py`, `routes.py`, `plugin.toml`, `__init__.py` (transport hook,
  section 11b).
- Tests: `test_embedder.py` (new), update `test_knowledge_plugin.py` (section 7).
- Check: `uv run pytest apps/agent/tests/knowledge -q` (+ db) and `apps/agent/tests/test_plugin_runtime.py`
  (plugin loading), ruff/pyright.
- Commit: `feat(agent): knowledge store searches by meaning too: a background job embeds chunks, kb_search fuses keyword and vector candidates (RRF), falls back to keywords when the service is off, slow or failing`

### Step 4: UI + design change log
- Section 5.12. Check tsc + vitest.
- Commit: `feat(agent): knowledge pages read the real embedding status; wording for re-embedding, similarity and the fused stage`

### Step 5: bench + numbers
- `backend/apps/agent/scripts/kb_bench.py` and `backend/apps/agent/scripts/kb_bench_pema.jsonl` (section 8).
- Run the 3 modes, paste the table into section 10; tune `vector_min_similarity` **only** on this bench (record
  the values tried and their results).
- Commit: `test(agent): knowledge retrieval bench (keyword, vector, hybrid) on the Pema demo corpus, with results`

### Step 6: run for real in Docker
- From the repo root: `docker compose up -d --build` (allowed; deleting anything is not, rule 0.4).
- `docker compose logs agent-migrate` must show `knowledge: ran 0002_vectors.sql` and
  `granted … on agent_rt.kb_embedding`.
- Ask the user to enter the key in Kho tri thức → Cài đặt → Embedding; "Kiểm tra kết nối" must show "Kết nối
  tốt · 1024 chiều · đã chuẩn hóa · … ms". (The builder never types or stores the key.)
- Wait until the warning strip no longer says "Đang nhúng…"; check with a read-only query:
  `docker exec cnbphongkham-postgres-1 psql -U postgres -d pema -tAc "select space, count(*) from agent_rt.kb_embedding group by 1"`
  → one `space`, row count ≈ chunk count (minus duplicate texts).
- "Thử tìm" with 3 questions of set B (section 8): stage "Ứng viên vector" has candidates, stage "Gộp RRF" shows.
- Update `docs/HANDOFF-agent-v2.md` (short entry: what was built, numbers, how to turn it on) and the status
  line of §19.4 in `PLAN-knowledge-plugin.md`. Commit the docs.

---

## 7. Required tests (suggested names; follow the existing style: an English sentence describing behaviour)

### `test_embedding.py` (httpx.MockTransport, like `tests/zalo/test_bot_client.py`)
- `test_it_posts_the_model_the_texts_and_the_dimensions_with_the_key` — URL `…/api/v1/embeddings`, Bearer
  header, body.
- `test_the_endpoint_is_joined_once` — `…/v1`, `…/v1/`, `…/v1/embeddings` → the same URL.
- `test_vectors_come_back_in_input_order` — response `data` in reversed `index` order.
- `test_a_longer_vector_is_cut_to_the_set_dimensions_and_normalised` — 8 dims → 4, norm 1.
- `test_a_shorter_vector_is_an_error_about_dimensions`.
- `test_errors_become_sentences` — parametrised 401, 403, 404, 429, 500, 400 "dimensions", bad JSON, timeout,
  ConnectError → right `kind`, `transient`, Vietnamese message; **the message never contains the key**.
- `test_a_config_without_a_key_is_not_ready`; `test_the_space_changes_with_model_dimensions_and_document_prefix`
  (not with `query_prefix`, `base_url`, `api_key`).
- `test_the_key_is_not_in_the_configs_repr`.

### `test_fusion.py`
- Two lists with common chunks → common ones first; score matches the formula (rank 1 in both = 2/61).
- One empty list → the other's order unchanged.
- Ties → order of first appearance.

### In-memory + plugin (`test_knowledge_plugin.py`, `test_embedder.py`)
Use the **deterministic fake embedding** of section 11b: "da bị sạm" (no word "nám") is close to the melasma
chunk by vector but does **not** match by keyword.
- `test_the_job_embeds_every_chunk_once` — `step()` until False; `missing_count == 0`; again → no API call.
- `test_re_cutting_a_source_with_the_same_text_needs_no_new_vectors` — reindex → no extra API call.
- `test_changing_the_model_makes_every_chunk_missing_again` — new `model` → `chunks_without_vector` = all chunks;
  `drop_stale_vectors` removes the old space.
- `test_a_paraphrase_is_found_by_meaning` — a question only the vector branch can match is in `final`;
  `tool_detail["vector_used"] is True`.
- `test_without_embedding_the_results_are_the_keyword_results` — **D8 regression**: same question with
  `vector=None` → `final` identical to the keyword branch (compare `[(h.chunk.id, h.score)]`).
- `test_a_slow_embedding_falls_back_to_keywords` — fake slower than the timeout (timeout 0.05 s in the test) →
  `vector_note` mentions "quá", `final` = keyword results.
- `test_the_query_vector_is_cached` — same question twice → one API call.
- `test_the_api_key_is_stored_sealed_and_never_sent_back` — PATCH `api_key` → GET settings `has_key` True, the
  response JSON has no key, the stored record differs from the key (runtime built with
  `env={"AGENT_SECRET_ENCRYPTION_KEY": KEY}` like `tests/zalo/test_accounts.py`).
- `test_an_empty_key_removes_it`.
- `test_test_embedding_reports_dimensions_and_norm` and `…_reports_the_error_sentence`.
- `test_reembed_clears_the_space_and_counts_the_queue`.
- `test_status_warns_while_off_working_and_failing`.
- Fix old tests that use `embedded` or `make_chunks`.

### Postgres (`test_knowledge_db.py`, `pytestmark = pytest.mark.db`)
- The existing fixture runs alembic + `migrate_plugins` → now also `0002`.
- `test_vectors_are_found_by_cosine_in_force_on_the_day_asked` — 2 sources (old/new like the existing test), fake
  4-dim vectors; `vector_search` returns the right source per date, `score` ≈ cosine, another tenant sees nothing.
- `test_missing_vectors_lists_each_text_once_and_save_is_idempotent`.
- `test_chunks_report_whether_they_have_a_vector`.
- `test_drop_stale_vectors_keeps_only_the_current_space_and_used_texts`.
- `test_the_migration_builds_the_same_embed_text_as_python` — insert a chunk, run the migration's two `UPDATE`
  statements on it, compare `embed_text`/`embed_hash` with `embed_text_of(...)` / `text_hash(...)`.

Run all knowledge tests (db included) before each commit of steps 2–3.

---

## 8. Bench: `scripts/kb_bench.py`

Purpose: learn what vectors buy and tune the threshold. Runs outside Docker with `InMemoryKnowledgeStore` + the
real `EmbeddingClient`.

```
cd pema-agent/backend/apps/agent
uv run python scripts/kb_bench.py \
  --docs "E:\Desktop\data test\AgentRAG_Pema_Demo\01_NAP_EMBEDDING" \
  --questions scripts/kb_bench_pema.jsonl --as-of 2026-10-12 \
  --modes keyword,vector,hybrid [--min-similarity 0.35] [--sweep 0.25,0.30,0.35,0.40,0.45] [--json out.json]
```

- Key from env `BEEKNOEE_API_KEY` (already a Windows user variable on the user's machine; **never print it, never
  write it**). No key → run `keyword` only and say so in one line.
- The script adds the `apps/agent` folder to `sys.path` to import `plugins.knowledge`.
- Load documents through `Ingest.preview/confirm` (YAML read, `lifecycle` from the meta).
- Embed all chunks by calling `Embedder.step()` until False (same code as the real job).
- Per question × mode: take `final` (results 6, char_budget 6000), compare document codes with `expect` (a match
  on **any** listed code). Print a table: mode, set, top1, top3, top6, MRR, median latency; then each miss.
- Mode `vector` = vector branch only (no keywords). `--sweep` prints hybrid results per threshold.

`scripts/kb_bench_pema.jsonl` (one line `{"set": "A"|"B", "q": …, "expect": [codes…]}`), **verbatim**:

```jsonl
{"set": "A", "q": "trị nám 1 buổi bao nhiêu tiền", "expect": ["DEMO-PEMA-D07"]}
{"set": "A", "q": "gói 10 buổi nám giá bao nhiêu, có giảm giá không", "expect": ["DEMO-PEMA-D08", "DEMO-PEMA-D07", "DEMO-PEMA-D09"]}
{"set": "A", "q": "khuyến mại tháng này", "expect": ["DEMO-PEMA-D09"]}
{"set": "A", "q": "hủy lịch có mất tiền không", "expect": ["DEMO-PEMA-D13"]}
{"set": "A", "q": "đặt lịch có phải cọc không", "expect": ["DEMO-PEMA-D12"]}
{"set": "A", "q": "bảo lưu gói được bao lâu", "expect": ["DEMO-PEMA-D08"]}
{"set": "A", "q": "hoàn tiền gói thế nào", "expect": ["DEMO-PEMA-D14"]}
{"set": "A", "q": "sau laser cần kiêng gì", "expect": ["DEMO-PEMA-D05"]}
{"set": "A", "q": "bớt hori có làm ở HCM không", "expect": ["DEMO-PEMA-D02", "DEMO-PEMA-D12", "DEMO-PEMA-D03"]}
{"set": "A", "q": "phòng khám ở đâu, mấy giờ mở cửa", "expect": ["DEMO-PEMA-D01"]}
{"set": "A", "q": "kem chống nắng giá bao nhiêu", "expect": ["DEMO-PEMA-D11"]}
{"set": "A", "q": "mụn trị thế nào", "expect": ["DEMO-PEMA-D10"]}
{"set": "A", "q": "khiếu nại bao lâu thì được trả lời", "expect": ["DEMO-PEMA-D15"]}
{"set": "A", "q": "có được chụp ảnh trước sau không", "expect": ["DEMO-PEMA-D16"]}
{"set": "A", "q": "bị sưng đỏ sau điều trị thì làm sao", "expect": ["DEMO-PEMA-D17", "DEMO-PEMA-D05"]}
{"set": "B", "q": "da mặt bị sạm nâu từng mảng là bệnh gì", "expect": ["DEMO-PEMA-D03"]}
{"set": "B", "q": "bắn laser có rát không", "expect": ["DEMO-PEMA-D06", "DEMO-PEMA-D04"]}
{"set": "B", "q": "làm xong bao lâu thì đánh phấn được", "expect": ["DEMO-PEMA-D06"]}
{"set": "B", "q": "đốm xanh xám ở gò má có chữa được không", "expect": ["DEMO-PEMA-D03", "DEMO-PEMA-D02"]}
{"set": "B", "q": "quẹt thẻ được không", "expect": ["DEMO-PEMA-D14", "DEMO-PEMA-D18"]}
{"set": "B", "q": "lỡ hẹn không tới thì có bị phạt không", "expect": ["DEMO-PEMA-D13"]}
{"set": "B", "q": "đi công tác 2 tháng muốn tạm dừng liệu trình", "expect": ["DEMO-PEMA-D08"]}
{"set": "B", "q": "lấy hóa đơn công ty được không", "expect": ["DEMO-PEMA-D14", "DEMO-PEMA-D18"]}
{"set": "B", "q": "có viên uống nào giúp da đẹp không", "expect": ["DEMO-PEMA-D11"]}
{"set": "B", "q": "bên mình có mấy cơ sở", "expect": ["DEMO-PEMA-D01", "DEMO-PEMA-D18"]}
{"set": "B", "q": "rủ bạn đi cùng có được ưu đãi gì không", "expect": ["DEMO-PEMA-D09"]}
{"set": "B", "q": "da bị phồng rộp chảy dịch sau khi bắn laser", "expect": ["DEMO-PEMA-D17", "DEMO-PEMA-D05"]}
{"set": "B", "q": "cho xin số tổng đài", "expect": ["DEMO-PEMA-D01", "DEMO-PEMA-D18"]}
{"set": "B", "q": "không muốn bị đăng ảnh mặt lên mạng", "expect": ["DEMO-PEMA-D16"]}
{"set": "B", "q": "nhân viên thái độ không tốt thì góp ý ở đâu", "expect": ["DEMO-PEMA-D15"]}
```

Set A = questions using the documents' words (keyword is already good: top3 14/15). Set B = paraphrases (where
vectors must help). The builder **may** fix a set-B `expect` if reading the documents shows the plan named the
wrong code (record why in section 12), but must **not** drop hard questions.

---

## 9. Definition of Done

1. All section-7 tests pass, Postgres included on the throwaway DB; ruff, ruff format, pyright clean on changed
   files; tsc + vitest of `plugins/knowledge/ui` pass.
2. **No regression**: hybrid on set A ≥ keyword on set A at top3 (now 14/15) and top6.
3. **A gain**: hybrid on set B beats keyword on set B at top3 (write the numbers). If it does not: do not tune
   for looks; report the numbers and a hypothesis in section 12.
4. Vectors off (no key) → the Kho tri thức pages, `kb_search` and the trace behave exactly as before; the warning
   strip says "chưa kết nối".
5. Wrong key → "Kiểm tra kết nối" shows "Khóa API sai hoặc hết hạn."; `kb_search` still answers by keyword
   within one timeout; the trace has `vector_skip = "error"`.
6. In Docker: `kb_embedding` holds a vector for every chunk of active sources; the trace of a real Zalo turn has
   `vector_used: true`.
7. No key, customer question or document text in the agent log (`docker compose logs agent | grep -i "sk-"` is
   empty).
8. Docs: HANDOFF + §19.4 updated; section 10 of this file has the numbers.

---

## 10. Results (filled by the builder in step 5)

| Mode | Set | top1 | top3 | top6 | MRR | median latency | threshold |
|---|---|---|---|---|---|---|---|
| keyword | A | | | | | | – |
| keyword | B | | | | | | – |
| vector | A | | | | | | |
| vector | B | | | | | | |
| hybrid | A | | | | | | |
| hybrid | B | | | | | | |

---

## 11. Risks and later work

| Risk / item | Now | Later |
|---|---|---|
| Beeknoee slow (1.5–4.4 s) | parallel keyword search, 6 s timeout, query cache | measure real latency from traces; consider a smaller model if p50 > 3 s |
| Beeknoee down | keyword fallback, page warning, job backoff | – |
| Customer questions leave the system | stated in D14; accepted for the demo | mask phone/ID/email before embedding questions, before real patients |
| Large store | exact scan | > 20,000 chunks: partial HNSW index on `(vector::public.vector(1024))` `WHERE space = '…'` for the space in use, or a fixed-dimension column |
| Several agent processes | not supported (compose runs one) | `pg_try_advisory_lock` around `step()` |
| Rerank | not done | next: listwise LLM rerank through `ctx.model` (needs core work) |
| Comparing models (Gemini, BGE-M3) | generic client; a model change is a new space | run `kb_bench.py` per model |
| LLM labelling/context | not done | after rerank |

---

## 11b. Test helpers (copy and adapt)

### Inject a fake HTTP transport: same pattern as Zalo

Zalo takes a fake transport through a config key **not declared in `plugin.toml`** (`plugins/zalo/__init__.py`:
`ctx.config.get("bot_transport")`; tests: `host.enable("zalo", {..., "bot_transport": fake.transport})` then
`build_runtime(..., plugins=host)`, see `tests/zalo/test_bot_channel.py::_runtime`). Do the same:

```python
# plugins/knowledge/__init__.py
def register(ctx: PluginContext) -> None:
    # ``embedding_transport`` is not a manifest setting: tests hand in an httpx transport that fakes the service
    transport = ctx.config.get("embedding_transport")
    plugin = KnowledgePlugin(
        ctx, client=EmbeddingClient(transport=transport if isinstance(transport, httpx.AsyncBaseTransport) else None)
    )
    plugin.register()
    ctx.register_routes(knowledge_routes(plugin))
```

```python
# tests/knowledge/test_knowledge_plugin.py
KEY = "0f" * 32   # AGENT_SECRET_ENCRYPTION_KEY of the test service (synthetic)

def _runtime(tmp_path: Path, transport: httpx.MockTransport | None = None) -> tuple[Runtime, PluginHost]:
    folder = ...  # agent.toml like the existing _runtime
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    config = {} if transport is None else {"embedding_transport": transport, "embedding_idle_s": 0.01}
    host.enable("knowledge", config)
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host), host
```

### Run the embed job in a test through public paths

```python
async def _embed_all(host: PluginHost, client: httpx.AsyncClient) -> None:
    """Runs the plugin's job "embed" until the settings page says no chunk is waiting, then stops it."""
    (job,) = [j for j in host.contributions().jobs if j.key == "knowledge/embed"]
    task = asyncio.create_task(job.run())
    try:
        async with asyncio.timeout(5):
            while (await client.get(f"{BASE}/settings")).json()["embedding"]["chunks_without_vector"] > 0:
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```
Unit tests of `Embedder` itself (`test_embedder.py`) build `Embedder(InMemoryKnowledgeStore(),
EmbeddingClient(transport=…), config=…)` directly and call `step()`.

### Deterministic fake embedding

```python
CONCEPTS: Final = (
    ("nam", "sam", "dom nau", "hori"),          # pigment
    ("gia", "tien", "bao nhieu", "phi"),        # price
    ("huy", "lo hen", "doi lich"),              # cancel/reschedule
    ("bao luu", "tam dung"),                    # pause a package
    ("the", "chuyen khoan", "hoa don"),         # payment
)


def concept_vector(text: str) -> list[float]:
    """One axis per concept (how often its words appear), plus a small constant so no vector is zero."""
    folded = f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "
    raw = [float(sum(folded.count(f" {word} ") for word in words)) for words in CONCEPTS] + [0.1]
    norm = math.sqrt(math.fsum(x * x for x in raw))
    return [x / norm for x in raw]


def embeddings_transport(calls: list[list[str]]) -> httpx.MockTransport:
    """An OpenAI-compatible /embeddings that answers with concept vectors and records every input it got."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(list(body["input"]))
        data = [{"index": i, "embedding": concept_vector(t)} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"object": "list", "data": data, "model": body["model"]})

    return httpx.MockTransport(answer)
```

Test settings: `dimensions = 6` (5 concepts + 1 constant), `base_url = "https://embed.test/v1"`, key
`"sk-test-synthetic"`. Note `fold("năm")` is also `nam`: keep "năm" out of the test documents. Count `calls` to
assert "no new API call" (cache, re-cut with the same text). Slow fake for timeout tests: an `async` handler with
`await asyncio.sleep(1)` and `timeout_s = 0.05`.

---

## 11c. Brief to hand to the builder (paste as is)

```
You build the `knowledge` plugin of this repo on a new branch feat/knowledge-embedding created from
feat/knowledge-ui. Follow pema-agent/docs/PLAN-knowledge-embedding.md exactly.

1. Read sections 0, 1, 2 and 3 of the plan before changing code. Section 0 is absolute: no AI attribution in
   commits, never write an API key to a file, no git stash, no push, Docker allowed except deleting anything
   (rm, rmi, volume rm, down -v, prune), targeted tests only, db tests only against agent_activity_test.
2. Do steps 1 → 6 of section 6 in order. Per step: code, the section-7 tests of that step, ruff + ruff format +
   pyright on changed files, then one commit with the suggested message (English, no attribution). Never merge
   steps.
3. Do not change a decision of section 2. If the plan is wrong or missing something: stop that step, write it in
   section 12 (date, step, problem, proposal) and report; do not invent another architecture.
4. Step 5: run scripts/kb_bench.py and fill section 10. The key comes from env BEEKNOEE_API_KEY; never print it.
   Do not edit questions to improve numbers.
5. After each step report briefly: what was done, which tests ran and their result, what is left.
```

---

## 12. Builder's questions / notes

(Write here when the plan is wrong or missing something, or when you had to choose differently. Each entry:
date, step, problem, what you did.)
