# Screens and business links

## System flow

Arrival at clinic → identification/profile → exam/consultation → plan/service → schedule/session → approved instructions/prescription → D1/D3/D7 follow-up by plan → update/photos with consent → doctor review/response → next appointment.

This is a design model; it does not mean every step is already implemented. Patient 360 aggregates context; the original event/record remains the source of truth. Check-in does not replace a clinical visit; invoice does not replace session; approved does not mean medicine has been dispensed.

## Platform split

| Context | Web | Flutter/mobile |
|---|---|---|
| Overview | KPIs with paths to work that needs handling | Next work, nearest appointment, short shortcuts |
| Patient 360 | Context + content tabs, using horizontal space | Compact identity + open each business screen |
| Coordination | Calendar/resources/filters, detailed tables | Day list, detail, date picker; do not cram in the desktop calendar |
| Orders | Multi-line editor and review/print | Search → cart → check → draft/approve → document |
| Follow-up | Queue and handoff status | Task list → separate response |
| Management | Services, doctors/rooms, cashier | Lookup/short tasks; complex administration prefers web |

Flutter Clinic: **Hôm nay / Lịch hẹn / Hồ sơ / Theo dõi / Thêm**. Care: **Trang chủ / Hành trình / Tin nhắn / Hồ sơ**. Do not increase main tabs just because a module is added; place the task in the correct context. The current Clinic/Care switch is a review tool, not login.

Current child screens: Patient 360; Đặt lịch/Chi tiết lịch/Lịch của tôi; Tư vấn/Kế hoạch điều trị/Buổi điều trị; Chăm sóc tại nhà/Gửi cập nhật/Phản hồi; Lên đơn nhanh/Kiểm tra đơn/Đơn thuốc & tư vấn/Phiếu A5; Hóa đơn/Thu ngân; Dịch vụ/Bác sĩ & phòng; Ảnh tiến triển/Ask Pema/Quyền riêng tư/Hướng dẫn.

## Design contract for each task

- State the patient and related record before mutation. Preserve choices when moving between screens/back; never make data from the previous person look as if it belongs to the next person.
- Primary action states the outcome (“Lưu nháp”, “Duyệt đơn”, “Gửi cập nhật”), not “Xong” for multiple different states.
- Validation appears near the faulty field and preserves entered content. Empty state points to the next step; loading/error/success are meaningful. Do not use a success toast when there is no real mutation yet.
- Define who receives the result, where it appears, the conditions for seeing it, and the next action. Store record status/permissions separately from UI state.
- Usage guidance must explain linkage/handoff and exception handling, not only a demo button-click script.

## Important flows

**Service/treatment:** service catalog → confirmed price and session count → plan → appointment → session with complete information → aftercare/follow-up → Care. In a complete implementation, invoice/plan must be reconciled, but care must not be completed from payment.

**Orders:** catalog → quantity/instructions → draft → classification check → doctor approval → Care/slip. Product source is the supplied Excel file; current snapshot has 115 rows (30 medicines, 78 advice items, 7 UNRESOLVED). Do not infer medicine from the name; missing type/usage must be handled before approval. Draft must not appear as instructions for the patient. Web has override reasons/NONE/separate A5 print; do not assume Flutter has them by default.

**Photos/responses:** content → consent if there are photos → submit → review queue → respond/resolve/escalate → Care. Separate consent, files, and task status; the label “ảnh đính kèm” does not replace storing a real photo. AI is a human-reviewed draft, not autonomous diagnosis/task closure.

**Cashier:** show total, collected, remaining, and related documents/status. A complete system needs ledger/deposits/partial collection/duplicate prevention; the template has not reached this level.

## Current boundaries to check before editing

Web Clinic/Patient Mobile use localStorage with the same origin/profile. Flutter is independent and memory-only; order/receipt, schedule/note/session/follow-up/cart are patient-scoped; Care/Clinic have separate selection. Flutter 09:00 schedule is hardcoded; A5 is only cards grouping approved orders; photos/AI/privacy are simulated; cashier still counts drafts and has no invoice entity/ledger. Do not hide these gaps with a production-like UI.

Read `docs/22_NATIVE_PARITY_AND_VALIDATION.md` for current state, `docs/20_CATALOG_ORDERS.md` for web orders/printing, `docs/06_CLINIC_WORKFLOW.md` and PB01 for the system contract. If assigned to complete business behavior, fix the data foundation and tests together with the UI, then update the matrix; do not treat template limits as permanent requirements.


## PB02 finance exception

The clinic-owner overview, revenue/reconciliation, and procedure fees newly use shared web/Flutter API/SQLite. Keep revenue, cash received, debt, and doctor fee distinct; rate snapshots, closing periods, role-based projections, and foreground notifications. Read `docs/24_FINANCE_AND_PROCEDURE_FEES.md` and the PB02 set before editing; the PB01 memory-only finance limit does not apply to the new module. Run `python prototype/finance_test.py` when changing formulas/ledger.


## CRM01 — staff-specific workspaces

The clinic owner sees an overall dashboard; doctors have their own home/schedule/profiles; CSKH has a work queue and workspace; accounting has cashier/reconciliation. BS. Tâm has separate owner and doctor views; do not model one shared dashboard for everyone. Patient 360 links context, and tasks open according to permissions/task. Accounts currently use sessionStorage demo, not an auth server.

CSKH today is proactive care; "Theo dõi" is clinical review. The appointment outcome must go to the existing form, validate, and only then resolve. Do not report “đã quay lại” as soon as booking starts. Conventions/sources: `docs/20_CRM01_PATIENT_LIFECYCLE.md`, `staff-context.js`, `crm-automation.js`, `crm-ui.js`.


Mobile CRM02: use `docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md` as the current-state source. Finance lives inside the Clinic shell; native selects the role before the task, and must not cram CSKH/cashier/clinical into one shared home. Care prioritizes one next step; internal work and handoffs must not become patient messages.
