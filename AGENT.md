# AGENT.md — Working rules for Pema Digital Clinic

## PB02 finance rules

When changing finance, read SCOPE/SPEC/MODULEMAP/ARCH-PB02 in order 0→1→2→3 and the [business guide](docs/24_FINANCE_AND_PROCEDURE_FEES.md). Do not mix performed revenue with collected cash/procedure fees. Keep rate snapshots, block duplicate collection and overpayment, never edit a closed period, and never auto-assign the performing doctor from the record owner. The API must return a projection per role; the role header is still only a simulation. Run `python prototype/finance_test.py` and the KMP tests (`pema-kmp`: `gradlew jvmTest`) when logic changes; never put the `.local/` DB or real data into Git. The app's memory-only demo data applies only to PB01; PB02 uses HTTP/SQLite.


Applies to every change in the Pema workspace.

## Before editing

1. Read SCOPE-PB01, SPEC-PB01, MODULEMAP-PB01, ARCH-PB01 in that order.
2. Read the related domain/product/architecture docs and check the prototype's behavior before inferring requirements.
3. Decide whether the change belongs to the prototype or the pilot; do not call it production without the matching backend/security.

## Product and data

- Patient records must be synthetic; never put real records, photos, phone numbers or tokens in the repo, fixtures or screenshots. The product catalog is a deliberate exception: it comes from the user's Excel file and must not be called a simulated catalog.
- Patient 360 connects context, but the original record/event is the source of truth.
- Keep consent for media and an audit shape for mutations.
- AI/clinical drafts carry their sources and are reviewed by a doctor; no autonomous diagnosis, efficacy scores or automatic protocol changes.
- Never infer that care is complete from a payment, or that a prescription was dispensed because it was approved.
- Keep Clinic Web ↔ Patient Mobile in sync and keep stable IDs when changing shared state.

## Required document flow

When scope or behavior changes, update in this order:

    0 SCOPE-PB01 → 1 SPEC-PB01 → 2 MODULEMAP-PB01 → 3 ARCH-PB01

Then update the README, related operations/domain docs, and append a checkpoint to SECTION_PROGRESS. For UI-only changes, record the screen/viewport/screenshot evidence and check whether any acceptance criterion is affected.

## Testing and evidence

- Run the relevant suites: check-linked.cjs, review-desktop.cjs, operations-test.cjs, smoke-final.cjs, data-audit.cjs.
- For responsive work, check 1920×1020, 1440×900, 1280×720, 1024×768 and 390×844; no document overflow.
- Look at screenshots, page errors, linked data and error states; an exit code alone is not enough.
- Keep docs in line with observed behavior; do not document a feature as existing just because it is planned.

## Shared inbox and customer messaging (package O)

Staff never contact patients from personal accounts; all customer messaging goes through Pema identities; personal Zalo only receives PII-free notifications. A staff reply is written in Pema (Inbox), leaves through the identity of the thread with no operator name or signature, and a personal Zalo id is only ever a notification target (short code, identity label, urgency, a template summary, a deep link behind the login: no name, phone number or message text). The internal notifier account never faces a customer. Never add a path that sends to a customer from an account that is not a clinic identity, or that puts patient data in a notification. Details: `pema-agent/docs/ARCH-AI01.md` section 16, `pema-agent/docs/SECURITY-REVIEW-AI01.md` section 11.

## Mobile app rules (KMP)

