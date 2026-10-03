# U3 — Patient 360 with the five tabs (overview, consult, plan, session, photos)

## Goal
Make `/patients/[id]` a full Patient 360 like the old web: consultation notes, treatment plan, treatment session
recording with consent and aftercare, and photos with consent — on real actions.

## Read first
1. `PLAN-AI01-U.md` §2 (principle 6 on photos), §3 row patients.
2. `prototype/shared/patient.js`, `clinic.js` (patient tabs), `data.js` (patient/session/event shape),
   `docs/06_CLINIC_WORKFLOW.md`, `docs/07_DOMAIN_MODEL.md`, `ARCH-PB01` data model (EpisodeOfCare, TreatmentPlan,
   TreatmentSession, ClinicalImageSet, Consent).
3. Existing actions `patient_360.py`, `consents.py`, `patients.py`; care timeline in `care/`.

## Ingredients
- Migration `u3_0010_sessions_plans_media.py`: `clinic.treatment_plan`, `clinic.treatment_session` (date, type,
  protocol id, region, note, next, aftercare, consent ref, reviewed, by), `clinic.media` (patient, session, stage
  before/after, path, mime, size, consent ref, uploaded_by).
- Actions: `plans.*`, `sessions.create/complete/review`, `media.upload_intent/confirm/list` (signed path on the
  configured storage, size and MIME checks, consent required), `consult.notes.*`.
- Pages: tabs on `/patients/[id]`: overview (existing + summary), consult, plan, session (form identical in fields to
  the old `session-*` inputs), photos (grid by stage, consent badge, upload).
- Agent: expose read-only `patient.get_care_context` enrichment (sessions/plan) through the existing agent tools path.

## Steps
1. Model and migration; `session.complete` emits the CRM event B2 uses for D+1/3/7 (verify with existing tests).
2. Actions with RBAC (doctor writes sessions; care staff per assignment; reception none) and audit.
3. Media: storage adapter behind a port (local volume now); never process images; thumbnails only if the storage can.
4. Pages and tests; mobile: tabs become a segmented control, photo grid 2 columns.
5. Inventory rows + smoke tests.

## Acceptance
- BE tests: session completion triggers CRM milestones; media upload refused without consent; RBAC denials; audit.
- FE: five tabs at 5 viewports, no overflow; inventory green; vitest ≥ baseline.
- No code path analyses image content.

## Out of scope
- Before/after collage, any image AI. Prescriptions/orders (U5).

## Report
Use `_REPORT-TEMPLATE.md`.
