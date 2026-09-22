# Pema Digital Clinic — Architecture PB01

## CRM01 runtime

Identity demo `pema-staff` ở sessionStorage: owner-tam, doctor-tam/mai/an/lan, care-maianh/thu, accountant. Route/control lọc theo capability; guard command cho clinical, billing, config, CRM và approval. Bác sĩ đọc hồ sơ phụ trách hoặc có lịch được phân công. PB02 nhận account qua liên kết để chọn đúng projection API sẵn có. Client vẫn giữ toàn state và cho chuyển demo role: hoàn toàn không thay thế auth/RBAC server.

CRM dùng cùng `pema-demo-v2`, không thêm backend: `crmTasks`, `crmActivities`, `crmAutomationRules`, `crmSegments`, `patient.crm`. Clock 2026-09-20; timestamp mutation CRM tăng deterministic trong ngày. Task key = rule + patient + source event; trạng thái resolved vẫn giữ để chống tái sinh. Read model tính overdue/risk/lifecycle từ visits, plans, appointments; booking khác actual reactivation. Ngày hẹn từ appointment ưu tiên khuyến nghị, hủy quay về khuyến nghị; hoàn tất session mới áp protocol.

Mutations đi qua snapshot/rollback của PemaOps; booking nhận crmTaskId và payload, validate trước rồi lưu appointment/activity/task trong một lần save. Không bọc transaction lồng. Migration chỉ bổ sung field; fixture kể chuyện chỉ áp dụng seed mới/reset. Opt-out chặn rule marketing và giữ audit. Demo chưa có authorization, concurrency đa thiết bị hay scheduler chạy khi browser đóng. Không đồng bộ CRM sang Flutter/PB02 ngoài boundary hiện có.

Tài liệu tách kiến trúc demo đang chạy và đích pilot. LocalStorage prototype không phải production architecture.

## Native review container (22/09/2026)

`flutter-template/` là project Flutter Material 3, targets Android/iOS/Web. Browser preview build từ Dart lên `/native-preview/`, không WebView và không chia sẻ localStorage web. DemoStore/ChangeNotifier lưu state phiên, assets bundle chứa catalog 115 dòng. Production cần thay store bằng repository/API và bổ sung identity, lưu bền vững, permission/media, PDF/share và test thiết bị. Chưa có APK/iOS build nghiệm thu.

## Current demo container view

    Browser profile / same origin http://127.0.0.1:4173
    ├── Clinic Web: prototype/clinic-web/index.html
    │   ├── shared/clinic.js, care-finance.js, guide.js
    │   └── shared/styles.css + design.css
    ├── Patient Mobile: prototype/patient-mobile/index.html
    │   └── shared/patient.js
    └── Static HTTP server: python -m http.server 4173
        └── localStorage key: pema-demo-v2
            └── synthetic patients, events, plans, sessions, followups, invoices

- Vanilla HTML/JS, không build và không backend.
- data.js tạo 36 patient nền, crm-data.js bổ sung 10 hồ sơ nhóm CSKH; state đọc/ghi trong browser.
- Event-shaped arrays và read models nằm trong patient state; không có event bus hay transaction server.
- Ảnh là SVG/placeholder hoặc data URL resize trong localStorage.
- Hai app chỉ chia sẻ state khi cùng origin và browser profile.
- AI brief/Ask Pema/clinical draft là deterministic simulation; không gọi model và không chẩn đoán.

### Catalog order / print (2026-09-22)

- `import-product-catalog.py` đọc XLSX bằng thư viện chuẩn Python, kiểm tra cột/mã trùng/giá; sinh `product-catalog.json` và `product-catalog.js` từ cùng dữ liệu và runtime. Product ID dựa trên mã Excel, không dựa trên thứ tự dòng. SHA-256 nguồn đi theo đơn.
- `order-data.js` mở rộng PemaOps: saveOrder, approveOrder, orderPrintData. Dùng transact để reload, snapshot, save và rollback khi lỗi. Lưu `patient.quickOrders[]`, một invoice/orderId; sự kiện ghi bác sĩ/thời gian. Bản sửa cần đúng version và chưa nhận tiền.
- Order item giữ code/productId, name/unit/sourceType, rowNumber, catalogRoute/route/routeReason, quantity/unitPrice, usage/note. Đơn duyệt giữ reviewedBy/reviewedAt và không chỉnh sửa trực tiếp.
- `order-ui.js` phục vụ Thu ngân/Patient 360; `order-review/` đọc theo patient/order ID, render bằng HTML escaped, không tự in khi vừa lưu. `order-review.css` dùng @page A5, natural flow, không giới hạn chiều cao khi in. Direct print nháp chỉ có nhãn chưa được duyệt.
- Mobile đọc cùng quickOrders, chỉ approved, nhóm PRESCRIPTION/CONSULTATION; NONE không hiển thị. `prescriptions[]` cũ vẫn được giữ, không fuzzy migrate nội dung lịch sử. Đơn nhanh cũ phải mở sửa để đối chiếu catalog trước khi duyệt.
- Đây vẫn là prototype: actor bác sĩ do UI mô phỏng, chưa có identity/RBAC server. Catalog sản phẩm từ Excel là dữ liệu người dùng cung cấp; hồ sơ dùng để kiểm thử vẫn tổng hợp. Không lấy hồ sơ người thật hoặc QR/địa chỉ từ project tham khảo.

