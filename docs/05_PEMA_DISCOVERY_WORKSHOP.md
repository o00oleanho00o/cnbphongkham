# Pema discovery workshop — dùng trực tiếp tại clinic

## Cách chạy onsite (150 phút)

- **0–10 phút — setup:** xin consent quan sát/ghi chú; không chụp mặt hoặc export PII. Chuẩn bị stopwatch, giấy event map, bảng role/permission.
- **10–35 — reception shadow:** theo một ca check-in thật; bấm giờ từ patient tới trạng thái “sẵn sàng vào phòng”; ghi mọi app/giấy/Zalo và handoff.
- **35–70 — doctor + nurse shadow:** một ca quay lại và một treatment session; vẽ timeline từ chart/ảnh/thiết bị/aftercare; ghi trường thiếu và quyết định.
- **70–90 — customer care/follow-up:** dựng lại một ca patient hỏi sau treatment; đo từ inbound đến owner/reply; phân biệt urgent và routine.
- **90–110 — owner/cashier:** xem báo cáo tuần, package/payment/refund/consent; truy nguồn một KPI về artifact gốc.
- **110–135 — patient replay:** cho 2–3 bệnh nhân (không nhập dữ liệu thật vào demo) kể lại hành trình; usability test bản mobile synthetic.
- **135–150 — playback:** đọc lại 3 broken handoffs, chọn top 3 hypothesis, thống nhất cách đo pilot.

**Nguyên tắc:** hỏi “hãy chỉ cho tôi lần gần nhất”, không hỏi feature wish-list; ghi `observed`, `reported`, `inferred`; ẩn danh tất cả dữ liệu bệnh nhân.

## Owner/manager
- Báo cáo nào phải ghép tay mỗi tuần? Từ nguồn nào?
- Chỉ số nào khiến anh/chị gọi staff để hỏi lại?
- Khi patient phàn nàn, mất bao lâu để dựng lại diễn biến?
- Tỷ lệ không quay lại được ước tính thế nào?
- Quyết định nào cần biết trạng thái treatment chứ không chỉ doanh thu?
- Workflow nào khác giữa cơ sở/bác sĩ?

## Doctor
- Trước khi mở cửa phòng, cần 5 thông tin nào?
- Lần gần nhất phải lục ảnh/note ở đâu để so sánh?
- Điều gì làm note bị thiếu hoặc nhập sau ca?
- Khi bệnh nhân báo đỏ/rát, ai triage và dựa trên gì?
- Khi nào AI brief sai hoặc gây nguy hiểm?
- Bác sĩ muốn approve note/aftercare ở bước nào?

## Reception
- 5 phút trước giờ hẹn, kiểm tra gì?
- Một ca check-in cần bao nhiêu màn hình/click?
- Khi đổi lịch/no-show, dữ liệu nào phải nhập lại?
- Bệnh nhân thiếu consent/ảnh/thanh toán được xử lý ra sao?
- Việc nào hiện nhắn Zalo hoặc gọi điện vì phần mềm chậm?

## Nurse/assistant
- Protocol chụp ảnh gồm góc, ánh sáng, body area nào?
- Session kết thúc khi nào là “đủ”?
- Aftercare/medication gửi từ đâu và ai chịu trách nhiệm?
- Thiết bị/settings nào cần lưu?
- Dấu hiệu nào phải escalation cho bác sĩ?

## Customer care
- Theo dõi ai quá hạn bằng danh sách nào?
- Tin nhắn patient gửi vào kênh nào? Có mất ảnh không?
- Cách ghi nhận kết quả gọi lại và next action?
- Khi nào patient cần bác sĩ trả lời?

## Cashier/accounting
- Thu cọc/hoàn/đổi package liên quan session thế nào?
- Biên lai/invoice cần link với episode hay appointment?
- Dữ liệu nào được phép xem theo vai trò?

## Patient
- Sau treatment, mở kênh nào đầu tiên và cần biết gì?
- Hướng dẫn nào thường bị hỏi lại?
- Gửi ảnh có khó, ngại hoặc không rõ ai xem không?
- Điều gì làm bạn bỏ lỡ follow-up?
- Bạn muốn thấy progress theo buổi, ảnh hay cảm nhận?

## Đồ cần Pema chuẩn bị trước onsite

Một lịch ngày đã ẩn danh; treatment/procedure templates; photo protocol hiện tại; consent mẫu; package/price và refund mẫu; report tuần/tháng; danh sách role; 3 ca follow-up (đã giải quyết, quá hạn, escalation); sơ đồ Zalo/SMS/call; quy tắc lưu/xóa ảnh. Không gửi dữ liệu bệnh nhân qua chat cá nhân.

## Output bắt buộc
Service blueprint, event vocabulary, top 3 broken handoffs, photo protocol, follow-up SLA, role permissions, và baseline task time. Không chốt feature trước khi có artifact.
