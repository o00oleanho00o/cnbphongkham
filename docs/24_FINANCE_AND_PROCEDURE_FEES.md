# Tài chính chủ phòng khám và tiền thủ thuật — PB02

Cập nhật 22/09/2026. Phần này đã có API/SQLite cục bộ dùng chung cho web và Flutter; các module lâm sàng PB01 vẫn giữ runtime cũ. Đây là dữ liệu thử, chưa dùng để tính lương hoặc xử lý tiền thật.

## Nghiệp vụ đã phân tích

| Chỉ số | Ý nghĩa / thời điểm |
|---|---|
| Doanh số thực hiện | Tổng giá sau giảm của các lượt thủ thuật được ghi nhận, theo ngày thực hiện; không phải doanh số bán sản phẩm toàn hệ thống |
| Doanh số bác sĩ | Giá sau giảm × tỷ trọng tham gia; tổng tỷ trọng các người trong một lượt bằng 100% |
| Thực thu | Phiếu thu thành công trong tháng, kể cả thanh toán hóa đơn tháng trước; không lấy tổng giá đơn nháp |
| Công nợ | Tổng giá trị hóa đơn nguồn trừ đã nhận tại thời điểm xem; gồm hóa đơn ngoài tháng lọc |
| Tiền thủ thuật đã duyệt | Cơ sở tính × tỷ lệ tiền của từng người, chỉ các lượt đã duyệt |
| Tiền chờ duyệt | Khoản dự kiến chưa vào số được kế toán xác nhận |

Mặc định đang đề xuất **giá sau giảm**; đây chưa phải chính sách thực tế được chủ phòng khám xác nhận. Kế toán cấu hình mỗi thủ thuật: giá sau giảm, giá niêm yết hoặc thực thu. Tỷ lệ tính bằng basis points (100 = 1%) và lưu snapshot trên từng lượt. UI hiện nhận tối đa hai người; API hỗ trợ bốn bác sĩ mẫu, chưa có danh mục kỹ thuật viên/role nhân sự riêng. Cần chủ phòng khám xác nhận cơ sở và tỷ lệ thật trước pilot.

Ví dụ laser 2.500.000, giảm 100.000: doanh số 2.400.000. BS chính nhận tỷ trọng doanh số 70%, tỷ lệ tiền 15%: doanh số 1.680.000, tiền 360.000. BS phối hợp 30%, tỷ lệ tiền 5%: doanh số 720.000, tiền 120.000. Tỷ trọng doanh số và tỷ lệ tiền là hai khái niệm riêng. Tiền làm tròn VND từng người; doanh số chia có phần dư giao dòng cuối để cộng lại đúng giá sau giảm.

## Vai trò và luồng thao tác

- **BS. Tâm/chủ:** xem toàn phòng khám, tổng hợp đội ngũ, inbox thanh toán, đối soát và chính sách. Bác có thể chuyển góc nhìn cá nhân của D0.
- **Kế toán:** ghi lượt hoàn tất/người thực hiện, cấu hình tỷ lệ, duyệt, kiểm chi tiết, xuất CSV cho Excel, chốt tháng và xác nhận đã chi với mã chứng từ.
- **Bác sĩ:** API chỉ trả các dòng của mình, không toàn bộ invoice/payment/policy/audit hoặc inbox chủ. UI không có nút chỉnh tiền/duyệt.
- Header chọn role phục vụ demo; chưa có login/identity tin cậy. API kiểm quyền theo role header nhưng caller có thể tự chọn header trong môi trường thử; chưa phải phân quyền production.

### Ghi người thực hiện ngay trong hệ thống

Web: Clinic → Tài chính & tiền thủ thuật → Tiền thủ thuật → Ghi nhận lượt. Link từ Clinic giữ patient đang chọn. Flutter: Clinic → Tài chính phòng khám → Thủ thuật → Ghi lượt; Patient 360 có shortcut khi tài khoản có quyền và API đã tải.

Chọn hồ sơ, thủ thuật, ngày đã thực hiện, giá/giảm giá, bác sĩ chính/phối hợp, tỷ trọng và tỷ lệ tiền, ghi chú xác nhận hoàn tất. Không tự đoán người thực hiện từ bác sĩ phụ trách hồ sơ. Lượt vào hàng chờ kế toán duyệt; danh sách sẽ tính tiền tự động, không cần điền công thức Excel cuối tháng.

**Gắn hóa đơn đã có** nếu thủ thuật thuộc hóa đơn/liệu trình đã bán. API kiểm invoice thuộc bệnh nhân và tổng giá trị lượt phân bổ không vượt hóa đơn; không tạo nợ thêm. Chỉ chọn **Tạo hóa đơn mới cho lượt này** khi đó là khoản bán mới. Chưa tự import các buổi lâm sàng cũ thành lượt tính tiền vì chúng thiếu người thực hiện và mapping hóa đơn chắc chắn. Phân bổ tiền thu trên hóa đơn nhiều lượt theo tỷ lệ đã thu, không suy mỗi buổi đã được trả riêng.

### Duyệt và chốt tháng

Chờ duyệt → đã duyệt → chốt kỳ → đã chi. Hủy trước chốt cần lý do, không xóa lịch sử. Không hủy lượt có tiền thu; cần quy trình hoàn/điều chỉnh riêng chưa nằm trong bản này. Hủy lượt gắn hóa đơn cũ không làm mất hóa đơn; hóa đơn tạo riêng cho lượt chưa thu được đưa giá trị về 0.

