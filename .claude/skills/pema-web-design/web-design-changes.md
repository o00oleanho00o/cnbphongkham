# Web design canvas change log

Sync baseline: `c40ba22`

Every time something **visible** in the Next.js front end (`pema-agent/frontend/src/app/**`, `src/ui/**`, `src/components/**`) is added, changed or removed (a page, tab, dialog, field, button, filter, status, flow, business-rule wording, or a design token in `src/ui/tokens.json` or `tokens.css`), add an entry under **Pending** and commit it in the same commit as the code. The `pema-web-design` skill reads these entries and only redraws the affected frames instead of re-checking all 81 screens. This is the Next.js counterpart of `.claude/skills/pema-web-to-canvas/web-changes.md` (which logs the old web `prototype/` for the app canvas); the old web itself is frozen and is not logged here.

**Log**: added or removed page, tab, modal or dialog · added, removed or changed field, button, filter, status · changed flow (which screen a button opens, where saving goes) · changed warning or business-rule wording ("AI chỉ là bản nháp", consent, not an emergency channel…) · changed colour, type or radius token · changed kit component look (`src/ui/*`).
**Do not log**: refactors with no visible change · tests · sample or mock data (unless it adds a new column or status) · fixes with no visible change · routes that only exist in Next.js and are out of the web canvas by decision D3 are still logged, with canvas target "none (D3)".

Template (newest entry on top):

```md
### YYYY-MM-DD · <add|change|remove> · <page/tab/dialog name>
- Where: `pema-agent/frontend/src/app/(admin)/<route>/page.tsx` · route `/<route>` · or `src/ui/<component>.tsx`
- Change: <which field/button/status/sentence/token was added, removed, changed; new flow>
- Web canvas target: <inventory ids, e.g. WB3, WB4 · "block <name>" · "token" · "none (D3)" · "new screen">
- Logged by: <name/agent> · commit/PR if any
```

If unsure of the canvas id, write "unknown"; the skill looks it up in `.claude/skills/pema-web-design/references/coverage-web.md`. Keep Vietnamese UI labels and wording exactly as they appear in the UI. `pending-web.cjs` accepts an entry as the log of a file when the entry names the file path (without `pema-agent/frontend/`) or, for files other than `page.tsx`/`layout.tsx`, its file name.

## Pending

### 2026-10-05 · add · Thu ngân (quick order, history) and the order dialog
- Where: `pema-agent/frontend/src/app/(admin)/cashier/page.tsx`, `src/components/orders/quick-order-dialog.tsx` · route `/cashier`
- Change: the menu item "Thu ngân" is no longer planned. Tiles (Tổng số đơn, Bản nháp, Đã duyệt, Catalog sản phẩm with its source file), banner "Lên đơn theo mẫu PEMA", button "Lên đơn nhanh", card "Hóa đơn & thanh toán" with a note that invoices and payment are the finance step (the old invoice list and "Thu tiền" are not built yet), history "Đơn thuốc & phiếu tư vấn" (Xem / in, Sửa nháp, 12 per page, "Chưa có đơn từ catalog."). Dialog "Tạo đơn thuốc / phiếu tư vấn" / "Sửa đơn nháp": patient, doctor, diagnosis, product search over the catalog, lines with quantity, sheet, usage, note and reason for a changed sheet, total, general advice, notice; the dialog is 1040px wide from `sm`. `?patient=` opens it for a patient, `?edit=` for a draft.
- Web canvas target: WF1, WF3, WF4, WF9, WF10, WF11, WF20, WF21, WF22 (WF2, WF23, WF24, WF25 are the payment half: not built, step U6)
- Logged by: U5

### 2026-10-05 · add · Tách đơn (order review) and Bản in A5
- Where: `pema-agent/frontend/src/app/(admin)/orders/[id]/page.tsx`, `src/app/(admin)/orders/[id]/print/page.tsx`, `src/components/orders/order-sheet.tsx`, `src/components/orders/order-sheet.css` · routes `/orders/[id]` and `/orders/[id]/print`
- Change: review page "Tách đơn – <patient>" with the two A5 sheets side by side (Đơn thuốc, Phiếu tư vấn), draft mark "BẢN NHÁP — CHỜ BÁC SĨ DUYỆT", notes for lines "Cần phân loại" and "Không in", buttons In đơn thuốc / In phiếu tư vấn / In tất cả (only for an approved, complete order), "Bác sĩ duyệt & gửi app" (responsible doctor or owner), "Sửa nháp", "Về thu ngân". Print page: toolbar, one sheet or both (`?sheet=`), A5 portrait, each sheet on its own page, a draft prints nothing; shell hidden in print.
- Web canvas target: WF5, WF6, WF7, WF8, WF12, WF13, WF14, WF15, WF16, WF17, WF18, WF19
- Logged by: U5

