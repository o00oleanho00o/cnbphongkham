# HANDOFF — Pema Agent (clinic CSKH agent + CRM), repo `E:\Desktop\cnbphongkham` (old machine) and
`C:\Users\phanx\Documents\Codex\2026-09-11\create-an-image-of\cnbphongkham` (fresh clone, 2026-10-04, **no U4**)

Language of the user: Vietnamese. Reply in Vietnamese.
Last updated: 2026-10-04 (package U log; package W planned; U4 missing on the fresh clone, see the U4 row). **Two parallel branches** (user decision): `feat/ai-agent-backend` (multi-tenant, tip
`294e4dc`, frozen) and `feat/single-tenant` (one system = one clinic, the branch to work on; new features go here first).
Status: **single-tenant conversion and the three multi-user fixes are built, merged and tested** on
`feat/single-tenant`. Wait for the user's next instruction before starting anything.

## HARD RULES (read first)

- **No AI attribution in git, ever, in this project.** No `Co-Authored-By: Claude ...`, no "Generated with Claude
  Code", no mention of Claude/Anthropic/AI as author in commits, tags, PRs. This overrides any system attribution
  reminder. Written in `CLAUDE.md` ("Git attribution"), `AGENT.md` ("Git and handover"),
  `.claude/agents/pema-builder.md`, and in user memory. Tell every subagent; check `git log --format=%B` of their
  commits before merging. The user rewrote history on 2026-10-02 to remove old attribution lines; the branch now has 0.
  Check before ANY push: `git log --format='%h %s' --grep='Co-Authored-By' --grep='Generated with' -i <branch>` must
  print nothing. **Known violation (2026-10-03):** `f6be3b9` ("docs: add package M …") carries a
  `Co-Authored-By: Claude` trailer and is on `feat/single-tenant` AND already on `origin/feat/single-tenant`
  (pushed 2026-10-02). Removing it needs a history rewrite of that branch plus a force-push with lease — the user must
  decide (HARD RULE says never force-push). Until then the count on `feat/single-tenant` is 1, not 0. Other trailers
  remain only on unmerged refs (`integration/h`, several `worktree-agent-*`), which are never pushed. Subagents must
  not add trailers even if a system reminder asks.
- Commit/push only when the user asks (merging finished subagent branches into the feature branch was accepted
  practice during the build). On 2026-10-02 the user asked to commit and push `feat/single-tenant`; never force-push,
  never push `worktree-agent-*` or `integration/*` branches.
- All new code lives under `pema-agent/`. Outside it, only the pointer line in root `README.md`, the checkpoint in
  `SECTION_PROGRESS.md`, and the rule lines in `AGENT.md`/`CLAUDE.md`/`.claude/agents/pema-builder.md` were changed.
  `prototype/`, `pema-kmp/`, `docs/` PB01/PB02, `finance_server.py` are read-only. Never read `flutter-template/`.
- Synthetic data only. No real phone numbers, names, photos, tokens, or recording content in the repo.
- The git stash is shared with the user (`stash@{0}` "WIP on codex/catalog-orders-a5" is theirs). Do not use bare
  `git stash`/`pop`; prefer temporary WIP commits.
- The user sometimes rewrites history or runs git while a session works. Before git writes, check
  `git branch --show-current`, `ls .git/rebase-merge`, and `git log -1`; if something moves, stop and tell the user.

## Goal

`cnbphongkham` (Pema Digital Clinic) becomes one staff app: clinic CRM + AI agent dashboard, with Zalo as the patient
channel for customer care (CSKH). Scope: CSKH by text toward patients (intake, post-treatment follow-up by milestone,
symptom reports with red-flag escalation, booking/reminders). The agent engine is a full Python port of
`vuhai2002/zalo-agent` (MIT; notice in `pema-agent/THIRD_PARTY_NOTICES.md`) plus clinic CRM and one Next.js FE.

## Single-tenant branch (`feat/single-tenant`) — read this first

Why: clinics, hospitals and banks want high security and each runs its own system. Decisions: remove RLS entirely
(one database = one clinic; keep ALL other protections), keep both branches in parallel, keep several Zalo accounts per
clinic as in zalo-agent. Details: `pema-agent/docs/CONTRACTS-AI01.md` §10 (single-tenant), §11 (live updates),
`ARCH-AI01.md` §14 (two branches) and §15 (live), `SECURITY-REVIEW-AI01.md` (SEC-45..63), `pema-agent/README.md`.

- **DB:** `clinic.clinic` holds exactly one row (CHECK + UNIQUE + delete trigger); no RLS policies, no
  `set_config('app.clinic_id')`; `ctx.the_clinic_id()`, `clinic.ensure_clinic`. Alembic single head
  `st_0009_single_tenant`. `clinic_id` columns and store/port arguments are KEPT on purpose as an "installation id"
  (CONTRACTS §10.8); removing them is a later contract change. Roles `be_app`/`agent_worker` and the `clinic_agent`
  views/SECURITY DEFINER functions stay (agent_worker still cannot read raw `clinic.*`).
