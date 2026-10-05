# Design implementation and handoff

## Sources in the repository

| Work | Where to check |
|---|---|
| Decisions/acceptance/module/runtime | `docs/SCOPE-PB01.md` → `SPEC-PB01.md` → `MODULEMAP-PB01.md` → `ARCH-PB01.md` |
| Web style/assets | `prototype/shared/design.css`, `workspace-layout.css`, `styles.css`, module CSS, and `assets/` |
| Web behavior | `prototype/shared/clinic.js`, `patient.js`, `operations-*`, `order-*`, `data.js` |
| App theme/navigation/screens | `pema-kmp/core/ui` (theme, widgets), `pema-kmp/composeApp/.../App.kt` (navigation), `pema-kmp/feature/*` (screens) |
| App state | `pema-kmp/shared` |
| App build + limits | `pema-kmp/README.md`, `pema-kmp/CONVENTIONS.md`, screen specs `design-specs/screens/<ID>.md` |

Read the actual CSS load order before overriding; avoid appending overlapping rules only to win specificity. Current font/logo assets are enough to start; image-generation services or paid tools are not required.

## Data and mocks

Use 46 synthetic patients (36 base + 10 CSKH groups) and the user-supplied catalog; do not enter real records. Fixtures need enough states and long names/notes to expose layout bugs. Do not fake synchronized metrics/history when that data does not exist.

Catalog: `data/danhsach.xlsx` → `prototype/import-product-catalog.py` → `prototype/shared/product-catalog.json` → copy bundle `pema-kmp/shared/src/commonMain/composeResources/files/products.json`. After catalog changes, check importer `--check`, hashes of the two JSON files, counts/types against the workbook, and affected acceptance. Do not hardcode 115 as a permanent invariant after the workbook has validly changed.

## Choose checks by change

Web server: from `prototype`, `python -m http.server 4173 --bind 127.0.0.1`; check for an existing server before running a duplicate. Use the same origin/profile for both web apps. Read script dependencies when running on a new machine.

| Change | Suitable check from repo root |
|---|---|
| Desktop layout | `node prototype/review-desktop.cjs`; inspect screenshots and overflow |
| Patient mobile UI | `node prototype/review-ui.cjs`, `node prototype/patient-smoke.cjs` |
| Linked business behavior | `node prototype/check-linked.cjs`, `node prototype/data-audit.cjs` |
| Schedule/services/cashier | `node prototype/operations-test.cjs` |
| Catalog/orders/web print | `python prototype/import-product-catalog.py --check`, `node prototype/product-catalog-test.cjs`, `node prototype/order-test.cjs`; if print changes, add `python prototype/order-pdf-test.py` |
| Web smoke | `node prototype/smoke-final.cjs` when the change affects navigation/shared behavior |
| App (KMP) | In `pema-kmp`: `.\gradlew.bat jvmTest :androidApp:assembleDebug`; inspect `build/shots/<ID>-vs.png` and the affected screens on a device |
| Docs/skill only | Links/files exist, source is cross-checked, environment frontmatter validator if available, `git diff --check` |

Do not run every suite for every small change. Do not use web PDF tests to confirm native print, and do not use store tests for orders/receipts to claim all data isolation. Read the current test source before reporting new coverage.

## Verifiable handoff

Report briefly: what changed and why, affected screens/flows, checks actually run, screenshot/artifact, and remaining limits. State clearly whether it is analysis, an approval template, or complete implementation. Check marks are only for work done; liking the design does not certify auth/payment/clinical safety.

Per project rules, when scope/behavior changes, update 0→1→2→3, then README/business/UI docs, and append SECTION_PROGRESS. When the design convention itself changes, update the corresponding skill. Keep test history on the correct date and channel.

If the user requests commit/push: review the diff, stage only task files clearly (including related docs), exclude unrelated logs/cache/artifacts, inspect staged diff, and push the selected branch; verify the remote SHA. Do not create a commit/push just because this skill has this instruction.


## PB02 finance exception

The clinic-owner overview, revenue/reconciliation, and procedure fees newly use the shared web/app API/SQLite. Keep revenue, cash received, debt, and doctor fee distinct; rate snapshots, closing periods, role-based projections, and foreground notifications. Read `docs/24_FINANCE_AND_PROCEDURE_FEES.md` and the PB02 set before editing; the PB01 memory-only finance limit does not apply to the new module. Run `python prototype/finance_test.py` when changing formulas/ledger.


Visible web changes (screen, tab, modal, dialog, field, button, status, flow, binding sentence, CSS token) must include an item in "Pending" of `.claude/skills/pema-web-to-canvas/web-changes.md` in the same commit, so the claude.ai/design canvas is updated in the right place without re-reviewing every screen. Details and the entry template are in `AGENT.md` › "Logging web changes for the design canvas".


Mobile CRM02: use `docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md` as the current-state source. Finance lives inside the Clinic shell; native selects the role before the task, and must not cram CSKH/cashier/clinical into one shared home. Care prioritizes one next step; internal work and handoffs must not become patient messages.
