# M2c — Staff routing, SLA, 24/7 on-call, reminder pause and reconcile

## Goal
After the agent decides to hand off, it **picks the right staff member and moves on** when declined or past SLA, and the chain **always ends at the clinic's 24/7 on-call Zalo number**. While staff handle the patient, **no scheduled reminders are sent**; on release, reconcile.

## Read first
1. `PLAN-AI01-M.md` §7, §8, §15 (decisions 2, 5).
2. M2b `control.py` (`accept/decline`), M1 tables `staff_profiles`, `patient_ownership`, `on_call_contacts`, `handoff_requests`.
3. S: scheduler, "late reminder, original schedule …" label, proactive cap.

## Ingredients
- `pema/care/routing.py`: `build_candidates(request) -> list[Candidate]`, `advance(request)`.
- `pema/care/oncall.py`: `current_on_call(clinic_id, now)`.
- `pema/care/reminders.py`: `pause_for(patient)`, `reconcile_on_release(patient, now)`.
- Staff notification via `Protocol StaffNotify` (push + in-app); if E/B1 lack it → create the Protocol.

## Steps
1. `build_candidates` (deterministic, **no LLM**): filter by `required_skill` and `urgency` (D5 → doctors only; D4 → treating doctor or doctor on shift) → prefer people in `patient_ownership` → then on shift, with capacity, matching skills → max 5 → **last element is always the on-call number** from `oncall.current_on_call`.
2. `advance`: notify `candidates[current_idx]` with the summary; wait for `accept` / `decline(reason, suggest_user_id)` / SLA expiry. `decline` with `suggest_user_id` → insert that person next. SLA expiry → `current_idx += 1`. Reaching on-call → `outcome=exhausted_to_oncall`, notify on-call.
3. SLA defaults (`clinic.settings`): `urgent/critical` 5 min, `normal` 30 min, out of hours: start of next shift. Schedule SLA checks through S, never `sleep`.
4. Out of hours with D5: besides routing to on-call, send the patient **one template message** with the on-call number + generic emergency guidance (doctor-approved template; no LLM text). D3–D4 out of hours: holding message with a response-time estimate.
5. `oncall.current_on_call` reads the DB **on every call** (cache ≤ 60 s) so a number change takes effect immediately. Log every use as `actions_log` kind `oncall_used`.
6. `reminders.pause_for`: on entering `HANDOFF_ROUTING`/`STAFF`, all due reminders for this patient → `paused`, shown to the owning staff with the prepared text (staff may send manually). **Never** auto-converted into a staff task.
7. `reminders.reconcile_on_release`: reminders past their meaning (per-type rules, e.g. D+1 when D+3 has passed) → drop and log; still useful → send at the nearest slot with S's "late" label. A patient reply during STAFF goes to staff; the agent does not act on it.
8. Store decline reasons on `handoff_requests`; provide a simple export for later skill-profile updates (do not modify `staff_profiles` automatically).

## Acceptance
- pytest with fake clock: chain always ends with on-call; 2 declines + 1 SLA expiry → reaches on-call with `outcome=exhausted_to_oncall`; `suggest_user_id` is placed next; D5 out of hours → patient receives exactly 1 template with the on-call number, LLM mock not called.
- In STAFF, scheduler fires D+3 → nothing sent, a `paused` record exists; release after 1 day → D+3 sent with late label; release after 10 days → D+1/D+3 dropped and logged.
- Changing the on-call number in DB → next turn uses the new number.
- ruff, pyright pass.

## Out of scope
- No LLM in staff selection. No automatic edits to skill profiles. No reminder of any kind sent while in STAFF.

## Report
Use `_REPORT-TEMPLATE.md`. State SLA defaults and the "past its meaning" rules you set temporarily.
