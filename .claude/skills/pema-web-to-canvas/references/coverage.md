# Web ↔ canvas coverage

Baseline: 2026-09-23 · canvas `Pema App.dc.html` has 82 screens (A–H core app screens, I–K added from the web).
When rerunning the skill, compare the new web dump with this table; any new or changed web screen/tab/dialog is a candidate to add or update. Update the table after every run.

## Clinic Web (`prototype/clinic-web`, `shared/clinic.js`, `operations-ui.js`, `crm-ui.js`)

| Web | Canvas |
|---|---|
| `dashboard` Tổng quan | I1 (A1 is the reduced app home) |
| `today` Hôm nay · tiếp đón, Check-in / Vắng / Mời vào phòng | I2 |
| `schedule` Điều phối lịch theo phòng | I3 (A2 is the app schedule) |
| Dialog Đặt lịch hẹn (bệnh nhân, dịch vụ, bác sĩ, phòng, giờ) | I4 (F8 is the app version) |
| `patients` + Hồ sơ mới | A3 · I5 |
| `crm` CSKH hôm nay | C1–C4 |
| `crm` › Xử lý (kênh, kết quả, bước tiếp, phụ trách, ưu tiên) | I13 (C6 is the app version) |
| `followups` Follow-up Inbox + filter | I6 · handled in: F10 |
| `studio` Ảnh trước / sau | I7 |
| `resources` Bác sĩ & phòng · Khóa phòng | F14 · I8 |
| `services` Dịch vụ · Chỉnh dịch vụ | F13 · I9 |
| `cashier` Thu ngân · invoice list · Thu tiền (tiền mặt/chuyển khoản) | I10 · I11 (F11/F12 by patient record) |
| `cashier` › Lên đơn nhanh | F4–F7 |
| `finance` Tài chính & tiền thủ thuật (4 tabs) | H1–H9 |
| `ask` Ask Pema | I12 · F15 |
| `guide` Hướng dẫn | F16 |

## Patient 360 (tab `data-tab`, modal `data-modal`)

| Web | Canvas |
|---|---|
| `overview` | F1 |
| `consult` Tiền sử & chẩn đoán + AI draft | J1 · F2 |
| `plan` Kế hoạch · modal `plan-edit` | J3 · J4 |
| `session` Ghi buổi điều trị (protocol, vùng/góc chụp) | J5 · F3 |
| `photos` | I7 |
| `finance` Dịch vụ & tài chính | J6 |
| `crm` CRM & CSKH | J7 |
| `history` Lịch sử hợp nhất | J8 |
| modal `note` (AI brief) · `message` · `edit` · `care` | J2 · J9 · J10 · J11 |

## Patient Mobile (`prototype/patient-mobile`, `shared/patient.js`)

| Web | Canvas |
|---|---|
| `home` | E1 |
| `appointments` (separate tab on web, not in the core app tabs) | K1 · G3 |
| `journey` + recent updates | E2 · K3 |
| `progress` / Ảnh trước & sau | G5 |
| `care` Chăm sóc tại nhà | G1 |
| `send` Gửi cập nhật | G2 |
| `messages` | E3 |
| `docs` Tài liệu & hóa đơn | K2 · G7 |
| `profile` + Quyền riêng tư | E4 · G8 |

## Canvas-only (app), no web comparison needed

A5 "Thêm", A6 switch workspace, A7 payment SnackBar, B1–B2 doctor, D1–D2 accountant, F17 access denied, H7 connection lost.