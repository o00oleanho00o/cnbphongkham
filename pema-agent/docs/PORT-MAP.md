# PORT-MAP: zalo-agent (TypeScript) to Pema Agent (Python)

Produced by package A. Coverage is machine-checked by `backend/apps/api/tests/test_port_map.py` against the clone below.

| | |
|---|---|
| Upstream | https://github.com/vuhai2002/zalo-agent (MIT, Copyright (c) 2026 Vu Van Hai) |
| Reference clone (outside the repo) | `E:\Desktop\zalo-agent-ref` |
| Commit | `bf154de68335e73073c2b6913c731be22ca3d0e6` |
| Upstream version | 0.3.1 (`package.json`) |
| Python target root | `pema-agent/backend/apps/api/pema/` (written `pema/...`); tests under `pema-agent/backend/apps/api/tests/` (written `tests/...`) |
| Files in `src/` | 519 (all mapped below; 10 are `no port`) |

Recreate the clone: `git clone --depth 1 https://github.com/vuhai2002/zalo-agent E:\Desktop\zalo-agent-ref` then `git -C E:\Desktop\zalo-agent-ref checkout bf154de68335e73073c2b6913c731be22ca3d0e6` (fetch the commit if the depth-1 clone moved on). Read-only for everyone.

## How to read the tables

* One row per upstream file. `Python target` is a module under `pema/` or a test under `tests/`. A test row keeps the test of its module: translate it to pytest with matching names (the original Vietnamese title goes in the docstring).
* `Package` is the ONLY package allowed to create or edit the target. `A` rows are already done and tested. `A, D1` means A delivered the first version and D1 owns it from now on.
* `no port` rows say why the file does not exist in the Python code base.
* Every ported module starts with `# ported from: src/<path>.ts` and records forced deviations in its docstring.

### Packages

| Package | Scope | Rows |
|---|---|---:|
| A | Contracts, skeleton, PORT-MAP (this package, done) | 34 |
| B1 | Clinic core: auth, RBAC, audit, patients/appointments/conversations/review items | 8 |
| B2 | CRM rules -> scheduler jobs | 0 |
| C1 | Zalo Bot API channel + middleware + shared inbound helpers | 34 |
| C2 | Zalo personal channel (Node bridge), shared outbound/turn pipeline | 62 |
| D1 | Agent engine, persona, providers, guards, trace, tuning/LLM settings, evals | 101 |
| D2 | Conversation, memory, account/agent stores, usage | 37 |
| D3 | Knowledge base | 62 |
| D4 | Tools, documents, images, video, web | 136 |
| D5 | MCP client | 21 |
| S | Scheduler | 36 |
| P | Policy profiles, red flags, PII, identity | 0 |
| E | Next.js frontend | 127 |
| F | Infra and docs | 12 |
| G | Integration and review | 2 |
| (no port) | files deliberately not translated | 43 |

## Dependency mapping

| zalo-agent | Pema Agent | Notes |
|---|---|---|
| Vercel AI SDK (`ai`, `streamText`, `tool()`, `stepCountIs`) | hand-written tool loop on the `openai` SDK (`AsyncOpenAI`, OpenAI-compatible: Ollama, llama-server, 9Router) + thin Anthropic and Google adapters | Keep step/`tool-loop-guard`/`maxRetries` semantics. `Tool` becomes `pema_contracts.tools.AgentTool`. No LangGraph in the loop. |
| `@ai-sdk/openai-compatible`, `@ai-sdk/anthropic`, `@ai-sdk/google` | `openai`, `anthropic`, `google-genai` SDKs | `LlmProviderKind` values unchanged. |
| `@ai-sdk/mcp` | `mcp` Python SDK, HTTP (streamable) transport | Per-agent default-deny and fingerprint drift stay (D5). |
| `node:sqlite` (sync, WAL, `BEGIN IMMEDIATE`) | SQLAlchemy 2 async + `psycopg` 3, Postgres 17 | Schema = Alembic 0001..0003. Single-process invariants (claim a job, count a cap) become atomic SQL (`UPDATE ... RETURNING`, `INSERT ... ON CONFLICT`) plus Redis locks. |
| SQLite FTS5 + `bm25()` + RRF | Postgres FTS (`tsvector` over the diacritics-folded column, `ts_rank_cd`) + `pgvector` (bge-m3, 1024) fused by the same RRF | The vector side is the only extension over the original (D3). |
| `zca-js` 2.1.2 | stays in a Node 22 + Hono bridge (`backend/bridges/zalo-personal`), flag off by default | Python talks to it over HTTP; events return through `/webhooks/zalo-bridge`. MIT notice in `THIRD_PARTY_NOTICES.md`. |
| `hono` + `@hono/node-server` | FastAPI + uvicorn | Routes are thin and call `pema.clinic.actions` or the stores. |
| `zod` | `pydantic` v2 (`pema_contracts`) and `pydantic-settings` |  |
| `pino`, `pino-roll`, `pino-pretty` | stdlib `logging` with `pema.shared.logger` | Adds PII redaction. |
| `luxon` | `zoneinfo` + `tzdata` | `pema.shared.zone_time`. |
| `cron-parser` | `croniter` | Validation of density stays in `schedule_parser` (S). |
| `docx`, `exceljs` | `python-docx`, `openpyxl` | Tools take DATA only, never code (prompt-injection rule); off in patient_channel. |
| `unpdf`, `saxes`, `image-size` | `pypdf`, `defusedxml` / `xml.sax`, `struct`-based image header read | Zip-bomb ceilings and worker timeout stay (D3). |
| `yt-dlp` (subprocess), tikwm | same subprocess; same sources whitelist | Off in patient_channel. |
| React 19 + Vite SPA dashboard (`web/`) | Next.js App Router (TypeScript, Tailwind), `openapi-typescript` | Package E translates the features, not the code line by line; Pema brand tokens. |
| `node --test` + `tsx` | `pytest` + `pytest-asyncio` (auto mode) | Test names kept; fake LLM, fake channel, fake Redis. |
| `ThreadType` (zca-js, 0/1) | `ThreadKind` (user/group); stored as int in `agent.threads.thread_type` |  |
| `loai`: `ca_nhan` / `bot` | `ChannelKind`: `zalo_personal` / `zalo_bot` (+ `zalo_oa` stub) |  |
| `KenhLuot` | `ChannelPort` + `TypingChannel`, `ReadReceiptChannel`, `ReactionChannel`, `MediaChannel`, `GroupChannel` | `pema_contracts.channel`. |
| `DASHBOARD_PASSWORD` + HMAC cookie | JWT HttpOnly cookie, per-user argon2 password, RBAC (B1) |  |
| `CREDENTIALS_ENCRYPTION_KEY` (AES-256-GCM) | `PEMA_SECRET_ENCRYPTION_KEY`, same wire format | `pema.config.secret_cipher`. |
| `data/` directory (SQLite, media, logs, credentials) | Postgres + object storage/local volume for files; `.local/` for dev logs (git-ignored) |  |

## Seams between packages (what you may rely on before the others land)

Each package runs in its own worktree and sees only the contracts of A. The seams below are Protocols in `pema_contracts` with fakes in `pema_contracts.testing`; real modules meet only in package G.

| Consumer | Needs | Contract |
|---|---|---|
| every package | `get_tuning`, `bot_time_zone` | `pema.config.runtime_tuning_settings` (done, A). 72 original defaults in `tuning_specs.py`. |
| every package | logger, zone time, secret cipher, DB session with clinic context | `pema.shared.logger`, `pema.shared.zone_time`, `pema.config.secret_cipher`, `pema.core.db.ClinicDatabase` (done, A). |
| C1, C2, S, D1 | who decides what leaves the system and what may be sent/run | `PolicyHooks` (default `PermissivePolicyHooks`); P implements. |
| C1 (bot router), C2 (personal router) | hand a merged batch to the worker | `TurnQueue`, `TurnJob`; `InMemoryTurnQueue` fake. |
| C2 turn processor, S | run the model, understand a failure | `AgentEngine`, `TurnCallbacks`; failures are `AgentTurnError(kind)`; `failed_turn_step`; D1 implements the engine. |
| C2 turn processor, S | save the trace of a turn | `UsageStore.save_turn_trace` / `append_step`; D2 implements. |
| C2 turn processor | messages that arrived while a turn runs | `PendingInbox`; C1 (batcher) implements over Redis. |
| C2 (outbound), S (delivery) | send one part | `ChannelPort.send_text` and the optional capability Protocols. |
| D1 | tools, history, memory, summary, usage, KB, MCP | `ToolRegistry`, `ConversationStore`, `KnowledgeSearch`, `McpToolProvider`, `TextGenerator`. |
| D4 `schedule_task`, B2 | create/list/cancel jobs | `SchedulerPort`; S implements. |
| S (job kind agent) | run an isolated turn | `AgentEngine` with `isolated=True` (injected, `pema.scheduler` never imports `pema.agent`). |
| D1, D4, P, C1, C2 | clinic data (care context, appointments, review items, identity, inbox) | `AgentFacingClinicActions`; B1 implements. In SQL: `clinic_agent` views and functions (migration 0003). |
| D2 stores, S, D3, D5 | Postgres tables | `agent.*` (migration 0002), RLS on `clinic_id`. |

## `src (root)`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/index-startup-order.test.ts` | 26 | `tests/test_startup_order.py` | G | startup order of the processes, adapted to api/worker/bridge |
| `src/index.ts` | 111 | `pema/bootstrap.py + pema/workers/main.py` | G | A created the skeleton bootstrap; G wires API, workers, bridge and the startup order (see index-startup-order.test.ts) |

## `src/agent`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/agent/agent-loop-conditions.ts` | 108 | `pema/agent/agent_loop_conditions.py` | D1 |  |
| `src/agent/agent-loop.test.ts` | 157 | `tests/agent/test_agent_loop.py` | D1 |  |
| `src/agent/agent-loop.ts` | 767 | `pema/agent/agent_loop.py` | D1 |  |
| `src/agent/agent-step-observer.test.ts` | 104 | `tests/agent/test_agent_step_observer.py` | D1 |  |
| `src/agent/agent-step-observer.ts` | 163 | `pema/agent/agent_step_observer.py` | D1 |  |
| `src/agent/agent-step-trace.test.ts` | 229 | `tests/agent/test_agent_step_trace.py` | D1 |  |
| `src/agent/agent-step-trace.ts` | 160 | `pema/agent/agent_step_trace.py` | D1 |  |
| `src/agent/agent-trace-store.test.ts` | 273 | `tests/conversation/test_agent_trace_store.py` | D2 | placed under conversation/ because it owns the agent.usage_steps table |
| `src/agent/agent-trace-store.ts` | 229 | `pema/conversation/agent_trace_store.py` | D2 | placed under conversation/ because it owns the agent.usage_steps table |
| `src/agent/agent-turn-content.test.ts` | 452 | `tests/agent/test_agent_turn_content.py` | D1 |  |
| `src/agent/agent-turn-content.ts` | 255 | `pema/agent/agent_turn_content.py` | D1 |  |
| `src/agent/batch-to-user-lines.ts` | 57 | `pema/agent/batch_to_user_lines.py` | D1 |  |
| `src/agent/cache-session-id.test.ts` | 96 | `tests/agent/test_cache_session_id.py` | D1 | x-session-id for router prompt caching; uses ThreadStore.get_thread_context_epoch |
| `src/agent/cache-session-id.ts` | 56 | `pema/agent/cache_session_id.py` | D1 | x-session-id for router prompt caching; uses ThreadStore.get_thread_context_epoch |
| `src/agent/failed-turn-trace.ts` | 65 | `packages/contracts/src/pema_contracts/turn_errors.py (failed_turn_step, AgentTurnError, ProviderErrorKind)` | A | done: moved to contracts so the channel pipeline (C2) and the scheduler (S) need not import pema.agent |
| `src/agent/google-base-url.test.ts` | 66 | `tests/agent/test_google_base_url.py` | D1 | Gemini base URL handling |
| `src/agent/history-to-model-messages.test.ts` | 294 | `tests/agent/test_history_to_model_messages.py` | D1 |  |
| `src/agent/history-to-model-messages.ts` | 141 | `pema/agent/history_to_model_messages.py` | D1 |  |
| `src/agent/llm-config-error.ts` | 40 | `pema/agent/llm_config_error.py` | D1 |  |
| `src/agent/llm-provider-safety.test.ts` | 116 | `tests/agent/test_llm_provider_safety.py` | D1 |  |
| `src/agent/llm-provider.ts` | 227 | `pema/agent/llm_provider.py` | D1 |  |
| `src/agent/llm-response-sanitizer.test.ts` | 97 | `tests/agent/test_llm_response_sanitizer.py` | D1 |  |
| `src/agent/llm-response-sanitizer.ts` | 74 | `pema/agent/llm_response_sanitizer.py` | D1 |  |
| `src/agent/memory-prompt-block.test.ts` | 174 | `tests/agent/test_memory_prompt_block.py` | D1 |  |
| `src/agent/memory-prompt-block.ts` | 76 | `pema/agent/memory_prompt_block.py` | D1 |  |
| `src/agent/mid-turn-injection.ts` | 171 | `pema/agent/mid_turn_injection.py` | D1 |  |
| `src/agent/model-vision-detection.test.ts` | 221 | `tests/agent/test_model_vision_detection.py` | D1 |  |
| `src/agent/model-vision-detection.ts` | 180 | `pema/agent/model_vision_detection.py` | D1 |  |
| `src/agent/persona-prompt.test.ts` | 326 | `tests/agent/test_persona_prompt.py` | D1 |  |
| `src/agent/persona-prompt.ts` | 162 | `pema/agent/persona_prompt.py` | D1 |  |
| `src/agent/persona-tool-rules.test.ts` | 123 | `tests/agent/test_persona_tool_rules.py` | D1 |  |
| `src/agent/persona-tool-rules.ts` | 146 | `pema/agent/persona_tool_rules.py` | D1 |  |
| `src/agent/prompt-leak-markers.ts` | 96 | `pema/agent/prompt_leak_markers.py` | D1 |  |
| `src/agent/provider-error-classifier.test.ts` | 229 | `tests/agent/test_provider_error_classifier.py` | D1 | SDK-specific classification stays here; run_turn raises AgentTurnError(kind) so consumers never see an SDK type |
| `src/agent/provider-error-classifier.ts` | 182 | `pema/agent/provider_error_classifier.py` | D1 | SDK-specific classification stays here; run_turn raises AgentTurnError(kind) so consumers never see an SDK type |
| `src/agent/reasoning-options.test.ts` | 78 | `tests/agent/test_reasoning_options.py` | D1 |  |
| `src/agent/reasoning-options.ts` | 78 | `pema/agent/reasoning_options.py` | D1 |  |
| `src/agent/run-agent-turn.test.ts` | 1083 | `tests/agent/test_run_agent_turn.py` | D1 |  |
| `src/agent/stream-text-result.ts` | 183 | `pema/agent/stream_text_result.py` | D1 | Vercel AI SDK stream result helper; Python: wrapper over openai streaming |
| `src/agent/streaming-model-test-helper.ts` | 67 | `pema/agent/streaming_model_test_helper.py` | D1 | test helper: a fake model that streams; Python: fake over the openai-compatible client |
| `src/agent/thread-summary-prompt-block.test.ts` | 151 | `tests/agent/test_thread_summary_prompt_block.py` | D1 |  |
| `src/agent/thread-summary-prompt-block.ts` | 44 | `pema/agent/thread_summary_prompt_block.py` | D1 |  |
| `src/agent/token-estimate.test.ts` | 175 | `tests/agent/test_token_estimate.py` | D1 |  |
| `src/agent/token-estimate.ts` | 211 | `pema/agent/token_estimate.py` | D1 |  |
| `src/agent/tool-call-signature.test.ts` | 101 | `tests/agent/test_tool_call_signature.py` | D1 |  |
| `src/agent/tool-call-signature.ts` | 80 | `pema/agent/tool_call_signature.py` | D1 |  |
| `src/agent/tool-loop-guard-thresholds.ts` | 53 | `pema/agent/tool_loop_guard_thresholds.py` | D1 |  |
| `src/agent/tool-loop-guard.test.ts` | 364 | `tests/agent/test_tool_loop_guard.py` | D1 |  |
| `src/agent/tool-loop-guard.ts` | 206 | `pema/agent/tool_loop_guard.py` | D1 |  |
| `src/agent/trim-context-to-budget.test.ts` | 207 | `tests/agent/test_trim_context_to_budget.py` | D1 |  |
| `src/agent/trim-context-to-budget.ts` | 135 | `pema/agent/trim_context_to_budget.py` | D1 |  |
| `src/agent/user-message-line.ts` | 74 | `pema/agent/user_message_line.py` | D1 |  |
| `src/agent/vision-rejection-fallback.test.ts` | 58 | `tests/agent/test_vision_rejection_fallback.py` | D1 |  |
| `src/agent/vision-rejection-fallback.ts` | 26 | `pema/agent/vision_rejection_fallback.py` | D1 |  |
| `src/agent/vision-sidecar.test.ts` | 196 | `tests/agent/test_vision_sidecar.py` | D1 |  |
| `src/agent/vision-sidecar.ts` | 197 | `pema/agent/vision_sidecar.py` | D1 |  |

