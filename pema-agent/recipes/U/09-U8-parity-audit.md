# U8 — Parity audit, evidence, docs, migration merge head

## Goal
Prove the package: every old screen exists and looks right, no current feature was lost, migrations have one head,
docs match reality.

## Read first
1. `PLAN-AI01-U.md` §5.
2. All U-step reports; `FEATURE-INVENTORY.md`; `visual-ref/old/`.
3. `pema-agent/docs/SCOPE-AI01.md`, `SPEC-AI01.md`, `MODULEMAP-AI01.md`, `ARCH-AI01.md`, `design-specs/README.md`,
   root `SECTION_PROGRESS.md`, `AGENT.md` doc flow.

## Steps
1. Alembic: if several `u*_0010_*` heads exist, add `u8_0011_merge_heads.py`; `upgrade head` + `downgrade` on a clean
   Postgres.
2. Run everything: BE pytest/ruff/pyright/import-linter; FE vitest/lint/tsc/build; `pnpm inventory`; `pnpm visual`.
3. Visual parity table: for each old `data-nav` screen and Patient 360 tab, old vs new screenshot paths at 1920×1020
   and 390×844, verdict (same structure / acceptable deviation / fix needed). Fix small deviations; log the rest.
4. Security pass on new actions: RBAC denials tested, audit on every mutation, media MIME/size limits, CSV injection
   guard, no PII in logs.
5. Docs: update SCOPE/SPEC/MODULEMAP/ARCH-AI01 (new modules, routes, tables), `pema-agent/README.md` (how to run the
   unified app), `design-specs` deviations note, one checkpoint line in root `SECTION_PROGRESS.md`. Record which
   old files are now superseded but kept (`prototype/*`, `finance_server.py`).
6. Write `pema-agent/docs/PARITY-AI01-U.md` with the table from step 3 and the final numbers.

## Acceptance
- Single alembic head; all suites green with numbers in the report; inventory signed; parity table complete.

## Out of scope
- Deleting old prototype code (owner decision). KMP changes.

## Report
Use `_REPORT-TEMPLATE.md` plus a link to `PARITY-AI01-U.md`.
