# HANDOFF — Pema Agent (clinic CSKH agent + CRM), repo `E:\Desktop\cnbphongkham` (old machine) and
`C:\Users\phanx\Documents\Codex\2026-09-11\create-an-image-of\cnbphongkham` (fresh clone, 2026-10-04, **no U4**)

Language of the user: Vietnamese. Reply in Vietnamese.
Last updated: 2026-10-04 (package W built and merged; git history of `feat/single-tenant` rewritten and merged to `dev`; frontend design rules, agent and hook added). **Branches:**
`feat/ai-agent-backend` (multi-tenant, tip `294e4dc`, frozen); `feat/single-tenant` (one system = one clinic, tip `3493f10`, merged to `origin/dev`
by PR #11 as `e972af3`); `feat/ui-parity` (packages U + W, tip `8ab9faa`, on origin, contains `e972af3`).
Status: single-tenant, package M, package U (U0–U12, merged into `feat/ui-parity`, NOT pushed; round 2 U9–U12 merged WITHOUT the merge gate, see "Round 2 progress") and packages W and W2 are built. The frontend now has a design gate
(rule + agent `pema-ui-builder` + pre-commit hook, see "Session log 2026-10-04"). Package O (shared inbox) is BUILT on `feat/shared-inbox` (O1–O7 merged 2026-10-06, `1f12ab7d`, not pushed) but was merged WITHOUT any full test gate at the owner's request, see "Result of package O". Wait for the user's next instruction before starting anything.

## HARD RULES (read first)

- **No AI attribution in git, ever, in this project.** No `Co-Authored-By: Claude ...`, no "Generated with Claude
  Code", no mention of Claude/Anthropic/AI as author in commits, tags, PRs. This overrides any system attribution
  reminder. Written in `CLAUDE.md` ("Git attribution"), `AGENT.md` ("Git and handover"),
  `.claude/agents/pema-builder.md`, and in user memory. Tell every subagent; check `git log --format=%B` of their
  commits before merging. The user rewrote history on 2026-10-02 to remove old attribution lines; the branch now has 0.
  Check before ANY push: `git log --format='%h %s' --grep='Co-Authored-By' --grep='Generated with' -i <branch>` must
  print nothing. **Known violation (state 2026-10-04): fixed locally, NOT pushed.** The "docs: add package M …" commit had a
  `Co-Authored-By: Claude` trailer. It is gone from `feat/single-tenant` (`3493f10`, `origin/dev`, 0 trailers) and, since
  2026-10-04, from the local `feat/ui-parity` (`git filter-branch --msg-filter` over `e972af3..HEAD`, 189 commits got new
  hashes, tree identical, `e972af3` and master hashes untouched, 0 trailers). `origin/feat/ui-parity` still holds the old
  history (1 trailer, old `f6be3b9`) until the user allows `git push --force-with-lease origin feat/ui-parity`. Do NOT run
  filter-branch over master's lineage: GitHub-signed merge commits lose their signature and change hash. Local branches
  `backup/ui-parity-before-rebase` and `design/*` still contain the old commit; never push them.
  Other trailers
  remain only on unmerged refs (`integration/h`, several `worktree-agent-*`), which are never pushed. Subagents must
  not add trailers even if a system reminder asks.
- Commit/push only when the user asks (merging finished subagent branches into the feature branch was accepted
  practice during the build). On 2026-10-02 the user asked to commit and push `feat/single-tenant`; never force-push,
  never push `worktree-agent-*` or `integration/*` branches.
- All new **code** lives under `pema-agent/`. Design packages (W, W2) also write, as their `recipes/<PKG>/00-README.md` lists, to `design-specs/`, `Pema Web redesign canvas/`, `design-system/`, `design-viewer/src` (additive) and `.claude/skills/pema-web-design/` — this is allowed for subagents. Outside those, only the pointer line in root `README.md`, the checkpoint in `SECTION_PROGRESS.md`, and the rule lines in `AGENT.md`/`CLAUDE.md`/`.claude/agents/pema-builder.md` change. `prototype/`, `pema-kmp/` (except a recipe-named touchpoint), `docs/` PB01/PB02, `finance_server.py` are read-only. Never read `flutter-template/`.
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

## Package U — UI parity with the old Pema web + port of the missing screens (U0–U8 BUILT on `feat/ui-parity` 2026-10-05, NOT pushed; round 2 — U9–U12 — BUILT and merged 2026-10-06, NOT pushed; gate NOT run, see the round-2 entry below)

### Progress log (director-run gate per step: FE vitest/lint/tsc/build + `pnpm inventory` + `pnpm visual`, BE full pytest
incl. evals + ruff + pyright + import-linter, 0 attribution lines; merged into `feat/ui-parity` only, NOT pushed)

| Step | Branch / commit | Merged as | Gate result | Notes |
|---|---|---|---|---|
| U0 design foundation | `ui/u0` `f6bd955` | `ed0ba2d` | FE vitest 591; BE 5256 / 10 / 0 | tokens.css + generated tokens.json, kit, AppShell with old sidebar order, `pnpm visual`; fixed 2 inherited contrast failures |
| U1 restyle + inventory | `ui/u1` 5 commits | `eb70b80` | FE vitest 602, inventory 40 routes, visual 190/0; BE 5256 / 10 / 0 | `FEATURE-INVENTORY.md` + `pnpm inventory`, `pnpm smoke`; admin tables still scroll on phone (owner decision) |
| U2 dashboard + schedule | `ui/u2` `0c326b0` | `2cf3cc1` | FE vitest 672 (first run 11 files did not report under load; rerun green), visual 200/0; BE 5282 / 10 / 0 | no migration; open: check-in only on the visit's day?, dashboard for reception/CSKH?, at-risk/abandoned KPIs need a read model |
| U3 Patient 360 five tabs | `ui/u3` → retry 1 `ui/u3-fix` `c41d622` + merge `d743145` | `1c734b2` | attempt 1 FAILED (M2c test downgraded "-1"); retry: FE vitest 753, visual 220/0; BE 5315 / 10 / 0 | migration `u3_0010`; open: photo retention, consent wording, manager photo access, storage location |
| U7 guide / ask / CRM | `ui/u7` → retry 1 `1e19f34` → retry 2 `ui/u7-fix2` `5488d3f` | `81057ed` | attempts 1–2 FAILED (relative downgrade; then two alembic heads); retry 2: FE vitest 820, visual 235/0; BE 5359 / 10 / 0 | migration `u7_0001` restacked on `u3_0010`; "Hỏi Pema" = passage search (no LLM); label changed "Ask Pema" → "Hỏi Pema" |
| U4 services / resources / studio | `ui/u4` → retry 1 `ui/u4-fix` `24dfd1c` → sync `ui/u4-sync` | `ff14ecf` (fast-forward, 2026-10-05) | attempt 1 FAILED (two heads after merge); retry 1 + sync with W2/master (14 conflict files, openapi/schema regenerated): FE vitest 875, inventory 48, visual 250/0; BE 5386 / 10 / 2 (the 2 = care on-call, see below) | migration `u4_0010` on `u7_0001`. Studio = before/after photo viewer of one patient. |
| U5 cashier / orders / catalog | `ui/u5` `5130c55` `1f2d6fb` | `0f78638` | FE vitest 940, inventory 51, visual 285/0; BE 5419 / 10 / 2 | migration `u5_0010` on `u4_0010`; CLI `pema catalog import <json>` (run once after seeding); approved orders immutable (trigger); payment half left for U6. Owner: may cashiers approve orders? no cashier role exists. |
| U6 finance (PB02) | `ui/u6` → retry 1 `bfb9764` (ruff PT018 in a test file) | `fa3a6a2` | FE vitest 1093, inventory 57, visual 335/0; BE 5526 / 10 / 2; openapi 207 → 224 ops, none removed | migration `u6_0010` on `u5_0010`; invoices, receipts, commissions, rates, periods, CSV; order ↔ invoice seam. Owner: dedicated accountant role (manager holds it now), MISA export, refund/adjustment process, no finance demo seed in BE. |
| U8 parity audit | `ui/u8` `4ee6116` → retry 1 `65f8d5a` (unclaimed finance routes, stale hub index) | `34ff3c1` | FE vitest 1093, inventory 57, visual 335/0; BE 5635 / 10 / 2; web gates: inventory ok 384, specs 384=384, canvases 211+173 exit 0, coverage 384, hub ok; alembic one head `u6_0010` | `PARITY-AI01-U.md` (19-row table), 109 security tests (RBAC per role, audit, no logging), docs SCOPE/SPEC/MODULEMAP/ARCH updated. **Not tương đương yet**, see open items below. |

