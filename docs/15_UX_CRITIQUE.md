# UX critique và vòng sửa

Reviewer: nhóm sản phẩm mô phỏng. Ngày: 20–21/09/2026. Vòng 1 được chạy thật bằng Chromium 1440×1000 và 390×844, ảnh lưu tại `demo-assets/screenshots/round-1/`; vòng final lưu tại `demo-assets/screenshots/final/`. Đây không phải kết quả usability test với Pema.

## Vòng 1: điều giữ lại

- Tông xanh trầm, nền sáng và khối hồ sơ làm Patient 360 có định danh rõ, không giống bảng ERP dày đặc.
- Dòng thời gian nối điều trị và phản hồi; cảnh báo da nhạy cảm xuất hiện ngay dưới tên người bệnh.
- Patient Home nói bằng ngôn ngữ người bệnh, có hành trình, lịch hẹn và chăm sóc, không thu nhỏ sidebar phòng khám.
- Ảnh minh họa tổng hợp có nhãn trực tiếp, tránh trình bày chúng như kết quả lâm sàng thật.

## Những lỗi phải sửa trước demo

| Mức | Quan sát từ code/runtime/ảnh | Hệ quả | Sửa yêu cầu |
|---|---|---|---|
| P1 | KPI 18 lịch/42 kế hoạch/3 chờ được gán cứng | Chủ phòng khám không kiểm tra được ý nghĩa số liệu | Tính từ dataset và truy được danh sách nguồn |
| P1 | Upload đọc file rồi bỏ dữ liệu ảnh | Bệnh nhân tưởng đã gửi ảnh nhưng bác sĩ không xem được | Lưu ảnh giả lập đã upload và hiển thị ở inbox đúng hồ sơ |
| P1 | Lưu buổi chỉ tăng completed và ghi timeline | Aftercare và session record không liên thông | Lưu session, ngày, nội dung, aftercare; tạo follow-up còn thiếu |
| P1 | Resolve follow-up chỉ đổi status | Không có phản hồi về patient app | Review từng mục, soạn phản hồi, lưu timeline + message |
| P1 | Nhiều nút filter/edit/document/privacy chưa có tác dụng | Mất tin cậy khi demo bằng click thật | Bind hành động hữu ích hoặc loại bỏ affordance giả |
| P1 | Draft AI chưa cho bác sĩ sửa trước khi duyệt | Review chỉ là nút hình thức | Cho sửa, duyệt và ghi dấu nguồn/actor |
| P2 | Ngày ảnh mốc gán cứng khác ngày buổi trên timeline | Khó biết đang so sánh mốc nào | Dùng metadata thật của demo, nhãn vùng/góc/consent |
| P2 | Cỡ chữ phụ nhỏ, card AI có vùng trống lớn | Khó đọc nhanh trong phòng khám | Tăng cỡ chữ tối thiểu và thu gọn khối phụ |
| P2 | Home mobile nhấn mạnh progress % | Có thể hiểu là % hiệu quả điều trị | Gắn nhãn rõ tiến độ số buổi, không là mức cải thiện da |

## Các câu hỏi reviewer đặt ra

- Bác sĩ thấy lần gần nhất, phản ứng và việc còn thiếu mà không phải mở nhiều menu?
- Lễ tân đổi trạng thái tiếp nhận tại chỗ, biết thiếu consent/ảnh?
- Bệnh nhân hiểu việc cần làm hôm nay và có thể gửi ảnh trong một flow?
- Sau khi bác sĩ phản hồi, cả hai phía có thấy cùng dữ liệu sau reload?
- UI có chỉ rõ đây là demo, AI mô phỏng, ảnh tổng hợp?

## Vòng 2: thay đổi và bằng chứng

- KPI, Today, Follow-up và Ask Pema đọc từ state; không còn số 18/42 gán cứng. Browser smoke kiểm tra trực tiếp 36 hồ sơ và kết quả Ask Pema.
- Reception có Check-in/Mời vào phòng; session kiểm tra ngày, consent, note, aftercare và chặn vượt số buổi.
- Ảnh được biến đổi kích thước, lưu vào follow-up/session với region/view/date; Before/After có lọc góc, side-by-side, slider/zoom, và nói rõ không tự căn chỉnh/không suy ra hiệu quả. Ảnh lỗi trong screenshot trước đã được xử lý bằng placeholder SVG và metadata tổng hợp.
- Follow-up mở review modal, cho bác sĩ sửa phản hồi, đóng mục và ghi message/timeline cùng hồ sơ. AI note/brief có bước sửa và duyệt.
- Mobile có điều hướng thay thế ở clinic, nút/nhãn bàn phím, focus ring, consent rõ, progress ghi “% số buổi… không phải tỷ lệ cải thiện da”. Scroll width bằng viewport ở 360, 390, 768 và clinic 390.

Kết quả: `prototype/smoke-final.cjs` đạt **12/12**, không console/page error; `prototype/data-audit.cjs` đạt **20/20**. Các ảnh final và manifest nằm trong `demo-assets/screenshots/final/`. Những điểm chưa giải quyết thuộc pilot production (auth/RBAC/server, tích hợp thật, clinical validation), không phải lỗi runtime của demo.
