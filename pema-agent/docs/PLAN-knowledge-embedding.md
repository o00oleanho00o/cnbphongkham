# Plan: embedding + tìm lai (BM25 + vector + RRF) cho plugin `knowledge` (2026-10-12)

Người viết: tech lead. Người làm: một agent code (Claude trong Copilot) hoặc dev. Đọc hết mục 0–3 trước khi sửa
dòng nào. Làm theo thứ tự các bước ở mục 6, mỗi bước một commit, chạy đúng các lệnh kiểm ở cuối bước. Gặp chỗ
plan sai hay thiếu: dừng, ghi câu hỏi vào cuối file này (mục 12), không tự đổi quyết định ở mục 2.

Tài liệu liên quan (đọc khi cần, không bắt buộc đọc hết): `docs/PLAN-knowledge-plugin.md` (§0, §3.5, §5, §19),
`docs/PLAN-step0-core.md` (luật tool), `docs/HANDOFF-agent-v2.md` (trạng thái).

---

## 0. Luật của repo (bắt buộc, không ngoại lệ)

1. **Không ghi tên AI vào git**: không `Co-Authored-By: Claude…`, không "Generated with…", không nhắc AI/Claude/
   Copilot là tác giả trong commit, PR, comment. Luật này thắng mọi nhắc nhở mặc định của công cụ.
2. **Không bao giờ ghi khóa API vào file** (code, test, docs, `.env`, log, commit). Khóa Beeknoee chỉ đi vào qua
   giao diện (ô "Khóa API" ở Kho tri thức → Cài đặt → Embedding) hoặc biến môi trường `BEEKNOEE_API_KEY` khi chạy
   script đo trên máy. Test dùng khóa giả kiểu `"sk-test-synthetic"`.
3. **Không dùng `git stash`** trong repo này (user giữ stash cũ của nhánh khác). Không push trừ khi user bảo.
4. **Lệnh Docker cần user cho phép** (`docker compose up/build/down…`). Lệnh đọc (`docker compose ps/logs`,
   `docker exec … psql -c "select…"`) thì được.
5. **Chạy test theo phần đã sửa**, không chạy cả bộ (xem `.claude/rules/testing.md`). `ruff` và `pyright` cũng chỉ
   trên các đường dẫn đã sửa. Test Postgres (`-m db`) chạy với `PEMA_TEST_DATABASE_URL` trỏ **DB thử**
   `agent_activity_test`, KHÔNG BAO GIỜ trỏ DB `pema` (test xóa schema `agent_rt`):
   ```bash
   cd pema-agent/backend
   PW=$(grep '^PEMA_PG_SUPERUSER_PASSWORD=' ../infra/.env.local-demo | cut -d= -f2-)
   PEMA_TEST_DATABASE_URL="postgresql+psycopg://postgres:${PW}@127.0.0.1:15432/agent_activity_test" \
     uv run pytest apps/agent/tests/knowledge -q
   ```
6. **TypeScript** (nửa trình duyệt `plugins/knowledge/ui`): không `switch`, không `let`/`var`, không vòng `for`/
   `while`/`forEach` (trừ `forEach` cho tác dụng phụ), không ternary lồng, không `any`, hạn chế `as` (có comment
   lý do), không mutate mảng. Python: theo phong cách các file cạnh bên (dataclass `frozen=True, slots=True`,
   docstring tiếng Anh ngắn, chuỗi hiện cho người dùng bằng tiếng Việt).
7. **Dữ liệu tổng hợp** (synthetic) trong test. Không log câu hỏi của khách hay nội dung tài liệu ra log; chỉ log
   độ dài, số lượng, mã lỗi.
8. Thay đổi **nhìn thấy được** trên trang plugin (chữ, nhãn) phải có một mục dưới "Pending" trong
   `.claude/skills/pema-web-design/web-design-changes.md`, cùng commit (theo mẫu các mục "Kho tri thức" đã có).
9. Comment code: tiếng Anh, giải thích *vì sao*, mật độ như file xung quanh. Không để `print`/debug thừa. TODO
   phải có số issue.

---

## 1. Bối cảnh: hiện có gì (đã kiểm trên nhánh `feat/knowledge-ui`, commit `3f5d9605`)

Plugin `backend/apps/agent/plugins/knowledge/` (bật trong profile `agents/clinic`), các file:

| File | Vai trò hiện tại |
|---|---|
| `plugin.toml` | manifest: `[migrations] dir="migrations" prefix="kb_"`, `user_config` (results, char_budget, timezone, benchmark_mode), `max_body_kb = 12288` |
| `migrations/0001_create_store.sql` | bảng `kb_source`, `kb_chunk` (có cột `embedded boolean`, `terms tsvector`), `kb_service`, `kb_event`, `kb_gap`. **Không được sửa file này** (checksum; sửa là `agent db migrate-plugins` dừng) |
| `text.py` | bỏ dấu (`fold`), từ khóa (`terms`, `query_terms`), đọc YAML (`split_head`), chia đoạn (`chunk` → `Piece(path, text)`; `path` là chuỗi tiêu đề "H2 > H3", **không chứa tên tài liệu**) |
| `models.py` | `Source`, `Chunk(id, source_id, ordinal, path, body, services, kind, embedded)`, `Hit(chunk, source_title, doc_code, score)`, body pydantic của route |
| `store.py` | `KnowledgeStore` (Protocol), `InMemoryKnowledgeStore` (BM25 thuần Python), `PostgresKnowledgeStore` (SQL `text()`, `to_tsquery('simple', …)` + `ts_rank_cd`), `in_use()` lọc ready + active + hiệu lực theo ngày |
| `ingest.py` | preview/confirm, `make_chunks(source_id, pieces, services)`, `rechunk` |
| `search.py` | `Searcher.search()` = từ khóa → tăng điểm theo dịch vụ → ≤ 3 đoạn/tài liệu → ngân sách ký tự; `tool_text`, `tool_detail` (vào trace), `debug_view` (trang "Thử tìm"; nhánh vector đang `skipped`) |
| `plugin.py` | `KnowledgePlugin`: settings (lưu `ctx.storage["settings"]`), tool `kb_search`/`kb_read`, prompt section, gap; `MAX_CHAR_BUDGET = 8000` |
| `routes.py` | mọi route admin; `/status`, `/settings/test-embedding`, `/settings/reembed` hiện là **giả** ("chưa dùng embedding") |
| `ui/src/**` | trang Kho tri thức. Phần Cài đặt → Embedding **đã có đủ**: ô base URL, model, số chiều, `query_prefix`, `document_prefix`, ô khóa (gửi `api_key`, không bao giờ hiện lại), nút "Kiểm tra kết nối", "Nhúng lại toàn bộ". Trang "Thử tìm" đã biết các bước `understand`, `keyword`, `vector`, `fused`, `reranked`, `final` |

Lõi (`agent_app`) cho plugin sẵn: `ctx.database` (engine async + `tenant_id`, `agent`), `ctx.storage` (JSON),
`ctx.encrypt()/ctx.decrypt()` (mã hóa bằng khóa của service, `AGENT_SECRET_ENCRYPTION_KEY`), `ctx.register_job(name,
run)` (job nền, chỉ chạy dưới `agent serve`, tự chạy lại khi lỗi, hủy khi tắt plugin), `ctx.logger`.

