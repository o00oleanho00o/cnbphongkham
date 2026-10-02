# CONTRACTS-AI01: contracts, ownership and conventions of the parallel packages

Written by package A. Read it after `PLAN-AI01.md` and before `PORT-MAP.md`. It is the document the 12
parallel packages (B1, B2, C1, C2, D1, D2, D3, D4, D5, S, P, E) depend on, so it states the interfaces they
may rely on, which directory each package owns, and the conventions they all follow. Anything not written
here is not a contract: ask in your report's "open items", do not guess.

Each package works in its own worktree and sees only what package A committed. The real modules meet in
package G. That is why every seam is a Protocol in `pema_contracts` with a fake in `pema_contracts.testing`.

## 1. What package A delivers (all tested)

| Area | Where | Check |
|---|---|---|
| Contracts (DTOs, ports, fakes) | `backend/packages/contracts/src/pema_contracts/` | `packages/contracts/tests` |
| Tooling | `backend/pyproject.toml`: uv workspace, ruff, pyright strict, pytest (asyncio auto), import-linter | `make lint` |
| OpenAPI skeleton | `backend/apps/api/pema/api/`; `openapi.json` committed | `tests/test_openapi_skeleton.py` (stale file fails) |
| DDL | Alembic 0001 `clinic.*`, 0002 `agent.*`, 0003 `clinic_agent.*`; roles `be_app`, `agent_worker` | `tests/test_database.py` on a clean Postgres + pgvector |
| Cross-package utilities | `pema.shared.{logger, zone_time, current_datetime, ky_tu_moi_token, safe_error_serializer, turn_log_context, db_transaction, doi_cho_den_khi}`, `pema.config.{env, runtime_tuning_settings, tuning_specs, secret_cipher}`, `pema.core.db`, `pema.channels.registry` | `tests/shared`, `tests/config`, `tests/channels` (ported tests where the original had them) |
| PORT-MAP | `docs/PORT-MAP.md`: every file of `src/`, `web/` and the rest of the clone | `tests/test_port_map.py` |
| Notices | `THIRD_PARTY_NOTICES.md` (zalo-agent and zca-js, MIT, verbatim) | |
| FE types | `frontend/src/lib/api/schema.d.ts` from `openapi.json` | `make types` |

## 2. Ownership of directories

A package creates and edits only the paths in its row (plus its own tests under `tests/<same path>`).
Everything else is read-only for it; a needed change elsewhere goes into the report as an open item.
`PORT-MAP.md` says which package owns each ported file.

| Package | Owns |
|---|---|
| A | `pema/core`, `pema/shared/{logger,zone_time,current_datetime,ky_tu_moi_token,safe_error_serializer,turn_log_context,db_transaction,doi_cho_den_khi}.py`, `pema/config/{env,secret_cipher,secret_cipher_core,tuning_specs}.py`, `pema/channels/registry.py`, `pema/bootstrap.py`, `pema/api/{router,deps,errors,export_openapi}.py`, `pema_contracts`, `alembic/versions/0001..0003`, root files |
| B1 | `pema/clinic/{domain,actions,rbac,audit,models}`, `pema/api/routers/{auth,patients,appointments,crm,conversations,review_items,admin_audit,admin_users}.py` (`admin_users.py`: `GET /admin/users` with `admin.users.read` for owner and manager; `POST /admin/users`, `PATCH /admin/users/{user_id}` and `POST /admin/users/{user_id}/password` with `admin.users`, owner only), `pema/api/{client_ip,dashboard_auth,dashboard_password_store,dashboard_session_store,dashboard_staff_store}.py` |
| B2 | `pema/clinic/crm_rules`, `pema/api/routers/admin_crm_rules.py` |
| C1 | `pema/channels/zalo_bot`, `pema/channels/oa_api.py` (stub), `pema/channels/{record_incoming_message,busy_wait_notice,payload_anomaly_watch,reply_target_tu_kenh}.py`, `pema/middleware`, `routers/{webhooks_zalo_bot,admin_bot_accounts}.py` |
| C2 | `pema/channels/zalo_personal`, the shared outbound/turn pipeline in `pema/channels/*.py` (the C2 rows of PORT-MAP), `pema/workers/turn_worker.py`, `backend/bridges/zalo-personal`, `routers/{webhooks_zalo_bridge,admin_accounts,admin_friends,admin_channels}.py` |
| D1 | `pema/agent` (not `agent/tools`), `pema/agent/providers`, `pema/config/{runtime_llm_settings,runtime_vision_settings,tuning_definitions,tuning_number_presets,env_llm}.py`, `runtime_tuning_settings.py` from A onward (DB provider, validation), `pema/shared/{log_cursor,log_file_lines,read_log_file}.py`, `routers/{admin_model,admin_usage}.py`, `evals/` |
| D2 | `pema/conversation`, `pema/config/{account_store,agent_store,accounts,parse_disabled_tools}.py`, `pema/shared/daily_task_schedule.py`, `routers/{admin_agents,admin_threads}.py` |
| D3 | `pema/knowledge`, `pema/shared/{bo_dau_tieng_viet,read_zip_entry,zip_stream_entry,xml_sax_scan}.py`, `pema/workers/kb_ingest_worker.py`, `pema/api/kb_route_guards.py`, `routers/admin_kb.py`, `kb-samples/` |
| D4 | `pema/agent/tools`, `pema/documents`, `pema/images`, `pema/video`, `pema/config/{runtime_image_settings,runtime_tool_settings}.py`, `pema/shared/{download_image,hourly_rate_limit,html_entities,html_to_text,jina_reader_fallback,private_address_guard,safe_remote_download,temp_file_store,web_search_providers}.py`, `routers/admin_tools.py` |
| D5 | `pema/mcp`, `pema/api/mcp_route_guards.py`, `routers/admin_mcp.py` |
| S | `pema/scheduler`, `pema/workers/scheduler_worker.py`, `routers/admin_schedules.py` |
| P | `pema/policy`, `routers/admin_policy.py`, the clinic cases of `evals/` |
| H2 | `pema/retention` (policy, rules, runner, schedule), `pema/workers/retention.py` (CLI `python -m pema.workers.retention`), `alembic/versions/h2_0007_retention.py`; the `retention_*` fields of `pema/config/env.py` |
| H (integration) | `alembic/versions/b1_0007_session_absolute_expiry.py` (B1), `alembic/versions/h_0008_merge_heads.py`, `infra/caddy`, `infra/docker-compose.proxy.yml`, `frontend/src/app/api/[...path]/route.ts` and `frontend/src/lib/server/api-proxy.ts` |
| E | `frontend/` (except `src/lib/api/schema.d.ts`, generated) |
| F | `infra/`, root `README.md` additions, SCOPE/SPEC/MODULEMAP/ARCH-AI01 |
| G | `pema/workers/main.py`, wiring in `bootstrap.py`, merging Alembic heads, regenerating `uv.lock` and `openapi.json`, cross-package tests |

