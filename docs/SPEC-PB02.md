# Spec PB02

- Owner D0 xem toàn phòng khám; accountant xem/cấu hình/duyệt/chốt/chi; doctor D0–D3 chỉ nhận dữ liệu cá nhân từ API, không toàn bộ khoản thu hay doanh số phòng khám. Vai trò demo bằng header, chưa bảo mật production.
- Lượt thủ thuật hoàn tất có patient, service, ngày thực hiện, giá niêm yết/giảm giá, invoice, người tham gia + tỷ trọng doanh số + tỷ lệ tiền thủ thuật snapshot. Thiếu người không được ghi; mỗi người chỉ một lần; tổng tỷ trọng 100, tổng tỷ lệ tiền không quá 100.
- Công thức: doanh số thực hiện = giá niêm yết − giảm giá; doanh số bác sĩ = doanh số × tỷ trọng; tiền thủ thuật = cơ sở × tỷ lệ, làm tròn VND từng dòng. Cơ sở có thể net/list/collected, mặc định net; collected phân bổ theo tỷ lệ đã thu của hóa đơn.
- Chờ duyệt → đã duyệt → chốt tháng → đã chi. Hủy trước chốt phải có lý do, giữ dấu vết; kỳ chốt không sửa tỷ lệ/số tiền snapshot. Không chốt còn dòng chờ duyệt. Không chốt tháng tương lai/chưa kết thúc; dữ liệu mẫu tháng trước để thử.
- Mỗi phiếu thu thành công tạo đúng một thông báo owner; retry cùng idempotency key không thu hai lần. Lỗi không thông báo thành công. Chỉ owner/accountant ghi tiền; doctor không nhận dữ liệu thu toàn phòng.
- Web thu ngân cũ chuyển ledger sang API qua đồng bộ có retry/idempotency; báo trạng thái khi chưa đồng bộ. Flutter nhận thông báo foreground qua polling. Không tuyên bố push OS đã có.
- Acceptance: kiểm tính tiền/giảm giá/chia người, tỷ lệ mới không đổi record cũ, duplicate payment, overpayment, quyền đọc/ghi, đóng kỳ và CSV, đồng bộ web → app, responsive và UI lỗi API.

Chốt theo thực thu yêu cầu thu đủ hóa đơn liên quan; chưa hỗ trợ chuyển phần tiền sang kỳ sau. Có thể gắn lượt vào invoice đã có, kiểm đúng patient và không phân bổ quá giá trị hóa đơn để tránh công nợ kép. UI tối đa 2 bác sĩ, API 4; chưa danh mục nhân sự kỹ thuật viên.