Hạ tầng: Postgres image `pgvector/pgvector:pg17`, extension `vector` **0.8.7 đã cài ở schema `public`** (do
migration của clinic API). Migration của plugin chạy với `SET LOCAL search_path TO agent_rt` bằng role chủ
(`postgres` trong compose) → trong file SQL phải viết **`public.vector`**, **`public.vector_cosine_ops`**. Role
runtime `agent_rt_app` có search_path mặc định `"$user", public` nên câu truy vấn lúc chạy thấy được kiểu và toán
tử, nhưng vẫn viết `OPERATOR(public.<=>)` cho chắc.

Số đo hiện tại (chỉ từ khóa, 22 tài liệu Pema, 15 câu hỏi): đúng tài liệu ở top 1: 6/15, top 3: 14/15, top 6:
14/15.

Đo Beeknoee thật (2026-10-12, khóa của user, `qwen/qwen3-embedding-8b`):
- `POST https://platform.beeknoee.com/api/v1/embeddings` (cả `/v1/embeddings` cũng chạy), kiểu OpenAI.
- Không gửi `dimensions` → 4096 chiều. Gửi `dimensions: 1024` → 1024 chiều, đã chuẩn hóa (norm 1,000).
- Câu "laser nám bao nhiêu tiền một lần" xếp đúng đoạn bảng giá #1: có câu lệnh Instruct 0,65, không câu lệnh
  0,61, gõ không dấu 0,64; đoạn không liên quan 0,29–0,37.
- **Độ trễ 1,5–4,4 s mỗi lần gọi.** Một lần lỗi JSON thoáng qua ở `/api/v1` (thử lại 1 lần là qua).

---

## 2. Quyết định (đã chốt, không đổi khi làm)

| # | Quyết định | Lý do |
|---|---|---|
| D1 | Nhà cung cấp mặc định: Beeknoee, OpenAI-compatible, `https://platform.beeknoee.com/api/v1`, model `qwen/qwen3-embedding-8b`, **1024 chiều**, cosine | user chốt 2026-10-12; client tổng quát nên đổi nhà cung cấp chỉ là đổi cài đặt |
| D2 | **Vector gắn với nội dung, không gắn với đoạn**: bảng mới `kb_embedding(space, text_hash, vector)`; `kb_chunk` thêm `embed_text`, `embed_hash`. Đoạn bị xóa/chia lại (nạp lại, sửa cấu trúc) mà chữ không đổi thì **không phải nhúng lại** | `rechunk` và `add_source` xóa rồi chèn lại đoạn mỗi lần; gắn vector vào dòng đoạn thì mất vector mỗi lần nạp lại |
| D3 | **"Không gian vector" (`space`)** = `sha256("{model}\|{dimensions}\|{document_prefix}")[:16]`. Đổi model, số chiều hay `document_prefix` = không gian mới; vector cũ không bị trộn | không bao giờ so vector của hai model khác nhau |
| D4 | Cột `vector public.vector` **không khai số chiều**, **không có index HNSW** bản này: quét đúng (exact) trên kho vài trăm–vài nghìn đoạn mất vài ms | đổi số chiều không cần migration; HNSW cần số chiều cố định. Khi kho > 20.000 đoạn: thêm index biểu thức theo `space` (ghi ở mục 11) |
| D5 | Văn bản đem nhúng của một đoạn: `embed_text = f"{source_title}\n{path}\n\n{body}"` (tên tài liệu + đường tiêu đề + nội dung). Lúc gửi đi ghép thêm `document_prefix` ở đầu (mặc định rỗng) | đoạn mang ngữ cảnh "bảng giá", "chăm sóc sau laser"…; `path` một mình không có tên tài liệu |
| D6 | Câu hỏi gửi đi kèm `query_prefix`, mặc định câu lệnh kiểu Qwen3: `"Instruct: Given a question from a skin clinic's customer, retrieve the passages of the clinic's documents that answer it\nQuery: "` | đo thật: biên rộng hơn khi có câu lệnh |
| D7 | Gộp hai danh sách bằng **RRF** (k = 60): `score = Σ 1/(60 + hạng)` trên danh sách từ khóa (≤ 40) và vector (≤ 40, độ giống cosine ≥ ngưỡng). Sau đó giữ nguyên các bước cũ: tăng điểm theo dịch vụ, ≤ 3 đoạn/tài liệu, ngân sách ký tự | chuẩn, không cần hiệu chỉnh thang điểm hai bên |
| D8 | **Khi vector tắt/lỗi/quá giờ: kết quả phải y hệt hôm nay** (chỉ từ khóa, điểm BM25, không qua RRF) | không được làm tụt bản đang chạy; test hồi quy bắt buộc |
| D9 | Nhúng câu hỏi chạy **song song** với tìm từ khóa; chờ tối đa `vector_timeout_s` (mặc định 6 s); quá giờ → bỏ nhánh vector cho lượt đó, ghi lý do vào trace | độ trễ Beeknoee 1,5–4,4 s |
| D10 | Cache vector câu hỏi **trong bộ nhớ tiến trình** (LRU 512, khóa `(space, query_prefix, câu hỏi đã strip)`). Không lưu câu hỏi của khách xuống DB | riêng tư; câu lặp lại không tốn 2–4 s |
| D11 | Nhúng đoạn chạy bằng **job nền** `embed` của plugin (lô 16 đoạn), không chặn lúc nạp: nạp xong tìm được ngay bằng từ khóa, vector đến sau vài giây–phút | nạp không phụ thuộc mạng ngoài |
| D12 | Khóa API: lưu **mã hóa** (`ctx.encrypt`) trong `ctx.storage` dưới khóa riêng `embedding_api_key`, **không** nằm trong JSON `settings`. API chỉ trả `has_key: bool` | cùng cách Zalo lưu bí mật |
| D13 | Ngưỡng nhánh vector dùng lại cài đặt có sẵn `search.min_score` ("Điểm tối thiểu", 0–1) = **độ giống cosine tối thiểu**, mặc định **0,35** (lấy từ đo thật: đoạn sai 0,29–0,37, đoạn đúng ≥ 0,6). Hiệu chỉnh bằng script đo (bước 6), không đoán | không thêm ô mới vào UI |
| D14 | Gọi Beeknoee là việc **hạ tầng của plugin**, không phải tool → không vướng luật `allow_internet = false` (luật đó cấm *tool* ra mạng tra cứu). Ghi chú riêng tư: câu hỏi của khách được gửi tới Beeknoee để nhúng; che số điện thoại/CCCD **đang tắt cho demo** (user chốt), phải bật trước khi dùng với bệnh nhân thật | đúng luật đã ghi ở PLAN-step0-core.md §0.2b |
| D15 | Chỉ nhúng đoạn của nguồn `processing = 'ready' AND lifecycle = 'active'` (kể cả nguồn hiệu lực trong tương lai). Nguồn nháp/hết hạn/bị thay không tốn tiền nhúng | tiết kiệm; các nguồn đó không bao giờ được tìm |
| D16 | Không làm ở bản này: rerank, gán nhãn bằng LLM, che dữ liệu nhạy cảm, HNSW, nhiều tiến trình agent | xem mục 11 |

---

## 3. Kiến trúc sau khi làm

