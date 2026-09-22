# AGENT.md — Quy tắc làm việc cho Pema Digital Clinic

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
5. DemoStore là memory-only, độc lập localStorage web. Chỉ order/receipt hiện tách patient; lịch/note/buổi/follow-up/cart còn dùng chung phiên. Khi sửa data model phải kiểm isolation và cập nhật ARCH/parity; không thêm flow nhiều bệnh nhân dựa trên giả định store đã cách ly đầy đủ.
6. Header Clinic/Care không phải RBAC. Phiếu A5 không phải PDF/in native. Checkbox ảnh không tạo file hoặc consent bền vững. Không ghi đã tích hợp các capability này chỉ vì có UI.
7. Khi Dart/assets thay đổi: `flutter analyze`, `flutter test --reporter expanded`, build preview; xem trực tiếp các màn bị ảnh hưởng. Review ở 360×800, 390×844, 430×932, 768×1024; suite hiện tại dùng height 844 ở cả bốn width. Không suy test tự động bằng test thiết bị.
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