## `src/agent/tools`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/agent/tools/add-reaction-tool.ts` | 44 | `pema/agent/tools/add_reaction_tool.py` | D4 |  |
| `src/agent/tools/clean-tool-caption.test.ts` | 77 | `tests/agent/tools/test_clean_tool_caption.py` | D4 |  |
| `src/agent/tools/clean-tool-caption.ts` | 55 | `pema/agent/tools/clean_tool_caption.py` | D4 |  |
| `src/agent/tools/create-document-tools.test.ts` | 209 | `tests/agent/tools/test_create_document_tools.py` | D4 |  |
| `src/agent/tools/create-document-tools.ts` | 147 | `pema/agent/tools/create_document_tools.py` | D4 |  |
| `src/agent/tools/create-image-tool-description.ts` | 61 | `pema/agent/tools/create_image_tool_description.py` | D4 |  |
| `src/agent/tools/create-image-tool.test.ts` | 392 | `tests/agent/tools/test_create_image_tool.py` | D4 |  |
| `src/agent/tools/create-image-tool.ts` | 197 | `pema/agent/tools/create_image_tool.py` | D4 |  |
| `src/agent/tools/draw-image-with-one-retry.test.ts` | 116 | `tests/agent/tools/test_draw_image_with_one_retry.py` | D4 |  |
| `src/agent/tools/draw-image-with-one-retry.ts` | 44 | `pema/agent/tools/draw_image_with_one_retry.py` | D4 |  |
| `src/agent/tools/get-datetime-tool.ts` | 21 | `pema/agent/tools/get_datetime_tool.py` | D4 |  |
| `src/agent/tools/get-group-info-tool.ts` | 45 | `pema/agent/tools/get_group_info_tool.py` | D4 |  |
| `src/agent/tools/index.ts` | 14 | `pema/agent/tools/index.py` | D4 |  |
| `src/agent/tools/kb-pack-result.test.ts` | 100 | `tests/agent/tools/test_kb_pack_result.py` | D4 |  |
| `src/agent/tools/kb-pack-result.ts` | 114 | `pema/agent/tools/kb_pack_result.py` | D4 |  |
| `src/agent/tools/kb-search-tool-description.ts` | 11 | `pema/agent/tools/kb_search_tool_description.py` | D4 |  |
| `src/agent/tools/kb-search-tool-sql-error.test.ts` | 122 | `tests/agent/tools/test_kb_search_tool_sql_error.py` | D4 |  |
| `src/agent/tools/kb-search-tool.test.ts` | 660 | `tests/agent/tools/test_kb_search_tool.py` | D4 | calls KnowledgeSearch (pema_contracts.knowledge); default-deny stays in D3 |
| `src/agent/tools/kb-search-tool.ts` | 101 | `pema/agent/tools/kb_search_tool.py` | D4 | calls KnowledgeSearch (pema_contracts.knowledge); default-deny stays in D3 |
| `src/agent/tools/khu-dai-phan-cach-gia.ts` | 79 | `pema/agent/tools/khu_dai_phan_cach_gia.py` | D4 |  |
| `src/agent/tools/khu-gia-mao-nhan-nguon.test.ts` | 236 | `tests/agent/tools/test_khu_gia_mao_nhan_nguon.py` | D4 |  |
| `src/agent/tools/khu-gia-mao-nhan-nguon.ts` | 146 | `pema/agent/tools/khu_gia_mao_nhan_nguon.py` | D4 |  |
| `src/agent/tools/mcp-registry-integration.test.ts` | 47 | `tests/agent/tools/test_mcp_registry_integration.py` | D4 | registry x MCP provider integration test; use a fake McpToolProvider |
| `src/agent/tools/mcp-tool-provider.ts` | 16 | `pema/mcp/mcp_tool_provider.py` | D5 | ToolSpecs of the MCP servers bound to an agent (McpToolProvider) |
| `src/agent/tools/read-image-tool.test.ts` | 211 | `tests/agent/tools/test_read_image_tool.py` | D4 |  |
| `src/agent/tools/read-image-tool.ts` | 99 | `pema/agent/tools/read_image_tool.py` | D4 |  |
| `src/agent/tools/save-memory-tool.ts` | 145 | `pema/agent/tools/save_memory_tool.py` | D4 | calls MemoryStore + PolicyHooks.allow_memory_write; off for patient content in patient_channel |
| `src/agent/tools/schedule-task-actions.ts` | 177 | `pema/agent/tools/schedule_task_actions.py` | D4 |  |
| `src/agent/tools/schedule-task-tool-description.ts` | 24 | `pema/agent/tools/schedule_task_tool_description.py` | D4 |  |
| `src/agent/tools/schedule-task-tool-schema.ts` | 188 | `pema/agent/tools/schedule_task_tool_schema.py` | D4 |  |
| `src/agent/tools/schedule-task-tool-sql-error.test.ts` | 125 | `tests/agent/tools/test_schedule_task_tool_sql_error.py` | D4 |  |
| `src/agent/tools/schedule-task-tool.test.ts` | 631 | `tests/agent/tools/test_schedule_task_tool.py` | D4 | calls SchedulerPort + PolicyHooks.check_job |
| `src/agent/tools/schedule-task-tool.ts` | 96 | `pema/agent/tools/schedule_task_tool.py` | D4 | calls SchedulerPort + PolicyHooks.check_job |
| `src/agent/tools/send-attachment-with-caption.test.ts` | 99 | `tests/agent/tools/test_send_attachment_with_caption.py` | D4 |  |
| `src/agent/tools/send-attachment-with-caption.ts` | 46 | `pema/agent/tools/send_attachment_with_caption.py` | D4 |  |
| `src/agent/tools/send-file-tool.ts` | 78 | `pema/agent/tools/send_file_tool.py` | D4 |  |
| `src/agent/tools/sent-by-tool-note.ts` | 66 | `pema/agent/tools/sent_by_tool_note.py` | D4 |  |
| `src/agent/tools/simple-tools.test.ts` | 208 | `tests/agent/tools/test_simple_tools.py` | D4 |  |
| `src/agent/tools/tag-ky-tu-an.ts` | 48 | `pema/agent/tools/tag_ky_tu_an.py` | D4 |  |
| `src/agent/tools/tag-member-tool.test.ts` | 98 | `tests/agent/tools/test_tag_member_tool.py` | D4 |  |
| `src/agent/tools/tag-member-tool.ts` | 54 | `pema/agent/tools/tag_member_tool.py` | D4 |  |
| `src/agent/tools/tai-video-tool-description.ts` | 27 | `pema/agent/tools/tai_video_tool_description.py` | D4 |  |
| `src/agent/tools/tai-video-tool.test.ts` | 406 | `tests/agent/tools/test_tai_video_tool.py` | D4 |  |
| `src/agent/tools/tai-video-tool.ts` | 235 | `pema/agent/tools/tai_video_tool.py` | D4 |  |
| `src/agent/tools/tim-lich-hen-trung.ts` | 102 | `pema/agent/tools/tim_lich_hen_trung.py` | D4 |  |
| `src/agent/tools/tool-catalog-action.ts` | 123 | `pema/agent/tools/tool_catalog_action.py` | D4 |  |
| `src/agent/tools/tool-catalog-read.test.ts` | 42 | `tests/agent/tools/test_tool_catalog_read.py` | D4 |  |
| `src/agent/tools/tool-catalog-read.ts` | 94 | `pema/agent/tools/tool_catalog_read.py` | D4 |  |
| `src/agent/tools/tool-catalog-types.ts` | 183 | `pema/agent/tools/tool_catalog_types.py` | D4 |  |
| `src/agent/tools/tool-catalog.ts` | 19 | `pema/agent/tools/tool_catalog.py` | D4 |  |
| `src/agent/tools/tool-failure-result-test-helper.ts` | 41 | `pema/agent/tools/tool_failure_result_test_helper.py` | D4 | test helper |
| `src/agent/tools/tool-failure-result.ts` | 76 | `pema/agent/tools/tool_failure_result.py` | D4 |  |
| `src/agent/tools/tool-registry.test.ts` | 268 | `tests/agent/tools/test_tool_registry.py` | D4 |  |
| `src/agent/tools/tool-registry.ts` | 106 | `pema/agent/tools/tool_registry.py` | D4 |  |
| `src/agent/tools/tool-schema-provider-compat.test.ts` | 226 | `tests/agent/tools/test_tool_schema_provider_compat.py` | D4 |  |
| `src/agent/tools/web-fetch-tool.ts` | 93 | `pema/agent/tools/web_fetch_tool.py` | D4 |  |
| `src/agent/tools/web-search-tool.ts` | 50 | `pema/agent/tools/web_search_tool.py` | D4 |  |
| `src/agent/tools/web-tools-failure-marking.test.ts` | 156 | `tests/agent/tools/test_web_tools_failure_marking.py` | D4 |  |
| `src/agent/tools/wrap-untrusted-content.test.ts` | 337 | `tests/agent/tools/test_wrap_untrusted_content.py` | D4 |  |
| `src/agent/tools/wrap-untrusted-content.ts` | 154 | `pema/agent/tools/wrap_untrusted_content.py` | D4 |  |

## `src/config`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/config/account-agent-stores.test.ts` | 164 | `tests/config/test_account_agent_stores.py` | D2 |  |
| `src/config/account-store.test.ts` | 60 | `tests/config/test_account_store.py` | D2 | agent.accounts; AccountConfig is in pema_contracts.agents |
| `src/config/account-store.ts` | 270 | `pema/config/account_store.py` | D2 | agent.accounts; AccountConfig is in pema_contracts.agents |
| `src/config/accounts.ts` | 49 | `pema/config/accounts.py` | D2 | seed reader; no accounts.json is committed (synthetic examples only) |
| `src/config/agent-store.ts` | 178 | `pema/config/agent_store.py` | D2 | agent.agents; AgentProfile is in pema_contracts.agents |
| `src/config/dashboard-host-binding.test.ts` | 108 | no port | - | Hono dashboard host/port binding; FastAPI/uvicorn binding is deployment config (F) |
| `src/config/decrypt-failure.test.ts` | 109 | `tests/config/test_decrypt_failure.py` | D1 | behaviour of runtime-llm-settings when the key changes; uses pema.config.secret_cipher (A) |
| `src/config/env-toi-thieu.test.ts` | 131 | `tests/config/test_env_toi_thieu.py` | D1 | minimal-env boot test |
| `src/config/env.ts` | 495 | `pema/config/env.py (platform subset, by A) + pema/config/env_llm.py (LLM settings, by D1)` | A, D1 | A ported platform settings; defaults of the 72 tuning parameters are in tuning_specs.py (generated). D1 ports the rest |
| `src/config/kb-extract-timeout-boot-guard.test.ts` | 93 | `tests/config/test_kb_extract_timeout_boot_guard.py` | D3 | boot guard for KB_EXTRACT_* limits; lives with the ingest worker config |
| `src/config/llm-provider-kind.ts` | 30 | `packages/contracts/src/pema_contracts/agents.py (LlmProviderKind)` | A | done |
| `src/config/parse-disabled-tools.ts` | 26 | `pema/config/parse_disabled_tools.py` | D2 |  |
| `src/config/runtime-image-settings.test.ts` | 72 | `tests/config/test_runtime_image_settings.py` | D4 | image generation settings; route is in admin_tools.py |
| `src/config/runtime-image-settings.ts` | 106 | `pema/config/runtime_image_settings.py` | D4 | image generation settings; route is in admin_tools.py |
| `src/config/runtime-llm-settings.test.ts` | 114 | `tests/config/test_runtime_llm_settings.py` | D1 |  |
| `src/config/runtime-llm-settings.ts` | 131 | `pema/config/runtime_llm_settings.py` | D1 |  |
| `src/config/runtime-tool-settings.test.ts` | 58 | `tests/config/test_runtime_tool_settings.py` | D4 | web_search / web_fetch chain settings |
| `src/config/runtime-tool-settings.ts` | 122 | `pema/config/runtime_tool_settings.py` | D4 | web_search / web_fetch chain settings |
| `src/config/runtime-tuning-settings.test.ts` | 258 | `tests/config/test_runtime_tuning_settings.py` | A, D1 | A wrote the cross-package API (get_tuning, bot_time_zone, provider hook) + contract tests; D1 adds the DB-backed provider, list_tuning and validate_tuning with the cross rules |
| `src/config/runtime-tuning-settings.ts` | 257 | `pema/config/runtime_tuning_settings.py` | A, D1 | A wrote the cross-package API (get_tuning, bot_time_zone, provider hook) + contract tests; D1 adds the DB-backed provider, list_tuning and validate_tuning with the cross rules |
| `src/config/runtime-vision-settings.test.ts` | 80 | `tests/config/test_runtime_vision_settings.py` | D1 |  |
| `src/config/runtime-vision-settings.ts` | 134 | `pema/config/runtime_vision_settings.py` | D1 |  |
| `src/config/secret-cipher-core.ts` | 39 | `pema/config/secret_cipher_core.py` | A | done |
| `src/config/secret-cipher.ts` | 24 | `pema/config/secret_cipher.py` | A | done |
| `src/config/tuning-definitions.ts` | 822 | `pema/config/tuning_specs.py (A, generated data) + pema/config/tuning_definitions.py (D1: labels, hints, groups)` | A, D1 | the 72 keys, defaults and bounds are done; D1 adds the UI metadata |
| `src/config/tuning-groups.test.ts` | 60 | `tests/config/test_tuning_groups.py` | D1 |  |
| `src/config/tuning-number-presets.test.ts` | 160 | `tests/config/test_tuning_number_presets.py` | D1 |  |
| `src/config/tuning-number-presets.ts` | 133 | `pema/config/tuning_number_presets.py` | D1 |  |

