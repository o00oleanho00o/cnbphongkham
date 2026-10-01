# HANDOFF — Clinic AI agent backend (Pema / cnbphongkham)

Language of the user: Vietnamese. Reply in Vietnamese.
Status: **design discussion only. No code written, no files in any repo changed** (only this file).

## Goal

Build a Python FastAPI backend + AI agent service to plug into the existing clinic project at `E:\Desktop\cnbphongkham` (Pema Digital Clinic). That project becomes **one unified app: CRM + agent dashboard** for staff, with **Zalo** as the customer-facing channel for CSKH (customer care).

Client requirements (from the recorded conversation between clinic owner "A" and tech advisor "B"):

1. Intake questions (age, location, duration, itching, prior treatment, prior drugs, effect).
2. Post-treatment follow-up at fixed milestones (e.g. 2 days after laser: pain/itch, medication used correctly, running out).
3. Handle patient reports ("red, itchy" -> ask for a photo; later: personalised replies from a reaction-photo library, escalate to doctor; bot "learns").
4. Booking and reminders (appointments, re-visit, birthdays, holidays).
5. Patient data and analytics (phone, before/after photos, meds; auto before/after collage after 3-4 months).
6. Vision: replicate to many private clinics, then Vietnam, then abroad. Priority: customer care first; advanced AI is "still far". A fears data leaks (declined a vendor's chatbot trial for that reason).

## Current Progress (conclusions only, nothing implemented)

### `E:\500-AI-Agents-Projects` (open-source catalog repo)

- 21 sample agents. Convention: exactly 5 files per agent (README.md, agent.py, requirements.txt, .env.example, metadata.yaml). CONTRIBUTION.md, DCO sign-off CI.
- `13-customer-support-agent`: LangGraph + FAISS RAG demo. English escalation keywords, `route_after_escalation_check` is a no-op, pins old `langgraph==0.2.0`, no `.env.example`.
- `21-pii-sanitization-agent`: calls the external TrustBoost API (itself a data exit) and strips phone numbers, which we need as an identifier.
- No existing agent covers the requirement.

### `E:\Desktop\cnbphongkham` (read-only exploration)

- A **localStorage prototype**: vanilla HTML/JS, key `pema-demo-v2`, static `python -m http.server 4173`. Plus the KMP mobile app `pema-kmp/`, plus `prototype/finance_server.py` (stdlib `http.server` + SQLite, port 4174; the `X-Pema-Role` header is only a simulation). **There is no FastAPI anywhere** (grep confirmed).
- `prototype/shared/crm-automation.js` and `crm-data.js` already hold the follow-up rule engine: d1/d3/d7 after laser, due, overdue, no_show, abandoned (45 days), dormant90/180, birthday (manual, "không gửi tự động"), `marketingOptOut`, channels `Gọi điện | Zalo | SMS | Ghi chú nội bộ`, entities `crmTasks / crmActivities / crmAutomationRules`. Demo clock fixed at 2026-09-20.
- `docs/ARCH-PB01.md` already targets a pilot "modular monolith": API gateway, Identity/RBAC, Postgres, job queue, Zalo/SMS adapters, AI orchestration with a doctor-approval gate, plus an authorization matrix.
- `AGENT.md` rules to respect: synthetic data only in the repo; AI drafts carry sources and are doctor-reviewed; no autonomous diagnosis, efficacy score or protocol change; docs flow SCOPE -> SPEC -> MODULEMAP -> ARCH; run the listed test suites; the role switch is not RBAC.

### External projects evaluated (README level only, no code read)

| Project | Verdict |
|---|---|
| Hermes Agent (Nous, Python, MIT) | Personal assistant, cron + chat channels, no Zalo, no RAG index, "not secured by default for multi-user". Not a core. |
| OpenClaw (Node/TS, MIT) | Personal gateway, 20+ channels, Zalo plugin `@openclaw/zalo`. Heavy 2026 security history (CVE-2026-25253, ClawHavoc malicious skills, exposed instances). Not a core. |
| `vuhai2002/zalo-agent` (TS/Node, SQLite FTS5, MIT, 6 stars) | Zalo-specific, KB + cron + MCP client (default-deny), good security design. Personal-account mode uses unofficial `zca-js` (ban risk). Bot API mode has only 7/15 tools, text only. Keyword-only search, single author. Usable as demo or channel layer, not as core. |
| `BuilderIO/agent-native` (TS/React/Nitro) | Adopted only the principle "agent works through the same action layer as the UI", not the stack. |

### Machine (this PC)

RTX 3060 12 GB, i5-12400F (6c/12t), 32 GB RAM, C: only 26 GB free, E: 1.1 TB free. User will run **Linux** and run the LLM on this PC. Linux mode (dual-boot/native vs WSL2) is NOT decided yet.

## Decisions (confirmed by user unless marked "proposed")

- Python **FastAPI** as BE and AI service. `cnbphongkham` = CRM + agent dashboard in one app. Zalo = CSKH channel to customers. (confirmed)
- Language decision (confirmed by user): **Python (latest stable, 3.14 / 3.12+) for BE and AI service; FE later = Next.js (TypeScript)**. Rust/Julia/Mojo/C++ rejected for BE/orchestration (no ecosystem benefit; time is spent in GPU inference, which is already C++ via llama.cpp). A TypeScript BE was considered and dropped (my earlier "shared types with the dashboard" argument was wrong: the current dashboard is vanilla JS).
- Because the FE will be Next.js: keep ALL business logic and permissions in the FastAPI `actions/` layer; Next.js is UI only (plus thin session-cookie/BFF handling if needed), never a second source of business rules. Generate TypeScript types/client from FastAPI's OpenAPI schema so FE and BE share contracts.
- Concurrency (confirmed): BE uses **1 CPU core** (1 API process + scheduler); remaining CPU/GPU is reserved for the AI side. Multi-core comes from separate processes, not threads; free-threaded Python only as an optional experiment for `ai-worker`.
- Inference engine: start with Ollama; move to `llama-server` (llama.cpp) if finer control is needed (parallel slots, JSON-schema/grammar-constrained output, KV-cache options, bge-m3 GGUF embeddings). `ai-worker` stays thin Python and talks to it over an OpenAI-compatible API.
- Note: the existing prototype dashboard stays vanilla JS until the Next.js FE exists; during the transition it should call the FastAPI API instead of localStorage.
- **PIVOT v2 (confirmed 2026-10-01, supersedes "channel layer only"):** build a **full Python derivative of `vuhai2002/zalo-agent`** — channels (Bot API + personal via Node bridge zca-js), agent loop, persona, all 15 tools (incl. images/video/documents/web), conversation memory (`save_memory`, rolling summary), knowledge base, scheduler, MCP client, token accounting — translated module-by-module with `# ported from:` headers and the original tests ported to pytest, PLUS clinic CRM, PLUS one Next.js FE for both CRM and AI configuration. Clinic-safety rules are applied via **policy profiles** (`staff_assistant` = original behaviour; `patient_channel` = draft→approval, red flags before LLM, PII masking, no `save_memory` from patient text, media/web tools off, identity verification), never by deleting ported features. Because this is a derivative work, `pema-agent/THIRD_PARTY_NOTICES.md` with the zalo-agent (and zca-js) MIT notice is required; user was told plainly. Plan v2 = `pema-agent/docs/PLAN-AI01.md`; package A must produce `PORT-MAP.md` (every `src/` TS file → Python module → owning package) and clone zalo-agent to a fixed path outside the repo.
- Personal-account mode (`zca-js`, unofficial) is KEPT per user decision, as an optional adapter behind the same `ChannelPort`: feature-flagged and off by default, use a secondary Zalo account (never the clinic's main one), daily proactive cap, kill switch, encrypted credentials, risk documented (account suspension / ToS). Official Bot API / OA remain the default path.
- Execution mode (confirmed): write the plan first, then fan out to **subagents (Sonnet 5.5, high effort)** working in separate worktrees; the user wants to be told BEFORE any subagent is started. Plan = `pema-agent/docs/PLAN-AI01.md` (goal, scope, architecture, repo layout, shared contracts, work packages A–G, conventions). **All new code/docs/infra live under one new folder `pema-agent/`** so the old prototype, KMP app and finance server are untouched. Subagent definition lives in the project at `.claude/agents/pema-builder.md` (model sonnet, effort high); note it is only loaded when a session starts with cwd = cnbphongkham. User asked to run ALL packages (A → B/C/D/E in parallel → F → G) in one go after a single "go", not stage by stage. **Next.js FE is now in scope** (package E). zalo-agent clone (depth 1) currently at the session scratchpad (`.../scratchpad/zalo-agent`); package A re-clones it to a fixed path outside the repo. (v1 said "no license file"; v2 is a derivative, so the notice file IS required — see PIVOT v2.)
- Scope for now (confirmed): **CSKH only, text only toward patients**. No before/after collage. v2: image/video/document/web tools ARE ported (staff_assistant may use them) but are OFF in the `patient_channel` profile; a patient-sent image is flagged in the Inbox and handed to staff, not analysed.
- **Separate the AI service from the BE** (LLM runs on this PC). Share one Postgres *server* but **not tables**: schemas `clinic.*` (BE-owned) and `ai.*` (AI-owned), separate DB roles; the AI role has no grant on `clinic.*`. (proposed; user said "tách riêng nhưng chung DB" and was told to share the server, not the tables)
- AI reaches patient data only through BE **actions** (HTTP/MCP, service token) that return minimal, PII-masked context. AI writes drafts via action `review_item.create`; doctor/CSKH approves in the dashboard; BE sends. PII is masked before any LLM call; embeddings are computed locally.
- BE layout (v2): one FastAPI app `pema-agent/backend/apps/api/pema/` with ported packages (`channels/`, `middleware/`, `agent/`, `conversation/`, `knowledge/`, `scheduler/`, `mcp/`, `documents/ images/ video/`, `config/`) plus new `clinic/` (domain, actions, crm_rules, rbac, audit) and `policy/` (profiles, redflags, pii). Processes: `api` (1 CPU core), `worker` (agent turns + scheduler), optional Node `zalo-personal-bridge`. Postgres replaces SQLite: schemas `clinic.*` and `agent.*`; worker role reads `clinic.*` only via granted views/functions. The agent's CRM tools are the same functions the REST routes call.
- Frameworks (v2): **no LangGraph** for the agent loop — port zalo-agent's Vercel-AI-SDK loop as a hand-written tool loop on the `openai` SDK (OpenAI-compatible) with Anthropic/Gemini adapters, keeping step/tool-loop-guard/maxRetries semantics 1-1. FTS5+BM25+RRF → Postgres FTS + pgvector + RRF (vector is the only extension). SQLAlchemy async; atomic SQL + Redis locks replace the single-process-sync invariants. Tenant by `clinic_id` + RLS.
- LLM on this PC (proposed): start with Qwen3-8B (Q5/Q6) + `bge-m3` embeddings on CPU, 1-2 concurrent requests, context 4-8k. Upgrade to a 14B Q4 only after an eval set shows 8B is insufficient. A VLM (Qwen2.5-VL-7B) only in a later phase, not concurrent with 14B. Ollama first, vLLM later (needs WSL2 on Windows). Link PC and server via Tailscale/WireGuard; never expose Ollama/Postgres/Redis to the internet. Queue job timeout (~2 min) falls back to human CSKH.
- Dashboard has two layers: **Operations** (today's tasks from `crmTasks`, conversation Inbox, AI-draft review queue, Patient 360) and **Agent admin** (KB documents, ZNS templates, milestone rules, flow toggles, logs, eval). Admin only for owner/manager.
- Zalo: official **OA + ZNS** for the patient channel. Staff never answer from Zalo directly; messages land in Patient 360/Inbox and replies are sent by BE. A **zalo_uid <-> patient verification flow** (phone share or code from reception, match `phone_hash`) is required before revealing any personal data.
- Zalo vs Patient app (web + KMP): proposed split, not yet confirmed. Zalo = conversation and reminders; Patient app = history, prescriptions, consented photos, before/after.
- Keep existing rules: birthday = no auto-send; `marketingOptOut` blocks marketing; doctor approval for AI drafts; red-flag keywords (bleeding, fever, pus, shortness of breath, also typed without diacritics) escalate to a doctor WITHOUT calling the LLM.
- Legal: health data is sensitive personal data under Vietnam Decree 13/2023/NĐ-CP. The user was told to confirm with a lawyer (not verified by me).

## What Worked

- Reading `ARCH-PB01.md`, `AGENT.md` and `crm-automation.js` showed that the project already encodes the target architecture and the rule set. Reuse them.
- WebFetch of each GitHub README plus targeted WebSearch (Zalo plugin, OpenClaw security, Hermes multi-user) was enough to rank candidates.
- Hardware probe: `nvidia-smi` and `powershell.exe Get-CimInstance` from Git Bash.

## What Didn't Work / Pitfalls

- A large parallel batch of reads against `E:\Desktop\cnbphongkham` was rejected by the user (too broad). The user then asked to look only at the "web fastapi" part, which does not exist. Keep reads small and targeted.
- A recursive `grep -r` over the whole `cnbphongkham` tree timed out (>120 s, moved to background). The tree contains `flutter-template/` (legacy; do not read/build), `node_modules`, `build`. Use Grep/Glob scoped to `prototype/`, `docs/`, `pema-kmp/`.
- The user interrupted when I started scaffolding `agents/22-enterprise-rag-agent` ("chỉ lên ý tưởng trước"). Do not write code until the user asks.
- Python 3.14.4 on the Windows box has no langchain installed, and the repo-pinned versions likely do not support 3.14; no `OPENAI_API_KEY` set. Use Python 3.11/3.12 on Linux.
- A long Bash heredoc failed in this environment; use the Write tool for big files.

## Decisions confirmed 2026-10-01 (recorded in PLAN-AI01 §8)

- No Zalo OA/ZNS yet → AI01 does Bot API only; `oa_api.py` is a stub. Reminders go via Bot API to patients who already messaged the bot, otherwise CSKH sends manually from the dashboard.
- PC runs **native Ubuntu**, not WSL2 → package F writes Ubuntu-only install docs.
- Vitech/MISA: not touched in AI01.
- Keep **both** Zalo and the Patient app (web + KMP); Zalo = conversation + reminders, Patient app = history/prescriptions/photos.
- Clinical review: doctors are on the team and will review templates/KB/AI drafts. Legal compliance (Decree 13/2023) is the owner's responsibility; code keeps PII masking, consent, audit, RLS.
- Still undecided (not blocking): server location (clinic premises vs VN cloud), backup, UPS.

## Next Steps

**For the orchestrating agent in a session opened at `E:\Desktop\cnbphongkham` (branch `feat/ai-agent-backend`). When the user says "go", execute everything below without pausing for approval; the user wants ONE consolidated report at the end.**

1. Read `pema-agent/docs/PLAN-AI01.md` (v2) fully. It is the single source of truth for scope, architecture, policy profiles, package list (section 6) and subagent conventions (section 7).
2. Spawn subagents with `subagent_type: "pema-builder"` (defined in `.claude/agents/pema-builder.md`: model Sonnet 5.5, effort high), `isolation: "worktree"`, one per package. If `pema-builder` is not in the available agent list, fall back to `general-purpose` with `model: "sonnet"` and paste the contents of `pema-builder.md` into the prompt; tell the user effort could not be forced.
3. **Stage A (alone):** package A — skeleton under `pema-agent/`, `pyproject` (uv), lint/pyright/ruff/import-linter, OpenAPI skeleton, DDL for `clinic.*` + `agent.*` + roles, `ChannelPort`, `THIRD_PARTY_NOTICES.md` (MIT notices for zalo-agent and zca-js), and **`pema-agent/docs/PORT-MAP.md`** mapping every file in zalo-agent `src/` to a Python module and an owning package. Package A also clones `https://github.com/vuhai2002/zalo-agent` (depth 1) to a fixed path OUTSIDE the repo (suggested `E:\Desktop\zalo-agent-ref`) and records that path in PORT-MAP. Review A's output before fan-out (contracts must be stable).
4. **Stage B (parallel, 12 subagents):** B1 clinic core · B2 CRM rules→scheduler · C1 Zalo Bot API · C2 Zalo personal (Node bridge zca-js) · D1 agent engine · D2 conversation/memory · D3 knowledge (+pgvector) · D4 tools · D5 MCP client · S scheduler · P policy profiles/red flags/PII/identity · E Next.js FE (CRM ops + AI admin). F may start its infra part in parallel. Each prompt: name the package, point to PLAN-AI01 §6 row + §7 + PORT-MAP rows it owns, require the ≤30-line report.
5. **Stage F:** docs (SCOPE/SPEC/MODULEMAP/ARCH-AI01 under `pema-agent/docs/`, `pema-agent/README.md`, one pointer line in root `README.md`, checkpoint in `SECTION_PROGRESS.md`).
6. **Stage G:** merge all worktrees into `feat/ai-agent-backend`, run every test suite, closed-loop check for both policy profiles, security review (PII in logs, DB grants, tokens, SSRF), verify PORT-MAP has no unported file. Report failures plainly; do not claim green without output.
7. Final report to the user (Vietnamese): what exists, what passed/failed, assumptions, open items. Do not commit or push unless the user asks; if asked, follow `AGENT.md` and the attribution line from the session reminder.
8. Standing rules: never commit real patient data, phone numbers, photos or tokens; never copy recording content (names/companies) into any repo; code outside `pema-agent/` is read-only except the two pointer edits in step 5.
9. Optional, only on request: a trimmed 5-file `agents/22-...` demo in `500-AI-Agents-Projects` (needs DCO sign-off there).