Router files: each `pema/api/routers/*.py` has ONE owner (table above and `router.py`). The owner replaces the
`not_implemented()` bodies; changing a path, a method or a DTO is a CONTRACT change (section 8).

## 3. Contract index

All in `backend/packages/contracts/src/pema_contracts/`. "Fake" means `pema_contracts.testing` or a class
named there.

| Contract | Module | Implemented by | Used by | Fake |
|---|---|---|---|---|
| `ChannelPort`, `ChannelCapabilities`, `InboundMessage`, `SendResult`, optional `TypingChannel` / `ReadReceiptChannel` / `ReactionChannel` / `MediaChannel` / `GroupChannel` | `channel` | C1 `ZaloBotChannel`, C2 `ZaloPersonalChannel` | C1, C2, S, D4, P | `FakeChannel`, `make_inbound` |
| `ChannelRegistry` | `channel` | A `pema.channels.registry.InMemoryChannelRegistry` | S, D4 (lookups); C1, C2 (register/unregister) | the real one |
| `AgentEngine`, `AgentTurnRequest/Result`, `TurnCallbacks`, `TextGenerator` | `agent_turn` | D1 | C2 turn processor, S, D2 (summary) | `FakeTextGenerator` |
| `AgentTurnError`, `ProviderErrorKind`, `failed_turn_step` | `turn_errors` | A (done); D1 raises it | C2, S | real |
| `TurnJob`, `TurnQueue`, `ThreadLock`, `PendingInbox` | `agent_turn` | queue/lock: C1 over Redis; `PendingInbox`: C1 batcher | C1 enqueue, C2 consume | `InMemoryTurnQueue`, `InMemoryThreadLock` |
| `PolicyProfile`, `PolicyHooks`, `PolicyContext`, `DEFAULT_PROFILES`, `effective_profile_key` | `policy` | P implements `PolicyHooks`; the data of the two profiles is done (A) | D1, S, C1, C2, D4, D2 call the hooks | `PermissivePolicyHooks` |
| `ToolSpec`, `ToolContext`, `ToolScope`, `AgentTool`, `ToolRegistry`, `McpToolProvider`, `BUILTIN_TOOL_KEYS` | `tools` | D4 registry; D5 provider | D1 | build fakes from `ToolSpec` |
| `ConversationStore` (= `HistoryStore`, `MemoryStore`, `ThreadStore`, `UsageStore`, `ContactStore`, `ImageDescriptionStore`) | `conversation` | D2 | D1, C1, C2, S, D4, admin routes | write a dict-based fake in your tests; keep it in your package |
| `AccountStore`, `AgentStore` | `agents` | D2 | C1, C2, S, D1, D4 | `InMemoryAccountStore`, `InMemoryAgentStore` |
| `KnowledgeStore`, `KnowledgeSearch`, `EmbeddingClient` | `knowledge` | D3 | D4 (`kb_search`), admin routes | dict-based fake |
| `McpPolicy`, `McpPolicyStore`, `McpManager`, `McpServerView` | `mcp` | D5 | D4 registry, admin routes | |
| `SchedulerPort`, `CreateScheduledJobInput`, `ScheduledJob`, `ProactiveSendGuard`, `ScheduleInput` | `scheduler` | S | B2, D4 (`schedule_task`), admin routes | |
| `AgentFacingClinicActions`, `CareContext`, `IdentityLink`, `InboxRef` | `clinic_actions` | B1 (`pema/clinic/actions/agent_facing.py`) | D1/D4 tools, P, C1/C2 (Inbox), S | dict-based fake |
| `ActionContext`, `Action` | `actions` | B1 | everyone calling an action | |
| Domain DTOs | `patients`, `appointments`, `crm`, `conversations`, `review`, `auth` (incl. `ChangePasswordRequest`, `ResetPasswordRequest`, `StaffUserOut`, `StaffUserCreate`, `StaffUserUpdate`), `admin`, `admin_agent`, `roles` (incl. `Permission.ADMIN_USERS = "admin.users"`, owner only, and `Permission.ADMIN_USERS_READ = "admin.users.read"`, owner and manager), `errors`, `common` | | B1, B2, E (via OpenAPI) | |
| Retention | `pema.retention` (`RetentionPolicy`, `Scope`, `RetentionRunner`, `start_retention_loop`) | H2 | worker (`Scope.AGENT`), API wiring (`Scope.CLINIC`), CLI | `pema.retention.pg_testing` |
| Tuning API | `pema.config.runtime_tuning_settings` (A, first version) | A API, D1 provider | every package | `StaticTuningProvider` |
| Secret cipher | `pema.config.secret_cipher` | A | C1, C2, D1, D2, D4, D5 | set `PEMA_SECRET_ENCRYPTION_KEY` in the test |
| DB session (no clinic context since ST-A) | `pema.core.db.ClinicDatabase`, `get_installation_clinic_id` | A | every store | `tests/test_database.py` shows the pattern; test clinic: `pema.core.testing.ensure_test_clinic` (section 10) |

