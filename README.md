# Pema Digital Clinic — Ultra Section

## Template Flutter để duyệt

Mở [Native review](http://127.0.0.1:4173/native-review/) để xem Flutter trong khung điện thoại 360/390/430px và tablet. Chuyển Clinic/Care ở header để duyệt hai không gian; mã nguồn và cách build ở [flutter-template](flutter-template/README.md), mapping màn hình ở [Native template](docs/NATIVE-TEMPLATE.md). Đây là template tương tác dùng state trong phiên, chưa kết nối backend/camera/in native. Chạy server prototype như bên dưới; nếu chưa có preview, build theo hướng dẫn Flutter rồi copy `flutter-template/build/web/` sang `prototype/native-preview/`.

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

Patient 360 hiện liên kết dịch vụ đã đăng ký với số buổi, giá chốt, giảm giá và hóa đơn chờ thu. Đơn thuốc đi qua trạng thái nháp và bác sĩ duyệt; Patient Mobile chỉ hiển thị đơn đã duyệt. Tiền cọc được ghi trong sổ phân bổ riêng để không tính trùng khi thu phần còn lại. Chạy `node prototype/check-linked.cjs` để kiểm tra luồng dịch vụ, đơn thuốc, hóa đơn và mobile.

## Lên đơn từ Excel và in tách phiếu

Vào **Thu ngân → Lên đơn nhanh** hoặc **Patient 360 → Tạo đơn nháp**. Tìm sản phẩm bằng mã/tên không dấu, nhập số lượng và cách dùng, lưu nháp rồi kiểm tra hai phiếu. Bác sĩ duyệt để mở các nút **In đơn thuốc / In phiếu tư vấn / In tất cả** và hiển thị hai nhóm trên Patient Mobile. Mở lại hoặc sửa nháp từ danh sách đơn ở Thu ngân/Patient 360.

Nguồn thực tế: `F:\BUL_Research\DalieuOs\data\danhsach.xlsx` (đường dẫn `F:\BUL\_Research\...` trong yêu cầu không tồn tại). 115 sản phẩm gồm **30 thuốc, 78 sản phẩm tư vấn, 7 thiếu loại**. Dòng thiếu loại cần chọn thủ công và ghi lý do trước khi duyệt. Chọn “Không in” vẫn tính sản phẩm trong hóa đơn.

Tái tạo dữ liệu sau khi cập nhật Excel: `python prototype/import-product-catalog.py`; kiểm tra đồng nhất: `python prototype/import-product-catalog.py --check`. Có thể truyền đường dẫn XLSX khác làm đối số. Không cần cài thêm thư viện để import.

Kiểm thử mới: `node prototype/product-catalog-test.cjs`, `node prototype/order-test.cjs`, `python prototype/order-pdf-test.py` (bước kiểm PDF cần `pymupdf`). [Hướng dẫn và giới hạn](docs/20_CATALOG_ORDERS.md). [Bằng chứng workflow](demo-assets/screenshots/orders/results.json), [bằng chứng PDF](demo-assets/screenshots/orders/pdf-results.json).

## Luồng tài liệu dự án (PB01)

Bộ tài liệu PB01 mô tả cùng một boundary sản phẩm theo thứ tự từ quyết định đến triển khai. Khi thay đổi phạm vi hoặc hành vi, đọc và cập nhật theo luồng **0 → 1 → 2 → 3**, rồi cập nhật tài liệu vận hành và bằng chứng:

0. [Scope PB01](docs/SCOPE-PB01.md) — vấn đề, boundary, actor, giả định, câu hỏi mở và Definition of Done.
1. [Spec PB01](docs/SPEC-PB01.md) — yêu cầu chức năng, NFR, use case, acceptance và ngoại lệ.
2. [Module Map PB01](docs/MODULEMAP-PB01.md) — móng ẩn, domain, experience, validation và cut line MVP.
3. [Architecture PB01](docs/ARCH-PB01.md) — container demo/pilot, data model, API, phân quyền, NFR và đường di chuyển.

[AGENT.md](AGENT.md) ghi quy tắc làm việc, dữ liệu giả lập, kiểm thử và cách giữ ranh giới prototype/pilot. Bộ tài liệu này áp dụng cho Pema Digital Clinic hiện tại; không phải giáo trình hay checklist đào tạo.