```
                 ┌──────────────── kb_search(query) ────────────────┐
                 │                                                   │
   query_terms ──┤  (song song)                                      │
                 │  store.search(terms)          embedder.query(q)   │  ← cache LRU, timeout 6 s
                 │      ≤40 hit BM25            store.vector_search  │  ← cosine ≥ min_score, ≤40
                 │            └────────── fuse (RRF k=60) ──────────┘│  ← vector tắt/lỗi: bỏ qua bước này
                 │              → boost dịch vụ → ≤3/tài liệu → ngân sách ký tự
                 └──────────────── tool_text + tool_detail(trace) ──┘

   job nền "embed" (mỗi 5 s, đánh thức ngay khi có nguồn mới / đổi cài đặt):
     store.missing_vectors(space, 16) → EmbeddingClient.embed(document_prefix + embed_text) → store.save_vectors
     mỗi giờ: store.drop_stale_vectors(space)
```

File mới: `embedding.py` (client HTTP + cấu hình + lỗi), `embedder.py` (job nền, cache câu hỏi, trạng thái),
`fusion.py` (RRF thuần), `migrations/0002_vectors.sql`, `scripts/kb_bench.py` + `scripts/kb_bench_pema.jsonl`
(đo), các test mới. File sửa: `models.py`, `store.py`, `ingest.py`, `search.py`, `plugin.py`, `routes.py`,
`plugin.toml`, `__init__.py` (nếu cần đăng ký job), vài file UI nhỏ.

---

## 4. Dữ liệu: migration `0002_vectors.sql`

Tạo file mới `backend/apps/agent/plugins/knowledge/migrations/0002_vectors.sql` (nguyên văn, chỉ sửa nếu Postgres
báo lỗi cú pháp; nếu sửa thì sửa trước khi nó từng chạy ở đâu):

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

Ghi chú cho người làm:
- `migrate-plugins` tự cấp quyền SELECT/INSERT/UPDATE/DELETE trên `kb_embedding` cho `agent_rt_app` (theo tiền
  tố `kb_`). Không cần sửa lõi.
- Hàm Python **phải** khớp công thức trên: `embed_text_of(title, path, body) -> f"{title}\n{path}\n\n{body}"`,
  `embed_hash = hashlib.sha256(embed_text.encode("utf-8")).hexdigest()`. Có test Postgres so hai bên (bước 2).
- Sau migration, chunk không còn cột `embedded`: cờ "đã có vector" của đoạn được **tính lúc đọc** (LEFT JOIN
  `kb_embedding` theo `space` hiện hành).
- `kb_source.progress.embedded` (jsonb) không còn là nguồn sự thật: route lấy số đoạn đã có vector từ
  `vector_counts(space)`. Vẫn ghi 0 vào jsonb khi lưu nguồn, không đọc nó nữa.

---

## 5. Thiết kế chi tiết từng module

### 5.1 `embedding.py` (mới): cấu hình, client, lỗi

```python
EMBED_BATCH: Final = 16          # texts per call
EMBED_MAX_CHARS: Final = 8000    # one text is cut to this before it is sent (Qwen3 takes ~32k tokens)
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
    def ready(self) -> bool: ...              # base_url, model, api_key all non-empty and not key_broken
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

Hành vi bắt buộc:
- **URL**: `base_url.rstrip("/")`; nếu đã kết thúc bằng `/embeddings` thì dùng nguyên, không thì nối
  `/embeddings`. (`…/api/v1` → `…/api/v1/embeddings`; `…/v1/` → `…/v1/embeddings`.)
- **Request**: `POST`, header `Authorization: Bearer <key>`, `Content-Type: application/json`, body
  `{"model": model, "input": [..texts..], "dimensions": dimensions, "encoding_format": "float"}`. Mỗi text cắt
  còn `EMBED_MAX_CHARS`. `len(texts)` từ 1 đến `EMBED_BATCH` (lớn hơn → `ValueError`, người gọi chia lô).
- **Response**: `data` sắp theo `index`; số vector phải bằng số text, không thì `bad_response`. Mỗi vector:
  dài hơn `dimensions` → cắt `[:dimensions]` (Qwen3 hỗ trợ Matryoshka) rồi chuẩn hóa lại; ngắn hơn →
  `dimensions` ("Dịch vụ trả về N chiều, ít hơn số chiều đã cài (M)."); luôn chuẩn hóa L2 (norm 0 →
  `bad_response`); phần tử phải là số hữu hạn.
- **Lỗi → câu tiếng Việt** (không chép body của nhà cung cấp quá 200 ký tự, không bao giờ chép khóa):
  - `ready` sai → `config` "Chưa cài địa chỉ, model hoặc khóa API cho embedding." (`key_broken` → "Khóa API đã
    lưu không giải mã được (khóa bí mật của agent đã đổi). Nhập lại khóa.")
  - 401/403 → `auth` "Khóa API sai hoặc hết hạn."
  - 404 → `not_found` "Sai địa chỉ hoặc tên model."
  - 400/422 có chữ "dimension" trong body → `dimensions` "Model không nhận số chiều {n}."; 400/422 khác →
    `bad_response`.
  - 429 → `rate_limit` "Dịch vụ embedding đang giới hạn lượt gọi, thử lại sau."
  - 5xx → `server` "Dịch vụ embedding lỗi (HTTP {code})."
  - `httpx.TimeoutException` → `timeout` "Quá {timeout_s:g} giây không trả lời."
  - `httpx.TransportError` khác → `network` "Không kết nối được tới {host}."
  - JSON hỏng / thiếu `data` → `bad_response` "Dịch vụ trả về dữ liệu không đọc được."
- **Mỗi lần gọi mở một `httpx.AsyncClient`** (`async with httpx.AsyncClient(transport=self._transport,
  follow_redirects=False) as http:`). Không giữ client sống lâu: `ctx.on_disable` chỉ nhận hàm đồng bộ nên không
  đóng được client async, và mỗi lần gọi đã mất 1,5–4 s nên chi phí mở kết nối không đáng kể. Plugin Zalo cũng
  mở client trong vòng chạy và đóng ở `finally` (xem `plugins/zalo/bot/channel.py`), cùng tinh thần.
- Log: chỉ `ctx.logger.info("embedded %d texts in %.0f ms", n, ms)` và mã lỗi; không log text, không log key.

### 5.2 `fusion.py` (mới): RRF thuần

```python
RRF_K: Final = 60

def fuse(ranked: Sequence[Sequence[Hit]], k: int = RRF_K) -> list[Hit]:
    """Reciprocal rank fusion: each chunk scores the sum of 1/(k + rank) over the lists it is in (rank from 1).
    The Hit kept for a chunk is its first appearance (keyword list first); its score becomes the RRF score.
    Ties: the order of first appearance."""
