# U9 — Patient 360 and `/patients` parity fixes (round 2, owner-approved 2026-10-05)

## Goal
Close every "fix needed" row of `PARITY-AI01-U.md` left by U8: the create-patient dialog and filter chips on
`/patients`, a "Dịch vụ & tài chính" tab on Patient 360, the remaining Patient 360 dialogs, and the missing
"Tiền sử & chẩn đoán" card. Owner decision 2026-10-05: build all of it (do not re-ask).

## Read first
1. `pema-agent/docs/PARITY-AI01-U.md` §4 (visual parity table, rows `/patients`, Patient 360 Tổng quan/Tư vấn,
   "Dịch vụ & tài chính").
2. Screen specs (ground truth for copy and fields, read the "Logic source" line of each):
   `design-specs/web/screens/WC3.md` (create-patient modal), `WC10.md`/`WC19.md`/`WC25.md`/`WC27.md`/`WC29.md`
   ("Dịch vụ & tài chính" tab, states for role care/accountant and an empty patient), `WC13.md`/`WC32.md` (AI brief
   dialog, states for an existing vs. a just-created patient), `WC14.md` (Gửi cập nhật / "Nhắn tin"), `WC15.md`
   ("Thông tin cần nhớ"), `WC16.md` ("Chăm sóc tại nhà"), `WC18.md`/`WC34.md` ("Ngày dự kiến quay lại" + its
   validation error), `WC5.md`/`WC6.md`/`WC31.md` (Tư vấn tab, for the "Tiền sử & chẩn đoán" card).
3. Old logic: `prototype/shared/clinic.js` (`modalHtml`, `patient360`), `care-finance.js` (`planPanel`,
   `prescriptionPanel`, `financial`, `addService`), `crm-ui.js` (`financial`, `handle('expected')`),
   `crm-automation.js` (`expected()` validation), `data.js` (`brief`).
4. Existing code: `pema/clinic/actions/patient_360.py`, `patients.py`, `crm_overview.py`; FE
   `components/ops/patient/*`, `components/ops/crm/*`; U11 (this recipe's sibling) adds the `accountant` role —
   if U11 is not yet merged, use `Role.MANAGER` for the accountant-only controls below and note it as an open item.

## Ingredients
- `/patients`: "＋ Hồ sơ mới" dialog (name required; synthetic data only, no real patient creation shortcuts) wired to
  the existing `POST /patients`; filter chips "Tất cả / Đang điều trị / Tái khám tuần này / Có cảnh báo" as a client
  filter over the existing list (no new BE field unless the data to compute "Có cảnh báo" does not exist yet — if so,
  add a read model action instead of a fake filter).
- Patient 360 new tab "Dịch vụ & tài chính": service plan list (service, sessions used/total, price snapshot),
  pending prescriptions, link to the patient's invoices (`/cashier`, `/orders/[id]`, `/finance` if U6/U11 merged);
  "＋ Thêm dịch vụ vào liệu trình" dialog (service select, sessions 1–20, discount, price fixed at save) restricted to
  `billing` capability (owner, accountant once U11 lands — manager meanwhile); "Mở thu ngân →" link. Empty states: no
  plan/prescription (`WC29`), role `care` hides the billing buttons (`WC25`), role `accountant` keeps them (`WC27`).
- Patient 360 header buttons: "AI brief" (opens a read-only draft built from the patient's events — **no LLM call,
  no clinical judgement**: the "brief" is a templated summary of existing events/next-step/overdue facts, doctor
  edits and approves it, "Sao chép" copies it; empty patient → the two fallback sentences of `WC32`) and "Nhắn tin"
  (`WC14`: a short note sent to the patient app timeline, not a new channel, not Zalo).
- "Thông tin cần nhớ" card/dialog: free-text alerts (one per line) + the existing photo-consent checkbox (reuse the
  consent action from U3, do not duplicate consent state).
- "Chăm sóc tại nhà" dialog: aftercare text sent to the patient app timeline; empty text is rejected.
- "Ngày dự kiến quay lại" dialog: date + reason + source (same source list as the old web, excluding `appointment`);
  validation error exactly as `WC34` describes.
- Tư vấn tab: "Tiền sử & chẩn đoán" card (read-mostly: conditions, allergies, current diagnosis; doctor edits) next
  to the existing consult-note draft.

## Steps
1. Confirm which of the above the current FE already has partially (header buttons may exist as placeholders) before
   adding anything twice; check `FEATURE-INVENTORY.md` first.
2. BE: new actions only where no equivalent exists (brief template, aftercare send, key-facts save, expected-return
   set, service-plan add) — RBAC per the capability each dialog needs (clinical: doctor/owner; billing: owner/
   accountant-or-manager); audit every mutation.
3. FE: the tab, the dialogs, the filter chips; mobile the tab becomes part of the existing segmented control.
4. Append rows to `FEATURE-INVENTORY.md`; update `PARITY-AI01-U.md` §4 rows from "fix" to "same"/"dev" with the new
   screenshot slugs.
5. Inventory + smoke + visual at 5 viewports.

## Acceptance
- Every row this recipe targets in `PARITY-AI01-U.md` §4 moves off "fix needed"; inventory green; vitest ≥ 1093
  (U8 baseline); visual 0 overflow.
- No action here calls an LLM or infers a clinical fact; "AI brief" is a template, not a judgement.

## Out of scope
- Image analysis of any kind. Changing who may approve orders (U11 decides that, separately).

## Report
Use `_REPORT-TEMPLATE.md`; list which rows of `PARITY-AI01-U.md` §4 you closed and which screen ids you used as the
source for copy/fields.
