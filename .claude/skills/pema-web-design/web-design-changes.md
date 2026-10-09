# Web design canvas change log

Sync baseline: `0c454cc`

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

### 2026-10-10 · add · Plugin agent: trang của plugin agent (Zalo)
- Where: `pema-agent/frontend/src/app/(admin)/admin/agent/layout.tsx`, `src/app/(admin)/admin/agent/page.tsx`, `src/app/(admin)/admin/agent/p/[plugin]/[page]/page.tsx`, `src/components/agent/agent-plugins.tsx`, `src/components/agent/plugin-kit.tsx`, `src/lib/nav.tsx`, `src/ui/icons.tsx`, `src/app/globals.css` · route `/admin/agent`, `/admin/agent/p/<plugin>/<page>`
- Change: menu entry "Plugin agent" (puzzle icon, section "Quản trị agent", `admin.agents`) opens the pages the agent's enabled plugins ship, drawn with the app kit: tabs "Trang của plugin agent" of the registered pages (plugin name added when several plugins have pages); today the Zalo plugin: "Tài khoản Zalo", "Danh bạ Zalo", "Bạn bè Zalo", "Nhóm Zalo", "Cầu nối Zalo" (`/admin/agent/p/zalo/accounts|contacts|friends|groups|bridge`). `/admin/agent` opens the first page or shows "Chưa có plugin nào có trang quản trị" ("Bật một plugin có trang quản trị (ví dụ Zalo) ở dịch vụ agent rồi mở lại mục này.") and "Không tải được trang của plugin: <tên>."; page states: spinner "Đang tải trang plugin", "Không tìm thấy trang này" (hint "Plugin <p> không có trang "<id>"." or "Plugin <p> chưa bật hoặc không có trang quản trị.", button "Về trang plugin agent"), "Không tải được trang của plugin <p>." + "Thử lại", "Không tải được trang plugin: <lỗi>" + "Thử lại", 403 with the API's sentence ("Bạn không có quyền quản trị agent."), 401 "Phiên đăng nhập đã hết. Đang chuyển tới trang đăng nhập…".
- Web canvas target: new screen (no web canvas id yet)
- Logged by: C3b-1

### 2026-10-10 · remove · Tài khoản Zalo, Danh bạ, Bạn bè (replaced by the Zalo plugin's pages)
- Where: `pema-agent/frontend/src/app/(admin)/admin/accounts/page.tsx`, `src/app/(admin)/admin/contacts/page.tsx`, `src/app/(admin)/admin/friends/page.tsx`, `src/components/admin/accounts/account-edit-drawer.tsx`, `identity-edit-dialog.tsx`, `identity-lines.tsx`, `notifier-card.tsx`, `qr-login-modal.tsx`, `src/components/admin/channels/channel-settings-panel.tsx`, `src/lib/nav.tsx`, `src/app/(admin)/layout.tsx` and `src/ui/README.md` (route lists in comments only) · routes `/admin/accounts`, `/admin/contacts`, `/admin/friends`
- Change: pages and menu entries "Tài khoản Zalo", "Danh bạ", "Bạn bè" removed; accounts (QR login, edit, delete), contacts and friends are now the Zalo plugin's pages under "Plugin agent". Not carried over by the plugin: the channel panel "Kênh gửi tin" (daily cap, gaps, send window, "Công tắc khẩn"), the policy-profile select, identities ("Sửa danh tính", "Giới hạn đang áp dụng", "Đang trực", "Lịch trực" link) and the card "Tài khoản thông báo nội bộ" (open question for the owner).
- Web canvas target: WJ23, WJ24, WJ25, WJ26, WJ27, WJ28, WJ29, WJ54-WJ66, WM24-WM29
- Logged by: C3b-1

### 2026-10-10 · change · SLA và khung giờ: bỏ liên kết "cài đặt kênh Zalo"
- Where: `pema-agent/frontend/src/app/(admin)/admin/care/timing/page.tsx` · route `/admin/care/timing`
- Change: card "Khung giờ gửi tin" now ends with "Múi giờ <tz>." only; the sentence "Khung giờ chỉnh ở cài đặt kênh Zalo." and its link to `/admin/accounts` (removed page) are gone.
- Web canvas target: unknown
- Logged by: C3b-1

