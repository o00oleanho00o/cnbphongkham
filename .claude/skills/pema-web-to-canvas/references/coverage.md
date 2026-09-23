# Đối chiếu web ↔ canvas

Mốc: 2026-09-23 · canvas `Pema App.dc.html` có 82 màn (A–H mirror Flutter, I–K bổ sung từ web).
Khi chạy lại skill, so dump web mới với bảng này; màn/tab/dialog web mới xuất hiện hoặc đổi nội dung là ứng viên cần thêm/sửa. Cập nhật bảng sau mỗi lần chạy.

## Clinic Web (`prototype/clinic-web`, `shared/clinic.js`, `operations-ui.js`, `crm-ui.js`)

| Web | Canvas |
|---|---|
| `dashboard` Tổng quan | I1 (A1 là home Flutter rút gọn) |
| `today` Hôm nay · tiếp đón, Check-in / Vắng / Mời vào phòng | I2 |
| `schedule` Điều phối lịch theo phòng | I3 (A2 là lịch Flutter) |
| Dialog Đặt lịch hẹn (bệnh nhân, dịch vụ, bác sĩ, phòng, giờ) | I4 (F8 là bản Flutter) |
| `patients` + Hồ sơ mới | A3 · I5 |
| `crm` CSKH hôm nay | C1–C4 |
| `crm` › Xử lý (kênh, kết quả, bước tiếp, phụ trách, ưu tiên) | I13 (C6 là bản Flutter) |
| `followups` Follow-up Inbox + lọc | I6 · xử lý: F10 |
| `studio` Ảnh trước / sau | I7 |
| `resources` Bác sĩ & phòng · Khóa phòng | F14 · I8 |
| `services` Dịch vụ · Chỉnh dịch vụ | F13 · I9 |
| `cashier` Thu ngân · danh sách hóa đơn · Thu tiền (tiền mặt/chuyển khoản) | I10 · I11 (F11/F12 theo hồ sơ) |
| `cashier` › Lên đơn nhanh | F4–F7 |
| `finance` Tài chính & tiền thủ thuật (4 tab) | H1–H9 |
| `ask` Ask Pema | I12 · F15 |
| `guide` Hướng dẫn | F16 |

## Patient 360 (tab `data-tab`, modal `data-modal`)

| Web | Canvas |
|---|---|
| `overview` | F1 |
| `consult` Tiền sử & chẩn đoán + nháp AI | J1 · F2 |
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
| `appointments` (tab riêng trên web, Flutter không có) | K1 · G3 |
| `journey` + cập nhật gần đây | E2 · K3 |
| `progress` / Ảnh trước & sau | G5 |
| `care` Chăm sóc tại nhà | G1 |
| `send` Gửi cập nhật | G2 |
| `messages` | E3 |
| `docs` Tài liệu & hóa đơn | K2 · G7 |
| `profile` + Quyền riêng tư | E4 · G8 |

## Chỉ có trên canvas (Flutter), không cần đối chiếu web

A5 Thêm, A6 đổi workspace, A7 SnackBar thanh toán, B1–B2 bác sĩ, D1–D2 kế toán, F17 ngoài quyền truy cập, H7 mất kết nối.