### Policy hook call sites (so P attaches without editing D1 or S)

`PolicyHooks` has eight async methods; a package that owns a call site MUST call them there, passing a
`PolicyContext` built from the account, the agent and `effective_profile_key`. When the profile flag is off
the hook may return at once, and the default `PermissivePolicyHooks` does nothing.

| Hook | Call site | Package |
|---|---|---|
| `before_llm` | start of `run_turn` (and for mid-turn injected messages): red flags and PII masking happen BEFORE any model call; a `HAND_OFF` decision stops the turn | D1 |
| `after_llm` | final text of a turn, before delivery (restore masked names) | D1 |
| `filter_tool_keys` | after `ToolRegistry.list_available` | D4 (registry) |
| `allow_memory_write` | `save_memory` tool | D4 |
| `on_outbound` | EVERY text that would leave the system: turn reply (`deliver_chat_reply`), scheduled message and scheduled agent output (`deliver_proactively`), tool sends | C2 and S |
| `check_job` | `create_job` and `run_scheduled_job` | S |
| `proactive_cap` | proactive send guard (cap key per account/thread or per patient/account) | S |
| `verify_identity` | before the agent may name a patient, an appointment or a medicine | D1 (via P) |

## 4. How a message travels (normative)

```
Zalo -> webhook (be_app, API process)
  C1 router: verify_webhook, parse_inbound, dedupe update_id (agent.channel_update_seen),
             allowlist, record_incoming_message (agent.history/threads via ConversationStore;
             Inbox via AgentFacingClinicActions.record_inbound_message), batcher (debounce, Redis)
  -> TurnQueue.enqueue(TurnJob)
Worker (agent_worker role; no privilege on clinic.*)
  C2 turn processor: ThreadLock.hold(account, thread) -> AgentEngine.run_turn(request, callbacks)
     D1: before_llm hook (patient_channel: red flag -> HAND_OFF, PII mask) -> loop with tools -> after_llm
     tools: clinic tools = AgentFacingClinicActions; memory/KB/schedule = stores and ports
  -> on_outbound hook:  SEND (staff_assistant)  |  HOLD_FOR_REVIEW (patient_channel: create_review_item)
  -> ChannelPort.send_text parts   (staff approves a review item -> same send path)
Scheduler worker (S): per active clinic, due jobs -> kind message (template) | kind agent (isolated turn)
  -> on_outbound hook -> proactive guard (atomic cap, kill switch, window, gap) -> ChannelPort.send_text
CRM rules (B2, be_app): rule + patient + source event -> crm_task (+ SchedulerPort.create_job with dedupe_key)
```

Two stores, one purpose each: `agent.history` is the LLM context store; `clinic.message` is the Inbox of record
that staff read. The channel layer writes both. Review items live in `clinic.review_item`.

## 5. Database

