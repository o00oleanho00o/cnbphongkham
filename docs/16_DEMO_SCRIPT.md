# Kịch bản demo 10 phút cho Dr. Tâm

Câu chuyện dùng hồ sơ tổng hợp **Nguyễn Minh Linh (P001)**. Dataset bắt đầu ở **2/5 buổi**; sau khi lưu buổi điều trị trong phần Clinic, hành trình thành **3/5**. Tất cả ngày trong UI là mốc demo cố định 20/09/2026.

## Chuẩn bị

1. Mở PowerShell tại `F:\BUL_Research\DalieuOs\prototype`.
2. Chạy `python -m http.server 4173 --bind 127.0.0.1`.
3. Mở Clinic Web và Patient Mobile trong cùng browser profile bằng đúng origin:
   - http://127.0.0.1:4173/clinic-web/
   - http://127.0.0.1:4173/patient-mobile/
4. Nếu dữ liệu đã bị thay đổi, bấm nút reset ở góc phải Clinic để về dataset demo. Không dùng `localhost`, `file://` hoặc browser profile khác vì hai app chỉ chia sẻ `localStorage` key `pema-demo-v2` trong cùng origin/profile.
5. Nếu muốn gửi ảnh, chọn một ảnh demo trong workspace (ví dụ `prototype/demo-update.png`). Ảnh này chỉ là synthetic/demo; UI sẽ yêu cầu consent trước khi gửi.

## Câu chuyện và thao tác

| Phút | Mở/click | Câu nói và giá trị |
|---:|---|---|
| 0:00–0:40 | Clinic Web → **Tổng quan** → `Xem lịch hôm nay` | “Tôi bắt đầu từ việc cần xử lý hôm nay.” KPI là số suy ra từ 46 hồ sơ giả lập khi seed mới và hàng đợi, không phải dashboard trang trí. |
| 0:40–1:30 | **Hôm nay** → bấm `Check-in` ở một dòng `Đặt hẹn` → chọn dòng đang chờ, chẳng hạn P001, rồi bấm `Mời vào phòng` | “Lễ tân chuyển trạng thái ngay trong hàng đợi; bác sĩ biết ai đã đến và ai đang được mời.” Các trạng thái tạo event reception trong timeline. |
| 1:30–2:20 | **Tìm bệnh nhân** → tìm `P001`/`Nguyễn Minh Linh` → `Mở →` | “Patient 360 trả lời ba câu hỏi: đã làm gì, phản hồi ra sao, bước tiếp theo là gì.” Cho thấy lúc đầu hồ sơ ở mốc **2/5**, cảnh báo, ảnh minh họa và chăm sóc tại nhà. |
| 2:20–3:20 | Tab **Tư vấn** → nhập vài ý vào `Ghi chú ngắn / transcript mô phỏng` → `Tạo bản nháp ghi chú` → sửa textarea `Bản nháp` → `Duyệt & lưu vào Patient 360` | “AI chỉ dựng bản nháp; bác sĩ sửa và duyệt trước khi ghi vào hồ sơ.” Đây là template deterministic từ event giả lập, không phải chẩn đoán. |
| 3:20–4:30 | Tab **Buổi điều trị** → nhập đánh giá và hướng dẫn chăm sóc → kiểm tra vùng/góc ảnh → `Lưu buổi điều trị` | “Một session hoàn tất phải kéo theo aftercare, event timeline và việc cần theo dõi.” Với P001, số buổi chuyển từ **2/5 → 3/5**. Nếu bỏ ảnh, demo cố ý tạo mục `Thiếu ảnh mốc đánh giá` để cho thấy missing-data detection. |
| 4:30–5:10 | Tab **Ảnh trước / sau** hoặc sidebar **Ảnh trước / sau** | “Studio lọc theo góc/vùng và hiển thị metadata.” SVG/placeholder có nhãn minh họa; ảnh upload demo là dữ liệu local đã thu nhỏ. Không nói đây là phần trăm cải thiện hay kết luận y khoa. |
| 5:10–6:10 | Cùng browser → Patient Mobile → **Trang chủ** → **Hành trình** → **Trang chủ** → **Chăm sóc** | “Sau khi rời phòng khám, bệnh nhân vẫn biết mình đang ở buổi nào và tối nay cần làm gì.” Cho thấy P001 **3/5**, medication, aftercare và nút xác nhận đã đọc. |
| 6:10–7:00 | Patient Mobile → `Gửi cập nhật →` → nhập triệu chứng → chọn ảnh demo (nếu dùng) → bật consent ảnh → `Gửi cho Pema` | “Ảnh/triệu chứng đi vào hàng đợi có người chịu trách nhiệm, không biến thành tin nhắn đã đọc vô chủ.” Patient Mobile chưa tự chọn slot mới; lịch đang có chỉ có thể xác nhận hoặc nhắn để yêu cầu đổi. |
| 7:00–8:00 | Quay Clinic → sidebar **Theo dõi** → mục `Ảnh cần bác sĩ xem` của P001 → `Mở` | “Bác sĩ thấy nội dung, ảnh và trạng thái review trong cùng queue.” Trong modal, sửa phản hồi nếu cần rồi bấm `Duyệt, phản hồi & đóng mục`. |
| 8:00–8:40 | Mở lại **Patient 360** P001 hoặc tab **Tin nhắn** ở Patient Mobile | “Phản hồi trở lại timeline và patient app; follow-up có owner, trạng thái và event.” Đây là localStorage đồng bộ trong cùng browser profile, không phải backend realtime. |
| 8:40–9:25 | Patient 360 → nút **AI brief** → sửa `Brief mô phỏng` → `Duyệt & lưu brief` | “Pre-visit brief có nguồn event và dấu bác sĩ duyệt.” Nội dung là template mô phỏng; không dùng như chỉ định hoặc chẩn đoán. |
| 9:25–10:00 | Sidebar **Ask Pema** → hỏi `Ai có ảnh gửi sau laser đang chờ xem?` → `Hỏi` → `Mở dữ liệu nguồn` | “Ask Pema trả lời từ bộ lọc dataset, hiển thị hồ sơ nguồn.” Đây là truy vấn deterministic, chưa tích hợp model AI thật. Kết thúc bằng câu hỏi: workflow nào cần shadow tại Pema trước pilot? |

