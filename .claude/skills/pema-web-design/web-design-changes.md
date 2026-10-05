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

### 2026-10-05 · add · Vai trò Kế toán (staff role, menu and Chốt kỳ)
- Where: `pema-agent/frontend/src/lib/ops/staff-view.ts`, `src/lib/session/session-context.tsx`, `src/lib/nav.tsx`, `src/components/admin/layout/app-shell.tsx`, `src/components/finance/finance-context.tsx`, `src/app/(admin)/finance/layout.tsx`, `src/app/(admin)/finance/periods/page.tsx`, `src/app/(admin)/finance/entries/page.tsx`, `src/lib/finance/finance-view.ts` · routes `/admin/users`, `/finance/periods`, `/finance/entries`, sign-in landing
- Change: a seventh role "Kế toán" in the role picker and filter of "Nhân viên" (hint "Kế toán: đối soát và thu ngân, tài chính, chốt kỳ; không duyệt đơn thuốc, không xem hồ sơ lâm sàng.") and in the user chip. The account opens on "Thu ngân" (`/cashier`) and its menu holds Tìm bệnh nhân, Thu ngân, Tài chính & tiền thủ thuật, Hướng dẫn (no Hôm nay, Theo dõi, Vòng đời khách hàng, Tổng quan, Điều phối lịch). "Chốt tháng" in Chốt kỳ and under the table of Tiền thủ thuật is shown by `finance_period.close` (accountant, manager, owner), "Xác nhận đã chi" stays with `finance.write`. A role that opens `/today` without the CSKH queue is moved to its own home instead of the "Bạn không có quyền xem màn này" card.
- Web canvas target: WI-series staff screen (Nhân viên), WG10 (Chốt kỳ), WG2 (Tiền thủ thuật); menu: block "sidebar"
- Logged by: U11

### 2026-10-05 · add · Tài chính & tiền thủ thuật: shell, Tổng quan, Chốt kỳ, Xuất CSV
- Where: `pema-agent/frontend/src/app/(admin)/finance/layout.tsx`, `src/app/(admin)/finance/page.tsx`, `src/app/(admin)/finance/periods/page.tsx`, `src/app/(admin)/finance/export/page.tsx`, `src/components/finance/finance-context.tsx`, `src/components/finance/finance-ui.tsx`, `src/components/finance/finance-dialogs.tsx`, `src/components/finance/test-support.tsx`, `src/lib/nav.tsx` · routes `/finance`, `/finance/periods`, `/finance/export`
- Change: the menu item "Tài chính & tiền thủ thuật" is no longer planned (needs `finance.read` or `finance.read_own`). The old single page with four tabs becomes routes under one shell: "ĐIỀU HÀNH • PEMA CLINIC", title, month picker "Kỳ báo cáo" (`?month=`), "Làm mới", tab bar "Phân hệ tài chính" (Tổng quan, Tiền thủ thuật, Chính sách tỷ lệ, Phiếu thu & thông báo, then two new tabs Chốt kỳ and Xuất CSV; a doctor and the owner on "Cá nhân" see Tổng quan, Tiền thủ thuật, Xuất CSV). The topbar role/doctor picker of the old web is gone: the projection comes from the signed-in user; the owner alone gets the chips "Toàn phòng khám" / "Cá nhân" (`?scope=own`). Tổng quan: hero (Đang đối soát / Đã chốt tháng / Đã chi), tiles Doanh số thực hiện, Thực thu trong tháng, Công nợ hiện tại, Tiền thủ thuật đã duyệt, personal view "GÓC NHÌN CÁ NHÂN" (Doanh số của tôi, Tiền chờ duyệt, no cash or debt), "Đóng góp của đội ngũ" / "Chi tiết của tôi" bars, "Việc cần đối soát" with "Mở bảng tiền thủ thuật →"; the hero line for the owner reads "CHỦ PHÒNG KHÁM • TỔNG QUAN ĐIỀU HÀNH" instead of "BS. TÂM • …". New screen Chốt kỳ: the last 12 months with state, entries, pending, the blocker sentence, "Mở bảng", "Chốt tháng", "Xác nhận đã chi". New screen Xuất CSV: month, projection, file name, "Tải CSV cho Excel", "Không xuất được bảng". The old `prompt()`/`confirm()` become dialogs (Hủy lượt thủ thuật with "Lý do hủy lượt chưa thu tiền", Chốt tháng with "Chốt số liệu tháng <tháng>? Các lượt trong kỳ sẽ bị khóa.", Xác nhận đã chi with "Mã chứng từ chi"). States: "Đang tải dữ liệu…", "Chưa kết nối dữ liệu tài chính: <reason>" with "Thử lại", "Vai trò của bạn không xem được dữ liệu tài chính.".
- Web canvas target: WG1, WG6, WG8, WG9, WG10, WG13, WG14, WG17, WG18, WG19, WG20 (Chốt kỳ and Xuất CSV as screens: new screen)
- Logged by: U6