```
Không async, không I/O, có test riêng (mục 7).

### 5.3 `text.py`: thêm

```python
def embed_text_of(title: str, path: str, body: str) -> str:
    """What a chunk is embedded as: its document's title, its headings and its text (the SQL of
    migrations/0002_vectors.sql builds the same string for chunks stored before it)."""
    return f"{title}\n{path}\n\n{body}"

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```
**Không dùng lại `content_hash`** của `text.py`: nó `strip()` text trước khi băm, còn SQL của migration 0002
không strip, nên hai bên sẽ lệch. `text_hash` là hàm mới, băm nguyên văn.

### 5.4 `models.py`

- `Chunk`: thêm `embed_text: str = ""`; thêm property `embed_hash` (= `text_hash(embed_text)`, rỗng nếu
  `embed_text` rỗng). Giữ field `embedded: bool = False` nhưng giờ nó được **điền lúc đọc** từ store.
  `shown()` giữ nguyên dạng (UI đọc `embedded`).
- Không đổi `Hit`. Điểm trong `Hit.score`: BM25 (nhánh từ khóa), độ giống cosine 0–1 (nhánh vector), RRF (sau
  gộp).

### 5.5 `ingest.py`

- `make_chunks(source_id, title, pieces, services)`: thêm tham số `title`, điền
  `embed_text=embed_text_of(title, piece.path, piece.text)`. Sửa mọi chỗ gọi (`_add`, `rechunk`, test
  `test_knowledge_db.py`). Trong `rechunk` dùng `source.title` (khi route `split` đổi tên thì dùng tên mới vì
  nó đã nằm trong `new_source`).
- Sau khi thêm/nạp lại nguồn: gọi `self._on_change()` (callback truyền vào `Ingest.__init__`, mặc định không làm
  gì) để plugin đánh thức job nhúng.

### 5.6 `store.py`

Thêm vào `KnowledgeStore` (Protocol) và **cả hai** bản (`InMemoryKnowledgeStore`, `PostgresKnowledgeStore`):

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
    # source_id -> its chunks that have a vector in `space`
async def clear_vectors(self, space: str) -> int: ...
    # deletes every vector of this tenant/agent in `space`; returns rows deleted
async def drop_stale_vectors(self, space: str) -> int: ...
    # deletes vectors of other spaces, and vectors in `space` no chunk refers to any more
```
và đổi chữ ký:
```python
async def chunks(self, source_id: str, q: str, page: int, page_size: int, space: str | None) -> tuple[list[Chunk], int]
    # each Chunk.embedded = it has a vector in `space` (False when space is None)
```

**Postgres** (theo đúng phong cách `text()` + `bindparam` hiện có, mọi câu có `tenant_id = :tenant_id AND agent =
:agent`):
- Vector truyền vào SQL dưới dạng chuỗi `"[0.0123,-0.04,…]"` (`"[" + ",".join(repr(float(x)) for x in v) + "]"`)
  và `CAST(:vector AS public.vector)`. Không thêm thư viện `pgvector` Python.
- `_INSERT_CHUNK`: bỏ `embedded`, thêm `embed_text`, `embed_hash`.
- `_CHUNKS`: `LEFT JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent AND e.space =
  :space AND e.text_hash = c.embed_hash`, chọn `(e.text_hash IS NOT NULL) AS embedded`. `space` None → truyền
  `''` (không khớp gì).
- `_SEARCH` (từ khóa): bỏ `c.embedded` khỏi SELECT; `_chunk(row)` đọc `row.get("embedded", False)` hoặc thêm
  `false AS embedded`. Chọn thêm `c.embed_text`.
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
- `_MISSING_COUNT`: như trên nhưng `SELECT count(*)` (đếm đoạn, không DISTINCT).
- `_SAVE_VECTOR`: `INSERT … (tenant_id, agent, space, text_hash, vector) VALUES (…, CAST(:vector AS
  public.vector)) ON CONFLICT DO NOTHING`, chạy executemany (list dict) trong **một** transaction.
- `_VECTOR_COUNTS`: `SELECT c.source_id, count(*) FROM kb_chunk c JOIN kb_embedding e ON … AND e.space = :space
  AND e.text_hash = c.embed_hash WHERE scope GROUP BY c.source_id`.
- `_CLEAR_VECTORS`: `DELETE FROM agent_rt.kb_embedding WHERE scope AND space = :space`.
- `_DROP_STALE`: `DELETE FROM agent_rt.kb_embedding e WHERE scope AND (e.space <> :space OR NOT EXISTS (SELECT 1
  FROM agent_rt.kb_chunk c WHERE c.tenant_id = e.tenant_id AND c.agent = e.agent AND c.embed_hash =
  e.text_hash))`.
- `rowcount` lấy như các hàm `delete` hiện có.

**In-memory**: `self._vectors: dict[tuple[str, str], tuple[float, ...]]` khóa `(space, text_hash)`. Cosine = tích
vô hướng (vector đã chuẩn hóa) — viết hàm thuần `_cosine(a, b)` dùng `math.fsum`. `vector_search` dùng `in_use()`
y như `search`. Đây là bản dùng cho test và cho script đo.

### 5.7 `embedder.py` (mới): job nền, cache câu hỏi, trạng thái

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
                 clock: Callable[[], datetime] = ..., sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 logger: logging.Logger) -> None: ...
    def wake(self) -> None: ...                          # sets an asyncio.Event
    async def step(self) -> bool: ...                    # one batch; True when it embedded something
    async def run(self) -> None: ...                     # the job: loop of step() with waits; never returns
    async def query_vector(self, question: str, *, timeout_s: float) -> tuple[list[float], str]: ...
        # (vector, space); cache hit returns at once; raises EmbeddingError / TimeoutError
    async def status(self) -> EmbedStatus: ...
```

Luật của `step()`:
1. `config = await self._config()`. Không `ready` → trạng thái `off` (message "Embedding chưa kết nối: đang tìm
   bằng từ khóa." hoặc câu "khóa không giải mã được"), trả False.
2. `items = await store.missing_vectors(config.space, EMBED_BATCH)`; rỗng → trạng thái `ok`, trả False.
3. `vectors = await client.embed(config, [config.document_prefix + text for _, text in items],
   timeout_s=DOCUMENT_TIMEOUT_S)`. Lỗi `transient` → **thử lại ngay 1 lần**; vẫn lỗi → ném lên.
4. `await store.save_vectors(config.space, list(zip(hashes, vectors)))`, trạng thái `working` (còn thiếu) hoặc
   `ok`, `last_ok_at = clock()`, trả True.

Luật của `run()` (vòng không bao giờ thoát, `CancelledError` để lọt ra):
- `step()` trả True → chạy tiếp ngay (vẫn `await asyncio.sleep(0)`).
- trả False → chờ `IDLE_S` (hoặc `NOT_READY_S` khi `off`) **hoặc** tới khi `wake()`, cái nào đến trước.
- `EmbeddingError` transient → trạng thái `error` + message, chờ theo `BACKOFF_S` (tăng dần, về đầu khi thành
  công). Không transient → `error`, chờ `STOP_S` hoặc `wake()`.
- Lỗi khác (bug, DB) → `logger.exception`, trạng thái `error` "Lỗi khi nhúng, xem log agent.", chờ `BACKOFF_S`.
- Mỗi `CLEANUP_EVERY_S`: `drop_stale_vectors(space)` (chỉ khi `ready`).
- Một config đổi (`space` khác lần trước) → reset backoff.

`query_vector`: cache `collections.OrderedDict` khóa `(space, query_prefix, question.strip())`, LRU 512; miss →
`asyncio.wait_for(client.embed(config, [query_prefix + question], timeout_s=timeout_s), timeout_s)`; **không** thử
lại (độ trễ). `config` không `ready` → `EmbeddingError("config", …)`.

`status()`: gộp trạng thái trong bộ nhớ + `missing_count(space)` (khi `ready`) + `model`.

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
    fused: tuple[Hit, ...]               # after RRF; equals candidates when the vector branch was not used
    final: tuple[Hit, ...]
    keyword_ms: float
    vector_ms: float                     # embed + vector SQL, 0 when not used
    vector_note: str | None              # why the vector branch was skipped or failed (Vietnamese), else None
    total_ms: float

    @property
    def vector_used(self) -> bool: return self.vector_note is None
```

