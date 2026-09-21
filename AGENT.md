# AGENT.md — Quy tắc làm việc cho Pema Digital Clinic

Áp dụng cho mọi thay đổi trong workspace Pema.

## Trước khi sửa

1. Đọc SCOPE-PB01, SPEC-PB01, MODULEMAP-PB01, ARCH-PB01 theo thứ tự.
2. Đọc domain/product/architecture docs liên quan và kiểm tra hành vi prototype trước khi suy ra yêu cầu.
3. Xác định thay đổi thuộc prototype hay pilot; không gọi là production nếu chưa có backend/security tương ứng.

## Sản phẩm và dữ liệu

- Chỉ dùng dữ liệu tổng hợp; không đưa hồ sơ, ảnh, số điện thoại hay token thật vào repo, fixture hoặc screenshot.
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

## Git

- Không reset, checkout -- hoặc xóa công việc của agent/người dùng khác.
- Commit message nêu rõ phạm vi, ví dụ: docs: define Pema PB01 scope spec modules and architecture.
- Trước commit chạy git diff --check và xem git status; chỉ commit file thuộc mục tiêu hoặc evidence do test tạo.
- Push theo yêu cầu và xác minh remote/commit sau push.