- **Env:** `PEMA_CLINIC_NAME`, optional `PEMA_CLINIC_ID`; `migrate.sh` stops if a second clinic row exists or the id
  changed.
- **Login:** email + password only (`clinic_slug` is refused with 422). Webhooks:
  `/api/v1/webhooks/zalo-bot/{account_id}` and `/api/v1/webhooks/zalo-bridge/{account_id}`; webhooks already registered
  at Zalo with the old path must be registered again. Clients outside `pema-agent/` (patient app, KMP, scripts) that
  send a slug or use old paths are NOT checked.
- **Live updates (new):** `GET /api/v1/events` (SSE, session required, re-verified every 15 s, per-user cap 5, no PII in
  payloads, types `inbox.changed`/`tasks.changed`/`review.changed`/`presence.changed`) over Redis pub/sub
  (`pema.live`); presence `POST/DELETE /api/v1/conversations/{id}/presence` (TTL 30 s, warning only, no lock) and
  `viewers` on conversation DTOs; Caddy skips compression for the stream. FE falls back to polling when the stream is
  down. Known: a closed tab leaves its viewer ~31 s (SEC-58); stream caps are per API process.
- **Assignee picker (new):** `GET /api/v1/staff/assignable` (any logged-in staff; active owner/manager/doctor/cs_staff;
  `{id,name,role}` only), one server-side check for conversation, CRM task and patient assignees, audit with ids.
- **Verified on the merged tip `0639903` (real Postgres pgvector pg17 + Redis 7, throwaway containers):** pytest
  4714 passed, 10 skipped, 0 failed; ruff, pyright strict, import-linter clean; FE vitest 407 passed, eslint/tsc/
  prettier clean, `next build` OK; bridge 296 passed. Real compose stack behind Caddy: login by email+password,
  assignable list, assign conversation → colleague's SSE stream got `inbox.changed`; two-browser run (presence in
  ≤2 s, inbound message in both Inboxes in ≤2 s without reload, Redis stop/start recovers). `live-real-check.ts` is a
  manual script, not CI. Not run: the 200-stream process cap with many users.
- **Pitfalls found:** the api Dockerfile used a shared uv cache that served a stale wheel (now `--no-cache`); a
  Postgres container on Docker Desktop stalls at checkpoint during long test runs (use `-c fsync=off` for throwaway
  DBs); the FE once sent `due_by` as datetime where the API wants a date (fixed; the mock had hidden it); tooling that
  creates worktrees refuses when the drive letter case differs (`e:` vs `E:`): create the worktree by hand with
  `git worktree add E:/...`.
- **Open (from SEC-63 and reviews):** assigning a conversation to a doctor outside their patient scope hides it from
  them (block it or widen scope?); a user locked after assignment keeps their items until reassigned; reception sees
  colleague names and roles; no general per-user rate limit on staff routes except login.

The sections below were written for `feat/ai-agent-backend` and still describe the shared engine; where they mention
RLS, clinic slug login or `h_0008_merge_heads`, the single-tenant branch differs as described above.

## Current Progress (what exists, written at `feat/ai-agent-backend` tip `294e4dc`)

Docs to read first: `pema-agent/docs/PLAN-AI01.md` (v2, §8 decisions), `CONTRACTS-AI01.md`, `PORT-MAP.md`,
`SCOPE-AI01.md`, `SPEC-AI01.md`, `MODULEMAP-AI01.md`, `ARCH-AI01.md` (§13 open items), `SECURITY-REVIEW-AI01.md`
(44 findings SEC-01..44), `pema-agent/README.md`, `pema-agent/infra/README.md`, `infra/ubuntu/HUONG-DAN-UBUNTU.md`.

- **Backend** `pema-agent/backend/apps/api/pema/` (FastAPI, Python 3.12, uv workspace, SQLAlchemy async, Postgres +
  pgvector, Redis): ported channels (Zalo Bot API; Zalo personal account via Node bridge `backend/bridges/zalo-personal`
  using zca-js), middleware, agent loop (own tool loop on `openai` SDK + Anthropic + Gemini adapters), 15 tools,
  conversation/memory, knowledge base, scheduler, MCP client; plus `clinic/` (CRM, RBAC, audit, RLS), `policy/`
  (profiles `staff_assistant` / `patient_channel`, red flags before LLM, PII masking, zalo_uid identity),
  `composition/` (wiring), `retention/`, `workers/main.py`. DB schemas `clinic.*`, `agent.*`, `clinic_agent`
  (views/SECURITY DEFINER functions); roles `be_app` (API) and `agent_worker` (worker, no raw `clinic.*`).
  Alembic single head `h_0008_merge_heads`.
- **Frontend** `pema-agent/frontend/` (Next.js 16 App Router, TS, Tailwind v4): ops screens (today, inbox, review
  queue, patient 360, templates), AI admin (accounts/QR, agents, model, tools, KB, schedules, MCP, usage, logs,
  policy, audit), **staff management `/admin/users`** (newest). Mock backend `frontend/mock` covers every OpenAPI
  operation. API address is read at runtime (`PEMA_API_INTERNAL_URL`, route handler proxy).