## Pilot target container view

    Clinic Web / Patient Mobile
            │ HTTPS + versioned API
    API gateway / BFF ── Identity & RBAC ── Audit/event envelope
            ├── Patient & Care service ── PostgreSQL relational core
            ├── Scheduling & Resource service
            ├── Billing/Deposit service
            ├── Follow-up/Communication service ── job queue ── Zalo/SMS/push adapters
            ├── Media/Consent service ── object storage + signed URLs
            └── AI orchestration ── prompt/version/source citations ── doctor approval gate
                             │
                   Patient 360 / Inbox / Mobile read models

Pilot có thể bắt đầu dạng modular monolith với boundary API rõ, sau đó tách service khi tải và ownership yêu cầu. Database/object storage là nguồn bền vững; read model là projection có thể rebuild.

## Data model tối thiểu

    Tenant/Clinic 1─N Staff/User ── Role/Permission
    Patient 1─N EpisodeOfCare 1─N TreatmentPlan 1─N TreatmentSession
    Patient 1─N Appointment ── Resource(Doctor/Room)
    PatientServicePlan ── ServiceCatalogItem ── Invoice 1─N Payment
    Invoice 1─N DepositAllocation
    TreatmentSession 1─N ClinicalImageSet ── Consent
    Patient 1─N Prescription 1─N PrescriptionLine
    Patient 1─N FollowUp 1─N Communication/Task
    All mutations ── AuditLog / ClinicalEventEnvelope

Bảng domain có tenantId, stable id, timestamps, actor và version; PII/clinical data tách quyền đọc. Approval, payment capture và consent revocation cần optimistic concurrency/idempotency.

## API boundaries cho pilot

| Boundary | Ví dụ endpoint | Ghi chú |
|---|---|---|
| Identity/RBAC | GET /me, GET /permissions | token, tenant, role; deny by default |
| Patients/360 | GET /patients/:id/360, POST /patients | source IDs trong read model |
| Scheduling | GET/POST /appointments, POST /appointments/:id/check-in | conflict server-side |
| Plans/sessions | POST /patients/:id/service-plans, POST /sessions/:id/complete | command validation |
| Prescription | POST /prescriptions, POST /prescriptions/:id/approve | chỉ bác sĩ |
| Follow-up | GET /followups, POST /followups/:id/respond | idempotent + audit |
| Media/consent | POST /media/upload-intent, POST /consents | signed URL, size/malware check |
| Billing | GET /invoices, POST /invoices/:id/payments | balance/overpayment guard |
| Guide/config | GET /guide/topics, GET /services | versioned config |

## Authorization matrix

| Action | Lễ tân | Bác sĩ | Chăm sóc | Thu ngân | Người bệnh |
|---|---:|---:|---:|---:|---:|
| Xem identity/lịch | ✓ | ✓ | ✓ | giới hạn | của mình |
| Sửa lịch/check-in | ✓ | giới hạn | ✗ | ✗ | yêu cầu |
| Ghi session | ✗ | ✓ | theo phân công | ✗ | ✗ |
| Duyệt prescription/AI draft | ✗ | ✓ | ✗ | ✗ | ✗ |
| Xem/phản hồi follow-up | ✗ | ✓ | ✓ | ✗ | gửi/xem của mình |
| Sửa invoice/thu tiền | ✗ | xem | ✗ | ✓ | xem |
| Xem ảnh clinical | theo consent | ✓ | theo phân công | ✗ | ảnh được chia sẻ |
| Quản trị catalog/role | quản lý | quản lý | ✗ | ✗ | ✗ |

Prototype chưa enforce matrix bằng login; đây là contract pilot cần deny-by-default tests.

## Reliability, security and clinical safety

- API mutation idempotency cho payment, approval, upload và message; optimistic locking khi hai người sửa cùng record.
- Mục tiêu p95 read < 500 ms và command < 1 s ở quy mô pilot; jobs retry có dead-letter và correlation ID.
- TLS, encryption at rest, secret manager, signed media URLs, tenant filter bắt buộc, không log PII/clinical content.
- Audit append-only cho đọc/sửa nội dung nhạy cảm; backup/restore drill và retention/erasure theo quyết định pháp lý.
- AI feature flag, prompt/model version, source event IDs và human approval; không autonomous diagnosis.
- Monitoring: error rate, queue lag, failed notification, stale projection, duplicate payment, consent violation.