### 2026-10-06 · change · Inbox: ba tab, lọc danh tính, người phụ trách và khóa soạn tin
- Where: `pema-agent/frontend/src/app/(admin)/inbox/page.tsx`, `src/components/ops/inbox/conversation-list.tsx`, `src/components/ops/inbox/thread-view.tsx`, `src/components/ops/inbox/holder-banner.tsx`, `src/components/ops/inbox/assignment-dialogs.tsx`, `src/ui/tabs.tsx` · route `/inbox`
- Change: tabs "Chờ nhận / Của tôi / Tất cả" with counts (segmented pills; `Tabs` gets `segmented`), select "Lọc theo danh tính" ("Tất cả danh tính" + the customer identities), tab and filter kept in the URL; each row shows "#code · identity", the holder ("Chưa ai nhận", "Bạn đang giữ", "<Tên> đang giữ") and the badge "<n> tin chưa đọc"; empty texts "Không có hội thoại nào đang chờ nhận" and "Bạn chưa phụ trách hội thoại nào"; thread header shows "<identity> · #code", buttons "Giao cho..." (`thread.assign`) and "Lịch sử phụ trách", and a holder banner: "Chưa có người phụ trách. Bấm Nhận ..." + "Nhận", "Bạn đang phụ trách hội thoại này." + "Trả lại", "<Tên> đang trả lời — Tiếp quản?" + "Tiếp quản", "Vai trò của bạn chỉ xem được hội thoại, không nhận hay trả lời được."; reply box locked with "<Tên> đang phụ trách. Tiếp quản để nhắn khách." while a colleague holds the thread; 409 `thread_locked` shows "Tin chưa gửi. Nội dung bạn soạn vẫn còn." + "Tiếp quản"; `no_identity` sentence and message badge; line "Khách thấy tin này từ "<identity>", không thấy tên nhân viên."; toast "Đã bị tiếp quản: <Tên> giữ hội thoại #code". Removed: the "Phụ trách:" picker and the button "Nhận xử lý" (replaced by the dialogs, owner design WM1-WM23).
- Web canvas target: WM1-WM16
- Logged by: O6

### 2026-10-06 · add · Inbox: hộp thoại Nhận, Tiếp quản, Trả lại, Giao cho..., Lịch sử phụ trách
- Where: `pema-agent/frontend/src/components/ops/inbox/assignment-dialogs.tsx` · route `/inbox`
- Change: dialog "Nhận hội thoại này?" (Hủy, Nhận); "Tiếp quản hội thoại" (field "Lý do tiếp quản" required, max 500, "Hoàng Nam, bạn và nhóm Zalo của đội sẽ nhận thông báo."); "Trả lại hội thoại" (radio "Về hàng chờ" / "Trả lại cho trợ lý AI", field "Ghi chú bàn giao", warning "Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được." on 501); "Giao hội thoại cho đồng nghiệp" (select "Người phụ trách" with "Bỏ người phụ trách (về hàng chờ)"); "Lịch sử phụ trách" (timeline of claim, takeover, release, shift end, assign).
- Web canvas target: WM17, WM18, WM19, WM20, WM21, WM22, WM23
- Logged by: O6

### 2026-10-06 · change · Tài khoản Zalo: danh tính, giới hạn đang áp dụng, thông báo nội bộ
- Where: `pema-agent/frontend/src/app/(admin)/admin/accounts/page.tsx`, `src/components/admin/accounts/identity-lines.tsx`, `identity-edit-dialog.tsx`, `notifier-card.tsx` · route `/admin/accounts`
- Change: subtitle "... mỗi account là một danh tính: khách chỉ thấy tên danh tính, không thấy tên nhân viên", heading "Danh tính" ("Khách hàng nhìn thấy tên của danh tính khi nhắn tin"), badge "Khách hàng" / "Nội bộ" per account, lines "Giới hạn đang áp dụng: tối đa N tin chủ động/ngày · cách nhau A–B giây (theo kênh | riêng)" and "Đang trực: ...", buttons "Sửa danh tính" and "Lịch trực"; dialog "Sửa danh tính" (name, purpose, daily cap, send gaps, blank = channel limit; "Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa."); card "Tài khoản thông báo nội bộ" (status, facts, "Cài đặt thông báo" dialog, or the warning with "Chọn tài khoản nội bộ"). No credential field.
- Web canvas target: WM24, WM25, WM26, WM27, WM28, WM29
- Logged by: O6

