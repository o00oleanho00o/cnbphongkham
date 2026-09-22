# Security & privacy notes

- Treat names, contact details, clinical notes, photos and patient updates as sensitive personal/health data.
- Minimize collection; separate identity from care projection; role-based access and clinic/tenant isolation.
- Consent records must state purpose, audience, retention and withdrawal path; clinical care sharing differs from marketing/before-after publishing.
- Encrypt in transit/at rest; signed short-lived image URLs; no raw photos in analytics logs.
- Audit view/export/edit/AI prompt/AI approval; alert bulk export.
- Define retention, correction, deletion/legal hold and breach response with counsel under Vietnamese law; use [Decree 13/2023/NĐ-CP](https://vanban.chinhphu.vn/?pageid=27160&docid=207759) as a starting reference.
- Patient messaging must state response expectation and emergency route; never present AI as a diagnosis or urgent triage substitute.
- Synthetic demo dataset must contain no real names, phone numbers, faces or identifiers.

## Current Vietnam legal checkpoint (20/09/2026)

The official government record for [Law 91/2025/QH15 — Personal Data Protection](https://vanban.chinhphu.vn/?pageid=27160&docid=214590&classid=1&orggroupid=1) states an effective date of **01/01/2026** and is the newer legal reference to review alongside [Decree 13/2023/NĐ-CP](https://vanban.chinhphu.vn/?pageid=27160&docid=207759). This prototype is not a legal compliance assessment. Before any real-patient pilot, counsel should establish controller/processor roles, permitted basis for sensitive health/photo processing, consent purpose separation, retention/correction/deletion, outsourcing agreements and cross-border AI/cloud data transfer conditions.

## Integration and AI handling
Zalo/SMS notifications should contain minimum necessary text and avoid clinical/photo details in push previews. E-invoice/payment providers receive only billing data required for the transaction. AI requests use role-filtered records, preferably pseudonymous patient IDs, with explicit provider data-processing terms and no training reuse by default unless separately consented and justified. Every generated note retains sources and clinician approval.

## Demo boundary
localStorage and synthetic SVG images are deliberately convenient for local demo; they provide neither encryption nor RBAC. Do not load real patient data. Production requires authenticated API, tenant/role checks, server audit, signed image URLs, retention and tested backup restore.


## Bổ sung Flutter template — 22/09/2026

Clinic/Care switch của Flutter không xác thực hoặc enforce RBAC. Privacy checkbox chỉ là widget state; consent ảnh mẫu không tạo bản ghi consent hay lưu file. Store chưa cách ly toàn bộ dữ liệu theo patient; không dùng hồ sơ thật. Các yêu cầu bảo mật trong tài liệu này là điều kiện pilot, không phải capability đã triển khai. Xem [ma trận native](22_NATIVE_PARITY_AND_VALIDATION.md).


## Bổ sung tài chính PB02

[Module tài chính và tiền thủ thuật](24_FINANCE_AND_PROCEDURE_FEES.md) dùng API :4174/SQLite chung cho web và Flutter. Role là mô phỏng, thông báo foreground; không áp mô tả memory-only của PB01 cho PB02. Chạy API riêng, không coi HTTP local là triển khai production.
