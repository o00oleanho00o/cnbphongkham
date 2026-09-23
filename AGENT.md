# AGENT.md — Quy tắc làm việc cho Pema Digital Clinic

## Quy tắc tài chính PB02

Khi sửa tài chính, đọc SCOPE/SPEC/MODULEMAP/ARCH-PB02 theo 0→1→2→3 và [hướng dẫn nghiệp vụ](docs/24_FINANCE_AND_PROCEDURE_FEES.md). Không trộn doanh số thực hiện với thực thu/tiền thủ thuật. Giữ snapshot tỷ lệ, chặn thu trùng/vượt nợ, không sửa kỳ chốt, không tự gán bác sĩ thực hiện từ owner hồ sơ. API phải trả projection theo role; role header vẫn chỉ là mô phỏng. Chạy `python prototype/finance_test.py` và Flutter test khi đổi logic; không đưa DB `.local/` hoặc dữ liệu thật vào Git. Giới hạn memory-only Flutter ở mục dưới chỉ áp dụng PB01; PB02 dùng HTTP/SQLite.


Áp dụng cho mọi thay đổi trong workspace Pema.

## Trước khi sửa

1. Đọc SCOPE-PB01, SPEC-PB01, MODULEMAP-PB01, ARCH-PB01 theo thứ tự.
2. Đọc domain/product/architecture docs liên quan và kiểm tra hành vi prototype trước khi suy ra yêu cầu.
3. Xác định thay đổi thuộc prototype hay pilot; không gọi là production nếu chưa có backend/security tương ứng.

## Sản phẩm và dữ liệu

- Hồ sơ bệnh nhân phải là dữ liệu tổng hợp; không đưa hồ sơ, ảnh, số điện thoại hay token thật vào repo, fixture hoặc screenshot. Catalog sản phẩm là ngoại lệ có chủ ý: dữ liệu từ Excel người dùng cung cấp, không được gọi là catalog giả lập.
- Patient 360 nối bối cảnh nhưng record/event gốc là nguồn sự thật.
- Giữ consent cho media và audit shape cho mutation.
- AI/clinical draft có nguồn và bác sĩ review; không autonomous diagnosis, efficacy score hoặc đổi phác đồ tự động.
- Không suy diễn chăm sóc hoàn tất từ thanh toán, hoặc đơn thuốc đã cấp từ việc được duyệt.
- Giữ Clinic Web ↔ Patient Mobile và stable IDs khi sửa shared state.

## Luồng tài liệu bắt buộc

Khi thay đổi scope hoặc hành vi, cập nhật theo thứ tự:

    0 SCOPE-PB01 → 1 SPEC-PB01 → 2 MODULEMAP-PB01 → 3 ARCH-PB01

Sau đó cập nhật README, docs vận hành/domain liên quan và append checkpoint vào SECTION_PROGRESS. Nếu chỉ sửa UI, ghi màn/viewport/screenshot evidence và kiểm tra acceptance bị ảnh hưởng hay không.

## Kiểm thử và bằng chứng

- Chạy suite phù hợp: check-linked.cjs, review-desktop.cjs, operations-test.cjs, smoke-final.cjs, data-audit.cjs.
- Với responsive, kiểm tra 1920×1020, 1440×900, 1280×720, 1024×768 và 390×844; không document overflow.
- Xem screenshot, page errors, dữ liệu liên kết và trạng thái lỗi; exit code một mình chưa đủ.
- Cập nhật docs khớp hành vi quan sát được, không ghi tính năng đã có chỉ vì dự kiến.

## Quy tắc riêng cho template Flutter

1. Đọc [mapping màn](docs/NATIVE-TEMPLATE.md), [runbook](docs/21_NATIVE_RUNBOOK.md) và [parity/test](docs/22_NATIVE_PARITY_AND_VALIDATION.md) trước khi sửa native. Xác định thay đổi là vòng duyệt thiết kế hay triển khai nghiệp vụ thật.
2. Source là `flutter-template/lib/` và assets; `prototype/native-review/index.html` chỉ là khung duyệt. Không sửa `build/` hoặc `prototype/native-preview/` đã compile; build lại sau sửa source.
3. Giữ logo Pema, Be Vietnam Pro local/OFL, primary #0B4F94, navy #083A6E, sky #3CAAE5. Dùng màn con và bottom sheet ngắn; không bê bảng desktop hoặc ép nhiều module lên home mobile. Token thay đổi phải cập nhật mapping và kiểm tra web liên quan.
4. Catalog đi từ `data/danhsach.xlsx` → importer web → `prototype/shared/product-catalog.json` → `flutter-template/assets/products.json`. Kiểm hash/count/type, không sửa độc lập hai bản hoặc suy loại từ tên. Xem lệnh ở runbook.
5. State Flutter là provider Riverpod sinh bằng `riverpod_generator` trong `flutter-template/lib/state/` (catalog, session, patients, orders/receipts, finance); memory-only, độc lập localStorage web. Provider giữ state phiên phải `keepAlive: true`; model immutable, sửa bằng method của notifier, không mutate map/list tại chỗ. State hiện tách theo patient: order/receipt, lịch/note/buổi/follow-up/cart, ghi chú CSKH và bàn giao; Care/Clinic giữ selection riêng. Khi sửa data model phải kiểm isolation và cập nhật ARCH/parity; giữ test cách ly mọi field mới và không suy ra persistence/auth từ cách ly memory.
6. Header Clinic/Care không phải RBAC. Phiếu A5 không phải PDF/in native. Checkbox ảnh không tạo file hoặc consent bền vững. Không ghi đã tích hợp các capability này chỉ vì có UI.
7. Khi sửa `lib/state/`: chạy `dart run build_runner build` và commit file `*.g.dart` sinh ra. Khi Dart/assets thay đổi: `dart analyze` (chạy cả `riverpod_lint`; `flutter analyze` không chạy plugin này), `flutter test --reporter expanded`, build preview; xem trực tiếp các màn bị ảnh hưởng. Review ở 360×800, 390×844, 430×932, 768×1024; suite hiện tại dùng height 844 ở cả bốn width. Không suy test tự động bằng test thiết bị.
8. Ghi riêng test đã chạy, kiểm tra thủ công, acceptance còn mở; không dùng kết quả web để xác nhận native. Android/iOS device, keyboard, accessibility, camera, PDF cần bằng chứng riêng.
9. Với thay đổi chỉ tài liệu: đối chiếu source, kiểm link nội bộ và `git diff --check`; không cần chạy lại suite app khi không đổi hành vi. Dẫn nguồn validation cũ rõ ngày, không ghi thành kết quả mới.
10. Cập nhật 0→1→2→3 trước; sau đó README, NATIVE-TEMPLATE, runbook/parity và docs nghiệp vụ bị ảnh hưởng; append SECTION_PROGRESS. Không sửa lịch sử PASS thành claim rộng hơn.

