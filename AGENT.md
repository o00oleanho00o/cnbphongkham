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

Then update the README, related operations/domain docs, and append a checkpoint to SECTION_PROGRESS. For UI-only changes, check whether any acceptance criterion is affected.

## Testing and evidence

- Run the relevant suites: check-linked.cjs, review-desktop.cjs, operations-test.cjs, smoke-final.cjs, data-audit.cjs.
- For responsive work, check 1920×1020, 1440×900, 1280×720, 1024×768 and 390×844; no document overflow.
- Look at page errors, linked data and error states; an exit code alone is not enough.
- Keep docs in line with observed behavior; do not document a feature as existing just because it is planned.

## Shared inbox and customer messaging (package O)

Staff never contact patients from personal accounts; all customer messaging goes through Pema identities; personal Zalo only receives PII-free notifications. A staff reply is written in Pema (Inbox), leaves through the identity of the thread with no operator name or signature, and a personal Zalo id is only ever a notification target (short code, identity label, urgency, a template summary, a deep link behind the login: no name, phone number or message text). The internal notifier account never faces a customer. Never add a path that sends to a customer from an account that is not a clinic identity, or that puts patient data in a notification. Details: `pema-agent/docs/ARCH-AI01.md` section 16, `pema-agent/docs/SECURITY-REVIEW-AI01.md` section 11.

## Mobile app rules (KMP)

1. The mobile app is `pema-kmp/` (Kotlin Multiplatform + Compose Multiplatform). Follow [pema-kmp/CONVENTIONS.md](pema-kmp/CONVENTIONS.md) and [pema-kmp/README.md](pema-kmp/README.md). `flutter-template/` is legacy code kept for reference only: do not develop, build or test it, and do not use it as a source.
2. Keep the Pema logo, local Be Vietnam Pro (OFL), primary #0B4F94, navy #083A6E, sky #3CAAE5. Use child screens and short bottom sheets; do not carry desktop tables over or cram many modules onto the mobile home.
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

The design skill [pema-design](.agents/skills/pema-design/SKILL.md) is available for Pema UI/UX work; use it when the user asks for it. Usage/sharing guide: [docs/23_PEMA_DESIGN_SKILL.md](docs/23_PEMA_DESIGN_SKILL.md). When tokens, navigation or capabilities change, update the skill together with the docs so the guide does not drift from the code.

## CRM01 and demo accounts

- Read the PB01 set in order 0→1→2→3 and `docs/20_CRM01_PATIENT_LIFECYCLE.md` before editing. CRM business logic lives in crm-data/automation; the UI does not duplicate rules.
- Do not merge the owner/doctor/CSKH/accountant screens. `staff-context.js` assigns workspaces and demo commands; it is not authentication. Doctors only open records they own or are scheduled for; CSKH does not do medical review; accountants do not do clinical work.
- Demo date 2026-09-20, idempotency rule+patient+source. Booking from CRM must be in the same transaction as the task/activity and go through the schedule validator. Do not count reactivated from a booking; keep closed tasks when rerunning.
- Migrations never rewrite existing clinical records/invoices. The eight old CRM01 cases only use a new seed/reset; the 10 Mobile CRM02 accounts are added once when upgrading data, never overwriting existing records. Marketing opt-out does not remove safety follow-up. The internal CRM log is never published to the patient app automatically; the mobile projection uses the patient's own identity, never the staff member's selection.
- Run crm-test.cjs, crm-browser-test.cjs and the related regression suites; keep the checks for save rollback, wrong patient, stale/duplicate task, demo permissions, prescription gating, 200-row pagination, 5 viewports. When output files are locked, use a separate PEMA_EVIDENCE_DIR; never mark PASS before the tests finish.


## Mobile CRM02 and shared-shell finance

Read the [current-state guide](docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md). Finance must mount/dispose inside Clinic, selectors/CSS scoped to the workspace, no second role picker. Seed the extra 10 records once, keep existing records and handle ID collisions. Update the bundle with `node prototype/export-native-patients.cjs`; run `--check`, mobile-crm-test.cjs and the KMP `jvmTest`. Internal CSKH notes/handovers must not go into updates meant for Care.