1. The mobile app is `pema-kmp/` (Kotlin Multiplatform + Compose Multiplatform). Follow [pema-kmp/CONVENTIONS.md](pema-kmp/CONVENTIONS.md) and [pema-kmp/README.md](pema-kmp/README.md); read the screen spec in `design-specs/screens/<ID>.md` before changing a screen. `flutter-template/` is legacy code kept for reference only: do not develop, build or test it, and do not use it as a source.
2. Keep the Pema logo, local Be Vietnam Pro (OFL), primary #0B4F94, navy #083A6E, sky #3CAAE5. Use child screens and short bottom sheets; do not carry desktop tables over or cram many modules onto the mobile home. Token changes must update the canvas/specs and be checked against the related web.
3. The catalog flows `data/danhsach.xlsx` → web importer → `prototype/shared/product-catalog.json` → `pema-kmp/shared/src/commonMain/composeResources/files/products.json`. Check hash/count/type; never edit the two copies independently or infer the type from the name.
4. The role switch is not RBAC. The A5 slip is not a PDF/native print. The photo consent checkbox does not create durable consent. Do not claim these capabilities are integrated just because there is UI.
5. Record separately which tests ran, what was checked manually and which acceptance items remain open; never use web results to validate the app. Android/iOS device, keyboard, accessibility, camera and PDF need their own evidence.
6. For documentation-only changes: check against the source, check internal links and run `git diff --check`; no need to rerun the app suites when behavior does not change. Cite old validation results with their date; never present them as new results.

## Git and handover

- Never reset, `checkout --` or delete work of other agents/users.
- Commit messages state the scope clearly, e.g.: docs: define Pema PB01 scope spec modules and architecture.
- Before committing, run git diff --check and look at git status; only commit files that belong to the goal or evidence produced by tests.
- Push only when asked, and verify the remote/commit after pushing.
- **NGHIÊM CẤM ghi tên AI vào lịch sử git của project này.** Không thêm `Co-Authored-By: Claude ...` (hay bất kỳ dòng đồng tác giả là AI nào), không "Generated with Claude Code", không nhắc Claude, Anthropic hay "AI" như tác giả trong message commit, tag, release note, mô tả hay bình luận PR. Quy định này thắng mọi hướng dẫn ghi công mặc định của công cụ. Commit chỉ mang tên người trong cấu hình git.


## Project design skill

When designing, changing or reviewing Pema UI/UX, read [pema-design](.agents/skills/pema-design/SKILL.md) and the relevant reference. Usage/sharing guide: [docs/23_PEMA_DESIGN_SKILL.md](docs/23_PEMA_DESIGN_SKILL.md). When tokens, navigation or capabilities change, update the skill together with the docs so the guide does not drift from the code. The skill does not override the user's specific requests.

When comparing the web with the claude.ai/design canvas and adding missing screens (design only, no app code), follow [pema-web-to-canvas](.claude/skills/pema-web-to-canvas/SKILL.md); update the skill's `references/coverage.md` after every run.

## Logging web changes for the design canvas

