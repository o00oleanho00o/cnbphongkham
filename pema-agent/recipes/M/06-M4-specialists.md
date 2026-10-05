# M4 — Specialist agents (Scheduler, Knowledge, Reviewer), TaskResult, budgets

## Goal
The care agent can delegate, at **depth 1 only**, to three specialist agents configured as data (not code), exchanging structured `TaskResult`s under a budget.

## Read first
1. `PLAN-AI01-M.md` §9, §11.
2. D1: agent config store (persona, tool allowlist, profile), tool registry, token accounting. P: profiles.
3. B1 actions: `appointment.search_slots`, `appointment.book`; D3: `kb_search`, `kb_ingest`, `kb_list`.

## Ingredients
- `pema/care/task_result.py`: `TaskResult{summary, artifacts[], citations[], needs_human: bool, confidence: float}`.
- `pema/care/budget.py`: per-turn budget (max 3 specialists, 8 tool steps each, token ceiling, deadline 3 min interactive / 20 min background).
- `pema/care/specialists/`: `scheduler.py`, `knowledge.py`, `reviewer.py` as **config factories** producing D1 agent records + a `delegate` tool available only to care agents.
- Seed: three agent records in `agent.agents` with the tool allowlists from PLAN §9.

## Steps
1. `delegate(agent_name, task, context_ref)` tool: registered for care agents only; specialists **do not** have it (depth 1 enforced by allowlist, asserted in tests).
2. Specialists return `TaskResult` via a schema-constrained final answer; the care agent reads fields only, never free text.
3. SchedulerAgent: `search_slots` free; `book` creates a draft unless M3 says L1 `appointment_confirm` applies to a patient-chosen slot.
4. KnowledgeAgent: `kb_search` must return citations; empty citations → `needs_human=True`.
5. ReviewerAgent: read-only; scores a draft against a checklist stored in `agent.skills` row `review_checklist` (has sources? diagnosis present? PII present? template respected? depth classified correctly?). Default checklist flagged `pending_doctor_approval`.
6. `budget.py`: wraps every delegation; on exhaustion → `TaskResult(needs_human=True)` and `actions_log` kind `budget_exhausted`.
7. Profile inheritance: the care agent runs with the strictest profile among itself and the specialists it calls; toward patients always `patient_channel`.
8. Record each delegation in `agent.tasks` with `parent_id`, tokens, cost, timing.

## Acceptance
- pytest with fake LLM: a specialist calling `delegate` fails at tool-resolution time; budget exhaustion yields `needs_human`; KnowledgeAgent with no citations yields `needs_human`; ReviewerAgent flags a draft containing a fake phone number; `agent.tasks` tree has depth ≤ 1.
- Real run with Ollama on the sample flow "find a slot next week + aftercare guidance" produces a `review_item` with slot + cited guidance (manual check, record timing).
- ruff, pyright pass.

## Out of scope
- No general coordinator agent; the care agent is the initiator.
- No new tools beyond the allowlists above.

## Report
Use `_REPORT-TEMPLATE.md`. Include measured latency of the sample flow.