`Searcher.search(question, as_of, *, results, char_budget, services, vector: VectorPlan | None = None)`:
1. `named`, `wanted` như cũ.
2. Chạy song song (`asyncio.TaskGroup` hoặc `gather`): `store.search(wanted, as_of, CANDIDATES)` và (nếu
   `vector` không None) `_vector_branch()`:
   `vec, space = await vector.embed(question, vector.timeout_s)` rồi `store.vector_search(space, vec, as_of,
   CANDIDATES, vector.min_similarity)`. Bắt `EmbeddingError` → `vector_note = err.message`; `TimeoutError` →
   `vector_note = f"Nhúng câu hỏi quá {timeout:g} giây: lượt này chỉ tìm bằng từ khóa."`. `vector is None` →
   `vector_note = "Embedding chưa bật: chỉ tìm bằng từ khóa."`.
3. `ranked = fuse([candidates, vector_hits])` nếu `vector_used` **và** `vector_hits` không rỗng; ngược lại
   `ranked = candidates` (giữ điểm BM25 — D8).
   Lưu ý: `vector_used` nhưng không đoạn nào qua ngưỡng → vẫn trả `ranked = candidates` (không RRF), nhưng
   `vector_note` vẫn None (nhánh đã chạy, chỉ là không có ứng viên).
4. Boost dịch vụ → `_spread` → `_packed` như cũ.
5. **Gap**: `plugin._search_tool` vẫn ghi gap khi `final` rỗng (không đổi).

`tool_text`: không đổi format (agent không cần biết điểm). `tool_detail` thêm:
`"keyword_candidates"`, `"vector_candidates"`, `"vector_used"`, `"vector_ms"` (làm tròn), `"vector_skip"`
(`None` hoặc mã ngắn: `"off" | "timeout" | "error"` — không đưa câu tiếng Việt dài vào trace),
`"top_similarity"` (độ giống cao nhất của nhánh vector, 4 số lẻ, 0 nếu không có). Giữ nguyên các khóa cũ
(`doc_ids`, `as_of`, `returned`, …) vì trace đo đang đọc chúng.

`debug_view`: bước `vector` thật (ms, note "N đoạn gần nghĩa, độ giống ≥ {min}" hoặc `vector_note`, `skipped =
not vector_used`, ứng viên với score = độ giống); thêm bước `fused` ("Gộp RRF (k = 60)", skipped khi không gộp)
giữa `vector` và `final`. Đổi `NO_VECTOR` thành câu ở bước 2 trên.

### 5.9 `plugin.py`

- `default_settings(config)`: nhóm `embedding` lấy mặc định từ `user_config` mới (mục 5.11); `search.min_score`
  mặc định `float(config.get("vector_min_similarity", 0.35))`.
- `embedding_config() -> EmbeddingConfig` (async): `settings()["embedding"]` + khóa: `sealed = await
  ctx.storage.get("embedding_api_key")`; có thì `ctx.decrypt(sealed)`; `PluginError` khi giải mã →
  `api_key=""`, `key_broken=True`.
- `save_settings(patch)`: nhóm `embedding` có `api_key`:
  - `""` → `await ctx.storage.delete("embedding_api_key")` (`PluginStorage` có `get`, `put`, `delete`, `list`;
    xem `agent_app/plugins/records.py`).
  - chuỗi khác → `strip()`, dài 8–500 ký tự, rồi `ctx.storage.put("embedding_api_key", ctx.encrypt(key))`.
  - `has_key` trong kết quả = có bản mã hóa trong storage (tính lúc đọc, **không lưu** `has_key` trong JSON).
  - `PluginError` khi `encrypt` (service không có khóa bí mật) → route trả 409 "Agent chưa có khóa bí mật để mã
    hóa (chạy bằng agent serve)."
  - Sau khi lưu nhóm `embedding` → `self.embedder.wake()`.
- Kiểm tra giá trị nhóm `embedding` ở server (trong `routes._checked_settings`): `base_url` rỗng hoặc
  `^https?://\S+$` ≤ 500; `model` 1–200; `dimensions` int 32–4096; `query_prefix`/`document_prefix` ≤ 500.
  Sai → 422 với câu tiếng Việt như các kiểm tra hiện có.
- Dựng: `KnowledgePlugin.__init__(ctx, *, store=None, clock=…, client: EmbeddingClient | None = None)`;
  `self.client = client or EmbeddingClient()` (test chèn transport giả qua `__init__.py`, mục 11b),
  `self.embedder = Embedder(self.store, self.client,
  self.embedding_config, clock=clock, logger=ctx.logger)`, `self.ingest = Ingest(..., on_change=self.embedder.wake)`.
- `register()`: thêm `ctx.register_job("embed", self.embedder.run)`. Không cần `on_disable`: client không sống
  lâu (5.1), job bị lõi hủy khi tắt plugin.
- Job chỉ chạy dưới `agent serve`. Dưới `agent chat` (CLI) không có job: vector có sẵn trong DB vẫn được dùng,
  đoạn mới chỉ tìm bằng từ khóa. Chấp nhận, ghi một dòng trong docstring của `embedder.py`.
- `_search_tool`: dựng `VectorPlan(min_similarity=settings["min_score"], timeout_s=config_timeout,
  embed=self.embedder.query_vector)` **chỉ khi** `(await self.embedding_config()).ready`; không thì `None`.
- `kb_read` không đổi.

### 5.10 `routes.py`

| Route | Sau khi làm |
|---|---|
| `GET /status` | `{"embedding_connected": status.state in ("ok","working"), "embedding_model": status.model, "queue": status.missing, "warnings": _warnings(status)}` |
| `GET /sources` | `summary.embedded_percent` từ `vector_counts(space)`; mỗi `Source` trả về có `embedded` = đếm thật; `warnings` = `_warnings(status)` (chỉ khi có nguồn) |
| `GET /sources/{id}` | `embedded` thật |
| `GET /sources/{id}/chunks` | truyền `space` (None khi chưa `ready`) |
| `GET /settings` | `embedding.has_key` thật; `embedding.chunks_without_vector = status.missing` (0 khi chưa `ready`: khi đó UI đã hiện cảnh báo chưa kết nối) |
| `PATCH /settings` | xử lý `api_key` (5.9), kiểm tra giá trị, đánh thức job |
| `POST /settings/test-embedding` | `probe(config)` → `{"ok": true, "dimensions": probe.dimensions, "normalised": abs(probe.norm - 1) < 0.01, "ms": round(probe.ms), "message": "Kết nối tốt"}`; `EmbeddingError` → `{"ok": false, …, "message": err.message}` (HTTP 200) |
| `POST /settings/reembed` | `cleared = clear_vectors(space)`; `queued = missing_count(space)`; `wake()`; trả `{"queued": queued}`. Chưa `ready` → 409 "Chưa kết nối embedding." |
| `POST /search/debug` | truyền `VectorPlan` như `kb_search` |

`_warnings(status)`: `off` → `["Embedding chưa kết nối: đang tìm bằng từ khóa."]` (hoặc câu khóa hỏng);
`error` → `[f"Embedding đang lỗi: {message} Các đoạn chưa có vector chỉ được tìm bằng từ khóa."]`;
`working` và `missing > 0` → `[f"Đang nhúng: còn {missing} đoạn chưa có vector."]`; `ok` → `[]`.
Xóa hằng `KEYWORD_ONLY` cũ nếu không còn dùng.

### 5.11 `plugin.toml`

Tăng `version = "0.3.0"`. Thêm `user_config` (kiểu như các khóa hiện có):

