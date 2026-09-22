# Technical architecture (demo → pilot)

## Implemented demo (current workspace)

`prototype/clinic-web/index.html` and `prototype/patient-mobile/index.html` are vanilla HTML/JS entry points. `prototype/shared/data.js` creates 36 synthetic Vietnamese patients and persists state under localStorage key `pema-demo-v2`; `prototype/shared/clinic.js` renders clinic routes; `prototype/shared/styles.css` supplies responsive UI. The current implementation is a local same-origin, same-browser-profile simulation: state changes are event-shaped objects inside patient records and follow-up arrays, not a server event bus. Both entry points need to be served by a static HTTP server (file:// is not the supported run path). Patient mobile reads/writes the same localStorage key when hosted under the same origin; cross-origin hosting will not share state without a future API.

## Demo seam

Keep clinic and patient routes visually distinct but use stable IDs so a session completion can feed patient app and follow-up queue. Current prototype supports synthetic session save, aftercare/event timeline, follow-up review/response, image upload persistence in localStorage, AI brief/note draft and deterministic Ask Pema simulation; it does not provide authentication, multi-tenant isolation, server persistence, or real outbound notifications. AI does not call a model or diagnose.

## Pilot seam
API boundaries: Identity/RBAC, Patient/Clinical, Scheduling, Media/Consent, Follow-up/Communication, AI orchestration, Audit. Postgres-style relational core + object storage for images; read models for Patient 360 and Inbox. Background jobs handle notifications and AI; every job idempotent.

## Entity → prototype mapping

| Domain entity | Current demo representation |
|---|---|
| Patient/Profile | `patients[]` with name, age, phone mask, concern, consent |
| Episode/Plan/Item | `plan`, `total/completed`, concern and procedure fields |
| Session/Procedure | `sessions[]` and `events[kind=session]`; device settings are not yet captured |
| ClinicalImage/ImageSet | `sessions[].imageData` / `followups[].imageData` as resized data URLs plus generated SVG placeholders; persisted only in localStorage for demo, not an object-storage media service |
| FollowUp/Communication | `followups[]`, `messages[]`, event kind followup/message |
| Appointment/Visit | patient `next`, `time`, `status`, appointment event |
| Medication/HomeCare | `meds[]`, `aftercare` |
| Catalog Order / Print | `quickOrders[]` via `order-data.js`, `order-ui.js`, `order-review/`; catalog generated from XLSX, two document projections and approved-only mobile |
| Audit | `audit[]` action/actor/time; not tamper-resistant |
| Invoice/Payment | synthetic `invoices[]` only |

Relationships: Patient 1→N Episode; Episode 1→N PlanItems and Sessions; Session 1→N ImageSet/Instructions/FollowUps; Patient 1→N Appointments/Communications. Timeline and Inbox are read models in the target architecture, but are derived inline in the demo.

## Production non-negotiables
TenantId on every record; no PII in logs; encrypted transport/storage; signed media URLs; explicit consent/retention; event/audit IDs; export/restore drill; feature flags for AI. Use synthetic data in demo.



## Bổ sung Flutter template — 22/09/2026

Bổ sung Flutter Material 3 trong `flutter-template/`; `main.dart` dùng DemoStore/ChangeNotifier, catalog bundle, memory-only. Browser preview là Flutter build, review shell chỉ chứa iframe. Target Android/iOS có scaffold nhưng chưa nghiệm thu build/device. Không nối API hoặc localStorage của web. [ARCH-PB01](ARCH-PB01.md) mô tả state boundary hiện tại; [runbook](21_NATIVE_RUNBOOK.md) hướng dẫn build và đồng bộ catalog.


## Bổ sung tài chính PB02

[Module tài chính và tiền thủ thuật](24_FINANCE_AND_PROCEDURE_FEES.md) dùng API :4174/SQLite chung cho web và Flutter. Role là mô phỏng, thông báo foreground; không áp mô tả memory-only của PB01 cho PB02. Chạy API riêng, không coi HTTP local là triển khai production.
