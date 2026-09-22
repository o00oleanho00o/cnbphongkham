# Màn hình và liên kết nghiệp vụ

## Mạch hệ thống

Đến phòng khám → định danh/hồ sơ → khám/tư vấn → kế hoạch/dịch vụ → lịch/buổi → hướng dẫn/đơn đã duyệt → theo dõi D1/D3/D7 theo kế hoạch → cập nhật/ảnh có consent → bác sĩ xem/phản hồi → lịch tiếp theo.

Đây là mô hình thiết kế, không có nghĩa mọi bước đã implement. Patient 360 tập hợp ngữ cảnh; event/record gốc mới là nguồn sự thật. Check-in không thay thế clinical visit; invoice không thay session; đã duyệt không đồng nghĩa đã cấp thuốc.

## Phân chia nền tảng

| Ngữ cảnh | Web | Flutter/mobile |
|---|---|---|
| Tổng quan | KPI có đường tới việc cần xử lý | Việc tiếp theo, lịch gần nhất, shortcut ngắn |
| Patient 360 | Bối cảnh + tab nội dung, tận dụng chiều ngang | Nhận diện gọn + mở từng màn nghiệp vụ |
| Điều phối | Lịch/tài nguyên/bộ lọc, bảng chi tiết | Danh sách ngày, chi tiết, date picker; không nhét lịch desktop |
| Đơn | Editor nhiều hàng và review/in riêng | Tìm → giỏ → kiểm tra → nháp/duyệt → tài liệu |
| Theo dõi | Hàng chờ và trạng thái bàn giao | Danh sách công việc → phản hồi riêng |
| Quản lý | Dịch vụ, bác sĩ/phòng, thu ngân | Tra cứu/tác vụ ngắn; quản trị phức tạp ưu tiên web |

Flutter Clinic: **Hôm nay / Lịch hẹn / Hồ sơ / Theo dõi / Thêm**. Care: **Trang chủ / Hành trình / Tin nhắn / Hồ sơ**. Không tăng tab chính chỉ vì thêm module; đặt tác vụ vào ngữ cảnh đúng. Switch Clinic/Care hiện là công cụ duyệt, không login.

Các màn con hiện có: Patient 360; Đặt lịch/Chi tiết lịch/Lịch của tôi; Tư vấn/Kế hoạch điều trị/Buổi điều trị; Chăm sóc tại nhà/Gửi cập nhật/Phản hồi; Lên đơn nhanh/Kiểm tra đơn/Đơn thuốc & tư vấn/Phiếu A5; Hóa đơn/Thu ngân; Dịch vụ/Bác sĩ & phòng; Ảnh tiến triển/Ask Pema/Quyền riêng tư/Hướng dẫn.

## Contract thiết kế cho mỗi tác vụ

- Ghi rõ patient và record liên quan trước mutation. Giữ lựa chọn khi chuyển màn/quay lại; không để dữ liệu từ người trước trông như thuộc người sau.
- Primary action diễn đạt kết quả (“Lưu nháp”, “Duyệt đơn”, “Gửi cập nhật”), không dùng “Xong” cho nhiều trạng thái khác nhau.
- Validation đặt gần trường lỗi, giữ nội dung đã nhập. Empty state chỉ ra bước tiếp theo; loading/error/success có ý nghĩa. Không dùng toast thành công nếu chưa có mutation thật.
- Xác định ai nhận kết quả, thấy ở đâu, điều kiện được thấy và hành động tiếp theo. Lưu trạng thái/quyền của record riêng với trạng thái UI.
- Hướng dẫn sử dụng phải giải thích liên kết/bàn giao và xử lý ngoại lệ, không chỉ script bấm nút demo.

## Luồng quan trọng

**Dịch vụ/điều trị:** catalog dịch vụ → giá và số buổi chốt → plan → appointment → session đủ thông tin → aftercare/follow-up → Care. Trong implementation đầy đủ cần đối chiếu invoice/plan nhưng không hoàn tất chăm sóc từ payment.

**Đơn:** catalog → số lượng/hướng dẫn → nháp → kiểm tra phân loại → bác sĩ duyệt → Care/phiếu. Nguồn sản phẩm là Excel được cung cấp; snapshot hiện tại 115 dòng (30 thuốc, 78 tư vấn, 7 UNRESOLVED). Không suy thuốc từ tên; thiếu loại/cách dùng phải được xử lý trước duyệt. Nháp không hiển thị như hướng dẫn cho người bệnh. Web có lý do override/NONE/in tách A5; không mặc định Flutter đã có.

**Ảnh/phản hồi:** nội dung → consent nếu có ảnh → gửi → hàng chờ review → phản hồi/resolve/escalate → Care. Tách consent, file, trạng thái task; nhãn “ảnh đính kèm” không thay việc lưu ảnh thật. AI là nháp có người review, không tự chẩn đoán/đóng việc.

**Thu ngân:** thể hiện tổng, đã thu, còn lại và chứng từ/trạng thái liên quan. Trong hệ thống đầy đủ cần ledger/cọc/thu từng phần/chống trùng; template hiện chưa đạt mức này.

## Ranh giới hiện tại phải kiểm trước khi sửa

Web Clinic/Patient Mobile dùng localStorage cùng origin/profile. Flutter độc lập, chỉ memory; order và receipt total theo patient, nhưng lịch/note/buổi/follow-up/cart còn dùng chung phiên. Flutter lịch 09:00 khóa cứng; A5 chỉ card nhóm approved orders; ảnh/AI/privacy mô phỏng; thu ngân còn tính cả nháp, không invoice entity/ledger. Không che các thiếu hụt bằng UI giống production.

Đọc `docs/22_NATIVE_PARITY_AND_VALIDATION.md` cho hiện trạng, `docs/20_CATALOG_ORDERS.md` cho web order/in, `docs/06_CLINIC_WORKFLOW.md` và PB01 cho contract hệ thống. Nếu được giao hoàn thiện nghiệp vụ, sửa nền dữ liệu và test cùng UI, rồi cập nhật ma trận; không cố giữ giới hạn template như yêu cầu vĩnh viễn.
