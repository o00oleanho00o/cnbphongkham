# Pema Native • template duyệt thiết kế

Flutter Material 3 cho Android/iOS. Bản trình duyệt được build từ cùng Dart/widget tree để duyệt giao diện trước. Không dùng WebView bọc website.

## Chạy

```sh
flutter pub get
flutter run -d chrome
flutter test
flutter analyze
flutter build web --base-href /native-preview/
```

Android: `flutter run -d <device-id>` sau khi có Android SDK/emulator. iOS cần macOS/Xcode. Bản duyệt browser chưa thay thế kiểm thử bàn phím, camera, safe-area và gesture trên điện thoại thật.

## Hai không gian

- Clinic: Hôm nay / Lịch hẹn / Hồ sơ / Theo dõi / Thêm.
- Care: Trang chủ / Hành trình / Tin nhắn / Hồ sơ.
- Nút Clinic/Care ở header mở bottom sheet đổi không gian. Đây là bộ chuyển vai trò để duyệt, không phải xác thực.

## Mạch duyệt

1. Clinic → Hồ sơ → Patient 360 → check-in → tư vấn → kế hoạch → hoàn tất buổi.
2. Lịch hẹn → đặt/dời → chọn ngày/giờ → xác nhận. Slot 09:00 khóa minh họa xung đột; chưa phải scheduler đầy đủ.
3. Thêm → Lên đơn nhanh → tìm mã/tên trong 115 sản phẩm → kiểm tra đơn → số lượng/hướng dẫn/phân loại → nháp hoặc bác sĩ duyệt.
4. Care → Hồ sơ → Đơn thuốc & tư vấn: chỉ thấy đơn đã duyệt cho hồ sơ đang chọn.
5. Care → Gửi cập nhật → nội dung/ảnh mẫu/consent → Clinic Theo dõi → phản hồi → Care Tin nhắn.
6. Thu ngân → xem dư nợ theo đơn → xác nhận thu mẫu. Thu tiền không tự hoàn tất buổi.

## Tính nhất quán với web

Logo và font Be Vietnam Pro lấy từ assets hiện tại, kèm OFL. Primary #0B4F94, navy #083A6E, accent #3CAAE5, nền #F4F8FB. Giữ trạng thái draft/approved, phân loại PRESCRIPTION/CONSULTATION/UNRESOLVED từ catalog web; không phân loại thuốc theo tên.

Màn điện thoại dùng danh sách, màn con và bottom sheet. Patient 360 có các mục mở riêng thay vì bảng dày hoặc nhiều panel nối dài. Touch target theo Material; SafeArea, back navigation, date picker và form là widget native.

## Giới hạn vòng duyệt

State trong bộ nhớ của phiên template, chưa sync với localStorage web/backend. 36 hồ sơ tổng hợp minh họa; luồng lâm sàng/lịch/follow-up mặc định tập trung P001. Catalog sản phẩm là dữ liệu Excel được người dùng cung cấp, không phải dữ liệu sản phẩm giả lập.

Ảnh tiến triển/camera, AI, quyền riêng tư, cảnh báo nguồn lực và phiếu A5 là template. Chưa xuất PDF/in native, chưa gửi notification/payment thật, chưa RBAC, chưa lưu bền vững. Bố cục phiếu A5 để duyệt hai nhóm; không phải đầu ra in đã nghiệm thu.

Thiết kế chi tiết và mapping: [NATIVE-TEMPLATE.md](../docs/NATIVE-TEMPLATE.md).
