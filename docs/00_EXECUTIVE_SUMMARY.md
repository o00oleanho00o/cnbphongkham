# Pema Digital Clinic — tóm tắt điều hành

## Vì sao xây
Pema có cơ hội biến một quy trình điều trị da liễu nhiều buổi thành một hành trình liền mạch: nhân viên biết việc tiếp theo, bác sĩ thấy bối cảnh trong vài giây, còn bệnh nhân biết hôm nay cần làm gì. Wedge không phải thêm menu ERP; đó là **Patient 360 + Follow-up Inbox + Patient Mobile** dùng chung một timeline. Đây là sản phẩm cần pilot tại Pema trước, không phải kết luận thị trường đại trà.

## Vì sao phần mềm “đủ tính năng” vẫn thiếu
Các sản phẩm công khai hiện gộp lịch, thanh toán, hồ sơ, ảnh, portal và AI (xem [Aesthetic Record Clinical Solutions](https://www.aestheticrecord.com/features/clinical-solutions/) và [Pabau Features](https://pabau.com/features/)). Độ rộng không đảm bảo liên kết giữa phiên điều trị, ảnh đúng vùng, phản hồi tại nhà và việc cần người xử lý. Khi thông tin nằm ở chart, chat, album ảnh và bảng tính, nhân viên phải tự nối ngữ cảnh. Đây là giả thuyết cần kiểm chứng bằng workshop Pema, không phải kết luận về vendor.

## V1 nên gồm
Today/Reception, tìm bệnh nhân, Patient 360 timeline, consultation, treatment plan/session, bộ ảnh trước-sau có metadata/consent, Follow-up Inbox, patient mobile (lịch trình, aftercare, gửi ảnh), và AI có review/approve: pre-visit brief, note draft, timeline summary, missing-data/follow-up detection, Ask Pema đọc dữ liệu demo.

## Cố ý loại khỏi V1
Chẩn đoán tự động, định lượng hiệu quả từ ảnh placeholder, kế toán/ERP sâu, kho/HR, native app, microservices và tích hợp thanh toán trước khi hiểu workflow.

## Moat và rủi ro
Moat 1–3 năm là dataset dọc có cấu trúc (treatment session → ảnh chuẩn hóa → phản hồi → follow-up), cùng workflow đúng tại Pema. Rủi ro gồm adoption, consent/riêng tư, bias ảnh, AI hallucination, và “dashboard đẹp nhưng không giúp thao tác”. Cần đo thời gian tiếp nhận, tỷ lệ follow-up đúng hạn, ảnh bị thiếu metadata và số lần nhân viên rời hệ thống.

## Demo cho Dr. Tâm
Kể câu chuyện một bệnh nhân nám đang buổi 3/5: Reception → Patient 360 → treatment/session + ảnh → chuyển sang app xem aftercare → bệnh nhân gửi ảnh → Follow-up Inbox → bác sĩ approve AI brief và đặt bước tiếp theo.

## 12 câu hỏi bắt buộc

1. **Vì sao xây?** Vì khoảng cách giữa một session và lần follow-up tạo rủi ro vận hành, trải nghiệm và dữ liệu; Pema có môi trường thật để đo.
2. **Vì sao hệ thống hiện tại chưa đủ?** Public evidence cho thấy feature breadth cao, nhưng review App Store vẫn nêu chart chậm/disjointed, mobile parity, login và crash; module không tự tạo context continuity.
3. **Wedge mạnh nhất?** Patient 360 + photo protocol + Follow-up Inbox + patient app cùng một event timeline.
4. **V1 gồm gì?** Today, Patient 360, treatment plan/session, photos, follow-up, patient mobile và practical AI review-first.
5. **Loại gì?** Autonomous diagnosis, ERP sâu, native app, production integrations và KPI vô nghĩa.
6. **Patient 360 quan trọng vì sao?** Doctor cần trả lời “đã làm gì, đáp ứng ra sao, tiếp theo là gì” trong vài giây.
7. **Patient app quan trọng vì sao?** Outcome và adherence xảy ra sau khi rời clinic; aftercare, update và reminder là một phần care loop.
8. **AI thực dụng ngay?** Pre-visit brief, note draft, timeline summary, rule-based missing/follow-up detection và evidence-based Ask Pema.
9. **Moat 1–3 năm?** Dataset dọc có protocol: session, vùng/góc ảnh, phản hồi, follow-up và outcome được consent/audit.
10. **Phải học gì từ Pema?** Event vocabulary, role handoff, protocol thực tế, SLA, exceptions, adoption friction, consent và chỉ số baseline.
11. **Rủi ro lớn?** Staff bypass, consent/privacy, ảnh không chuẩn, AI over-trust, tích hợp local, dữ liệu synthetic không đại diện và scope creep.
12. **Demo gì trước Dr. Tâm?** Một ca nám “Nguyễn Minh Linh” từ Today → 360 → session/photo → app aftercare → patient update → Inbox → AI brief có nguồn.
