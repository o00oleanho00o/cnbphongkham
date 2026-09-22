# Flutter: mức tương đương web và bằng chứng

> **Hiện trạng Mobile CRM02 (22/09/2026):** tài chính trong Clinic shell, 46 hồ sơ mẫu/10 nhóm chăm sóc; Flutter phân workspace và tách state theo patient. Các mô tả state chung hoặc chưa có native CRM phía dưới là baseline trước bản mở rộng này. Xem [hướng dẫn cập nhật](25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).


## Cập nhật PB02 — 22/09/2026

Các hàng memory-only/thu ngân PB01 bên dưới mô tả state trong phiên, đã tách theo patient ID. Module tài chính PB02 mới dùng API/SQLite, có invoice/payment, tỷ lệ/lượt/người thực hiện, role projection, chốt kỳ và thông báo foreground. Chưa thay thu ngân PB01 hoặc sync lâm sàng; chưa có OS push. [Ma trận nghiệp vụ và bằng chứng mới](24_FINANCE_AND_PROCEDURE_FEES.md). Mốc PB02 có 12 test; Mobile CRM02 hiện có 17 test. Bằng chứng 6 test lịch sử ở dưới được giữ nguyên; xem VALIDATION và báo cáo Mobile CRM02 cho lượt chạy mới.


Đối chiếu source tại 22/09/2026: `flutter-template/lib/main.dart`, `lib/store.dart`, `test/template_test.dart`. “Có” dưới đây chỉ nói template trong phiên, không có nghĩa production.

## Ma trận nghiệp vụ

| Module | Flutter đang làm được | Phần chưa tương đương web / chưa triển khai |
|---|---|---|
| Identity / Patient 360 | Chọn 46 hồ sơ snapshot tổng hợp, mở các tác vụ | Không dataset lâm sàng đầy đủ; nhiều nhãn tĩnh; không auth/RBAC |
| Dashboard | Check-in thay đổi counter, shortcut tác vụ | 12 lịch hiển thị tĩnh; không projection vận hành đầy đủ |
| Lịch | Chọn ngày, slot, đặt/dời và xác nhận mẫu | 09:00 khóa cứng; không engine conflict bác sĩ/phòng/waitlist |
| Tư vấn / buổi | Lưu note, hoàn tất buổi khi có note + checkbox, tăng đếm tới 5 | Note/sessions theo patient trong memory; không record session, event, follow-up tự sinh |
| Catalog | Bundle 115 dòng, tìm mã/tên chữ thường, thêm hàng và tăng lượng | Chỉ 20 kết quả đầu; chưa search bỏ dấu; quantity tối thiểu 1, chưa validation domain đầy đủ |
| Đơn | Snapshot hàng, nháp/sửa/duyệt cùng ID; chặn thiếu loại/cách dùng | Không NONE/Không in, lý do override, version, audit, reviewer/time, persistence |
| Care documents | Ẩn nháp; nhóm thuốc và tư vấn approved theo patient | Không enforce approval immutable/role tại server |
| Phiếu A5 | Card tổng hợp đơn đã duyệt, tách hai nhóm | Không document từng đơn, pagination, PDF, print/share native; test PDF web không áp dụng |
| Thu ngân | Tổng đơn của patient, tổng đã thu riêng patient; xác nhận thu phần còn lại | Tổng gồm nháp; chỉ thu toàn phần tiền mặt; không invoice entity/ledger/cọc/partial/refund |
| Aftercare | Checkbox xác nhận trong phiên | Không acknowledgment record theo người/buổi |
| Cập nhật / phản hồi | Text bắt buộc, consent nếu chọn ảnh mẫu, ghi phản hồi theo patient | Không camera/file/ảnh được lưu; không owner/SLA/unread/resolve lifecycle |
| Ảnh / privacy | Ô ảnh bằng icon, checkbox quyền riêng tư | Không clinical media hoặc consent bền vững; checkbox privacy mất khi mở lại |
| AI | Tóm tắt deterministic từ dữ liệu đếm | Không model, trích event thật hay workflow clinical approval |
| Dịch vụ / nguồn lực | Danh sách/card để duyệt bố cục | Chưa quản trị nghiệp vụ đầy đủ như màn web |

**Cách ly dữ liệu:** đơn lọc theo `patient`, receipts là map theo patientId. Cart, editingOrder, lịch, note, sessions, updates, response, CSKH note/escalation và các boolean nghiệp vụ đã tách theo patient ID. Care/Clinic có selection riêng; vẫn chưa bảo mật hoặc persistence server. Reload mất toàn bộ mutation. Catalog là dữ liệu người dùng cung cấp, bệnh nhân là giả lập.

## Bằng chứng đã có (không chạy lại trong lần cập nhật tài liệu)

Nguồn: [VALIDATION](../flutter-template/VALIDATION.md), [test source](../flutter-template/test/template_test.dart).

| Kiểm tra | Kết quả đã ghi / phạm vi |
|---|---|
| Flutter analyze | No issues found trên Flutter 3.47.5 / Dart 3.13.4 |
| Test 1 — store | 115 hàng, 7 UNRESOLVED; thiếu usage chặn ready; sửa nháp thành duyệt không nhân đôi; đơn/paid tách patient |
| Test 2–5 — widget | Clinic home và 12 detail route có cart/order tại widths 360/390/430/768, tất cả height 844; không Flutter exception |
| Test 6 — interaction | Tap sản phẩm thêm cart, nút xem đơn mở review; không phải toàn flow duyệt end-to-end |
| Build web | Thành công với base-href /native-preview/; có warning font CupertinoIcons ở framework adaptive path |
| Visual browser | Clinic home, sheet đổi không gian, Care home ở 390×844 đã xem; không phải toàn bộ màn |

12 route widget: Patient 360, Đặt lịch, Lên đơn nhanh, Kiểm tra đơn, Thu ngân, Gửi cập nhật, Ảnh tiến triển, Ask Pema, Bác sĩ & phòng, Kế hoạch điều trị, Phiếu A5, Đơn thuốc & tư vấn. Suite này không chứng minh mọi thao tác trong từng route đã chạy.

## Checklist duyệt tiếp — chưa đánh dấu đạt

- [ ] Chủ sản phẩm duyệt nhận diện, mật độ nội dung, điều hướng Clinic/Care và các màn con.
- [ ] Chạy xuyên tạo nháp → đổi Care kiểm tra ẩn → quay Clinic sửa/duyệt → Care hiển thị đúng nhóm.
- [ ] Duyệt đặt/dời lịch, note/buổi, aftercare, gửi cập nhật/phản hồi và thu tiền; ghi rõ state trong phiên và các mô phỏng.
- [ ] Xem đầy đủ màn ở 360×800, 390×844, 430×932, 768×1024 với nội dung dài/đơn nhiều dòng.
- [ ] Kiểm tra bàn phím mở, text scaling, screen reader, focus, contrast, safe area và gesture trên Android/iOS thật.
- [ ] Sau khi có backend: isolation mọi record, quyền từng role, audit/version, retry/offline và thanh toán idempotent.
- [ ] Sau tích hợp plugin: permission/camera/consent, ảnh lưu thật, PDF/in/share và notification trên thiết bị.

Ưu tiên triển khai sau duyệt: hoàn thiện typed models → repository/persistence/auth → hoàn thiện nghiệp vụ → plugin → test device. Không coi việc có đủ màn là đã hoàn thành các bước này.
