# Pema Digital Clinic — Module Map PB01

## CRM01: foundation → experience

`staff-context.js` chứa danh sách tài khoản giả lập, workspace routes, capability guards và liên kết role sang PB02. SessionStorage theo tab giúp hai nhân viên demo mở hai cửa sổ riêng; không phải identity provider. Patient Mobile giữ identity riêng và projection đơn thuốc đọc đúng identity, không dựa vào patient đang chọn của nhân viên.

`crm-data.js` (migration không phá state, clock, 8 case khi reset) → `crm-automation.js` (rules, read models, task/activity commands, metrics) → operations transaction (booking/check-in) → `crm-ui.js` + `crm.css` (queue/workspace, Patient 360, dashboard, tiếp đón). Clinic shell chỉ nối navigation/render; Patient Mobile chỉ đọc projection chăm sóc. Clinical Follow-up Inbox độc lập với proactive CSKH; PB02 vẫn sở hữu tài chính mới. `crm-test.cjs` kiểm rules/commands; browser evidence kiểm flow A/B/C và responsive.

Module map đi từ nền ẩn đến trải nghiệm nhìn thấy. Module phải có owner, contract trạng thái và bằng chứng trước khi mở rộng màn hình.

## Native template (22/09/2026)

`flutter-template/lib/state/` giữ catalog và state trong phiên bằng Riverpod; `main.dart` gồm Theme/Workspace/Detail, Clinic/Care navigation, form và sheet. `assets/` dùng logo/font/catalog hiện tại. Test domain và layout đặt trong `test/`. API, auth, camera/PDF plugins để sau duyệt.

## Foundation layer — móng ẩn

| Module | Trách nhiệm | Contract |
|---|---|---|
| Identity placeholder | Actor demo; seam cho login/RBAC pilot | actorId, role, tenant/clinic placeholder |
| Patient identity | patientId ổn định, search, masked contact, duplicate guard | PatientProfile, merge policy mở |
| Shared state/store | localStorage demo, migration, reset, cross-app read/write | key pema-demo-v2, schemaVersion |
| Event/audit envelope | nguồn mutation | eventId, patientId, episodeId, actorId, occurredAt, type |
| Consent | ảnh, aftercare và privacy acknowledgement | status, capturedAt, scope, revocation |
| Read-model conventions | Patient 360, Inbox và Mobile projection | source IDs, derivedAt, stale/error state |
| Synthetic fixture | 36 patient, dịch vụ, lịch, invoice, media placeholder | deterministic seed, no real PII |

## Domain layer

1. Patient / Episode / Care Journey — identity, concern, owner, timeline.
2. Service Catalog — duration, prep/buffer, giá tham khảo, protocol link.
3. Patient Service Plan — agreed price/discount, total/used sessions, owner, status.
4. Scheduling / Reception — appointment, waitlist, check-in, conflict, room block.
5. Treatment Session — planned → arrived → in_progress → completed/cancelled; note, operator, aftercare.
6. Prescription / Homecare — draft, reviewed/approved/rejected/revoked; medication lines, visibility.
   - Product Catalog: importer XLSX tái lập + snapshot JS/JSON, rowNumber/source hash, phân loại thiếu cần review.
   - Catalog Order: nhiều dòng, route có lý do, version/snapshot, hóa đơn liên kết, duyệt và mobile projection.
   - Order Review/Print: preview theo nhóm, in A5 từng nhóm/tất cả, giữ đủ nội dung nhiều trang.
7. Follow-up / Communication — update, message, task, severity, dueAt, assignee, resolution.
8. Clinical Media — image set, body area, capture context, consent, review state.
9. Invoice / Payment / Deposit — invoice snapshot, payment, allocation, balance và guards.
10. Guide / SOP links — role và journey guidance tied to routes.

## Experience layer

| Surface | Modules | Mục tiêu |
|---|---|---|
| Clinic shell | navigation, search, notifications, responsive layout | đi đúng nơi theo vai trò |
| Dashboard/Today | appointments, tasks, counts | biết việc cần làm ngay |
| Patient 360 | identity, journey, domain panels, read models | hiểu bối cảnh trước hành động |
| Schedule/Reception | scheduling, service, resources | xếp đúng người, nguồn lực |
| Treatment workspace | plan, session, media, aftercare | ghi nhận và bàn giao |
| Follow-up Inbox | follow-up, communication, media | không bỏ sót phản hồi |
| Cashier | invoice, payment, deposit | đối soát minh bạch |
| Patient Mobile | mobile projections, consent, messages | người bệnh biết bước tiếp theo |
| In-app Guide | guide/SOP links | hướng dẫn xuyên hệ thống |

## Validation and observability

