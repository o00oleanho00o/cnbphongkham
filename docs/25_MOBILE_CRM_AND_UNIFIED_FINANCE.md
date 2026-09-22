# Mobile, tài khoản chăm sóc và tài chính trong Clinic

Cập nhật 22/09/2026. Phần này mở rộng CRM01 sang trải nghiệm mobile; các giới hạn native cũ về state chung được thay bằng mô hình theo người bệnh bên dưới.

## Tài chính là một phân hệ của Clinic

Vào **Clinic → Tài chính & tiền thủ thuật**. Sidebar, bộ chọn nhân viên, tìm bệnh nhân và đường quay lại dùng cùng khung Clinic. Trong nội dung có Tổng quan, Tiền thủ thuật, Chính sách tỷ lệ, Phiếu thu & thông báo. Không có bộ chọn vai trò tài chính thứ hai.

- Chủ phòng khám: toàn cảnh, đối soát, thông báo thu tiền.
- Kế toán: thu ngân, đối soát, tỷ lệ, chốt kỳ; không xem inbox riêng của chủ.
- Bác sĩ: mục **Doanh số của tôi**, dữ liệu cá nhân từ API, không có tab thu tiền toàn phòng khám.
- CSKH: không có mục tài chính. Link trực tiếp bị đưa về không gian được phép.

URL `/finance/?staff=accountant&patient=P037` vẫn dùng được: chuyển đến `/clinic-web/?screen=finance&staff=accountant&patient=P037`, mở bảng thủ thuật đúng bệnh nhân. Phân hệ vẫn dùng API :4174/SQLite; không đổi công thức hoặc trộn doanh số với thực thu. Mã hồ sơ API nhận P001–P999; dropdown lấy hồ sơ hiện có trong Clinic. Đây vẫn là actor mô phỏng, chưa đăng nhập thật.

`PemaFinance.mount(root)` giới hạn selector trong vùng tài chính; `dispose()` dừng polling, bỏ response lỗi thời khi chuyển màn/nhân viên. Không dùng iframe hoặc nhân bản bộ tính tiền.

## Thử đủ các nhóm CSKH

Mở **Patient Mobile → Hồ sơ → Nhóm tài khoản mẫu**. Chọn nhóm, sau đó về Trang chủ. Tài khoản là hồ sơ tổng hợp để duyệt trải nghiệm, không có mật khẩu hoặc xác thực thật.

| Hồ sơ mặc định | Nhóm | Việc trên mobile |
|---|---|---|
| P037 · Nguyễn Ánh Dương | D+1 | Gửi tình trạng sau điều trị |
| P038 · Trần Minh Châu | D+3 | Gửi cập nhật/ảnh có đồng ý |
| P039 · Lê Bảo Ngọc | D+7 | Gửi tiến triển để bác sĩ review |
| P040 · Phạm Gia Linh | Đến hạn | Xem lịch; liên hệ nếu chưa có lịch |
| P041 · Vũ Thanh Mai | Quá hạn | Nhắn nhu cầu sắp xếp tái khám |
| P042 · Đặng Hoàng Yến | Vắng hẹn | Hỗ trợ chọn lại lịch |
| P043 · Bùi Ngọc Hà | Còn buổi, gián đoạn | Trao đổi kế hoạch tiếp tục |
| P044 · Ngô Hải Anh | 90 ngày | Kết nối chăm sóc |
| P045 · Đỗ Thu Hương | 180 ngày | Trao đổi nhu cầu hiện tại |
| P046 · Hồ Khánh Chi | Sinh nhật | Lời chúc và tin nhắn |

Ngày chăm sóc mẫu cố định **20/09/2026**. Mỗi hồ sơ có task thật từ cùng CRM rules, không chỉ đổi nhãn UI; một hồ sơ có thể thuộc nhiều nhóm. Nhóm mẫu giúp kiểm từng tình huống, không thay điều kiện rule. Tài khoản được thêm một lần khi mở Clinic hoặc Mobile; không cần reset. Nếu ID đã tồn tại, bộ tạo chọn ID trống tiếp theo. Dữ liệu, ghi chú và lịch cũ không bị ghi đè. Fresh seed có 46 hồ sơ và 85 lịch, gồm một lịch vắng hẹn mới; lịch active hôm nay vẫn 31.