### 2026-10-06 · add · Lịch trực
- Where: `pema-agent/frontend/src/app/(admin)/admin/roster/page.tsx`, `src/components/ops/roster/roster-dialog.tsx`, `src/components/ops/roster/week-grid.tsx`, `src/lib/nav.tsx` · route `/admin/roster`
- Change: new page "Lịch trực" and menu entry "Lịch trực" (section "Zalo & CSKH"): tabs per identity, card "Đang trực bây giờ" with "Kết thúc ca", week grid with "Tuần trước" / "Tuần sau", "Thêm ca trực", "Thêm ca", legend "CSKH / Bác sĩ / Chủ phòng khám, quản lý"; dialogs "Thêm ca trực", "Sửa ca trực" (kiểu lịch "Lặp theo thứ" / "Một ngày", overnight sentence, "Xóa ca"), "Xóa ca trực này?", "Kết thúc ca của <Tên>?"; toast "Đã kết thúc ca: N hội thoại chuyển người trực, N về hàng chờ, N bỏ qua."; read-only sentence "Bạn chỉ xem được lịch trực. ..."; empty "Chưa có ca trực nào", error "Không tải được lịch trực.".
- Web canvas target: WM30-WM41
- Logged by: O6

### 2026-10-06 · add · Thông báo của tôi
- Where: `pema-agent/frontend/src/app/(admin)/me/notifications/page.tsx`, `src/components/ops/notifications/zalo-link-dialog.tsx`, `src/ui/top-bar.tsx`, `src/components/admin/layout/app-shell.tsx` · route `/me/notifications`
- Change: new page "Thông báo của tôi" (cards "Trong ứng dụng", "Đẩy lên điện thoại", "Chuông Zalo", "Giờ yên tĩnh", team group sentence), dialog "Liên kết Zalo" (one-time code, countdown, "Tạo mã mới" when expired), confirm "Hủy liên kết Zalo?", toasts "Đã liên kết Zalo." and "Đã lưu giờ yên tĩnh."; the top bar gets a gear link "Thông báo của tôi" beside the bell for roles with `notify.self`.
- Web canvas target: WM42-WM51
- Logged by: O6

### 2026-10-05 · change · Dark-mode tokens brand-500 and accent-strong (contrast)
- Where: `pema-agent/frontend/src/ui/tokens.css` (`.dark`), `src/ui/tokens.json`, `design-system/tokens.json`
- Change: dark `--color-brand-500` #2b7fc9 -> #3b8dd5 and `--color-accent-strong` #b5594a -> #c17467 so the `surface` label on them is 4.56:1 and 4.57:1 (was 3.81:1 and 3.44:1, below AA 4.5:1). Light mode unchanged. Affects primary button, active chip/tab, progress bar and avatar fills in dark mode.
- Web canvas target: token block of both web canvases (rebuilt by `web-canvas-build.cjs`) + every dark frame
- Logged by: U12

### 2026-10-05 · add · Hôm nay: bảng tiếp đón
- Where: `pema-agent/frontend/src/app/(admin)/today/page.tsx`, `src/components/ops/today/reception-table.tsx` · route `/today`
- Change: above the CSKH queue (kept, now under the heading "Việc CSKH hôm nay") the old reception table "Hôm nay tại Pema" for roles that read the schedule: subtitle "Tiếp đón theo từng lịch hẹn · <ngày>", button "＋ Đặt lịch mới" (`appointment.write`), tiles "Tổng lịch" and "Đã đến" plus six tiles that filter (Chưa đến with the confirmed visits, Đang chờ, Đang khám/điều trị, Hoàn tất, Đã hủy, Vắng hẹn), fields "Tên / mã KH / liên hệ" ("Tìm nhanh khách…"), "Trạng thái" ("Tất cả trạng thái", "Chưa đến (gồm đã xác nhận)" and the seven statuses) and "Bác sĩ" (none for a doctor), table columns Giờ, Mã KH · bệnh nhân, Liên hệ (phone and age), Nội dung, Trạng thái, Bác sĩ, Phòng and Người tạo (both from 1280px), Tiếp đón with Check-in and Vắng (Chưa đến, Đã xác nhận), Mời vào phòng (Đang chờ), Mở 360 (other statuses), "Không có lịch phù hợp.", paging "N lịch · Trang a/b · 25 dòng/trang" with "← Trước" and "Sau →"; below 768px the rows are the cards of the schedule board. Not built: column "Giá lịch dự kiến" and tile "Phát sinh hóa đơn hôm nay" (an appointment has no price or invoice here).
- Web canvas target: WB3, WB4, WB10, WB25, WB26, WB27, WB28, WB29
- Logged by: U10