| Khóa | Kiểu | Mặc định | Mô tả (tiếng Anh, như file) |
|---|---|---|---|
| `embedding_base_url` | string | `"https://platform.beeknoee.com/api/v1"` | OpenAI-compatible base URL of the embedding service |
| `embedding_model` | string | `"qwen/qwen3-embedding-8b"` | |
| `embedding_dimensions` | integer | `1024` | |
| `embedding_query_prefix` | string | câu Instruct ở D6 (`\n` trong TOML: dùng chuỗi `"…\nQuery: "`) | Put before a question when it is embedded |
| `embedding_document_prefix` | string | `""` | Put before a chunk when it is embedded |
| `vector_min_similarity` | number | `0.35` | Least cosine similarity a vector candidate needs |
| `vector_timeout_s` | number | `6.0` | Seconds a search waits for the question's vector |

`user_config` nhận các kiểu `string`, `number`, `integer`, `boolean` (`agent_app/plugins/manifest.py`). Đọc
bằng `float(ctx.config.get(...))`/`int(...)` như `default_settings` hiện làm.

### 5.12 UI (`plugins/knowledge/ui/src`), nhỏ

1. `settings/settings-logic.ts` `reembedWarning`: đổi câu thành "Mọi đoạn của kho sẽ được nhúng lại bằng
   {model}. Việc chạy nền và tốn phí gọi embedding; trong lúc đó các đoạn chưa có vector mới chỉ được tìm bằng
   từ khóa." (thiết kế D2/D3: không còn "dùng vector cũ").
2. `settings/search-section.tsx`: ô "Điểm tối thiểu" đổi hint thành "Độ giống tối thiểu (0 đến 1) của kết quả tìm
   theo nghĩa; mặc định 0,35".
3. `try/try-logic.ts`: `SCORE_LABEL.vector` từ "khoảng cách" → "độ giống" (server trả độ giống, cao là tốt).
4. Sửa test tương ứng (`settings-logic.test.ts`, test của try-logic nếu có), chạy
   `pnpm exec tsc --noEmit -p .` và `pnpm exec vitest run` trong `plugins/knowledge/ui`.
5. Ghi một mục "Pending" vào `.claude/skills/pema-web-design/web-design-changes.md`:
   `### 2026-10-1x · change · Kho tri thức: embedding thật (Cài đặt, Thử tìm, cảnh báo)`, liệt kê 3 câu đã đổi,
   các cảnh báo mới ở dải trên bảng Nguồn, bước "Gộp RRF" ở Thử tìm. "Web canvas target: none (no canvas frame
   for the agent pages)".
6. Mock của web (`pema-agent/frontend/mock/knowledge/*`): **không bắt buộc**. Nếu sửa thì chỉ để `dev:mock` trả
   bước `fused`; không đụng `src/**` của frontend.

---

## 6. Thứ tự làm (mỗi bước một commit; commit message tiếng Anh kiểu `feat(agent): …`, KHÔNG attribution)

### Bước 1: client embedding + RRF (không đụng DB, không đụng hành vi)
- Tạo `embedding.py`, `fusion.py`, thêm `embed_text_of`/`text_hash` vào `text.py`.
- Test mới `tests/knowledge/test_embedding.py`, `tests/knowledge/test_fusion.py` (mục 7).
- Kiểm: `uv run pytest apps/agent/tests/knowledge/test_embedding.py apps/agent/tests/knowledge/test_fusion.py -q`;
  `uv run ruff check` + `ruff format --check` + `uv run pyright` trên các file đã sửa.
- Commit: `feat(agent): knowledge embedding client (OpenAI-compatible, cut and normalise to the set dimensions, errors a person can read) and reciprocal rank fusion`

### Bước 2: migration + store
- `migrations/0002_vectors.sql`, sửa `models.py`, `store.py` (cả hai bản), `ingest.py` (`make_chunks` có `title`,
  `on_change`).
- Sửa test cũ gọi `make_chunks` / `chunks(...)`.
- Test mới trong `test_knowledge_db.py` (Postgres) và test in-memory (mục 7).
- Kiểm: test knowledge (không db) + test db với DB thử (lệnh ở mục 0.5) + ruff/pyright.
- Commit: `feat(agent): knowledge vectors keyed by text and vector space (kb_embedding), cosine search in force on the day asked`

### Bước 3: embedder (job, cache, trạng thái) + nối vào plugin/routes/search
- `embedder.py`; sửa `search.py`, `plugin.py`, `routes.py`, `plugin.toml`.
- Test: `test_embedder.py` (mới), cập nhật `test_knowledge_plugin.py` (mục 7).
- Kiểm: `uv run pytest apps/agent/tests/knowledge -q` (+ db) và `apps/agent/tests/test_plugin_runtime.py` (plugin
  load), ruff/pyright.
- Commit: `feat(agent): knowledge store searches by meaning too: a background job embeds chunks, kb_search fuses keyword and vector candidates (RRF), falls back to keywords when the service is off, slow or failing`

### Bước 4: UI + log thay đổi giao diện
- Mục 5.12. Kiểm tsc + vitest. Commit: `feat(agent): knowledge pages read real embedding status; wording for re-embedding, similarity and the fused stage`

### Bước 5: script đo + số đo
- `backend/apps/agent/scripts/kb_bench.py` và `backend/apps/agent/scripts/kb_bench_pema.jsonl` (mục 8).
- Chạy 3 chế độ, dán bảng kết quả vào mục 10 của file này; hiệu chỉnh `vector_min_similarity` **chỉ** theo bộ
  này (ghi giá trị đã thử và kết quả).
- Commit: `test(agent): knowledge retrieval bench (keyword, vector, hybrid) on the Pema demo corpus, with results`

### Bước 6: chạy thật trong Docker (cần user cho phép lệnh Docker)
- Nhờ user chạy (hoặc xin phép rồi chạy) ở thư mục gốc repo: `docker compose up -d --build`.
- Kiểm `docker compose logs agent-migrate` có dòng `knowledge: ran 0002_vectors.sql` và
  `granted … on agent_rt.kb_embedding`.
- User nhập khóa ở Kho tri thức → Cài đặt → Embedding → "Kiểm tra kết nối" phải ra "Kết nối tốt · 1024 chiều ·
  đã chuẩn hóa · … ms".
- Đợi dải cảnh báo hết "Đang nhúng…"; kiểm SQL đọc:
  `docker exec cnbphongkham-postgres-1 psql -U postgres -d pema -tAc "select space, count(*) from agent_rt.kb_embedding group by 1"`
  → một `space`, số dòng ≈ số đoạn (trừ đoạn trùng chữ).
- "Thử tìm" với 3 câu ở bộ B (mục 8): bước "Ứng viên vector" có kết quả, bước "Gộp RRF" hiện.
- Cập nhật `docs/HANDOFF-agent-v2.md` (một mục ngắn: đã làm gì, số đo, cách bật) và §19.4 của
  `PLAN-knowledge-plugin.md` (dòng trạng thái). Commit docs.

---

## 7. Test bắt buộc (tên gợi ý; viết theo phong cách test hiện có: tên câu tiếng Anh mô tả hành vi)

### `test_embedding.py` (httpx.MockTransport, như `tests/zalo/test_bot_client.py`)
- `test_it_posts_the_model_the_texts_and_the_dimensions_with_the_key` — kiểm URL `…/api/v1/embeddings`, header
  Bearer, body.
