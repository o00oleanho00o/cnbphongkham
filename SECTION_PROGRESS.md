# SECTION_PROGRESS.md

## 2026-09-22 — Flutter native template review 01

- Added flutter-template: real Flutter Material 3 widget app with Android/iOS/Web scaffolds, Clinic/Care modes, Pema logo and Be Vietnam Pro, blue branding aligned to current web.
- Added native navigation, Patient 360 task screens, schedule/date selection, catalog quick order, draft/approve states, order projection, follow-up response, aftercare and payment demo. Bundled all 115 products; 7 unresolved types block approval.
- Added interactive browser review shell at /native-review/ and Flutter compiled preview /native-preview/. Generated preview is git-ignored; build-preview.ps1 recreates it from source.
- Updated docs in Scope → Spec → Module Map → Architecture order; README and docs/NATIVE-TEMPLATE.md explain mapping and review scope.
- Validation: flutter analyze clean; six tests pass including four viewport suites (360/390/430/768), populated order screens and catalog-to-review interaction; web build succeeds. Visually inspected Clinic/Care homes and role-switch sheet in browser.
- Native hardware, camera, PDF/printing, authentication, backend sync remain outside this template review. Source and limitations: flutter-template/README.md and VALIDATION.md. Next: user review of screen hierarchy, colors, density and task flows.

## 2026-09-20 — Research/domain checkpoint

### Completed by `/root/research_docs`
- Read the full Ultra package files: `START_PROMPT.txt`, `ULTRA_MASTER_PROMPT.md`, `PEMA_CONTEXT.md`, `FINAL_REVIEW_CHECKLIST.md`, `README_RUN.md`.
- Created the complete research/domain documentation set under `/docs` (00, 01–13, 16, 17), including executive summary, competitor gaps, top problems/opportunities, Pema workshop, workflow, domain model, product scope, patient app, AI roadmap, commercialization, architecture, privacy notes, demo script and exclusions.
- Created `/research/sources.md`, `/research/competitor-notes/official-capability-notes.md`, `/research/competitor-notes/vttech.md`, `/research/complaint-notes/evidence-log.md`, `/research/complaint-notes/appstore-verified.md`, `/research/complaint-notes/verified-complaints.md`; stored Apple RSS raw reviews under `/research/raw/`.
- Verified official public sources: ModMed dermatology/AI, Aesthetic Record Clinical Solutions, Pabau Features, Canfield VISIA, Skin Analytics, FDA AI/ML device list, VTTech public marketing pages and YouMed workflow pain article.
- Added dated Apple App Store review samples for Aesthetic Record EMR and PatientNow. Treat as qualitative, self-selected user signals; no prevalence claims.
- Documented VTTech access boundary: `annam.vttechsolution.vn` is a login shell; public marketing domain is `vttechsolution.com`; no patient or tenant data accessed.

### Product decisions passed to builder
- Differentiator is workflow continuity: Patient 360 + standardized photo metadata/consent + Follow-up Inbox + patient mobile, not another module checklist.
- Session completion must create/verify aftercare and follow-up ownership; patient-submitted photos stay `new` until staff/doctor review.
- AI output is draft/cited/doctor-reviewed; no diagnostic claim or efficacy score from placeholder images.
- Mobile must cover treatment journey/aftercare/send update, not only booking; chart and photo upload should be smoke-tested after every build change.

### Evidence limits / next work
- No independent VTTech complaint was verified. Capterra/G2/GetApp/Trustpilot/Reddit endpoints returned 403 or verification; no unsupported complaint was invented.
- Root agent should merge this checkpoint with actual prototype routes, screenshots and test evidence. Root owns `/docs/14_PERSONA_TESTING.md`, `/docs/15_UX_CRITIQUE.md`, screenshot/final-review checkpoints.
- Keep this file append-only. Each agent should add a dated checkpoint with files, test evidence, blockers and next exact action.

