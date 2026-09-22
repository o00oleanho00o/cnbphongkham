---
name: pema-design
description: Thiết kế, triển khai và review UI/UX Pema Digital Clinic cho Clinic Web, Patient Mobile và template Flutter; áp dụng nhận diện Pema, luồng chăm sóc, responsive và kiểm chứng nghiệp vụ khi thêm hoặc sửa màn hình của dự án.
---

# Pema Design

Thiết kế để nhân viên tìm đúng bệnh nhân, hiểu việc cần làm và bàn giao được; người bệnh biết bước tiếp theo. Giữ nhận diện Pema và ngôn ngữ nghiệp vụ giữa web/native, điều chỉnh bố cục theo nền tảng. Skill này dùng cho dự án Pema, không áp phong cách này lên sản phẩm khác.

## Đọc theo công việc

- Thiết kế màu, chữ, icon, ảnh nền hoặc component: [visual-system](references/visual-system.md).
- Thêm màn, sửa navigation hoặc luồng nghiệp vụ: [screens-and-flows](references/screens-and-flows.md).
- Sửa bố cục desktop/mobile/Flutter: [platform-layout](references/platform-layout.md).
- Triển khai, kiểm thử và bàn giao: [delivery-and-review](references/delivery-and-review.md).

Các đường dẫn source trong references tính từ gốc repository, không từ thư mục skill. Skill nằm tại `.agents/skills/pema-design/`; hướng dẫn chia sẻ ở `docs/23_PEMA_DESIGN_SKILL.md`. Nếu chỉ có bản skill rời, dùng hướng dẫn thiết kế bên trong và yêu cầu source khi cần kiểm chứng implementation; không giả định các file dự án tồn tại.

## Những quyết định cần giữ

1. **Pema hiện tại là xanh/Be Vietnam Pro.** Logo Pema local; primary #0B4F94, navy #083A6E, sky #3CAAE5, nền #F4F8FB. Manrope/teal trong tài liệu cũ là lịch sử. Không tự đổi thương hiệu theo giao diện mẫu mới tìm được.
2. **Patient 360 là điểm nối bối cảnh.** Tác vụ liên quan phải giữ đúng patient/plan/order, thể hiện trạng thái và kết quả; menu hoặc card đẹp chưa chứng minh nghiệp vụ hoạt động.
3. **Desktop dùng được chiều ngang; mobile gọn theo công việc.** Chuẩn Clinic Web 1920×1020 CSS pixels ở zoom 100%; không khóa workspace trong cột hẹp. Mobile home chỉ tóm tắt việc tiếp theo; chi tiết mở màn con, không kéo dài vô tận.
4. **Giữ ý nghĩa, không sao chép bố cục.** Web dùng bảng/lịch tài nguyên; native dùng danh sách theo ngày, màn con và sheet ngắn. Flutter dùng widget Material 3, SafeArea và Navigator, không WebView bọc website.
5. **Tách dữ liệu, thiết kế và khả năng thực tế.** Nháp khác đã duyệt; thanh toán không phải hoàn tất điều trị. Web dùng localStorage; Flutter hiện memory-only và còn state chung theo phiên. Đọc ma trận parity trước khi mô tả tính năng native.
6. **Tham khảo có chọn lọc.** Pema.vn là tham chiếu nhận diện; ảnh Annam, Fastboy/Go Check In và repo thiết kế là gợi ý để đánh giá, không phải yêu cầu sao chép hoặc thêm feature. Vòng đời chăm sóc dẫn thiết kế; CRM/loyalty/marketing chỉ thêm khi nằm trong scope được giao.

## Cách thực hiện

Xác định người dùng, nền tảng, tác vụ chính, trạng thái đầu/cuối và source hiện tại. Đọc `AGENT.md`, bộ PB01 theo 0→1→2→3 và tài liệu liên quan; xem màn thực tế nếu công cụ cho phép. Chỉ hỏi khi thiếu quyết định ảnh hưởng đáng kể đến kết quả.

Khi người dùng yêu cầu phân tích/plan, trình bày phát hiện và phương án trước khi sửa. Khi đã yêu cầu triển khai, thực hiện đến kiểm tra và bàn giao trong scope; không dừng xin duyệt từng bước. Nếu nhiệm vụ là template để duyệt, giữ rõ các phần mô phỏng, không tự mở rộng sang backend production.

Với mỗi màn mới, xác định: điểm vào → ngữ cảnh → hành động chính → validation → trạng thái sau lưu → bên nhận bàn giao → đường quay lại. Chọn độ nổi bật bằng hierarchy và khoảng cách trước khi thêm màu/card/ảnh. Tận dụng component và asset hiện có.

Kiểm tra bằng dữ liệu có ý nghĩa và viewport phù hợp; xem screenshot lẫn tương tác. Báo rõ đã chạy gì, chưa chạy gì và giới hạn. Cập nhật Scope → Spec → Module Map → Architecture khi scope/hành vi đổi, rồi README, hướng dẫn và SECTION_PROGRESS. Skill hỗ trợ thực hiện công việc, không tự cấp quyền publish, gửi thông báo hay push Git ngoài yêu cầu người dùng.