## `src/conversation`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/conversation/contact-store.test.ts` | 89 | `tests/conversation/test_contact_store.py` | D2 |  |
| `src/conversation/contact-store.ts` | 103 | `pema/conversation/contact_store.py` | D2 |  |
| `src/conversation/database-pragma.test.ts` | 60 | no port | - | SQLite PRAGMA (WAL, synchronous); no Postgres equivalent |
| `src/conversation/database.ts` | 346 | `pema/core/db.py + alembic 0001..0003` | A | SQLite -> Postgres: schema is the Alembic revisions, access is ClinicDatabase (RLS) |
| `src/conversation/friend-request-store.test.ts` | 103 | `tests/channels/zalo_personal/test_friend_request_store.py` | C2 | table agent.friend_requests; feature of the personal account |
| `src/conversation/friend-request-store.ts` | 108 | `pema/channels/zalo_personal/friend_request_store.py` | C2 | table agent.friend_requests; feature of the personal account |
| `src/conversation/friend-schema.ts` | 31 | `alembic 0002 (agent.friend_requests)` | A | done |
| `src/conversation/history-store.test.ts` | 181 | `tests/conversation/test_history_store.py` | D2 |  |
| `src/conversation/history-store.ts` | 177 | `pema/conversation/history_store.py` | D2 |  |
| `src/conversation/image-description-store.ts` | 48 | `pema/conversation/image_description_store.py` | D2 |  |
| `src/conversation/media-store.test.ts` | 110 | `tests/conversation/test_media_store.py` | D2 | image persistence; object storage or local volume (D2 decides, PLAN-AI01 section 3) |
| `src/conversation/media-store.ts` | 194 | `pema/conversation/media_store.py` | D2 | image persistence; object storage or local volume (D2 decides, PLAN-AI01 section 3) |
| `src/conversation/memory-edit-store.test.ts` | 188 | `tests/conversation/test_memory_edit_store.py` | D2 |  |
| `src/conversation/memory-edit-store.ts` | 108 | `pema/conversation/memory_edit_store.py` | D2 |  |
| `src/conversation/memory-store.test.ts` | 169 | `tests/conversation/test_memory_store.py` | D2 |  |
| `src/conversation/memory-store.ts` | 158 | `pema/conversation/memory_store.py` | D2 |  |
| `src/conversation/startup-backfill.test.ts` | 61 | no port | - | one-time upgrade backfill of an older SQLite file; Postgres starts clean |
| `src/conversation/startup-backfill.ts` | 18 | no port | - | one-time upgrade backfill of an older SQLite file; Postgres starts clean |
| `src/conversation/thread-store.test.ts` | 79 | `tests/conversation/test_thread_store.py` | D2 |  |
| `src/conversation/thread-store.ts` | 200 | `pema/conversation/thread_store.py` | D2 |  |
| `src/conversation/thread-summarizer.test.ts` | 203 | `tests/conversation/test_thread_summarizer.py` | D2 |  |
| `src/conversation/thread-summarizer.ts` | 168 | `pema/conversation/thread_summarizer.py` | D2 |  |
| `src/conversation/usage-store.test.ts` | 92 | `tests/conversation/test_usage_store.py` | D2 |  |
| `src/conversation/usage-store.ts` | 111 | `pema/conversation/usage_store.py` | D2 |  |
| `src/conversation/wipe-thread-context.test.ts` | 256 | `tests/conversation/test_wipe_thread_context.py` | D2 |  |
| `src/conversation/wipe-thread-context.ts` | 135 | `pema/conversation/wipe_thread_context.py` | D2 |  |
| `src/conversation/xoa-han-session.test.ts` | 119 | `tests/conversation/test_xoa_han_session.py` | D2 | deletes one whole session (conversation) from the Sessions page; route `DELETE /admin/threads/{account_id}/{thread_id}` |
| `src/conversation/xoa-han-session.ts` | 62 | `pema/conversation/xoa_han_session.py` | D2 | deletes one whole session (conversation) from the Sessions page; route `DELETE /admin/threads/{account_id}/{thread_id}` |

## `src/documents`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/documents/document-content-schema.test.ts` | 161 | `tests/documents/test_document_content_schema.py` | D4 |  |
| `src/documents/document-content-schema.ts` | 215 | `pema/documents/document_content_schema.py` | D4 |  |
| `src/documents/document-limits.test.ts` | 133 | `tests/documents/test_document_limits.py` | D4 |  |
| `src/documents/document-limits.ts` | 120 | `pema/documents/document_limits.py` | D4 |  |
| `src/documents/document-rate-limit.test.ts` | 81 | `tests/documents/test_document_rate_limit.py` | D4 |  |
| `src/documents/document-rate-limit.ts` | 24 | `pema/documents/document_rate_limit.py` | D4 |  |
| `src/documents/docx-text-runs.ts` | 23 | `pema/documents/docx_text_runs.py` | D4 |  |
| `src/documents/render-docx-styles.ts` | 66 | `pema/documents/render_docx_styles.py` | D4 |  |
| `src/documents/render-docx-tables.ts` | 96 | `pema/documents/render_docx_tables.py` | D4 |  |
| `src/documents/render-docx.test.ts` | 167 | `tests/documents/test_render_docx.py` | D4 |  |
| `src/documents/render-docx.ts` | 141 | `pema/documents/render_docx.py` | D4 |  |
| `src/documents/render-xlsx-styles.ts` | 80 | `pema/documents/render_xlsx_styles.py` | D4 |  |
| `src/documents/render-xlsx.test.ts` | 259 | `tests/documents/test_render_xlsx.py` | D4 |  |
| `src/documents/render-xlsx.ts` | 186 | `pema/documents/render_xlsx.py` | D4 |  |
| `src/documents/spreadsheet-formula-values.ts` | 96 | `pema/documents/spreadsheet_formula_values.py` | D4 |  |
| `src/documents/xlsx-themes.ts` | 47 | `pema/documents/xlsx_themes.py` | D4 |  |

## `src/images`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/images/image-generation-client.test.ts` | 305 | `tests/images/test_image_generation_client.py` | D4 |  |
| `src/images/image-generation-client.ts` | 161 | `pema/images/image_generation_client.py` | D4 |  |
| `src/images/image-rate-limit.test.ts` | 48 | `tests/images/test_image_rate_limit.py` | D4 |  |
| `src/images/image-rate-limit.ts` | 22 | `pema/images/image_rate_limit.py` | D4 |  |
| `src/images/image-retry-policy.test.ts` | 51 | `tests/images/test_image_retry_policy.py` | D4 |  |
| `src/images/image-retry-policy.ts` | 53 | `pema/images/image_retry_policy.py` | D4 |  |
| `src/images/read-image-sse-stream.test.ts` | 145 | `tests/images/test_read_image_sse_stream.py` | D4 |  |
| `src/images/read-image-sse-stream.ts` | 135 | `pema/images/read_image_sse_stream.py` | D4 |  |

## `src/knowledge`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/knowledge/chay-trich-xuat-tach-luong.test.ts` | 269 | `tests/knowledge/test_chay_trich_xuat_tach_luong.py` | D3 |  |
| `src/knowledge/chay-trich-xuat-tach-luong.ts` | 190 | `pema/knowledge/chay_trich_xuat_tach_luong.py` | D3 |  |
| `src/knowledge/chunk-text.test.ts` | 199 | `tests/knowledge/test_chunk_text.py` | D3 |  |
| `src/knowledge/chunk-text.ts` | 170 | `pema/knowledge/chunk_text.py` | D3 |  |
| `src/knowledge/doc-text-extract.test.ts` | 27 | `tests/knowledge/test_doc_text_extract.py` | D3 |  |
| `src/knowledge/doc-text-extract.ts` | 35 | `pema/knowledge/doc_text_extract.py` | D3 |  |
| `src/knowledge/docx-sax-paragraph-builder.ts` | 188 | `pema/knowledge/docx_sax_paragraph_builder.py` | D3 |  |
| `src/knowledge/docx-sax-table-tracker.ts` | 88 | `pema/knowledge/docx_sax_table_tracker.py` | D3 |  |
| `src/knowledge/don-doan-mo-coi.test.ts` | 84 | `tests/knowledge/test_don_doan_mo_coi.py` | D3 |  |
| `src/knowledge/don-doan-mo-coi.ts` | 36 | `pema/knowledge/don_doan_mo_coi.py` | D3 |  |
| `src/knowledge/extract-docx-text.test.ts` | 277 | `tests/knowledge/test_extract_docx_text.py` | D3 |  |
| `src/knowledge/extract-docx-text.ts` | 53 | `pema/knowledge/extract_docx_text.py` | D3 |  |
| `src/knowledge/extract-pdf-text.test.ts` | 50 | `tests/knowledge/test_extract_pdf_text.py` | D3 |  |
| `src/knowledge/extract-pdf-text.ts` | 27 | `pema/knowledge/extract_pdf_text.py` | D3 |  |
| `src/knowledge/extract-xlsx-text.test.ts` | 289 | `tests/knowledge/test_extract_xlsx_text.py` | D3 |  |
| `src/knowledge/extract-xlsx-text.ts` | 66 | `pema/knowledge/extract_xlsx_text.py` | D3 |  |
| `src/knowledge/fixtures/README.md` | 65 | `tests/knowledge/fixtures/README.md` | D3 | fixture copied as-is (MIT notice in THIRD_PARTY_NOTICES.md); must stay synthetic |
| `src/knowledge/fixtures/excel-o-rong-co-dinh-dang.xlsx` | 8988 B | `tests/knowledge/fixtures/excel-o-rong-co-dinh-dang.xlsx` | D3 | fixture copied as-is (MIT notice in THIRD_PARTY_NOTICES.md); must stay synthetic |
| `src/knowledge/fixtures/word-table.docx` | 13776 B | `tests/knowledge/fixtures/word-table.docx` | D3 | fixture copied as-is (MIT notice in THIRD_PARTY_NOTICES.md); must stay synthetic |
| `src/knowledge/fixtures/word-tabstop.docx` | 13482 B | `tests/knowledge/fixtures/word-tabstop.docx` | D3 | fixture copied as-is (MIT notice in THIRD_PARTY_NOTICES.md); must stay synthetic |
| `src/knowledge/hop-nhat-rrf.test.ts` | 41 | `tests/knowledge/test_hop_nhat_rrf.py` | D3 |  |
| `src/knowledge/hop-nhat-rrf.ts` | 42 | `pema/knowledge/hop_nhat_rrf.py` | D3 |  |
| `src/knowledge/kb-agent-binding.test.ts` | 90 | `tests/knowledge/test_kb_agent_binding.py` | D3 |  |
| `src/knowledge/kb-agent-binding.ts` | 110 | `pema/knowledge/kb_agent_binding.py` | D3 |  |
| `src/knowledge/kb-chunk-store.test.ts` | 162 | `tests/knowledge/test_kb_chunk_store.py` | D3 |  |
| `src/knowledge/kb-chunk-store.ts` | 121 | `pema/knowledge/kb_chunk_store.py` | D3 |  |
| `src/knowledge/kb-extract-worker.ts` | 46 | `pema/knowledge/kb_extract_worker.py` | D3 |  |
| `src/knowledge/kb-file-store.test.ts` | 54 | `tests/knowledge/test_kb_file_store.py` | D3 |  |
| `src/knowledge/kb-file-store.ts` | 46 | `pema/knowledge/kb_file_store.py` | D3 |  |
| `src/knowledge/kb-fts-query.test.ts` | 37 | `tests/knowledge/test_kb_fts_query.py` | D3 | SQLite FTS5 MATCH query building -> Postgres to_tsquery over the diacritics-folded column |
| `src/knowledge/kb-fts-query.ts` | 68 | `pema/knowledge/kb_fts_query.py` | D3 | SQLite FTS5 MATCH query building -> Postgres to_tsquery over the diacritics-folded column |
| `src/knowledge/kb-ingest-worker-attempt-limit.test.ts` | 151 | `tests/knowledge/test_kb_ingest_worker_attempt_limit.py` | D3 |  |
| `src/knowledge/kb-ingest-worker-empty-chunks.test.ts` | 81 | `tests/knowledge/test_kb_ingest_worker_empty_chunks.py` | D3 |  |
| `src/knowledge/kb-ingest-worker-real-timeout-branch.test.ts` | 73 | `tests/knowledge/test_kb_ingest_worker_real_timeout_branch.py` | D3 |  |
| `src/knowledge/kb-ingest-worker.test.ts` | 243 | `tests/knowledge/test_kb_ingest_worker.py` | D3 |  |
| `src/knowledge/kb-ingest-worker.ts` | 200 | `pema/knowledge/kb_ingest_worker.py` | D3 |  |
| `src/knowledge/kb-schema.ts` | 83 | `alembic 0002 (agent.kb_document, kb_chunk with tsvector + vector(1024), agent_kb_document)` | A | done |
| `src/knowledge/kb-search-quality.test.ts` | 162 | `tests/knowledge/test_kb_search_quality.py` | D3 |  |
| `src/knowledge/kb-search.test.ts` | 149 | `tests/knowledge/test_kb_search.py` | D3 |  |
| `src/knowledge/kb-search.ts` | 78 | `pema/knowledge/kb_search.py` | D3 |  |
| `src/knowledge/kb-slow-docx-test-fixture.ts` | 19 | `pema/knowledge/kb_slow_docx_test_fixture.py` | D3 | test helper |
| `src/knowledge/kb-source-queries.test.ts` | 85 | `tests/knowledge/test_kb_source_queries.py` | D3 |  |
| `src/knowledge/kb-source-queries.ts` | 138 | `pema/knowledge/kb_source_queries.py` | D3 |  |
| `src/knowledge/kb-source-store.test.ts` | 98 | `tests/knowledge/test_kb_source_store.py` | D3 |  |
| `src/knowledge/kb-source-store.ts` | 168 | `pema/knowledge/kb_source_store.py` | D3 |  |
| `src/knowledge/ooxml-limits.ts` | 181 | `pema/knowledge/ooxml_limits.py` | D3 |  |
| `src/knowledge/ooxml-zip-test-helper.ts` | 231 | `pema/knowledge/ooxml_zip_test_helper.py` | D3 | test helper |
| `src/knowledge/xlsx-sax-shared-strings.ts` | 67 | `pema/knowledge/xlsx_sax_shared_strings.py` | D3 |  |
| `src/knowledge/xlsx-sax-sheet-builder.test.ts` | 103 | `tests/knowledge/test_xlsx_sax_sheet_builder.py` | D3 |  |
| `src/knowledge/xlsx-sax-sheet-builder.ts` | 216 | `pema/knowledge/xlsx_sax_sheet_builder.py` | D3 |  |

## `src/mcp`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/mcp/mcp-agent-binding-cleanup.test.ts` | 30 | `tests/mcp/test_mcp_agent_binding_cleanup.py` | D5 |  |
| `src/mcp/mcp-agent-binding.test.ts` | 42 | `tests/mcp/test_mcp_agent_binding.py` | D5 |  |
| `src/mcp/mcp-agent-binding.ts` | 52 | `pema/mcp/mcp_agent_binding.py` | D5 |  |
| `src/mcp/mcp-client-connect.test.ts` | 26 | `tests/mcp/test_mcp_client_connect.py` | D5 |  |
| `src/mcp/mcp-client-connect.ts` | 54 | `pema/mcp/mcp_client_connect.py` | D5 |  |
| `src/mcp/mcp-connection-pool.ts` | 171 | `pema/mcp/mcp_connection_pool.py` | D5 |  |
| `src/mcp/mcp-manager.test.ts` | 181 | `tests/mcp/test_mcp_manager.py` | D5 |  |
| `src/mcp/mcp-manager.ts` | 108 | `pema/mcp/mcp_manager.py` | D5 |  |
| `src/mcp/mcp-schema.test.ts` | 61 | `tests/mcp/test_mcp_schema.py` | D5 | table/default-deny test, adapted to Postgres |
| `src/mcp/mcp-schema.ts` | 38 | `alembic 0002 (agent.mcp_servers, agent_mcp_servers)` | A | done |
| `src/mcp/mcp-server-store.test.ts` | 55 | `tests/mcp/test_mcp_server_store.py` | D5 |  |
| `src/mcp/mcp-server-store.ts` | 154 | `pema/mcp/mcp_server_store.py` | D5 |  |
| `src/mcp/mcp-tool-definition.test.ts` | 135 | `tests/mcp/test_mcp_tool_definition.py` | D5 |  |
| `src/mcp/mcp-tool-definition.ts` | 180 | `pema/mcp/mcp_tool_definition.py` | D5 |  |
| `src/mcp/mcp-tool-drift.test.ts` | 54 | `tests/mcp/test_mcp_tool_drift.py` | D5 |  |
| `src/mcp/mcp-tool-drift.ts` | 33 | `pema/mcp/mcp_tool_drift.py` | D5 |  |
| `src/mcp/mcp-types.ts` | 46 | `pema/mcp/mcp_types.py` | D5 |  |