### Next action
Builder continues clinic/patient prototype. Root validates routes, cross-app state, screenshots, and updates this file. Scheduler should resume from here if the run is interrupted.

## 2026-09-20 — Research/domain deepening checkpoint

### Additional work
- Expanded executive summary to answer all 12 master-prompt questions explicitly.
- Added onsite discovery agenda (150 minutes), artifacts/data to bring, observation protocol and cashier/accounting questions.
- Added Patient/Episode/Plan/Session/Image/FollowUp relationship diagram and entity-to-current-prototype mapping.
- Documented current implementation accurately: vanilla static HTML/JS, 36 synthetic patients, `localStorage` key `pema-demo-v1`, same-origin sharing, no auth/server/RBAC/outbound notifications.
- Expanded commercialization with Zalo/SMS/e-invoice/payment adapter boundaries and AI/data-processing guardrails.
- Added official government record for Law 91/2025/QH15 (effective 01/01/2026) alongside Decree 13/2023; marked both as counsel review inputs, not a compliance certification.
- Added PatientNow and Zenoti official market references, plus App Store review evidence date precision.

### Handoff to root
Root should append actual runtime validation, screenshots, route names, test outcomes, UX critique and final review status here. If prototype behavior differs from docs, update docs to match observed behavior rather than claiming intended behavior.

## 2026-09-20 — Documentation handoff update

- Added root `README.md` with Python static-server run commands, URLs, same-origin localStorage limitation, synthetic-data warning and deliverable links.
- Added action/evidence linkage to top-problem, AI roadmap, product opportunities and product-scope docs.
- Confirmed existing prototype contains 36 synthetic patient records, clinic and patient entry points, and first-round screenshots; final runtime/screenshot status remains owned by root.

## 2026-09-20 — Patient app hardening checkpoint

- Patched `prototype/shared/patient.js`: safe persisted identity with P001 fallback; draft message/photo/consent survive clinic-originated state updates while Send screen is open; image data persists on new follow-up object; photo consent is explicit; aftercare acknowledgement and privacy actions update demo state; documents/aftercare actions have visible behavior; labels now say “tiến độ số buổi” rather than implying efficacy percentage.
- `node --check` passes for patient.js. Static server returned HTTP 200 for both `/patient-mobile/` and `/clinic-web/` before shutdown.
- Root should smoke-test browser interaction after this patch and align any CSS for semantic buttons.

## 2026-09-20 — Agent handoff safety note

Root/build agents temporarily hit service rate limits; all research/domain files and patient.js hardening are persisted on disk. Existing round-1 screenshots are intact under `demo-assets/screenshots/round-1/`. Ports 4173 are occupied by existing Python processes; final agent should reuse or stop only confirmed prototype server PIDs, then capture final screenshots and update docs 14/15/checklist.

## 2026-09-21 — Heartbeat continuation
- Scheduler heartbeat resumed the same task after interruption; no new section created.
- Verified docs/research and current prototype source present. Reused local static server on loopback port 4173.
- Final work: harden storage/data contract, run browser flows, capture final evidence, update review/checklist.

## 2026-09-21 — Patient.js verification checkpoint

- Guarded every patient mutation with snapshot/rollback around `Pema.save()`. Save failure now leaves message/photo/consent draft intact and never shows success; state mutation rolls back.
- Dynamic appointment display now handles missing/invalid dates with an explicit “Chưa có lịch” state and disabled confirmation.
- Stored identity is validated against dataset with P001 fallback; changing identity clears unsent draft to prevent cross-patient photo leakage.
- Consent is initially unchecked, resets when selecting a new photo, and is required only when an image is attached. Transformed upload data is previewed and persisted to follow-up `imageData`.
- Added progressbar ARIA labels and explicit copy that percentages represent completed sessions, not skin efficacy; added form labels/aria and live status toast.
- `node --check` passes for data.js, clinic.js, patient.js. Fresh Playwright smoke passed Home → Journey → Progress → Send (no console/page errors). Quota/save-failure test passed: rollback, draft retention, photo preview and retry persistence.
- Root owns final clinic cross-app tests and screenshot/final-review updates.