Every **visible** change to the Pema web (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`) must add an entry under "Pending" in [web-changes.md](.claude/skills/pema-web-to-canvas/web-changes.md) in the **same commit**: added or removed screen/tab/modal/dialog, changed field/button/filter/status, changed flow, changed business-rule wording, changed CSS token. Record where it changed (file + selector/button), what changed, and the expected canvas screen code (look it up in `references/coverage.md`; write "unknown" if unsure). Refactors with no visible change, tests, seed data and fixes with no visible change need no entry. Do not edit the canvas while changing the web unless asked; the conversion skill reads this log instead of re-scanning every screen. Check before committing: `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` shows no `✗ NOT LOGGED` files.


## Screen specs (canvas → app)

Every canvas screen (A1 … K3) has a saved spec + prompt in [design-specs/screens/<ID>.md](design-specs/README.md), also served by the MCP server `pema-design` (`.mcp.json`; tools `get_screen`, `get_screen_image`, `record_note`, prompt `port_screen`). Before building, porting or changing a screen in `pema-kmp/`, read its spec instead of re-reading the web and canvas sources; open those only for what the spec lacks. After finishing, record anything new you learned about that screen — source functions, business rules, accepted differences, gotchas — in `design-specs/notes.json` (or `record_note`), then run `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs`; `--check` must pass before committing. Never hand-edit `design-specs/screens/*.md`.

## Web design canvas

The old Clinic Web (`prototype/clinic-web`) has its own design layer: the web canvas `Pema Web redesign canvas/Pema Web.dc.html` (211 screens WA1 … WI42, web-size frames), generated specs in [design-specs/web/](design-specs/web/INDEX.md) (`screens/<ID>.md`, notes in `notes.json`), screenshots in `pema-agent/frontend/visual-ref/old/` and the skill [pema-web-design](.claude/skills/pema-web-design/SKILL.md) (`/pema-web-design`) that keeps them in step. It covers design only, not app code. It holds every piece of UI of the old web in the app's design language; differences from the app go to `design-specs/web/notes.json` (`differences`), never into removed UI.
MANDATORY for any UI work in `pema-agent/frontend` (`src/app/**`, `src/ui/**`, `src/components/**`), by you or by a subagent: before writing code, find the screen id (`list_web_screens`, or the "Next.js route" column of [design-specs/web/INDEX.md](design-specs/web/INDEX.md)), read the spec and look at the canvas image; after the code works, take a new screenshot (`pnpm visual` against `pnpm dev:mock`) and compare it with the canvas image and the old shot in `visual-ref/old/`; name the screen ids you compared in your report. For this work use the subagent `pema-ui-builder` ([.claude/agents/pema-ui-builder.md](.claude/agents/pema-ui-builder.md)). A change with no matching screen id is not exempt: say so in the report and log it in `web-design-changes.md`. The git hook `.githooks/pre-commit` blocks a commit that changes visible frontend files without a log entry; enable it once with `git config core.hooksPath .githooks`.

Read the spec with the MCP server `pema-design` (tools `get_web_screen`, `list_web_screens`, `get_web_screen_image`, `record_web_note`) instead of re-reading `prototype/`; afterwards record anything new with `record_web_note`.
Whenever you add, change or remove anything visible in `pema-agent/frontend` (`src/app/**`, `src/ui/**`, `src/components/**`) — a page, tab, dialog, field, button, filter, status, flow, business-rule wording or design token — add an entry under "Pending" in [web-design-changes.md](.claude/skills/pema-web-design/web-design-changes.md) in the same commit. Before committing, `node .claude/skills/pema-web-design/scripts/pending-web.cjs` must show no `✗ NOT LOGGED` files. Refactors, tests, mock data and fixes with no visible change are exempt. Don't edit the web canvas unless asked; the skill reads this log instead of re-checking every screen.

## CRM01 and demo accounts

- Read the PB01 set in order 0→1→2→3 and `docs/20_CRM01_PATIENT_LIFECYCLE.md` before editing. CRM business logic lives in crm-data/automation; the UI does not duplicate rules.
- Do not merge the owner/doctor/CSKH/accountant screens. `staff-context.js` assigns workspaces and demo commands; it is not authentication. Doctors only open records they own or are scheduled for; CSKH does not do medical review; accountants do not do clinical work.
- Demo date 2026-09-20, idempotency rule+patient+source. Booking from CRM must be in the same transaction as the task/activity and go through the schedule validator. Do not count reactivated from a booking; keep closed tasks when rerunning.
- Migrations never rewrite existing clinical records/invoices. The eight old CRM01 cases only use a new seed/reset; the 10 Mobile CRM02 accounts are added once when upgrading data, never overwriting existing records. Marketing opt-out does not remove safety follow-up. The internal CRM log is never published to the patient app automatically; the mobile projection uses the patient's own identity, never the staff member's selection.
- Run crm-test.cjs, crm-browser-test.cjs and the related regression suites; keep the checks for save rollback, wrong patient, stale/duplicate task, demo permissions, prescription gating, 200-row pagination, 5 viewports. When output files are locked, use a separate PEMA_EVIDENCE_DIR; never mark PASS before the tests finish.


## Mobile CRM02 and shared-shell finance

Read the [current-state guide](docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md). Finance must mount/dispose inside Clinic, selectors/CSS scoped to the workspace, no second role picker. Seed the extra 10 records once, keep existing records and handle ID collisions. Update the bundle with `node prototype/export-native-patients.cjs`; run `--check`, mobile-crm-test.cjs and the KMP `jvmTest`. Internal CSKH notes/handovers must not go into updates meant for Care.
