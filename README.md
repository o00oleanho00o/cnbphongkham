# Pema Digital Clinic — Ultra Section

## Tài chính & tiền thủ thuật (PB02)

Đã có phân hệ tài chính trong Clinic, dùng chung khung điều hướng và tách góc nhìn chủ phòng khám, kế toán, bác sĩ: doanh số thực hiện, thực thu, công nợ, tỷ lệ thủ thuật/người thực hiện, duyệt/chốt tháng và inbox thanh toán. Chạy thêm `python prototype/finance_server.py`; mở [Tài chính web](http://127.0.0.1:4173/clinic-web/?screen=finance) hoặc app mobile (`pema-kmp`) Clinic → Tài chính phòng khám. [Nghiệp vụ, công thức, hướng dẫn và giới hạn](docs/24_FINANCE_AND_PROCEDURE_FEES.md).

Riêng PB02 dùng API/SQLite chung và lưu bền vững cục bộ; mô tả memory-only/localStorage bên dưới vẫn áp dụng các module PB01. Thông báo hiện đồng bộ khi app mở, chưa có push OS khi đóng app.

## App mobile (KMP)

App mobile Pema nằm ở [`pema-kmp/`](pema-kmp/README.md) (Kotlin Multiplatform + Compose Multiplatform, Android và iOS): cách build/chạy, cấu trúc module và trạng thái ở [pema-kmp/README.md](pema-kmp/README.md), quy ước ở [CONVENTIONS](pema-kmp/CONVENTIONS.md), spec từng màn ở [design-specs](design-specs/README.md). Thư mục `flutter-template/` chỉ là mã cũ giữ lại để tham khảo, không còn phát triển.

Workspace này chứa prototype và tài liệu nghiên cứu của Pema Digital Clinic. Hồ sơ bệnh nhân là giả lập; catalog 115 sản phẩm lấy từ Excel người dùng cung cấp.

- [Bản đồ tài liệu](docs/README.md) và luồng [Scope](docs/SCOPE-PB01.md) → [Spec](docs/SPEC-PB01.md) → [Module Map](docs/MODULEMAP-PB01.md) → [Architecture](docs/ARCH-PB01.md).
- [Quy tắc cập nhật cho agent](AGENT.md), [hiện trạng mobile và tài khoản mẫu](docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).
- [`pema-agent/`](pema-agent/README.md): agent CSKH qua Zalo (bản dịch Python của zalo-agent) và CRM phòng khám phía server, chạy tách khỏi các prototype ở đây; xem [SCOPE-AI01](pema-agent/docs/SCOPE-AI01.md) → [SPEC](pema-agent/docs/SPEC-AI01.md) → [MODULEMAP](pema-agent/docs/MODULEMAP-AI01.md) → [ARCH](pema-agent/docs/ARCH-AI01.md); chưa chạy với Zalo/mô hình thật.

| Bản                        | Mục đích                                | Lưu dữ liệu                                         |
| -------------------------- | --------------------------------------- | ---------------------------------------------------- |
| Clinic Web + Patient Mobile | Prototype nghiệp vụ liên thông          | localStorage cùng origin/profile                     |
| App mobile KMP (`pema-kmp`) | App Android/iOS theo design canvas      | Bộ nhớ trong tiến trình; tài chính PB02 qua API      |
| Native pilot/production    | Giai đoạn triển khai tiếp sau duyệt     | Backend/auth/storage chưa được triển khai            |

## Tiêu chuẩn hiển thị UI

- Clinic Web lấy **1920×1020 CSS pixels, zoom trình duyệt 100%** làm viewport desktop chuẩn để thiết kế và nghiệm thu. Đây là vùng nội dung trình duyệt, không phải độ phân giải màn hình gồm thanh công cụ.
- Vùng làm việc dùng chiều ngang khả dụng; tránh giới hạn cứng 920/1050px gây khoảng trắng lớn. Hướng dẫn chia nội dung và thông tin bàn giao thành hai cột ở màn rộng để giữ dòng chữ dễ đọc; bác sĩ/dịch vụ dùng bốn cột từ 1600px.
- Kiểm tra thêm 1440×900, 1280×720, 1024×768 và 390×844. Lịch và bảng dữ liệu có thể cuộn bên trong; toàn trang không được tràn ngang. Patient Mobile giữ bố cục dành cho điện thoại.
- Mỗi lần sửa bố cục, chạy `node prototype/review-desktop.cjs` khi server đang hoạt động. Script chụp 11 màn chính và 5 tab Patient 360 tại cả 5 kích thước; kết quả và ảnh ở `demo-assets/screenshots/desktop-1920/`. Xem ảnh để đánh giá bố cục bên cạnh kết quả tự động.

## Khởi động

### Chạy nhanh bằng Docker Compose

Tại thư mục gốc của workspace, chạy 1 lệnh:

```powershell
docker compose up -d --build
```

Sau khi container lên, mở:

- Clinic Web: [http://127.0.0.1:4173/clinic-web/](http://127.0.0.1:4173/clinic-web/)
- Patient Mobile: [http://127.0.0.1:4173/patient-mobile/](http://127.0.0.1:4173/patient-mobile/)

Lệnh dừng:

```powershell
docker compose down
```

### Chạy local bằng Python

Mở PowerShell tại `F:\BUL_Research\DalieuOs\prototype` và chạy:

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

Mở **cả hai URL trong cùng browser profile**:

- Clinic Web: [http://127.0.0.1:4173/clinic-web/](http://127.0.0.1:4173/clinic-web/)
- Patient Mobile: [http://127.0.0.1:4173/patient-mobile/](http://127.0.0.1:4173/patient-mobile/)

Hai app là vanilla HTML/JavaScript, không cần `npm install` hoặc bước build. Chúng dùng chung `localStorage` key `pema-demo-v2` khi chạy cùng **origin `http://127.0.0.1:4173` và cùng browser profile**. Không mở một app bằng `localhost`, file trực tiếp (`file://`) hoặc browser profile khác nếu muốn thấy thay đổi cross-app. Clinic có nút reset để khôi phục dataset tổng hợp.

Ảnh và sự kiện upload trong prototype chỉ phục vụ demo; ảnh được thu nhỏ và lưu trong localStorage. Không nạp dữ liệu bệnh nhân thật.

### Design Viewer — xem design canvas

→ Mở **http://localhost:4190** (Docker) hoặc `cd design-viewer; npm run dev` → **http://localhost:4180** (tự nạp lại khi sửa canvas).

Phím tắt: `Ctrl+cuộn` phóng/thu, `Space+kéo` hoặc `H` để di chuyển, `V` để tương tác prototype, `Shift+1` vừa khung. Ghi nhớ vị trí zoom, props và trạng thái panel trong `localStorage`.

**Xuất ảnh màn hình (như Figma):**
- Chọn màn: bấm vào **tên màn** (ô mã + tên phía trên khung) trên canvas, hoặc bấm màn trong danh sách bên trái. Màn đang chọn có viền xanh; bấm đúp tên màn để phóng tới.
- Nút **Xuất ảnh** (biểu tượng chia sẻ trên thanh công cụ) mở bảng xuất: chọn **tỉ lệ** 1x / 2x / 3x và **định dạng** PNG / JPG, rồi:
  - **Xuất A1** — tải một ảnh `A1 · Hôm nay@2x.png` (390×844 → 780×1688 px ở 2x);
  - **Nhóm A · 7 màn (.zip)** — cả nhóm của màn đang chọn;
  - **Tất cả · 82 màn (.zip)** — toàn bộ canvas (~20 giây ở 2x).
- Nút tải xuống xuất hiện khi rê chuột lên từng màn trong danh sách → xuất ngay màn đó với cài đặt hiện tại. Phím tắt `Ctrl+Shift+E` xuất màn đang chọn.
- Ảnh gồm cả khung điện thoại (thanh trạng thái 9:41), không có viền chọn; PNG giữ góc bo trong suốt, JPG nền trắng. Font Be Vietnam Pro và icon Material Symbols được nhúng vào ảnh. Ảnh chụp đúng trạng thái đang hiển thị (props, màn prototype đang bấm tới).
- Ảnh tham chiếu cho so sánh KMP (`pema-kmp/design-ref/`) được tạo tự động bằng `canvas-shots.cjs`, không cần xuất tay — xem [pema-kmp/README.md](pema-kmp/README.md).

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

Mở [Điều phối lịch](http://127.0.0.1:4173/clinic-web/?screen=schedule), [Bác sĩ &amp; phòng](http://127.0.0.1:4173/clinic-web/?screen=resources), [Dịch vụ](http://127.0.0.1:4173/clinic-web/?screen=services), [Thu ngân](http://127.0.0.1:4173/clinic-web/?screen=cashier). Dữ liệu mock và thao tác chi tiết trong [hướng dẫn demo](docs/19_OPERATIONS_DEMO.md). Chạy `node prototype/operations-test.cjs` để kiểm tra 20 tình huống vận hành.

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

## Design skill dùng chung cho đồng nghiệp

Dùng **$pema-design** để thiết kế/review Clinic Web, Patient Mobile và app mobile theo nhận diện, luồng và responsive của dự án. [Skill trong repository](.agents/skills/pema-design/SKILL.md) có bốn reference về visual, màn hình/flow, layout và kiểm thử. [Hướng dẫn chia sẻ + prompt mẫu](docs/23_PEMA_DESIGN_SKILL.md). Có thể clone repo hoặc copy nguyên thư mục skill; không cần đường dẫn máy tác giả.

## CRM01 — replacement và vòng đời khách hàng (22/09/2026)

Mở [Clinic Web](http://127.0.0.1:4173/clinic-web/) và chọn **Tài khoản demo**: BS. Tâm — Chủ phòng khám, bác sĩ điều trị, CSKH Mai Anh/Thu hoặc Kế toán. Mỗi vai có trang bắt đầu, menu và tác vụ riêng. Chủ xem tổng quan; bác sĩ xem lịch/hồ sơ phụ trách và doanh số cá nhân; CSKH xử lý hàng đợi; kế toán làm thu ngân/đối soát. Đây là mô phỏng tài khoản, chưa auth/RBAC thật.

CRM01 nối expected visit, protocol D+1/D+3/D+7/D+30, vắng hẹn, bỏ dở, dormant và sinh nhật vào work queue. Xử lý → kết quả → timeline → đặt lịch qua validation hiện có → Patient Mobile. Booking và khách đã quay lại là hai chỉ số riêng. Hướng dẫn đầy đủ: [CRM01](docs/20_CRM01_PATIENT_LIFECYCLE.md). Tab Hướng dẫn trong app cũng có bài CSKH/tài khoản.

Ngày demo cố định 20/09/2026, 46 bệnh nhân khi seed mới: 36 hồ sơ nền + 10 tài khoản nhóm CSKH; giữ 8 case P025–P032. Migration giữ dữ liệu đã nhập; dùng nút reset nếu muốn khôi phục fixture kể chuyện (xóa thay đổi thử ở browser, không reset DB tài chính). Chuẩn desktop 1920×1020; bảng phân trang/cuộn riêng, kiểm thêm 1440/1280/1024/390. Kiểm tải 200 dòng là UI fixture, không chứng minh năng lực xếp 200 lịch với nguồn lực hiện có.

Chạy `node prototype/crm-test.cjs` và `node prototype/crm-browser-test.cjs`; bằng chứng ở `demo-assets/screenshots/crm01/`. Suite desktop/operations nhận `PEMA_EVIDENCE_DIR` để lưu evidence riêng, tránh ghi đè ảnh các vòng trước. App mobile/PB02 tiếp tục giữ phạm vi riêng; chưa native CRM hoặc gửi tin thật.

## Mobile và tài chính cùng Clinic

[Tài chính](http://127.0.0.1:4173/clinic-web/?screen=finance&staff=accountant) nay dùng chung sidebar và bộ chọn nhân viên; URL `/finance/` cũ tự chuyển hướng. [Patient Mobile](http://127.0.0.1:4173/patient-mobile/) → Hồ sơ → Nhóm tài khoản mẫu để thử đủ 10 nhóm. Trong app mobile (`pema-kmp`): nút đổi không gian ở thanh trên; Care → Hồ sơ để đổi bệnh nhân. Không cần reset dữ liệu web. [Hướng dẫn và phạm vi](docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).
