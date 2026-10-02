# M3 — Autonomy levels L0–L2, trust scores, time-boxed override, kill switches

## Goal
Each care agent has an **autonomy level per action type**, promoted by approved-unchanged drafts, demoted by serious edits or by a staff time-boxed override; three kill switches.

## Read first
1. `PLAN-AI01-M.md` §4, §15 (decisions 1, 3).
2. M1 columns `autonomy_levels`, `autonomy_override`, `trust_scores`, `paused`. B1 `review_items` (approval state, edit diff).
3. P profiles: `patient_channel` is a hard ceiling; M3 must never exceed it.

## Ingredients
- `pema/care/autonomy.py`: `effective_level(care_agent, action_type, now) -> L0|L1|L2`, `may_auto_send(decision, level) -> bool`.
- `pema/care/trust.py`: score updates from review outcomes.
- Config `clinic.settings.autonomy` {`N_to_L2` per type, `templates_L1` list of doctor-approved template ids, `serious_edit_rule`}; defaults flagged `pending_doctor_approval=True`.

## Steps
1. `action_type` catalogue: `reminder_template`, `care_guide_template`, `appointment_confirm`, `faq_kb_answer`, `symptom_reply`, `medical_judgement`, `birthday_greeting`.
2. `effective_level`: if `autonomy_override.until > now` → use `override.level`; expired → clear override, fall back to `autonomy_levels[action_type]`. `paused=True` or any kill switch on → L0.
3. Hard, non-configurable rules: `medical_judgement` and any D4/D5 → always human; `birthday_greeting` → never auto-sent (clinic rule); `marketingOptOut` blocks all marketing.
4. `may_auto_send`: L1 only for actions **from a template in `templates_L1`** or `appointment_confirm` of a slot the patient picked; L2 adds `faq_kb_answer` when ≥1 KB citation, `confidence ≥ threshold`, no red flag, depth ≤ D2 (D3 only when the doctor enables it per type).
5. `trust.py`: on B1 review events: approved **unchanged** → +1 for `(care_agent, action_type)`; reaching `N_to_L2` → promote that type to L2, log. Minor edit → no change. Serious edit (per `serious_edit_rule`: changed clinical meaning, removed a warning, added a drug) → whole care agent to L0, log, alert manager.
6. Staff API: `set_override(care_agent, level, until, note)` (used by M2b `release_to_auto`), `pause/resume` per patient. Manager API: kill switch per specialist agent and system-wide (`clinic.settings.kill_switch`).
7. Every level change → `actions_log` kind `autonomy_change` with `initiator`.

## Acceptance
- pytest: new patient → L0 for all types; enabling a template → L1 can send that template but not another; 10 approved-unchanged (N=10) → L2 for `faq_kb_answer`; one serious edit → L0 for everything; override L0 for 7 days → back to previous level after 7 days; system kill switch → nothing auto-sends; `medical_judgement` is never `may_auto_send=True` even if config tries.
- ruff, pyright pass.

## Out of scope
- Do not decide final N, confidence threshold or serious-edit rule (doctor decides); set temporary values flagged for approval.
- Do not change how B1 stores diffs; if missing → `Protocol ReviewOutcome` and an open item.

## Report
Use `_REPORT-TEMPLATE.md`. List temporary N and thresholds.