Chỉ chốt tháng đã kết thúc, không còn lượt chờ duyệt. Với cơ sở thực thu, chặn chốt khi hóa đơn liên quan chưa thu đủ để không bỏ sót phần tiền trả sau; chưa có chuyển khoản tiền thủ thuật sang kỳ sau/điều chỉnh hồi tố. Kỳ chốt lưu bản chụp dòng tính tiền và không sửa/ghi thêm lượt trong kỳ. Xác nhận đã chi là trạng thái kế toán, không chuyển tiền ngân hàng. Có dữ liệu mẫu tháng trước để thử quy trình.

### Thanh toán → thông báo

- Phiếu thu từ module tài chính (web hoặc Flutter) cập nhật invoice, payment và notification trong một SQLite transaction.
- Retry cùng mã/nội dung trả cùng phiếu; mã đã dùng với nội dung khác hoặc số thu vượt nợ bị từ chối. Không tạo thông báo khi thất bại.
- Thu ngân web cũ vẫn ghi localStorage; bridge mirror toàn snapshot hóa đơn và payment ledger sang API, retry mỗi 10 giây nếu cần. Payment ID có namespace chống trùng. Link trên header báo đã đồng bộ/chờ kết nối. Không coi mirror là giao dịch thu tiền thứ hai.
- Inbox owner lưu trạng thái đọc trên server. Flutter poll khoảng 4 giây khi foreground; có badge và snackbar cho thông báo mới trong phiên Clinic. Care không hiện thông báo tiền của phòng khám.
- **Chưa có FCM/APNs, background push khi đóng app, SMS hay Zalo.** Cần credential/provider, bản cài và nghiệm thu thiết bị cho bước đó. Polling trên browser không được gọi là push OS.

## Cách chạy

Từ gốc repo, mở API bằng Python 3 chuẩn (không dependency ngoài):

```powershell
python prototype/finance_server.py
```

API ở `http://127.0.0.1:4174`; database `.local/finance.sqlite3` bị git-ignore. Không xóa DB để reset nếu muốn giữ lịch sử thử. `--db <path>` và `--port <number>` dành cho test cô lập. SQLite hiện lưu một document JSON trong transaction; chưa phải schema relational/migration production.

Static server cũ ở 4173; nếu chưa chạy, từ `prototype` chạy `python -m http.server 4173 --bind 127.0.0.1`. Mở [Tài chính web](http://127.0.0.1:4173/finance/) hoặc [Flutter review](http://127.0.0.1:4173/native-review/).

Build Flutter theo [runbook](21_NATIVE_RUNBOOK.md). Dependency mới `http`; finance controller có timeout, lỗi hiển thị, retry và tạm ngưng poll khi lifecycle không foreground. API base có thể cấu hình bằng `--dart-define=PEMA_FINANCE_API=...`. Server hiện bind loopback, nên máy thật cần thiết lập tunnel/reverse phù hợp trong môi trường phát triển; chưa nghiệm thu Android/iOS networking/cleartext/ATS. Không expose API demo ra Internet.

Khi API tắt, tài chính hiển thị lỗi/thử lại, không giả vờ đã lưu. Chức năng lâm sàng cũ vẫn hoạt động; receipts web chờ đồng bộ. DB finance và localStorage là hai kho riêng: reset Clinic web không reset DB tài chính. Không có sync lâm sàng toàn hệ thống.

## Giới hạn và hướng triển khai tiếp

Tổng quan hiện phản ánh các lượt thủ thuật đã ghi trong PB02 và phiếu thu có ledger; khoản received lịch sử thiếu phiếu không được bịa ngày thu để cộng vào tháng. Fixture PB02 là 24 lượt riêng, không tự coi là các buổi legacy đã được nhập. Tiền thu từ web cũ được mirror một chiều; hóa đơn source web chỉ thu tại cashier cũ. Bridge có thể chậm và chưa có version/merge chống snapshot từ browser cũ, nên chỉ dùng một profile cashier cho demo. Chưa có hoàn tiền, reopen kỳ, lương/thuế, thu nhập kỹ thuật viên, tổng lợi nhuận/chi phí hay kế toán pháp định.

Production cần auth/RBAC/tenant, database schema/version, API sở hữu toàn bộ ledger, audit bất biến/backup, đối soát hóa đơn và session IDs chống nhập trùng, permission FCM/APNs, job outbox/retry và chính sách điều chỉnh kỳ đã chốt. Không suy đã đạt các điều kiện này từ bản thử.

## Kiểm thử và bằng chứng

- `python prototype/finance_test.py`: 11 test, database tạm; tiền giảm/chia/snapshot, role read/write, idempotency và 5 request đồng thời, chống overpayment, khóa kỳ, invoice có sẵn, rounding và HTTP/CSV theo role.
- Flutter: 12 test tổng, gồm 6 test trước + 2 controller/API + 4 layout của các tab tài chính/form ở 360/390/430/768 × 844. Analyze sạch và build web thành công; không test thiết bị thật.
- Kiểm tra browser trực tiếp: tạo laser sau giảm 2.400.000, chia 70/30 và tỷ lệ 15/5, duyệt, thu 100.000 trên tài chính; thu 50.000 từ cashier cũ và mirror vào inbox; Flutter nhìn thấy thông báo web; doctor không có nút duyệt/form và chỉ thấy dòng của mình.
- Đo 4 màn × 5 viewport (1920×1020, 1440×900, 1280×720, 1024×768, 390×844), không tràn document. [Kết quả](../demo-assets/screenshots/finance/layout-results.json), [ảnh web](../demo-assets/screenshots/finance/web-overview.png), [ảnh app](../demo-assets/screenshots/finance/native-notification.png).
- Đã sửa overflow thanh chọn kỳ Flutter ở 360/390 và giữ form web khi poll. Cấu hình/chốt/CSV được kiểm ở domain/HTTP; không tuyên bố mọi nhánh GUI đã end-to-end.