## Git và bàn giao

- Không reset, checkout -- hoặc xóa công việc của agent/người dùng khác.
- Commit message nêu rõ phạm vi, ví dụ: docs: define Pema PB01 scope spec modules and architecture.
- Trước commit chạy git diff --check và xem git status; chỉ commit file thuộc mục tiêu hoặc evidence do test tạo.
- Push theo yêu cầu và xác minh remote/commit sau push.


## Skill thiết kế của dự án

Khi thiết kế, sửa hoặc review UI/UX Pema, đọc [pema-design](.agents/skills/pema-design/SKILL.md) và reference phù hợp. Hướng dẫn dùng/chia sẻ ở [docs/23_PEMA_DESIGN_SKILL.md](docs/23_PEMA_DESIGN_SKILL.md). Khi token, navigation hoặc capability đổi, cập nhật skill cùng docs, tránh để bản hướng dẫn lệch code. Skill không thay yêu cầu cụ thể của người dùng.

Khi đối chiếu web với design canvas claude.ai/design và bổ sung màn còn thiếu (chỉ thiết kế, không code .dart), làm theo [pema-web-to-canvas](.claude/skills/pema-web-to-canvas/SKILL.md); cập nhật `references/coverage.md` của skill sau mỗi lần chạy.

## Ghi nhận thay đổi web cho design canvas

Mỗi thay đổi **hiển thị** trên web Pema (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`) phải thêm một mục vào "Chờ chuyển" của [web-changes.md](.claude/skills/pema-web-to-canvas/web-changes.md) trong **cùng commit**: màn/tab/modal/dialog thêm hoặc xóa, trường/nút/bộ lọc/trạng thái đổi, luồng đổi, câu ràng buộc nghiệp vụ đổi, token CSS đổi. Ghi nơi sửa (file + selector/nút), thay đổi, mã màn canvas dự kiến (tra `references/coverage.md`, không chắc ghi "chưa rõ"). Refactor không đổi giao diện, test, seed dữ liệu và sửa lỗi không đổi hiển thị thì không cần ghi. Không tự sửa canvas trong lúc sửa web, trừ khi được yêu cầu; skill chuyển đổi đọc nhật ký này thay vì rà lại toàn bộ màn. Kiểm tra trước commit: `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` không còn file `✗ CHƯA GHI`.


## CRM01 và tài khoản demo

- Đọc bộ PB01 theo 0→1→2→3 và `docs/20_CRM01_PATIENT_LIFECYCLE.md` trước khi sửa. Nghiệp vụ CRM nằm ở crm-data/automation, UI không nhân bản rules.
- Không gộp màn owner/bác sĩ/CSKH/kế toán. `staff-context.js` phân workspace và command demo, không phải authentication. Bác sĩ chỉ vào hồ sơ phụ trách/được phân lịch; CSKH không duyệt y khoa, kế toán không làm clinical.
- Ngày demo 2026-09-20, idempotency rule+patient+source. Booking từ CRM phải cùng transaction với task/activity và đi qua validator lịch. Không tính reactivated từ booking; giữ task đã đóng khi rerun.
- Migration không viết lại lâm sàng/hóa đơn hiện có. Tám case CRM01 cũ chỉ dùng seed mới/reset; 10 tài khoản Mobile CRM02 được bổ sung một lần khi nâng dữ liệu, không ghi đè hồ sơ hiện có. Opt-out marketing không xóa việc theo dõi an toàn. CRM log nội bộ không tự công bố lên patient app; projection mobile lấy đúng identity người bệnh, không dùng selected của nhân viên.
- Chạy crm-test.cjs, crm-browser-test.cjs và suite regression liên quan; giữ kiểm lỗi save rollback, wrong patient, stale/duplicate task, quyền demo, prescription gating, 200-row pagination, 5 viewport. Khi kiểm output bị khóa file, dùng PEMA_EVIDENCE_DIR riêng; không đánh dấu PASS khi test chưa kết thúc.


## Mobile CRM02 và tài chính chung shell

Đọc [hướng dẫn hiện trạng](docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md). Finance phải mount/dispose trong Clinic, selector/CSS giới hạn workspace, không thêm role picker thứ hai. Seed thêm 10 hồ sơ một lần, giữ hồ sơ đã có và xử lý va chạm ID. Cập nhật bundle bằng `node prototype/export-native-patients.cjs`; chạy `--check`, mobile-crm-test.cjs và Flutter mobile_roles_test. Ghi chú nội bộ/bàn giao CSKH không được đưa vào updates dành cho Care.