## `src/middleware`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/middleware/allowlist-filter.test.ts` | 139 | `tests/middleware/test_allowlist_filter.py` | C1 |  |
| `src/middleware/allowlist-filter.ts` | 61 | `pema/middleware/allowlist_filter.py` | C1 |  |
| `src/middleware/message-batcher.test.ts` | 695 | `tests/middleware/test_message_batcher.py` | C1 | debounce + PendingInbox (mid-turn injection) over Redis |
| `src/middleware/message-batcher.ts` | 337 | `pema/middleware/message_batcher.py` | C1 | debounce + PendingInbox (mid-turn injection) over Redis |
| `src/middleware/rate-limiter.test.ts` | 56 | `tests/middleware/test_rate_limiter.py` | C1 |  |
| `src/middleware/rate-limiter.ts` | 51 | `pema/middleware/rate_limiter.py` | C1 |  |
| `src/middleware/thread-run-chain.ts` | 115 | `pema/middleware/thread_run_chain.py` | C1 | serialises turns per (account, thread): in-process chain -> Redis lock behind pema_contracts.agent_turn.ThreadLock |

## `src/scheduler`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/scheduler/delivery-attempt-store.test.ts` | 71 | `tests/scheduler/test_delivery_attempt_store.py` | S |  |
| `src/scheduler/delivery-attempt-store.ts` | 32 | `pema/scheduler/delivery_attempt_store.py` | S |  |
| `src/scheduler/job-run-log-store.test.ts` | 91 | `tests/scheduler/test_job_run_log_store.py` | S |  |
| `src/scheduler/job-run-log-store.ts` | 113 | `pema/scheduler/job_run_log_store.py` | S |  |
| `src/scheduler/lich-hen-kenh-bot.test.ts` | 363 | `tests/scheduler/test_lich_hen_kenh_bot.py` | S |  |
| `src/scheduler/next-run.test.ts` | 141 | `tests/scheduler/test_next_run.py` | S |  |
| `src/scheduler/next-run.ts` | 117 | `pema/scheduler/next_run.py` | S |  |
| `src/scheduler/proactive-send-counter-store.test.ts` | 137 | `tests/scheduler/test_proactive_send_counter_store.py` | S |  |
| `src/scheduler/proactive-send-counter-store.ts` | 144 | `pema/scheduler/proactive_send_counter_store.py` | S |  |
| `src/scheduler/proactive-send-guard.test.ts` | 412 | `tests/scheduler/test_proactive_send_guard.py` | S |  |
| `src/scheduler/proactive-send-guard.ts` | 219 | `pema/scheduler/proactive_send_guard.py` | S |  |
| `src/scheduler/proactive-send-queue.ts` | 64 | `pema/scheduler/proactive_send_queue.py` | S |  |
| `src/scheduler/run-scheduled-job-trial.test.ts` | 170 | `tests/scheduler/test_run_scheduled_job_trial.py` | S |  |
| `src/scheduler/run-scheduled-job-trial.ts` | 149 | `pema/scheduler/run_scheduled_job_trial.py` | S |  |
| `src/scheduler/run-scheduled-job.test.ts` | 719 | `tests/scheduler/test_run_scheduled_job.py` | S |  |
| `src/scheduler/run-scheduled-job.ts` | 283 | `pema/scheduler/run_scheduled_job.py` | S |  |
| `src/scheduler/schedule-parser.test.ts` | 122 | `tests/scheduler/test_schedule_parser.py` | S |  |
| `src/scheduler/schedule-parser.ts` | 143 | `pema/scheduler/schedule_parser.py` | S |  |
| `src/scheduler/scheduled-job-cap-guard.ts` | 140 | `pema/scheduler/scheduled_job_cap_guard.py` | S |  |
| `src/scheduler/scheduled-job-conclude.ts` | 71 | `pema/scheduler/scheduled_job_conclude.py` | S |  |
| `src/scheduler/scheduled-job-list-store.ts` | 27 | `pema/scheduler/scheduled_job_list_store.py` | S |  |
| `src/scheduler/scheduled-job-prompt.test.ts` | 65 | `tests/scheduler/test_scheduled_job_prompt.py` | S |  |
| `src/scheduler/scheduled-job-prompt.ts` | 65 | `pema/scheduler/scheduled_job_prompt.py` | S |  |
| `src/scheduler/scheduled-job-record.ts` | 112 | `pema/scheduler/scheduled_job_record.py` | S |  |
| `src/scheduler/scheduled-job-reply-target.ts` | 62 | `pema/scheduler/scheduled_job_reply_target.py` | S |  |
| `src/scheduler/scheduled-job-send.test.ts` | 236 | `tests/scheduler/test_run_scheduled_job.py` | S |  |
| `src/scheduler/scheduled-job-send.ts` | 177 | `pema/scheduler/scheduled_job_send.py` | S |  |
| `src/scheduler/scheduled-job-store.test.ts` | 364 | `tests/scheduler/test_scheduled_job_store.py` | S |  |
| `src/scheduler/scheduled-job-store.ts` | 285 | `pema/scheduler/scheduled_job_store.py` | S |  |
| `src/scheduler/scheduled-job-thread-cap.ts` | 27 | `pema/scheduler/scheduled_job_thread_cap.py` | S |  |
| `src/scheduler/scheduler-loop.test.ts` | 687 | `tests/scheduler/test_scheduler_loop.py` | S |  |
| `src/scheduler/scheduler-loop.ts` | 235 | `pema/scheduler/scheduler_loop.py` | S |  |
| `src/scheduler/silent-sentinel.test.ts` | 50 | `tests/scheduler/test_silent_sentinel.py` | S |  |
| `src/scheduler/silent-sentinel.ts` | 59 | `pema/scheduler/silent_sentinel.py` | S |  |

## `src/server`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/server/client-ip.test.ts` | 36 | `tests/api/test_client_ip.py` | B1 | client IP for login rate limiting |
| `src/server/client-ip.ts` | 42 | `pema/api/client_ip.py` | B1 | client IP for login rate limiting |
| `src/server/dashboard-auth.test.ts` | 109 | `tests/api/test_dashboard_auth.py` | B1 | password+cookie dashboard auth -> JWT cookie, RBAC (pema.clinic.rbac) |
| `src/server/dashboard-auth.ts` | 137 | `pema/api/dashboard_auth.py` | B1 | password+cookie dashboard auth -> JWT cookie, RBAC (pema.clinic.rbac) |
| `src/server/dashboard-password-route.test.ts` | 108 | `tests/api/test_dashboard_password_route.py` | B1 | route `POST /auth/password` added in the final integration round; 204 with the same cookie, 422 (not 400) for a short password |
| `src/server/dashboard-password-store.test.ts` | 117 | `tests/api/test_dashboard_password_store.py` | B1 | single dashboard password -> per-user argon2 hashes in clinic.user_account |
| `src/server/dashboard-password-store.ts` | 106 | `pema/api/dashboard_password_store.py` | B1 | single dashboard password -> per-user argon2 hashes in clinic.user_account |
| `src/server/dashboard-server-mcp-mount.test.ts` | 25 | `tests/api/test_dashboard_server_mcp_mount.py` | D5 | MCP routes mounted on the app; adapt to the router skeleton |
| `src/server/dashboard-server.test.ts` | 446 | `tests/test_openapi_skeleton.py` | A | done: skeleton test (health live, everything else 501 with the error envelope, openapi.json up to date) |
| `src/server/dashboard-server.ts` | 248 | `pema/bootstrap.py + pema/api/router.py` | A | done: FastAPI app factory, routers per owner |
| `src/server/dashboard-session-store.ts` | 71 | `pema/api/dashboard_session_store.py` | B1 | server-side sessions -> JWT (revocation list if needed) |
| `src/server/overview-stats.test.ts` | 73 | `tests/conversation/test_overview_stats.py` | D2 | getAccountStats / getSystemInfo; UsageStore.get_account_stats |
| `src/server/overview-stats.ts` | 76 | `pema/conversation/overview_stats.py` | D2 | getAccountStats / getSystemInfo; UsageStore.get_account_stats |
| `src/server/update-check.test.ts` | 151 | no port | - | checks GitHub releases of zalo-agent for self-update; not applicable to a deployed clinic backend |
| `src/server/update-check.ts` | 140 | no port | - | checks GitHub releases of zalo-agent for self-update; not applicable to a deployed clinic backend |

## `src/server/routes`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/server/routes/account-routes.ts` | 247 | `pema/api/routers/admin_accounts.py` | C2 | bot-token endpoint -> admin_bot_accounts.py (C1) |
| `src/server/routes/agent-routes.ts` | 99 | `pema/api/routers/admin_agents.py` | D2 |  |
| `src/server/routes/contact-routes.ts` | 32 | `pema/api/routers/admin_threads.py` | D2 | contacts_router |
| `src/server/routes/delete-contact-session-routes.test.ts` | 122 | `tests/api/routers/test_delete_contact_session_routes.py` | D2 |  |
| `src/server/routes/friend-routes.test.ts` | 123 | `tests/api/routers/test_friend_routes.py` | C2 |  |
| `src/server/routes/friend-routes.ts` | 78 | `pema/api/routers/admin_friends.py` | C2 |  |
| `src/server/routes/image-routes.test.ts` | 113 | `tests/api/routers/test_image_routes.py` | D4 | image-gen settings |
| `src/server/routes/image-routes.ts` | 60 | `pema/api/routers/admin_tools.py` | D4 | image-gen settings |
| `src/server/routes/kb-inspect-routes.ts` | 40 | `pema/api/routers/admin_kb.py` | D3 |  |
| `src/server/routes/kb-route-guards.ts` | 125 | `pema/api/kb_route_guards.py` | D3 | size caps before parsing |
| `src/server/routes/kb-routes.test.ts` | 726 | `tests/api/routers/test_kb_routes.py` | D3 |  |
| `src/server/routes/kb-routes.ts` | 231 | `pema/api/routers/admin_kb.py` | D3 |  |
| `src/server/routes/log-routes.test.ts` | 102 | `tests/api/routers/test_admin_usage_routes.py` | D1 | logs_router |
| `src/server/routes/log-routes.ts` | 51 | `pema/api/routers/admin_usage.py` | D1 | logs_router |
| `src/server/routes/mcp-route-guards.ts` | 41 | `pema/api/mcp_route_guards.py` | D5 |  |
| `src/server/routes/mcp-routes.test.ts` | 131 | `tests/api/routers/test_mcp_routes.py` | D5 |  |
| `src/server/routes/mcp-routes.ts` | 95 | `pema/api/routers/admin_mcp.py` | D5 |  |
| `src/server/routes/memory-routes.ts` | 29 | `pema/api/routers/admin_threads.py` | D2 | memories_router |
| `src/server/routes/overview-routes.test.ts` | 81 | `tests/api/routers/test_admin_usage_routes.py` | D1 |  |
| `src/server/routes/overview-routes.ts` | 66 | `pema/api/routers/admin_usage.py` | D1 |  |
| `src/server/routes/provider-routes.ts` | 120 | `pema/api/routers/admin_model.py` | D1 |  |
| `src/server/routes/schedule-routes.test.ts` | 454 | `tests/scheduler/test_schedule_routes.py` | S |  |
| `src/server/routes/schedule-routes.ts` | 181 | `pema/api/routers/admin_schedules.py` | S |  |
| `src/server/routes/thread-routes-wipe.test.ts` | 145 | `tests/api/routers/test_thread_routes_wipe.py` | D2 |  |
| `src/server/routes/thread-routes.ts` | 122 | `pema/api/routers/admin_threads.py` | D2 |  |
| `src/server/routes/tool-routes.test.ts` | 152 | `tests/api/routers/test_tool_routes.py` | D4 |  |
| `src/server/routes/tool-routes.ts` | 146 | `pema/api/routers/admin_tools.py` | D4 |  |
| `src/server/routes/trace-routes-paging.test.ts` | 128 | `tests/api/routers/test_admin_usage_routes.py` | D1 |  |
| `src/server/routes/trace-routes.test.ts` | 122 | `tests/api/routers/test_admin_usage_routes.py` | D1 | traces_router |
| `src/server/routes/trace-routes.ts` | 83 | `pema/api/routers/admin_usage.py` | D1 | traces_router |
| `src/server/routes/tuning-routes.test.ts` | 239 | `tests/api/routers/test_admin_model_routes.py` | D1 |  |
| `src/server/routes/tuning-routes.ts` | 82 | `pema/api/routers/admin_model.py` | D1 |  |
| `src/server/routes/version-routes.ts` | 10 | no port | - | reports the latest zalo-agent release (update-check); not applicable |
| `src/server/routes/vision-routes.test.ts` | 144 | `tests/api/routers/test_admin_model_routes.py` | D1 |  |
| `src/server/routes/vision-routes.ts` | 73 | `pema/api/routers/admin_model.py` | D1 |  |

