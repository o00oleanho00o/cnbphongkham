# Pema Digital Clinic — Ultra Section

Workspace này chứa prototype tổng hợp và tài liệu nghiên cứu của Pema Digital Clinic. Dữ liệu trong demo hoàn toàn giả lập.

## Tiêu chuẩn hiển thị UI

- Clinic Web lấy **1920×1020 CSS pixels, zoom trình duyệt 100%** làm viewport desktop chuẩn để thiết kế và nghiệm thu. Đây là vùng nội dung trình duyệt, không phải độ phân giải màn hình gồm thanh công cụ.
- Vùng làm việc dùng chiều ngang khả dụng; tránh giới hạn cứng 920/1050px gây khoảng trắng lớn. Hướng dẫn chia nội dung và thông tin bàn giao thành hai cột ở màn rộng để giữ dòng chữ dễ đọc; bác sĩ/dịch vụ dùng bốn cột từ 1600px.
- Kiểm tra thêm 1440×900, 1280×720, 1024×768 và 390×844. Lịch và bảng dữ liệu có thể cuộn bên trong; toàn trang không được tràn ngang. Patient Mobile giữ bố cục dành cho điện thoại.
- Mỗi lần sửa bố cục, chạy `node prototype/review-desktop.cjs` khi server đang hoạt động. Script chụp 11 màn chính và 5 tab Patient 360 tại cả 5 kích thước; kết quả và ảnh ở `demo-assets/screenshots/desktop-1920/`. Xem ảnh để đánh giá bố cục bên cạnh kết quả tự động.

## Khởi động

Mở PowerShell tại `F:\BUL_Research\DalieuOs\prototype` và chạy:

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

Mở **cả hai URL trong cùng browser profile**:

- Clinic Web: [http://127.0.0.1:4173/clinic-web/](http://127.0.0.1:4173/clinic-web/)
- Patient Mobile: [http://127.0.0.1:4173/patient-mobile/](http://127.0.0.1:4173/patient-mobile/)

Hai app là vanilla HTML/JavaScript, không cần `npm install` hoặc bước build. Chúng dùng chung `localStorage` key `pema-demo-v2` khi chạy cùng **origin `http://127.0.0.1:4173` và cùng browser profile**. Không mở một app bằng `localhost`, file trực tiếp (`file://`) hoặc browser profile khác nếu muốn thấy thay đổi cross-app. Clinic có nút reset để khôi phục dataset tổng hợp.

Ảnh và sự kiện upload trong prototype chỉ phục vụ demo; ảnh được thu nhỏ và lưu trong localStorage. Không nạp dữ liệu bệnh nhân thật.

## Giới hạn demo cần nói rõ

AI brief, clinical note draft và Ask Pema là output mô phỏng/deterministic trên dataset giả lập; không gọi model AI thật và không chẩn đoán. Ảnh Before/After là SVG/placeholder tổng hợp hoặc ảnh upload của demo, không phải bằng chứng hiệu quả điều trị. Patient Mobile có thể xác nhận một lịch đã được clinic tạo và gửi yêu cầu qua tin nhắn; chưa có đặt slot tự phục vụ từ phía bệnh nhân. Không có authentication, server persistence, tenant isolation, push/SMS/Zalo thật hoặc audit production.

## Deliverables

- Product/domain docs: [`docs/`](docs/)
- Research sources và raw App Store RSS: [`research/`](research/)
- Prototype và demo data: [`prototype/`](prototype/)
- Screenshot evidence: [`demo-assets/screenshots/`](demo-assets/screenshots/)
- Smoke evidence: [`demo-assets/screenshots/final/smoke-results.json`](demo-assets/screenshots/final/smoke-results.json)
- Section progress: [`SECTION_PROGRESS.md`](SECTION_PROGRESS.md)

## Quản lý vận hành mở rộng

Mở [Điều phối lịch](http://127.0.0.1:4173/clinic-web/?screen=schedule), [Bác sĩ & phòng](http://127.0.0.1:4173/clinic-web/?screen=resources), [Dịch vụ](http://127.0.0.1:4173/clinic-web/?screen=services), [Thu ngân](http://127.0.0.1:4173/clinic-web/?screen=cashier). Dữ liệu mock và thao tác chi tiết trong [hướng dẫn demo](docs/19_OPERATIONS_DEMO.md). Chạy `node prototype/operations-test.cjs` để kiểm tra 20 tình huống vận hành.