## Điều cần nói rõ khi demo

- Tên, số điện thoại, timeline, ảnh và triệu chứng đều là **dữ liệu giả lập**.
- AI brief, clinical note draft và Ask Pema là **mô phỏng có review**, không chẩn đoán tự động.
- Ảnh SVG/placeholder không dùng để suy ra hiệu quả điều trị; consent và metadata thật cần được triển khai riêng.
- Patient Mobile hiện không có patient self-service booking/đổi slot trực tiếp; clinic tạo lịch, bệnh nhân xác nhận lịch có sẵn hoặc gửi tin nhắn yêu cầu hỗ trợ.
- localStorage chỉ dùng cho demo cùng origin/browser; không có authentication, server persistence, push notification, SMS/Zalo, e-invoice hay audit production.

## Bằng chứng smoke

Các kiểm tra runtime và screenshot được ghi trong [`demo-assets/screenshots/final/smoke-results.json`](../demo-assets/screenshots/final/smoke-results.json). Tài liệu này không mở rộng kết quả test ngoài những check có trong JSON đó; các bước như Before/After Studio và AI brief là hướng dẫn trình diễn UI, cần được đánh dấu riêng nếu chưa có check tương ứng trong artifact.


## Bổ sung: điều phối và quản lý vận hành
Xem [19_OPERATIONS_DEMO.md](19_OPERATIONS_DEMO.md) cho demo 5 phút: lịch ngày/tuần, kéo thả, phát hiện trùng, danh sách chờ, khóa phòng, sửa dịch vụ và thu tiền liên thông Patient Mobile.