- **Infra** `pema-agent/infra/`: docker-compose (postgres, redis, migrate, api, worker, frontend, bridge, caddy
  profile `proxy` with `docker-compose.proxy.yml`), Dockerfiles, `.env.example`, scripts (secrets, roles, migrate,
  backup/restore), Ubuntu-native guide, Caddy (`infra/caddy`, TLS auto/internal/off). Makefile targets include
  `up-proxy`, `down-proxy`, `retention-dry-run`.
- **LLM: third-party API** (2026-10-02, user decision, like zalo-agent): `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_API_KEY`/
  `LLM_MODEL` or the admin Model screen; seed `LLM_BASE_URL=https://openrouter.ai/api/v1`, model/key empty. Local
  Ollama is paused: commented blocks labelled `TẠM TẮT LLM LOCAL (2026-10-02)` in compose, Makefile (`up-ollama`),
  `.env.example`, FE preset; `PEMA_EMBEDDING_ENABLED` defaults to false (KB = keyword search, as in zalo-agent).
  Re-enable by searching that label. Consequence documented: conversation text leaves the clinic; `patient_channel`
  still masks PII; `staff_assistant` does not force masking.
- **Done after the main build (2026-10-02):** absolute session lifetime (`PEMA_SESSION_ABSOLUTE_DAYS`, default 7);
  owner password reset `POST /api/v1/admin/users/{id}/password`; staff list/create/edit/lock
  `GET/POST/PATCH /api/v1/admin/users` (perm `admin.users.read` owner+manager, `admin.users` owner only; no self-lock,
  keep ≥1 active owner, lock/role change revokes sessions, no hard delete); retention purge (`pema/retention`,
  `python -m pema.workers.retention [--dry-run]`, `PEMA_RETENTION_*_DAYS`, 0 = keep; clinical/messages default keep);
  Caddy reverse proxy; `PEMA_TRUSTED_PROXIES`; runtime FE API URL.

### Last verified results (staff-screen run, real Postgres pgvector pg17 + Redis 7)

| Suite | Result |
|---|---|
| pytest backend + evals | 4579 passed, 10 skipped, 0 failed |
| ruff check/format, pyright strict, import-linter | clean (4 contracts kept) |
| FE eslint/tsc/prettier, vitest | clean, 294 tests passed, `next build` OK |
| Bridge (Node) | 296 tests passed (earlier run) |
| Playwright 5 viewports (mock) | no overflow, no console errors |
| Login through Caddy (internal TLS, seeded demo) | worked, cookie HttpOnly+Secure; owner reset revokes target session |

DB tests need `PEMA_TEST_DATABASE_URL` (superuser URL, image `pgvector/pgvector:pg17`) and `PEMA_TEST_REDIS_URL`;
without them ~880 tests skip. On this Windows box: no `make` (run recipe commands by hand), set `UV_LINK_MODE=copy`,
run `uv sync --all-packages` first.

### NOT verified yet

Real Zalo (Bot API token, QR login via bridge), any real LLM call (no API key on this machine), real Ollama on
Ubuntu, NVIDIA driver/Tailscale/ufw/UPS on Ubuntu, Let's Encrypt (`auto` TLS), encrypted backups (age/gpg), FE on a
real device or against the real API outside the proxy test, model quality (evals never run on a real model).

## What Worked

- Plan first, then one stage A (contracts, skeleton, PORT-MAP) alone, then parallel `pema-builder` subagents
  (`.claude/agents/pema-builder.md`, Sonnet, `isolation: "worktree"`), then one integration subagent on a
  temporary `integration/*` branch, then fast-forward `feat/ai-agent-backend`. Each subagent prompt names its owned
  paths, forbids touching shared docs during parallel work, and requires a ≤30-line report with real test output.
- Every worktree starts on old `master`: prompts must begin with `git reset --hard feat/ai-agent-backend`.
- Per-package Postgres/Redis containers with unique names and random host ports avoid clashes in parallel runs.
- After a rate-limit stop (HTTP 429, "session limit"), resuming each subagent with SendMessage from its uncommitted
  worktree state lost no work; resume in small waves and tell them to commit often and not spawn sub-subagents.
- Independent spot checks before merging: `git merge-base --is-ancestor` for every branch, grep for tracked `.env`/keys,
  grep commit messages for attribution.

## What Didn't Work / Pitfalls

- Launching 13 subagents at once hit the API session limit; all stopped mid-work. Launch in waves.
- A subagent stopped by the user cannot be resumed; move its WIP via a temporary commit on its branch and start a new
  subagent that resets onto that branch.
- The user's history rewrite flattened merge commits and dropped fixtures from two conftest files
  (`tests/api/routers/conftest.py`, `tests/config/conftest.py`); fixed forward in `2b8be9b`. After any rewrite,
  compare `git diff <old-tip> HEAD -- pema-agent` before trusting the tree.
- A full pytest run once failed `test_port_map_targets.py::test_every_src_file_has_an_existing_python_target` while
  the repo was being rewritten; it passed alone and in the next full run. Treat as environment, re-check if it recurs.