### 2026-10-05 · add · Điều phối lịch: cột theo phòng
- Where: `pema-agent/frontend/src/app/(admin)/schedule/page.tsx`, `src/components/ops/schedule/room-grid.tsx`, `src/components/ops/schedule/appointment-card.tsx`, `src/components/ops/schedule/appointment-sheet.tsx` · route `/schedule`
- Change: switch "Cột theo" with "Theo bác sĩ" (the doctor columns, still the default) and "Theo phòng" for the day view, remembered per browser; the room grid (region "Lưới lịch theo phòng"): column "Giờ" with half-hour rows 08:00-18:00, a column per room headed by the room name and "N lịch", a compact card for each visit in its room (time and patient, status as the left edge and chip, next-step button on visits of 45 minutes or more), hatched strips "Khóa <từ>–<đến>" with the reason for each room block, a button "Đặt lịch <phòng> <giờ>" on each empty half hour (opens the booking sheet with that room and time), a card "Chưa xếp phòng" for visits without a room, button "＋ Khóa phòng" for `admin.rules` (the existing block sheet); the booking sheet has a field "Phòng" ("Chưa xếp phòng", the active rooms) and the card of the doctor board and the lists names the room beside the doctor; the backend's sentences "Phòng đang bận hoặc đang chuẩn bị sau lịch <giờ>.", "Trùng thời gian khóa: <lý do>", "Phòng đang tạm ngưng." and, when blocking, "Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng." Not built (as before): drag of a card onto a slot, service colours, buffer strips, "Chờ xếp lịch".
- Web canvas target: WB5, WB11, WB12, WB15, WB17
- Logged by: U10

### 2026-10-05 · add · Vai trò Kế toán (staff role, menu and Chốt kỳ)
- Where: `pema-agent/frontend/src/lib/ops/staff-view.ts`, `src/lib/session/session-context.tsx`, `src/lib/nav.tsx`, `src/components/admin/layout/app-shell.tsx`, `src/components/finance/finance-context.tsx`, `src/app/(admin)/finance/layout.tsx`, `src/app/(admin)/finance/periods/page.tsx`, `src/app/(admin)/finance/entries/page.tsx`, `src/lib/finance/finance-view.ts` · routes `/admin/users`, `/finance/periods`, `/finance/entries`, sign-in landing
- Change: a seventh role "Kế toán" in the role picker and filter of "Nhân viên" (hint "Kế toán: đối soát và thu ngân, tài chính, chốt kỳ; không duyệt đơn thuốc, không xem hồ sơ lâm sàng.") and in the user chip. The account opens on "Thu ngân" (`/cashier`) and its menu holds Tìm bệnh nhân, Thu ngân, Tài chính & tiền thủ thuật, Hướng dẫn (no Hôm nay, Theo dõi, Vòng đời khách hàng, Tổng quan, Điều phối lịch). "Chốt tháng" in Chốt kỳ and under the table of Tiền thủ thuật is shown by `finance_period.close` (accountant, manager, owner), "Xác nhận đã chi" stays with `finance.write`. A role that opens `/today` without the CSKH queue is moved to its own home instead of the "Bạn không có quyền xem màn này" card.
- Web canvas target: WI-series staff screen (Nhân viên), WG10 (Chốt kỳ), WG2 (Tiền thủ thuật); menu: block "sidebar"
- Logged by: U11

### 2026-10-05 · add · Hồ sơ bệnh nhân for the accountant (billing tab only)
- Where: `pema-agent/frontend/src/app/(admin)/patients/[id]/page.tsx`, `src/components/ops/patient/finance-only-view.tsx` · route `/patients/[id]`
- Change: a role that has `finance.read` but no Patient 360 (Kế toán) no longer gets the "no access" notice on a patient page: it sees the header (avatar, name, code, age) and the tab "Dịch vụ & tài chính" alone, from a projection without clinical data; every other role is unchanged.
- Web canvas target: WC27 (tab "Dịch vụ & tài chính"), header of WC4
- Logged by: U11 (entry added at the U12 merge)

### 2026-10-05 · add · Hồ sơ bệnh nhân: the four chips and "＋ Hồ sơ mới"
- Where: `pema-agent/frontend/src/app/(admin)/patients/page.tsx`, `src/components/ops/patient/new-patient-dialog.tsx` · route `/patients`
- Change: chips "Tất cả", "Đang điều trị", "Tái khám tuần này", "Có cảnh báo" under the search box (one selected, the list is asked for that view); button "＋ Hồ sơ mới" in the page header with `patient.write` opens the sheet "Thêm người bệnh" (eyebrow "Hồ sơ mới"; fields Họ và tên, Ngày sinh instead of Tuổi, Số điện thoại, Nguồn khách; no "Mối quan tâm"; button "Tạo hồ sơ"; error "Nhập tên người bệnh"), toast "Đã tạo hồ sơ" and the new record opens.
- Web canvas target: WC1, WC3
- Logged by: U9