## 2026-09-21 — Final runtime evidence
- Clinic and patient JS passed node syntax checks after hardening.
- prototype/smoke-final.cjs: 12/12 checks pass; no console/page errors. Verified 36 synthetic patients, dynamic KPI, reception, session + aftercare, follow-up review/reply, AI note review, Ask Pema, patient image follow-up, cross-app inbox receipt and no horizontal overflow at 390px.
- prototype/capture-screens.cjs: final screenshots captured for clinic dashboard/today/Patient 360/consultation/treatment plan/treatment/studio/Follow-up/Ask Pema and patient Home/Journey/Before-after/Aftercare/Send/Appointments/Documents/Profile. No page errors; scroll width equals viewport at 360, 390, 768 and clinic 390.
- Synthetic export saved at demo-assets/demo-data/patients-and-events.json; 36 patients and 79 seeded sessions.
- Before/After explicitly labels synthetic illustration and no auto-alignment/efficacy claim. Patient-facing progress is labelled completed sessions, not skin improvement.
- Remaining pilot work is documented: real Pema shadowing, auth/RBAC/server persistence, consent/legal review, real image protocol, outbound integrations and clinical validation. Scheduler may be removed only after this evidence and checklist are reviewed.


## 2026-09-21 — Final documentation alignment checkpoint

- Rewrote root `README.md` and `prototype/README.md` with exact `127.0.0.1` binding/URLs, same-origin + same-browser-profile requirement, `pema-demo-v2` key, synthetic/localStorage/demo limitations, and patient self-service booking gap.
- Rewrote `docs/16_DEMO_SCRIPT.md` against actual current labels and controls: P001 Nguyễn Minh Linh, initial 2/5 → 3/5 after session save, Check-in/Mời vào phòng, Patient 360, Tư vấn note draft/edit/approve, Ghi buổi điều trị, Studio, Patient Home/Journey/Care/Send, Follow-up review modal, AI brief approve, deterministic Ask Pema.
- Updated `docs/12_TECH_ARCHITECTURE.md` to describe v2 localStorage imageData persistence and simulated AI; updated `docs/09_PATIENT_APP.md` with no patient self-service booking/rescheduling boundary.
- Demo script cites only `demo-assets/screenshots/final/smoke-results.json` for runtime evidence and explicitly calls other paths demo walkthroughs unless separately checked.
- No docs14/docs15/final-checklist changes; root owns those. No claims beyond smoke JSON added.

## 2026-09-21 — Final verification and evidence checkpoint

- Re-ran `node prototype/capture-screens.cjs` after the placeholder-image filter change. Capture completed with `errors: []`, 36 seed patients, and no horizontal overflow at patient widths 360/390/768 plus clinic width 390. `clinic-before-after.png` now shows valid synthetic SVG illustrations with explicit “minh hoạ tổng hợp” and no broken image icon.
- Re-ran node syntax checks for `prototype/shared/data.js`, `clinic.js`, and `patient.js`; all passed.
- Re-ran `node prototype/data-audit.cjs`: **20/20 PASS**.
- Re-ran `node prototype/smoke-final.cjs`: **12/12 PASS**, no console/page errors. Cross-app reception, treatment + aftercare, follow-up review/reply, AI note approval, Ask Pema, patient text + image update, clinic inbox receipt, and mobile overflow checks all passed.
- Final screenshots and manifests are present under `demo-assets/screenshots/final/`; synthetic export remains `demo-assets/demo-data/patients-and-events.json`.
- Package/root review checklists are aligned to the verified deliverables. Remaining limitations are documented as pilot work (auth/RBAC/server persistence, real clinic validation, consent/legal review, integrations, clinical image protocol, and no autonomous diagnosis).

