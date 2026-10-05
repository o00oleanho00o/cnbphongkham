# M2b — Conversation control state machine and the `handoff` skill

## Goal
The agent **decides by itself** when a human is needed (there is no "talk to a human" button), moves the conversation to `HANDOFF_ROUTING`, goes quiet correctly, and **only staff** can return it to `AUTO`.

## Read first
1. `PLAN-AI01-M.md` §5, §6, §15 (decisions 1, 4).
2. P: `redflags.py` (D5), `pii.py`, profiles. S: per-thread `bot_enabled` flag (ported from zalo-agent) — extend it, do not rewrite.
3. D1: how skills/instructions are declared for an agent.

## Ingredients
- `pema/care/control.py`: state machine + API `request_handoff`, `accept`, `decline`, `release_to_auto(note, override_level=None, until=None)`.
- `pema/care/depth.py`: depth classifier D1–D5 (rules + schema-constrained LLM; D5 is **rules only**, from P).
- `pema/care/handoff_skill.py`: runs before every reply, returns `HandoffDecision`.
- Matrix config: `agent.skills` row `handoff` with `classifier_config` jsonb; defaults flagged `pending_doctor_approval=True`.

## Steps
1. `HandoffDecision` (pydantic): `action: answer|handoff`, `reason`, `depth: D1..D5`, `confidence: float`, `required_skill: str`, `urgency: normal|urgent|critical`.
2. `depth.py` order: (a) red flags from P → D5 immediately, **no LLM call**; (b) keyword/intent rules for D1 (administrative); (c) LLM with JSON schema for D2–D4, with `confidence`.
3. `handoff_skill.py` weighs the signals in PLAN §6: depth, confidence < threshold, patient state (VIP, complex history, past complaint, unverified → D1 only), sentiment/repeated question/patient asking for a human (a signal, not a command), out of hours, within 48h after a procedure, exceeds autonomy level. Thresholds come from `classifier_config`, never hardcoded.
4. `control.py`:
   - `AUTO → HANDOFF_ROUTING`: insert `handoff_requests` (candidates empty; M2c fills), send **one** template holding message via ChannelSend, store a PII-masked context summary on the request.
   - `HANDOFF_ROUTING → STAFF`: on `accept(staff_id)`; set `staff_owner`.
   - `STAFF → AUTO`: only via `release_to_auto` by a user with a staff role; store `release_note` into `care_memory` source `staff`; if `override_level` given → write `autonomy_override` (read by M3).
   - No automatic path back to AUTO; `auto_release_after` defaults to null and requires an explicit config flag to be non-null.
5. While in `HANDOFF_ROUTING`/`STAFF`: `loop.run_turn` records history only and produces **suggestions for staff** (`review_item` kind `suggestion`, never sent).
6. Log every transition to `actions_log` with `initiator`.

## Acceptance
- pytest: red-flag message → `handoff` D5 `critical` and the LLM mock is **not called**; unverified patient asking D2 → handoff; VIP configured "human from D2" → handoff at D2; staff `release_to_auto` → AUTO; patient or system calling it → `PermissionError`; no test may show a time-based return to AUTO.
- Exactly **one** holding message even if several events arrive during routing.
- ruff, pyright pass.

## Out of scope
- No staff selection, SLA or on-call (M2c).
- No final thresholds; all defaults carry `pending_doctor_approval`.

## Report
Use `_REPORT-TEMPLATE.md`. List the temporary default thresholds.