## `src/shared`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/shared/bo-dau-tieng-viet.test.ts` | 14 | `tests/shared/test_bo_dau_tieng_viet.py` | D3 | diacritics folding for KB indexing and queries |
| `src/shared/bo-dau-tieng-viet.ts` | 26 | `pema/shared/bo_dau_tieng_viet.py` | D3 | diacritics folding for KB indexing and queries |
| `src/shared/console-encoding.ts` | 16 | no port | - | Windows console code page; Python logging writes UTF-8 JSON (PYTHONUTF8) |
| `src/shared/current-datetime.test.ts` | 50 | `tests/shared/test_current_datetime.py` | A | done |
| `src/shared/current-datetime.ts` | 87 | `pema/shared/current_datetime.py` | A | done |
| `src/shared/daily-task-schedule.ts` | 21 | `pema/shared/daily_task_schedule.py` | D2 | run a cleanup now and every 24 h (asyncio task); used by media cleanup |
| `src/shared/db-transaction.test.ts` | 83 | `tests/shared/test_db_transaction.py` | A | done |
| `src/shared/db-transaction.ts` | 42 | `pema/shared/db_transaction.py` | A | done |
| `src/shared/doi-cho-den-khi.test.ts` | 99 | `tests/shared/test_doi_cho_den_khi.py` | A | done: test helper used by channel, scheduler, video-queue tests |
| `src/shared/doi-cho-den-khi.ts` | 97 | `pema/shared/doi_cho_den_khi.py` | A | done: test helper used by channel, scheduler, video-queue tests |
| `src/shared/download-image.ts` | 33 | `pema/shared/download_image.py` | D4 | image download; used by D1 (vision) and D2 (media-store) through an injected downloader |
| `src/shared/fake-agent-profile.ts` | 32 | `packages/contracts/src/pema_contracts/testing.py (fake_agent_profile, fake_account_config)` | A | done |
| `src/shared/hourly-rate-limit.test.ts` | 182 | `tests/shared/test_hourly_rate_limit.py` | D4 | documents / images / video rate limits |
| `src/shared/hourly-rate-limit.ts` | 106 | `pema/shared/hourly_rate_limit.py` | D4 | documents / images / video rate limits |
| `src/shared/html-entities.test.ts` | 28 | `tests/shared/test_html_entities.py` | D4 |  |
| `src/shared/html-entities.ts` | 86 | `pema/shared/html_entities.py` | D4 |  |
| `src/shared/html-to-text.test.ts` | 234 | `tests/shared/test_html_to_text.py` | D4 |  |
| `src/shared/html-to-text.ts` | 211 | `pema/shared/html_to_text.py` | D4 |  |
| `src/shared/jina-reader-fallback.test.ts` | 129 | `tests/shared/test_jina_reader_fallback.py` | D4 | third-party fallback; off in patient_channel (web tools disabled) |
| `src/shared/jina-reader-fallback.ts` | 91 | `pema/shared/jina_reader_fallback.py` | D4 | third-party fallback; off in patient_channel (web tools disabled) |
| `src/shared/ky-tu-moi-token.test.ts` | 43 | `tests/shared/test_ky_tu_moi_token.py` | A | done |
| `src/shared/ky-tu-moi-token.ts` | 42 | `pema/shared/ky_tu_moi_token.py` | A | done |
| `src/shared/log-cursor.ts` | 56 | `pema/shared/log_cursor.py` | D1 | log paging for /admin/logs/app |
| `src/shared/log-file-lines.ts` | 47 | `pema/shared/log_file_lines.py` | D1 |  |
| `src/shared/logger-turn-fields.test.ts` | 107 | `tests/shared/test_logger.py` | A | done |
| `src/shared/logger.ts` | 84 | `pema/shared/logger.py` | A | done: stdlib logging + turn context + PII redaction |
| `src/shared/private-address-guard.test.ts` | 79 | `tests/shared/test_private_address_guard.py` | D4 | SSRF guard for web_fetch / downloads |
| `src/shared/private-address-guard.ts` | 139 | `pema/shared/private_address_guard.py` | D4 | SSRF guard for web_fetch / downloads |
| `src/shared/read-log-file-paging.test.ts` | 109 | `tests/shared/test_read_log_file_paging.py` | D1 |  |
| `src/shared/read-log-file.test.ts` | 132 | `tests/shared/test_read_log_file.py` | D1 |  |
| `src/shared/read-log-file.ts` | 172 | `pema/shared/read_log_file.py` | D1 |  |
| `src/shared/read-zip-entry.test.ts` | 82 | `tests/shared/test_read_zip_entry.py` | D3 | zip-bomb ceilings for docx/xlsx parsing |
| `src/shared/read-zip-entry.ts` | 155 | `pema/shared/read_zip_entry.py` | D3 | zip-bomb ceilings for docx/xlsx parsing |
| `src/shared/safe-error-serializer.test.ts` | 111 | `tests/shared/test_safe_error_serializer.py` | A | done |
| `src/shared/safe-error-serializer.ts` | 88 | `pema/shared/safe_error_serializer.py` | A | done |
| `src/shared/safe-remote-download.test.ts` | 158 | `tests/shared/test_safe_remote_download.py` | D4 | streamed, size-capped, public-IP-only download |
| `src/shared/safe-remote-download.ts` | 293 | `pema/shared/safe_remote_download.py` | D4 | streamed, size-capped, public-IP-only download |
| `src/shared/temp-file-store.test.ts` | 125 | `tests/shared/test_temp_file_store.py` | D4 |  |
| `src/shared/temp-file-store.ts` | 104 | `pema/shared/temp_file_store.py` | D4 |  |
| `src/shared/test-env-setup.ts` | 59 | `tests/conftest.py (per package) + pema.config.env` | A | replaced: pytest fixtures and the Postgres test database (tests/test_database.py) |
| `src/shared/turn-log-context.test.ts` | 57 | `tests/shared/test_turn_log_context.py` | A | done |
| `src/shared/turn-log-context.ts` | 41 | `pema/shared/turn_log_context.py` | A | done |
| `src/shared/web-search-providers.test.ts` | 101 | `tests/shared/test_web_search_providers.py` | D4 |  |
| `src/shared/web-search-providers.ts` | 128 | `pema/shared/web_search_providers.py` | D4 |  |
| `src/shared/xml-sax-scan.test.ts` | 89 | `tests/shared/test_xml_sax_scan.py` | D3 | bounded XML scanning for OOXML |
| `src/shared/xml-sax-scan.ts` | 90 | `pema/shared/xml_sax_scan.py` | D3 | bounded XML scanning for OOXML |
| `src/shared/zip-stream-entry.test.ts` | 181 | `tests/shared/test_zip_stream_entry.py` | D3 |  |
| `src/shared/zip-stream-entry.ts` | 155 | `pema/shared/zip_stream_entry.py` | D3 |  |
| `src/shared/zone-time.test.ts` | 148 | `tests/shared/test_zone_time.py` | A | done |
| `src/shared/zone-time.ts` | 116 | `pema/shared/zone_time.py` | A | done |

## `src/video`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/video/chay-yt-dlp.test.ts` | 236 | `tests/video/test_chay_yt_dlp.py` | D4 |  |
| `src/video/chay-yt-dlp.ts` | 254 | `pema/video/chay_yt_dlp.py` | D4 |  |
| `src/video/chon-format-video.test.ts` | 217 | `tests/video/test_chon_format_video.py` | D4 |  |
| `src/video/chon-format-video.ts` | 50 | `pema/video/chon_format_video.py` | D4 |  |
| `src/video/chuan-bi-anh-bia-video.test.ts` | 118 | `tests/video/test_chuan_bi_anh_bia_video.py` | D4 |  |
| `src/video/chuan-bi-anh-bia-video.ts` | 108 | `pema/video/chuan_bi_anh_bia_video.py` | D4 |  |
| `src/video/chuoi-nguon-video.test.ts` | 272 | `tests/video/test_chuoi_nguon_video.py` | D4 |  |
| `src/video/chuoi-nguon-video.ts` | 151 | `pema/video/chuoi_nguon_video.py` | D4 |  |
| `src/video/doc-khung-hinh-mp4.test.ts` | 212 | `tests/video/test_doc_khung_hinh_mp4.py` | D4 |  |
| `src/video/doc-khung-hinh-mp4.ts` | 186 | `pema/video/doc_khung_hinh_mp4.py` | D4 |  |
| `src/video/gui-video-qua-zalo.test.ts` | 328 | `tests/video/test_gui_video_qua_zalo.py` | D4 |  |
| `src/video/gui-video-qua-zalo.ts` | 265 | `pema/video/gui_video_qua_zalo.py` | D4 |  |
| `src/video/hang-doi-tai-video.test.ts` | 143 | `tests/video/test_hang_doi_tai_video.py` | D4 |  |
| `src/video/hang-doi-tai-video.ts` | 100 | `pema/video/hang_doi_tai_video.py` | D4 |  |
| `src/video/kiem-gioi-han-video.test.ts` | 100 | `tests/video/test_kiem_gioi_han_video.py` | D4 |  |
| `src/video/kiem-gioi-han-video.ts` | 59 | `pema/video/kiem_gioi_han_video.py` | D4 |  |
| `src/video/kiem-url-video-truoc-khi-gui.test.ts` | 157 | `tests/video/test_kiem_url_video_truoc_khi_gui.py` | D4 |  |
| `src/video/kiem-url-video-truoc-khi-gui.ts` | 179 | `pema/video/kiem_url_video_truoc_khi_gui.py` | D4 |  |
| `src/video/nguon-tikwm.test.ts` | 177 | `tests/video/test_nguon_tikwm.py` | D4 |  |
| `src/video/nguon-tikwm.ts` | 116 | `pema/video/nguon_tikwm.py` | D4 |  |
| `src/video/nguon-yt-dlp.test.ts` | 287 | `tests/video/test_nguon_yt_dlp.py` | D4 |  |
| `src/video/nguon-yt-dlp.ts` | 250 | `pema/video/nguon_yt_dlp.py` | D4 |  |
| `src/video/tai-video-vao-ram.test.ts` | 180 | `tests/video/test_tai_video_vao_ram.py` | D4 |  |
| `src/video/tai-video-vao-ram.ts` | 116 | `pema/video/tai_video_vao_ram.py` | D4 |  |
| `src/video/thong-tin-video.ts` | 87 | `pema/video/thong_tin_video.py` | D4 |  |
| `src/video/video-rate-limit.ts` | 32 | `pema/video/video_rate_limit.py` | D4 |  |
| `src/video/whitelist-nguon-video.test.ts` | 235 | `tests/video/test_whitelist_nguon_video.py` | D4 |  |
| `src/video/whitelist-nguon-video.ts` | 210 | `pema/video/whitelist_nguon_video.py` | D4 |  |

## `src/zalo`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/zalo/account-manager-kenh.test.ts` | 221 | `tests/channels/zalo_personal/test_account_manager_kenh.py` | C2 |  |
| `src/zalo/account-manager.ts` | 202 | `pema/channels/zalo_personal/account_manager.py` | C2 | running personal accounts; start/stop; goes through the bridge |
| `src/zalo/busy-wait-notice.test.ts` | 213 | `tests/channels/test_busy_wait_notice.py` | C1 | reassurance text when a thread is busy for BUSY_ACK_AFTER_MS; text-only; shared by both channels (C2 imports it) |
| `src/zalo/busy-wait-notice.ts` | 101 | `pema/channels/busy_wait_notice.py` | C1 | reassurance text when a thread is busy for BUSY_ACK_AFTER_MS; text-only; shared by both channels (C2 imports it) |
| `src/zalo/deliver-chat-reply.ts` | 81 | `pema/channels/deliver_chat_reply.py` | C2 | channel-agnostic; both channels use it; calls PolicyHooks.on_outbound before every send |
| `src/zalo/friend-auto-accept-sweep.test.ts` | 114 | `tests/channels/zalo_personal/test_friend_auto_accept_sweep.py` | C2 |  |
| `src/zalo/friend-auto-accept-sweep.ts` | 87 | `pema/channels/zalo_personal/friend_auto_accept_sweep.py` | C2 |  |
| `src/zalo/friend-event-handler.test.ts` | 123 | `tests/channels/zalo_personal/test_friend_event_handler.py` | C2 |  |
| `src/zalo/friend-event-handler.ts` | 103 | `pema/channels/zalo_personal/friend_event_handler.py` | C2 |  |
| `src/zalo/incoming-message-router.test.ts` | 134 | `tests/channels/zalo_personal/test_incoming_message_router.py` | C2 | same shape as the bot router: ... -> batcher (C1) -> TurnQueue |
| `src/zalo/incoming-message-router.ts` | 142 | `pema/channels/zalo_personal/incoming_message_router.py` | C2 | same shape as the bot router: ... -> batcher (C1) -> TurnQueue |
| `src/zalo/kenh-ca-nhan.ts` | 57 | `pema/channels/zalo_personal/kenh_ca_nhan.py` | C2 | ChannelPort implementation of the personal account (talks to the Node bridge) |
| `src/zalo/kenh-luot.ts` | 61 | `packages/contracts/src/pema_contracts/channel.py (ChannelPort, capabilities)` | A | done: KenhLuot became ChannelPort + capability Protocols |
| `src/zalo/markdown-inline-styles.ts` | 131 | `pema/channels/markdown_inline_styles.py` | C2 |  |
| `src/zalo/markdown-to-zalo-styles.test.ts` | 424 | `tests/channels/test_markdown_to_zalo_styles.py` | C2 |  |
| `src/zalo/markdown-to-zalo-styles.ts` | 192 | `pema/channels/markdown_to_zalo_styles.py` | C2 |  |
| `src/zalo/message-receipts.test.ts` | 155 | `tests/channels/zalo_personal/test_message_receipts.py` | C2 |  |
| `src/zalo/message-receipts.ts` | 101 | `pema/channels/zalo_personal/message_receipts.py` | C2 |  |
| `src/zalo/message-turn-history-write.test.ts` | 299 | `tests/channels/test_message_turn_history_write.py` | C2 |  |
| `src/zalo/message-turn-injection.test.ts` | 306 | `tests/channels/test_message_turn_injection.py` | C2 |  |
| `src/zalo/message-turn-per-sender.test.ts` | 285 | `tests/channels/test_message_turn_per_sender.py` | C2 |  |
| `src/zalo/message-turn-processor.ts` | 258 | `pema/channels/message_turn_processor.py` | C2 | worker side: consumes a TurnJob, runs AgentEngine, delivers through ChannelPort; builds TurnCallbacks from PendingInbox |
| `src/zalo/message-turn-quote.test.ts` | 183 | `tests/channels/test_message_turn_quote.py` | C2 |  |
| `src/zalo/message-turn-sanitize.test.ts` | 248 | `tests/channels/test_message_turn_sanitize.py` | C2 |  |
| `src/zalo/message-turn-timestamp.test.ts` | 230 | `tests/channels/test_message_turn_timestamp.py` | C2 |  |
| `src/zalo/message-turn-tool-sends.test.ts` | 195 | `tests/channels/test_message_turn_tool_sends.py` | C2 |  |
| `src/zalo/multiline-markup-per-line.ts` | 119 | `pema/channels/multiline_markup_per_line.py` | C2 |  |
| `src/zalo/ngan-sach-byte-theo-kenh.test.ts` | 245 | `tests/channels/test_ngan_sach_byte_theo_kenh.py` | C2 |  |
| `src/zalo/normalize-zalo-styles.test.ts` | 116 | `tests/channels/test_normalize_zalo_styles.py` | C2 |  |
| `src/zalo/normalize-zalo-styles.ts` | 77 | `pema/channels/normalize_zalo_styles.py` | C2 |  |
| `src/zalo/notify-technical-error.test.ts` | 104 | `tests/channels/test_notify_technical_error.py` | C2 |  |
| `src/zalo/payload-anomaly-watch.test.ts` | 136 | `tests/channels/test_payload_anomaly_watch.py` | C1 | logs unexpected payload shapes (ids only, never content); shared by both channels (C2 imports it) |
| `src/zalo/payload-anomaly-watch.ts` | 67 | `pema/channels/payload_anomaly_watch.py` | C1 | logs unexpected payload shapes (ids only, never content); shared by both channels (C2 imports it) |
| `src/zalo/prepare-outgoing-text.ts` | 32 | `pema/channels/prepare_outgoing_text.py` | C2 |  |
| `src/zalo/qr-login-manager.test.ts` | 133 | `tests/channels/zalo_personal/test_qr_login_manager.py` | C2 |  |
| `src/zalo/qr-login-manager.ts` | 117 | `pema/channels/zalo_personal/qr_login_manager.py` | C2 |  |
| `src/zalo/reaction-icons.ts` | 31 | `pema/channels/zalo_personal/reaction_icons.py` | C2 |  |
| `src/zalo/reconnect-planner.test.ts` | 138 | `tests/channels/zalo_personal/test_reconnect_planner.py` | C2 |  |
| `src/zalo/reconnect-planner.ts` | 91 | `pema/channels/zalo_personal/reconnect_planner.py` | C2 |  |
| `src/zalo/record-incoming-message.ts` | 86 | `pema/channels/record_incoming_message.py` | C1 | writes agent.history + agent.threads at receipt (ConversationStore) and the Inbox (AgentFacingClinicActions.record_inbound_message); shared by both channels (C2 imports it) |
| `src/zalo/reply-quote.test.ts` | 145 | `tests/channels/test_reply_quote.py` | C2 |  |
| `src/zalo/reply-quote.ts` | 133 | `pema/channels/reply_quote.py` | C2 |  |
| `src/zalo/reply-target-tu-kenh.ts` | 36 | `pema/channels/reply_target_tu_kenh.py` | C1 | builds the ReplyTarget from a ChannelPort; shared by both channels (C2 imports it) |
| `src/zalo/sanitize-code-block.ts` | 66 | `pema/channels/sanitize_code_block.py` | C2 |  |
| `src/zalo/sanitize-reply-text.test.ts` | 340 | `tests/channels/test_sanitize_reply_text.py` | C2 |  |
| `src/zalo/sanitize-reply-text.ts` | 277 | `pema/channels/sanitize_reply_text.py` | C2 |  |
| `src/zalo/send-reply-in-parts.ts` | 354 | `pema/channels/send_reply_in_parts.py` | C2 | channel-agnostic; both channels use it; calls PolicyHooks.on_outbound before every send |
| `src/zalo/send-reply-quote.test.ts` | 169 | `tests/channels/test_send_reply_quote.py` | C2 |  |
| `src/zalo/send-reply-style-fallback.test.ts` | 115 | `tests/channels/test_send_reply_style_fallback.py` | C2 |  |
| `src/zalo/split-long-message.test.ts` | 80 | `tests/channels/test_split_long_message.py` | C2 |  |
| `src/zalo/split-long-message.ts` | 146 | `pema/channels/split_long_message.py` | C2 |  |
| `src/zalo/split-styled-message.test.ts` | 322 | `tests/channels/test_split_styled_message.py` | C2 |  |
| `src/zalo/split-styled-message.ts` | 171 | `pema/channels/split_styled_message.py` | C2 |  |
| `src/zalo/typing-indicator.test.ts` | 143 | `tests/channels/zalo_personal/test_typing_indicator.py` | C2 |  |
| `src/zalo/typing-indicator.ts` | 76 | `pema/channels/zalo_personal/typing_indicator.py` | C2 |  |
| `src/zalo/zalo-client.ts` | 126 | `bridges/zalo-personal/src/zalo-client.ts (Node, zca-js kept) + pema/channels/zalo_personal/bridge_client.py` | C2 | zca-js is not ported: it stays in the Node bridge behind a flag (off by default); credential cookie stored encrypted in agent.accounts.credential_enc |
| `src/zalo/zalo-credential-store.ts` | 50 | `bridges/zalo-personal/src/zalo-credential-store.ts (Node, zca-js kept) + pema/channels/zalo_personal/bridge_client.py` | C2 | zca-js is not ported: it stays in the Node bridge behind a flag (off by default); credential cookie stored encrypted in agent.accounts.credential_enc |
| `src/zalo/zalo-image-variant.test.ts` | 99 | `tests/channels/zalo_personal/test_zalo_image_variant.py` | C2 |  |
| `src/zalo/zalo-image-variant.ts` | 93 | `pema/channels/zalo_personal/zalo_image_variant.py` | C2 |  |
| `src/zalo/zalo-listener.ts` | 119 | `bridges/zalo-personal/src/zalo-listener.ts (Node, zca-js kept) + pema/channels/zalo_personal/bridge_client.py` | C2 | zca-js is not ported: it stays in the Node bridge behind a flag (off by default); credential cookie stored encrypted in agent.accounts.credential_enc |
| `src/zalo/zalo-message-parser.test.ts` | 159 | `tests/channels/zalo_personal/test_zalo_message_parser.py` | C2 |  |
| `src/zalo/zalo-message-parser.ts` | 110 | `pema/channels/zalo_personal/zalo_message_parser.py` | C2 |  |
| `src/zalo/zalo-message-timestamp.test.ts` | 76 | `tests/channels/zalo_personal/test_zalo_message_timestamp.py` | C2 |  |
| `src/zalo/zalo-message-timestamp.ts` | 72 | `pema/channels/zalo_personal/zalo_message_timestamp.py` | C2 |  |