## Runtime Flutter đang có — 22/09/2026

Luồng build: `Dart + bundled assets → flutter build web → prototype/native-preview → iframe native-review`. HTTP server chỉ phục vụ file tĩnh, không phải API. Android/iOS có target scaffold nhưng chưa có nghiệm thu build/thiết bị.

`main.dart → DemoStore (ChangeNotifier) → rootBundle products.json + patients.json`. Store không đọc localStorage `pema-demo-v2`; mở cùng origin vẫn không đồng bộ với Clinic Web/Patient Mobile. Reload/new session khôi phục fixture. Trong cùng instance, Clinic và Care đọc chung store.

| Dữ liệu | Shape / phạm vi thực tế |
|---|---|
| Bệnh nhân | 46 hồ sơ từ assets/patients.json, export fresh fixture web; không phải clinical aggregate đầy đủ |
| Order | id DN-n, patient, name, approved, total, items snapshot; sửa thay record cùng id |
| Receipt | Map patientId → tổng số đã thu; không có payment entity, ledger hay đối soát |
| Cart/editingOrder | Lưu trong PatientState theo patient ID, đổi người không mang giỏ/đơn đang sửa sang hồ sơ khác |
| Lịch, sessions, note, updates, response, consent UI | Lịch/buổi/note/messages/cart theo patient ID trong memory; privacy checkbox chỉ ở widget; không durable consent |

Mobile CRM02 đã kiểm cách ly lịch/note/buổi/cập nhật/phản hồi/cart/đơn đang sửa/ghi chú CSKH; Care và Clinic giữ selection riêng. Đây là cách ly state trong memory, không phải authorization. Pilot vẫn cần patientId trên từng record bền vững, repository theo domain, quyền server và test chống lẫn dữ liệu. Approval hiện là bool, chưa immutable/versioned và chưa có reviewer timestamp. Phiếu chỉ là projection trên approved orders, không document service.

Đích kiến trúc bên dưới là yêu cầu pilot, chưa phải implementation Flutter. Runbook: [21_NATIVE_RUNBOOK](21_NATIVE_RUNBOOK.md).

## Open architecture decisions

- Modular monolith hay service split tại pilot đầu tiên.
- PostgreSQL và object storage/provider phù hợp hạ tầng Pema.
- Identity provider và map staff/branch/role.
- Event transport (outbox + queue) và rebuild read model.
- Zalo/SMS provider, payment/e-invoice adapter và retry policy.
- Mobile offline, export, deletion và tenant migration.

## Migration path từ demo

1. Đóng schema fixture và stable IDs; adapter đọc state demo để seed test.
2. Tách command/read contracts theo MODULEMAP; viết API contract và authorization tests.
3. Chuyển media khỏi localStorage sang object storage với consent/retention.
4. Chuyển invoice/payment sang ledger server-side và reconciliation.
5. Bổ sung identity, audit, backup, notification sandbox và migration có kiểm tra.
6. Chỉ bật AI/notification production sau clinical owner sign-off và observability.


## Phân phối design skill

Pema Design là gói Markdown/YAML version cùng repository trong `.agents/skills/pema-design/`. Không được load vào app runtime và không thêm dependency backend. Có thể copy nguyên thư mục để dùng với agent khác; source path tính từ repo root. Không yêu cầu SDK/cache/compiled output trong package. Chi tiết [chia sẻ skill](23_PEMA_DESIGN_SKILL.md).


## Mobile và Clinic shell — 22/09/2026

Finance mount(root) đóng polling và bỏ response cũ khi unmount, selector giới hạn root, role lấy từ PemaStaff duy nhất. /finance chuyển query sang /clinic-web/?screen=finance. Seed bổ sung có marker phiên bản, ID tránh va chạm; dữ liệu hiện có giữ nguyên. Mobile ensure CRM trước render với guard event. Flutter state theo patient trong memory, riêng selection Care/Clinic; phân vai UI là mô phỏng, chưa auth server.

UI review CSKH mobile: trạng thái Cần làm / Đã liên hệ / Chờ bác sĩ ở đầu màn; tìm kiếm và nút Lọc mở sheet 10 nhóm, không trải 10 chip lên home. Card đầu nằm trong 440px đầu ở viewport 360; lọc/trạng thái phải thực sự đổi danh sách. Widget `care_workspace.dart` dùng cùng PatientState, ghi chú nội bộ giữ tách Care.
