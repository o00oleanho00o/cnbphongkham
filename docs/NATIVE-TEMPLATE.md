# Pema • Native Flutter review 01

> **Hiện trạng Mobile CRM02 (22/09/2026):** tài chính trong Clinic shell, 46 hồ sơ mẫu/10 nhóm chăm sóc; Flutter phân workspace và tách state theo patient. Các mô tả state chung hoặc chưa có native CRM phía dưới là baseline trước bản mở rộng này. Xem [hướng dẫn cập nhật](25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).


## Bổ sung PB02 — tài chính dùng chung

Flutter Clinic đã có tổng quan chủ phòng khám, góc nhìn bác sĩ, kế toán ghi/duyệt/chốt lượt, cấu hình tỷ lệ, thu tiền và inbox qua API/SQLite cùng web. Mở từ Home/Thêm; Patient 360 có lối ghi lượt theo patient. Care không thấy tài chính phòng khám. [Chi tiết](24_FINANCE_AND_PROCEDURE_FEES.md). Những giới hạn memory-only/thu ngân/A5 phía dưới mô tả PB01; module PB02 là ngoại lệ mới, không phải thay thế toàn bộ PB01.


## Phạm vi duyệt

Chuyển các luồng web sang app Flutter với hai không gian Clinic/Care. Đây là template tương tác cần chủ sản phẩm duyệt trước phát triển native production. Bản preview chạy trên browser là Flutter thật, không phải trang HTML giả lập Flutter.

## Mapping màn hình

| Web | Native | Điều chỉnh cho điện thoại |
|---|---|---|
| Dashboard + Today | Hôm nay | Hero ngắn, hai số liệu chính, ba shortcut, lượt khám tiếp theo |
| Lịch ngày/tuần | Lịch hẹn → Chi tiết → Đặt/dời | Date strip, danh sách thời gian, date picker; không ép lịch nhiều cột |
| Patients + Patient 360 | Hồ sơ → Patient 360 → màn nghiệp vụ | Search, card nhận diện, điều hướng theo công việc |
| Consult / plan / session | Tư vấn / Kế hoạch / Buổi điều trị | Form riêng, validation trước hoàn tất |
| Catalog order | Lên đơn → Kiểm tra → Nháp/duyệt → Phiếu | Tìm sản phẩm, số lượng, hướng dẫn; loại thiếu chặn duyệt |
| Cashier | Thu ngân → sheet xác nhận | Khoản còn lại nổi bật; giao dịch mẫu có xác nhận |
| Follow-up Inbox | Theo dõi → Phản hồi | Một việc mỗi màn, feedback sau gửi |
| Resources/services | Thêm → danh sách chi tiết | Giữ dữ liệu ca, giá và duration; quản trị phức tạp vẫn ở web |
| Before/After | Ảnh tiến triển | Hai ô minh họa cùng ngữ cảnh, không efficacy score |
| Ask Pema | Ask Pema → Tư vấn | Tóm tắt mô phỏng từ số đếm; chưa có trích dẫn event, bác sĩ có màn sửa nội dung |
| Guide | Thêm → Hướng dẫn | Mạch bàn giao, không giáo trình demo |
| Patient home | Care Trang chủ | Chỉ bước tiếp theo, lịch và việc cần làm |
| Patient journey | Hành trình → kế hoạch/ảnh/aftercare | Nội dung chi tiết ở màn con |
| Patient messages | Tin nhắn → Gửi cập nhật | Consent khi đính ảnh mẫu; trạng thái chờ xem |
| Patient documents | Hồ sơ → Đơn/Hóa đơn | Chỉ chiếu đơn approved, không thấy draft |

## Token và hành vi native

- Font Be Vietnam Pro local: body 14–16, heading 25, label 12; tránh ép chữ vào chiều cao cố định.
- Primary #0B4F94, navy #083A6E, accent #3CAAE5, ink #17324D, muted #5D7184, paper #F4F8FB.
- Card 18px, hero 24px; spacing 4/8/12/16/20/24; icon Material outlined cùng trọng lượng cảm nhận.
- Bottom navigation 4 mục Care, 5 mục Clinic chủ, 2 mục công việc/hồ sơ cho bác sĩ/CSKH/kế toán; màn con dùng nút Back và giữ navigation stack.
- Thông tin quan trọng lên trước, một tác vụ chính trên mỗi màn; modal/bottom sheet chỉ chứa quyết định ngắn.
- Keyboard dùng Scaffold resize + scroll; SafeArea chống đè hệ thống; tap target tối thiểu Material 48 logical pixels.

## Checklist duyệt của chủ sản phẩm

- [ ] Nhận diện Pema và mật độ chữ đúng mong muốn.
- [ ] Hôm nay/Care home gọn, không trộn mọi module vào trang chủ.
- [ ] Patient 360 chia màn nghiệp vụ thuận tiện trên điện thoại.
- [ ] Lên đơn đủ mã/tên/giá/số lượng/cách dùng, nhóm thiếu loại dễ nhận ra.
- [ ] Bác sĩ hiểu rõ nháp khác duyệt; người bệnh chỉ nhận nội dung duyệt.
- [ ] Mạch gửi cập nhật → phản hồi có thể duyệt xuyên hai không gian.
- [ ] Sheet thu tiền rõ ràng, không nhầm trạng thái chăm sóc.

