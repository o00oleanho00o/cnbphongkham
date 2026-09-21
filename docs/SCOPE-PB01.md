# Pema Digital Clinic — Scope PB01

Trạng thái: chốt cho prototype/pilot slice. Ngày: 2026-09-21.

Phương pháp: làm rõ boundary, giả định, quyết định và bằng chứng theo tài liệu PM AI Bootcamp; nội dung này chỉ mô tả sản phẩm Pema hiện tại.

## Vấn đề và mục tiêu

Phòng khám cần giữ một mạch chăm sóc từ tiếp nhận đến sau điều trị. Khi lịch, hồ sơ, buổi điều trị, ảnh, hướng dẫn, phản hồi và thu tiền rời nhau, nhân viên phải hỏi lại, bác sĩ thiếu bối cảnh và người bệnh không biết bước tiếp theo.

PB01 tạo vertical slice để lễ tân tìm đúng người bệnh, đội ngũ xử lý Patient 360, xếp lịch và buổi điều trị, gửi chăm sóc sau điều trị, nhận cập nhật từ Patient Mobile, theo dõi việc cần làm và đối soát dịch vụ/đơn thuốc/hóa đơn.

## Phạm vi trong PB01

### Clinic Web

- Dashboard và Today/Reception cho hàng đợi trong ngày.
- Tìm bệnh nhân, hồ sơ và Patient 360 với Tổng quan, Tư vấn, Kế hoạch, Buổi điều trị, Ảnh trước/sau.
- Điều phối lịch ngày/tuần, waitlist, bác sĩ, phòng, duration, buffer và xung đột.
- Danh mục dịch vụ và dịch vụ đã đăng ký: giá chốt, giảm giá, số buổi, tiến độ, bác sĩ phụ trách.
- Kế hoạch điều trị và ghi nhận buổi: trạng thái, ghi chú, aftercare, bước tiếp theo và ảnh có consent.
- Đơn thuốc nháp → bác sĩ duyệt → hiển thị có điều kiện trên Patient Mobile.
- Follow-up Inbox cho phản hồi/ảnh người bệnh, owner, severity và trạng thái.
- Thu ngân với hóa đơn chờ thu, tiền cọc, phân bổ cọc, thu một phần/toàn phần và chống thu trùng.
- Hướng dẫn trong hệ thống, liên kết theo hành trình và vai trò.

### Patient Mobile

- Trang chủ và hành động tiếp theo.
- Lịch hẹn, hành trình điều trị, aftercare, đơn thuốc đã duyệt, tài liệu/hóa đơn.
- Gửi cập nhật và ảnh với đồng ý sử dụng ảnh; xem trạng thái đã nhận/đang xem/đã phản hồi.
- Hồ sơ và tùy chọn riêng tư ở mức mô phỏng.

### Dữ liệu và bằng chứng

- 36 người bệnh tiếng Việt giả lập, có lịch, dịch vụ, liệu trình, phiên điều trị, follow-up, ảnh SVG/placeholder và hóa đơn mẫu.
- Cùng dataset qua localStorage để chứng minh liên thông hai app trên cùng origin.
- Kiểm thử flow, overflow desktop/mobile và screenshot evidence trong demo-assets.

## Ngoài phạm vi hoặc để pilot sau

- Đăng nhập thật, RBAC thật, tenant isolation và đồng bộ nhiều thiết bị.
- Backend/API production, backup, phục hồi, migration và audit bất biến.
- Thanh toán ngân hàng, thẻ, hoàn tiền, hóa đơn điện tử và kế toán đầy đủ.
- Kho, mua sắm, HR, lương, marketing automation và CRM đa chi nhánh.
- SMS/Zalo/push thật và đặt lịch tự phục vụ từ Patient Mobile.
- Media production, signed URL, retention và import hồ sơ thật.
- AI model thật, chẩn đoán tự động, chấm điểm hiệu quả hoặc đổi phác đồ không có bác sĩ duyệt.
- Native iOS/Android và triển khai sản xuất.

