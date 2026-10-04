---
name: pema-web-design
description: Design of the old Pema Clinic Web (prototype/clinic-web) as a frozen screen inventory, screenshots, screen specs and a web canvas. Stub from step W0; the final text is written in W4. Use the scripts only as the package W recipes say.
---

# pema-web-design (stub)

Created in package W step W0. See `pema-agent/docs/PLAN-AI01-W.md`; the final text of this skill is written in W4.

Today it holds:

- `scripts/lib/pw.cjs` loads Playwright (`PLAYWRIGHT_MODULE`, then the frontend `node_modules`, then the npx cache).
- `scripts/lib/old-web.cjs` opens one inventory entry from a fresh page (`open`), fixes clock and fonts (`freeze`) and
  closes dialogs (`closeAll`).
- `scripts/lib/catalog.cjs` is the hand-kept list of screens, with ids that never change.
- `scripts/web-inventory.cjs` walks the old web, checks the catalog against what the UI offers, and writes
  `design-specs/web/inventory.json` (`--check` fails on any difference).

The old web (`prototype/`) is read-only. Serve it with
`python -m http.server 4173 --bind 127.0.0.1 --directory prototype` and the finance API with
`python prototype/finance_server.py --port 4174 --db <temp>/finance.sqlite3`.