## `src/zalo-bot`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `src/zalo-bot/api-ca-nhan-guard.test.ts` | 138 | `tests/channels/zalo_bot/test_api_ca_nhan_guard.py` | C1 |  |
| `src/zalo-bot/bot-account-runner.test.ts` | 96 | `tests/channels/zalo_bot/test_bot_account_runner.py` | C1 | per-account lifecycle: webhook OR getUpdates polling (mutually exclusive) |
| `src/zalo-bot/bot-account-runner.ts` | 126 | `pema/channels/zalo_bot/bot_account_runner.py` | C1 | per-account lifecycle: webhook OR getUpdates polling (mutually exclusive) |
| `src/zalo-bot/bot-message-router.test.ts` | 190 | `tests/channels/zalo_bot/test_bot_message_router.py` | C1 | allowlist -> record incoming -> batcher -> TurnQueue.enqueue (no in-process turn) |
| `src/zalo-bot/bot-message-router.ts` | 110 | `pema/channels/zalo_bot/bot_message_router.py` | C1 | allowlist -> record incoming -> batcher -> TurnQueue.enqueue (no in-process turn) |
| `src/zalo-bot/chan-tool-tren-kenh-bot.test.ts` | 104 | `tests/channels/zalo_bot/test_chan_tool_tren_kenh_bot.py` | C1 | blocked tools never reach the schema; test with a fake ToolRegistry |
| `src/zalo-bot/kenh-bot.test.ts` | 99 | `tests/channels/zalo_bot/test_kenh_bot.py` | C1 | the ChannelPort implementation (KenhLuot of the bot): send_text, typing |
| `src/zalo-bot/kenh-bot.ts` | 103 | `pema/channels/zalo_bot/kenh_bot.py` | C1 | the ChannelPort implementation (KenhLuot of the bot): send_text, typing |
| `src/zalo-bot/kiem-chung-bot-api.ts` | 116 | `pema/channels/zalo_bot/kiem_chung_bot_api.py` | C1 | CLI that probes the Bot API (zalo-bot-check); keep as a python -m script |
| `src/zalo-bot/lich-hen-tren-kenh-bot.test.ts` | 253 | `tests/channels/zalo_bot/test_lich_hen_tren_kenh_bot.py` | C1 | scheduler on the bot channel; test with a fake SchedulerPort |
| `src/zalo-bot/luot-tren-kenh-bot.test.ts` | 144 | `tests/channels/zalo_bot/test_luot_tren_kenh_bot.py` | C1 |  |
| `src/zalo-bot/nang-luc-kenh-bot.test.ts` | 148 | `tests/channels/zalo_bot/test_nang_luc_kenh_bot.py` | C1 | blocked_tools + persona rule -> ChannelCapabilities of ZaloBotChannel |
| `src/zalo-bot/nang-luc-kenh-bot.ts` | 84 | `pema/channels/zalo_bot/nang_luc_kenh_bot.py` | C1 | blocked_tools + persona rule -> ChannelCapabilities of ZaloBotChannel |
| `src/zalo-bot/tao-tai-khoan-bot.test.ts` | 221 | `tests/channels/zalo_bot/test_tao_tai_khoan_bot.py` | C1 |  |
| `src/zalo-bot/zalo-bot-api-client.test.ts` | 252 | `tests/channels/zalo_bot/test_zalo_bot_api_client.py` | C1 |  |
| `src/zalo-bot/zalo-bot-api-client.ts` | 240 | `pema/channels/zalo_bot/zalo_bot_api_client.py` | C1 |  |
| `src/zalo-bot/zalo-bot-api-types.ts` | 84 | `pema/channels/zalo_bot/zalo_bot_api_types.py` | C1 |  |
| `src/zalo-bot/zalo-bot-listener.test.ts` | 170 | `tests/channels/zalo_bot/test_zalo_bot_listener.py` | C1 |  |
| `src/zalo-bot/zalo-bot-listener.ts` | 117 | `pema/channels/zalo_bot/zalo_bot_listener.py` | C1 |  |
| `src/zalo-bot/zalo-bot-update-parser.test.ts` | 174 | `tests/channels/zalo_bot/test_zalo_bot_update_parser.py` | C1 |  |
| `src/zalo-bot/zalo-bot-update-parser.ts` | 94 | `pema/channels/zalo_bot/zalo_bot_update_parser.py` | C1 |  |

## Modules with no zalo-agent source

Each package also builds the parts below; they have no upstream file, so they are not rows above.

