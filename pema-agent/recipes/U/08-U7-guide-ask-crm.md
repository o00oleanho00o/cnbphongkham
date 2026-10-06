# U7 — Guide (KB-backed), "Hỏi Pema" entry, CRM01 leftovers

## Goal
Give the sidebar its old `ask` and `guide` entries with real content, and port whatever CRM01/operations screens are
not yet covered by Today, Patients, Inbox and Review.

## Read first
1. `PLAN-AI01-U.md` §3 rows ask/guide and CRM01.
2. `prototype/shared/guide.js`, `guide.css`, `crm-ui.js`, `crm-data.js`, `docs/20_CRM01_PATIENT_LIFECYCLE.md`,
   `docs/19_OPERATIONS_DEMO.md`; `design-specs/screens/` ids for guide/CRM.
3. Existing `/admin/kb`, staff agent chat entry point, `crm.py` router, package M supervision screens.

## Ingredients
- `/guide`: articles from the KB (`kb_search`/list with a `guide` tag), topics as the old `guide/topics` did; read-only
  for staff, editable through `/admin/kb`.
- `/ask`: the existing staff assistant chat embedded under the old label "Hỏi Pema" (no new agent, no new tools).
- `/crm`: segments (new, returning, treating, dormant, reactivated), rules list (read-only view of `crm_rules`),
  activities log with outcomes and channels exactly as `crm-ui.js` shows; opt-out toggle with audit.

## Steps
1. Compare `crm-ui.js`/`operations-ui.js` features against the inventory; port only what is missing.
2. Guide: tag-based listing + article page; seed 3 synthetic articles.
3. Ask: route + layout only; reuse existing components.
4. CRM leftovers with actions already present (`crm_tasks.py`, templates) — add actions only if truly missing.
5. Inventory rows + smoke tests.

## Acceptance
- Sidebar has all 11 old entries working; inventory green; vitest ≥ baseline; 5 viewports clean.

## Out of scope
- New agent behaviour. Marketing campaigns.

## Report
Use `_REPORT-TEMPLATE.md`; list CRM01 items you judged already covered and where.