* Schemas: `ctx` (neutral helpers), `clinic` (CRM), `clinic_agent` (the agent's only door into the clinic), `agent`
  (engine tables). Mapping of every zalo-agent table is in the docstring of `0002_agent_schema.py`.
* Roles: `be_app` (API process, DML on `clinic.*` and `agent.*`, `audit_log` insert/select only), `agent_worker`
  (DML on `agent.*`; reads `clinic_agent` views; EXECUTE on `clinic_agent` functions; NOTHING on `clinic.*`).
  **Single tenant (section 10): there is no RLS any more.**
* ~~RLS~~ (removed by migration `st_0009_single_tenant`, section 10): every table keeps `clinic_id` as the fixed
  installation id; open a unit of work with `async with db.session() as s:`; the id comes from
  `get_installation_clinic_id(db)`; `ctx.the_clinic_id()` is the SQL function behind it.
* `agent_worker` reaches the clinic through `clinic_agent.patient_ref`, `patient_appointment`, `patient_open_task`,
  `patient_care_plan`, `patient_last_session`, `consent_current`, `identity_verified`, `channel_policy`,
  `message_template_approved` (no phone, birth date, address, clinical free text or credentials) and the functions
  `touch_identity`, `resolve_identity`, `create_review_item` (idempotent on `job_id`, audits as actor `agent`).
  A package that needs more adds a view/function in its own migration and says so; it never grants a table.
* Migrations: never edit `0001..0003`. A package adds `alembic/versions/<pkg>_NNNN_<what>.py` with
  `down_revision = "0003_clinic_agent_access"` (or its own previous revision). Several heads are fine
  (`alembic upgrade heads`, `make db-upgrade`); package G merges them. Every new table needs `clinic_id` (no RLS, no policy since `st_0009`), and
  grants to the right role(s). DDL tests run with `PEMA_TEST_DATABASE_URL` against a THROWAWAY database.
* Windows: psycopg async needs the selector loop: call `pema.core.event_loop.ensure_selector_event_loop_policy()`
  before the loop starts (done in `tests/conftest.py`). Production is Ubuntu, where it is a no-op.

## 6. Conventions

* Faithful port: `# ported from: src/<path>.ts` first line, forced deviations in the module docstring (SQLite to
  Postgres, Vercel AI SDK to `openai`, sync to async, one process to Redis). Keep names, constants, thresholds and
  the reasoning of the comments (translated). Test names: snake_case of `describe_it`, the Vietnamese title in
  the docstring (see `tests/shared/test_zone_time.py`).
* Time: ISO 8601 with `+07:00` on every boundary (`VnDatetime`); naive datetimes are rejected. Inside stores use
  aware UTC; `pema.shared.zone_time` converts. Days (cap, usage) are computed in `bot_time_zone()`.
* Tuning: `from pema.config.runtime_tuning_settings import get_tuning, bot_time_zone`. Never read `os.environ`
  for a tuning key. In tests use `install_tuning_provider(StaticTuningProvider({...}))` and reset it.
* Errors: raise `DomainError(ErrorCode, "Vietnamese text without PII")`; the API turns it into `ErrorResponse`.
  `AgentEngine.run_turn` raises `AgentTurnError`. Channel guards answer a rejected `SendResult`, they do not raise.
* Logging: `create_logger("scope")`, keyword fields, ids and codes only. Keys such as `text`, `content`,
  `sender_name`, `phone`, `token`, `headers` are redacted automatically; never rely on that, never pass PII. Errors
  go through `err=exc` (safe serializer).
* Secrets: encrypt with `pema.config.secret_cipher`; DTOs never carry a secret (`has_bot_token`, `api_key_masked`).
* Dependencies: all expected libraries are declared in `apps/api/pyproject.toml`. If you need another, append one
  line, mention it in your report, and do not commit `uv.lock` changes you did not need.
* Tests: pytest + pytest-asyncio (auto). Use the fakes of `pema_contracts.testing`; wait with
  `doi_cho_den_khi` (never `sleep(N)` then assert; it does not prove negatives, see its docstring); DB tests are
  marked `db` and skip without `PEMA_TEST_DATABASE_URL`. Everything synthetic: no real phone, name, photo or token.
* Lint gate for every package: `make lint` (ruff, ruff format, pyright strict, import-linter) and `make test`.
* import-linter (enforced): contracts is a leaf; `clinic.domain` / `clinic.actions` never import channels, api,
  agent, workers, middleware; agent-side packages reach `pema.clinic` only through `pema.clinic.actions`; only
  `bootstrap`, `api` and `workers` import `pema.api` / `pema.workers`. By convention (not enforced): `pema.scheduler`
  and `pema.channels` receive the engine as `AgentEngine`; they do not import `pema.agent`.

## 7. Decisions taken by package A (change only with a reason)

1. **Proactive cap default is 10**, the original `SCHEDULER_MAX_PROACTIVE_PER_DAY`, per (account, thread, day);
   `patient_channel` keys it per (patient, account, day). The "60 per day" of the discarded v1 design is not used.
2. **Account and agent configuration lives in `agent.accounts` / `agent.agents`**, with `policy_profile` on both;
   the restrictive one wins and the default of both is `patient_channel` (fail safe). `clinic.channel_setting` is the
   clinic-wide switchboard per channel kind (kill switch, cap, window); a proactive send needs both to allow it.
3. **Status enums keep the original Vietnamese values** where they are stored and shown (`cho_xu_ly`, `da_ket_noi`,
   `can_duyet_lai`, ...). Python member names are English.
4. **Tuning**: 72 parameters, defaults and bounds extracted mechanically from `env.ts` / `tuning-definitions.ts`
   (`tuning_specs.py`), read synchronously from an in-memory provider that D1 fills from `agent.runtime_settings`.
5. **Shared pipeline split**: the channel-agnostic outbound/turn pipeline (`send_reply_in_parts`, split, sanitize,
   markdown, `message_turn_processor`) is C2's as the plan says; the small shared inbound helpers
   (`record_incoming_message`, `busy_wait_notice`, `payload_anomaly_watch`, `reply_target_tu_kenh`) are C1's.
   C2 needs a few C1 signatures and C1 needs none of C2: the bot router only enqueues a `TurnJob`.
6. **The turn runs in the worker, not in the webhook handler.** The batcher is in the API process and talks to the
   worker through Redis (`TurnQueue`, `PendingInbox`, `ThreadLock`).
7. **CRM rules (B2) run as `be_app`** (they read broad clinic data), in an API-process task or a CLI, and create jobs
   through `SchedulerPort`. The `agent_worker` role is for turns, scheduler delivery and KB ingest only.
8. **Message templates**: `clinic.message_template` (doctor-approved) is what a `kind: message` job may send in
   `patient_channel`; `payload` carries the template key.
9. **Logger redacts PII keys** and the safe error serializer is mandatory for exceptions: a deliberate addition.
10. **`kenh-luot` became `ChannelPort`**; `TOOL_KHONG_CHAY_TREN_BOT` became data (`ChannelCapabilities.blocked_tools`).

## 8. Changing a contract

Additive changes (new optional field, new enum member, new Protocol method with no existing implementer) can be
made by their owner and reported. Anything else (rename, removal, a new required field, a changed route or DTO of
the OpenAPI) goes to package G: edit, run `make openapi` and `make types`, update this file and the affected
packages in one change.

## 9. Open items for the plan owner

* Booking by the agent in `patient_channel` (`appointment.book`): proposal vs confirmed appointment. Contract says
  "proposal that a human confirms"; B1 needs the product decision.
* Where the files (images, KB uploads, generated documents) live: object storage vs a local volume (D2/D3/D4).
* One worker per clinic or a shared worker for several clinics; which process owns which Zalo account (F/G).
* `evals/` has no package in PLAN section 6; assigned to D1 (original scenarios) and P (clinic cases).
* The doctor's sign-off on KB documents and message templates is modelled (`approved_by_clinical_owner`,
  `approved_at`) but no screen is assigned except E's admin KB and templates (templates: B1 route `admin_templates`, E screen).