- `test_the_endpoint_is_joined_once` — `…/v1`, `…/v1/`, `…/v1/embeddings` → cùng một URL.
- `test_vectors_come_back_in_input_order` — response `data` đảo thứ tự `index`.
- `test_a_longer_vector_is_cut_to_the_set_dimensions_and_normalised` — 8 chiều → 4, norm 1.
- `test_a_shorter_vector_is_an_error_about_dimensions`.
- `test_errors_become_sentences` — tham số hóa 401, 403, 404, 429, 500, 400 "dimensions", JSON hỏng, timeout,
  ConnectError → đúng `kind`, `transient`, message tiếng Việt; **message không chứa khóa**.
- `test_a_config_without_a_key_is_not_ready`, `test_the_space_changes_with_model_dimensions_and_document_prefix`
  (không đổi theo `query_prefix`, `base_url`, `api_key`).
- `test_the_key_is_not_in_the_configs_repr`.

### `test_fusion.py`
- Hai danh sách có phần chung → phần chung lên đầu; điểm đúng công thức (so số với tay: hạng 1 cả hai = 2/61).
- Một danh sách rỗng → thứ tự của danh sách kia giữ nguyên.
- Hòa điểm → thứ tự xuất hiện đầu tiên.

### In-memory + plugin (`test_knowledge_plugin.py`, `test_embedder.py`)
Dùng **embedding giả có tính quyết định** (fake client hoặc `httpx.MockTransport`): ví dụ bảng "khái niệm" — mỗi
text có chữ "nám"/"sạm"/"đốm nâu" → trục 0; "giá"/"tiền"/"bao nhiêu" → trục 1; "hủy"/"lỡ hẹn" → trục 2; … rồi
chuẩn hóa. Như vậy "da bị sạm" (không có chữ "nám") gần đoạn nám theo vector nhưng **không** khớp từ khóa.
- `test_the_job_embeds_every_chunk_once` — `step()` tới khi False; `missing_count == 0`; gọi lại không gọi API.
- `test_re_cutting_a_source_with_the_same_text_needs_no_new_vectors` — nạp lại → API không bị gọi thêm.
- `test_changing_the_model_makes_every_chunk_missing_again` — đổi `model` → `chunks_without_vector` = tổng đoạn;
  vector cũ bị `drop_stale_vectors` xóa.
- `test_a_paraphrase_is_found_by_meaning` — câu chỉ vector bắt được → có trong `final`, `tool_detail
  ["vector_used"] is True`.
- `test_without_embedding_the_results_are_the_keyword_results` — **hồi quy D8**: cùng câu, `vector=None` →
  `final` giống hệt trước khi làm (so `[(h.chunk.id, h.score)]` với kết quả của nhánh từ khóa).
- `test_a_slow_embedding_falls_back_to_keywords` — fake chờ lâu hơn timeout (dùng timeout 0.05 s trong test) →
  `vector_note` có "quá", `final` = kết quả từ khóa.
- `test_the_query_vector_is_cached` — hai lần cùng câu → API 1 lần.
- `test_the_api_key_is_stored_sealed_and_never_sent_back` — PATCH `api_key` → GET settings `has_key` True,
  JSON trả về không chứa khóa, giá trị trong storage khác khóa (runtime dựng với
  `env={"AGENT_SECRET_ENCRYPTION_KEY": KEY}` như `tests/zalo/test_accounts.py`).
- `test_an_empty_key_removes_it`.
- `test_test_embedding_reports_dimensions_and_norm` và `…_reports_the_error_sentence`.
- `test_reembed_clears_the_space_and_counts_the_queue`.
- `test_status_warns_while_off_working_and_failing`.
- Sửa test cũ có `embedded` hay `make_chunks` cho khớp.

### Postgres (`test_knowledge_db.py`, `pytestmark = pytest.mark.db`)
- Fixture sẵn có chạy alembic + `migrate_plugins` → giờ chạy cả `0002`.
- `test_vectors_are_found_by_cosine_in_force_on_the_day_asked` — 2 nguồn (cũ/mới như test hiện có), vector giả
  4 chiều, `vector_search` trả đúng nguồn theo ngày, `score` ≈ cosine, tenant khác không thấy.
- `test_missing_vectors_lists_each_text_once_and_save_is_idempotent`.
- `test_chunks_report_whether_they_have_a_vector`.
- `test_drop_stale_vectors_keeps_only_the_current_space_and_used_texts`.
- `test_the_migration_backfills_the_same_embed_text_as_python` — chèn `kb_source` + `kb_chunk` bằng SQL thô
  **trước** khi chạy 0002 là khó với fixture hiện tại → thay bằng: chạy câu `UPDATE … SET embed_text = …` của
  0002 trên một dòng mới chèn rồi so `embed_hash` với `text_hash(embed_text_of(...))` của Python.

Chạy hết test knowledge (cả db) trước mỗi commit của bước 2–3.

---

## 8. Đo: `scripts/kb_bench.py`

Mục đích: biết vector mua được bao nhiêu, và hiệu chỉnh ngưỡng. Chạy ngoài Docker, dùng `InMemoryKnowledgeStore`
+ `EmbeddingClient` thật.

```
cd pema-agent/backend/apps/agent
uv run python scripts/kb_bench.py \
  --docs "E:\Desktop\data test\AgentRAG_Pema_Demo\01_NAP_EMBEDDING" \
  --questions scripts/kb_bench_pema.jsonl --as-of 2026-10-12 \
  --modes keyword,vector,hybrid [--min-similarity 0.35] [--json out.json]
```

- Khóa đọc từ biến môi trường `BEEKNOEE_API_KEY` (đã có trong biến người dùng Windows của user; **không in, không
  ghi file**). Không có khóa → chỉ chạy `keyword`, in một dòng báo.
- Script tự thêm thư mục `apps/agent` vào `sys.path` để import `plugins.knowledge`.
- Nạp tài liệu qua `Ingest.preview/confirm` y như `scratchpad/try_pema.py` cũ (đọc YAML, `lifecycle` từ meta).
- Nhúng hết đoạn bằng `Embedder.step()` lặp tới khi False (cùng code với job thật).
- Mỗi câu × mỗi chế độ: lấy `final` (results 6, char_budget 6000), so mã tài liệu với `expect` (khớp **bất kỳ**
  mã trong danh sách). In bảng: chế độ, top1, top3, top6, MRR, độ trễ trung vị; in từng câu trượt.
- Chế độ `vector` = chỉ nhánh vector (bỏ từ khóa) để biết riêng nó.
- Tùy chọn `--sweep 0.25,0.30,0.35,0.40,0.45` cho ngưỡng: in bảng hybrid theo từng ngưỡng.

`scripts/kb_bench_pema.jsonl` (mỗi dòng `{"q": …, "expect": [mã…], "set": "A"|"B"}`), nội dung **nguyên văn**:

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

Bộ A = câu dùng từ giống tài liệu (từ khóa đã tốt: top3 14/15). Bộ B = câu nói khác chữ (chỗ vector phải giúp).
Người làm **được** sửa `expect` của một câu bộ B nếu đọc tài liệu thấy plan ghi sai mã (ghi lý do vào mục 12),
**không** được bỏ câu khó.

---

## 9. Tiêu chí xong (Definition of Done)

1. Mọi test mục 7 qua, gồm test Postgres trên DB thử; ruff, ruff format, pyright sạch trên file đã sửa; tsc +
   vitest của `plugins/knowledge/ui` qua.