| Package | New module | Source of truth |
|---|---|---|
| B1 | `pema/clinic/{domain,actions,rbac,audit}`, routers `auth`, `patients`, `appointments`, `crm`, `conversations`, `review_items`, `admin_audit`, `admin_templates` (message templates a doctor approves), `pema/clinic/actions/agent_facing.py` (implements `AgentFacingClinicActions`) | `docs/ARCH-PB01.md` (authorization matrix, API boundaries), `prototype/shared/*.js` (read-only behaviour) |
| B2 | `pema/clinic/crm_rules/*`, router `admin_crm_rules` | `prototype/shared/crm-automation.js`, `crm-data.js`, `prototype/crm-test.cjs` (clock 2026-09-20, cases P025-P032); `docs/20_CRM01_PATIENT_LIFECYCLE.md` |
| C1 | `pema/channels/zalo_bot/webhook.py` (webhook receiver, `update_id` de-duplication), `pema/channels/oa_api.py` (stub: `NotImplementedError`, no OA/ZNS yet) | Zalo Bot API docs (https://docs.zaloplatforms.com/docs/BOT), PLAN-AI01 section 8 |
| C2 | `backend/bridges/zalo-personal/` (Node 22 + zca-js + Hono), `pema/channels/zalo_personal/bridge_client.py`, kill switch and quota enforcement | zca-js 2.1.2 API; README must state the account-lock risk |
| D1 | `pema/agent/providers/*` (OpenAI-compatible / Anthropic / Gemini adapters), `pema/workers/agent_worker.py` hook, fake LLM for tests | PLAN-AI01 section 3 |
| D2 | Postgres implementations of every Protocol in `pema_contracts.conversation` | migration 0002 |
| D3 | `pema/knowledge/embedding_client.py` (bge-m3, OpenAI-compatible `/embeddings`), hybrid search SQL, `pema/workers/kb_ingest_worker.py` | `KnowledgeStore`, `EmbeddingClient` |
| S | `pema/workers/scheduler_worker.py` (loop over `ctx.list_active_clinic_ids`), Redis lock integration | `SchedulerPort`, `ProactiveSendGuard` |
| P | `pema/policy/{profiles,redflags,pii,identity}.py`, router `admin_policy`; evals of the dermatology CSKH set | PLAN-AI01 section 5, `AGENT.md` |
| E | screens Today's tasks, Inbox, Review queue, Patient 360 (+ the admin screens translated from `web/` above) | `pema_contracts` OpenAPI, Pema design tokens |
| F | `infra/*` (compose, Ubuntu + Ollama/llama-server, Tailscale), docs SCOPE/SPEC/MODULEMAP/ARCH-AI01, README, pointer in root README + SECTION_PROGRESS | PLAN-AI01 section 6 |

## Outside `src/`

Dashboard (`web/`, package E translates the FEATURES to Next.js), evals, scripts, config, docs, root files and planning notes.

## `web/`, `evals/`, `scripts/`, `config/`, `docs/`, root and `plans/`

| Upstream file | Lines | Python target | Package | Note |
|---|---:|---|---|---|
| `web/index.html` | 38 | `frontend/ (Next.js App Router config and root layout)` | E | Vite SPA entry replaced by Next.js |
| `web/public/apple-touch-icon.png` | 26217 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/public/dashboard-background-dark.webp` | 13050 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/public/dashboard-background.webp` | 7360 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/public/favicon.png` | 4382 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/public/zalo-agent-icon.webp` | 5262 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/public/zalo-agent-logo.webp` | 32970 B | no port | - | zalo-agent logos and backgrounds; Pema brand tokens are used instead (AGENT.md mobile rules) |
| `web/src/app.tsx` | 175 | `frontend/src/app/(admin)/layout.tsx + route tree` | E | react-router -> App Router |
| `web/src/dashboard-api-client.ts` | 881 | `frontend/src/lib/api/ (openapi-typescript client over pema-agent/backend/apps/api/openapi.json)` | E | typed client replaces the hand-written one |
| `web/src/layout/page-header.tsx` | 40 | `frontend/src/components/admin/layout/page-header.tsx` | E |  |
| `web/src/layout/sidebar-nav.tsx` | 232 | `frontend/src/components/admin/layout/sidebar-nav.tsx` | E |  |
| `web/src/main.tsx` | 10 | `frontend/ (Next.js App Router config and root layout)` | E | Vite SPA entry replaced by Next.js |
| `web/src/pages/account-edit-drawer.tsx` | 367 | `frontend/src/components/admin/accounts/account-edit-drawer.tsx` | E |  |
| `web/src/pages/accounts-page.tsx` | 184 | `frontend/src/app/(admin)/admin/accounts/page.tsx` | E |  |
| `web/src/pages/agent-card.tsx` | 198 | `frontend/src/components/admin/agents/agent-card.tsx` | E |  |
| `web/src/pages/agent-create-modal.tsx` | 143 | `frontend/src/components/admin/agents/agent-create-modal.tsx` | E |  |
| `web/src/pages/agent-create-page.tsx` | 167 | `frontend/src/app/(admin)/admin/agents/page.tsx` | E |  |
| `web/src/pages/agent-detail-form.ts` | 71 | `frontend/src/lib/admin/agents/agent-detail-form.ts` | E |  |
| `web/src/pages/agent-detail-page.tsx` | 192 | `frontend/src/app/(admin)/admin/agents/page.tsx` | E |  |
| `web/src/pages/agent-draft.test.ts` | 71 | `frontend/src/lib/admin/agents/agent-draft.test.ts` | E |  |
| `web/src/pages/agent-draft.ts` | 57 | `frontend/src/lib/admin/agents/agent-draft.ts` | E |  |
| `web/src/pages/agent-field-validators.ts` | 34 | `frontend/src/lib/admin/agents/agent-field-validators.ts` | E |  |
| `web/src/pages/agent-form-field.tsx` | 94 | `frontend/src/components/admin/agents/agent-form-field.tsx` | E |  |
| `web/src/pages/agent-form-layout.tsx` | 74 | `frontend/src/components/admin/agents/agent-form-layout.tsx` | E |  |
| `web/src/pages/agent-id-field.tsx` | 95 | `frontend/src/components/admin/agents/agent-id-field.tsx` | E |  |
| `web/src/pages/agent-identity-section.tsx` | 124 | `frontend/src/components/admin/agents/agent-identity-section.tsx` | E |  |
| `web/src/pages/agent-kb-refresh-bridge.ts` | 19 | `frontend/src/lib/admin/agents/agent-kb-refresh-bridge.ts` | E |  |
| `web/src/pages/agent-kb-sources-section.tsx` | 155 | `frontend/src/components/admin/agents/agent-kb-sources-section.tsx` | E |  |
| `web/src/pages/agent-model-section.tsx` | 188 | `frontend/src/components/admin/agents/agent-model-section.tsx` | E |  |
| `web/src/pages/agent-tools-section.tsx` | 195 | `frontend/src/components/admin/agents/agent-tools-section.tsx` | E |  |
| `web/src/pages/agents-page.tsx` | 173 | `frontend/src/app/(admin)/admin/agents/page.tsx` | E |  |
| `web/src/pages/agents-toolbar.tsx` | 165 | `frontend/src/components/admin/agents/agents-toolbar.tsx` | E |  |
| `web/src/pages/change-password-section.tsx` | 115 | `frontend/src/components/admin/auth/change-password-section.tsx` | E |  |
| `web/src/pages/contacts-page.tsx` | 121 | `frontend/src/app/(admin)/admin/threads/page.tsx` | E |  |
| `web/src/pages/friends-page.tsx` | 193 | `frontend/src/app/(admin)/admin/accounts/page.tsx` | E |  |
| `web/src/pages/image-settings-modal.tsx` | 197 | `frontend/src/components/admin/model/image-settings-modal.tsx` | E |  |
| `web/src/pages/kb-add-source-modal.tsx` | 202 | `frontend/src/components/admin/kb/kb-add-source-modal.tsx` | E |  |
| `web/src/pages/kb-agent-sources-dirty.test.ts` | 32 | `frontend/src/lib/admin/kb/kb-agent-sources-dirty.test.ts` | E |  |
| `web/src/pages/kb-agent-sources-dirty.ts` | 17 | `frontend/src/lib/admin/kb/kb-agent-sources-dirty.ts` | E |  |
| `web/src/pages/kb-assign-agents-modal.tsx` | 148 | `frontend/src/components/admin/kb/kb-assign-agents-modal.tsx` | E |  |
| `web/src/pages/kb-chunks-modal.tsx` | 93 | `frontend/src/components/admin/kb/kb-chunks-modal.tsx` | E |  |
| `web/src/pages/kb-delete-warning-message.test.ts` | 33 | `frontend/src/lib/admin/kb/kb-delete-warning-message.test.ts` | E |  |
| `web/src/pages/kb-delete-warning-message.ts` | 20 | `frontend/src/lib/admin/kb/kb-delete-warning-message.ts` | E |  |
| `web/src/pages/kb-guide-modal.tsx` | 109 | `frontend/src/components/admin/kb/kb-guide-modal.tsx` | E |  |
| `web/src/pages/kb-page-clamp.test.ts` | 21 | `frontend/src/lib/admin/kb/kb-page-clamp.test.ts` | E |  |
| `web/src/pages/kb-page-clamp.ts` | 10 | `frontend/src/lib/admin/kb/kb-page-clamp.ts` | E |  |
| `web/src/pages/kb-poll-guard.test.ts` | 62 | `frontend/src/lib/admin/kb/kb-poll-guard.test.ts` | E |  |
| `web/src/pages/kb-poll-guard.ts` | 64 | `frontend/src/lib/admin/kb/kb-poll-guard.ts` | E |  |
| `web/src/pages/kb-poll-loop.test.ts` | 332 | `frontend/src/lib/admin/kb/kb-poll-loop.test.ts` | E |  |
| `web/src/pages/kb-poll-loop.ts` | 160 | `frontend/src/lib/admin/kb/kb-poll-loop.ts` | E |  |
| `web/src/pages/kb-source-name-from-file.test.ts` | 50 | `frontend/src/lib/admin/kb/kb-source-name-from-file.test.ts` | E |  |
| `web/src/pages/kb-source-name-from-file.ts` | 29 | `frontend/src/lib/admin/kb/kb-source-name-from-file.ts` | E |  |
| `web/src/pages/kb-source-row.tsx` | 143 | `frontend/src/components/admin/kb/kb-source-row.tsx` | E |  |
| `web/src/pages/kb-upload-size-guard.test.ts` | 59 | `frontend/src/lib/admin/kb/kb-upload-size-guard.test.ts` | E |  |
| `web/src/pages/kb-upload-size-guard.ts` | 36 | `frontend/src/lib/admin/kb/kb-upload-size-guard.ts` | E |  |
| `web/src/pages/knowledge-page.tsx` | 241 | `frontend/src/app/(admin)/admin/kb/page.tsx` | E |  |
| `web/src/pages/llm-base-url-presets.test.ts` | 84 | `frontend/src/lib/admin/model/llm-base-url-presets.test.ts` | E |  |
| `web/src/pages/llm-base-url-presets.ts` | 78 | `frontend/src/lib/admin/model/llm-base-url-presets.ts` | E |  |
| `web/src/pages/log-row.tsx` | 61 | `frontend/src/components/admin/logs/log-row.tsx` | E |  |
| `web/src/pages/login-page.tsx` | 63 | `frontend/src/app/(admin)/admin/auth/page.tsx` | E |  |
| `web/src/pages/logs-page.tsx` | 163 | `frontend/src/app/(admin)/admin/logs/page.tsx` | E |  |
| `web/src/pages/mcp-assign-agents-modal.tsx` | 138 | `frontend/src/components/admin/mcp/mcp-assign-agents-modal.tsx` | E |  |
| `web/src/pages/mcp-header-fields.tsx` | 120 | `frontend/src/components/admin/mcp/mcp-header-fields.tsx` | E |  |
| `web/src/pages/mcp-page.tsx` | 135 | `frontend/src/app/(admin)/admin/mcp/page.tsx` | E |  |
| `web/src/pages/mcp-server-form-modal.tsx` | 149 | `frontend/src/components/admin/mcp/mcp-server-form-modal.tsx` | E |  |
| `web/src/pages/mcp-server-row.tsx` | 108 | `frontend/src/components/admin/mcp/mcp-server-row.tsx` | E |  |
| `web/src/pages/mcp-status-label.test.ts` | 16 | `frontend/src/lib/admin/mcp/mcp-status-label.test.ts` | E |  |
| `web/src/pages/mcp-status-label.ts` | 30 | `frontend/src/lib/admin/mcp/mcp-status-label.ts` | E |  |
| `web/src/pages/memory-page.tsx` | 90 | `frontend/src/app/(admin)/admin/threads/page.tsx` | E |  |
| `web/src/pages/mo-ta-loai-kenh.test.ts` | 93 | `frontend/src/lib/admin/accounts/mo-ta-loai-kenh.test.ts` | E |  |
| `web/src/pages/mo-ta-loai-kenh.ts` | 56 | `frontend/src/lib/admin/accounts/mo-ta-loai-kenh.ts` | E |  |
| `web/src/pages/overview-page.tsx` | 274 | `frontend/src/app/(admin)/admin/overview/page.tsx` | E |  |
| `web/src/pages/provider-form-fields.test.ts` | 48 | `frontend/src/lib/admin/model/provider-form-fields.test.ts` | E |  |
| `web/src/pages/provider-form-fields.ts` | 41 | `frontend/src/lib/admin/model/provider-form-fields.ts` | E |  |
| `web/src/pages/providers-section.tsx` | 156 | `frontend/src/components/admin/model/providers-section.tsx` | E |  |
| `web/src/pages/qr-login-modal.tsx` | 113 | `frontend/src/components/admin/accounts/qr-login-modal.tsx` | E |  |
| `web/src/pages/reset-all-settings-section.tsx` | 85 | `frontend/src/components/admin/tuning/reset-all-settings-section.tsx` | E |  |
| `web/src/pages/schedule-destination-fields.tsx` | 87 | `frontend/src/components/admin/schedules/schedule-destination-fields.tsx` | E |  |
| `web/src/pages/schedule-edit-drawer.tsx` | 161 | `frontend/src/components/admin/schedules/schedule-edit-drawer.tsx` | E |  |
| `web/src/pages/schedule-fields-section.tsx` | 126 | `frontend/src/components/admin/schedules/schedule-fields-section.tsx` | E |  |
| `web/src/pages/schedule-form-helpers.ts` | 53 | `frontend/src/lib/admin/schedules/schedule-form-helpers.ts` | E |  |
| `web/src/pages/schedule-job-row.tsx` | 174 | `frontend/src/components/admin/schedules/schedule-job-row.tsx` | E |  |
| `web/src/pages/schedule-page.tsx` | 144 | `frontend/src/app/(admin)/admin/schedules/page.tsx` | E |  |
| `web/src/pages/schedule-run-history-drawer.tsx` | 82 | `frontend/src/components/admin/schedules/schedule-run-history-drawer.tsx` | E |  |
| `web/src/pages/session-detail-drawer.tsx` | 288 | `frontend/src/components/admin/traces/session-detail-drawer.tsx` | E |  |
| `web/src/pages/session-trace-view.tsx` | 79 | `frontend/src/components/admin/traces/session-trace-view.tsx` | E |  |
| `web/src/pages/sessions-page.tsx` | 171 | `frontend/src/app/(admin)/admin/traces/page.tsx` | E |  |
| `web/src/pages/timezone-select.tsx` | 90 | `frontend/src/components/admin/schedules/timezone-select.tsx` | E |  |
| `web/src/pages/tool-chain-settings-modal.tsx` | 200 | `frontend/src/components/admin/tools/tool-chain-settings-modal.tsx` | E |  |
| `web/src/pages/tool-settings-modal-shell.tsx` | 148 | `frontend/src/components/admin/tools/tool-settings-modal-shell.tsx` | E |  |
| `web/src/pages/tools-page.tsx` | 330 | `frontend/src/app/(admin)/admin/tools/page.tsx` | E |  |
| `web/src/pages/trace-page.tsx` | 179 | `frontend/src/app/(admin)/admin/traces/page.tsx` | E |  |
| `web/src/pages/trace-step-card.tsx` | 145 | `frontend/src/components/admin/traces/trace-step-card.tsx` | E |  |
| `web/src/pages/tuning-commit-value.test.ts` | 38 | `frontend/src/lib/admin/tuning/tuning-commit-value.test.ts` | E |  |
| `web/src/pages/tuning-commit-value.ts` | 26 | `frontend/src/lib/admin/tuning/tuning-commit-value.ts` | E |  |
| `web/src/pages/tuning-detail-panel.tsx` | 91 | `frontend/src/components/admin/tuning/tuning-detail-panel.tsx` | E |  |
| `web/src/pages/tuning-field-control.tsx` | 200 | `frontend/src/components/admin/tuning/tuning-field-control.tsx` | E |  |
| `web/src/pages/tuning-field.tsx` | 170 | `frontend/src/components/admin/tuning/tuning-field.tsx` | E |  |
| `web/src/pages/tuning-group-icon.tsx` | 47 | `frontend/src/components/admin/tuning/tuning-group-icon.tsx` | E |  |
| `web/src/pages/tuning-nav.tsx` | 130 | `frontend/src/components/admin/tuning/tuning-nav.tsx` | E |  |
| `web/src/pages/tuning-page.tsx` | 190 | `frontend/src/app/(admin)/admin/tuning/page.tsx` | E |  |
| `web/src/pages/usage-bar-chart.tsx` | 142 | `frontend/src/components/admin/overview/usage-bar-chart.tsx` | E |  |
| `web/src/pages/use-provider-form.ts` | 117 | `frontend/src/lib/admin/model/use-provider-form.ts` | E |  |
| `web/src/pages/use-tuning-search.ts` | 42 | `frontend/src/lib/admin/tuning/use-tuning-search.ts` | E |  |
| `web/src/pages/vision-settings-modal.tsx` | 218 | `frontend/src/components/admin/model/vision-settings-modal.tsx` | E |  |
| `web/src/shared/account-filter.tsx` | 40 | `frontend/src/components/admin/shared/account-filter.tsx` | E |  |
| `web/src/shared/backdrop-close-guard.test.ts` | 65 | `frontend/src/lib/admin/shared/backdrop-close-guard.test.ts` | E |  |
| `web/src/shared/backdrop-close-guard.ts` | 52 | `frontend/src/lib/admin/shared/backdrop-close-guard.ts` | E |  |
| `web/src/shared/background-image.ts` | 12 | `frontend/src/lib/admin/shared/background-image.ts` | E |  |
| `web/src/shared/confirm-dialog.tsx` | 121 | `frontend/src/components/admin/shared/confirm-dialog.tsx` | E |  |
| `web/src/shared/dashboard-icons.tsx` | 290 | `frontend/src/components/admin/shared/dashboard-icons.tsx` | E |  |
| `web/src/shared/file-drop-zone.tsx` | 126 | `frontend/src/components/admin/shared/file-drop-zone.tsx` | E |  |
| `web/src/shared/fold-for-search.test.ts` | 54 | `frontend/src/lib/admin/shared/fold-for-search.test.ts` | E |  |
| `web/src/shared/fold-for-search.ts` | 40 | `frontend/src/lib/admin/shared/fold-for-search.ts` | E |  |
| `web/src/shared/format-bot-time.ts` | 45 | `frontend/src/lib/admin/shared/format-bot-time.ts` | E |  |
| `web/src/shared/kb-formats.ts` | 8 | `frontend/src/lib/admin/shared/kb-formats.ts` | E |  |
| `web/src/shared/menu-hanh-dong.tsx` | 94 | `frontend/src/components/admin/shared/menu-hanh-dong.tsx` | E |  |
| `web/src/shared/secret-input.tsx` | 51 | `frontend/src/components/admin/shared/secret-input.tsx` | E |  |
| `web/src/shared/select-menu-popup.tsx` | 203 | `frontend/src/components/admin/shared/select-menu-popup.tsx` | E |  |
| `web/src/shared/select-menu.tsx` | 192 | `frontend/src/components/admin/shared/select-menu.tsx` | E |  |
| `web/src/shared/slugify-vietnamese.test.ts` | 71 | `frontend/src/lib/admin/shared/slugify-vietnamese.test.ts` | E |  |
| `web/src/shared/slugify-vietnamese.ts` | 43 | `frontend/src/lib/admin/shared/slugify-vietnamese.ts` | E |  |
| `web/src/shared/so-sanh-phien-ban.test.ts` | 46 | `frontend/src/lib/admin/shared/so-sanh-phien-ban.test.ts` | E |  |
| `web/src/shared/so-sanh-phien-ban.ts` | 35 | `frontend/src/lib/admin/shared/so-sanh-phien-ban.ts` | E |  |
| `web/src/shared/ui-bits.tsx` | 341 | `frontend/src/components/admin/shared/ui-bits.tsx` | E |  |
| `web/src/shared/unsaved-changes-guard.test.ts` | 61 | `frontend/src/lib/admin/shared/unsaved-changes-guard.test.ts` | E |  |
| `web/src/shared/unsaved-changes-guard.ts` | 50 | `frontend/src/lib/admin/shared/unsaved-changes-guard.ts` | E |  |
| `web/src/shared/use-theme.ts` | 92 | `frontend/src/lib/admin/shared/use-theme.ts` | E |  |
| `web/src/shared/use-unsaved-changes-prompt.ts` | 41 | `frontend/src/lib/admin/shared/use-unsaved-changes-prompt.ts` | E |  |
| `web/src/styles.css` | 96 | `frontend/src/app/globals.css (Tailwind + Pema brand tokens)` | E |  |
| `web/src/vite-env.d.ts` | 8 | `frontend/ (Next.js App Router config and root layout)` | E | Vite SPA entry replaced by Next.js |
| `web/tsconfig.json` | 17 | `frontend/ (Next.js App Router config and root layout)` | E | Vite SPA entry replaced by Next.js |
| `web/vite.config.ts` | 34 | `frontend/ (Next.js App Router config and root layout)` | E | Vite SPA entry replaced by Next.js |
| `evals/eval-assert.test.ts` | 283 | `evals/test_eval_assert.py` | D1 | P adds clinic cases |
| `evals/eval-assert.ts` | 142 | `evals/eval_assert.py` | D1 | P adds clinic cases |
| `evals/eval-case-type.ts` | 94 | `evals/eval_case_type.py` | D1 | P adds clinic cases |
| `evals/eval-cases-cach-noi.ts` | 294 | `evals/eval_cases_cach_noi.py` | D1 | 17 original scenarios (translate); package P adds the dermatology CSKH set (fictional) |
| `evals/eval-cases-memory.ts` | 65 | `evals/eval_cases_memory.py` | D1 | 17 original scenarios (translate); package P adds the dermatology CSKH set (fictional) |
| `evals/eval-cases-tool.ts` | 129 | `evals/eval_cases_tool.py` | D1 | 17 original scenarios (translate); package P adds the dermatology CSKH set (fictional) |
| `evals/eval-cases.ts` | 24 | `evals/eval_cases.py` | D1 | 17 original scenarios (translate); package P adds the dermatology CSKH set (fictional) |
| `evals/eval-env.ts` | 98 | `evals/eval_env.py` | D1 | P adds clinic cases |
| `evals/eval-formatting-view.test.ts` | 63 | `evals/test_eval_formatting_view.py` | D1 | P adds clinic cases |
| `evals/eval-formatting-view.ts` | 73 | `evals/eval_formatting_view.py` | D1 | P adds clinic cases |
| `evals/eval-report.ts` | 47 | `evals/eval_report.py` | D1 | P adds clinic cases |
| `evals/fake-zalo-api.ts` | 101 | `evals/fake_zalo_api.py` | D1 | P adds clinic cases |
| `evals/preflight-web-search.test.ts` | 58 | `evals/test_preflight_web_search.py` | D1 | P adds clinic cases |
| `evals/preflight-web-search.ts` | 60 | `evals/preflight_web_search.py` | D1 | P adds clinic cases |
| `evals/read-real-llm-settings.ts` | 77 | `evals/read_real_llm_settings.py` | D1 | P adds clinic cases |
| `evals/read-real-search-settings.ts` | 71 | `evals/read_real_search_settings.py` | D1 | P adds clinic cases |
| `evals/README.md` | 97 | `evals/README.md` | D1 | describe the 17 original scenarios plus the dermatology CSKH set |
| `evals/run-eval.ts` | 254 | `evals/run_eval.py` | D1 | P adds clinic cases |
| `scripts/login-account.ts` | 57 | no port | - | CLI QR login; replaced by POST /admin/accounts/{id}/login (C2) |
| `config/accounts.example.json` | 14 | `infra/accounts.example.json` | D2 | synthetic example only |
| `docs/deployment-guide.md` | 209 | `docs/ (Ubuntu + Ollama/llama-server + Tailscale guide)` | F |  |
| `docs/ke-toan-token-cua-agent.html` | 1020 | `docs/ (token accounting and MCP architecture notes)` | F | keep as reference diagrams if still accurate |
| `docs/mcp-client-architecture.html` | 507 | `docs/ (token accounting and MCP architecture notes)` | F | keep as reference diagrams if still accurate |
| `docs/project-roadmap.md` | 6498 | no port | - | upstream roadmap; reference only |
| `docs/release-guide.md` | 114 | no port | - | upstream release process |
| `docs/system-architecture.md` | 534 | `docs/ARCH-AI01.md` | F | rewrite for the Python + Postgres + clinic architecture |
| `docs/vps-setup-checklist.md` | 128 | `docs/ (Ubuntu + Ollama/llama-server + Tailscale guide)` | F |  |
| `README.md` | 395 | no port | - | upstream README; read for behaviour, not ported |
| `README.en.md` | 390 | no port | - | idem |
| `CLAUDE.md` | 153 | no port | - | upstream project rules; their DECISIONS are already reflected in PLAN-AI01 |
| `CHANGELOG.md` | 421 | no port | - | upstream history |
| `LICENSE` | 21 | `pema-agent/THIRD_PARTY_NOTICES.md` | A | MIT notice reproduced verbatim: done |
| `package.json` | 96 | no port | - | TS toolchain; replaced by backend/pyproject.toml and frontend/package.json |
| `pnpm-lock.yaml` | 2948 | no port | - | TS lockfile; Python uses uv.lock |
| `pnpm-workspace.yaml` | 10 | no port | - | TS workspace; the frontend has its own package.json |
| `tsconfig.json` | 17 | no port | - | TS compiler config; pyright strict replaces it |
| `tsconfig.build.json` | 25 | no port | - | TS build config |
| `.env.example` | 71 | `infra/.env.example` | F | PEMA_* variables + the original tuning names |
| `.env.production.example` | 91 | `infra/.env.example` | F |  |
| `.dockerignore` | 44 | `infra/` | F |  |
| `Dockerfile` | 119 | `infra/docker/api.Dockerfile` | F | Python images |
| `docker-compose.prod.yml` | 119 | `infra/docker-compose.yml` | F | adds postgres(pgvector), redis |
| `Caddyfile.site` | 68 | `infra/ (reverse proxy)` | F | optional |
| `deploy.sh` | 76 | `infra/` | F |  |
| `.gitattributes` | 41 | no port | - | upstream line-ending rules; pema-agent/.gitattributes |
| `.gitignore` | 29 | no port | - | pema-agent/.gitignore covers the Python/Node equivalents |
| `.claude/launch.json` | 11 | no port | - | upstream agent configuration |
| `plans/260725-1650-web-dashboard-and-memory/ (6 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260725-1910-accounts-agents-qr-web/ (1 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260727-1135-tao-file-docx-xlsx/ (7 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260731-0042-lich-hen-nhan-chu-dong/ (9 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260802-1348-agent-chuan-production/ (12 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260808-2354-knowledge-base-tra-cuu-tai-lieu/ (7 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260809-remediation-kho-tri-thuc/ (11 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260821-1127-noi-lich-hen-vao-kenh-zalo-bot/ (7 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260822-1320-tai-video-tiktok-facebook/ (3 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260824-0116-ap-dung-pattern-tu-deepseek-harness/ (7 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260825-0125-tab-ban-be/ (2 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |
| `plans/260829-0726-mcp-client-cam-mcp-ngoai/ (9 files)` |  | no port | - | upstream planning notes; read for the rationale of a decision, not ported |

## Khác biệt so với PORT-MAP ban đầu

Cập nhật 2026-10-02 (gói F), đối chiếu với cây file thật trên nhánh `feat/ai-agent-backend` (commit `1ce6cca`). Các bảng phía trên được giữ nguyên như gói A viết; đây là chỗ thực tế lệch khỏi chúng. Mục này chỉ dùng gạch đầu dòng và bảng ba cột để `tests/test_port_map.py` (đọc các dòng bảng năm cột) không đổi kết quả.

**Kết quả đối chiếu máy**: mọi đích `pema/**/*.py` ghi trong các hàng của bảng đều tồn tại (0 đích thiếu). Ngược lại, 104 file Python dưới `pema/` (không tính `__init__.py` và các thư mục ghi bằng dấu ngoặc nhọn hoặc `*` ở bảng "Modules with no zalo-agent source") không có tên trong PORT-MAP; chúng được phân loại bên dưới. Mười đường dẫn test từng ghi sai tên đã được sửa ở vòng cuối (xem cuối mục).

### Gói P: nhiều module hơn kế hoạch

PORT-MAP ghi gói P có 0 hàng và bốn file `pema/policy/{profiles,redflags,pii,identity}.py`. Thực tế `pema/policy/` có 12 file (kể cả `__init__.py`). Ngoài bốn file trên, gói P thêm:

- `hooks.py` (`ClinicPolicyHooks`, tám hook), `gateway.py` (cửa `agent_worker` vào `clinic_agent`), `review.py` (dựng `review_item` do chính sách mở), `turn_guard.py` (thứ tự chuẩn của một lượt, hàm tham chiếu), `identity_admin.py` (phía nhân viên: xác nhận, từ chối, cấp mã; chạy ở API với `be_app`), `testing.py` (đồ giả), `text_normalize.py` (chuẩn hóa chữ cho cờ đỏ và PII).
- Router `admin_policy` và migration `p0001_identity_link` (bảng `clinic.identity_link_code`, `clinic.identity_link_attempt`, các hàm liên kết).

### Tệp từng ghi "no port" nhưng đã được dịch

- `src/conversation/xoa-han-session.ts` và `.test.ts` từng ghi "no port" với lý do "hết hạn phiên dashboard". Mô tả đó sai file: tệp này là "xóa hẳn một session (cuộc trò chuyện)" của trang Sessions. Gói D2 đã dịch thành `pema/conversation/xoa_han_session.py` (route `DELETE /admin/threads/{account_id}/{thread_id}`). Vòng sửa cuối đã sửa hai hàng của bảng `src/conversation` thành đích thật.

### Gói G: composition và tiến trình

`pema/composition/` (8 file: `runtime`, `intake`, `outbound`, `api_wiring`, `auth_bridge`, `adapters`, `testing`, `__init__`) không có hàng nào và không có nguồn TypeScript: đó là gốc ghép (composition root) tạo mọi đối tượng một lần mỗi tiến trình và nối các gói theo CONTRACTS-AI01. Cùng gói G: phần ghép trong `pema/bootstrap.py` (lifespan), `pema/workers/main.py` (điểm vào `python -m pema.workers.main`), migration `g_0005_merge_heads`, `uv.lock` và `openapi.json` sinh lại, các kịch bản vòng khép kín trong `tests/integration/`, tool phòng khám `pema/agent/tools/clinic_tools.py` (bốn tool `patient.get_care_context`, `appointment.book` dạng đề xuất, `review_item.create` soạn nháp followup chờ duyệt, `escalation.create`; bốn khóa của `CLINIC_TOOL_KEYS` đều đã đăng ký), route `POST /auth/password` (đổi mật khẩu của chính mình, dịch `dashboard-password-route.ts`).

### Workers

Bảng "no zalo-agent source" ghi D1 làm `pema/workers/agent_worker.py`. File đó **không tồn tại**. Việc đó do `pema/workers/turn_worker.py` làm (claim `TurnJob`, chạy `process_turn_job`); thêm `scheduler_worker.py` (S), `kb_ingest_worker.py` (D3), `main.py` (G).

### File có thật nhưng PORT-MAP không gọi tên (phân loại)

| Nhóm | File | Ghi chú |
|---|---|---|
| Đồ giả và hỗ trợ test | `pema/agent/{testing,testing_conversation,testing_engine}.py`, `agent/tools/testing.py`, `api/{clinic_testing,kb_test_support}.py`, `api/routers/admin_stores_testing.py`, `channels/pipeline_testing.py`, `channels/zalo_bot/testing.py`, `channels/zalo_personal/{testing,service_testing}.py`, `composition/testing.py`, `config/testing_settings.py`, `conversation/pg_testing.py`, `knowledge/kb_test_support.py`, `mcp/testing.py`, `policy/testing.py`, `scheduler/{testing,testing_env}.py` | nằm trong gói sản xuất để test và eval dùng chung; không có nguồn TS |
| Kho/ghép Postgres, Redis | `conversation/{store,sql_util}.py`, `knowledge/postgres_knowledge_store.py`, `config/{runtime_settings_kv,runtime_settings_store}.py`, `middleware/{redis_backends,redis_ops}.py`, `scheduler/{store,redis_locks,pg_readers,session_scope,run_context,deps,ports,admin_service}.py`, `api/routers/admin_stores.py` | hệ quả của SQLite → Postgres và một tiến trình → Redis |
| Clinic (B1) | `clinic/models/{audit,base,care,crm,inbox,scheduling,tenant}.py` và routers `auth`, `patients`, `appointments`, `crm`, `conversations`, `review_items`, `admin_audit`, `admin_templates`, `system` | mới, không có TS |
| CRM (B2) | router `admin_crm_rules` | nguồn là JS của prototype, không phải zalo-agent |
| Kênh (C1, C2) | `channels/zalo_bot/{settings,bot_account_manager,bot_account_admin}.py`; `channels/zalo_personal/{proactive_gate,bridge_events,bridge_signing,channel_settings,credential_vault,audit_writer,services}.py`; `channels/{registry,turn_ports,utf16_text}.py`; routers `webhooks_zalo_bot`, `webhooks_zalo_bridge`, `admin_bot_accounts`, `admin_channels` | `proactive_gate` là cổng an toàn của clinic (kill switch, cửa sổ, trần, khoảng cách) đặt trong `send_text` |
| Agent, MCP, tri thức | `agent/{model_types,safe_turn_error,text_generator,tag_name_padding}.py`, `agent/tools/{function_tool,tool_deps,tool_send,tool_policy_tags,unicode_char_classes}.py`, `mcp/{mcp_profile_gate,mcp_schema}.py`, `knowledge/{chu_ky_file,kb_extract_timeout_boot_guard}.py` | `mcp_profile_gate` thực thi "patient_channel chặn mọi tool MCP" |
| Tiện ích | `api/{deps,errors,export_openapi}.py`, `core/event_loop.py`, `shared/js_whitespace.py`, `scheduler/template_placeholders.py` | `template_placeholders`: chỗ giữ của mẫu chỉ điền khi danh tính đã xác minh |

### Migration

PORT-MAP ghi "Schema = Alembic 0001..0003". Thực tế còn `b1_0004_auth_session_and_inbox`, `b2_0001_crm_protocol_marker`, `s_0004_scheduler_runtime`, `p0001_identity_link`, `g_0005_merge_heads` (gộp bốn đầu nhánh), `g_0006_definer_search_path`, rồi `b1_0007_session_absolute_expiry` (hạn tuyệt đối của phiên) và `h2_0007_retention` (tác vụ xóa theo thời hạn lưu; mới, không có TS) cùng nối sau `g_0006` và được `h_0008_merge_heads` gộp lại: chỉ một đầu. Cách chạy là `alembic upgrade heads`.

### Test được ghi tên nhưng không có dưới tên đó

Đã sửa ở vòng cuối: các hàng của `log-routes`, `overview-routes`, `trace-routes`, `trace-routes-paging` trỏ vào `tests/api/routers/test_admin_usage_routes.py`; `tuning-routes` và `vision-routes` vào `tests/api/routers/test_admin_model_routes.py`; `schedule-routes` vào `tests/scheduler/test_schedule_routes.py`; `scheduled-job-send` vào `tests/scheduler/test_run_scheduled_job.py`. `tests/test_startup_order.py` có thật. `dashboard-password-route` đã có route `POST /auth/password` và `tests/api/test_dashboard_password_route.py`. `tests/test_port_map_targets.py` pin danh sách thiếu là rỗng: mọi đích của bảng đều tồn tại.

### Hạ tầng và tài liệu (các hàng "F")

- `Dockerfile` → ghi `infra/Dockerfile.api, Dockerfile.worker`; thực tế một ảnh dùng chung cho api, worker và migrate tại `infra/docker/api.Dockerfile`, cộng `infra/docker/frontend.Dockerfile` và `infra/docker/bridge.Dockerfile` (mỗi cái có `.dockerignore` riêng).
- `docs/deployment-guide.md` và `docs/vps-setup-checklist.md` → ghi `docs/`; thực tế là `infra/ubuntu/HUONG-DAN-UBUNTU.md` (tiếng Việt) kèm `infra/ubuntu/systemd/`.
- `docs/system-architecture.md` → `docs/ARCH-AI01.md` (đã viết; cùng SCOPE, SPEC, MODULEMAP-AI01).
- `docs/ke-toan-token-cua-agent.html`, `docs/mcp-client-architecture.html`: ghi "giữ làm sơ đồ nếu còn đúng"; **chưa chuyển** (không có trong `pema-agent/docs/`).
- `Caddyfile.site` → `infra/caddy/Caddyfile` cùng `infra/caddy/modes/{auto,internal,off}.caddy` và `infra/docker-compose.proxy.yml` (profile `proxy`; không phải bản dịch, viết mới cho repo này). `deploy.sh`: **chưa có**; triển khai bằng `make up-proxy` (xem `infra/README.md`, mục Reverse proxy).
- `.env.production.example` gộp vào `infra/.env.example`; `config/accounts.example.json` → `infra/accounts.example.json` đúng như ghi.

### Frontend (các hàng "E")

Hàng ghi một `page.tsx` cho nhiều trang gốc, nhưng thực tế mỗi trang của dashboard gốc là một route riêng dưới `frontend/src/app/(admin)/admin/<vùng>/page.tsx` (ví dụ `admin/accounts`, `admin/agents`, `admin/kb`, `admin/schedules`, `admin/tuning/[group]`). Thành phần dịch ở `frontend/src/components/admin/<vùng>` và logic ở `frontend/src/lib/admin/<vùng>`; mã không có bản gốc ở `components/ops`, `lib/ops` và trang `admin/policy`. Dashboard gốc dùng `dashboard-api-client.ts` với DTO tên tiếng Việt; bản Next.js dùng client gõ kiểu từ `openapi.json` (DTO snake_case tiếng Anh) kèm vài adapter thuần (`tuning-types.ts`, `trace-types.ts`). Chi tiết ở `frontend/README.md` (mục "Port notes").

### Eval

`evals/` có thêm `eval_cases_clinic.py`, `clinic_cases.json`, `eval_wiring.py`, `eval_canned_tools.py` (gói P và D1) ngoài các file được ánh xạ. `evals/` nằm trong `testpaths` của `backend/pyproject.toml` (`../evals`), nên `make test` chạy cả 78 test của nó; `make lint` kiểm cả `../evals` bằng ruff.
