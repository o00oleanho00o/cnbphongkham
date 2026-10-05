# M2a — Event-driven turns, daily tick, priority, send window, caps

## Goal
A care agent is **woken by events** and by a **06:00 tick**, runs its turn through D1's shared pipeline, in priority order, inside the allowed send window, never above the per-patient proactive cap.

## Read first
1. `PLAN-AI01-M.md` §2, §3, §14.
2. D1: `HarnessProcessor` entry point (module per `PORT-MAP.md`). S: scheduler, proactive cap, per-thread `bot_enabled` flag.
3. B2: CRM policy engine emitting events (D+1/3/7, overdue, 90/180 days, birthday).

## Ingredients
- `pema/care/loop.py`: `run_turn(care_agent_id, event)`.
- `pema/care/tick.py`: `daily_tick(clinic_id, now)`.
- `pema/care/priority.py`: 3-level priority queue.
- `pema/care/ports.py`: `Protocol Harness`, `Protocol Scheduler`, `Protocol ChannelSend` if the other packages are not there yet.

## Steps
1. `CareEvent` (pydantic): `kind` (`patient_message|session_completed|milestone_due|visit_overdue|no_show|dormant|birthday|staff_command|doctor_edit|daily_tick`), `initiator` (`patient|system|staff|doctor`), `patient_ref` (code, no PII), `payload`, `occurred_at`.
2. Subscribe to events from B2/S and from the Zalo webhook (C1/C2) → push to the priority queue: **patient message > due event > tick**.
3. `run_turn`: load patient context via `actions/` (PII-masked, minimal) → check `conversation_control.state` (if not `AUTO` → record history only, no action, except what M2c specifies) → call `HarnessProcessor` with the care-agent persona → get decision → act according to autonomy level (M3; if M3 is absent treat everything as L0 = create `review_item`).
4. `daily_tick`: 06:00 `Asia/Ho_Chi_Minh`, patients in batches; mostly **rules without LLM** (missed milestone? stale pending work?); call the LLM only when something must be drafted.
5. Send window default 08:00–20:00 (`clinic.settings`): messages produced outside it are queued for the start of the next window.
6. Per-(patient, day) proactive cap via S's atomic mechanism; over cap → `actions_log` entry `paused` with reason.
7. Every turn writes `agent.actions_log` and updates `care_agents.last_tick_at`.

## Acceptance
- pytest with fake clock and fake LLM: a patient message arriving after a due event is still processed first; a 22:00 message is deferred to 08:00; over-cap sends nothing; non-AUTO state sends nothing.
- Tick over 100 fake patients calls the LLM no more times than patients that genuinely need drafting (assert via counting mock).
- ruff, pyright pass.

## Out of scope
- No `handoff` skill or routing (M2b, M2c). Where "answer or hand off" is needed, call `Protocol HandoffDecider` returning `answer`.
- Never call the Zalo client directly; go through C1/C2 `ChannelSend`.

## Report
Use `_REPORT-TEMPLATE.md`. List Protocols you created and measured turns/second on the test machine.