- `test_scheduler_loop` slow-job test used ms thresholds and flaked; now gated by an event.
- Compose passes unset vars as empty strings: integer settings need empty-to-None validators (done for retention).
- Next.js `rewrites()` are fixed at build time; hence the runtime route-handler proxy.
- Long Bash heredocs sometimes fail here; use the Write tool or small Python scripts for big edits. Preserve CRLF/LF
  of the existing file when editing on Windows.
- Early in the project the user rejected broad reads of the repo and a recursive grep timed out (node_modules, build,
  flutter-template). Scope searches to `pema-agent/`.

## Open decisions for the clinic owner / doctors (do not decide in code)

1. May an owner lock / change role / reset password of another owner? (allowed now, except self and last active owner)
2. Open `admin.users.read` to cs_staff/reception so the "Phụ trách" picker on Today can list staff? (not opened)
3. Real retention periods per Decree 13/2023; deletion rules for decided review items, Zalo display names/contacts,
   CRM activity notes, conversation summaries.
4. SEC-22: staff manual sends carry a client-declared `proactive` flag (false bypasses kill switch, window, cap,
   consent); choose a server-side rule and whether the kill switch also blocks replies.
5. Drafts made by `review_item.create` carry no KB citations while AGENT.md wants sources on AI drafts.
6. Doctor review: red-flag list (two provisional groups `severe_allergy`, `vascular_vision`), holding message, 46 eval
   cases, RBAC matrix, persona sentence asking phone/receptionist code, auto reassurance, auto reminders before
   template approval, proactive cap 10/day, MCP for patients.
7. Data processing agreement with the third-party LLM vendor before real data; server location; file storage
   (local volume vs object storage); public HTTPS for Zalo webhook (polling recommended until then); backup retention;
   UPS budget. Zalo personal account (zca-js, unofficial) risks account lock: use a secondary account.

## Package M — per-patient care agent (BUILT on `feat/single-tenant`, 2026-10-03; wiring and real-model run still open)

### Progress log (one line per step; merge commit on `feat/single-tenant`; gate = full backend pytest + ruff +
pyright strict + import-linter run by the director in the step's worktree, 0 attribution lines, report received)

| Step | Branch / commit | Merged as | Gate result | Notes |
|---|---|---|---|---|
| M1 schema, models, pairing | `care/m1` `d4c6dc5` | `4c7ae84` | pytest 4750 passed / 10 skipped / 0 failed; lint clean | 7 `agent.*` + 3 `clinic.*` tables, migration `m_0001_care_tables`, worker reads staff tables via `clinic_agent.*` views; open: `create_patient` does not call pairing yet; `patient_ownership` vs `patient.doctor_id` not synced |
| M2a event loop, tick, window, cap | `care/m2a` `7fc0f0f` | `0ee3d17` | pytest 4798 / 10 / 0; lint clean | Protocols in `pema/care/ports.py` for Harness, ChannelSend, Scheduler, ReviewSink…; open: wiring adapters + webhook→`CareEventBus`, `TickRuleSource` impl, product question "night replies wait for 08:00?" |
| M3 autonomy L0–L2, trust, override, kill switches | `care/m3` `aeb7c1b` | `0901452` | pytest 4827 / 10 / 0; lint clean | Settings in `agent.runtime_settings` keys `care.autonomy`/`care.kill_switch`; all thresholds `pending_doctor_approval`; open: `actions_log` needs `kind`/`initiator` columns (one migration, M2b/M2c/M4 also want it); M1 bug `autonomy_override` JSONB needs `none_as_null=True`; hooks to wire: B1 approve → `ReviewDecidedHook`, M2b `release_to_auto` → `set_override`, M4 → `KillSwitchState.blocks` |
| M4 specialists Scheduler/Knowledge/Reviewer, delegate depth 1, TaskResult, budget | `care/m4` `de26497`+`a29367d` | `3657633` | pytest 4943 / 10 / 0; lint clean | Status partial: no real Ollama run (local LLM off on this box) — M6/wiring must record real timing; Reviewer is deterministic (5 checks, no model); 3 locks keep depth = 1; open: wiring `build_delegate_spec` into `DefaultToolRegistry`, `CareTurnScope` in `ToolContext.extras`, `seed_specialists`, a `SlotSearch` impl; staff must bind/approve KB sources for `care-knowledge` |
| M2b control state machine, handoff skill, depth D1–D5 | `care/m2b` `c176c0b`+`e820fae`, retry 1 `care/m2b-fix` `dcd2adb` | `f457314` | attempt 1 FAILED gate (47 failed: `extra={"created": …}` reserved LogRecord key in `control.py`, hidden in care-only runs); retry 1: pytest 5100 / 10 / 0; lint clean; guard test `test_log_extra_keys.py` | Red flags → D5 with no model call; failed model → D4 conf 0; all thresholds `pending_doctor_approval`; open: `ReviewKind` has no `suggestion`; `handoff_requests` needs a `summary` column; wiring for `MessageTextSource`/`DepthLlm` |
| M2c staff routing, SLA, 24/7 on-call, reminder pause/reconcile | `care/m2c` `fca8103`+`0f7cbff`+`eb563dd` | `eac431e` | pytest 5206 / 10 / 0; lint clean (pre-fix run had 121 failures, all the M2b LogRecord bug) | Migration `m_0002_paused_reminders`; chain state in `handoff_requests.candidates`; on-call read from DB each call; SLA 5/30 min and `max_late_hours` all `pending_doctor_approval`; open: real `StaffNotify`/`SlaScheduler`/`DueReminderSource` adapters + periodic `sweep_overdue`; no re-alert after chain ends at on-call (product decision); disabled users stay in chain (`staff_profile` has no active flag) |
| M5 supervision + admin screens, care API contract | `care/m5` `e6cbf1b`+`efa5be9`+`f5c4bff` | `f829a70` | pytest 5223 / 10 / 0; lint clean; FE eslint/tsc/prettier clean, vitest 56 files / 459, `gen:types` no diff, `next build` OK | Status partial: 15 routes `/api/v1/care/**` + perms `care.read/act/admin/matrix/approve` + events `handoff.changed`/`care.changed`; routes answer 503 until a `CareSupervision` impl is installed as `app.state.care` (NOT built — needs a wiring package: SQL impl over `SqlControlStore`/`CareControl`/`RoutingService`/`autonomy`, audit rows, worker-side event publish, doctor scope); screens live under `(admin)/care` and `(admin)/admin/care` (no `(ops)` group); screenshots `pema-agent/demo-assets/m5/` |
| M6 evaluation, labelled cases, report | `care/m6` `fa34e4d`+`71aaf97` | `1c5994c` | pytest 5256 / 10 / 0 (incl. evals); lint clean | `evals/care/`: 83 synthetic cases, `run_eval.py`, generated `report.md`; everything model-free measured, model numbers NOT MEASURED (no Ollama here; commands in report §9); defects found, not fixed: D1 rule misses "mở cửa mấy giờ" (M2b), serious-edit recall 10/12 (M3 negation list), `d4-10` over-triaged to D5 (doctor decides); PyYAML absent → `yaml_subset.py` stopgap |

