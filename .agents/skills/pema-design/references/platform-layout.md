# Bố cục theo nền tảng

## Clinic Web

Chuẩn 1920×1020 CSS pixels, zoom 100% (viewport nội dung, không phải toàn màn hình máy). Dùng chiều ngang khả dụng; không max-width 920/1050px cho toàn workspace. Tách cột ngữ cảnh và nội dung, giữ độ dài dòng văn bản vừa đọc thay vì kéo mọi paragraph hết màn.

Lịch: header/bộ lọc gọn, thống kê một hàng khi đủ chỗ, vùng tài nguyên theo chiều cao khả dụng. Bảng/lịch có thể cuộn bên trong; document không tràn ngang. Patient 360 cân đối timeline/ngữ cảnh; hướng dẫn có cột thao tác/bàn giao; dịch vụ/bác sĩ có thể 4 cột từ 1600px như layout đang có. Đây là pattern để chọn theo nội dung, không ép mọi màn thành grid 4 cột.

Kiểm thêm 1440×900, 1280×720, 1024×768, 390×844. Ở màn nhỏ ưu tiên thông tin/action thiết yếu, disclosure/filter gọn và scroll container rõ. Không thu font toàn trang hoặc ẩn controls nghiệp vụ để chữa overflow.

## Patient Mobile web

App shell theo viewport, header/navigation và nội dung cuộn không chồng nhau; chừa safe area dưới. Home cho lịch gần nhất, bước chăm sóc tiếp theo và vài shortcut; lịch sử đầy đủ ở Hành trình/màn con. Progressive disclosure/tải thêm dùng khi cần, không dựng toàn bộ timeline/ảnh/đơn nối dọc ở home.

Mốc review hiện có 360×800, 375×667, 390×844. Kiểm thao tác khi bàn phím mở và nội dung dài; browser resize không thay bằng chứng thiết bị thật.

## Flutter native template

Material 3, SafeArea, Navigator/Back, date picker, scrollable form; sheet dành cho quyết định ngắn. Màn form dài hoặc review nhiều dòng có màn riêng. Giữ dữ liệu khi validation lỗi; bàn phím không che CTA/trường đang nhập. Giữ touch target 48 logical pixels và kiểm text scaling; không fixed height khiến tiếng Việt bị cắt.

Review shell hỗ trợ 360×800, 390×844, 430×932, 768×1024. Widget tests hiện tại widths 360/390/430/768 **đều height 844**, không chứng minh toàn bộ các khung trên đã được kiểm. Android/iOS physical device, safe area hệ thống, keyboard, gesture và accessibility phải có evidence riêng khi scope yêu cầu.

Tablet có thể tăng cột/độ rộng hợp lý nhưng không biến thành desktop dashboard thu nhỏ. Không cố giữ một số lượng card cố định nếu chữ/dữ liệu dài làm mất khả năng thao tác.

## Review screenshot có mục tiêu

Kiểm lần lượt: định vị người bệnh/tác vụ → thứ bậc nội dung → khoảng cách/alignment → chữ/icon/contrast → chiều dài/scroll → trạng thái/navigation/CTA. Chụp trước/sau cùng viewport và state khi so sánh. Mỗi nhận xét cần chỉ ra vấn đề, ảnh hưởng thao tác và cách sửa; tránh nhận xét chung “chưa hiện đại”. Sau sửa test cả click/validation, không chỉ chụp màn rỗng đẹp.