* Retention periods (history, traces, media) for patient data under Decree 13/2023: tuning keys exist
  (`AGENT_TRACE_RETENTION_DAYS`, `MEDIA_RETENTION_DAYS`, `HISTORY_MAX_MESSAGES_PER_THREAD`); the values are the
  clinic owner's decision.
* Retention: `pema.retention` exists (integration H). The periods are still the clinic owner's decision; the code
  default keeps clinical data and messages (0) and gives only technical data a short life. No rule yet for decided
  `review_item`, `display_name`/`contacts`, `crm_activity` and conversation summaries.
* Staff management (H4): `GET /admin/users` (owner and manager), `POST /admin/users`, `PATCH /admin/users/{user_id}`
  and the password reset (owner only) have a screen (`/admin/users`). The owner can lock, re-role or reset the
  password of another owner (refused only for the caller's own account for lock and role, for the caller's own
  password reset, and when it would leave the clinic without an active owner); whether the clinic wants that is
  the clinic owner's decision. `StaffUserOut` carries no password or hash; the list is for the owner and the manager
  only, so the "Phụ trách" box of "Việc hôm nay" (used by `cs_staff`) does not use it: opening `admin.users.read` to
  `cs_staff` and `reception` is an open product decision, not done.

## 10. Single-tenant (package ST-A, branch `feat/single-tenant`)

Decision: **one installation is ONE clinic with its own database.** Nothing lets several clinics share a system any
more. The `clinic_id` column stays in every table as the fixed "installation id" (no schema rewrite, foreign keys and
composite keys keep working); only the mechanisms for many clinics go. Sections 3 and 5 above describe the old model
where they mention RLS, `current_clinic_id`, `resolve_clinic`, `list_active_clinic_ids` or "per active clinic": this
section wins.

### 10.1 Database (migration `st_0009_single_tenant`, the only head, after `h_0008_merge_heads`)

