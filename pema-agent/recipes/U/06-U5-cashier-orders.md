# U5 — Cashier: quick orders, prescriptions, product catalog, A5 order review/print

## Goal
Port the old cashier flow: create a quick order from the 115-item product catalog (or from Patient 360 as a draft),
doctor approval, A5 order review and print, with the catalog served by the BE.

## Read first
1. `PLAN-AI01-U.md` §3 row cashier.
2. `docs/20_CATALOG_ORDERS.md`, `prototype/shared/order-data.js` (saveOrder, approveOrder, orderPrintData, version
   rules), `order-ui.js`, `order-review.js`, `order-review.css` (@page A5), `product-catalog.json`,
   `prototype/import-product-catalog.py` (Excel → JSON, product id = Excel code, SHA-256 provenance).
3. `AGENT.md`: catalog is the user's real data (not synthetic); "never infer a prescription was dispensed because it
   was approved"; doctor approves orders.

## Ingredients
- Migration `u5_0010_orders_catalog.py`: `clinic.product` (code as id, name, unit, source type, route, price,
  catalog hash), `clinic.order` (patient, items[], status draft/approved, version, reviewedBy/At, invoice link),
  `clinic.order_item`.
- Catalog loader: read `prototype/shared/product-catalog.json` **at import time only** via a CLI
  (`pema catalog import <json>`) that stores hash/count; no runtime dependency on the prototype path.
- Actions: `orders.create_draft/update/approve/print_data`, `catalog.list/search`; RBAC: cashier/reception create,
  doctor approve; approved orders immutable (edit = new version, only if no payment).
- Pages: `/cashier` (quick order), `/orders/[id]` (review), `/orders/[id]/print` (A5, natural flow, draft watermark
  when not approved), entry from `/patients/[id]` plan tab.

## Steps
1. Reproduce the prototype rules in BE tests first (version must match, no edit after payment, approved immutable).
2. Catalog import CLI + tests on the real JSON (hash and count asserted).
3. Actions, routers, OpenAPI, FE types; pages with the kit; print stylesheet.
4. Mobile shows approved orders only, grouped PRESCRIPTION/CONSULTATION (as the old Patient Mobile did) — this is
   the staff view; patient-facing exposure is NOT part of this step.
5. Inventory rows + smoke tests.

## Acceptance
- BE tests green incl. rule parity; catalog import idempotent.
- FE: pages at 5 viewports; print preview A5 verified by screenshot; inventory green; vitest ≥ baseline.

## Out of scope
- Payments/invoices (U6). Dispensing/stock.

## Report
Use `_REPORT-TEMPLATE.md`.