- check-linked.cjs: service, invoice, prescription, mobile, five Patient 360 tabs và 390px overflow.
- review-desktop.cjs: 11 Clinic screens + 5 Patient 360 tabs ở 5 viewport.
- operations-test.cjs: conflict, waitlist, resource, service, payment, rollback.
- smoke-final.cjs: route và interaction smoke.
- data-audit.cjs: fixture relationships, status và cross-app state.
- product-catalog-test.cjs + import-product-catalog.py --check: catalog khớp Excel; order-test.cjs: workflow UI và guards; order-pdf-test.py: kích thước, số trang, đủ dòng/chữ và footer PDF thực tế.
- Screenshot evidence ở final, operations, ui-refresh và desktop-1920.
- SECTION_PROGRESS.md là checkpoint append-only.

## MVP cut line

MVP PB01 gồm patient identity, shared state, consent/audit shape, Patient 360, schedule/reception, service plan, session, prescription approval, follow-up, cashier/deposit, Patient Mobile và evidence.

Để sau MVP: real auth/RBAC, API/database, object storage, notification thật, payment gateway, warehouse/accounting, multi-branch, native production, model-backed AI, import/migration patient. Template Flutter để duyệt đã nằm trong scope riêng, không thay thế các module nền này.

## Module Flutter hiện tại — 22/09/2026

| Thành phần | Nguồn | Trách nhiệm / phụ thuộc |
|---|---|---|
| App shell, theme, navigation, các màn | `flutter-template/lib/main.dart` | Material 3; `ref.watch` provider, ghi qua notifier; chưa tách feature package |
| CSKH mobile | `flutter-template/lib/care_workspace.dart` | Ba trạng thái, tìm kiếm, lọc nhóm trong sheet và mở tác vụ đúng patient |
| Tài khoản mẫu | `flutter-template/assets/patients.json`, `prototype/export-native-patients.cjs` | Snapshot 46 hồ sơ/10 nhóm từ fresh fixture; kiểm đồng nhất bằng `--check` |
| State và đơn hàng | `flutter-template/lib/state/*.dart` (+ `*.g.dart` sinh tự động) | Riverpod `@riverpod`; catalog, session/selection, state theo patient + cart, order snapshot, receipt totals, finance; memory only trừ finance HTTP |
| Catalog | `flutter-template/assets/products.json` | Bản sao `prototype/shared/product-catalog.json`; import Excel ở web trước rồi đồng bộ bundle |
| Nhận diện | `flutter-template/assets/` | Logo, Be Vietnam Pro và giấy phép OFL; dùng chung ngôn ngữ thiết kế web |
| Review shell | `prototype/native-review/index.html` | Chọn khung iframe; không sở hữu nghiệp vụ Flutter |
| Build và kiểm tra | `flutter-template/build-preview.ps1`, `test/` | build_runner, build/copy preview và 18 test (template, finance, mobile roles); generated output không sửa trực tiếp |

Thứ tự phát triển sau duyệt: chốt identity + per-patient model → repository/API + persistence → phân quyền/audit → nghiệp vụ lịch/đơn/ledger/follow-up → plugin media/PDF/notification → device acceptance. Không thêm màn để che thiếu nền. Phân định web/native theo [ma trận parity](22_NATIVE_PARITY_AND_VALIDATION.md).

## Dependency order

1. Identity/patient IDs → shared state/schema migration.
2. Consent + event/audit shape → domain mutations.
3. Catalog/service plan → appointment/session → follow-up/media.
4. Prescription approval và invoice/deposit projections.
5. Patient 360 và mobile read models.
6. Guide, QA scripts, screenshots và evidence.

Không xây thêm màn hình chỉ để đủ menu khi module nền chưa có trạng thái, mutation và acceptance test.

## Câu hỏi ownership

- Ai sở hữu catalog/protocol và ai được sửa giá chốt?
- Ai chịu SLA Follow-up Inbox và escalation ngoài giờ?
- Ai duyệt template prescription/aftercare và AI draft?
- Khi có backend, module nào sở hữu event và module nào chỉ đọc projection?


## Module hỗ trợ thiết kế

`.agents/skills/pema-design/` chứa SKILL.md, agents/openai.yaml và bốn references visual-system, screens-and-flows, platform-layout, delivery-and-review. `docs/23_PEMA_DESIGN_SKILL.md` hướng dẫn dùng/chia sẻ. Skill đọc source/assets/docs hiện có, không tạo bản sao runtime hoặc catalog.


## Mobile và Clinic shell — 22/09/2026

Tái dùng finance.js dưới dạng mount/dispose, CSS giới hạn trong finance-workspace; Clinic làm shell duy nhất. crm-data bổ sung fixtures và projection patientNext; patient.js chọn nhóm/tài khoản. Flutter provider chứa hồ sơ và state theo patient, Workspace chọn vai trò trước khi chọn tác vụ.

UI review CSKH mobile: trạng thái Cần làm / Đã liên hệ / Chờ bác sĩ ở đầu màn; tìm kiếm và nút Lọc mở sheet 10 nhóm, không trải 10 chip lên home. Card đầu nằm trong 440px đầu ở viewport 360; lọc/trạng thái phải thực sự đổi danh sách. Widget `care_workspace.dart` dùng cùng PatientState, ghi chú nội bộ giữ tách Care.