* `clinic.clinic` holds EXACTLY ONE row, enforced by the database (`singleton boolean NOT NULL DEFAULT true`,
  `CHECK (singleton)`, `UNIQUE (singleton)`); a second INSERT fails, the row cannot be DELETEd (trigger). The upgrade
  refuses a database that already holds two or more clinics.
* `clinic.ensure_clinic(name, slug, timezone, id)`: idempotent create of that row (never renames, never changes the
  id, raises when asked for another id). Owner role only, no grant to `be_app`/`agent_worker`. The migration calls it
  with `PEMA_CLINIC_NAME` (default `Pema Clinic`), the fixed slug `clinic`, and `PEMA_CLINIC_ID` as id when set
  (otherwise an id is generated once). An installed clinic is left alone.
* `ctx.the_clinic_id()`: STABLE SECURITY DEFINER, both runtime roles may call it, RAISES `no clinic installed` when the
  table is empty. It replaces `ctx.current_clinic_id()` everywhere: the ten `clinic_agent` views and the nine
  `clinic_agent` definer functions were re-created from the catalog with it (attributes, `security_barrier`, grants and
  the `search_path ... pg_temp` of g_0006 kept). New SQL: use `ctx.the_clinic_id()`, never read `app.clinic_id`.
* Dropped: every policy `clinic_isolation` (41), ROW LEVEL SECURITY on all tables of `clinic.*` and `agent.*`,
  `ctx.current_clinic_id`, `ctx.resolve_clinic`, `ctx.list_active_clinic_ids`. A new table needs `clinic_id` (FK to
  `clinic.clinic`) and grants; **no RLS, no policy**.
* Grants unchanged: `agent_worker` still has NOTHING on `clinic.*` and reaches the clinic only through the
  `clinic_agent` views/functions; `be_app` keeps its grants (`audit_log` insert/select only); `clinic.audit_log` is still
  append-only. Accepted consequence: `be_app` and `agent_worker` now read every row of the tables they hold a grant on,
  whatever a session setting says (there is one clinic in the database). The views still filter by the installation id.
* Downgrade restores policies, RLS and the old functions (one round trip is tested); the clinic row stays.

### 10.2 Python surface (what exists now, what is deprecated, what goes)

| Item | State | Who changes callers |
|---|---|---|
| `pema.core.db.get_installation_clinic_id(db, *, verify=False) -> UUID` | NEW, source of truth: cache per `ClinicDatabase`, then `PEMA_CLINIC_ID`, then `ctx.the_clinic_id()`; also fills `pema_contracts.installation`. Call it once at start-up (`verify=True` compares `PEMA_CLINIC_ID` with the DB) | all |
| `ClinicDatabase.session()` | REMOVED the `clinic_id` argument (no `app.clinic_id` is set); no caller passes it any more (ST-G1) | done |
| `ClinicDatabase.system_session()` | REMOVED (ST-G1; no caller left) | done |
| `ClinicDatabase.resolve_clinic(slug=None)` | REMOVED (ST-G1; login, webhooks and bridge read the installation id) | done |
| `ClinicDatabase.list_active_clinic_ids()` | REMOVED (ST-G1); the loops over clinics (scheduler, KB ingest, retention, MCP, snapshots) are one pass | done |
| `ClinicDatabase.read_installation_clinic_id()` / `.installation_clinic_id` | NEW (uncached read / cache) | |
| `pema_contracts.installation`: `installation_clinic_id()`, `installation_clinic_id_or_none()`, `set_installation_clinic_id()`, `reset_installation_clinic_id()`, `InstallationClinicNotLoadedError` | NEW (leaf, process-wide value) | |
| `clinic_id` of `ActionContext`, `TurnJob`, `AgentTurnRequest`, `ReviewItemCreate`, `CreateScheduledJobInput` | now `Field(default_factory=installation_clinic_id)`: leave it out and it is filled (raises if the id was not loaded); passing it still works | ST-B/ST-C drop the argument at call sites |
| `clinic_id` of `PolicyContext`, `ToolContext` (dataclasses), `AccountConfig`, `AgentProfile`, `ScheduledJob`, `McpPolicy`, `UserSummary`, `ToolScope`, every store/port method argument (`AccountStore`, `AgentStore`, `ConversationStore`, `KnowledgeStore`, `ChannelRegistry.get_running/list_running`, `ThreadLock.hold`, ...) | UNCHANGED in this step (still passed explicitly; pass `get_installation_clinic_id(db)`). Removing them is a contract change of the owning package, done after the steps below | ST-B, ST-C |
| `Settings.clinic_name` (`PEMA_CLINIC_NAME`), `Settings.clinic_id` (`PEMA_CLINIC_ID`, optional) in `pema.config.env` | NEW | ST-F puts them in compose/`.env.example` |
| `pema.core.installation.ensure_clinic(conn, name=None, *, clinic_id=None, timezone=None) -> UUID`, `ensure_clinic_async(...)`, CLI `python -m pema.core.installation` | NEW: idempotent create-or-get of the one clinic (owner connection) for seeds and bootstrap | ST-B (`seed_demo`), ST-F (bootstrap) |
| `pema.core.testing.ensure_test_clinic(conn) -> UUID`, `ensure_test_clinic_async(conn)`, `truncate_installation_data(conn)` | NEW test helpers (below) | ST-B, ST-C |
| Login `clinic_slug`, webhook path `/webhooks/zalo-bot/{clinic_slug}/{account_id}`, bridge clinic segment | REMOVED (ST-B, ST-C, ST-E); the paths are now `/api/v1/webhooks/zalo-bot/{account_id}` and `/api/v1/webhooks/zalo-bridge/{account_id}`, `openapi.json` and `schema.d.ts` regenerated | done |