## Actor và trách nhiệm

| Actor | Trách nhiệm |
|---|---|
| Lễ tân/điều phối | Tìm hồ sơ, đặt/xác nhận/check-in lịch, waitlist và nguồn lực |
| Bác sĩ | Đọc Patient 360, ghi tư vấn, duyệt kế hoạch/đơn thuốc, phản hồi nội dung lâm sàng |
| Điều dưỡng/chăm sóc | Ghi buổi, gửi aftercare, xem follow-up và chuyển việc cần bác sĩ |
| Thu ngân | Đối soát hóa đơn, phân bổ cọc, thu tiền và kiểm tra dư nợ |
| Người bệnh | Xem hành trình, hướng dẫn, đơn đã duyệt và gửi cập nhật/ảnh |
| Quản lý | Xem tải vận hành, dữ liệu mẫu và bằng chứng kiểm thử |

## Giả định

1. PB01 là prototype nội bộ, dữ liệu không phải hồ sơ y tế thật.
2. Một patient có thể có nhiều episode/plan; tiến độ buổi chỉ tăng khi session hoàn tất.
3. Dịch vụ danh mục là giá tham khảo; dịch vụ gắn patient giữ giá chốt và snapshot giảm giá.
4. Đơn nháp không phải hướng dẫn đã phát hành; chỉ đơn được bác sĩ duyệt mới lên Patient Mobile.
5. Tiền cọc và lần thu sau là ledger entry riêng; không trừ ngầm hoặc ghi nhận hai lần.
6. Demo dùng cùng origin và browser profile; reset localStorage sẽ khôi phục fixture.

## Câu hỏi mở cho pilot

- Mô hình chi nhánh, timezone, ca làm và phân quyền cụ thể của Pema?
- Trường bắt buộc cho consent, ảnh, đơn thuốc và thời hạn lưu?
- Quy tắc hủy/no-show, hoàn cọc, chuyển gói và gia hạn liệu trình?
- Kênh thông báo và SLA phản hồi D1/D3/D7?
- Ai duyệt mẫu AI, aftercare và thay đổi protocol?
- Khi nào cần kế toán, payment gateway hoặc Zalo?

## Quyết định nền

- Patient 360 nối bối cảnh; event/record gốc vẫn là nguồn sự thật.
- Output AI/clinical draft có nguồn, trạng thái nháp và người duyệt.
- Ảnh phải có consent; ảnh từ mobile vào hàng chờ review trước khi dùng.
- Không suy diễn trạng thái điều trị từ thanh toán hoặc trạng thái đơn thuốc.
- Thay đổi scope cập nhật lần lượt Scope → Spec → Module Map → Architecture và ghi SECTION_PROGRESS.

## Definition of Done PB01

- Flow chính trong SPEC-PB01 chạy được trên dataset giả lập.
- Dịch vụ → liệu trình → lịch → buổi → follow-up → mobile có liên kết kiểm tra được.
- Đơn nháp bị ẩn trên mobile; đơn duyệt hiển thị kèm reviewer/time.
- Cọc, thu một phần/toàn phần, hóa đơn chờ và chống overpayment được kiểm tra.
- UI không tràn ngang ở 1920×1020, 1440×900, 1280×720, 1024×768 và 390×844.
- Smoke/operations/data audit không có page error; screenshot evidence được lưu.
- README, AGENT và docs downstream khớp hành vi quan sát được.

## Ranh giới prototype và pilot

Prototype dùng vanilla HTML/JS, localStorage, synthetic data và AI mô phỏng để trả lời câu hỏi luồng có dễ hiểu và vận hành thử không. Pilot cần identity/RBAC, API/backend, database, object storage, audit/backup, consent/retention, notification adapter, template được duyệt và SOP ngoại lệ. PASS prototype không phải chứng nhận sẵn sàng lâm sàng hay pháp lý.