### 2026-10-05 · add · Tiền thủ thuật (table, record form, approve and void)
- Where: `pema-agent/frontend/src/app/(admin)/finance/entries/page.tsx`, `src/components/finance/entries-table.tsx`, `src/components/finance/entry-form.tsx` · route `/finance/entries`
- Change: table "Bảng tiền thủ thuật • <tháng>" with the month badge, columns Ngày / Hồ sơ, Thủ thuật / Bác sĩ, Doanh số phân bổ, Cơ sở × tỷ lệ (with the basis), Tiền thủ thuật, Trạng thái (Chờ duyệt, Đã duyệt, Đã hủy with the reason), "Duyệt" and "Hủy" per row only while the month is open and for whoever may write, "Chưa có lượt thủ thuật trong kỳ này.", "Xuất CSV cho Excel", "Chốt tháng đã kết thúc" / "Xác nhận đã chi". Collapsible form "+ Ghi nhận lượt thủ thuật đã hoàn tất" (`?form=open`): Tìm hồ sơ (new search box) and Hồ sơ select fed by the patients API instead of the 36 fixed codes, Thủ thuật, Ngày thực hiện, Giá niêm yết, Giảm giá, Gắn hóa đơn đã có (only the invoices of the chosen patient, or "Tạo hóa đơn mới cho lượt này"), Ghi chú hoàn tất, "Ai thực hiện và được ghi nhận?" with Bác sĩ chính / Người phối hợp (tùy chọn), Tỷ trọng doanh số % and Tỷ lệ tiền thủ thuật %, "Ghi nhận • Chờ duyệt"; the old sentences for a wrong form show in a red notice above it. A closed or paid month shows no form and no row action.
- Web canvas target: WG2, WG3, WG7, WG11, WG13, WG14, WG16, WG21, WG22
- Logged by: U6

### 2026-10-05 · add · Chính sách tỷ lệ
- Where: `pema-agent/frontend/src/app/(admin)/finance/rates/page.tsx` · route `/finance/rates`
- Change: card "Chính sách theo thủ thuật" with the old notice; per service "Phiên bản N" (version of the service terms), Cơ sở (Giá sau giảm, Giá niêm yết, Theo thực thu), Tỷ lệ %, "Lưu tỷ lệ"; "Tỷ lệ chưa đổi." when nothing changed; a role that may not manage the catalog sees "Tỷ lệ chỉ hiển thị cho người quản lý danh mục."; the doctor text "Bác sĩ xem tỷ lệ trên các lượt của mình…" is not needed (a doctor has no such tab).
- Web canvas target: WG4
- Logged by: U6

### 2026-10-05 · add · Phiếu thu & thông báo, and the invoice panel of the cashier
- Where: `pema-agent/frontend/src/app/(admin)/finance/payments/page.tsx`, `src/app/(admin)/cashier/page.tsx`, `src/components/finance/payment-dialog.tsx`, `src/components/finance/invoice-panel.tsx`, `src/components/finance/billable-orders.tsx` · routes `/finance/payments`, `/cashier`
- Change: `/finance/payments`: "Thu tiền khách hàng" (Hóa đơn còn nợ, Số thu, Phương thức, "Xác nhận thu"), "Giao dịch trong kỳ" / "Chưa có phiếu thu.", owner-only "Thông báo của chủ phòng khám" with "Đã đọc", "Kế toán không đọc inbox của chủ." for the accountant, and the block "Đơn sản phẩm chưa có hóa đơn" with "Lập hóa đơn" and "In tách đơn". The old sentence "Phiếu thu mới đồng bộ với app khi đang mở. Hóa đơn web cũ thu tại Thu ngân Clinic…" is replaced by one about the anti-duplicate key and no collection over the balance (every invoice is collected in this app now). `/cashier`: the note in the card "Hóa đơn & thanh toán" is replaced by the old panel: totals, filter chips Tất cả / Còn phải thu / Đã thanh toán, table (Hóa đơn / bệnh nhân, Dịch vụ / đơn nhanh, Tổng tiền, Đã thu, Còn lại), "Thu tiền", badge "Đã thanh toán", "Không có hóa đơn.", paging "← Trước" / "Sau →" (12 per page), "In tách đơn", orders without an invoice with "Lập hóa đơn"; dialog "Thu tiền · <patient>" with the balance notice, "Số tiền (VND)", Phương thức (Tiền mặt, Chuyển khoản), "Xác nhận thu tiền", the error lines "Số tiền phải lớn hơn 0 và không vượt số còn lại." and "Số thu vượt công nợ". A role with neither `finance.read` nor `finance.collect` sees a note on who handles invoices.
- Web canvas target: WG5, WG12, WG15, WG23, WF1, WF2, WF21, WF22, WF23, WF24, WF25
- Logged by: U6

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