Pushed to `origin/feat/single-tenant` after each merge (user instruction 2026-10-03: push step by step, write HANDOFF
when done). Running protocol: one `pema-builder` per recipe in a hand-made worktree (`git worktree add E:/... <base>`),
rolling start (next step starts from the previous step's first commit, before its gate), ≤4 agents at once.

### Result of package M (2026-10-03, all 8 steps merged, tip pushed)

M6 numbers (`pema-agent/evals/care/report.md`, run `PYTHONPATH=.. uv run python -m evals.care.run_eval` in
`pema-agent/backend`; tests `uv run pytest -c pyproject.toml ../evals/care`): D5 recall 19/19 = 100% with 0 model calls
(95/95 after 5 rewrites each, 0/66 changed without diacritics); oracle depth accuracy 98.8%, handoff precision/recall
100%, 0 false negatives; rules-only 0 false negatives, 21 safe false positives; auto-send gate 0 hard-rule violations in
36,288 combinations; routing chain ends at on-call 220/220, SLA correct 330/330, no model; reminders 0 sent / 0 model
calls while a person holds the conversation (97 scenarios); orchestration-only p50/p95: 0.08/0.13 ms (D1), 0.12/0.18 ms
(D2), 2.67/3.54 ms (D2 + two specialists), 0.28/0.46 ms (D5 handoff); tick over 500 patients 2–4 ms, 0 depth calls,
reply calls = drafts queued. NOT MEASURED (needs Ubuntu + RTX 3060 + Qwen3-8B, commands in report §9): real D2–D4
accuracy, per-call latency/tokens, tokens per patient per month.

What is NOT wired (package M has no live path yet; nothing talks to a patient): a `CareSupervision` SQL implementation
installed as `app.state.care` (M5 routes answer 503 until then); adapters for `Harness`, `PatientContextLoader`,
`ChannelSend`, `Scheduler`, `ReviewSink`, `MessageTextSource`, `DepthLlm`, `StaffNotify`, `SlaScheduler`,
`DueReminderSource`, `SlotSearch`; `build_delegate_spec` into `DefaultToolRegistry` + `CareTurnScope` in
`ToolContext.extras` + `seed_specialists`; webhook/B2 → `CareEventBus.publish`; a `TickRuleSource`; `create_patient` →
`CareAgentPairing.on_patient_created`; B1 approve → `ReviewDecidedHook`; periodic `sweep_overdue`; worker-side publish of
`handoff.changed`/`care.changed`. Suggested next package "M7 wiring" (one recipe, after the owner agrees).

Schema follow-ups (one migration): `actions_log.kind`/`initiator`/`reason`, `handoff_requests.summary`,
`care_agents.autonomy_override` with `none_as_null=True`, `ReviewKind.suggestion`; `patient_ownership` vs
`patient.doctor_id` sync; `staff_profile` active flag.

Doctor/owner decisions (all defaults flagged `pending_doctor_approval`): depth/autonomy matrix, N and confidence
threshold, serious-edit rule, holding-message wording, SLA minutes, `max_late_hours`, red-flag list (`d4-10`), re-alert
after the chain ends at on-call, whether night replies wait for 08:00, whether a rejected draft demotes, staff skill
list and the real 24/7 number.


What it is: one care agent per patient (1-to-1 pairing), proactive on events and a 06:00 tick; autonomy levels L0–L2
per action type; conversation control `AUTO → HANDOFF_ROUTING → STAFF` where the agent decides by itself to hand off
(`handoff` skill, depth D1–D5, D5 red flags without LLM), picks staff deterministically by skill/shift/SLA and moves on
when declined, chain always ending at the clinic's 24/7 on-call Zalo number read from DB; reminders paused while in
STAFF and reconciled on release; specialists Scheduler/Knowledge/Reviewer at delegation depth 1.

Where: plan `pema-agent/docs/PLAN-AI01-M.md` (§15 = owner decisions of 2026-10-02); recipes
`pema-agent/recipes/M/` — `00-README.md` (order, dependencies, code locations, rules), `_REPORT-TEMPLATE.md`,
`01-M1-schema` … `08-M6-eval`, one file per step, English. Recipes are in HEAD of `feat/single-tenant` (`17b70e2`).

Owner decisions already taken (do not re-ask): thresholds/matrix/N are the doctor's; no reminders while in STAFF
(pause, reconcile on release); return-to-AUTO may lower the level for a period; handoff is the agent's decision (no
"talk to a human" button); agent picks and re-picks staff, ending at the 24/7 number; multi-agent never talks to the
patient as a group. Still owed by the clinic: final depth/autonomy matrix, labelled sample cases, staff skill list,
the 24/7 number.