Trang chủ ưu tiên một bước tiếp theo, hành trình và lịch gần nhất; không lặp lại nhóm shortcut khi đã có việc ưu tiên. Không hiển thị nhãn rủi ro, ghi chú liên hệ hoặc activity nội bộ cho người bệnh. Identity Mobile riêng với selected của nhân viên. Nháp chưa duyệt vẫn bị ẩn; thu tiền không làm hoàn tất buổi điều trị.

## Flutter Clinic / Care

Ở header, mở bộ chọn không gian: Chủ phòng khám, Bác sĩ Tâm/Mai, CSKH Mai Anh, Kế toán, Người bệnh. Chủ giữ màn tổng quan; bác sĩ có công việc/hồ sơ phụ trách và doanh số cá nhân; CSKH có hàng đợi nhóm chăm sóc; kế toán có đối soát/thu ngân. Tài chính nhận vai trò từ workspace, không đổi sang chủ ngay trong màn tài chính. Chuông/nhắc thanh toán chỉ hiện cho chủ khi Clinic đang mở.

Care → Hồ sơ có bộ chọn 46 người bệnh và 10 nhóm tương ứng web. Tên/ID/case xuất từ fresh fixture bằng `node prototype/export-native-patients.cjs`; kiểm đồng nhất bằng `--check`. Đây là snapshot để duyệt, **không đồng bộ trạng thái CRM với browser web**.

Lịch, note, số buổi, xác nhận, aftercare acknowledgment, giỏ/đơn đang sửa, cập nhật, phản hồi, ghi chú CSKH và bàn giao được lưu riêng theo patient ID trong bộ nhớ. Care và Clinic nhớ người bệnh đang chọn riêng. CSKH lưu kết quả liên hệ nội bộ, mở form hỗ trợ đặt lịch hoặc chuyển bác sĩ; bàn giao vào hàng chờ bác sĩ và không xuất hiện như tin nhắn người bệnh. Chỉ phản hồi do bác sĩ gửi mới hiện ở Care.

Giới hạn: CRM Flutter là template với snapshot hàng đợi và trạng thái liên hệ trong phiên, chưa có rule engine động/idempotency task/SLA đầy đủ như web, chưa persistence/auth/sync clinical. Lịch vẫn chưa có engine xung đột thật. PB02 tài chính dùng API riêng, thông báo foreground; chưa FCM/APNs. Chưa kiểm Android/iOS thật, camera, bàn phím hệ thống hoặc in PDF native.

## Kiểm chứng

- `node prototype/mobile-crm-test.cjs`: link cũ/cùng shell, vai trò, 20 layout tài chính, 10 nhóm mobile, gửi đúng người bệnh, ẩn nội bộ, migration idempotent. [Kết quả và ảnh](../demo-assets/screenshots/mobile-crm02/results.json).
- `node prototype/crm-test.cjs`, `crm-browser-test.cjs`, `operations-test.cjs`, `review-desktop.cjs` và API finance regression.
- `flutter analyze`, `flutter test --reporter expanded`, build preview. Test mới ở `flutter-template/test/mobile_roles_test.dart`: 10 case/rules, state isolation và chuyển các vai trò ở 360/390/430/768 × 844.
- Nghiệm thu từng lượt chạy và giới hạn evidence ghi ở `SECTION_PROGRESS.md`; test viewport không thay kiểm thiết bị thật.


## Review bố cục CSKH trên điện thoại

Ảnh người dùng chỉ ra 10 chip chiếm gần nửa màn và đẩy công việc xuống dưới. Bản sửa dùng ba ô trạng thái có số lượng và lọc thật; tìm tên/mã cùng một hàng với nút Lọc. Mười nhóm chuyển vào sheet cuộn; màn chính chỉ giữ chip của nhóm đang chọn. Card khách có tên, lý do chăm sóc, mã và bác sĩ, mở chi tiết để ghi nhận. Ghi chú nội bộ không cần chiếm một banner lớn tại hàng đợi; hướng dẫn nằm ở tác vụ liên hệ. Nút lưu là hành động chính, đặt lịch/chuyển bác sĩ là hành động phụ.
