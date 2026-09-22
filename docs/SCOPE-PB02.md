# Scope PB02 — Tài chính chủ phòng khám và tiền thủ thuật

BS. Tâm vừa là bác sĩ vừa là chủ phòng khám. Chủ xem tổng hợp doanh số thực hiện, thực thu, công nợ, tiền thủ thuật; kế toán cấu hình tỷ lệ, đối soát người thực hiện và chốt tháng; bác sĩ chỉ xem phần của mình. Clinic Web và Flutter Clinic dùng chung API cục bộ. Care không nhận thông báo tiền của phòng khám.

Giả định chờ xác nhận: cơ sở tính mặc định là giá thực hiện sau giảm giá; mỗi thủ thuật có tỷ lệ riêng; hỗ trợ nhiều người với tỷ lệ riêng tính trực tiếp trên cùng cơ sở, tổng không vượt 100%. Doanh số phân bổ cho bác sĩ theo tỷ trọng tham gia, tổng tỷ trọng 100%; tiền thủ thuật không phải doanh số. Có thể cấu hình cơ sở thực thu hoặc niêm yết cho lượt mới. Không tự gán người thực hiện từ bác sĩ phụ trách hồ sơ.

Trong scope: dashboard tháng, ghi lượt hoàn tất/người tham gia, snapshot chính sách, duyệt, hủy có lý do trước chốt, đóng kỳ/đánh dấu đã chi, CSV đối soát, phiếu thu và thông báo trong app. Kỳ chốt khóa dữ liệu. Ngoài scope: kế toán pháp định, thuế/lương đầy đủ, bank webhook, production identity, push OS/background. Dữ liệu minh họa, role switch demo.


## Mobile và Clinic shell — 22/09/2026

Đồng bộ mobile và điều hướng: tài chính mở trong Clinic shell; URL cũ chuyển tới cùng workspace. Thêm 10 hồ sơ tổng hợp P037–P046 theo 10 nhóm CSKH, bổ sung một lần và không sửa 36 hồ sơ hiện có. Patient Mobile dùng bước tiếp theo theo rule, không lộ ghi chú nội bộ. Flutter bổ sung phân vai demo, chọn bệnh nhân theo tình huống và tách state theo patient; CRM native vẫn là template độc lập, không sync localStorage.
