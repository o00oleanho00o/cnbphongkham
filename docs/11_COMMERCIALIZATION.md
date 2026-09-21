# Commercialization hypothesis

## Reusable core
Tenant/clinic boundary, patient/episode/timeline, plans/sessions, photo protocol, follow-up queue, portal/mobile, RBAC, audit, notification adapters.

## Configuration
Treatment/procedure templates, image views and body areas, consent, forms, SLA/escalation, branding, service/package catalog, local language and message templates.

## Pema-specific during pilot
Exact clinical protocols, staff naming, package economics, Zalo/call habits and owner dashboards. Keep in config or adapters; don't fork core.

## Deployment/data
Start with single-tenant pilot or logically isolated tenant with tested export/backup. Document data owner/controller, processor, retention and deletion. Vietnam personal-data handling must account for [Decree 13/2023/NĐ-CP](https://vanban.chinhphu.vn/?pageid=27160&docid=207759); consult counsel before production. HIPAA is a US reference only ([HHS Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/index.html)), not a substitute for local advice.

## Local integration boundaries

- **Zalo/SMS:** adapter chỉ gửi template đã consent; lưu delivery/status và opt-out; không để inbound photo/symptom mất khỏi Follow-up Inbox. Zalo OA/mini app credentials thuộc clinic tenant, secret không nằm frontend.
- **E-invoice/payment:** tích hợp provider qua idempotent transaction reference; invoice/payment chỉ là context cho session, không lưu card data; refund/void phải audit. Xác nhận hóa đơn điện tử với đơn vị kế toán và quy định thuế hiện hành trước production.
- **National/e-prescription/medical data:** không quảng bá “tích hợp” nếu chưa có contract, mapping và legal review.

Vietnam legal baseline: [Nghị định 13/2023/NĐ-CP](https://vanban.chinhphu.vn/?pageid=27160&docid=207759) về bảo vệ dữ liệu cá nhân; [Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15](https://vanban.chinhphu.vn/?pageid=27160&docid=214590&classid=1&orggroupid=1) has effective date **01/01/2026** in its official record. Counsel must reconcile effective dates, health-data handling, cross-border transfer and processor/controller roles. Do not treat HIPAA as Vietnam compliance.

Integrations should be adapters after workflow validation. Audit exports and AI access. Productize only after 6–8 weeks baseline + pilot metrics.
