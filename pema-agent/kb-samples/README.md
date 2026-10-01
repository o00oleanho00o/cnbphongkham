# kb-samples

FICTIONAL dermatology documents (Vietnamese, markdown) to demo and test the knowledge base of the CSKH agent.

| File | Content |
|---|---|
| `cham-soc-sau-laser.md` | after-laser skin care: first 24 hours, first week, when to call the clinic |
| `thuoc-boi-thuong-gap.md` | generic topical products and the rule "prescription items only as the doctor says" |
| `khi-nao-can-kham-lai.md` | red-flag signs (bleeding, pus, fever, breathing trouble...) and routine follow-up |

Every file starts with the banner **"NỘI DUNG GIẢ LẬP, CẦN BÁC SĨ DUYỆT"**: the text is invented, contains no
real protocol, drug name, dose or patient data. Real content is uploaded by the clinic doctor through the admin
screen, who also signs it off (`approved_by_clinical_owner`). A `patient_channel` agent cites a document ONLY
after that sign-off, so after loading these samples a demo needs the approval step too.

## Load them (API)

```text
POST /api/v1/admin/kb/sources/file      (multipart: file=<one of the .md>, name=<optional>)
PATCH /api/v1/admin/kb/sources/{id}/approval   {"approved": true}     (role doctor or owner)
PUT   /api/v1/admin/kb/agents/{agent_id}/sources   {"ids": ["<source id>"]}
POST  /api/v1/admin/kb/search           {"query": "sau laser cần tránh gì", "agent_id": "...", "limit": 5}
```

The ingest worker (`python -m pema.workers.kb_ingest_worker`) turns a `cho_xu_ly` source into chunks and
vectors within a few seconds.

## Hybrid search and the embedding model

Search is Postgres full-text (keyword, diacritics folded) fused by RRF with pgvector (meaning) when an
embedding endpoint is configured. Without one it still works on keywords alone, so everything above runs on a
machine with no GPU. To use the real model (`bge-m3`, 1024 dimensions) through Ollama:

```bash
ollama pull bge-m3                       # once, on the machine that runs Ollama
# environment of the worker AND of the API process (names are prefixed PEMA_EMBEDDING_):
PEMA_EMBEDDING_BASE_URL=http://localhost:11434/v1     # OpenAI-compatible root of Ollama (or llama-server)
PEMA_EMBEDDING_MODEL=bge-m3
# PEMA_EMBEDDING_ENABLED=false           # keyword-only mode
```

The URL must be a machine inside the clinic network (loopback, private range, Tailscale `100.64.0.0/10`, a
single-label host such as `ollama`, `*.ts.net`, `*.local`): a public host is refused unless
`PEMA_EMBEDDING_ALLOW_REMOTE=true`. Check the endpoint before relying on it:

```bash
curl -s http://localhost:11434/v1/embeddings -H 'content-type: application/json' \
  -d '{"model":"bge-m3","input":["chăm sóc da sau laser"]}' | python -c "import sys,json; print(len(json.load(sys.stdin)['data'][0]['embedding']))"   # must print 1024
```

Sources processed while the endpoint was down are stored without vectors (found by keyword only); press
"reindex" on them once it is back.

The tests of the hybrid search use fake embedding clients (`tests/knowledge/test_kb_search_hybrid.py`), so they
need no Ollama. The distance cut-off of the vector side (`KHOANG_CACH_VECTOR_TOI_DA` in
`pema/knowledge/kb_search.py`) is an estimate: calibrate it on these samples with the real model before the
pilot.
