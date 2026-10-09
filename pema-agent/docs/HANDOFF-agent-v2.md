# Handoff — agent-v2 (general agent core)

Lives in the repo (`pema-agent/docs/HANDOFF-agent-v2.md`) so it is pushed and shared; update it here after
each stage. Last updated 2026-10-09, after S4d (`8f765862`).

Next session focus: S4 is complete — ask the user what comes next (S5 Graph, HMAC, Zalo channel plugin, plugin
UI, verifier hook). Reply to the user in Vietnamese. Open items to handle later are under "Loose ends".

## Where things are

- Repo: `E:\Desktop\cnbphongkham` (Pema Digital Clinic). Agent work lives in `pema-agent/backend` (uv workspace).
- Branch: `feat/agent-v2` — the branch made to rewrite the agent from scratch (commits `588f18fc`, `eadaac30`
  removed the old agent layer; see their messages and `pema-agent/backend/apps/api/pema/composition/app_runtime.py`
  docstring: "a future agent service talks to the clinic through the HTTP API only").
- Done so far (read the commits, do not re-derive): S0 … S4d, see "Roadmap and status" and the progress
  entries below; latest `8f765862`.
- Tests: full agent suite `uv run pytest packages/agent-core packages/secret-cipher apps/agent -q` (418 at
  S4d, Postgres tests need `PEMA_TEST_DATABASE_URL`). ruff, pyright strict, lint-imports clean.
- Reference repos cloned in `E:\Desktop\clone-git`: `claw-code`, `hermes-agent`, `openclaw-src` (the empty
  `openclaw` folder is junk), `zalo-agent`, `mattpocock-skills`.
- Installed project skill: `.claude/skills/handoff/` (from `mattpocock/skills@b0618bc`, MIT `LICENSE` kept).
- `AGENTS.md` at the repo root = byte-for-byte copy of `CLAUDE.md` (for Copilot/Codex). Not `AGENT.md`: that
  file already holds the project's own working rules and Windows paths are case-insensitive. The two copies
  drift if only one is edited — re-copy after changing `CLAUDE.md`.

## What the user wants (overall)

- A **general agent core** like OpenClaw / Hermes Agent ("Agent = Model + Harness"). Everything domain-specific
  is a **plugin added later**: Zalo channels, RAG (`knowledge_pg`), memory consolidation, and the clinic
  customer-care ideas of stakeholder "A" (intake questions, post-treatment follow-up, booking/reminders,
  personalised replies, photos — all later).
- Development flow follows 5 layers: **Prompt → Context → Harness → Loop → Graph**, after a walking skeleton.
- Learn from 4 repos, inherit selectively: claw-code (loop, compaction, permissions, mock harness),
  zalo-agent (model config, error classifier, loop guard, trim to budget), Hermes (tool registry, frozen
  prompt, memory tool with char limits, skills, background review, plugin `register(ctx)`), OpenClaw
  (channel contract, durable ingress, pairing, session keys, memory flush, hybrid memory search).

## Decisions already locked (do not reopen unless the user does)

| Topic | Decision |
|---|---|
| Framework | None (no LangChain/LangGraph — the 4 reference repos use none either). Official SDKs only |
| Language / stack | Python 3.12, uv, pydantic v2, pyright strict, ruff (T20: no `print`), pytest asyncio auto |
| Location | `pema-agent/backend/packages/agent-core` (core) + `apps/agent` (service); later `plugins/` |
| Import rules | `agentcore` never imports `pema`, `pema_contracts`, `agent_app`; `agent_app` never imports `pema` (import-linter contracts in `backend/pyproject.toml`) |
| Profiles | TOML (no pyyaml in the repo); API key only from env `LLM_API_KEY`; env overrides profile |
| Tenancy | `tenant_id` everywhere, default `"default"`; one tenant now, clinic chain later |
| Storage | Postgres later (own schema, own Alembic); pgvector reserved for RAG. S0–S1 use in-memory store |
| Model layer | Follow zalo-agent: 3 provider kinds (openai-compatible, anthropic, google), settings DB → env → default, one reasoning-effort map, classified errors. S0 has only openai-compatible |
| Memory | Hermes-style tiers with char limits, frozen snapshot per session; memory flush before compaction (OpenClaw). Consolidation = later generic plugin |
| Skills | Hermes-style: index in prompt, content on demand; **agent may write/patch skills itself without approval** (for now) |
| Tools | No terminal / filesystem tools |
| Approvals & business rules | **Dropped for now** — only technical guides/sensors (arg validation, loop guard, size limits). Goal: agent runs first |
| Channels | Plugin contract ~8 methods (Hermes shape + OpenClaw capabilities); Zalo later |
| Git | Commit when a step is done; **never** any AI attribution (no Co-Authored-By, no "Generated with", no AI names). Push only when asked |

## Roadmap and status

| Stage | Content | Status |
|---|---|---|
| S0 | Walking skeleton: messages, model port, OpenAI-compatible adapter (always streams, `include_usage`), tool registry, `get_datetime`, `run_turn` (max_steps, final turn without tools, tool errors → `is_error`, store before tools, one empty-completion retry), in-memory store, `agent chat` CLI | **Done** |
| S1 | Prompt: sections + scopes, frozen system, transient context message, status bar | **Done `f4b68879`** (real-model check pending) |
| S2 | Context: token estimate, providers, history window, trim without splitting tool pairs, compaction (aux model + heuristic fallback), memory tool + `MemoryBackend`, skills tools + `SkillSource` | **Done** `aad3ce48`, `c0e6e1d9`, `80596312` |
| S3 | Harness: full model layer (3 providers, DB settings, AES-GCM secrets, reasoning map), parallel read-only tools, guide/sensor pipeline, Postgres store, trace, channel API + HTTP `/v1/chat`, plugin loader + profiles | **Done**: S3a `95aa0d10`, S3b `949eb697`, S3c `b798d78d`, S3d-1 `0c6fa3b3`, S3d-2 `981e7363`, S3e-1 `a693729d`, S3e-2 `3f6a4ffb`, S3e-3 `fac0bfcf` |
| S4 | Loop: budgets, recovery per error kind (429 wait once, context overflow cut once, auth stop), loop guard, mid-turn injection (`collect`/`steer`), one run per session, verifier hook, trigger runtime | In progress: S4a `ff0c66a0`, S4b `ccb21241`, S4c `09c2096a`, S4d `8f765862` done (real-model cassettes still to record; verifier hook deferred) |
| S5 | Graph: nodes/edges/state, `run_turn` as node, sub-agent `delegate` — only when needed | Planned |

## S1 plan (approved and done — kept for reference)

- D1 Each prompt section has a scope: `session` (built once, frozen), `turn`, `step`.
- D2 `session` sections → frozen system prompt stored per session with a fingerprint; profile change → rebuild
  and log a "prompt cache break" (Hermes).
