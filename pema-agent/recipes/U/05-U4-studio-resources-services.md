# U4 — Studio, Resources (doctors, rooms), Services (catalog, prices, protocols)

## Goal
Port the three configuration/operations screens the old web had under `studio`, `resources`, `services`, with real
actions, so Schedule (U2), Cashier (U5) and Finance (U6) can reference services and resources.

## Read first
1. `PLAN-AI01-U.md` §3 row studio/resources/services.
2. `prototype/shared/clinic.js` (what each of the three screens renders), `operations-data.js` (resources),
   `prototype/finance_server.py` `seed()` (services with price, rate, basis, version), `docs/19_OPERATIONS_DEMO.md`,
   `docs/24_FINANCE_AND_PROCEDURE_FEES.md` (rate snapshots), `design-specs/screens/` ids for these screens.
3. `AGENT.md` PB02 rules: keep rate snapshots; never auto-assign the performing doctor from the record owner.

## Ingredients
- Migration `u4_0010_services_resources.py`: `clinic.service` (name, price, rate, basis, protocol id, version,
  active), `clinic.resource` (doctor/room, capacity, schedule), `clinic.protocol` (milestones used by B2 rules, e.g.
  laser-co2 → D+1/3/7, D+30 review).
- Actions: `services.*` (versioned; price/rate change creates a new version), `resources.*`, `protocols.*`;
  managers only (matrix "Quản trị catalog/role").
- Pages: `/services` (table, version history), `/resources` (doctors, rooms, shifts — link to `clinic.staff_profiles`
  from package M instead of duplicating), `/studio` (implement exactly what the prototype shows; if the prototype's
  "studio" is a room/procedure board, build that; write the interpretation in the report).

## Steps
1. Derive each screen's behaviour from the prototype; do not invent features.
2. Models/migration, actions with audit, routers, OpenAPI, FE types.
3. Pages with the kit (four-column layout ≥1600 for doctors/services as the old README states).
4. Wire protocols to B2 rule config so milestone days are data, with a test that the existing laser-co2 behaviour is
   unchanged.
5. Inventory rows + smoke tests.

## Acceptance
- BE tests: service versioning, protocol → milestone mapping, RBAC; audit rows.
- FE: three pages at 5 viewports; inventory green; vitest ≥ baseline.

## Out of scope
- Orders/prices on invoices (U5), commission maths (U6).

## Report
Use `_REPORT-TEMPLATE.md`; state what "studio" was interpreted as.