### 2026-10-05 · change · Patient 360 Kế hoạch tab: orders card
- Where: `pema-agent/frontend/src/components/ops/patient/plan-tab.tsx`, `src/components/orders/patient-orders-card.tsx` · route `/patients/[id]?tab=plan`
- Change: card "Đơn thuốc & phiếu tư vấn" under the plans (with `order.read` or `order.write`): "Tạo đơn nháp" (opens `/cashier?patient=`), the history of the patient with "Xem / in", and "Hiển thị trên app (xem trước cho nhân viên)" with approved orders grouped as Đơn thuốc and Phiếu tư vấn.
- Web canvas target: WC7, WC24
- Logged by: U5

### 2026-10-05 · change · Kit: wide dialog, print-friendly shell, menu alias
- Where: `pema-agent/frontend/src/ui/dialog.tsx`, `src/ui/app-shell.tsx`, `src/ui/sidebar.tsx`, `src/ui/top-bar.tsx`, `src/components/admin/layout/mobile-tab-bar.tsx`, `src/lib/nav.tsx`
- Change: `Dialog`/`Sheet` take `xwide` (1040px from `sm`, for two panes); the sidebar, top bar, tab bar and the page frame drop out of the printout (`print:` classes) so a page prints alone; the pages under `/orders` keep "Thu ngân" lit in the menu (`aliases`).
- Web canvas target: block Dialog · "none" for the rest (print media is not drawn)
- Logged by: U5

### 2026-10-05 · add · Dịch vụ (catalog, history, protocols)
- Where: `pema-agent/frontend/src/app/(admin)/services/page.tsx`, `src/components/catalog/{service-sheet,service-history-dialog,protocol-sheet}.tsx` · route `/services`
- Change: the menu item "Dịch vụ" is no longer planned. Catalog cards (price, treatment and room preparation minutes, rooms, protocol, Đang dùng / Tạm ngưng, terms version), add and edit sheet, history of price and rate versions, follow-up protocols (D+1, D+3, D+7, review day); commission rate and basis only for `admin.rules`; 1/2/3/4 columns (4 from 1600).
- Web canvas target: WE5, WE6
- Logged by: U4 sync

### 2026-10-05 · add · Bác sĩ & phòng (doctors, rooms, room blocks)
- Where: `pema-agent/frontend/src/app/(admin)/resources/page.tsx`, `src/components/catalog/room-sheets.tsx` · route `/resources`
- Change: the menu item "Bác sĩ & phòng" is no longer planned. Doctor cards with the shift and load of the chosen day, rooms (add, edit, deactivate), room blocks list, "Khóa phòng" dialog (08:00-18:00, reason) and "Gỡ khóa" after a confirmation.
- Web canvas target: WE3, WE4, WE7, WE8
- Logged by: U4 sync

### 2026-10-05 · add · Ảnh trước / sau (studio)
- Where: `pema-agent/frontend/src/app/(admin)/studio/page.tsx`, `src/components/catalog/studio-view.tsx` · route `/studio`
- Change: the menu item "Ảnh trước / sau" is no longer planned. Patient search kept in `?patient=`, view select (Chính diện, Má trái, Má phải) in `?view=`, side-by-side or slider comparison, zoom, illustrative placeholders while no photo exists, notices and consent metadata, "Thêm ảnh" goes to the patient record.
- Web canvas target: WE1, WE2
- Logged by: U4 sync

## Done

The skill moves entries from "Pending" down here with their result, then updates **Sync baseline** to the commit it compared against. Keep about the 20 most recent entries; older ones are in git history.

### 2026-10-04 · full sync · baseline
- Package W (W0–W4): inventory of the old web (81 ids), 405 screenshots at 5 viewports, 81 specs in `design-specs/web/`, MCP web tools, web canvas with 81 screens (`Pema Web redesign canvas/Pema Web.dc.html`).
- Result: the log starts here. Baseline `c40ba22` is the commit that holds W0–W3c (the front end was not touched by package W). Not pushed to claude.ai/design yet (W5).
