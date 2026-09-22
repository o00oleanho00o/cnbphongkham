# Pema Digital Clinic prototype

Lên đơn từ Excel: **Thu ngân → Lên đơn nhanh** hoặc **Patient 360 → Tạo đơn nháp**. Sau khi lưu, kiểm tra hai phiếu và bác sĩ duyệt trước khi in/gửi app. [Hướng dẫn và lệnh import/test](../docs/20_CATALOG_ORDERS.md).

Hai trải nghiệm browser dùng chung dataset giả lập qua `localStorage` key `pema-demo-v2` khi chạy trên cùng origin và cùng browser profile:

- Clinic Web: http://127.0.0.1:4173/clinic-web/
- Patient Mobile: http://127.0.0.1:4173/patient-mobile/

Chạy từ thư mục này:

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

Dùng Clinic sidebar để mở Today, Patient 360, Tư vấn, ghi buổi điều trị và xử lý Follow-up Inbox. Mở Patient Mobile bằng URL bên trên trong cùng browser profile để thấy treatment journey, aftercare và gửi update. Nút reset ở Clinic khôi phục dataset cố định. AI và ảnh trong demo là mô phỏng; không dùng dữ liệu bệnh nhân thật.

## Chuẩn viewport

Clinic Web mặc định thiết kế và nghiệm thu tại **1920×1020 CSS pixels, zoom 100%**. Vùng làm việc giãn theo chiều ngang; không áp giới hạn chiều rộng hẹp cho toàn bộ màn. Hướng dẫn dùng cột nội dung và cột bàn giao trên màn rộng; các bảng/lịch cuộn bên trong khi cần.

Kiểm tra hồi quy ở 1440×900, 1280×720, 1024×768, 390×844; Patient Mobile vẫn giữ bố cục điện thoại. Chạy `node prototype/review-desktop.cjs` từ workspace gốc sau khi bật server 4173. Ảnh và kết quả ở `demo-assets/screenshots/desktop-1920/`.
