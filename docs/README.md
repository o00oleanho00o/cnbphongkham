# Bản đồ tài liệu Pema

## PB02 — Tài chính và tiền thủ thuật

Đọc [Scope](SCOPE-PB02.md) → [Spec](SPEC-PB02.md) → [Module Map](MODULEMAP-PB02.md) → [Architecture](ARCH-PB02.md), rồi [24 — Nghiệp vụ/cách chạy/validation](24_FINANCE_AND_PROCEDURE_FEES.md). API chung web/Flutter chỉ cho PB02; chưa chuyển toàn bộ lâm sàng PB01.


Cập nhật 22/09/2026. Đọc theo quyết định → yêu cầu → module → kiến trúc; tránh lấy một screenshot hoặc tên menu làm bằng chứng chức năng.

| Thứ tự | Nguồn chính | Nội dung |
|---|---|---|
| 0 | [SCOPE-PB01](SCOPE-PB01.md) | Boundary, giả định, câu hỏi mở, DoD web và template |
| 1 | [SPEC-PB01](SPEC-PB01.md) | Role/use case/acceptance; contract NT riêng Flutter |
| 2 | [MODULEMAP-PB01](MODULEMAP-PB01.md) | Module nền, dependency, source hiện tại |
| 3 | [ARCH-PB01](ARCH-PB01.md) | Runtime, model/state, phân quyền mục tiêu và migration |

## Duyệt và phát triển native

- [Native template](NATIVE-TEMPLATE.md): nhận diện, navigation, màn hình và mạch thao tác.
- [21 — Native runbook](21_NATIVE_RUNBOOK.md): fresh clone, SDK, build/preview, catalog, xử lý lỗi.
- [22 — Parity & validation](22_NATIVE_PARITY_AND_VALIDATION.md): có gì thực sự, giới hạn, test đã chạy, checklist còn mở.
- [Flutter README](../flutter-template/README.md), [validation lịch sử](../flutter-template/VALIDATION.md).

## Nghiệp vụ và vận hành

- [06 — Workflow](06_CLINIC_WORKFLOW.md), [07 — Domain](07_DOMAIN_MODEL.md), [08 — Scope V1](08_PRODUCT_SCOPE_V1.md), [09 — Patient app](09_PATIENT_APP.md).
- [12 — Architecture](12_TECH_ARCHITECTURE.md), [13 — Security/privacy](13_SECURITY_PRIVACY_NOTES.md).
- [18 — UI/UX](18_UI_UX_REFRESH.md), [19 — Vận hành](19_OPERATIONS_DEMO.md), [20 — Catalog/đơn/in web](20_CATALOG_ORDERS.md).
- [14 — Persona testing](14_PERSONA_TESTING.md), [15 — UX critique](15_UX_CRITIQUE.md), [16 — Demo script](16_DEMO_SCRIPT.md), [Review findings](REVIEW_FINDINGS.md).

Các tài liệu 00–05, 10–11 và 17 giữ bối cảnh nghiên cứu, chiến lược và scope lịch sử. Phần ghi kết quả web không tự áp dụng cho Flutter. Ngày/channels cụ thể và test source quyết định phạm vi bằng chứng; PB01 và ma trận 22 mô tả boundary hiện tại. Nếu code lệch spec, ghi chênh lệch và cập nhật theo 0→1→2→3, không tự ghi PASS.

Quy tắc đóng góp: [AGENT](../AGENT.md). Khởi động chung: [README](../README.md). Checkpoint append-only: [SECTION_PROGRESS](../SECTION_PROGRESS.md).


## Skill thiết kế Pema

[23 — Chia sẻ và sử dụng Pema Design](23_PEMA_DESIGN_SKILL.md): cách dùng $pema-design, cài/copy cho đồng nghiệp và prompt mẫu. [Entrypoint skill](../.agents/skills/pema-design/SKILL.md) dẫn tới hệ màu/chữ/ảnh, luồng nghiệp vụ, bố cục đa nền tảng và quy trình kiểm tra.


## CRM01 — replacement + proactive care

[20_CRM01_PATIENT_LIFECYCLE](20_CRM01_PATIENT_LIFECYCLE.md): tách tài khoản chủ/bác sĩ/CSKH/kế toán, mapping VTTECH, expected next visit, protocol tasks, work queue, timeline, metrics, tám case và demo 5 phút. CRM là web/localStorage; Flutter và tài chính PB02 đọc theo tài liệu riêng. Phạm vi/acceptance/module/architecture được cập nhật trong PB01.