## 2026-09-21 — Package checklist synchronized
- Reviewed package deliverables against root runtime evidence and research files.
- Marked all package `PEMA_DIGITAL_CLINIC_ULTRA_SINGLE_SECTION/FINAL_REVIEW_CHECKLIST.md` items complete and added evidence index linking smoke (12/12), data audit (20/20), final screenshots, persona/UX docs and scope caveats.
- Package checklist is synchronized; scheduler deletion remains a root-agent decision after final screenshot verification.

## 2026-09-21 — UI/UX refresh after owner feedback
- Replaced the serif/fallback typography with local Manrope; vendored Lucide SVG icons and licenses. Added shared design.css and ui.js.
- Reworked clinic navigation, metric strip, Patient 360 summary and timeline hierarchy, controls and modal keyboard access.
- Rebuilt mobile Home as a concise care hub and Journey with three recent events and expandable detail/history. Viewport-height app shell keeps header, scroll content and navigation separate.
- Browser smoke remains 12/12 PASS; patient smoke passes. Additional viewport/UI evidence: demo-assets/screenshots/ui-refresh/review-results.json.
- Audit, decisions and remaining accessibility/device validation limits: docs/18_UI_UX_REFRESH.md.

## 2026-09-21 — Pema brand and Fastboy lifecycle analysis
- Checked official Pema homepage/about with live desktop and mobile captures. Confirmed blue identity (`#0B4F94` + light blue), Pema+ clinic & spa logo, Be Vietnam Pro body/navigation and FS Magistral display headings; documented values Professional/Perfect, science, care and sustainability.
- Checked official Fastboy pages for Go Check In, Go Booking and company history. Extracted the useful pattern: phone check-in → recognized customer/visit history → reminders → review/return loop, plus booking/deposit/no-show controls.
- No code changes were made from this research pass. A plan is documented before implementation in `research/brand-review/README.md`; user screenshots are reference only.


## 2026-09-21 — Pema visual identity implementation
- Implemented the planned Pema pass: official local logo, Be Vietnam Pro, Pema blue tokens, cool clinical surfaces, semantic status colors and subtle Care Loop wave artwork.
- Updated Clinic Web and Patient Mobile headers/branding; mobile home remains compact with fixed viewport shell and independent scrolling.
- Fresh evidence after implementation: `smoke-final.cjs` 12/12, `patient-smoke.cjs` PASS, `data-audit.cjs` 20/20, `review-ui.cjs` 10/10, `capture-screens.cjs` errors `[]`.
- Final screenshots are refreshed under `demo-assets/screenshots/final/`; design rationale is in `docs/18_UI_UX_REFRESH.md`.


## 2026-09-21 — Functional management and resource scheduling
- Added operations-data.js, operations-ui.js and operations.css; wired four Clinic Web screens: resource calendar, doctors/rooms, services, cashier.
- Mock data: 84 appointments across seven days, four doctors/rooms/services, six waitlist entries, twelve unpaid/part-paid invoices, maintenance block.
- Supports actual create/move/drag-to-edit/cancel/confirm/check-in, conflict and buffer/shift/room checks, room blocking, service edits, partial/full payment with duplicate/overpayment guards, atomic rollback on save failure. Patient appointments/invoices synchronize using the shared store.
- New operation tests: 20/20 PASS, zero page errors. Previous smoke 12/12, UI 10/10, data 20/20 and patient smoke PASS.
- Evidence: demo-assets/screenshots/operations/. Usage, five-minute walkthrough and limitations: docs/19_OPERATIONS_DEMO.md.
- Local server restarted on 127.0.0.1:4173; direct scheduling entry /clinic-web/?screen=schedule.


## 2026-09-21 — Optimize work surfaces from user screenshots
- Removed narrow/max-width constraints from Clinic workspace and patient list. Added doctor and next appointment columns to use the space for actionable data.
- Schedule KPI cards condensed into a single strip; compact title/toolbar; desktop calendar and waitlist constrained to available viewport height. Patient table has its own scrolling region and sticky header.
- Captured schedule/patient layouts at 2048×978, 1440×900, 1280×720: no desktop document overflow; patient table fills main width less 48px padding. Evidence: demo-assets/screenshots/operations/layout-results.json and layout-*.png.
- Operations regression 20/20 PASS.

