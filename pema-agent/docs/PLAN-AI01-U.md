# PLAN-AI01-U — Package U: UI parity with the old Pema web + port of the missing screens

Status: planned 2026-10-03, nothing built. Branch: `feat/ui-parity` (created 2026-10-03 from `feat/single-tenant` at `bc094c8`; merge back when the package is accepted). Recipes: `pema-agent/recipes/U/`.
Owner decision (2026-10-03): (1) port the missing old Clinic Web features into the existing Next.js FE, (2) rewrite in
Next.js, never wire the old localStorage web to the API, (3) restyle the whole existing FE to look like the old Pema web
**without losing any current feature** (CSKH, agent admin, care supervision). Reason: the same design will be ported to
the KMP app later; one design system and one set of screen specs keep that cheap.

## 1. Goal

One staff app in `pema-agent/frontend` that looks like `prototype/clinic-web` (layout, navigation, tokens, components)
and contains **everything** the old Clinic Web had plus everything the new FE already has.

## 2. Principles

1. **Old web is the visual and behavioural reference, not the code base.** Read `prototype/shared/*.js`, `design.css`,
   `workspace-layout.css`, `design-specs/screens/*.md`, `docs/06,19,20,20_CRM01,24`; write Next.js + BE actions.
   Never import or iframe the prototype.
2. **No feature loss, proven by inventory.** U1 freezes a `FEATURE-INVENTORY.md` (every route, every capability, its
   test id). Every later step must keep it green; U8 signs it.
3. **Actions first, routes thin.** Every new screen is backed by `pema/clinic/actions/*` (RBAC, audit) and a thin
   router; the agent gets the same actions as tools where it makes sense.
4. **One token source for web and app.** Tokens live in `frontend/src/ui/tokens.css` (Tailwind `@theme`) and are
   exported to `frontend/src/ui/tokens.json`; KMP consumes the JSON later. Screen specs keep the `design-specs` ids.
5. Single-tenant rules apply (no RLS, `clinic_id` = installation id). Synthetic data only. No AI attribution in git.
6. Photos: upload/view with consent only. **No image analysis, no before/after automation** (still out of scope).

## 3. Old Clinic Web inventory → target

| Old nav (`data-nav`) | Old behaviour source | Target route(s) | BE gap |
|---|---|---|---|
| dashboard | `clinic.js` | `/dashboard` | KPI read model action |
| today | `clinic.js`, `crm-ui.js` | `/today` (exists; restyle) | — |
| schedule | `operations-ui.js`, `operations-data.js` | `/schedule` (day/week, reception statuses booked→confirmed→arrived→in_progress→completed, missed/cancelled) | check-in/status actions |
| patients + Patient 360 tabs overview/consult/plan/session/photos | `patient.js`, `clinic.js`, `data.js` | `/patients`, `/patients/[id]` with the 5 tabs | sessions, plans, photos/media+consent actions |
| followups | `crm-ui.js`, `data.js` followups | `/inbox` + `/review` (exist; restyle) | — |
| studio / resources / services | `clinic.js`, finance seed (services, prices) | `/studio`, `/resources` (doctors, rooms), `/services` (catalog, prices, protocols) | services/resources actions |
| cashier (quick order, prescriptions, A5 order review, product catalog 115 items) | `order-data.js`, `order-ui.js`, `order-review.js`, `product-catalog.json`, `import-product-catalog.py`, `docs/20_CATALOG_ORDERS.md` | `/cashier`, `/orders/[id]`, `/orders/[id]/print` | orders, catalog serving (keep Excel code as product id, SHA-256 provenance) |
| finance (PB02) | `prototype/finance/*`, `finance_server.py`, `care-finance.js`, `docs/24` | `/finance/*` (owner, accountant, doctor projections; approve/close month; payment inbox) | port finance rules into `pema/clinic/finance` with `finance_test.py` equivalence |
| ask / guide | `guide.js` | "Hỏi Pema" = existing staff agent chat; "Hướng dẫn" = KB articles | — |
| CRM01 screens | `crm-ui.js`, `docs/20_CRM01` | merged into today/patients/inbox; leftovers in `/crm` | — |

Everything that exists today in the new FE (login, today, patients, inbox, review, templates, care/*, admin/*) stays
and is restyled only.

## 4. Steps (one recipe each, `recipes/U/`)

| Step | Scope | Needs |
|---|---|---|
| **U0** Design foundation | tokens.css/json, UI kit (`src/ui/`), AppShell with the old sidebar order + new groups, old-web reference screenshots, Playwright visual harness at 5 viewports | — |
| **U1** Restyle + inventory freeze | migrate every existing route to the kit, `FEATURE-INVENTORY.md`, route smoke tests, vitest count must not drop | U0 |
| **U2** Dashboard, Schedule | `/dashboard`, `/schedule`; KPI + reception-status actions | U1 |
| **U3** Patient 360 full | tabs consult/plan/session/photos; sessions, plans, media+consent actions | U1 |
| **U4** Studio, Resources, Services | `/studio`, `/resources`, `/services`; actions | U1 |
| **U5** Cashier & orders | `/cashier`, `/orders/*`, catalog, A5 print; orders/catalog actions | U1, U4 (services) |
| **U6** Finance PB02 | `pema/clinic/finance` + `/finance/*`; equivalence with `finance_test.py` | U1, U5 (invoices link) |
| **U7** Guide, Ask, CRM leftovers | KB-backed guide, "Hỏi Pema" entry, `/crm` leftovers | U1 |
| **U8** Parity audit | old-vs-new screenshots per screen, inventory signed, docs (SCOPE/SPEC/MODULEMAP/ARCH-AI01, SECTION_PROGRESS, design-specs deviations), alembic merge head | all |

Order: U0 → U1 → (U2 ‖ U3 ‖ U4 ‖ U7) → U5 → U6 → U8. Each step that adds migrations uses prefix `u<step>_` and branches
from the current head; U8 adds the merge revision (pattern `h_0008_merge_heads`).

## 5. Acceptance for the package

- Every old `data-nav` screen and Patient 360 tab exists in the new FE and is reachable from the sidebar.
- `FEATURE-INVENTORY.md` fully green; vitest count ≥ baseline (407 at `0639903`); eslint/tsc/prettier/`next build` clean.
- Visual harness: 5 viewports, no horizontal overflow, each screen's screenshot reviewed next to the old one
  (`pema-agent/frontend/visual-ref/{old,new}/`).
- BE: pytest/ruff/pyright/import-linter green; finance equivalence tests pass; all mutations audited.
- Tokens JSON exported and documented for KMP.

## 6. Owner / doctor inputs still needed

Which services/prices/protocols are real for seed (synthetic until then); whether cashiers may approve orders; finance
period-close policy owner; photo consent wording.
