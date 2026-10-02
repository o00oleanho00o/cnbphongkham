# M1 — Schema, migration, auto-pairing

## Goal
Create all package-M tables in `agent.*` and `clinic.*`, plus the **1-to-1 pairing patient ↔ care_agent** created automatically when a patient record is created.

## Read first
1. `pema-agent/docs/PLAN-AI01-M.md` §2, §10.
2. `pema-agent/docs/CONTRACTS-AI01.md` and existing migrations in `apps/api/alembic/versions/` (naming, RLS by `clinic_id`).
3. `docs/ARCH-PB01.md` "Data model tối thiểu" (tenantId, stable id, timestamps, actor, version).

## Ingredients
- SQLAlchemy async models in `pema/care/models.py`.
- Alembic migration `m_0001_care_tables.py`.
- `pema/care/pairing.py`: `ensure_care_agent(patient_id) -> CareAgent`, idempotent.

## Steps
1. Models for (names/columns exactly as PLAN §10):
   - `agent.care_agents` (unique `patient_id`; `autonomy_levels` jsonb; `autonomy_override {level, until}`; `trust_scores` jsonb; `preferences` jsonb; `last_tick_at`; `paused`).
   - `agent.care_memory` (`source` enum `patient|staff|doctor_edit`; `valid_until`; **no column may hold clinical record data**).
   - `agent.conversation_control` (`state` enum `AUTO|HANDOFF_ROUTING|STAFF`; `staff_owner`; `release_note`; `auto_release_after` nullable, default null).
   - `agent.handoff_requests` (`candidates` jsonb list; `current_idx`; `accepted_by`; `outcome` enum `accepted|exhausted_to_oncall|cancelled`).
   - `agent.tasks`, `agent.actions_log`, `agent.skills`.
   - `clinic.staff_profiles`, `clinic.patient_ownership`, `clinic.on_call_contacts` (with `is_fixture` bool for test data).
2. Every table has `clinic_id`, `created_at/updated_at`, `version`; enable RLS by `clinic_id` like existing tables.
3. Grants: worker role may read `clinic.staff_profiles`, `clinic.patient_ownership`, `clinic.on_call_contacts`; write `agent.*`; nothing else in `clinic.*`.
4. `pairing.py`: hook after B1's create-patient action. If no hook exists → `Protocol PatientCreatedHook` in `ports.py`, invoked from tests.
5. Dev seed: 3 fake staff with different skills, 1 fake on-call number `is_fixture=True`, 2 fake patients.

## Acceptance
- `alembic upgrade head` on a clean Postgres then `downgrade -1` both succeed.
- pytest: creating a patient yields exactly one `care_agent`; calling again creates none; RLS: another `clinic_id` cannot read; worker cannot `INSERT` into `clinic.*`.
- ruff and pyright strict pass.

## Out of scope
- No turn logic, routing or autonomy (later steps).
- No changes to other packages' tables; a new column on `clinic.patients` → open item.

## Report
Use `_REPORT-TEMPLATE.md`. Name the migration and any Protocol you created.