How to run it (when the user says so):
1. Work on `feat/single-tenant`. Prerequisites exist on this branch: D1 harness, S scheduler + `bot_enabled`, P
   profiles/red flags/PII, B1 actions, E frontend. Read `00-README.md` first; it maps steps to `pema/care/*`.
2. One `pema-builder` subagent per recipe, worktree from HEAD (create by hand with `git worktree add E:/...` if the
   tool refuses on drive-letter case). Prompt: "Follow `pema-agent/recipes/M/<file>.md`. Branch feat/single-tenant.
   Single-tenant: skip every RLS step, keep `clinic_id` as installation id (CONTRACTS §10.8). No git trailers."
3. Order: M1 → (M2a ‖ M3) → M2b → (M2c ‖ M4) → M5 → M6 (`00-README.md` table). Each returns a ≤30-line report.
4. Single-tenant adaptations the recipes do not yet say: M1 "enable RLS" → do NOT; grants/roles stay; `ensure_clinic`
   gives the installation id. M2a/M2c tick and SLA use the one clinic. M5 lives beside the existing live-updates FE
   (SSE `GET /api/v1/events`); add event types `handoff.changed`/`care.changed` rather than polling.
5. Before merging a worktree: pytest/ruff/pyright/import-linter green in the worktree, `git log --format=%B` of its
   commits has no attribution, report filed. Merge into `feat/single-tenant` only; never push `worktree-agent-*`.
6. M6 numbers (D5 recall 100% with zero LLM calls, p50/p95 latency on the RTX 3060) go into
   `pema-agent/evals/care/report.md` and a line here.

## Package U — UI parity with the old Pema web + port of the missing screens (IN PROGRESS on `feat/ui-parity`, 2026-10-04)

### Progress log (director-run gate per step: FE vitest/lint/tsc/build + `pnpm inventory` + `pnpm visual`, BE full pytest
incl. evals + ruff + pyright + import-linter, 0 attribution lines; merged into `feat/ui-parity` only, NOT pushed)