## Giới hạn

Các luồng tương tác chính dùng state phiên trong provider Riverpod (`lib/state/`); không sync web/backend. Scheduler chỉ minh họa slot và date picker, không copy engine xung đột web. Camera, media, AI, PDF/in, auth, privacy persistence chưa nối native plugin. Chỉ sau duyệt mới triển khai repository/API, permission, storage và thiết bị thật. Không gọi template này là ứng dụng production.

## Sơ đồ điều hướng và màn con

Clinic có Hôm nay / Lịch hẹn / Hồ sơ / Theo dõi / Thêm. Care có Trang chủ / Hành trình / Tin nhắn / Hồ sơ. Header mở sheet chọn Clinic hoặc Care; cùng instance dùng chung store. Màn con dùng Navigator stack; nút Back trở lại ngữ cảnh trước, không phải route HTML độc lập. Reload không giữ stack hay dữ liệu.

| Nhóm | Màn chi tiết | Nhiệm vụ / đích tiếp theo |
|---|---|---|
| Hồ sơ | Patient 360 | Chọn tác vụ tư vấn, kế hoạch, đơn, thu ngân từ cùng hồ sơ |
| Lịch | Đặt lịch, Chi tiết lịch, Lịch của tôi | Chọn/dời ngày giờ, xem hoặc xác nhận lịch mẫu |
| Điều trị | Tư vấn, Kế hoạch điều trị, Buổi điều trị | Nhập ghi chú, xem tiến độ, hoàn tất buổi có điều kiện |
| Chăm sóc | Chăm sóc tại nhà, Gửi cập nhật, Phản hồi | Xác nhận đã đọc, gửi text/consent ảnh mẫu, phản hồi |
| Đơn | Lên đơn nhanh, Kiểm tra đơn, Đơn thuốc & tư vấn, Phiếu A5 | Tìm catalog → chỉnh nháp → duyệt → xem nhóm approved |
| Tài chính | Hóa đơn, Thu ngân | Xem tổng mẫu từ đơn, xác nhận thu phần còn lại |
| Tra cứu | Dịch vụ, Bác sĩ & phòng | Xem thông tin minh họa phù hợp điện thoại |
| Bổ trợ | Ảnh tiến triển, Ask Pema, Quyền riêng tư, Hướng dẫn | Placeholder ảnh/AI/privacy và hướng dẫn bàn giao |

## Mạch sử dụng để duyệt

1. **Bắt đầu từ hồ sơ:** Clinic → Hồ sơ → chọn P001 → Patient 360. Mở tư vấn, lưu note; xem kế hoạch; nhập ghi chú và checkbox trước hoàn tất buổi. Kiểm đếm tăng nhưng không coi đây là session/event bền vững.
2. **Sắp lịch:** mở Lịch hẹn/Đặt lịch, chọn ngày/slot, xác nhận. 09:00 bị khóa để minh họa; chưa kiểm trùng bác sĩ/phòng. Lịch thay đổi trong PatientState của người đang chọn, không tạo booking backend.
3. **Lên đơn:** tìm mã hoặc tên đúng dấu, thêm sản phẩm; vào Kiểm tra đơn để chỉnh lượng/cách dùng/phân loại. Lưu nháp, chuyển Care kiểm tra nháp bị ẩn. Quay Clinic sửa và duyệt; Care → Hồ sơ → Đơn thuốc & tư vấn chỉ hiển thị approved. Phiếu A5 gom các đơn duyệt theo bệnh nhân thành hai nhóm, chưa in.
4. **Theo dõi:** Care → Gửi cập nhật, nhập text; nếu chọn ảnh mẫu phải đồng ý consent. Clinic → Theo dõi → Phản hồi; quay Care chọn đúng patient để xem phản hồi của mình. Ảnh không được lưu, task chưa có resolve/unread/SLA.
5. **Thu tiền:** mở Thu ngân, xem tổng và đã thu, xác nhận thu số còn lại. Không hoàn tất chăm sóc tự động. Đây là phép tính theo đơn kể cả nháp, chưa là hóa đơn/kế toán.

Đây là hướng dẫn đi qua hành vi hiện có, không phải biên bản đã kiểm thử đủ năm mạch. Xem [parity và validation](22_NATIVE_PARITY_AND_VALIDATION.md) để phân biệt bằng chứng và việc chờ duyệt.

## Tiêu chí thiết kế khi sửa tiếp

Giữ home ngắn và ưu tiên việc tiếp theo; nội dung dài đi vào màn con, không giới hạn chiều cao cứng để giấu overflow. Duyệt tên/ghi chú dài, nhiều dòng đơn, empty/error states, bàn phím và text scaling. Token nêu trên là baseline hiện tại; các mô tả teal/Manrope trong ghi chép UI cũ chỉ là lịch sử. Có SafeArea/Material widget không thay thế test OS/thiết bị.

Build/khôi phục preview: [21_NATIVE_RUNBOOK](21_NATIVE_RUNBOOK.md). Source và giới hạn state: [ARCH-PB01](ARCH-PB01.md). Checklist duyệt vẫn mở đến khi có kết quả cụ thể từ chủ sản phẩm.
