# Package U recipes — UI parity with the old Pema web + port of missing screens

One file = one step. Template: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report.
A subagent takes **one file** and returns a report using `_REPORT-TEMPLATE.md`.
Source of truth: `pema-agent/docs/PLAN-AI01-U.md`; the plan wins over a recipe.

## Order

```
01-U0-design-foundation ─► 02-U1-restyle-inventory ─┬─► 03-U2-dashboard-schedule ──┐
                                                    ├─► 04-U3-patient360 ─────────┤
                                                    ├─► 05-U4-studio-resources-services ─► 06-U5-cashier-orders ─► 07-U6-finance ─┤
                                                    └─► 08-U7-guide-ask-crm ──────┴─► 09-U8-parity-audit ─┬─► 10-U9-patient-parity-fixes ──┐
                                                                                                          ├─► 11-U10-reception-room-views ─┤
                                                                                                          ├─► 12-U11-accountant-role-finance┤
                                                                                                          └─► 13-U12-housekeeping ──────────┘
```
U9–U12 (round 2, owner-approved 2026-10-05) may run in parallel worktrees; the director merges them one at a time
(same reasons as U2/U3/U4/U7: shared `nav.tsx`, `FEATURE-INVENTORY.md`, `openapi.json`/`schema.d.ts`).

## Locations

```
pema-agent/frontend/src/ui/                 tokens.css, tokens.json, kit components (U0; dark-mode contrast fix U12)
pema-agent/frontend/src/app/(admin)/        routes (existing + new)
pema-agent/frontend/visual-ref/{old,new}/   reference and current screenshots (git-ignored except README; regen U12)
pema-agent/frontend/scripts/visual-check.ts Playwright harness (U0)
pema-agent/frontend/FEATURE-INVENTORY.md    frozen feature list (U1)
pema-agent/backend/apps/api/pema/clinic/actions/   new actions per step
pema-agent/backend/apps/api/pema/clinic/finance/   U6, U11
pema-agent/backend/apps/api/alembic/versions/u<step>_*.py
pema-agent/backend/apps/api/tests/clinic/   BE tests per step
pema-agent/docs/PARITY-AI01-U.md            U8 writes it; U9/U10 update their own rows (U12 only)
docs/ARCH-PB01.md                           U11 only: role → permission table (not the read-only narrative sections)
design-specs/README.md · .claude/skills/pema-web-design/{SKILL.md,scripts/*.cjs} · design-specs/web/snapshot.json · design-system/colors.md
                                             U12 only: wording, tooling baseline and contrast-table fixes
```

## Reference material (read-only)

- Visual: `prototype/clinic-web/index.html`, `prototype/shared/design.css`, `styles.css`, `workspace-layout.css`,
  `.agents/skills/design-system/references/*.md`, `.agents/skills/brand/`, `docs/23_PEMA_DESIGN_SKILL.md`,
  `design-specs/README.md` + `design-specs/screens/*.md`.
- Behaviour: `prototype/shared/*.js`, `prototype/finance/*`, `prototype/finance_server.py`, `finance_test.py`,
  `docs/06_CLINIC_WORKFLOW.md`, `19_OPERATIONS_DEMO.md`, `20_CATALOG_ORDERS.md`, `20_CRM01_PATIENT_LIFECYCLE.md`,
  `24_FINANCE_AND_PROCEDURE_FEES.md`, `AGENT.md` (PB02 finance rules).
- Run the old web for screenshots: `python -m http.server 4173 --bind 127.0.0.1 --directory prototype`
  (`prototype/review-desktop.cjs` with `PEMA_EVIDENCE_DIR=<path under pema-agent>` captures 11 screens + 5 tabs).

## Common rules

- Only create/modify under `pema-agent/`, **plus** the extra paths named above for U11 and U12 (the usual rule for
  any package: write to the paths your own step's "Locations" line names, nothing else outside `pema-agent/`). Old
  code (`prototype/`) is read-only; never import, copy-paste or iframe it.
- Keep every existing feature: run `FEATURE-INVENTORY.md` checks (U1+) and the full vitest suite before reporting.
- New screens: action in `pema/clinic/actions` (RBAC + audit) → thin router → OpenAPI → regenerate FE types → page.
- Single-tenant: no RLS; `clinic_id` is the installation id (`CONTRACTS-AI01.md` §10.8). Migrations prefix `u<step>_`.
- Viewports to check: 1920×1020 (primary), 1440×900, 1280×720, 1024×768, 390×844. No horizontal overflow.
- Vietnamese UI copy, same labels as the old web where the feature is the same.
- Synthetic data only. No AI attribution in commits. Report ≤ 30 lines with real test results.