**Round 2 progress (U9–U12, 2026-10-06, director merged one at a time into `feat/ui-parity`, nothing pushed). The owner told the director to SKIP the merge gate for this round (no full BE pytest, no `pnpm visual`, no `pnpm build`, no `pnpm smoke`), so the numbers below are the agents' own targeted runs, NOT director-run gate results; one regression got through because of that (see U11 fix).**

| Step | Branch / commit | Merged as | Agent-reported checks (targeted, not the gate) | Notes |
|---|---|---|---|---|
| U11 accountant role | `ui/u11` `545ed38` `3c16ca3` | `7675f8c` | BE 159 + FE 272 targeted tests, inventory 57/137, ruff/pyright/tsc/eslint clean | `Role.ACCOUNTANT` (7th role), permission `finance_period.close` (accountant, manager, owner), migration `u11_0010` on `u6_0010` (role = text + CHECK, not a Postgres enum). **Safety flag, owner to confirm:** `order.approve` was NOT given to accountant or reception (doctor + owner only; a test and an HTTP 403 test pin it); "thu ngân duyệt đơn" needs its own explicit recipe. `ASSIGNABLE_ROLES` unchanged, test asserts accountant excluded. |
| U10 reception + room views | `ui/u10` `0e452b1` → sync `3dd2066` | `0d427d8` | BE 8 + 101 + 169, FE vitest 108 + 265 + 310 targeted, inventory 57/141 | migration `u10_0010` (appointment.room_id) restacked on `u11_0010`; room rules + blocks in the one appointment validator; reception table on `/today`, room grid on `/schedule`; CSKH queue and doctor board kept. Visual at 5 viewports NOT run. Old grid had mouse drag-to-move; not built (sheet does the same). |
| U9 patient parity | `ui/u9` `9434b79` → syncs `82ca797` `a6ed582` | `0f65ed3` | FE vitest 1191 (full run by the agent), BE 427 targeted, inventory 58/140 | migration `u9_0010` restacked on `u10_0010` (chain u6 → u11 → u10 → u9, one head); "Dịch vụ & tài chính" tab, create-patient dialog, chips, brief (template, no LLM) / Nhắn tin / key facts / aftercare / expected return, "Tiền sử & chẩn đoán". Accountant reaches the tab through `GET /patients/{id}/finance-tab` (`finance.read`), no clinical data. Visual comparison NOT done. |
| U11 fix | `ui/u11` `fe78dec` | `dc932a3` | 115 targeted + director re-run of care_routing_store/care_schema/test_database/test_u11_accountant: 112 passed, 3 failed (the 3 clock tests) | **Regression the skipped gate let through:** `u11_0010.downgrade` narrowed the role CHECKs while the seeded accountant existed, breaking 3 package-M migration tests. Fix: downgrade keeps the CHECKs widened (no data destroyed, no role recast, audit not rewritten); regression test added. |
| U12 housekeeping | `ui/u12` `fe036a3` → sync `7d0c87d` | `58243e5` | director re-ran: web-inventory 0, web-specs 0 (384), canvas-build 0, unify-index 0, pending-web 0, pending 0; agent: design-specs 0, design-system check 8/8, tokens 0, tokens.test 58 | hub wording, MCP `get_web_screen` serves the spec without a snapshot, catalog text, `inventory_sha` recomputed by tool, pending baseline `0c454cc`, dark contrast (brand-500 3.81 → 4.56:1, accent-strong 3.44 → 4.57:1, light unchanged). **Not met:** old-web shots 1150 generated into git-ignored `visual-ref/old/`, but 103 (9.0%) differ from `manifest.json` SHAs (recipe asks 0, tool tolerates 5%); agent says pixel noise, geometry identical, `--check` (30+ min) not run; manifest not rewritten. |

Round-2 known failures: package-M `tests/care/test_care_routing_store.py` now has **3** clock-dependent failures, not 2 (the two on-call tests plus `test_out_of_hours_d5_over_postgres_gives_one_template_with_the_number_of_the_database`); the third also fails at `472616b`, before round 2, so it is not new. Owner still declined to fix them. Still open from round 2: `text-white` on `bg-brand-500` in dark mode (admin pages) is below 4.5:1; `patient_app_event` and `patient_brief` have no reader on the Patient Mobile side yet; billing-only Tổng quan / Kế hoạch / Lịch sử for the accountant would be a later step; the full BE pytest, `pnpm visual`, `pnpm build`, `pnpm smoke` have not been run on the merged tree (`58243e5`).

**Known baseline failure (package M, not package U):** `tests/care/test_care_routing_store.py` (3 tests: `test_the_on_call_contact_comes_from_the_database_on_every_call`, `test_the_whole_chain_over_postgres_ends_with_the_on_call_contact_and_staff_can_still_accept`, and — seen on 2026-10-06 — `test_out_of_hours_d5_over_postgres_gives_one_template_with_the_number_of_the_database`, which also fails at `472616b`, before round 2) fail in every full run. Earlier gate runs (U4–U8) showed only the first two. The test freezes `NOW = 2026-10-05 03:00 UTC` while the seeded on-call row gets `valid_from = now()` from the DB (`m_0001`), so the row is never valid at `NOW` after that instant. Fix: an explicit `valid_from` in the seed. Not fixed (outside package U).