## 2026-09-21 — Desktop viewport and responsive review
- Set Clinic Web acceptance baseline to 1920×1020 CSS pixels at 100% browser zoom; widened fluid workspaces and removed the Guide article width cap on wide screens.
- Guide now uses a readable instruction column plus a handoff/context column; resources and services use four columns on wide monitors. Smaller desktop and phone breakpoints retain internal scrolling and no document horizontal overflow.
- Added `prototype/review-desktop.cjs`; reviewed 11 Clinic screens and 5 Patient 360 tabs at 1920×1020, 1440×900, 1280×720, 1024×768 and 390×844 (80 captures, no overflow). Evidence: `demo-assets/screenshots/desktop-1920/results.json`.
- Existing UI regression, operations and end-to-end smoke checks remain passing.


## 2026-09-21 — In-app system user guide
- Added Hướng dẫn navigation and direct route /clinic-web/?screen=guide, with nine searchable topics, role-based guidance, care journey map, related reading and links to operational screens.
- Rewrote docs/19_OPERATIONS_DEMO.md to match system usage guidance rather than demo walkthrough. Explains data handoffs and distinguishes current functionality from planned automation.
- Checked all nine topics, Vietnamese accent-insensitive search, empty search state, cashier link, direct load, and 390/768/1440 viewport widths: PASS, no page errors. Evidence guide-results.json / guide-desktop.png under demo-assets/screenshots/operations.

## 2026-09-21 — Patient-linked services and prescriptions
- Added shared `prototype/shared/care-finance.js` to migrate the existing mock dataset with service plans, agreed price/discount, session progress, deposit ledger and prescription status.
- Patient 360 now shows Dịch vụ & liệu trình and Đơn thuốc. Adding a service creates a linked pending invoice; draft prescriptions stay clinic-only until a doctor approves them.
- Patient Mobile shows approved prescriptions only, alongside the existing invoices and aftercare. Deposit allocation remains separate from later payment collection.
- Verified add-draft/approve/mobile visibility and 390px no-overflow in `prototype/check-linked.cjs`; existing UI, operations and smoke suites remain passing.

## 2026-09-21 — Documentation workflow PB01

- Đọc PM AI Bootcamp chỉ để rút ra phương pháp làm rõ scope, acceptance, foundation-first module map, architecture, human approval và validation; không đưa nội dung bài tập/đào tạo vào sản phẩm.
- Tạo bộ tài liệu áp dụng cho Pema hiện tại: docs/SCOPE-PB01.md, docs/SPEC-PB01.md, docs/MODULEMAP-PB01.md, docs/ARCH-PB01.md và root AGENT.md.
- Scope ghi rõ Clinic Web, Patient Mobile, Patient 360, dịch vụ/liệu trình, session, prescription approval, follow-up, consent, cashier/deposit và ranh giới prototype/pilot.
- Spec bổ sung use case, FR/NFR, Given/When/Then acceptance, ngoại lệ và synthetic-data constraints; Module Map đặt shared state, consent, audit/read-model conventions trước màn hình; Architecture tách demo localStorage khỏi pilot API/RBAC/database/media.
- README đã liên kết luồng 0 → 1 → 2 → 3 và quy tắc cập nhật downstream.
- Next exact action: chạy toàn bộ suite kiểm thử, kiểm tra diff, commit và push tài liệu cùng các thay đổi prototype đang có.

## 2026-09-21 — Final validation and publish checkpoint

