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
| B1 | `pema/clinic/{domain,actions,rbac,audit,models}`, `pema/api/routers/{auth,patients,appointments,crm,conversations,review_items,admin_audit,admin_users}.py` (`admin_users.py`: `POST /admin/users/{user_id}/password`, permission `admin.users`, owner only), `pema/api/{client_ip,dashboard_auth,dashboard_password_store,dashboard_session_store}.py` |
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
| Domain DTOs | `patients`, `appointments`, `crm`, `conversations`, `review`, `auth` (incl. `ChangePasswordRequest`, `ResetPasswordRequest`), `admin`, `admin_agent`, `roles` (incl. `Permission.ADMIN_USERS = "admin.users"`, owner only), `errors`, `common` | | B1, B2, E (via OpenAPI) | |
| Retention | `pema.retention` (`RetentionPolicy`, `Scope`, `RetentionRunner`, `start_retention_loop`) | H2 | worker (`Scope.AGENT`), API wiring (`Scope.CLINIC`), CLI | `pema.retention.pg_testing` |
| Tuning API | `pema.config.runtime_tuning_settings` (A, first version) | A API, D1 provider | every package | `StaticTuningProvider` |
| Secret cipher | `pema.config.secret_cipher` | A | C1, C2, D1, D2, D4, D5 | set `PEMA_SECRET_ENCRYPTION_KEY` in the test |
| DB session with clinic context | `pema.core.db.ClinicDatabase` | A | every store | `tests/test_database.py` shows the pattern |

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
  Neither owns tables, so RLS applies to both.
* RLS: every table has `clinic_id` and `USING (clinic_id = ctx.current_clinic_id())`. Open a unit of work only with
  `async with db.session(clinic_id) as s:` (`ClinicDatabase`), which sets `app.clinic_id` for the transaction.
  No context means no rows. `ctx.resolve_clinic(slug)` and `ctx.list_active_clinic_ids()` work without a context.
* `agent_worker` reaches the clinic through `clinic_agent.patient_ref`, `patient_appointment`, `patient_open_task`,
  `patient_care_plan`, `patient_last_session`, `consent_current`, `identity_verified`, `channel_policy`,
  `message_template_approved` (no phone, birth date, address, clinical free text or credentials) and the functions
  `touch_identity`, `resolve_identity`, `create_review_item` (idempotent on `job_id`, audits as actor `agent`).
  A package that needs more adds a view/function in its own migration and says so; it never grants a table.
* Migrations: never edit `0001..0003`. A package adds `alembic/versions/<pkg>_NNNN_<what>.py` with
  `down_revision = "0003_clinic_agent_access"` (or its own previous revision). Several heads are fine
  (`alembic upgrade heads`, `make db-upgrade`); package G merges them. Every new table needs `clinic_id`, RLS, and
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
* The owner can reset the password of another owner (`POST /admin/users/{user_id}/password` refuses only the
  caller's own account); there is no route or screen that lists staff, so the reset has no UI yet.