**Open items after U8 — status 2026-10-06 (the list is as written after U8; round 2 CLOSED the patient-parity items, the reception/room views, the accountant role, the catalog text, the `inventory_sha` and the pending baseline; what is still open: the 14 `none` inventory ids not covered by U9, the guide articles, old-web PNG regeneration drift (103 of 1150 SHAs), and the owner decisions below). Original text, recorded in `pema-agent/docs/PARITY-AI01-U.md`:** create-patient dialog (WC3, `POST /patients` exists), filter chips on `/patients`, Patient 360 "Dịch vụ & tài chính" tab and add-service dialog (WC10, WC19), AI brief / Nhắn tin / key facts / home care / expected return dialogs (WC13/15/16/18), "Tiền sử & chẩn đoán" card; 14 inventory ids still `none` (WA10, WC3, WC10, WC13, WC15, WC16, WC18, WC19, WC25, WC27, WC29, WC32, WC34, WC28 stale); guide has 3 of the old 11 articles; old-web PNGs in `visual-ref/old/` are git-ignored, so a fresh checkout has only `manifest.json` (run `web-shots.cjs` against the old web); `pending-web.cjs`/`pending.cjs` fail because the sync baseline `c40ba22` is not in git history (now `0c454cc` after the 2026-10-05 history rewrite below — same tree, new hash); `catalog-nextjs.cjs` text still says /cashier and /finance are greyed "(sắp có)"; `snapshot.json` `meta.inventory_sha` was edited by hand after the catalog change (re-walking the old web takes hours). Owner decisions: reception list on `/today`?, room-column grid on `/schedule`?, accountant role, cashier approval, period-close owner, photo consent wording, deleting superseded `prototype/*` and `finance_server.py`.

**Owner decisions 2026-10-05 (round 2, on the open items above) — full reasoning in `PLAN-AI01-U.md` §7, new recipes
`recipes/U/10-U9-*.md` … `13-U12-*.md`, built and merged 2026-10-06 (see "Round 2 progress" above):**
1. The 2 package-M on-call test failures: **leave them, do not fix** (owner declined). The earlier claim in this file
   that they "will pass the next day" was wrong — they fail on every run, forever, until the seed sets an explicit
   `valid_from`; the owner chose not to spend a step on it now.
2. Build the U8 parity "fix needed" items (create-patient dialog + chips, "Dịch vụ & tài chính" tab, the remaining
   Patient 360 dialogs, "Tiền sử & chẩn đoán" card): **yes → U9**.
3. Dedicated accountant role + "can the cashier approve orders" + who closes a finance period: **yes to the
   bundle, with one flagged deviation.** `Role.ACCOUNTANT` was added (U11, merged 2026-10-06) — this restores a role the old web
   already had (`staff-context.js`: `accountant`, "Đối soát & thu ngân") that the new backend had dropped in favour
   of projecting it onto `manager` (`finance.py` docstring, now reversed). Letting accountant/reception approve a
   prescription **order was NOT built**: both the old web (`order-data.js`: `'Cần bác sĩ duyệt đơn.'`, doctor-
   only, and only the assigned doctor) and the current backend enforce doctor-only order approval as a clinical
   safety rule (`AGENT.md`); removing it needs the owner's explicit, separate sign-off after reading this note, not
   a one-word "có" folded into a three-part question. Default taken for period-close: accountant closes it, owner/
   manager keep an override.
4. Reception table on `/today` + room-column grid on `/schedule`, additive (keep the current CSKH queue and
   doctor-column board): **yes → U10**.
5. Real service/price basis, the remaining 8 guide articles, photo-consent wording: owner said **"ok"**, read as
   "keep synthetic for now, real content later" — not a request to invent real-looking numbers or articles. Stays
   open (`PLAN-AI01-U.md` §6).
6. Delete superseded `prototype/*` / `finance_server.py`: **no, keep** (package W still reads them for screenshots
   and specs; already read-only by the HARD RULES).
7. Token / room hand-off / "Hỏi Pema" / photo-retention decisions: **left open** ("tạm để suy nghĩ"), not re-asked.

Housekeeping also queued (`U12`, no product decision in it): `design-specs/README.md`/`SKILL.md` stale "82-screen"/
"211 screens" wording, MCP `get_web_screen` error for a Next.js id with no snapshot, `catalog-nextjs.cjs` still
greying out `/cashier`/`/finance`, `snapshot.json` `meta.inventory_sha` hand-edit, `pending-web.cjs`/`pending.cjs`
baseline (`c40ba22` → `0c454cc`, see the history-rewrite note below), regenerating `visual-ref/old/` (empty on this
checkout), and the two dark-mode contrast failures (`surface` on `brand-500` 3.81:1, on `accent-strong` 3.44:1, both
below 4.5:1).