| Step | Branch / commit | Merged as | Gate result | Notes |
|---|---|---|---|---|
| U0 design foundation | `ui/u0` `f6bd955` | `ed0ba2d` | FE vitest 591; BE 5256 / 10 / 0 | tokens.css + generated tokens.json, kit, AppShell with old sidebar order, `pnpm visual`; fixed 2 inherited contrast failures |
| U1 restyle + inventory | `ui/u1` 5 commits | `eb70b80` | FE vitest 602, inventory 40 routes, visual 190/0; BE 5256 / 10 / 0 | `FEATURE-INVENTORY.md` + `pnpm inventory`, `pnpm smoke`; admin tables still scroll on phone (owner decision) |
| U2 dashboard + schedule | `ui/u2` `0c326b0` | `2cf3cc1` | FE vitest 672 (first run 11 files did not report under load; rerun green), visual 200/0; BE 5282 / 10 / 0 | no migration; open: check-in only on the visit's day?, dashboard for reception/CSKH?, at-risk/abandoned KPIs need a read model |
| U3 Patient 360 five tabs | `ui/u3` → retry 1 `ui/u3-fix` `c41d622` + merge `d743145` | `1c734b2` | attempt 1 FAILED (M2c test downgraded "-1"); retry: FE vitest 753, visual 220/0; BE 5315 / 10 / 0 | migration `u3_0010`; open: photo retention, consent wording, manager photo access, storage location |
| U7 guide / ask / CRM | `ui/u7` → retry 1 `1e19f34` → retry 2 `ui/u7-fix2` `5488d3f` | `81057ed` | attempts 1–2 FAILED (relative downgrade; then two alembic heads); retry 2: FE vitest 820, visual 235/0; BE 5359 / 10 / 0 | migration `u7_0001` restacked on `u3_0010`; "Hỏi Pema" = passage search (no LLM); label changed "Ask Pema" → "Hỏi Pema" |
| U4 services / resources / studio | `ui/u4` → retry 1 `ui/u4-fix` `24dfd1c` | (gate running) | attempt 1 FAILED (two heads after merge); retry 1: FE vitest 875, inventory 48, visual 250/0; BE pending | migration `u4_0010` restacked on `u7_0001` (chain m_0002 → u3_0010 → u7_0001 → u4_0010, one head). **2026-10-04: U4 is NOT on origin and NOT on the fresh clone** (`24dfd1c` unknown there, no `ui/u4*` branch, no `/studio` `/resources` `/services`, no `u4_0010`); it exists only on the old machine `E:\Desktop\cnbphongkham`. Push `ui/u4-fix` from there, or redo U4 from its recipe on top of `u7_0001`. BE gate result never recorded. |
| U5 cashier / orders | — | — | — | waits for U4 merge |
| U6 finance | — | — | — | waits for U5 |
| U8 parity audit | — | — | — | waits for all; PARITY-AI01-U.md |

Lessons for the remaining steps: every new migration must stack on the current single head (`alembic heads` = 1) or
`test_the_migration_chain_has_one_head` fails; migration tests must downgrade to a named revision, never "-1". Parallel
steps conflict on `openapi.json`/`schema.d.ts` (regenerate with `uv run python -m pema.api.export_openapi` and
`pnpm gen:types`), `router.py`, `actions/__init__.py`, `models/__init__.py`, `nav.tsx`/`nav.test.ts`,
`FEATURE-INVENTORY.md`. The director merges `feat/ui-parity` into a finished step's worktree, resolves, and gates the
merged tree before merging back. Gate scripts used: `fe-gate.sh <worktree> <log> <app-port> <mock-port>` (vitest, lint,
tsc, inventory, build, then `dev:mock` on its own ports + `pnpm visual`) and `be-gate.sh` (full pytest on a throwaway
`pgvector/pgvector:pg17 -c fsync=off` + `redis:7`). Parallel agents need their own PORT/MOCK_PORT. Worktrees are made by
hand (`git worktree add E:/... -b ui/<step> <base>`) because tool-made worktrees start from old `master`.


Owner decision 2026-10-03: port the old Clinic Web features that the Next.js FE lacks (dashboard, schedule, Patient 360
tabs consult/plan/session/photos, studio/resources/services, cashier/orders/catalog/A5 print, finance PB02, guide/ask,
CRM01 leftovers) by **rewriting them in Next.js + BE actions**; never wire the old localStorage web to the API; and
restyle the **whole** existing FE to the old web's design (tokens, sidebar, layout) **without losing any current feature**
(CSKH, agent admin, care supervision). Same design will be ported to the KMP app later, so tokens are exported as JSON.

Where: plan `pema-agent/docs/PLAN-AI01-U.md`; recipes `pema-agent/recipes/U/` (`00-README.md` order/locations/rules,
`_REPORT-TEMPLATE.md`, `01-U0` … `09-U8`). Old web is reference only (`prototype/`, `design-specs/`,
`.agents/skills/design-system/`), read-only.

How to run (when the user says so): branch `feat/ui-parity` (from `feat/single-tenant` at `bc094c8`; merge back to `feat/single-tenant` only when the user accepts the package); one `pema-builder` per recipe in its own worktree;
prompt "Follow pema-agent/recipes/U/<file>.md on branch feat/ui-parity. Single-tenant: no RLS, clinic_id =
installation id. Return the report in _REPORT-TEMPLATE.md format." Order U0 → U1 → (U2 ‖ U3 ‖ U4 ‖ U7) → U5 → U6 → U8.
Gates before merging a worktree: FE vitest ≥ 407 and `pnpm inventory`/`pnpm visual` green (from U1 on), lint/tsc/build,
BE pytest/ruff/pyright/import-linter, no attribution in `git log --format=%B`, report filed. Migrations use prefix
`u<step>_`; U8 adds the merge head. Photos: upload/view with consent only, no image analysis (scope unchanged).

## Package W — design of the old Pema web: screenshots, screen specs, web canvas (PLANNED 2026-10-04, awaiting owner approval)

Why: the app has a canvas (`Pema App.dc.html`, 82 mobile screens), generated specs (`design-specs/screens/`), the MCP
server `pema-design` and two skills. The old web has only its code in `prototype/`. Package U ports the old web by
reading that code directly, and `pema-agent/frontend/visual-ref/old/` is empty on this clone. The capture script
`prototype/review-desktop.cjs` requires Playwright from another machine's path.