- PB01 docs, AGENT.md, README links and existing linked service/prescription prototype changes committed as `03ea2fa` with message `docs: define Pema PB01 scope spec modules and architecture`.
- Validation: `git diff --check` PASS; `check-linked.cjs` PASS; responsive rerun 80/80 screens with zero overflow/page errors; `operations-test.cjs` 20/20; `smoke-final.cjs` 12/12; `data-audit.cjs` 20/20.
- Pushed and verified `origin/master` at `03ea2fa83004c117b94fceca131d6de3aa49e378`.
- Workspace still contains pre-existing/untracked `data/` and `%SystemDrive%/` artifacts; they were intentionally excluded from the commit.

## 2026-09-22 — Excel catalog orders, consultation split and A5 printing

- Read `E:\codex\indon\overview\.md`, print-template.js and preview.css. Used workbook at `F:\BUL_Research\DalieuOs\data\danhsach.xlsx`; requested `F:\BUL\_Research\...` path does not exist. No reference-project patient records imported.
- Rebuilt catalog reproducibly with a standard-library Python importer and source SHA-256. 115 products: 30 prescription, 78 consultation, 7 missing type kept UNRESOLVED (previous experimental catalog incorrectly routed missing types to consultation). JS/JSON parity verified.
- Added multi-item order entry to cashier and Patient 360, quantity/instructions/notes, explicit route override reasons, draft editing/version guards, snapshot prices, linked invoices, approval, persisted history and approved-only mobile groups.
- Added named review page, separate prescription/consultation previews, selective/all A5 monochrome printing, draft print guard, natural long-content pagination and consultation terminology. Kept legacy prescriptions without guessing matches; legacy quick-order drafts require catalog review before approval.
- Fixed malformed cashier table markup that interrupted modal interaction. Retained existing workspace changes and did not modify the reference project.
- Multi-tab payment/order stress exposed an unnecessary persisted payment-total cache in care hydration. Removed that write; totals already project from invoice ledger, preventing a reading mobile tab from overwriting newly created orders. Reran the order workflow twice after the fix and reran operations/smoke.
- Validation: catalog 9 checks + importer --check; order workflow 13 groups; actual PDF audit 7 files (5 items + footer on one A5, 24 long items on 6 pages, one oversized instruction on 5 pages, no missing text/blank pages); linked workflow PASS; operations 20/20; data audit 20/20; smoke 12/12; responsive 80/80, no page errors/overflow. New editor/review also checked at 1920, 1440, 1280, 1024 and 390 widths.
- Evidence under `demo-assets/screenshots/orders/` including results.json, pdf-results.json, screenshots and PDFs. Updated Scope → Spec → Module Map → Architecture, README and domain/operations docs. Still a localStorage prototype with simulated doctor identity; no production backend/RBAC claim.


## 2026-09-22 — Tài liệu chi tiết Flutter native template

- Đối chiếu main.dart, DemoStore, widget tests, build script và validation hiện có; cập nhật Scope → Spec → Module Map → Architecture theo boundary template hiện tại.
- Mở rộng AGENT.md, README gốc/Flutter, mapping màn và mạch sử dụng; thêm docs/README.md, 21_NATIVE_RUNBOOK.md và 22_NATIVE_PARITY_AND_VALIDATION.md. Đồng bộ ghi chú domain, scope, patient app, architecture, privacy, testing, UI/UX, vận hành và catalog.
- Ghi rõ memory-only/không sync web; order/receipt theo patient nhưng lịch/lâm sàng/follow-up/cart chung phiên; thu ngân chưa ledger, phiếu chưa PDF/in, ảnh và privacy là placeholder. Không gán bằng chứng web cho Flutter hoặc ghi template đã được chủ sản phẩm duyệt.
- Kiểm tra tài liệu: 93 liên kết nội bộ tồn tại; catalog web/Flutter bằng nhau theo SHA-256, 115 dòng (30 PRESCRIPTION, 78 CONSULTATION, 7 UNRESOLVED); git diff --check không lỗi whitespace. Đối chiếu test source: 6 test đã ghi trước đó, bốn widths đều height 844. Không chạy lại Flutter suite vì chỉ sửa tài liệu.
- Giữ nguyên các artifact/log không liên quan. Lần cập nhật này chưa commit/push.