**History rewrite 2026-10-05 (attribution fix, same tree):** the U4-sync merge (old hash `3bc3d40`) was made by fast-forwarding `feat/ui-parity` onto a merge done on the `ui/u4-sync` worktree, which had `ui/u4-fix` (`24dfd1c`) as a parent. `ui/u4-fix` predates the earlier `filter-branch` rewrite of `feat/ui-parity` (see the attribution note above), so merging it pulled back ~90 pre-rewrite commit hashes, including the one with a `Co-Authored-By: Claude` trailer. Fix: `git replace --graft 3bc3d40 649940d` (the W12 merge, 3bc3d40's other, post-rewrite parent) then `git filter-branch -- 649940d..feat/ui-parity` to make it permanent; the `649940d..HEAD` tree is byte-identical to before (`git diff` empty), only commit hashes from U4 on changed. New hashes: `3bc3d40`→`ff14ecf`, `22df969`→`0f78638`, `9281762`→`fa3a6a2`, `142800b`→`34ff3c1`, the docs commit (old `2415cd7`) → `84757b9`. Verified after rewrite: `f6be3b9` is not an ancestor, 0 attribution trailers in the whole branch history. Backup of the pre-fix tip: local branch `backup/ui-parity-before-graft` (never push). `origin/feat/ui-parity` still has the old history (through U5, pushed 2026-10-05 17:43) until the user allows `git push --force-with-lease=feat/ui-parity:<old tip> origin feat/ui-parity`.

Lesson from round 2: a migration that changes a CHECK constraint must be tested with a downgrade while rows that use the new value exist (the seed adds an accountant); if the full gate is skipped, still run `tests/care/test_care_schema.py`, `tests/test_database.py` and every test that calls `downgrade(`. Leftovers to know: a Docker container `pema-pg-u6` (throwaway Postgres from the U6 agent) was still running on 2026-10-06 and was not removed; `git stash list` has one old entry (`codex/catalog-orders-a5` WIP, 13 days old) that is not from package U.

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

## Package W — design of the old Pema web: screenshots, screen specs, web canvas (BUILT 2026-10-04: 211 screens incl. Patient Mobile; merged into `feat/ui-parity` and pushed; W5 push to claude.ai/design optional)

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

Known gaps (2026-10-04):
- Empty-state texts with no scripted state in the old web were not given ids ("Inbox đã sạch", "Không còn việc CSKH mở", "Đã xếp hết danh sách chờ", `#crm-error`, booking rule errors); native confirm/prompt/print dialogs are only described in notes.
- 390 top-bar title still truncates on long page names; `.k-stack>.bt` selectors share the `display:contents` flaw.
- Kit gaps vs `pema-agent/frontend/src/ui` (hero, timeline, board, weekGrid, a5, photos, avatar, …): listed in `blocks-web.md`.
- `design-specs.cjs --check` fails on this clone because git-ignored `pema-kmp/design-ref/*.png` are absent (not CRLF); `pending.cjs` needs baseline commit `1564115`.
- `feat/web-design` is merged into `feat/ui-parity` (pushed). Branches `design/*`, worktrees `C:/wt/*` and `feat/web-design` still exist locally; nothing was deleted.
- The 1150 PNG shots in `visual-ref/old/` and `pema-agent/infra/.env` are git-ignored: they exist only on this machine.

### Progress log

| Step | Branch / commit | Merged as | Gate result | Notes |
|---|---|---|---|---|
| W0 inventory + skill skeleton | `design/w0` `072e457`+`bfcd847` | `17c36fb` | `web-inventory.cjs --check` 0 twice; scope clean | 81 ids (14 page, 11 tab, 6 modal, 13 dialog, 37 state), 8 groups, 132 entry points; clock 2026-09-20, role owner-tam |
| W1 old web shots | `design/w1` 4 commits | `b460eb2` | 405 shots (81×5) + 80 legacy + 10 print; 0 page errors | agent stopped by director after ~2.5 h (single browser, flaky `http.server`); finished state verified; PNGs git-ignored, in main checkout `pema-agent/frontend/visual-ref/old/`; manifest SHAs re-synced from disk (112 had drifted) |
| W2 specs + MCP | `design/w2` 6 commits | `8a966e1` | `web-specs.cjs --check` 0 (81 specs, 0 missing); `get_screen("A1")` byte-identical | 4 MCP tools + resource + prompt added; 55 unmatched colours |
| W3a canvas foundation | `design/w3a` `168d15a`+`e35f1c3` | `02793f7` | `web-canvas-build.cjs --check` 0; WA1+WB1 proof | canvas generated from `parts/*.js` so 8 agents can work in parallel |
| W3b WA…WH (8 agents) | `design/w3b-wa` … `w3b-wh` | `9a1fe5d` WA, `43555e0` WE, `58ae88a` WD, `bd64183` WH, `77cae65` WG, `768912a` WF, WB, `453e114` WC | each group `--complete` check 0 | `notes.json` conflicts resolved by structured JSON merge |
| W3c template fixes | `design/w3c` | `c40ba22` | all 81: errors/overflow/unresolved/missing empty; `web-specs --check` 0; 154 `demo_data` exemptions → 0 | bell by role, money nowrap, hero actions, dialog close label, table row variants, card tint, board buffer, notice bullets |
| W4 skill, docs, audit | `design/w4` 6 commits | merge on `feat/web-design` | inventory/specs/canvas/coverage all 81; counts table equal | `pema-web-design` SKILL.md, `coverage-web.md`, `web-design-changes.md` + `pending-web.cjs`, CLAUDE.md section, `design-specs/README.md` row, SECTION_PROGRESS |
| W6a gap audit: Patient Mobile web (group WI) + every parked state | `design/w6a` 4 commits | merge on `feat/web-design` | `web-inventory.cjs --check` 0 (4 min 33 s): 211 ids (+130), static guard 0 unclaimed of 226 UI items (before: 123) | owner rule repeated 2026-10-04: no screen may be missing; WI = 42 Patient Mobile ids (9 pages, 9 next-step cards, empty/toast/error/approved/pending variants); 11 `non_screens` each proven unreachable by a grep; native confirm/prompt/print/download/select get ids with `native_dialog` |
| W6b shots (4 agents) + specs (3 agents) for the 130 new ids | `design/w6b-shots-a…d`, `design/w6b-specs-1…3` | merged; manifest and snapshot/notes merged by script (`web-snapshot.cjs --merge=`) | manifest 1150 rows, 1150 PNG on disk, SHA 0 mismatch; `web-specs.cjs --check` 0 (211 specs, 0 missing) | each agent used its own old-web server (4173, 4175–4180); PNGs copied into the main checkout folder; `web-shots.cjs` records `native_dialog` messages |
| W6c-0 phone frame + Patient Mobile blocks | `design/w6c0` | `88bdfcf` | proofs WI1, WI9, WI23 | `mob()` 390×844 frame, `native()` dialog frame, `errLine`, blocks appt/events/bubbles/upload/stepper/quick/rx |
| W6c frames for 130 new ids (5 agents: WI-1, WI-2, OPS, REST-1, REST-2) | `design/w6c-wi1` … `rest2` | `f00e068` | **all 211 ids**: `web-canvas.cjs check … --complete --viewport=all --frames` exit 0, total 211/211, 263 frames, errors/overflow/unresolved/missing empty; `web-specs.cjs --check` 0; `web-coverage.cjs --check` ok (1150 files) | one-line fix in `canvas-layout.cjs` (dialog toast listed in Layout) |
| Local viewer (Docker) | `feat/web-design` | — | image builds, `http://127.0.0.1:4191/` serves `Pema Web.dc.html` (462 KB), 0 page errors | `docker compose up -d --build pema-web-design-viewer` from the repo root; `design-viewer/Dockerfile` takes `CANVAS_DIR` (default app canvas, port 4190); the "Pema Web" tab is next to "Pema Web blocks" |

| W5 push to claude.ai/design | — | — | — | OPTIONAL now (only to share on claude.ai): needs the user to create the project and run `/design-sync`; see `recipes/W/07-W5-push-design.md` |

## Session log 2026-10-04 (after package W)

- **Rebase of `feat/single-tenant` onto master `073b21f`** (tree of `feat/ai-agent-backend`): conflicts resolved in `kb_ingest_worker.py`,
  `router.py`, `openapi.json`, the care package files, frontend live files and three docs. The resolved tree differed from the old
  tip `4296064` in 11 files (two live tests were lost); the fix-up commit restores them, so the tree equals `4296064` (checked with
  `git diff`). PR #11 merged into `dev` as `e972af3`; `origin/feat/single-tenant` = `3493f10`.
- **Attribution fix:** the "package M" commit lost its trailer by an interactive reword (script dropped lines with
  co-authored-by / claude / anthropic / generated with). Check over `073b21f..HEAD` = 0.
- **`feat/ui-parity` and master:** `pull --rebase origin dev` replays the old single-tenant commits (old hashes) and conflicts.
  Do not use it. Because `e972af3` has the same tree as `4296064`, the branch took `git merge -s ours e972af3`
  (`8ab9faa`, pushed): tree unchanged, history contains master. Backup of the tip before this: local branch
  `backup/ui-parity-before-rebase`. Not run on the rebased branches: backend pytest/ruff (this machine has no `uv`) and the frontend gate.
- **Design gate for the frontend (uncommitted at the time of writing):** `CLAUDE.md` and `AGENT.md` carry the same "Screen specs" and
  "Web design canvas" sections; the web canvas rule is now MANDATORY for `pema-agent/frontend/src/{app,ui,components}` (read spec and
  canvas image first, new `pnpm visual` shot compared with canvas and old shot, ids named in the report). New agent
  `.claude/agents/pema-ui-builder.md`. New git hook `.githooks/pre-commit` runs `pending-web.cjs` and blocks a commit with
  `✗ NOT LOGGED`; each clone must run `git config core.hooksPath .githooks` once (already set on this machine). The hook cannot
  check that an agent really compared the images; that depends on its report. Screen counts in the docs now say 211 (was 81).
- **Open:** force-push of the cleaned `feat/ui-parity` (see HARD RULES); cleanup of worktrees and `design/*` branches;
  run lint and tests on the merged branches.

## Package W2 — design the Next.js-only screens, one Design System, one claude.ai/design project (BUILT 2026-10-05: W7–W12 merged into `feat/ui-parity`, NOT pushed)

Result: web inventory 384 ids (WA–WI 211 old web, WJ 115 / WK 39 / WL 19 Next.js-only = 173); two canvas files `Pema Web.dc.html` (211 ids, 263 frames) and `Pema Web (Next.js).dc.html` (173 ids, 251 frames) + `Pema Web blocks.dc.html`; viewer dropdown Web cũ / Màn mới / Cả hai; `design-system/` (tokens.json, colors.md, typography.md, 64 component pages, `check.cjs` 8/8); hub `design-specs/INDEX.md` = app 82 + web 384 + Design System with the two-way app↔web table, built by `unify-index.cjs` (app tool `design-specs.cjs` keeps it through a 12-line hook in `specs-lib.cjs`, owner accepted 2026-10-05). Merge commits: W7 `7154edd`, W9 `dc6952a`, W8 `c55f047`, W10 `ec33103`, W11 `ef30d4a` (retry 1), W12 `649940d`. Nothing published to claude.ai/design.
Pitfall: `web-specs --check` once depended on git-ignored PNGs on disk (image lines), fixed by regenerating in a checkout without PNGs; the app tool `design-specs.cjs` has the same dependence on `pema-kmp/design-ref/` (run `gradlew canvasRefs` in a fresh worktree). On Windows (`autocrlf=true`) `design-specs.cjs --check` reports "out of date" until `design-specs.cjs` is run once; that produces no git diff.
Outside write list, still open: `design-specs/README.md` calls INDEX.md the "82-screen list"; SKILL.md body says "211 screens"; MCP `get_web_screen` throws for Next.js ids without snapshot (`pema-design-mcp.cjs` line 161); dark-mode contrast misses (surface on brand-500 3.81:1, surface on accent-strong 3.44:1); owner decisions on tokens (ink-soft/danger vs old values).

Check result 2026-10-05: the web canvas covers the old web completely (211 ids WA–WI, specs and frames consistent), but
by decision D3 **no Next.js-only screen is designed**: `/admin/*` (26 routes), `/care/*` (5), `/templates`, `/login`
(~33 routes, ~70–100 frames with states/dialogs). No Design System artifact exists. The account has **no published
artifact** (neither canvas is on claude.ai/design). App canvas (82) and web canvas (211) are separate files with no
reverse index.

Owner decisions 2026-10-05: (1) Patient Mobile web (group WI, 42 screens) is dropped as a Next.js target — designs stay
for KMP/Zalo, INDEX rows marked `served by KMP/Zalo`; revisit as a Zalo-opened web only when a Zalo OA exists.
(2) Publishing to claude.ai/design is **deferred** until the owner asks; W2 stays in the repo. (4, 2026-10-05) **Old-web canvas stays pure**: WJ/WK/WL frames go to a separate `Pema Web (Next.js).dc.html`; the local viewer gets a dropdown "Web cũ" (default) / "Màn mới" / "Cả hai". W10 worktrees in flight keep writing `parts/*`; the director applies the two-file build and the viewer dropdown when merging W10 (recipe `04-W10` updated). (3) Keep two canvas files; unify through one
Design System source and one cross-index (`design-specs/INDEX.md`).

Where: plan `pema-agent/docs/PLAN-AI01-W2.md`; recipes `pema-agent/recipes/W2/` (`00-README.md`, `_REPORT-TEMPLATE.md`,
`01-W7` inventory → `02-W8` shots ‖ `03-W9` specs → `04-W10` frames+blocks → `05-W11` design-system source →
`06-W12` unify). No publish step. Reuses package-W scripts in `.claude/skills/pema-web-design/scripts/`.
Writes only to `design-specs/`, `Pema Web redesign canvas/`, new `design-system/`, that skill folder, and `pema-agent/docs|recipes`.
No FE/BE code changes; U0/U1 implement the new blocks from `BLOCKS.md`.

How to run (when the user says so): branch `feat/ui-parity`; one `pema-builder` per recipe in its own worktree; prompt
"Follow pema-agent/recipes/W2/<file>.md on branch feat/ui-parity. Return the report in _REPORT-TEMPLATE.md format."
Gate: `web-inventory.cjs --check` 0; `web-canvas.cjs check --complete --viewport=all --frames` 0 for all ids;
`web-coverage.cjs` counts equal; viewer 0 page errors; no attribution in commits. Merge into `feat/ui-parity` only.

## Package O — one identity, many operators: shared inbox over Zalo (BUILT 2026-10-06 on `feat/shared-inbox`: O1–O7 merged, NOT pushed, NO director-run gate; details in "Result of package O" below)

Branch `feat/shared-inbox`, created 2026-10-06 from `feat/ui-parity` `0d7bfda7` (M, U0–U12, W, W2 included). v1 of
the plan (branch `plan/package-o` `b2fecd6`, 2026-10-05) is superseded; keep that branch, never build from it.

Owner decisions 2026-10-05 (unchanged): customers talk only to clinic identities ("Long" on Zalo; a Facebook Page
later); staff never message customers from personal Zalo, they reply only inside Pema; personal Zalo is a notification
bell. (1) Outgoing text shows only the identity. (2) Takeover allowed; previous and new operator both notified.
(3) KMP push primary, personal Zalo fallback, Zalo team group broadcast. (4) The 24/7 on-call number stays.

Why v2: v1 assumed tables and wiring that do not exist. Checked in the code (full list in `PLAN-AI01-O.md` §2):
channel accounts already exist (`agent.accounts`, `/admin/accounts`); limits are per channel (`clinic.channel_setting`),
so O1 adds per-identity overrides; `clinic.conversation` has `assigned_user_id` but no account id, so O1 adds
`account_id`; `message.sender_user_id` already records the sender; package M is built but NOT wired, so O builds M's
`StaffNotify`/`SlaScheduler` adapters and a claim↔`CareControl.accept` bridge while the care loop itself stays M7;
`pema-kmp` has no push code, so the live chain in O is in-app → personal Zalo (internal notifier account) → team group,
with push ready behind a fake provider until FCM/APNs credentials and a KMP step exist; UI must be design-first (AGENT.md),
so O gets a design step (group WM) before the FE step.

Where: plan `pema-agent/docs/PLAN-AI01-O.md`; recipes `pema-agent/recipes/O/`: `01-O1` identities, limits, roster →
`02-O2` assignment, lock, takeover → (`03-O3` notifications ‖ `04-O4` outbound as identity ‖ `05-O5` design) →
`06-O6` FE shared inbox (`pema-ui-builder`) → `07-O7` eval, docs, AGENT.md rule. Migrations `o<step>_*` on the single
head. New BE package `pema/notify`; seams in `pema/clinic/actions`, wiring in `pema/composition`.

Defaults until the owner answers (`PLAN-AI01-O.md` §7): roster entered in Pema; managers may read threads silently
(presence "đang xem"); team group id and internal notifier account are config (step skipped and logged when unset);
push provider fake; ack timeout 3 minutes; Facebook is package F.

How to run (when the user says so): switch the main checkout to `feat/shared-inbox` (tree clean); first run the full
gate once on the branch base and record it (U9–U12 were merged without a gate); then one subagent per recipe in its own
worktree from the current branch head; gate before each `--no-ff` merge; merge into `feat/shared-inbox` only; never
push unless asked. Expected baseline failures: the 3 clock-dependent tests in `tests/care/test_care_routing_store.py`.

### Result of package O (2026-10-06, all 7 steps merged into `feat/shared-inbox`, NOT pushed, NOT gated)

**Read this first.** After the baseline gate the owner told the director to skip gates ("bỏ qua xử lý cổng nền", then "viết test nhưng tạm chưa cần chạy pass"). From O1 on, the director ran **no** pytest, no vitest, no `pnpm visual`/`build`/`smoke`, no `web-*` gate on any step. Before each merge the director only checked: one alembic head (read from the `down_revision` chain), no conflict markers, no AI attribution in commit messages, `openapi.json`/`schema.d.ts` consistent (no path or schema removed), and for O5 that `Pema Web.dc.html` is byte-identical. Every test number below is what the step's own agent reported, not a director-run result. Many DB-backed tests were written and never run.

**Branch state.** `feat/shared-inbox` = `1f12ab7d`, created from `feat/ui-parity` `0d7bfda7`, plan commit `df277b3a`. **19 commits ahead of `df277b3a`.** The branch does not exist on `origin`; nothing was pushed. Attribution check `git log --format=%B df277b3a..HEAD`: 0 lines.

**Baseline gate (step 0, director-run, on `df277b3a`, before the owner said skip):**
- BE: ruff check clean; ruff format 1063 files clean; pyright 0 errors; import-linter 4 kept / 0 broken; alembic head `u9_0010_patient_parity`; pytest **5722 passed, 10 skipped, 4 failed** (1206 s). The 4 failures: the 3 clock-dependent care tests in `tests/care/test_care_routing_store.py` (owner declined to fix) plus `packages/contracts/tests/test_contracts.py::test_roles_are_the_six_fixed_ones` (asserts 6 roles; U11 added `accountant` as the 7th and did not update the test — a second regression of the ungated U9–U12 round; fix = add `"accountant"` to the set and rename; the owner was asked and did not answer, so it is still red).
- FE: `pnpm test` 1195 passed in 126 files; lint, `check:types`, `build` exit 0; `pnpm inventory` 58 routes / 149 test ids green; `pnpm visual` 335 screens, 0 overflow, 0 failing; `pnpm smoke` failed once while the machine was loaded (BE pytest and build ran at the same time) and passed alone: 55 routes, 0 problems.
- Baseline containers were removed.

**Merges (order of completion; O3 was merged after O4):**

| Step | Branch / agent commit | Merge commit | What the agent reported (not director-run) |
|---|---|---|---|
| O1 identities, limits, roster | `o/1` `8797ee56`, follow-up `37d06103` (schema.d.ts) | `6ed4b189`, `f7d0a397` | one full pytest mid-step before Docker broke: 5820 passed, 4 failed (the same 4 as baseline), 10 skipped; the 6 new ops test files passed in that run, then only comment/line-wrap edits; schema.d.ts paths 184 → 189, schemas 276 → 285, none removed |
| O2 assignment, lock, takeover | `o/2` `9107594a` | `253c4055`, types `1b7fa574` | ruff/pyright/import-linter clean, 17 no-DB tests passed; **DB tests written, never run** (`test_o2_assignment`, `test_o2_migration`, `test_o2_care_bridge`, `test_o2_live`); schema.d.ts +6 paths, +6 schemas |
| O4 outbound as the identity | `o/4` `31da745b` | `c4a4c5ff` | 21 + 18 no-DB tests passed; ruff/pyright/import-linter clean; **10 DB tests never run** (`test_o4_outbound_action`); no migration; schema.d.ts: only `no_identity` added |
| O3 notifications | `o/3` `c9ac4d24`, sync `7ea424d7` | `7208b63c` | 44 no-DB tests, 65 after the O4 sync, passed; ruff/pyright/import-linter clean; **DB tests never run** (`test_o3_actions`, `test_o3_migration`); schema.d.ts +9 paths, +12 schemas |
| O5 design | `o/5` `29ea0921` | `82198f16` | tool checks by the agent: web-inventory 0 (435 ids), web-specs 0 (only with PNG placeholders), web-canvas check 0 (224 screens, 310 frames), web-canvas-build 0, coverage 0; director re-checked: old canvas diff empty, canvas-build and unify-index OK |
| O6 front end | `o/6` `9e9c7bfc`, notes `ef557542` | `97e20580` | vitest 683/684 on the touched files (the 1 failure, a date format in `notify-view`, fixed and its file re-run 5/5, the rest not re-run); tsc, eslint clean; inventory 60 routes / 157 ids; smoke 4 routes 0 problems; visual on 4 routes at 1440 and 390: 0 overflow; `pending-web.cjs` no NOT LOGGED; two-browser takeover run on the **mock only** |
| O7 eval, races, security, docs | `o/7` `9917c8db` | `1f12ab7d` | `evals/ops` on a throwaway Postgres: 92 passed, 1 xfailed, 0 failed (no-DB: 76 passed, 17 skipped); ruff/pyright strict on evals clean; the existing `tests/ops`, `lint-imports`, full BE and FE suites **not run** |

Alembic chain: `u9_0010_patient_parity` → `o1_0010_identities_roster` → `o2_0010_assignment` → `o3_0010_notifications` (one head). O4–O7 added no migration. All downgrades target a named revision.

**What each step built**
- **O1**: `agent.accounts.purpose` (customer | internal, CHECK) and per-identity overrides `send_gap_min_s`, `send_gap_max_s`, `daily_cap` (NULL = channel row); `clinic.conversation.account_id` with a composite FK and two triggers (a conversation never points to an internal account; an account with conversations cannot become internal); backfill only where exactly one customer account of the channel has a matching `agent.threads` row (real counts not measured, the migration logs them); `clinic.account_roster`; `staff_profiles.notify_zalo_user_id` / `notify_zalo_consented_at`; 9-argument `record_inbound_message` that fills a NULL account and never overwrites; actions `identities.py`, `roster.py`; routes `GET/PATCH /identities`, `GET /identities/{id}/on-duty`, `GET/POST/PATCH/DELETE /roster`; permissions `identity.manage`, `roster.manage` (owner, manager), `roster.read` (owner, manager, doctor, cs_staff); `composition/roster_routing.py` (`RosterRoutingDirectory`) ranks rostered operators first, on-call stays last (M has two `Ownership` slots, so only one doctor and one other operator rank first, labelled `cs_owner`/`treating_doctor`).
- **O2**: `conversation.assignment_version`, append-only `clinic.conversation_assignment` (takeover needs a reason, CHECK), `clinic.notification_outbox`; actions claim, takeover, release (to the queue or `to_agent` through a `CareHandback` seam), assign, `end_shift`, history; `send_message` refuses a non-holder with 409 `thread_locked`; live event `assignment.changed` (carries only the conversation id); permissions `thread.claim`, `thread.assign`, `thread.end_shift`; routes `POST /conversations/{id}/claim|takeover|release|assign`, `GET /conversations/{id}/assignments`, `POST /staff/{id}/end-shift`; `composition/care_assignment.py` (`CareAssignmentBridge`: M's accept → claim, M's release → release). Accountant and reception never hold a thread. **Decision taken by default (not in PLAN §7):** the first reply on an unassigned thread auto-claims it (the literal recipe would have broken replying on every unassigned thread).
- **O4**: `pema/channels/identity_send_queue.py` (shared per-identity gap; a proactive message also takes one slot of the identity's daily cap, key `identity:<account>`; the kill switch blocks everything including replies; a Redis outage fails open like the scheduler gate); `outbound.py` resolves the identity (conversation account, else the channel's single enabled customer account, else the message stays `queued` with `no_identity`, 409); internal accounts refused (`policy_denied`); send-time re-check of the lock (old holder → `rejected`, `thread_locked`); text sent unchanged (no signature); `external_message_id` stored (first part id), status `sent` (no `delivered` state).
- **O3**: `pema/notify/` (consumer, providers, internal sender, link code, `OutboxStaffNotify`, `DurableSlaScheduler` + `SlaCheckRunner`); migration adds outbox retry/lease/ack columns and the tables `notification_log`, `push_token`, `notify_setting`, `notify_preference`, `notify_link_code`, `sla_check`; routes `GET /me/notifications`, `POST /notifications/{id}/ack`, `POST /notifications/ack`, `POST/DELETE /me/push-tokens[/{id}]`, `GET/POST/DELETE /me/notify-zalo[/link]`, `GET/PUT /me/notify-preferences`, `GET/PUT /notifications/settings`; permissions `notify.self` (owner, manager, doctor, cs_staff), `notify.manage` (owner, manager); live event `notifications.changed`; the O3 notice DTO is `NoticeOut` (it first collided with the finance `NotificationOut`, which FastAPI then renamed; fixed). A 5 s loop runs in the API process.
- **O5**: group **WM**, ids **WM1–WM51**, Next.js-only, in `Pema Web (Next.js).dc.html` (224 screens now, 310 frames); WM1–WM23 Inbox (tabs Chờ nhận / Của tôi / Tất cả, identity filter, holder banner, composer lock, dialogs Nhận / Tiếp quản / Trả lại / Giao cho / Lịch sử, toast, 409/403/501 states), WM24–WM29 `/admin/accounts`, WM30–WM41 `/admin/roster`, WM42–WM51 `/me/notifications`; catalog flags `planned` and `planned_route` added to the web tooling (O6 dropped `planned_route` for its pages); group letters A–L became A–M in the scripts; `Pema Web.dc.html` and `Pema Web blocks.dc.html` unchanged.
- **O6**: `/inbox` (tabs with counts, identity filter, URL state `?tab=`, `?identity=`, `?c=`, deep link `?conversation=`, holder banner, the five dialogs, locked composer, `thread_locked` keeps the draft, `no_identity` has its own sentence, live `assignment.changed` with the "Đã bị tiếp quản" toast, a role without `thread.claim` sees one sentence), `/admin/accounts` additions, new `/admin/roster` and `/me/notifications` (+ gear link in the top bar), kit: `Tabs` `segmented` mode, `TopBar` `notifyHref`; mock handlers for everything. No backend change. Built: WM1–WM47 and WM49–WM51; WM48 only partly.
- **O7**: `pema-agent/evals/ops/` (`run_eval.py` → `report.md`, `measure_*`, `invariants.py`, `test_ops_eval.py`, `test_ops_races.py`, `test_ops_security.py`); docs `ARCH-AI01` §16, `CONTRACTS-AI01` §12, `SECURITY-REVIEW-AI01` §11 (SEC-64 … SEC-78), `pema-agent/README.md` (operator onboarding), and the **AGENT.md rule**: "Staff never contact patients from personal accounts; all customer messaging goes through Pema identities; personal Zalo only receives PII-free notifications." `evals/ops/report.md` §6 is the HANDOFF-ready list for M7 and the KMP push client.

**O7 measured numbers** (real Postgres; queue and chain on a virtual clock with fakes — Zalo, push-service and bridge network time are NOT measured; scenario limits are the eval's parameters, not clinic settings): 1000 claim attempts over 200 threads → 200 won, 800 `thread_locked`, every thread exactly one holder, 0 SQL invariant violations (wall 4.2 s; claim p50 17.3 ms / p95 23.5 ms; reply p50 29.4 / p95 37.2 ms); 0 gap violations over 260 + 30 + 260 sends; the personal-Zalo bell rang for 0 of 113 acknowledged notices and 87 of 87 unacknowledged; 0 of 307 notice texts failed the PII mask; the 24/7 on-call contact was reached in 12 of 12 no-acceptance cases and 0 of 9 accepted ones; 0 model calls.

**Package M ports: what O built and what is still M7.** Built in O, tested only against M's fakes, and **not registered in the care loop**: `StaffNotify` (`OutboxStaffNotify`), `SlaScheduler` (`DurableSlaScheduler` + runner; M7 must pass `RoutingService.on_sla_expired` as `sla_handler` and use `stack.staff_notify`/`stack.sla_scheduler`), the `RoutingDirectory` roster adapter, and the `CareAssignmentBridge`. Until M7 the checks wait in `clinic.sla_check` and M's `sweep_overdue` is the backstop. Still without a production adapter: `ChannelSend`, `RoutingAdvance` and the other M ports listed under "What is NOT wired". The care loop itself, KMP push and the real-model run stay out of O.

**The notification chain as it really works today.** Live path: in-app notice (SSE) at once → personal-Zalo bell through the internal notifier account after `ack_timeout` (default 180 s) unless acknowledged or in quiet hours (an `urgent` notice still rings) → team-group post once → the 24/7 on-call number rung directly for handoffs nobody accepts; bounded retries 20/40/80 s, max 3, one log row per attempt with latency. **Push is still fake**: `FakePushProvider`, and the FCM/APNs provider refuses to start; `pema-kmp` has no push code; the API does not wire a push provider (the step logs `provider_disabled`). Notices carry no PII (short code, identity label, urgency, templated one-liner, deep link `/inbox?conversation=<id>` or `/care/handoffs?request=<id>`). An acknowledgement does **not** stop M's SLA or accept a handoff; only M's accept/decline does. The team group id, the internal account and the public base URL are config; the step is skipped and logged while unset.

**Defect found, not fixed — SEC-64.** The same `Idempotency-Key` sent again while the first send is still in flight stores one message but delivers it twice (`--runxfail` gives `assert 2 == 1`). It is a strict xfail in `evals/ops/test_ops_races.py` (it will turn red when fixed — then remove the marker). Fix: claim the row (`queued` → `sending`) before the channel call, in `pema/clinic/actions/outbound.py`. O7 was not allowed to edit actions.

**Other security-review findings, all open:** SEC-65 staff can still message customers from personal Zalo outside the system (training, not code); SEC-67 the PII mask flags a 12-digit run and a UUID's last group is all digits about 1 time in 280, so the mask runs on summary and label, not on the link line; SEC-75 unverified whether the Zalo bridge can `send_text` to a phone number (the on-call ring needs it; if not, a uid lookup is needed); SEC-76 O4's per-identity daily cap is not merged with package S's per-job cap; SEC-77 a doctor cannot see or claim an unlinked customer's thread.

**Open items.** (1) Full gate never run on O1–O7. (2) `test_roles_are_the_six_fixed_ones` red since U11. (3) FE: the queue tab and identity filter work only on the first 100 loaded rows because `ConversationSummary` has no `account_id` and `GET /conversations` has no account or unassigned filter (BE follow-up: `account_id` in the DTO plus `unassigned` and `account_id` filters). (4) The push card always reads "Chưa đăng ký" (WM48): there is a POST/DELETE for push tokens but no GET to list devices and no "test notification" route. (5) The old "Phụ trách:" picker and "Nhận xử lý" button are gone for every role (O5 design): a role without `thread.assign` can no longer hand a thread to a colleague — the owner has not confirmed that cs_staff and doctor lose this. (6) The bell link handler runs only in the API process; a polling bot in the worker drops internal-account messages (logged), so the internal account must use webhook or the bridge. (7) The SLA checks live in `clinic.sla_check`, not on `pema.scheduler` (a deviation: `agent.jobs` is bound to an account and thread and has no callback kind; moving them needs a new `JobKind` in package S). (8) The real-stack two-browser takeover run was never done (mock only). (9) `web-specs.cjs --check` reports 211 old-web specs out of date in any checkout without the git-ignored PNGs (inherited from U12, which regenerated the specs in a worktree that had 1150 PNGs); O5's specs pass only with empty placeholder PNGs; do not regenerate specs in a checkout without PNGs. (10) The WM fields that depend on O3 (WM25, WM29, WM42–WM51) are marked provisional in `notes.json` until compared with the O3 DTOs; that comparison was not done. (11) A doctor-on-roster rule is open (SEC-77).

**Owner decisions needed.** Confirm that cs_staff and doctor can no longer assign threads to colleagues; whether doctors on the roster should see unlinked customers' threads; fix `test_roles_are_the_six_fixed_ones`?; FCM/APNs credentials and the KMP push client; the team group id, the internal notifier account and the public base URL; whether the SLA checks should move onto `pema.scheduler`; training against personal-Zalo contact (SEC-65). Defaults still in force from PLAN-AI01-O §7: roster entered in Pema; managers may read threads silently (presence "đang xem"); ack timeout 3 minutes; push fake; Facebook is package F.

**Deviations from the owner's command (all disclosed to the owner).** The baseline gate found one red test beyond the 3 expected; the command said to stop and report before O1, the director reported but started O1 in parallel when told to skip the baseline. The owner then skipped gates, so no step was gated. Every subagent prompt was the fixed sentence plus extra lines (worktree path, own ports, "no Docker", "write tests but do not run them", "no gen:types" at first). O1, O3 and O6 were resumed several times (session rate limit, "Not logged in", session restart, Docker 500); O3 got one extra sync job with O4; no step exceeded 2 retries. Edits outside the O README write list were accepted: `contracts/{errors,live,conversations}.py`, `clinic/models/inbox.py`, `_mappers.py`, `live_access.py`, `api/router.py` (O2), `contracts/errors.py` (O4, `no_identity`). `record_web_note` from the O6 agent wrote its notes into the main checkout; the director committed them as `ef557542` and reverted an accidental `web-specs.cjs` regeneration (275 files) that the missing-PNG pitfall caused.

**Leftovers.** Worktrees `.claude/worktrees/o-1` … `o-7` and branches `o/1` … `o/7` (all merged, safe to delete once the user agrees). No Docker containers of package O remain. The machine was slow and Docker Desktop was restarted during this package; `git`, `uv` and `pnpm` were sluggish with many worktrees on disk. Still on disk from earlier packages: the `feat/ui-parity`, `ui/*` and `w2/*` branches and about 60 worktrees; `git stash list` has one 13-day-old entry from `codex/catalog-orders-a5` that is not ours.

**Next steps (in this order).** 1. Run the full gate on `feat/shared-inbox` `1f12ab7d` now that Docker works: BE ruff/format/pyright/import-linter, full pytest on a throwaway `pgvector/pgvector:pg17 -c fsync=off` + `redis:7` with `PEMA_TEST_DATABASE_URL`/`PEMA_TEST_REDIS_URL`, `alembic heads` = 1; FE `pnpm test`, `lint`, `check:types`, `inventory`, `build`, `smoke`, `dev:mock` + `pnpm visual`; expected failures are only the 3 clock tests and, until fixed, the roles test; run `tests/ops`, `tests/clinic` and `tests/live` explicitly (O2 changed the send path, the PATCH assign and the viewers list). 2. Fix SEC-64 (one small step), then the roles test. 3. Ask the owner the decisions above. 4. Small BE follow-up for the inbox filters and the device list. 5. M7 wiring, then the KMP push client. 6. Push only when the owner asks.

## CRM idea tooling (a second person, own Claude account, shapes CRM ideas; written 2026-10-06, committed locally as `178c9fe9`, NOT pushed)

Purpose: someone else proposes CRM ideas and proves them on a copy of the old web; the owner of the new system
(Python + Next.js) reads the result and decides how to port it. That person never turns an idea into `pema-agent/` code.

Where things are (decision of the owner: Claude config lives in `.claude/`, idea records at the repo root, the lab copy
only on its own branch):
- `.claude/skills/crm-idea/SKILL.md` (`/crm-idea`): dialogue and hand-over; checks it is on `crm/ideas`, asks until
  `IDEA.md` is clear, delegates the build, sets status `sẵn sàng xem`; refuses to port into the new system.
- `.claude/agents/crm-lab-builder.md`: builds one idea in `crm-lab/` (before/after shots with `crm-lab/tools/shot.cjs`,
  fills `CHANGES.md`); edits only `crm-lab/` and the idea folder; does not commit.
- `.claude/rules/crm-ideas.md`: no edits to `prototype/`; no porting into `pema-agent/` without the system owner's
  written request in `PORT-NOTES.md`; no commits on `feat/*`, `master`, `dev`; names free; no AI attribution.
- `crm-ideas/` (repo root): `README.md` index, `_TEMPLATE/{IDEA,CHANGES,PORT-NOTES}.md`; one folder per idea, any name.
- `crm-lab/` (editable copy of `prototype/`: web on 4177, finance on 4176, own `.local/crm-lab-finance.sqlite3`) exists
  ONLY on branch `crm/ideas` (pushed, tip `7563320a`, 2 commits on `0d7bfda7`).

What happened: a first version put everything (including `crm-lab/`, CLAUDE.md and HANDOFF changes) on `crm/ideas`;
cherry-picking it onto `feat/shared-inbox` conflicted in HANDOFF.md and the owner wanted the sandbox files out of the
code branch, so the copy on `feat/shared-inbox` (`82c7f44d`, never pushed) was deleted with `git reset --hard 7fb7e761`
(still in the reflog) and the config was rewritten into `.claude/`. The owner committed the 7 files himself as
`178c9fe9` "Rules for CRM idea" on `feat/shared-inbox` (not pushed); only this HANDOFF section was still uncommitted.

Open: `crm/ideas` still has the older skill text and a CRM section in its own `CLAUDE.md`/`HANDOFF.md` — sync it with
the `.claude/` files above when the owner says so (copy the three files, drop the CLAUDE.md section). Add the other
person as a collaborator and tell them to `git switch crm/ideas`, then run `pnpm install` and
`npx playwright install chromium` once in `pema-agent/frontend` (the shot tool finds Playwright there), then `/crm-idea`.

## Next Steps (only when the user asks)

0b. **CRM idea tooling** is committed locally on `feat/shared-inbox` (`178c9fe9`, see the section above): push when the owner asks, then sync `crm/ideas`.
0a. **Package O (shared inbox) is built but not gated** on `feat/shared-inbox` `1f12ab7d` — run the full gate first (see "Result of package O" → "Next steps"), then fix SEC-64 and the roles test, then decide the owner items.
0. **Run next:** the merge gate on `feat/ui-parity` `58243e5` (full BE pytest on a throwaway Postgres + Redis, FE `pnpm test`/`lint`/`check:types`/`inventory`/`build`/`smoke`, `pnpm dev:mock` + `pnpm visual`, `alembic heads` = 1): package U round 2 (U9–U12) was merged on 2026-10-06 without it at the owner's request. Then: owner decisions still open (real pricing, guide content, consent wording, token values, room hand-off, "Hỏi Pema" label, photo retention, whether non-doctors may approve orders), and push when the owner asks.
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