2. **Không hồi quy**: chế độ hybrid trên bộ A ≥ chế độ keyword trên bộ A ở top3 (hiện 14/15) và top6.
3. **Có lợi**: hybrid trên bộ B hơn keyword trên bộ B ở top3 (ghi số cụ thể). Nếu không hơn: không "chỉnh cho
   đẹp", báo lại số và giả thuyết trong mục 12.
4. Vector tắt (không khóa) → trang Kho tri thức, `kb_search`, trace chạy y như trước; dải cảnh báo nói "chưa kết
   nối".
5. Khóa sai → "Kiểm tra kết nối" hiện "Khóa API sai hoặc hết hạn."; `kb_search` vẫn trả lời bằng từ khóa trong
   ≤ 1 lượt chờ timeout; trace có `vector_skip = "error"`.
6. Trong Docker: `kb_embedding` có vector cho mọi đoạn của nguồn active; trace của một lượt Zalo thật có
   `vector_used: true`.
7. Không có khóa, câu hỏi khách, nội dung tài liệu trong log agent (`docker compose logs agent | grep -i "sk-"`
   rỗng).
8. Docs: HANDOFF + §19.4 cập nhật; mục 10 của file này có bảng số đo.

---

## 10. Kết quả đo (người làm điền ở bước 5)

| Chế độ | Bộ | top1 | top3 | top6 | MRR | trễ trung vị | ngưỡng |
|---|---|---|---|---|---|---|---|
| keyword | A | | | | | | – |
| keyword | B | | | | | | – |
| vector | A | | | | | | |
| vector | B | | | | | | |
| hybrid | A | | | | | | |
| hybrid | B | | | | | | |

---

## 11. Rủi ro và việc để sau

| Rủi ro / việc | Xử lý bây giờ | Sau |
|---|---|---|
| Beeknoee chậm (1,5–4,4 s) | chạy song song từ khóa, timeout 6 s, cache câu hỏi | đo trễ thật từ trace; cân nhắc model nhỏ hơn nếu p50 > 3 s |
| Beeknoee sập | rơi về từ khóa, cảnh báo trên trang, job thử lại có backoff | – |
| Câu hỏi khách gửi ra ngoài | ghi rõ D14; demo chấp nhận | bật che SĐT/CCCD/email trước khi nhúng câu hỏi trước khi dùng với bệnh nhân thật |
| Kho lớn | quét đúng | > 20.000 đoạn: index HNSW theo biểu thức `(vector::public.vector(1024))` lọc `WHERE space = '…'` (partial index theo space đang dùng), hoặc cột số chiều cố định |
| Nhiều tiến trình agent | không hỗ trợ (compose chạy 1) | advisory lock `pg_try_advisory_lock` quanh `step()` |
| Rerank | không làm | bước sau: LLM listwise qua `ctx.model` (cần lõi) |
| So model (Gemini, BGE-M3) | client tổng quát, đổi cài đặt là đổi space | chạy `kb_bench.py` với từng model |
| Gán nhãn/ngữ cảnh bằng LLM | không làm | sau rerank |

---

## 11b. Mã mẫu cho test (chép rồi chỉnh, không bắt buộc y hệt)

### Chèn HTTP giả vào plugin: theo đúng mẫu của Zalo

Zalo nhận transport giả qua một khóa config **không có trong `plugin.toml`** (`plugins/zalo/__init__.py`:
`ctx.config.get("bot_transport")`; test: `host.enable("zalo", {..., "bot_transport": fake.transport})` rồi
`build_runtime(..., plugins=host)`, xem `tests/zalo/test_bot_channel.py::_runtime`). Knowledge làm y vậy:

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

def _runtime(tmp_path: Path, transport: httpx.MockTransport | None = None) -> Runtime:
    folder = ...  # agent.toml như _runtime hiện có
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("knowledge", {} if transport is None else {"embedding_transport": transport})
    return build_runtime(load_profile(folder), fake=True, env=env, db=None, plugins=host)
```

Chạy job nhúng trong test **qua đường công khai**, không với vào đối tượng plugin: lấy job lõi đã đăng ký rồi
chạy nó vài nhịp.

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

Muốn job không chờ `IDLE_S = 5 s` giữa các nhịp trong test: các route lưu cài đặt / nạp nguồn gọi `wake()` nên
nó chạy ngay; nếu vẫn chậm, cho `Embedder` nhận `idle_s` từ `ctx.config.get("embedding_idle_s")` (khóa test, không
khai trong `plugin.toml`, cùng kiểu `embedding_transport`). Test đơn vị của chính `Embedder` (`test_embedder.py`)
thì dựng `Embedder(InMemoryKnowledgeStore(), EmbeddingClient(transport=…), config=…)` trực tiếp và gọi `step()`.

### Embedding giả có tính quyết định

```python
CONCEPTS: Final = (
    ("nam", "sam", "dom nau", "hori"),          # sắc tố
    ("gia", "tien", "bao nhieu", "phi"),        # giá
    ("huy", "lo hen", "doi lich"),              # hủy/đổi lịch
    ("bao luu", "tam dung"),                    # bảo lưu
    ("the", "chuyen khoan", "hoa don"),         # thanh toán
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

Cài đặt dùng trong test: `dimensions = 6` (5 khái niệm + 1 hằng), `base_url = "https://embed.test/v1"`, khóa
`"sk-test-synthetic"`. Lưu ý `fold("năm")` cũng ra `nam`: viết tài liệu thử tránh chữ "năm".

Đếm `calls` để kiểm "không gọi lại API" (cache, nạp lại cùng chữ). Giả chậm cho test timeout: một transport
`async def` với `await asyncio.sleep(1)` và `timeout_s = 0.05`.

---

## 11c. Lời giao việc (dán nguyên văn cho agent làm)

```
Bạn là kỹ sư làm plugin `knowledge` của repo này (nhánh feat/knowledge-ui hoặc nhánh mới tách từ đó, tên
feat/knowledge-embedding). Làm đúng plan pema-agent/docs/PLAN-knowledge-embedding.md.

1. Đọc hết mục 0, 1, 2, 3 của plan trước khi sửa. Tuân thủ tuyệt đối mục 0 (không ghi tên AI vào commit, không ghi
   khóa API vào file, không git stash, không push, không chạy docker compose up/build/down khi chưa được phép,
   test theo phần đã sửa, test DB chỉ trỏ agent_activity_test).
2. Làm lần lượt Bước 1 → 6 ở mục 6. Mỗi bước: code, test mục 7 của bước đó, ruff + ruff format + pyright trên file
   đã sửa, rồi một commit với message như plan gợi ý (tiếng Anh, không attribution). Không gộp bước.
3. Không đổi quyết định ở mục 2. Gặp chỗ plan sai/thiếu: dừng bước đó, ghi vào mục 12 của plan (ngày, bước, vấn
   đề, đề xuất) và báo lại, không tự sáng tạo kiến trúc khác.
4. Bước 5: chạy scripts/kb_bench.py, điền bảng mục 10. Khóa lấy từ biến môi trường BEEKNOEE_API_KEY, không in
   ra. Không sửa câu hỏi để số đẹp hơn.
5. Cuối mỗi bước báo ngắn: đã làm gì, test nào chạy và kết quả, còn gì dở.
```

---

## 12. Câu hỏi / ghi chú của người làm

(Ghi ở đây khi plan sai, thiếu, hay khi phải chọn khác plan. Mỗi mục: ngày, bước, vấn đề, đã làm gì.)
