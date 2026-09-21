# Vòng thiết kế UI/UX — 21/09/2026

Phạm vi: prototype hiện hành trong `../prototype/`, không phải bản cũ trong package đầu vào.

## Vấn đề và thay đổi

| Trước | Sau |
|---|---|
| Georgia/Times ở tiêu đề, font mono chưa tải, chữ phụ nhỏ và kiểu chữ rời rạc | Manrope variable hỗ trợ tiếng Việt được lưu local; dùng một hệ font cho tiêu đề, bảng, số liệu và controls |
| Ký tự Unicode dùng làm icon, nét và baseline không đều | Lucide SVG 20px, stroke 1.7; icon trang trí có aria-hidden; nút chỉ có icon có tên truy cập |
| Sidebar tối chiếm thị giác, bóng đổ và khối xanh cạnh tranh | Sidebar sáng cùng nền; trắng cho hồ sơ; teal cho hành động, màu cảnh báo chỉ dùng theo trạng thái |
| Patient 360 thiếu một lớp tóm tắt nhanh | Tên người bệnh nổi bật, thanh tab dạng nhóm, hàng tóm tắt liệu trình / số buổi / lịch hẹn; timeline giữ nội dung chính |
| Home mobile lặp liệu trình và tiến độ, quá nhiều nội dung xếp dọc | Home chỉ giữ liệu trình, lịch hẹn, ba hành động chăm sóc / ảnh / gửi cập nhật |
| Hành trình in toàn bộ lịch sử và ảnh trên cùng trang | Ba sự kiện gần nhất; mở chi tiết bằng disclosure; tải thêm ba mốc; ảnh ở màn riêng |
| Thanh navigation đè lên trang dài | App shell theo chiều cao viewport, header và navigation riêng; vùng nội dung cuộn độc lập, có safe-area |
| Modal thiếu cơ chế bàn phím | Dialog có tên, focus trong hộp thoại, Tab giới hạn trong modal và Escape để đóng; nội dung nền inert |

## Quyết định thiết kế

Người dùng là bác sĩ chuẩn bị khám lại, lễ tân tiếp nhận và bệnh nhân đang chăm sóc tại nhà. Những yếu tố dẫn dắt thiết kế: liệu trình nhiều buổi, mốc ảnh, hồ sơ dài hạn, hướng dẫn đã duyệt, phản hồi cần xem và lịch hẹn tiếp theo.

Màu đến từ không gian phòng khám: giấy trắng, nền xám xanh nhẹ, teal của nhận diện, xanh nhạt của chăm sóc, màu đất cho cảnh báo. Điểm nhận diện là hành trình có các mốc buổi: xuất hiện trong Patient 360, tóm tắt liệu trình, progress, timeline và patient hero. Dùng neutral cho cấu trúc, màu đậm cho hành động chính; không đặt mọi vùng vào card nhấn màu.

Các giá trị được triển khai trong `prototype/shared/design.css`: font Manrope, body 14px, heading clinic 30px, patient 25px, radius card 14–16px, control 8–10px, spacing 4/8/12/16/20/24px. Lưu font và icon trong `prototype/shared/assets/` kèm license. App không tải CDN khi chạy.

## Kiểm tra

- `node prototype/smoke-final.cjs`: 12/12 checks, không console/page errors.
- `node prototype/patient-smoke.cjs`: Home → Journey → Photos → Send thành công, consent ban đầu chưa chọn.
- `node prototype/review-ui.cjs`: kiểm tra 8 màn patient ở 360×800, 390×844, 375×667; viewport clinic 1440, 1024, 768 và 390px. Kiểm tra font local, document overflow, vùng nội dung không chồng navigation, disclosure, lịch sử xem thêm và keyboard modal.
- Ảnh trước ở `demo-assets/screenshots/ui-refresh-before/`. Ảnh sau đúng kích thước viewport ở `demo-assets/screenshots/ui-refresh/`; kết quả máy đọc ở `review-results.json`.
- Đây là kiểm tra trình duyệt Chromium với kích thước điện thoại mô phỏng; chưa phải kiểm thử trên thiết bị iOS/Android vật lý hoặc với nhân viên Pema.

## Điểm cần tiếp tục khi pilot

- Chưa đồng bộ các route/filter vào URL, chưa kiểm tra toàn diện bằng screen reader.
- Cần xác minh bàn phím ảo và safe-area trên Safari iOS/Chrome Android thực tế.
- Bảng clinic giữ cuộn ngang có chủ ý trên điện thoại; Patient Mobile là trải nghiệm dành cho bệnh nhân.
- Dữ liệu giả lập, ảnh minh họa và AI mô phỏng vẫn giữ nhãn và giới hạn cũ.

## Tài liệu đã tham khảo

- [Interface Design — craft, hierarchy, density, system](https://github.com/Dammyjay93/interface-design/blob/main/.claude/skills/interface-design/SKILL.md)
- [Vercel Web Design Guidelines](https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md)
- [Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md)


## Vòng nhận diện Pema — 21/09/2026

- Đổi màu vận hành sang xanh Pema `#0B4F94`, xanh sáng `#3CAAE5`, nền trắng/xám xanh; màu đỏ/vàng chỉ giữ cho cảnh báo và trạng thái.
- Dùng logo chính thức Pema clinic & spa local tại `prototype/shared/assets/pema-logo.png` cho Clinic Web và Patient Mobile.
- Dùng Be Vietnam Pro local cho nội dung tiếng Việt, thay fallback Times/Georgia ở tiêu đề và controls.
- Thêm `prototype/shared/assets/care-waves.svg`: đường wave xanh nhẹ gợi Care Loop/Patient 360, chỉ nằm ở hero và vùng nhận diện để không làm rối dữ liệu lâm sàng.
- Patient Mobile giữ shell theo viewport, vùng nội dung cuộn riêng và 3 hành động ngắn ở Home; đã kiểm tra 360×800, 375×667 và 390×844 không tràn ngang.
- Sau vòng này: `smoke-final.cjs` 12/12, `patient-smoke.cjs` PASS, `data-audit.cjs` 20/20, `review-ui.cjs` 10/10, `capture-screens.cjs` không lỗi.


## Tối ưu bố cục theo ảnh phản hồi

Bỏ giới hạn chiều rộng ở workspace và bảng bệnh nhân, bổ sung bác sĩ/hẹn tiếp theo. Lịch dùng thống kê một hàng, header gọn, chiều cao vùng làm việc bám viewport. Trên desktop chỉ vùng lịch/danh sách cuộn, tiêu đề và bộ lọc đứng yên. CSS riêng tại `prototype/shared/workspace-layout.css`. Đã chụp và đo ở 2048×978, 1440×900, 1280×720; kết quả `demo-assets/screenshots/operations/layout-results.json`.
## Chuẩn desktop 1920×1020 — 21/09/2026

Clinic Web lấy viewport 1920×1020 CSS pixels ở zoom 100% làm chuẩn. Hướng dẫn tận dụng chiều ngang bằng cột thao tác và cột bàn giao; ảnh trước/sau mở rộng vùng làm việc; bác sĩ và dịch vụ dùng bốn cột trên màn rộng. Patient 360 cân đối cột hành trình và ngữ cảnh.

Đã chụp 80 trạng thái: 11 màn chính và 5 tab hồ sơ tại 1920, 1440, 1280, 1024, 390px; không tràn ngang toàn trang. Ảnh và kết quả: `demo-assets/screenshots/desktop-1920/`. Kiểm thử UI, vận hành và smoke đều đạt. Quy trình kiểm tra được ghi trong README và `prototype/review-desktop.cjs`.