### 10.3 Recipe for the fixtures (ST-B, ST-C)

A migrated database now already contains its one clinic, so `INSERT INTO clinic.clinic` per test fails
(`UNIQUE (singleton)`). Change every fixture from "create a fresh clinic id per test" to "use the one clinic, clean
the data between tests":

```python
from pema.core.testing import ensure_test_clinic, truncate_installation_data

with admin_engine.begin() as conn:
    clinic_id = ensure_test_clinic(conn)   # same id every time; also sets the installation id for the DTO defaults
    truncate_installation_data(conn)       # all of clinic.* and agent.* except clinic.clinic (superuser, test DB only)
    # then insert the agent/accounts/patients the test needs with clinic_id=clinic_id
```

Rules: no test inserts a second clinic; "tenant isolation" tests (two clinics must not see each other) are deleted or
turned into "agent_worker has no raw access to `clinic.*`" (see `tests/test_database.py`); a test that needs a clinic
with other settings updates the one row. `PgTestServer`-style helpers that create a throwaway database per module
keep working (the migration creates the clinic in it; set `PEMA_CLINIC_NAME` if the name matters). Call
`pema_contracts.installation.reset_installation_clinic_id()` when a fixture swaps databases.

### 10.4 Who removes what (after this step the build is green; the removal is incremental)

* **ST-B (auth, actions, workers, scheduler, retention)**: `pema/api/dashboard_auth.py` (login by slug, `account_key`
  with slug), `pema/api/clinic_testing.py`, `pema/clinic/actions/seed_demo.py` (use `ensure_clinic`), the
  `ActionContext` construction in the API layer, `pema/composition/{runtime,api_wiring}.py`,
  `pema/workers/{main,scheduler_worker,retention,kb_ingest_worker}.py`, `pema/scheduler/scheduler_loop.py`,
  `pema/retention/runner.py` (loops over `list_active_clinic_ids`); the `pema/core` shims once nobody calls them.
  Delete `tests/clinic/test_rls_isolation.py`.
* **ST-C (Zalo channels, bridge, agent stores, MCP, KB, policy)**: `pema/channels/zalo_bot/{webhook,settings,
  bot_account_manager}.py`, `pema/channels/zalo_personal/{services,service_testing,testing,account_manager,
  bridge_client,bridge_events,channel_settings,qr_login_manager}.py`, `pema/api/routers/webhooks_zalo_{bot,bridge}.py`,
  `pema/composition/{intake,testing}.py` (`make_clinic_resolver`), `pema/config/{account_store,runtime_settings_store}.py`,
  `pema/mcp/{mcp_manager,mcp_schema}.py`, `pema/knowledge/kb_ingest_worker.py`, the `clinic_id` arguments of the stores
  in `pema/conversation`, `pema/knowledge`, `pema/config`, `pema/mcp`, `pema/policy`.
* **ST-E (UI)**: the clinic slug field of `frontend/src/components/admin/auth/login-form.tsx` and the use of
  `UserSummary.clinic_id`/`clinic_name`, once ST-B changes the login DTO and regenerates `openapi.json` and `schema.d.ts`.