### 2026-10-05 · add · Patient 360: tab "Dịch vụ & tài chính" and the dialog "Thêm dịch vụ vào liệu trình"
- Where: `pema-agent/frontend/src/components/ops/patient/finance-tab.tsx`, `src/components/ops/patient/patient-360-view.tsx`, `src/lib/ops/patient-tabs.ts` · route `/patients/[id]?tab=finance`
- Change: sixth tab "Dịch vụ & tài chính" (phone label "Tài chính"). Cards: "Hóa đơn của <tên>" (subtitle "Giá trị phát sinh, tiền đã thu và dư nợ; không suy hoàn tất điều trị", columns Hóa đơn, Dịch vụ, Phát sinh, Đã thu, Còn lại, foot "N hóa đơn của hồ sơ này", "Mở thu ngân →"; only with `finance.read` or `finance.collect`), "Dịch vụ & liệu trình" (sessions used/total, the price after discount fixed when added, "Chưa có dịch vụ gắn với hồ sơ.", "＋ Thêm dịch vụ" with `finance.write`) and "Đơn thuốc" ("Chưa có đơn thuốc.", "＋ Tạo đơn nháp" with `order.write`). Dialog "Thêm dịch vụ vào liệu trình" (Dịch vụ, Số buổi, Giảm giá (₫), notice "Giá đã chốt được lưu trên hồ sơ; thay đổi danh mục sau này không làm đổi liệu trình đã đăng ký.", "Lưu dịch vụ"). The accountant (no Patient 360) opens `/patients/[id]` on the header plus this tab alone (WC27). Not shown on purpose: the deposit notice (no deposit ledger exists); roles without a finance permission see no amounts and no billing button.
- Web canvas target: WC10, WC19, WC25, WC27, WC29
- Logged by: U9

### 2026-10-05 · add · Patient 360: "✦ AI brief", "Nhắn tin", "Thông tin cần nhớ", "Chăm sóc tại nhà", "Ngày dự kiến quay lại"
- Where: `pema-agent/frontend/src/components/ops/patient/patient-dialogs.tsx`, `src/components/ops/patient/patient-360-view.tsx`, `src/components/ops/patient/overview-tab.tsx` · route `/patients/[id]`
- Change: header buttons "✦ AI brief" (`session.write`) and "Nhắn tin" (`conversation.reply`), warning chips under the name. Dialog "Brief trước buổi hẹn" (subtitle says the draft is made from the records, not by a model; field "Brief mô phỏng · sửa trước khi duyệt"; the source notice; "Sao chép", "Duyệt & lưu brief"; "Brief không được để trống."). Dialog "Gửi cập nhật" (eyebrow "Tin nhắn · <tên>", "Gửi tin nhắn", a line that the note goes to the patient app timeline and not to Zalo or SMS). Tổng quan cards: "Thông tin cần nhớ" with "Sửa thông tin" (dialog "Thông tin cần nhớ": "Cảnh báo · mỗi dòng một mục", "Có đồng ý sử dụng ảnh chăm sóc", "Lưu thông tin"), and in "Chăm sóc sau điều trị" the buttons "Sửa ngày dự kiến" (dialog "Ngày dự kiến quay lại": date, Lý do, Nguồn with four sources, the notice about real appointments, "Lưu ngày dự kiến", error "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.") and "Chăm sóc tại nhà" (dialog "Chăm sóc tại nhà": "Hướng dẫn đã duyệt cho người bệnh", "Duyệt & gửi patient app", error "Hãy nhập hướng dẫn.").
- Web canvas target: WC13, WC14, WC15, WC16, WC18, WC32, WC34
- Logged by: U9

### 2026-10-05 · add · Patient 360 Tư vấn: card "Tiền sử & chẩn đoán"
- Where: `pema-agent/frontend/src/components/ops/patient/clinical-note-card.tsx`, `src/components/ops/patient/consult-tab.tsx` · route `/patients/[id]?tab=consult`
- Change: card at the top of the tab: subtitle "Bác sĩ ghi nhận, không dùng AI tự chẩn đoán", fields "Tiền sử đã khai thác" and "Khám / chẩn đoán do bác sĩ xác nhận" (both required), button "Bác sĩ lưu nhận định" (`session.write`), toast "Đã lưu nhận định có bác sĩ xác nhận", error "Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận."; read only without the permission.
- Web canvas target: WC5, WC6, WC31
- Logged by: U9

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
- Where: `pema-agent/frontend/src/app/(admin)/services/page.tsx`, `src/components/catalog/service-sheet.tsx`, `src/components/catalog/service-history-dialog.tsx`, `src/components/catalog/protocol-sheet.tsx` · route `/services`
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
- Result: the log starts here. Baseline `0c454cc` is the commit that holds W0–W3c (the front end was not touched by package W). Not pushed to claude.ai/design yet (W5).
