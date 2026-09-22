# Pema Digital Clinic — Module Map PB01

Module map đi từ nền ẩn đến trải nghiệm nhìn thấy. Module phải có owner, contract trạng thái và bằng chứng trước khi mở rộng màn hình.

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

Để sau MVP: real auth/RBAC, API/database, object storage, notification thật, payment gateway, warehouse/accounting, multi-branch, native app, model-backed AI, import/migration patient.

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
