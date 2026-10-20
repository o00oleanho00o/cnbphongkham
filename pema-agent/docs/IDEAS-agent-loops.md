# Ý tưởng: các vòng lặp của agent và nhắc hẹn do CRM báo (ghi 2026-10-19, chưa làm)

Ghi lại từ buổi bàn với chủ về plugin `crm`. Thiết kế mục 2 đã được chọn và nằm trong `PLAN-crm-plugin.md` (mục 3.4-3.7);
cách agent hỏi CRM theo chu kỳ đã bị bỏ. Việc chưa làm: `HANDOFF-agent-v2.md` mục 13.

## 1. "Loop engineering": agent có mấy tầng vòng

Không phải thuật ngữ có định nghĩa chuẩn; ở đây hiểu là **thiết kế vòng chạy agent**: khi nào gọi model, gọi tool gì,
kiểm kết quả ra sao, khi nào dừng, khi nào chạy lại.

| Tầng | Trong code | Thiết kế vòng ở đây là |
|---|---|---|
| **Vòng trong: một lượt** | `run_turn`: model ↔ tool tới câu trả lời cuối | Số bước tối đa, loop guard, hook kiểm kết quả tool, nén lịch sử, dừng khi có câu trả lời, xem lại khi khách nhắn thêm lúc đang viết (steer) |
| **Vòng giữa: một cuộc chat** | `Dispatcher`: hàng đợi, khóa phiên, gom tin, chờ khi khách đang gõ | Khi nào bắt đầu một lượt, gộp tin, không chạy hai lượt cùng lúc cho một khách |
| **Vòng ngoài: agent tự hành động** | Vòng chăm sóc lại (`FollowUps`), nhắc hẹn | Kích hoạt, trạng thái, chống trùng, ngân sách, điều kiện dừng, công tắc tắt, người duyệt |
| **Vòng cải tiến** | Replay, bộ đánh giá (kiểu harness2) | Chạy lại hội thoại mẫu, chấm điểm, sửa prompt và tool, đo lại |

### Bảy câu mỗi vòng ngoài phải trả lời

1. **Kích hoạt:** cái gì đánh thức vòng (mốc giờ, sự kiện từ CRM, tin của khách)?
2. **Quan sát:** vòng đọc trạng thái nào trước khi làm (lịch còn hiệu lực không, khách đã trả lời chưa)?
3. **Hành động:** việc gì làm bằng code chắc chắn (giờ trong tin nhắc), việc gì để model làm (hiểu câu trả lời)?
4. **Kiểm:** làm xong có kiểm không (CRM trả trạng thái mới đúng chưa)?
5. **Dừng:** khi nào vòng kết thúc (đã xác nhận, đã hủy, đã qua giờ, hết số lần)?
6. **Giới hạn và tắt:** ngân sách, công tắc khẩn, dấu vết.
7. **Người trong vòng:** chỗ nào bắt buộc có nhân viên (hủy muộn, khách khó chịu)?

### Năm nguyên tắc chung (áp cho cả vòng chăm sóc lại đã có)

1. Mỗi vòng có **một nguồn kích hoạt** rõ ràng: mốc giờ hoặc tin của khách, không cả hai.
2. Có **khóa chống trùng** cho mỗi việc nó làm.
3. Có **điều kiện dừng**: số lần tối đa, trạng thái kết thúc.
4. Có **ngân sách**: hạn mức mỗi ngày, mỗi khách.
5. Có **công tắc tắt khẩn** và **dấu vết**: nhìn được vòng đã làm gì, vì sao.

Mỗi kế hoạch thêm vòng mới có mục "Vòng và cách chặn" điền đủ năm điều này, kèm một test cho mỗi cách chặn.

## 2. CRM báo lịch cho agent (thay cho agent hỏi định kỳ; đã chọn)

```
CRM: đặt/đổi/hủy/xác nhận lịch (có mối nối Zalo)
  → ghi sự kiện vào bảng outbox, cùng giao dịch với việc đổi lịch
  → worker gửi POST /v1/plugins/crm/events sang agent (ký HMAC như sự kiện của bridge Zalo), thử lại có giãn cách
Agent: nhận sự kiện → cập nhật bảng nhắc của mình → tính các mốc 24 giờ / 3 giờ
  → hẹn giờ tới mốc gần nhất → tới giờ thì gửi tin nhắc qua đường chủ động có sẵn
```

- **Outbox trong giao dịch:** đổi lịch xong mà agent đang tắt thì sự kiện vẫn còn, gửi lại sau. Bảng outbox là của CRM.
- **Sự kiện chỉ mang tối thiểu:** mã lịch, kênh, Zalo ID, giờ, trạng thái, `version`, ai đổi (`actor_type`). Không tên,
  không số điện thoại.