- D3 `turn`/`step` sections are NOT in the system prompt: they go into one **transient context message**
  appended at the end of the request and never stored (keeps the provider's prefix cache intact).
- D4 The final-turn "step limit reached" note goes into that same transient message.
- D5 `SectionRegistry` like the tool registry; the profile lists sections and their order; unknown name → error.
- D6 `system_prompt_file` (path relative to the profile) as an alternative to inline `system_prompt`.
- D7 `run_turn` takes `prompt: PromptBuilder` instead of `system_prompt: str`, plus an injectable `clock`.
- Built-in sections: `identity` (session), `tool_usage` (session, omitted with no tools), `environment` (turn:
  time + weekday in agent timezone, channel), `status` (step: "step k of n", tools; wrap-up hint on last step).
- Files: `agentcore/prompt/{section,registry,builder,builtin}.py`; store gains session meta (frozen system +
  fingerprint, per tenant); `run_turn.py`; `agent_app/profile.py` (`[prompt] sections`, `system_prompt_file`);
  CLI `/prompt` command; `profiles/dev.toml` + `prompts/dev.md`; ~14 tests incl. a full-request snapshot with a
  fixed clock.
- Out of S1: skills index and memory (S2), token budget (S2), Anthropic cache breakpoints (S3).

## Decisions after S1

- 2026-10-09: the user asked why prompt text is split (persona file `profiles/prompts/dev.md` vs wording in
  `prompt/builtin.py` and `prompt/builder.py`). Compared with Hermes (`SOUL.md` + `agent/prompt_builder.py`),
  claw-code (`CLAUDE.md` + `runtime/src/prompt.rs`), OpenClaw (workspace `AGENTS.md`/`SOUL.md`/`IDENTITY.md`/
  `USER.md`/`MEMORY.md` + `src/agents/system-prompt.ts`): all split user text (files) from framework text (code).
  Offered: (1) move all framework wording into `builtin.py`, (2) OpenClaw-style per-agent folder later.
  **User: "đừng gom" — keep the layout as it is.**

## S2 plan (written 2026-10-09, awaiting approval)

Reference facts (checked in the clones): Hermes memory tool `tools/memory_tool.py` (MEMORY.md 2200 chars,
USER.md 1375 chars, actions add/replace/remove with `old_text`, frozen snapshot at session start); Hermes
compressor `agent/context_compressor.py` (threshold % of window, tail budget = threshold × summary ratio 0.20,
structured summary headings, deterministic fallback); Hermes skills `tools/skills_tool.py` (`skills_list`,
`skill_view`), `tools/skill_manager_tool.py` (`skill_manage`, name `^[a-z0-9][a-z0-9._-]*$` ≤64, description
≤1024, content ≤100k chars); claw-code `runtime/src/compact.rs` (chars heuristic, keep last 4 messages);
zalo-agent `src/agent/trim-context-to-budget.ts` (drop oldest whole units, tool pairs atomic, protect tail).

Split in two commits: **S2a context budget + compaction**, **S2b memory + skills**.

S2a:
- C1 `agentcore/context/tokens.py`: chars-per-token heuristic (default 3.0, Vietnamese-safe) + per-message
  overhead; counts system + messages + context block + tool schemas.
- C2 Profile `[context]`: `window_tokens` (required for compaction, e.g. 128000), `compact_at` (0.75 of
  window minus max_output_tokens), `keep_recent_ratio` (0.20 of the threshold, min = current turn).
- C3 Check before every model call in `run_turn`; over the threshold \u2192 compact, then build the request.
- C4 Cut points only at turn boundaries (before a user message); an assistant tool call and its results are
  never split; the current turn is always kept.
- C5 Summary by a model call (same model by default, optional `[context] summary_model` later in S3) with
  fixed headings: Goal, Decisions, Progress, Pending user asks, Facts and identifiers, Next steps. Fallback when
  it fails: drop the oldest whole turns (zalo-agent) and leave a one-line "earlier messages omitted" note.
- C6 Store keeps full history (append-only) + a compaction record `(summary, first_kept_index)`; the request is
  `[<conversation-summary> user message] + history[first_kept:]`. After a compaction the frozen system prompt
  is rebuilt (Hermes: the only moment it refreshes besides a config change; the cache is broken anyway).
- C7 CLI `/context` (estimate, window, threshold, compactions) and `/compact` (force). TurnResult reports a
  compaction happened.

S2b:
- M1 `MemoryBackend` port: targets `memory` (agent notes, 2200 chars) and `user` (about the person, 1375
  chars); key = (tenant_id, agent_name) for `memory`, (tenant_id, agent_name, user_id) for `user`.
  `run_turn` and `ToolContext` gain `user_id` (CLI: "cli-user").
- M2 Tool `memory`: actions add / replace / remove (`old_text` substring must match exactly one entry);
  over the cap \u2192 error with current usage so the model consolidates.
- M3 Session section `memory`: snapshot rendered when the system prompt is built; writes during the session are
  not in the prompt until the next session or the next compaction. Session sections then need data loaded
  async: `SessionSection.render(env, data)` with `SessionData(memory, skills)` loaded by `PromptBuilder.system()`.
- M4 Memory flush before compaction (OpenClaw): one silent call offering only the `memory` tool ("context is
  about to be compacted; save what is worth keeping"), max 2 steps, its messages not stored.
- M5 Storage in S2: JSON files under `pema-agent/backend/.agent-data/` (gitignored) so memory survives CLI
  restarts; Postgres in S3. Sessions stay in memory.
- K1 `SkillSource` port + file implementation `.agent-data/skills/<tenant>/<name>/SKILL.md` (frontmatter
  name, description). Limits: name `^[a-z0-9][a-z0-9._-]*$` \u226464, description \u22641024, body \u226420000 chars.
- K2 Tools `skill_list`, `skill_view(name)`, `skill_write(name, description, body)`, `skill_patch(name,
  old_text, new_text)`; no approval (user decision); the tool writes the frontmatter itself.
- K3 Session section `skills`: "## Skills" index `- name: description`, capped (50 skills / 4000 chars), with
  "read a skill with skill_view before a task it covers". Frozen like memory.
- K4 Profile `[memory]`, `[skills]`; dev profile turns them on; CLI `/memory`.

Open questions for the user: Q1 chars/token 3.0? Q2 summary by the main model for now? Q3 `.agent-data/` JSON
files for memory/skills in S2? Q4 add `user_id` now? Q5 two commits S2a then S2b?

**Approved 2026-10-09**: Q1 ok, Q2 ok, Q3 ok for now (user asked about NoSQL — answer: stay on Postgres
JSONB in S3, files behind a port in S2; a separate NoSQL server only for a concrete need), Q4 ok (user_id
keeps one person's memory away from another; it does not by itself stop replies going to the wrong person —
that is the channel layer in S3: reply goes to the session's bound thread, never to a target the model picks),
Q5 ok. Implementation started with S2a.

S2a design refinements made while implementing:
- The summary goes into the **system prompt** (a `<conversation-summary>` block after the session sections),
  not as a message: a summary user message followed by the first kept user message would give two user
  messages in a row. The system prompt is rebuilt right after a compaction anyway.
- Visible history = `history[first_kept:]`, always starting at a user message. Only the latest compaction
  record is kept; a new summary folds in the previous one.
- `run_turn(context=ContextManager | None)`: None = no compaction (S1 behaviour). Summariser usage is added
  to the turn usage. `TurnResult.compactions` counts them. In-turn overflow (the current turn alone too big) is
  not handled here: S4 recovery.
- 2026-10-09: the user stopped me ("đừng vội làm, trả lời trước"); the S2a draft files were removed from the
  working tree. S2a rewritten from scratch after approval.
- 2026-10-09 storage decision (approved): human-written agent definition = .md files in the repo, read-only to the
  agent: `apps/agent/agents/<name>/{agent.toml, SOUL.md, AGENTS.md, skills/<n>/SKILL.md}` (no IDENTITY.md /
  TOOLS.md). Agent-written data = Postgres schema `agent_rt` (own Alembic, version table
  `alembic_version_agent_rt`; same stack as `apps/api`: SQLAlchemy async + psycopg 3 + Alembic; pattern
  `apps/api/alembic/env.py`; db tests marked `db`, skipped without `PEMA_TEST_DATABASE_URL`): tables
  `agent_memory`, `agent_skill`, Markdown text. `apps/api` already has a schema `agent` — do not reuse that name.
  Sessions / compactions stay in memory until **S3**.
- 2026-10-09 new repo rule `.claude/rules/testing.md` (user asked): run only the tests that cover the change
  (~20% is enough), full suite only when asked / before push / core-wide changes. Staged, not committed yet.
- 2026-10-09: "ok go" — S2a implementation started (plan in the chat; summary in /memories/session/plan.md).
- S2a core written (uncommitted): `agentcore/context/{tokens,policy,compaction,__init__}.py`,
  `CompactionRecord` + `load_compaction`/`save_compaction` on the store port and `InMemorySessionStore`,
  `PromptBuilder.system(..., refresh=True)` appends a `<conversation-summary>` block, `run_turn(context=...)`
  checks the budget before every call (incl. final) and sends `history[first_kept:]`; `TurnResult.compactions`.
  ruff + pyright clean on `agent-core/src`; existing run_turn / prompt / core tests pass (45). Next: profile
  `[context]`, CLI `/context` `/compact`, new tests.
- **S2a committed `aad3ce48`** "agent-v2: context budget and compaction (S2a)". Profile `[context]`
  (window_tokens None = off; dev = 128000), `Profile.context_policy()`, CLI `/context`, `/compact` (force: keeps
  only the newest turn), stats line shows `compactions=`. Tests: new `packages/agent-core/tests/test_context.py`
  (18) + 3 in `apps/agent/tests/test_agent_app.py`. Targeted run (per the testing rule): test_context,
  test_run_turn, test_prompt, test_core_basics, apps/agent = 80 passed; test_openai_compat / test_tools /
  test_scripted not re-run (untouched). ruff, pyright strict, lint-imports 6/6 clean. Fake CLI checked.
  `.claude/rules/testing.md` still staged, not committed (ask the user).
- Next: S2b (agent folder + SOUL.md/AGENTS.md, memory + skills, Postgres `agent_rt`). Plan steps 9–15 in
  /memories/session/plan.md.
- S2b in progress (uncommitted). Core written, ruff + pyright clean on agent-core/src:
  - `agentcore/memory/{service,tool}.py`: `MemoryService` over a `MemoryBackend` port (load -> `StoredNotes(text,
    version)`, `save(key, text, expected_version) -> bool` compare-and-swap, 3 attempts), entries separated by
    `\n§\n` (Hermes format), caps 2200/1375, add/replace/remove with unique `old_text`; tool `memory`.
  - `agentcore/skills/{library,tools}.py`: `Skill` (validated), SKILL.md frontmatter parse/render,
    `load_bundled_skills(dir)` (folder name = skill name), `SkillStore` port + in-memory, `SkillLibrary` (bundled
    first, bundled names read-only, max 100 agent skills); tools skill_list/view/write/patch.
  - `agentcore/prompt/data.py`: `SessionData` loaded in `PromptBuilder.system(user_id=...)` from optional
    `memory=` / `skills=`; `SessionSection.render(env, data)` (signature changed). `PromptEnv.rules`.
    New sections `rules`, `skills`, `memory`, `user_memory`; DEFAULT_SECTIONS = identity, rules, tool_usage,
    skills, memory, user_memory, environment, status.
  - `ToolContext.user_id`, `run_turn(user_id=)`, `flush_memory()` in run_turn.py called through
    `ContextManager.compact(before_summary=...)` (memory tool only, ≤2 calls, not stored, model error skips).
  Next: agent folder `apps/agent/agents/dev/` + profile loading + CLI `/memory`, tests, commit; then Postgres.
- **S2b part 1 committed `c0e6e1d9`** "agent-v2: agent folder, memory and skills (S2b, part 1)":
  agent folder `apps/agent/agents/dev/{agent.toml, SOUL.md, AGENTS.md, skills/write-a-plan/SKILL.md}`
  (old `profiles/dev.toml` + `prompts/dev.md` removed; `system_prompt_file` dropped; SOUL.md/AGENTS.md vs inline
  `system_prompt`/`rules` = error if both); `load_profile(dir or toml)`, `Profile.folder` (private attr via
  `in_folder()`), `[memory]`, `[skills]`; `agent_app/assembly.py` `build_agent()` / `build_prompt()`; CLI
  `--profile apps/agent/agents/dev`, `/memory`, `/compact` runs the memory flush too, CLI user `cli-user`.
  Tests: new `test_memory.py`, `test_skills.py`; app tests updated. Targeted run 115 passed (memory, skills,
  prompt, context, run_turn, core_basics, apps/agent); ruff, pyright strict, lint-imports clean.
- Next: S2b part 2 — Postgres schema `agent_rt` (tables `agent_memory`, `agent_skill`), own Alembic in
  `apps/agent/alembic`, `PostgresMemoryBackend` / `PostgresSkillStore`, CLI uses them when `AGENT_DATABASE_URL`
  is set (else in-memory + warning), db tests marked `db`.
- **S2b part 2 committed `80596312`** "agent-v2: Postgres storage for notes and agent skills (S2b, part 2)":
  `apps/agent/agent_app/storage.py` (`AgentDatabase`, `PostgresMemoryBackend` CAS insert/update on version,
  `PostgresSkillStore` upsert version+1; plain parameterised SQL), `apps/agent/alembic.ini`,
  `alembic/env.py` (`AGENT_MIGRATION_DATABASE_URL`, version table `alembic_version_agent_rt`),
  `alembic/versions/0001_agent_rt.py` (check constraints mirror core caps; agent target ⇔ user_id ''),
  deps sqlalchemy[asyncio]/alembic/psycopg[binary] on agent-app (uv.lock updated). CLI: `AGENT_DATABASE_URL`
  → Postgres, else process memory (banner says which); `asyncio.run(loop_factory=SelectorEventLoop)` on
  Windows. `apps/agent/tests/test_storage.py` (6, marker `db`, each test runs its async part on a selector loop
  via `asyncio.run(loop_factory=...)` — `set_event_loop_policy` is flagged deprecated by pyright).
  Ran against a throwaway container `agent-rt-test` (postgres:17-alpine, 127.0.0.1:55432, password
  `agent-test`, db `agent_test`): 25 app tests passed; without the URL the 6 db tests skip.
  The user committed `.claude/rules/testing.md` themselves (`09536622` "feat: teting rules").
- **S2 is complete.** Not done / later: runtime DB role + grants for `agent_rt` (S3), sessions/compactions in
  Postgres (S3), injection scan of memory/skill writes (S3), real DeepSeek run of S1+S2 (user, own terminal).
- Next stage: S3 Harness — write the plan first and get approval.
- 2026-10-09 live runs with DeepSeek (`deepseek-v4-pro`, key pasted by the user in chat — told to rotate it;
  set only in the command and removed after): one question "mấy giờ rồi?" answered from the `<agent-context>`
  time without a tool call (1 model call, in=1463, out=68, 21.4s total; the model call itself ~17–19s).
  Memory test with Postgres: the agent called `memory` (target user), `/memory` showed the note, a new process +
  new session answered "Nam, thích câu trả lời ngắn gọn" from the system prompt (3.7s). DeepSeek latency varies a
  lot (3.7s to ~40s per call).
- Found: the first memory write after a long model call timed out at 15s although it was saved (retry said
  "Already saved", no duplicate). Isolated: Postgres ops 0.01–0.3s normally; after 70–100s idle a write took
  0.5–16s through Docker Desktop's port proxy (Windows). Keepalive helps but is not reliable there;
  `pool_recycle` did not help. **Committed `ab7f3856`**: `CONNECT_ARGS` (connect_timeout 10, TCP keepalives)
  on `AgentDatabase`, `STORAGE_TOOL_TIMEOUT_S = 30` for `memory` and `skill_*` tools, 2 tests.
- **For S3 (agreed with the user):** re-check storage latency on Postgres running on Linux (the real target),
  and add a safe retry for connection errors in the Postgres stores (writes are compare-and-swap / upsert, so a
  retry after an unknown outcome must re-read first).
- 2026-10-09: user: "đừng làm vội S3" — S3 waits for a plan and the user's explicit go.
- 2026-10-09 S3 plan approved with decisions: order S3a model → S3b tools+hooks → S3c state+trace (Postgres) →
  S3d channels + HTTP gateway → S3e plugins; DB model settings + AES-GCM encrypted keys in **S3d**; S3a providers =
  openai-compatible/DeepSeek + Anthropic (Google later); FastAPI for the gateway; plugin manifest **YAML like
  Hermes** (plugin.yaml, safe_load) — ask at S3e whether TOML too. Work rule: finish one sub-stage, commit, STOP and
  report; the next one only after the user's "go".
- **TODO (later, user asked to note it): the HTTP gateway starts with a bearer service token; replace/add HMAC
  request signing afterwards.**
- **Note (user, S3a step 5): the Anthropic adapter is provisional ("tạm dùng") — built and tested with fakes only
  (no Anthropic key); revisit with a real key before relying on it.**
- 2026-10-09 "go" for S3a (plan in /memories/session/plan.md, section "S3a detailed plan").
- S3a progress (uncommitted):
  - Verified docs: DeepSeek thinking is ON by default at effort high (explains ~17–19s calls); toggle
    `extra_body={"thinking":{"type":"enabled|disabled"}}`, effort `reasoning_effort` low/high/max (medium→high);
    **when the request carries tools, `reasoning_content` of ALL previous assistant messages must be sent back,
    else 400**. Anthropic SDK 1.11 (in uv.lock, uses httpx2): `thinking` {adaptive|disabled|enabled+budget},
    `output_config.effort` low..max, `messages.stream` helper, errors incl. OverloadedError/RequestTooLargeError,
    usage cache_read/cache_creation + output_tokens_details.thinking_tokens.
  - Core done: ThinkingBlock.provider/redacted_data; Usage cache_read/cache_write/reasoning tokens;
    `ReasoningEffort` off|low|medium|high on LlmRequest; `StreamSink`; `complete(request, *, sink)`;
    `harness/model/reasoning.py` (typed maps); error helpers moved to `errors.py` (retry_after_seconds,
    mentions_context_overflow, shorten, MAX_RETRY_AFTER_S); openai_compat: dialect auto (deepseek host),
    reasoning params, reasoning_content → ThinkingBlock(provider=deepseek) and sent back (deepseek dialect),
    sink, richer usage; new `harness/model/anthropic.py` (provisional); run_turn `observer` (TurnObserver:
    text/thinking/tool_call/tool_result), `LoopPolicy.reasoning`, `TurnResult.duration_s`; scripted models
    stream into the sink. agent-core depends on anthropic (uv.lock +2 lines). All 134 agent-core tests pass.
  - Next: app (profile provider/reasoning/dialect, env LLM_PROVIDER/LLM_REASONING, factory, CLI live output),
    new tests, commit, STOP and report.
- **S3a committed `95aa0d10`** "agent-v2: model layer (S3a) ...". App: `[model] provider = openai-compatible |
  anthropic`, `reasoning`, `dialect`; env `LLM_PROVIDER`, `LLM_REASONING` (invalid value → config error);
  `model_factory.resolve_model_settings()` / `ModelSettings`; `Agent.policy` (LoopPolicy with resolved
  reasoning); CLI `ConsoleObserver` prints text live, "(thinking...)" once per model call, tool lines as they run;
  `stats_line` shows steps, seconds, in/out, cached, reasoning, stop, compactions. Summariser + memory flush send
  `reasoning="off"`. dev agent.toml documents `reasoning` (left unset = provider default). Tests: new
  `test_anthropic.py` (mapping, cache breakpoints, thinking round trip, SSE through the real SDK via
  httpx2.MockTransport, errors), openai additions (reasoning stream, usage cache/reasoning, DeepSeek resend rule,
  dialect guess, params per effort), run_turn observer/reasoning, app tests. Ran full agent-core + apps/agent
  (core types changed): 194 passed, 6 db skipped; ruff, pyright strict, lint-imports clean. Fake CLI OK.
  **Not done: live DeepSeek run of S3a** (needs the user's key; compare reasoning off vs default).
- STOPPED after S3a as agreed; S3b (tool executor + hooks) waits for the user's "go".
- 2026-10-09 live S3a run (user's key, removed after): reasoning off 1.3s, DeepSeek default 1.4s (19 reasoning
  tokens, 1408/1463 cached), thinking low + get_datetime over 2 turns (Tokyo, London) 2.4s/2.1s with no 400 →
  reasoning_content resend works; prompt cache ~96%. Earlier 17–40s calls were probably DeepSeek load.
- 2026-10-09 S3b plan approved (Q1 block memory/skill writes, warn on tool results; Q2 4 parallel / 8 calls per
  step; Q3 no built-in post_model sensor; Q4 redact env secret values; Q5 port Hermes threat patterns, MIT,
  credited). "go" given. Plan in /memories/session/plan.md "S3b detailed plan".
- **S3b committed `949eb697`** "agent-core: hooks, technical guards and a parallel tool executor (S3b)".
  - `harness/guards/threats.py` (Hermes port, scopes all/context/strict, NFKC + invisible unicode),
    `guards/secrets.py` (`SecretRedactor`: key shapes + values of *KEY/TOKEN/SECRET/PASSWORD env vars ≥ 8 chars).
  - `harness/hooks/base.py`: `HookSet` with pre/post model and pre/post tool; pre_tool fail-closed (error or
    timeout → Deny), others fail-open; `Allow/Deny/Rewrite`. `hooks/builtin.py`: `injection_guard`,
    `secret_redactor(env)`, `result_warning`.
  - `ToolSpec.read_only` / `prompt_args`; `harness/tools/executor.py` `ToolExecutor` (consecutive read-only calls
    in parallel behind a semaphore, writes alone, results in call order, cap per step → error result).
  - `run_turn(hooks=)`, `flush_memory(hooks=)`; `LoopPolicy.max_parallel_tools` / `max_tool_calls_per_step`.
  - App: profile `[guards]` (injection_scan, redact_secrets, warn_tool_results, limits), `Agent.hooks`, CLI passes
    hooks to run_turn and /compact flush; dev agent.toml has the section.
  - Tests: new test_guards.py, test_executor.py, additions in test_run_turn/test_memory/test_agent_app.
    agent-core + apps/agent: 225 passed, 6 db skipped; ruff, pyright strict, lint-imports 6/6 clean.
  - Known limit: post_model hooks run after streaming, so the CLI shows the unhooked text.
  - STOPPED after S3b; S3c (Postgres sessions + trace) waits for a plan and the user's "go".
- 2026-10-09 S3c plan approved (trace = agent_turn + agent_turn_event, metadata only; keep traces forever,
  prune later; own role agent_rt_app, not infra bootstrap-roles.sh; latency probe in a Linux container; CLI
  --session + /sessions + /trace). "go" given.
- **S3c committed `b798d78d`** "agent: sessions and turn trace in Postgres, runtime role, safe retry (S3c)".
  - Core `agentcore/trace.py`: `TraceEvent` (model_call / tool_call / compaction / memory_flush, JSON detail),
    `TurnTrace`, `Tracer`, `InMemoryTracer`. `run_turn(tracer=)` writes one trace per turn at the end, also on
    failure (stop="error", error_kind), 10s timeout, tracer errors only logged. `TurnResult.turn_id` (uuid str).
    `ToolExecutor.execute()` returns `ToolRun` (result, duration, blocked_by); `Deny.hook`.
  - Migration `0002_sessions_trace`: agent_session (prompt + latest compaction on the row), agent_message
    (seq, uid unique, JSONB), agent_turn, agent_turn_event (no FK to session). Grants to agent_rt_app only if
    the role exists: DML on memory/skill/session/message, SELECT+INSERT on trace.
  - `agent db bootstrap-role` (`agent_app/db_roles.py`): env AGENT_MIGRATION_DATABASE_URL + AGENT_RT_APP_PASSWORD
    (≥16 chars); creates/updates role, CONNECT on the db, grants on tables that exist. Safe to re-run.
  - `storage.py`: `retrying()` (one retry, connection errors only), notes CAS unknown outcome read back,
    `PostgresSessionStore(db, agent=)` (upsert of the session row locks it → consecutive seq; uid makes a
    retried append idempotent; NUL → U+FFFD; other agent's session refused / never read; open_session,
    list_sessions), `PostgresTracer(db, agent=, model=)` with `last()`.
  - CLI: with AGENT_DATABASE_URL sessions + trace in Postgres; `--session` resumes ("resumed session X (n
    messages)"); `/sessions`, `/trace` (works in memory too); `agent db bootstrap-role`.
  - Tests: agent-core + apps/agent 254 passed incl. 15 Postgres tests (container agent-rt-test); ruff, pyright
    strict, lint-imports 6/6 clean. Manual fake-model CLI run with Postgres + resume OK.
  - Latency probe: psql from a Linux container on the same Docker network: ~0.2–0.7 ms per read/write, also
    after 30 s and 90 s idle. Same probe from Windows through the port proxy today: 1–5 ms, no stall. The
    earlier 16 s stall was the Docker Desktop port proxy, not Postgres.
  - Known: running bootstrap-role after a downgrade/upgrade is not needed (the migration grants when the role
    exists); grant lists live in two places (migration 0002, frozen, and db_roles.GRANTS).
  - STOPPED after S3c; S3d (channels + HTTP gateway + DB model settings) waits for a plan and "go".
- 2026-10-09 S3d split into S3d-1 / S3d-2 (user). Decisions: sync + SSE; busy -> wait 60s then 202 + poll;
  session = conversation (channel + conversation_id, default user_id) + epoch (reset keeps old session);
  crypto as a separate shared package (S3d-2); model settings DB > env > profile; admin HTTP endpoints like
  zalo-agent with a separate admin token (S3d-2).
- **S3d-1 committed `0c6fa3b3`** "agent: HTTP gateway, durable ingress, one run per session, repair of
  interrupted sessions (S3d-1)".
  - Core: `agentcore/loop/repair.py` `missing_tool_results()` (run_turn appends error results for dangling
    tool calls before the user message; trace event `repair`); executor `_truncate` keeps head + tail;
    `agentcore/channels.py` `InboundMessage`, `ChannelCapabilities`, `session_id_for(agent, channel,
    conversation, epoch)` (hash when > 200 chars).
  - Migration `0003_ingress`: `agent_conversation` (epoch), `agent_ingress` (unique tenant+agent+channel+
    external_id, status queued|processing|done|failed|dead, reply jsonb), event kind `repair`; grants +
    sequences; `db_roles.GRANTS` updated.
  - App: `ingress.py` (types, protocols, in-memory store/conversations/locks), `ingress_store.py` (Postgres;
    run lock = `pg_try_advisory_lock(hashtextextended(...))` polled on its own AUTOCOMMIT connection),
    `dispatcher.py` (accept -> drain per session oldest first -> run_turn -> finish/fail; wait(); sweeper
    requeues orphaned `processing` rows whose session lock is free, dead after 3 attempts; StreamObserver
    sends only names, no reasoning/tool content), `runtime.py` (`build_runtime` wiring), `gateway.py`
    (FastAPI), CLI `agent serve --profile ... [--fake] [--host 127.0.0.1] [--port 8088]` (needs
    `AGENT_GATEWAY_TOKEN` >= 32 chars); CLI chat holds the session lock (30s, "session busy").
  - Endpoints: POST /v1/chat, POST /v1/chat/stream (SSE accepted/text/thinking/tool_call/tool_result/
    done|error, ping 15s), GET /v1/ingress/{id}, POST /v1/conversations/reset, GET /v1/sessions/{id},
    GET /health, GET /ready. Body <= 64KB, text <= 8000 chars, extra fields refused.
  - Tests: agent-core + apps/agent 278 passed including Postgres tests (container); ruff, pyright strict,
    lint-imports 6/6 clean. Smoke run of `agent serve --fake` with Postgres: chat, duplicate message_id,
    401 without token, SSE OK.
  - Known limits: the frozen system prompt carries the first speaker's user notes (group chats, revisit with
    Zalo); queued messages run one turn each (no "collect"); a dispatcher waits for a session lock without
    timeout; HMAC still TODO.
  - STOPPED after S3d-1; S3d-2 (shared secret-cipher package, agent_model_settings, admin endpoints) waits
    for "go".
- **S3d-2 committed `981e7363`** "agent: model settings in the database with an encrypted key, admin
  endpoints; shared secret-cipher package (S3d-2)".
  - New workspace package `packages/secret-cipher` (module `secretcipher`): AES-256-GCM, base64(iv|tag|ct),
    Node wire format, mask_secret. Clinic `pema/config/secret_cipher_core.py` now re-exports it (clinic tests
    unchanged and pass); `apps/api` and `agent-app` depend on it; import-linter contract 7 "secret cipher is a
    leaf"; ruff src / pyright extraPaths / isort updated; `infra/docker/api.Dockerfile` copies the package.
  - Migration `0004_model_settings`: `agent_model_settings` (tenant, agent PK; provider, model, base_url,
    reasoning, dialect, api_key_enc, version); grant to agent_rt_app; `db_roles.GRANTS` updated.
  - `agent_app/model_settings.py`: `StoredModelSettings`, `resolve_effective` (DB > env > profile per field,
    `sources`, stored key decrypted with `AGENT_SECRET_ENCRYPTION_KEY`; undecryptable -> env key +
    `api_key_broken`), stores (in-memory / Postgres; clear keeps the row with NULLs so the version never goes
    back), `DynamicModel` (checks version at most every 5 s, rebuilds client on change, fills reasoning only
    when the request leaves it unset), `ModelAdmin` (show/update/clear/test; update: value sets, null clears,
    api_key "" keeps; logs field names only).
  - `model_factory.client_for(settings)`, `ModelSettings.dialect`; `build_agent(model=...)` (policy reasoning
    None then); `build_runtime` builds the DynamicModel (not with --fake) and the admin; tracer model name is
    read per turn.
  - Gateway: `AGENT_ADMIN_TOKEN` (>= 32 chars, must differ from the chat token) enables GET/PATCH/DELETE
    /v1/admin/model and POST /v1/admin/model/test; 5 failed admin logins per IP per minute -> 429; PATCH
    without encryption key -> 409.
  - CLI: `agent model show|set|clear|test --profile ...` (needs AGENT_DATABASE_URL; key via --api-key-env NAME
    or --ask-key, never argv; --clear FIELD).
  - Tests: agent-core + secret-cipher + apps/agent + clinic test_secret_cipher: 301 passed incl. Postgres;
    ruff, pyright strict, lint-imports 7/7 clean. Smoke `agent serve --fake` with admin token: GET/PATCH/DELETE,
    chat token refused on admin routes, DB row encrypted.
  - Note: a ruff format run over `apps/api/pema/config` reformatted clinic `env.py` (one blank line); reverted,
    not committed.
  - STOPPED after S3d-2. Next: S3e plugin loader (plan first, YAML manifest like Hermes; ask whether TOML too).
- 2026-10-09 live run of S3d with DeepSeek (`deepseek-v4-pro`, key stored encrypted via PATCH /v1/admin/model,
  cleared afterwards): admin test ok 1.1s; /v1/chat with get_datetime 3.4s / 3.3s (2 steps, cache ~90%),
  duplicate message_id 0.0s same reply; SSE accepted/tool_call/tool_result/text/done; reasoning switched to low
  then high via admin without restart; high: 2 parallel tool calls + thinking (29 reasoning tokens) 4.0s, no
  400; thinking block stored as `thinking:deepseek`; trace rows carry model + per-call timings. Reasoning low
  produced no thinking on simple questions. The user pasted the key in chat (first copy was 1 char short) —
  told to rotate it.
- 2026-10-09 S3e decisions (user): manifest TOML and YAML, lenient; locations bundled `apps/agent/plugins/`,
  `agents/<agent>/plugins/`, installed dir (`AGENT_PLUGIN_DIR`); plugins listed in agent.toml that fail stop the
  start, API-managed ones that fail get auto-disabled with the error stored; example plugin `calculate`; API now,
  UI later in `pema-agent/frontend`, marketplace later; pip install of plugin deps allowed (S3e-2). Split:
  S3e-1 core + hot host + calculate + `agent plugins list`; S3e-2 manager backend (`agent_plugin` table,
  encrypted secrets, install folder/zip/git, pip, `/v1/admin/plugins`, CLI); S3e-3 ChannelAdapter + delivery.
- **S3e-1 committed `a693729d`** "feat(agent): plugin host with hot enable/disable and a bundled calculate plugin".
  - `agent_app/plugins/manifest.py`: `PluginManifest` (name regex, version, description, api=1, entry,
    requires_env, requires, user_config of `ConfigField` with `sensitive`), `read_manifest` (TOML wins over YAML,
    `yaml.safe_load`), `discover(roots)` -> `Discovery(plugins, broken)`; a name found twice raises `PluginError`.
  - `agent_app/plugins/host.py`: `PluginHost(sources, env)` enable/disable/close/contributions/status, `version`
    counter; `PluginContext` (config = defaults + given, `secret()` only for requires_env, register_tool /
    register_prompt_section / register_hook / on_disable, each returns a disposer); module imported as
    `agent_plugin_<name>_<gen>`; failed register disposes everything and drops the module; duplicate tool or
    section names across plugins refused.
  - `agent_app/live.py` `LiveAgent`: rebuilds the `Agent` when `host.version` changes; `enable()` rolls back a
    plugin that clashes with a built-in tool/section; `use_model()` for tests. Memory backend and skill store are
    created once in `build_runtime`, so notes survive rebuilds. `Runtime.live`, properties `agent`/`plugins`,
    `close()`; Dispatcher takes `Agent | LiveAgent` and reads the current agent per turn.
  - `build_agent(plugins=Contributions)`: plugin tools after built-ins; plugin sections after the profile's
    unless the profile lists them; plugin hooks after guards. Profile `[plugins] enabled` + `[plugins.<name>]`.
    `runtime.plugin_roots`, `start_plugins` (fail loud), `BUNDLED_PLUGINS`, `PLUGIN_DIR_ENV`.
  - `apps/agent/plugins/calculate`: safe AST arithmetic (+ - * / // % **, bool/complex/names/calls refused, 100
    digit cap, power pre-check, precision setting 0-15) + session section "## Arithmetic". Enabled in dev agent.
  - CLI `agent plugins list --profile P` (JSON: enabled_in_profile, plugins status, broken, error).
  - deps: pyyaml (apps/agent), types-pyyaml (dev). Tests `tests/test_plugins.py` (38); full agent-core +
    secret-cipher + apps/agent with DB: 332 passed; ruff, pyright strict, lint-imports 7/7 clean.
  - STOPPED after S3e-1. Next: S3e-2 after the user's "go".
- **S3e-2 committed `3f6a4ffb`** "feat(agent): plugin manager with stored choices, encrypted settings, install
  and admin API". (User pushed `feat/agent-v2` to origin after S3e-1.)
  - Migration `0005_plugins`: `agent_rt.agent_plugin` (tenant_id, agent, name PK; enabled, config jsonb,
    secrets_enc, install jsonb, last_error, updated_at); grant to `agent_rt_app`; added to `db_roles.DATA_TABLES`.
  - `plugins/state.py`: `PluginState`, in-memory + Postgres stores (list/get/save/delete/fingerprint =
    count + max(updated_at)).
  - `plugins/install.py`: `PluginInstaller(root, runner, allow_local_git)`: stage_folder / stage_zip (20 MB, 64
    MB unpacked, 2000 entries, no `..`/absolute/links, top folder unwrapped) / stage_git (https only, no
    credentials, ref regex, `-c protocol.file.allow=never`, `--`, `.git` removed, commit recorded);
    `install_requirements` (plain specs only, `pip --target <plugin>/.deps` or `uv pip`); atomic `commit` swap.
    Host appends `<plugin>/.deps` to sys.path while enabled.
  - `plugins/manager.py` `PluginManager`: stored row overrides profile; `refresh()` reconciles before each turn
    (dispatcher `before_turn`, CLI chat), at most every 5 s → other processes follow within seconds; enable /
    disable / configure (validated against `user_config` types; sensitive = one encrypted JSON, "" keeps, null
    clears); a failing managed plugin is switched off and `last_error` stored; install_folder/zip/git (name
    clash with bundled/agent refused, upgrade reloads), uninstall (installed only); `describe` gives the UI
    form (settings with type/title/required/sensitive/default/value masked/source).
  - Gateway: `/v1/admin/plugins` GET, `/{name}` GET, `/install` POST (folder|git), `/install/zip` POST raw body
    (20 MB limit), `/{name}/enable|disable` POST, `/{name}/settings` PATCH, `/{name}` DELETE; errors 404 /
    409 no_encryption_key / 422 plugin_error. `create_app(plugins=...)`.
  - CLI `agent plugins list|enable|disable|set|install|uninstall --profile P` (`--set K=V` JSON-or-text,
    `--unset K`, `--secret K` prompt; changes need AGENT_DATABASE_URL).
  - Tests: `tests/test_plugin_manager.py` (27, incl. real local git), DB tests in `test_ingress_db.py`; full
    agent-core + secret-cipher + apps/agent with DB: 361 passed; ruff, pyright, lint-imports clean. CLI smoke
    against the test DB ok.
  - Known limits: AGENT_PLUGIN_DIR must be shared by all processes; a bad setting on an enabled plugin switches
    it off (fix the setting, enable again); an in-flight turn keeps the old plugin objects.
  - STOPPED after S3e-2. Next: S3e-3 (ChannelAdapter + reply delivery with retry + migration) after "go".
- **S3e-3 committed `fac0bfcf`** "feat(agent): chat channels from plugins with ordered, retried reply delivery".
  - `agentcore/channels.py`: `ChannelAdapter` protocol (name, capabilities, start(receive), stop, send),
    `OutboundMessage` (conversation_id, text, user_id, reply_to, part/parts, metadata), `ChannelSendError`
    (retryable, retry_after_s), `Receive`, `split_reply` (paragraph > line > space > hard cut),
    `valid_channel_name`.
  - Plugins: `ctx.register_channel(adapter)` (name rules, `http`/`cli` reserved, unique across plugins);
    `Contributions.channels`, `PluginStatus.channels`, manager describe shows them.
  - Migration `0006_delivery`: agent_ingress `delivery` (pending|sending|sent|failed|skipped, NULL for HTTP),
    `delivery_attempts`, `delivered_parts`, `delivery_error`, `delivery_at`, `delivery_after`; partial index.
  - Ingress stores: `accept(deliver=)`, `due_deliveries`, `claim_delivery` (turn over + due/stale + no earlier
    open delivery in the session), `delivery_progress`, `retry_delivery(after_s)`, `finish_delivery`. Postgres
    statements now use `SELECT *` / `RETURNING *` (rows read by name; avoids S608 interpolation).
  - Dispatcher: `accept(deliver=)`, `on_finished(listener)`.
  - `agent_app/channel_hub.py` `ChannelHub` + `DeliverySettings` (tick 2 s, 4 attempts, backoff 2/10/60 s,
    send timeout 30 s, stale 120 s): tick = plugin refresh + start/stop adapters with their plugin (start errors
    shown, retried after 30 s) + schedule due replies; receive forces the channel name, drops id-less/empty
    messages, cuts text to 8000; deliver resumes after sent parts; refused (retryable False) or attempts used
    up -> failed; failed turn -> skipped (nothing sent). At-least-once on a crash mid-send.
  - Wiring: `Runtime.channel_hub(dispatcher)`; `create_app(channels=)` runs the hub in the lifespan (stop:
    sweeper/hub tasks, dispatcher.close, hub.close); `GET /v1/admin/channels`; `/v1/ingress/{id}` shows
    `delivery`. `agent serve` wires it.
  - Tests: `tests/test_channels.py` (9) + Postgres delivery test in `test_ingress_db.py`; full agent-core +
    secret-cipher + apps/agent with DB: 371 passed; ruff, pyright, lint-imports clean. Smoke `agent serve --fake`
    ok (channels [] , chat echo).
  - Not done (later): a reply for failed turns (users on a channel get silence), streaming to channels,
    per-channel rate limits, real Zalo adapter (domain plugin).
  - STOPPED after S3e-3 — S3 complete. Next: S4 (plan first: retry backoff + Retry-After, stream idle watchdog,
    repeat-tool reminder 3/5/8, collect/steer, keyless replay tests; HMAC for the gateway still TODO).
- 2026-10-09 S4 split agreed: S4a recovery of model calls, S4b loop guard (repeat-tool reminder 3/5/8, tool
  error streak, maybe token budget), S4c collect/steer, S4d keyless replay tests + verifier hook. HMAC deferred
  (see "Deferred by the user"). Failure reply on channels: a configurable text per agent (option a).
- **S4a committed `ff0c66a0`** "feat(agent): retry failed model calls, recover from context overflow, limit turn
  time".
  - `agentcore/loop/retry.py` `RetryPolicy` (max_retries 4, base 0.5 s doubling, cap 10 s, jitter 20 %,
    `Retry-After` wins; retries rate_limit / transient / empty_response). `LoopPolicy.retry`, `.max_turn_s`
    (300 s, None = no limit). The old one-off empty-completion retry is gone (covered by the policy).
  - `run_turn(sleep=, timer=)` (tests skip pauses and move time); retry loop in `call_model`: each failed call is
    a `model_call` error event, each retry a `model_retry` event (duration = pause; detail error_kind, retry,
    streamed); `context_overflow` → `compact(force=True)` once and resend (trace `compaction` detail `forced`),
    a second overflow or no context manager fails the turn; auth/config/unknown fail at once.
  - Deadline: before steps 2..n, if `max_turn_s` passed → one last call without tools, `stop = "deadline"`
    (`TurnStop`/`TraceStop` gained it). Failed-turn trace `steps` = highest step reached, not calls.
  - `RetryObserver` (runtime_checkable): observers with `retry(error_kind)` hear when streamed text became void.
    SSE `StreamObserver` sends `event: retry`; CLI prints "(the model stopped: …; trying again)".
  - Adapters: `max_retries` default 0 (SDK no longer retries on its own), `timeout_s` = longest gap between
    stream pieces (read timeout), new `connect_timeout_s` 10 s (`openai.Timeout(read, connect=...)`).
  - Migration `0007_retry_deadline`: agent_turn stop + 'deadline', agent_turn_event kind + 'model_retry'.
  - Profile: `[agent] failure_reply` (≤ 1000 chars; dev has an English sentence), `[loop] max_turn_s`;
    `ChannelHub(failure_reply=)` sends it for failed turns (delivery `sent`, the record keeps `error_kind`);
    `Runtime.channel_hub` passes the profile's text. HTTP keeps its error status.
  - Tests: new `packages/agent-core/tests/test_recovery.py` (8); run_turn/gateway/storage/channels tests updated
    (gateway rate-limit test now counts 1 + 4 calls). Full agent-core + secret-cipher + apps/agent with DB:
    381 passed; ruff, pyright strict, lint-imports 7/7 clean. **Not run against a real model** (no key in env).
  - STOPPED after S4a. Next: S4b plan, after the user's "go".
- 2026-10-09 S4b decisions (user "go" on the proposals): count per turn (not per session), hard stop yes,
  token budget included.
- **S4b committed `ccb21241`** "feat(agent): loop guard for repeated and failing tool calls, turn token budget".
  - `agentcore/loop/guard.py`: `LoopGuardPolicy` (repeat_thresholds (3,5,8), stop_after_repeats 10 / None,
    error_streak_remind 3, error_streak_stop 5, exclude, preview_chars 500; validated: thresholds ≥ 2, unique,
    stop above the last threshold, error stop above remind), `LoopGuard.observe(use, result) -> [GuardNote]`,
    `canonical_arguments` (sorted-key JSON; raw text when not JSON). Port of deepseek-harness
    `packages/guard/repeat-tool-reminder` (MIT, credited in the module docstring; reminder wording theirs).
    Consecutive identical calls; a different call resets; excluded tools transparent; error streak over any
    tool, a success resets.
  - `run_turn`: one `LoopGuard` per turn; after each step's tools `watch()` records `guard` trace events
    (name = tool, detail reason/count/stop) and queues reminder texts; they go into the next call's context
    block (`TurnPrompt.context(step, notes)`), cleared after a successful call, never stored. A stop note →
    final call without tools, `stop = "loop"`. `LoopPolicy.max_turn_tokens` (input + output of the turn) checked
    before steps 2..n → `stop = "budget"`. `LoopPolicy.guard`.
  - Migration `0008_loop_guard`: agent_turn stop + 'budget', 'loop'; agent_turn_event kind + 'guard'.
  - Profile `[loop]`: `max_turn_tokens`, `repeat_thresholds`, `stop_after_repeats`, `error_streak_remind`,
    `error_streak_stop` (validated at load); dev agent.toml documents them.
  - Tests: new `packages/agent-core/tests/test_loop_guard.py` (14), app profile test, Postgres trace test in
    `test_storage.py`. Full agent-core + secret-cipher + apps/agent with DB: 397 passed; ruff, pyright strict,
    lint-imports 7/7 clean. Not run against a real model.
  - STOPPED after S4b. Next: S4c plan (collect/steer), after the user's "go".
- 2026-10-09 S4c decisions (user "go" on the proposals): default mode `steer` (like OpenClaw), join only the
  same person's messages, quiet window 0.8 s (at most 3 s). `interrupt` not built. Reference read:
  OpenClaw `docs/concepts/queue.md`, `queue-steering.md`.
- **S4c committed `09c2096a`** "feat(agent): collect and steer messages that come while a turn runs".
  - `DispatchSettings`: `queue_mode` (followup | collect | steer; default followup here so explicit settings in
    tests keep the old behaviour), `queue_by_channel`, `debounce_s`, `max_wait_s`, `max_batch`, `mode_for()`.
    `Runtime.dispatcher()` without settings builds them from the profile `[loop]` (`queue_mode` default
    `steer`, `queue_by_channel`, `queue_debounce_s` 0.8, `queue_max_wait_s` 3.0, `queue_max_batch` 20;
    max_wait ≥ debounce validated). `QueueMode` lives in `agent_app.profile`.
  - Drain: for collect/steer `_quiet()` waits until the session's queued count stops changing (debounce, cap
    max_wait), then `_gather()` claims the next queued messages of the same user, stopping at another user's
    message (order kept). `_process(lead, joined, steer=)` runs one turn on the texts joined with a blank line;
    with steer, `run_turn(steer=)` gathers more after each tool batch. All joined records end with the lead's
    reply or error; a joined record with a delivery gets `finish_delivery(skipped, "answered together with
    message N")` before it is finished (the hub never sends it); waiters/observers of joined ids are released.
  - Core: `run_turn(steer=, collected=)`: steered texts stored as user messages after the tool results (the
    Anthropic adapter merges consecutive user content); `inbox` trace events (collect at step 0, steer per
    step). Migration `0009_inbox` adds the event kind. Ingress stores: `queued_in_session(tenant, session,
    limit)`.
  - Tests: new `apps/agent/tests/test_queue_modes.py` (6), core steer test in `test_run_turn.py`, Postgres
    collect test in `test_ingress_db.py`. Full suite 405 passed; ruff, pyright strict, lint-imports clean.
  - Known: a crash mid-turn requeues the joined messages too (they may run again; at-least-once); every
    message now waits ~0.8 s before its turn starts in collect/steer; the CLI chat does not use the queue.
  - STOPPED after S4c. Next: S4d plan, after the user's "go".
- 2026-10-09 S4d decisions (user): own JSONL cassette format (not deepseek's Session JSONL); three real
  scenarios recorded by the assistant with the user's key (option b): (a) a plain question, (b) "mấy giờ rồi"
  with `get_datetime`, (c) arithmetic through the `calculate` plugin plus a memory note; verifier hook later.
- **S4d committed `8f765862`** "feat(agent): record a model once and replay it in keyless tests".
  - `agentcore/harness/model/replay.py`: lines `Header` (format 1, recorded_at, model), `Turn` (user_text),
    `Call` (request summary = tool names + start of the user's latest words (context block skipped, 300
    chars) + reasoning; `stream` deltas; `result` AssistantResult or `error` kind/message/retry_after_s).
    `Cassette.load` (header first, format check, exactly one of result/error), `CassetteWriter` (line by line,
    LF), `RecordingModel(inner, writer)`, `ReplayModel(cassette, strict=True)` (drift → `CassetteError` with
    "record the scenario again", extra calls, `assert_consumed()`). Credited to deepseek-harness llm-replay (MIT).
  - `build_runtime(model_wrapper=)`: wraps the model all calls use, summariser included (Echo when fake).
  - `agent_app/replay.py`: `replay(cassette, profile)` runs the turns like `agent chat` (user `cli-user`,
    channel `cli`, env {}, in-memory stores, no retry pauses, no turn deadline) and returns a transcript
    (user/assistant text, `call <tool> <args>`, `result <tool> ok|error: …`, stop/steps/compactions, trace event
    kinds) masked for datetimes, dates, times, uuids, weekdays.
  - CLI: `agent chat --record CASSETTE` (records turns + calls; warns that /compact is not replayable);
    `agent replay CASSETTE --profile P [--expect FILE] [--update]` (diff on mismatch, exit 1).
  - Fixtures `apps/agent/tests/replays/<name>/{cassette.jsonl, expected.txt}`: `echo-two-turns` (recorded with
    --fake) and `calculate-after-rate-limit` (hand-written: tool call, rate-limit error line, retry). Tests:
    `packages/agent-core/tests/test_replay.py`, `apps/agent/tests/test_replays.py` (runs every scenario).
    Full suite 418 passed; ruff, pyright strict, lint-imports clean.
  - To add a real scenario (without AGENT_DATABASE_URL, so memory starts empty): set LLM_API_KEY / LLM_BASE_URL
    / LLM_MODEL in the terminal, `uv run agent chat --profile apps/agent/agents/dev --record
    apps/agent/tests/replays/<name>/cassette.jsonl`, type the turns, `/exit`; then `uv run agent replay
    <cassette> --profile apps/agent/agents/dev --expect <dir>/expected.txt --update`; check the cassette has no
    secret before committing. Any change to the dev agent's tools makes the cassettes drift: re-record.
  - STOPPED after S4d. Pending: record the 3 real scenarios with the user's key.
- **Real scenarios committed `f7ff799b`** (2026-10-09, deepseek-v4-pro, no database, key set only in the
  recording terminal and removed after): `plain-question` (1 call), `time-tool` (get_datetime Asia/Tokyo, 2
  calls), `calculate-and-remember` (calculate, then a memory note about the user, 4 calls). Each turn took
  3–4 s with ~90 % prompt cache. Cassettes scanned: no key or token. The replays run the real tools (calculate,
  memory) against the recorded model replies. **S4 is complete.** The user pasted the key in chat again —
  told to rotate it.

## S1 progress log (newest last)

- Approved by the user ("làm tiếp s1"). Design refinements made while starting (within D1–D7):
  - Three section types instead of one class with a scope flag, so a section can only read what its scope
    allows: `SessionSection(name, render(env))`, `TurnSection(name, render(env, turn))`,
    `StepSection(name, render(env, turn, step))`. `PromptEnv(agent_name, persona, timezone, tool_names)`,
    `TurnInfo(now aware, channel)`, `StepInfo(step, max_steps, final)`.
  - Fingerprint = hash of the configuration (env + section names), NOT of the rendered text: in S2 the memory
    snapshot / skills index will live in session sections and must stay frozen when they change mid-session.
    Consequence: editing a built-in section's wording in code does not rebuild old sessions (start a new one).
  - Channel lives in `TurnInfo` (runtime), not in the profile or the fingerprint.
  - The transient context goes at the tail: appended as an extra text block to the last message when that is the
    user's message (avoids two user messages in a row; some DeepSeek models reject that), else as a new user
    message after tool results. Never stored.
  - The final-turn note is always added on the final call, even when the profile leaves out `status`.
  - A shared `agentcore/clock.py` (utc_now, weekday names, zone lookup) used by `get_datetime` and the
    `environment` section.
- Code written (uncommitted): `agentcore/clock.py`, `agentcore/prompt/{sections,builtin,builder,__init__}.py`,
  `StoredPrompt` + `load_prompt`/`save_prompt` on `SessionStore` and `InMemorySessionStore`, `run_turn(prompt=,
  channel=, clock=)` (system frozen before the user message is stored), `PromptBuilder.fixed(text)` for tests /
  simple callers, profile `system_prompt_file` + `[prompt] sections`, `profiles/prompts/dev.md`, CLI
  `build_prompt`, `show_prompt`, `/prompt`. Existing 75 tests pass after the signature change; pyright clean.
- Next: new tests for the prompt package, store, profile and CLI; then real DeepSeek check; then commit.
- Tests added: `packages/agent-core/tests/test_prompt.py` (17 tests: registry, fingerprint, freeze per session /
  tenant, cache-break log, context block text, status/final note, turn vs step render counts, `with_context`,
  full two-turn request snapshot with a fixed clock) + 4 in `apps/agent/tests/test_agent_app.py` (prompt file,
  both sources refused, unknown section exits 2, `/prompt` output). `EchoModel` now echoes only the first block
  of the last user message (the context block is appended after it).
- Status: 95 tests pass; ruff, ruff format, pyright strict, lint-imports (6/6) clean. Fake CLI run OK.
- Remaining for S1: real DeepSeek run (needs the user to set `LLM_API_KEY` in their own terminal), then commit
  on `feat/agent-v2` (S1 files only, not the staged `AGENTS.md` / handoff skill unless the user says so).
- **Committed `f4b68879`** "agent-v2: prompt layer (S1) ..." (S1 files only). The user had already committed
  `AGENTS.md` + the handoff skill themselves as `78d84919` "handoff sn".
- Still open: a real DeepSeek run of S1 (system prompt + `<agent-context>` with tools). The key is not in the
  environment; the user must set `$env:LLM_API_KEY` in their own terminal. Command (from
  `pema-agent/backend`): `$env:LLM_BASE_URL="https://api.deepseek.com"; $env:LLM_MODEL="deepseek-v4-pro";
  uv run agent chat --profile apps/agent/profiles/dev.toml`, then ask "mấy giờ rồi?" and `/prompt`.
- Next stage after that: S2 Context (plan first, get approval).

## Facts learned the hard way

- Run setup with `uv sync --all-packages` (the Makefile does). `openai` 3.22 uses **`httpx2`** (not `httpx`):
  tests mock with `httpx2.MockTransport`.
- pyright strict: use typed default factories (`Field(default_factory=list[X])`), avoid `sys.stdout.reconfigure`
  directly (use `getattr`), no `# pyright: ignore`.
- PowerShell 5.1 pipes to native programs in ASCII unless `$OutputEncoding = [Text.UTF8Encoding]::new()`;
  to read UTF-8 output also set `[Console]::OutputEncoding`.
- PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM: never use it on source files (edit with the editor
  tools instead).
- The user switches branches themselves. Always check `git branch --show-current` before running; if the code
  is on another branch, use a temporary `git worktree` (then remove it) — do not `git checkout` without asking.
- Real model check passed: DeepSeek, OpenAI-compatible, `LLM_BASE_URL=https://api.deepseek.com`,
  `LLM_MODEL=deepseek-v4-pro`; tool call + multi-turn history worked. The user pasted their API key in chat
  ([REDACTED]); they were told to rotate it. Never write a key to a file; set it only in the terminal session and
  remove it after.
- DeepSeek thinking mode (`reasoning_effort` + `extra_body.thinking`) is not sent yet; in S3, thinking + tool
  calls needs `reasoning_content` sent back on later steps (claw-code has a fix for this).

## User preferences

- Vietnamese, short. Asks for plans before code ("đừng làm vội", "lên kế hoạch cụ thể để tôi duyệt").
- Wants careful work, full unit tests; sometimes runs tests themselves, sometimes says "bạn tự chạy".
- No time estimates. No markdown docs in the repo unless asked.
- Repo rules: `AGENT.md`, `CLAUDE.md` (synthetic data only; no AI attribution; UI work rules don't apply here).

## Loose ends

- `AGENTS.md` and `.claude/skills/handoff/` were committed by the user (`78d84919`).
- First action next session: ask the user what comes next (S5 Graph, HMAC for the gateway, a Zalo channel
  plugin, the plugin UI, the verifier hook). S3e and S4 run against DeepSeek only through the recorded
  scenarios so far.

### Deferred: verifier hook (user, 2026-10-09)

- A hook that checks the final answer before it is returned (e.g. clinic rules: no diagnosis, no promised
  prices) and asks the model for one revision. Build it when a concrete rule exists, likely as a new hook
  kind plugins can register (`register_hook`), with one revision at most and a trace event.
- A stale custom agent draft exists at `C:\Users\My PC\AppData\Roaming\Code\User\prompts\zalo-agent-builder.agent.md`
  (written before the "general core" decision; it says Hermes-based). Offer to rewrite or delete it.

### Known limits of S3e (handle later; the user asked to keep them here)

- ~~**Failed turn on a channel gets no answer.**~~ Done in S4a: `[agent] failure_reply` is sent through the
  channel when set; empty keeps the old behaviour (`delivery = 'skipped'`).
- **Delivery is at least once.** A process that dies mid-send (or a send that times out but went through) makes
  the next attempt repeat that part. Possible fix: pass an idempotency key (`ingress_id` + part) in
  `OutboundMessage` for channels whose API supports it; dedupe on the channel side.
- **No streaming to channels.** Replies go out only when the turn is done (`ChannelCapabilities.streaming` is
  unused). Later: typing indicator / partial sends for channels that support it.
- **No per-channel rate limit.** The hub sends as fast as replies finish (max 4 at once per process). Add a
  per-channel token bucket in `ChannelHub` when a real channel (Zalo) has limits; honour `retry_after_s` already
  works per message only.
- Plugin manager limits (S3e-2): `AGENT_PLUGIN_DIR` must be shared by all processes; a bad setting on an enabled
  plugin switches it off (fix the setting, enable again); an in-flight turn keeps the old plugin objects.

### Deferred by the user (2026-10-09)

- **HMAC signing for the HTTP gateway** — not in S4; do it later as its own small step. Today the gateway
  checks a bearer token only (`AGENT_GATEWAY_TOKEN`, admin routes `AGENT_ADMIN_TOKEN`, see
  `apps/agent/agent_app/gateway.py`). Plan when picked up: the caller signs `timestamp + body` with a shared
  secret (`X-Agent-Timestamp`, `X-Agent-Signature`, HMAC-SHA256), the gateway rejects a bad signature or a
  timestamp older than ~5 min (replay), compares with `hmac.compare_digest`; keep the bearer token as well.

## Suggested skills

- `handoff` (`.claude/skills/handoff/SKILL.md`) — run again at the end of the next session to refresh this doc.
- `agent-customization` — only if the user asks to rewrite the stale `.agent.md` file above.
- Project `pema-*` skills are for UI/design work and do not apply to agent-v2.