* **ST-F (infra, docs)**: `infra/docker-compose.yml` and `.env.example` (`PEMA_CLINIC_NAME`, optional `PEMA_CLINIC_ID`),
  `infra/scripts/{migrate,bootstrap-roles,backup-postgres}.sh` and `infra/README.md` wording about RLS/clinics,
  `ARCH-AI01` sections 3 and 8, `SECURITY-REVIEW-AI01` SEC-06/SEC-12 (RLS is gone; the accepted limit is now "one clinic
  per database"), `MODULEMAP-AI01`, `PORT-MAP.md` mentions, the open item "one worker per clinic" of section 9.

### 10.5 Tests (history of the ST-A step, closed in ST-G1)

After the database step alone, a full `pytest` run on Postgres 17 + Redis 7 showed 393 failures and 497 errors: fixtures
that insert a second clinic, and tests of RLS or slug behaviour. ST-B and ST-C moved the fixtures to the one clinic
(`ensure_test_clinic` + `truncate_installation_data`) and deleted the tests that only checked isolation between two
clinics (`tests/clinic/test_rls_isolation.py`, the per-clinic cases of the runtime settings and MCP boot tests). After the
merge of the four packages and the clean-up of ST-G1 (below) the full backend run on a clean Postgres 17 + Redis 7 is
**4583 passed, 10 skipped, 0 failed, 0 errors** (the skips are optional tools and platform limits).

### 10.6 Rules for new code from now on

No `set_config('app.clinic_id')`, no `ctx.current_clinic_id()`, no policy, no `ENABLE ROW LEVEL SECURITY`. SQL that needs
the clinic calls `ctx.the_clinic_id()`. Python that needs the id calls `get_installation_clinic_id(db)` once at start-up
(or lets the DTO default fill it). A new test never inserts a second clinic.

### 10.7 Infrastructure done in ST-F (`infra/`)

* `infra/.env.example` documents `PEMA_CLINIC_NAME` (default `Pema Clinic`) and the optional `PEMA_CLINIC_ID` (UUID,
  empty = generated once). `docker-compose.yml` passes both to `migrate` and (through `x-backend-env`) to `api` and
  `worker`; an empty `PEMA_CLINIC_ID` means "unset" (the migration and `Settings` both read empty as unset).
* `infra/scripts/migrate.sh`, after `alembic upgrade heads`, checks that `clinic.clinic` holds exactly one row, prints
  `migrate: clinic '<name>' (id <uuid>), exactly one row in clinic.clinic`, and fails when the row count is not one or
  `PEMA_CLINIC_ID` differs from the stored id. `restore-postgres.sh` makes the same count check; `backup-postgres.sh`
  checks that `clinic.clinic` data is in the archive.
* No Makefile target or script takes a clinic slug or `--clinic`. Webhook paths in infra docs are
  `/api/v1/webhooks/zalo-bot/<account_id>` and `/api/v1/webhooks/zalo-bridge/<account_id>` (the new paths owned by
  ST-C; the Caddy block on `zalo-bridge/*` is unchanged).
* A second clinic is a second stack (own `.env`, secrets, compose project, ports, database, Redis, domain, backups):
  `infra/README.md`, "One system, one clinic".

### 10.8 Integration state (ST-G1: merge of ST-B, ST-C, ST-E, ST-F and clean-up)

* One migration head, `st_0009_single_tenant`; `alembic upgrade heads` on an empty database leaves exactly one row in
  `clinic.clinic` (`test_the_migration_chain_has_one_head` does not name the head).
* Removed from `pema/core/db.py`: `session(clinic_id)` argument, `system_session`, `resolve_clinic`,
  `list_active_clinic_ids`. Removed "which clinics" callables: `RuntimeSettingsSnapshot.start_refresh_loop(clinic_ids)`
  (now `start_refresh_loop(interval_s=...)`, it refreshes the installation clinic it was given by `refresh`),
  `KbAvailabilitySnapshot(store, clinic_ids)` (now `KbAvailabilitySnapshot(store)`), `DefaultMcpManager(clinic_ids=...)`,
  `installation_clinic_ids()` and `Runtime.clinic_ids()` of the composition root. `RuntimeSettingsSnapshot` holds one
  set of rows; the `ContextVar` that picked a clinic for a synchronous read (`use_settings_clinic`,
  `set_settings_clinic`, `current_settings_clinic`) is gone, nothing sets a "current clinic" per task or request.
* **Kept on purpose, "installation id"**: the `clinic_id` argument of the stores and ports (`AccountStore`, `AgentStore`,
  `ConversationStore`, `KnowledgeStore`, `RuntimeSettingsStore` and `RuntimeSettingsSnapshot.refresh/set/delete`,
  `update_llm_settings` and the other settings writers, MCP stores, `ThreadLock`, ...), the `clinic_id` fields of
  `PolicyContext`, `ToolContext`, `AccountConfig`, `AgentProfile`, `ScheduledJob`, `McpPolicy`, `UserSummary`, `ToolScope`
  and the `clinic_id` column of every table. Removing them touches the contract of several packages and every test
  fixture at once for no behavioural gain; callers pass the installation id (`get_installation_clinic_id(db)`, or the
  DTO default). A new store may omit the argument and read `installation_clinic_id()`.
* Webhooks: `POST /api/v1/webhooks/zalo-bot/{account_id}` and `POST /api/v1/webhooks/zalo-bridge/{account_id}`; the
  bridge `.env.example`, Caddyfile, `infra/README.md` and the Ubuntu guide use the same paths. `openapi.json` and
  `frontend/src/lib/api/schema.d.ts` are regenerated (`make openapi types`); `LoginRequest` is e-mail + password.
* Not yet in the backend (wave 4, the frontend mock serves them as `PENDING_CONTRACT`): `GET /api/v1/events` (SSE),
  `POST /api/v1/conversations/{conversation_id}/presence`, `GET /api/v1/staff/assignable`.
* New closed-loop tests: `tests/integration/test_loop_single_tenant.py` (real login with e-mail and password only, then
  `/me` and refresh; two Zalo bot accounts of the one clinic answer their own customers independently, each with its own
  webhook secret). The harness `pema.composition.testing.open_loop` takes `extra_accounts`.
