# Lên đơn sản phẩm và tách phiếu

Triển khai trong prototype Pema, tham chiếu `E:\codex\indon\overview\.md`, print-template.js và preview.css. Không import hồ sơ người bệnh từ project tham khảo.

## Thao tác

1. Thu ngân → Lên đơn nhanh, hoặc mở bệnh nhân → Tạo đơn nháp.
2. Chọn đúng người bệnh và bác sĩ. Nhập chẩn đoán/nội dung tư vấn, tìm mã/tên sản phẩm (hỗ trợ không dấu).
3. Thêm sản phẩm, nhập số lượng, cách dùng/tần suất/thời gian và ghi chú. Thêm cùng mã tăng số lượng; nút × bỏ dòng.
4. Thuốc tự vào Đơn thuốc; TPCN/mỹ phẩm/loại khác có giá trị vào Phiếu tư vấn. Loại trống giữ Cần phân loại. Muốn đổi nhóm hoặc Không in, ghi lý do.
5. Lưu nháp & xem tách đơn. Nháp chưa hiển thị trên mobile và chưa in được. Danh sách “Cần phân loại” và “Không in” luôn được liệt kê để đối chiếu tổng số dòng.
6. Sửa nháp qua Thu ngân/Patient 360 nếu cần. Đơn đã thu tiền không sửa được; bản sửa từ cửa sổ cũ bị từ chối để tránh ghi đè.
7. Bác sĩ duyệt & gửi app sau khi kiểm tra. Thiếu cách dùng hoặc nội dung tư vấn sẽ hiện lỗi. Chỉ duyệt khi còn ít nhất một sản phẩm được phát hành.
8. In riêng Đơn thuốc, Phiếu tư vấn hoặc tất cả; chọn A5 dọc, tắt header/footer trình duyệt nếu bật. Hai loại phiếu bắt đầu trên trang riêng, nội dung dài tự sang trang. Bản in dùng logo Pema hiện tại, tên bác sĩ và thuật ngữ riêng cho từng phiếu.

Không in chỉ ảnh hưởng phiếu/mobile, vẫn tính tiền. Thanh toán và duyệt đơn độc lập, không tự đánh dấu đã cấp thuốc. Đơn duyệt giữ nguyên snapshot tên/giá/hướng dẫn dù catalog được cập nhật sau đó. Sản phẩm giá 0 trong Excel giữ giá 0, không tự suy ra giá khác.

## Nguồn catalog

File dùng: `data/danhsach.xlsx` trong workspace `F:\BUL_Research\DalieuOs`. SHA-256: `3047d9e3bb50f813c39a15b9848e01697a59f6984d3ac676bdbd28186c387de5`.

115 dòng sản phẩm: 30 Thuốc, 64 Mỹ Phẩm, 14 TPCN, 7 trống Loại. Không tự xếp bảy dòng thiếu loại thành tư vấn như catalog thử nghiệm cũ. Giữ tên nguyên văn, mã, đơn vị, giá sau thuế, VAT, số dòng; bỏ hàng Excel hoàn toàn trống.

```powershell
python prototype/import-product-catalog.py
python prototype/import-product-catalog.py --check
node prototype/product-catalog-test.cjs
node prototype/order-test.cjs
python prototype/order-pdf-test.py
```

Server tại 127.0.0.1:4173 phải chạy khi test trình duyệt. PDF test dùng PyMuPDF (`python -m pip install pymupdf`). Không cần Node build cho ứng dụng. Import hiện qua script, chưa có upload Excel trực tiếp trong giao diện.

## Kiểm chứng và ranh giới

Evidence: `demo-assets/screenshots/orders/`. Workflow kiểm thử nhập/sửa/duyệt/mobile, route thiếu, lý do override, số lượng sai, stale edit, rollback localStorage, in riêng và 5 viewport. PDF được đọc lại để kiểm A5, số dòng, toàn bộ hướng dẫn dài và footer; 5 sản phẩm ngắn nằm trên một trang, 24 sản phẩm dài qua nhiều trang.

Đơn mới nằm ở `quickOrders[]`; `prescriptions[]` cũ vẫn giữ nguyên để tương thích và không được fuzzy match/phân loại lại tự động. Những đơn nhanh tạo bởi bản thử nghiệm cũ phải mở Sửa nháp, đối chiếu catalog rồi mới duyệt.

Tài khoản bác sĩ, dữ liệu người bệnh và đồng bộ localStorage vẫn là mô phỏng. Bản in mang nhãn demo; chưa có đăng nhập/RBAC server, backend, ký số hoặc QR phòng khám được cấu hình. Không sao chép QR hay địa chỉ chưa xác minh từ project khác.