Owner request 2026-10-04: build all three layers with subagents following recipes:
1. Screenshots of every old-web screen at 5 viewports.
2. Specs per web screen, served by the MCP server.
3. A web canvas on claude.ai/design whose blocks map 1:1 to `pema-agent/frontend/src/ui`, plus a skill
   `pema-web-design`.

**Owner rule (2026-10-04, final, replaces an earlier "app first" reading): the result must contain EVERY piece of
UI the old web has** — every page, tab, modal, dialog, state, field, action, status, filter and text. Nothing is
filtered or dropped. The app design supplies only the look: tokens, block shapes, kit components, sample data.
Where old web and app disagree on wording or a step, keep the old web's UI and record the app's version in
`design-specs/web/notes.json` (`differences`); the owner decides later (D8). `app_canvas` is a cross-reference,
never a filter.

Plan: `pema-agent/docs/PLAN-AI01-W.md` (scope, paths, gate, acceptance, decisions D1–D8). Recipes:
`pema-agent/recipes/W/` (`00-README.md`, `_REPORT-TEMPLATE.md`, `01-W0` … `07-W5`).
- Order: `W0 inventory → (W1 shots ‖ W2 specs+MCP) → W3a canvas foundation → W3b canvas screens → W4 skill/docs/audit
  → W5 push`.
- W5 is done by the director with the user (`/design-sync`). It is not a subagent step.
- Screen ids are `W<A-H><n>`, frozen in `design-specs/web/inventory.json` by W0.

Decisions waiting for the owner, with the plan's defaults:
- D1: write outside `pema-agent/` (only `design-specs/web/`, `Pema Web redesign canvas/`,
  `.claude/skills/pema-web-design/`, an additive MCP change, a pointer section in `CLAUDE.md`).
- D2: branch `feat/web-design` from `feat/ui-parity` `821f813`.
- D3: no Next.js-only screens in the canvas yet.
- D4: frames are 1440×900, plus 1920 and 390 for pages.
- D5: PNGs are not committed; `manifest.json` is committed.
- D6: the web canvas becomes the design-first source for Next.js, with a change-log rule.
- D7: new claude.ai/design project.
- D8: on a disagreement, keep the old web's UI, note the app's version in `notes.json`.

How to run, once approved:
1. Create the branch.
2. Start the shared services: old web on 4173, finance on 4174, design-viewer on 4180.
3. Per step, make a hand-made worktree (`git worktree add C:/wt/pema-<step> -b design/<step> feat/web-design`).
4. Spawn one `pema-builder` per step with `PLAYWRIGHT_MODULE` set to the main checkout's
   `pema-agent/frontend/node_modules/playwright` (Chromium installed 2026-10-03).
5. Gate per plan §5 before each `--no-ff` merge.
6. Never push until the user says so.

Machine note (2026-10-04): this checkout is `C:\Users\phanx\Documents\Codex\2026-09-11\create-an-image-of\cnbphongkham`,
a fresh clone, not `E:\Desktop\cnbphongkham`.
- It has no U4 commits: `ui/u4-fix` `24dfd1c` exists only on the old machine.
- `feat/ui-parity` IS on origin (`821f813`).
- The real Docker stack was started here: `pema-agent/infra/.env` was generated (git-ignored), and `seed_demo` was
  loaded (users `owner@example.test` and others; the password was given in the session, not stored here). The stack
  runs on ports 3000/8000.

### Progress log

| Step | Branch / commit | Merged as | Gate result | Notes |
|---|---|---|---|---|
| (none yet) | | | | |

## Next Steps (only when the user asks)

1. Small leftovers: rate limit on `PATCH /admin/users`; stale sentence in `frontend/README` saying change-password is
   disabled (`POST /auth/password` exists); `TableShell` missing space when `ghimCotCuoi` is on.
2. Apply the owner's answers to the open decisions above (each is a small, isolated change).
3. Real-environment acceptance: Ubuntu box, real LLM key, Zalo Bot API test bot, then QR login on a secondary
   personal account, then `evals` against the chosen model.
4. Housekeeping when the user agrees: about 45 `.claude/worktrees/*` worktrees (incl. `st-g2a`, `care-m1`…`care-m6`,
   `care-m2b-fix`) and the `care/*` branches, the `worktree-agent-*`
   branches and the temporary branches `integration/ai01`, `integration/h`, `integration/st`, `integration/st-live` are
   still on disk; nothing was deleted. All their
   work is already in `feat/ai-agent-backend` except the abandoned v1 worktrees. Docker build cache remains.
5. PR to `master` only if the user asks (no AI attribution in the PR body).
6. Package M is built (see "Result of package M" above). Next: the owner's answers to the decisions listed there, then
   an "M7 wiring" recipe, then the real-model run on the Ubuntu box.
7. Optional: cherry-pick live updates / assignee picker to `feat/ai-agent-backend` (default: no).