## 2026-09-22 — Pema Design skill để chia sẻ

- Đóng gói `.agents/skills/pema-design/`: entrypoint, UI metadata và bốn reference visual-system, screens-and-flows, platform-layout, delivery-and-review. Giữ nhận diện Pema/Be Vietnam Pro, responsive 1920×1020, mobile theo tác vụ, Flutter Clinic/Care và workflow có bàn giao.
- Thêm docs/23_PEMA_DESIGN_SKILL.md với cách dùng trong repo/copy độc lập, prompt mẫu và bảo trì; cập nhật Scope → Spec → Module Map → Architecture, AGENT, README, docs index và UI/UX.
- Phân biệt quy ước thiết kế, khả năng template và mục tiêu production; không nhân bản assets/catalog hoặc đóng gói dữ liệu bệnh nhân. Đường dẫn không phụ thuộc máy tác giả.
- Validation: quick_validate.py PASS (chạy Python -X utf8 do default Windows cp1252 không đọc được tiếng Việt); 113 liên kết nội bộ hợp lệ; YAML UI metadata và default prompt hợp lệ; git diff --check PASS. Không đổi runtime, không chạy lại app tests. Chưa có đánh giá hành vi bởi agent độc lập.
- Người dùng yêu cầu commit/push; gom cả bộ tài liệu Flutter của lượt trước. Loại log/cache và các artifact không liên quan khỏi staging.


## 2026-09-22 — PB02 tài chính và tiền thủ thuật web/Flutter

- Phân tích và bổ sung Scope → Spec → Module Map → Architecture PB02: tách doanh số thực hiện, thực thu, công nợ, doanh số phân bổ và tiền thủ thuật; mặc định net sau giảm, cơ sở cấu hình, snapshot từng người và khóa kỳ.
- Thêm API Python/SQLite local :4174, dữ liệu mẫu 24 lượt/tháng hiện tại và trước; transaction, kiểm role projection, idempotent receipt/notification, duyệt/hủy, chốt tháng/đã chi, CSV, mirror cashier legacy. Không auth production hoặc push OS/background.
- Web workspace tài chính, config tỷ lệ, ghi 2 người (API 4), bảng đối soát, thu tiền/inbox; gắn invoice có sẵn để tránh nợ kép. Flutter module riêng dùng HTTP chung với web, home/chuông/Thêm/Patient 360 liên kết, màn chủ/kế toán/bác sĩ và polling foreground. PB01 lâm sàng giữ runtime cũ.
- Kiểm thử: 11 Python domain/HTTP tests PASS; Flutter analyze sạch, 12 tests PASS, build web PASS (warning CupertinoIcons framework như trước); cú pháp JS và git diff --check PASS. Đã copy build mới sang native-preview.
- Browser trực tiếp xác nhận split 70/30 và phí 15/5 trên net 2.400.000, duyệt; thanh toán 100.000 tạo thông báo trên Flutter; cashier cũ thu 50.000 mirror sang API/inbox; bác sĩ chỉ thấy phần cá nhân, không có form/duyệt. Đo 20 trạng thái web theo 5 viewport không document overflow. Ảnh và kết quả ở demo-assets/screenshots/finance. Dùng browser tool sau khi lệnh automation browser qua shell bị policy từ chối; không chạy lại đường bị chặn.
- Cập nhật AGENT/README, native docs/parity, hướng dẫn 24 và skill design; 102 liên kết tài liệu đã kiểm hợp lệ. UI Android/iOS thật, FCM/APNs, lương/thuế/hoàn tiền, điều chỉnh kỳ và migration buổi cũ chưa triển khai. Chính sách cơ sở/tỷ lệ cần xác nhận với phòng khám, hiện dùng giả định có cấu hình.
- Server :4173/:4174 đang chạy. Thay đổi lượt này chưa commit/push; giữ nguyên artifact/log không liên quan.
