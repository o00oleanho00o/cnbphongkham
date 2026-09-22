# Kiểm thử theo vai trò và tình huống

Ngày thực hiện: 20/09/2026. Toàn bộ hồ sơ là dữ liệu giả lập. Đây là mô phỏng bởi nhóm sản phẩm, chưa phải usability test với nhân viên/bệnh nhân Pema.

## Tiêu chí quan sát

Mỗi vai trò cần tìm thấy việc tiếp theo, biết bệnh nhân nào đang thao tác, và kiểm tra được kết quả sau khi lưu. Các bước bên dưới sẽ được chạy trên trình duyệt; kết quả và bằng chứng sẽ được bổ sung sau runtime test.

| Vai trò | Tình huống cần hoàn thành | Dấu hiệu thành công | Rủi ro cần quan sát |
|---|---|---|---|
| Chủ phòng khám | Xem công việc đang chờ và bệnh nhân quá hạn | KPI truy được về hồ sơ trong dataset | Số liệu trang trí, không có hành động tiếp theo |
| Bác sĩ da liễu | Chuẩn bị khám lại một bệnh nhân nhiều buổi | Đọc được vấn đề, buổi gần nhất, phản ứng, ảnh và bước kế tiếp | AI nói chắc chắn về dữ liệu thiếu; timeline rời rạc |
| Điều dưỡng | Ghi nhận buổi điều trị và hướng dẫn về nhà | Nội dung đã lưu xuất hiện ở Patient Mobile | Không rõ đang thao tác trên đúng hồ sơ hay chưa |
| Lễ tân | Tìm bệnh nhân và tiếp nhận từ danh sách hôm nay | Trạng thái đổi, tiếp cận được Patient 360 | Click nhiều, không thấy thiếu consent/ảnh |
| Chăm sóc khách hàng | Nhận ảnh cập nhật, chuyển bác sĩ và phản hồi | Follow-up hết trạng thái chờ và phản hồi xuất hiện ở app | Đánh dấu đã xử lý nhưng bệnh nhân không nhận câu trả lời |
| Thu ngân | Xem ngữ cảnh thanh toán của lần khám | Xem được chứng từ minh họa gắn đúng bệnh nhân | Nhầm prototype với sổ kế toán hoặc hóa đơn pháp lý |

## Năm tình huống bệnh nhân

1. **Bệnh nhân mới:** mở Home, xác định lịch hẹn sắp tới và xem thông tin cá nhân. Không yêu cầu hiểu thuật ngữ quản trị.
2. **Bệnh nhân điều trị nhiều tháng:** mở hành trình, xác định buổi đã hoàn tất và bước kế tiếp; so sánh hai mốc ảnh cùng vùng da.
3. **Bệnh nhân vừa điều trị:** đọc aftercare và chăm sóc tại nhà, tìm cách liên hệ phòng khám khi lo lắng.
4. **Bệnh nhân cần theo dõi:** gửi nội dung và ảnh giả lập; thấy xác nhận gửi và phản hồi sau khi phòng khám review.
5. **Bệnh nhân lâu chưa quay lại:** xem lịch, đặt/yêu cầu hẹn mới và kiểm tra trạng thái đã lưu; không hiểu nhầm yêu cầu thành lịch được xác nhận nếu chưa có xác nhận của phòng khám.

## Sáu flow bắt buộc

| Flow | Hành động | Bằng chứng cần lưu |
|---|---|---|
| 1 | Today → tiếp nhận → hồ sơ → bác sĩ | Trạng thái tiếp nhận và đúng hồ sơ |
| 2 | Patient 360 → timeline → liệu trình → ảnh | Dữ liệu một bệnh nhân nhất quán |
| 3 | Hoàn tất buổi điều trị → aftercare → Patient Mobile | Nội dung mới tồn tại sau reload và ở tab bệnh nhân |
| 4 | Bệnh nhân gửi cập nhật → inbox → review → timeline/phản hồi | Kết quả đồng bộ giữa hai tab |
| 5 | Tạo pre-visit brief | Nguồn dữ liệu rõ; không tự chẩn đoán |
| 6 | Ask Pema | Kết quả khớp dataset, có hồ sơ làm căn cứ |

## Kiểm tra phụ

- Không lỗi console/runtime, request 404, ảnh hỏng hoặc route trắng.
- Không tràn ngang ở kích thước desktop và điện thoại 390px/360px.
- Tìm kiếm không có kết quả có empty state; input rỗng không tạo bản ghi vô nghĩa.
- Nội dung người dùng nhập hiển thị như văn bản; upload chỉ chấp nhận ảnh và có giới hạn.
- Dữ liệu vẫn tồn tại sau reload; thay đổi ở tab này cập nhật tab kia.
- Các action quan trọng thay đổi trạng thái thật; không có nút chỉ để trang trí.

## Kết quả thực thi

## Kết quả runtime

Chromium smoke đã thực thi các thao tác chính trên dữ liệu giả lập. `prototype/smoke-final.cjs` ghi 12/12 PASS, không có console/page error: reception check-in, treatment + aftercare, follow-up review/reply, AI note review, Ask Pema, patient gửi text + ảnh, clinic nhận follow-up và mobile không tràn ngang. Các persona còn lại là kịch bản cần chạy với nhân viên/bệnh nhân Pema trong discovery workshop; không suy diễn đây là bằng chứng usability ngoài nhóm mô phỏng.


## Bổ sung Flutter template — 22/09/2026

Các kết quả web phía trên giữ nguyên phạm vi và ngày kiểm tra. Bằng chứng Flutter trước lần cập nhật tài liệu: analyze sạch, 6 test (1 store, 4 layout widths 360/390/430/768 đều height 844, 1 tương tác catalog → review), build web thành công. Visual review chỉ Clinic home, role sheet, Care home 390×844. Chưa có test đầy đủ Care/end-to-end/device. Chi tiết [VALIDATION](../flutter-template/VALIDATION.md) và [coverage/checklist](22_NATIVE_PARITY_AND_VALIDATION.md). Lần sửa tài liệu này không chạy lại suite Flutter.


## Mobile CRM02 — bằng chứng mới 22/09/2026

Đã chạy analyze, 17 test Flutter và build preview; browser native kiểm bốn khung 360×800, 390×844, 430×932, 768×1024 và luồng lọc D3 → P038 → lưu liên hệ → Đã liên hệ. Đây là kiểm thử kỹ thuật, chưa thử với nhân viên thật hoặc thiết bị Android/iOS. [Báo cáo mới](../demo-assets/screenshots/mobile-crm02/validation-summary.json); các kết quả cũ ở trên giữ nguyên theo phạm vi lúc chạy.