- **Agent không thăm dò CRM:** đồng hồ hẹn giờ ngủ tới mốc kế tiếp, thức sớm hơn khi sự kiện làm đổi mốc.
- **Một lần đối soát mỗi ngày** (hoặc khi agent khởi động): hỏi CRM "các lịch có mối nối trong 48 giờ tới" để vá sự
  kiện bị lỡ. Lưới an toàn, không phải thăm dò.
- **Luật:** thêm một chiều mới. CRM gửi sự kiện đã ký tới đúng một route của agent; route đó chỉ nhận, không trả dữ liệu
  gì về, kiểm chữ ký, chỉ mở trong mạng nội bộ.
- Chưa kiểm: CRM có worker chạy nền nào để gửi outbox chưa (có thể phải thêm một tiến trình).

## 3. Những vòng có thể tự quay và cách chặn

| Vòng | Ví dụ | Chặn bằng |
|---|---|---|
| **Vọng lại** | Agent xác nhận lịch → CRM báo "lịch đổi" → agent hẹn nhắc lại → nhắn khách lần nữa | Khóa "đã nhắc" là (mã lịch, giờ khám, mốc); chỉ đổi giờ khám mới tính lại mốc; sự kiện do agent gây ra (`actor_type = agent`) không sinh tin |
| **Trùng sự kiện** | Worker gửi lại vì mạng chập chờn | Mỗi sự kiện có mã; bỏ mã đã nhận, bỏ `version` cũ hơn bản đang giữ |
| **Bão thử lại** | Agent chết, CRM thử lại liên tục | Giãn cách tăng dần, tối đa N lần, rồi vào danh sách lỗi; đối soát hằng ngày bù lại |
| **Hai bot nói chuyện** | Zalo của khách có trả lời tự động, agent trả lời lại mãi | Giới hạn số lượt agent trả lời mỗi khách trong một giờ; tin nhắc chỉ sinh từ mốc giờ, không từ câu trả lời |
| **Hai vòng chồng nhau** | Vòng chăm sóc lại và vòng nhắc hẹn cùng nhắn một khách một ngày | Một hạn mức tin chủ động chung mỗi khách mỗi ngày; vòng chăm sóc lại bỏ qua khách có lịch sắp tới |
| **Nhắc người đã hủy** | Khách hủy 10:00, tin nhắc 11:00 vẫn chạy | Ngay trước khi gửi đọc lại trạng thái; đã hủy hoặc qua giờ thì bỏ |

## 4. Khách và lịch hẹn: các kịch bản (mức 3)

- **Khách hỏi lại lịch của mình:** tool không tham số, CRM trả lịch sắp tới của hồ sơ đã nối (giờ, thời lượng, trạng
  thái, ghi chú dịch vụ, mã lịch). An toàn vì mối nối chỉ do chính Zalo đó tạo hoặc nhân viên nối, và không gộp theo
  số điện thoại.
- **Nhắc hẹn:** mẫu câu cố định có giờ do code điền ("…nhắc lịch 14:00 hôm nay (29/10). Chị trả lời *đồng ý* để giữ
  lịch, hoặc nhắn nếu cần đổi giờ hay hủy"). Hỏi đồng ý nhận nhắc khi đặt lịch (Nghị định 91/2020, 13/2023).
- **Khách trả lời tin nhắc:**

| Khách | Agent làm |
|---|---|
| "ok", "đồng ý" | xác nhận: `booked` → `confirmed` |
| "đổi sang 16h" | xem giờ trống, khách chọn, dời lịch (giờ cũ trả lại) |
| "không đến được" | hỏi có muốn hẹn lại không, rồi hủy với lý do "khách hủy qua Zalo" |
| "ừ", không rõ | hỏi lại, không tự xác nhận |
| không trả lời | không nhắn thêm; (tùy chọn) vào danh sách "chưa xác nhận" để lễ tân gọi |

- **Hủy trong vòng 3 giờ:** agent hủy được nhưng nên báo lễ tân (việc `CrmTask` "khách hủy muộn"); chính sách hủy muộn
  (cọc, phí) nằm trong kho tri thức, agent chỉ trích dẫn.
- **Chặn:** khóa `version` khi lịch đổi giữa chừng; mã lịch của người khác trả 404; chỉ đụng lịch `booked`/`confirmed`
  chưa tới giờ; gửi Zalo thất bại thì vào danh sách "nhắc không tới".
- **Khách cũ đặt qua điện thoại, chưa từng chat:** khi khách lưu liên hệ trên Zalo mà số trùng hồ sơ cũ, CRM tạo **đề
  nghị nối** để nhân viên bấm duyệt (không gộp tự động). Zalo OA có nút trả lời nhanh cho tin nhắc: làm sau.
