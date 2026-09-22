# Pema Digital Clinic — Scope PB01

## CRM01 — Clinic Replacement + Patient Lifecycle (22/09/2026)

Theo góp ý bổ sung: phân không gian theo tài khoản demo Chủ phòng khám / Bác sĩ / CSKH / Kế toán. BS. Tâm có góc nhìn chủ và góc nhìn bác sĩ riêng. CSKH vào hàng đợi, bác sĩ vào lịch/hồ sơ phụ trách, kế toán vào thu ngân; không ghép các dashboard vào cùng trang cho mọi người. Đây là phân vai thao tác bằng sessionStorage, không đăng nhập hoặc bảo mật production.

Mở rộng web trên nền PB01/PB02 hiện tại: tiếp đón theo appointment, Patient 360 có CRM/timeline, expected next visit, CSKH chủ động và dashboard dẫn tới hành động. Giữ 36 hồ sơ nền và 8 câu chuyện mẫu khi reset, bổ sung 10 tài khoản chăm sóc qua Mobile CRM02; không thay lịch sử người dùng lúc nâng phiên bản. Ngày demo cố định 20/09/2026. Clinic/Patient Mobile web dùng cùng localStorage. CRM01 ban đầu chỉ triển khai web; bản Mobile CRM02 bổ sung workspace/queue mẫu Flutter và đưa tài chính PB02 vào Clinic shell. Chưa có provider gửi tin thật.

Giả định: protocol laser mẫu D+1/D+3/D+7/D+30 chỉ tạo việc cho nhân viên, không tự gửi lời khuyên y khoa. Booking sau CSKH là kết quả đặt lại lịch; chỉ check-in/thực hiện sau đó mới tính đã quay lại. Opt-out chặn tái kích hoạt/sinh nhật, không xóa việc theo dõi an toàn lâm sàng. Ngưỡng bỏ dở 45 ngày, dormant 90/180 ngày cần chủ phòng khám duyệt trước pilot. Chi tiết và mapping parity: [CRM01](20_CRM01_PATIENT_LIFECYCLE.md).

Trạng thái: chốt cho prototype/pilot slice. Ngày: 2026-09-21.

Phương pháp: làm rõ boundary, giả định, quyết định và bằng chứng theo tài liệu PM AI Bootcamp; nội dung này chỉ mô tả sản phẩm Pema hiện tại.

## Vấn đề và mục tiêu

Phòng khám cần giữ một mạch chăm sóc từ tiếp nhận đến sau điều trị. Khi lịch, hồ sơ, buổi điều trị, ảnh, hướng dẫn, phản hồi và thu tiền rời nhau, nhân viên phải hỏi lại, bác sĩ thiếu bối cảnh và người bệnh không biết bước tiếp theo.

PB01 tạo vertical slice để lễ tân tìm đúng người bệnh, đội ngũ xử lý Patient 360, xếp lịch và buổi điều trị, gửi chăm sóc sau điều trị, nhận cập nhật từ Patient Mobile, theo dõi việc cần làm và đối soát dịch vụ/đơn thuốc/hóa đơn.

## Phạm vi trong PB01

### Clinic Web

- Dashboard và Today/Reception cho hàng đợi trong ngày.
- Tìm bệnh nhân, hồ sơ và Patient 360 với Tổng quan, Tư vấn, Kế hoạch, Buổi điều trị, Ảnh trước/sau.
- Điều phối lịch ngày/tuần, waitlist, bác sĩ, phòng, duration, buffer và xung đột.
- Danh mục dịch vụ và dịch vụ đã đăng ký: giá chốt, giảm giá, số buổi, tiến độ, bác sĩ phụ trách.
- Kế hoạch điều trị và ghi nhận buổi: trạng thái, ghi chú, aftercare, bước tiếp theo và ảnh có consent.
- Đơn thuốc nháp → bác sĩ duyệt → hiển thị có điều kiện trên Patient Mobile.
- Lên đơn nhiều sản phẩm từ `data/danhsach.xlsx` tại Thu ngân hoặc Patient 360; tách Đơn thuốc / Phiếu tư vấn, lưu nháp, sửa, duyệt và in A5 từng loại hoặc tất cả. Loại trống cần review, không tự suy đoán.
- Follow-up Inbox cho phản hồi/ảnh người bệnh, owner, severity và trạng thái.
- Thu ngân với hóa đơn chờ thu, tiền cọc, phân bổ cọc, thu một phần/toàn phần và chống thu trùng.
- Hướng dẫn trong hệ thống, liên kết theo hành trình và vai trò.

### Patient Mobile

- Trang chủ và hành động tiếp theo.
- Lịch hẹn, hành trình điều trị, aftercare, đơn thuốc đã duyệt, tài liệu/hóa đơn.
- Gửi cập nhật và ảnh với đồng ý sử dụng ảnh; xem trạng thái đã nhận/đang xem/đã phản hồi.
- Hồ sơ và tùy chọn riêng tư ở mức mô phỏng.

### Dữ liệu và bằng chứng

- 36 người bệnh tiếng Việt giả lập, có lịch, dịch vụ, liệu trình, phiên điều trị, follow-up, ảnh SVG/placeholder và hóa đơn mẫu.
- Cùng dataset qua localStorage để chứng minh liên thông hai app trên cùng origin.
- Kiểm thử flow, overflow desktop/mobile và screenshot evidence trong demo-assets.

## Native template duyệt thiết kế (22/09/2026)

Thêm template Flutter Clinic/Care, giữ nhận diện và luồng web, catalog 115 sản phẩm. Có mã Dart và browser preview từ Flutter để duyệt trước. State mẫu trong phiên; không phải triển khai native production. Chi tiết: [NATIVE-TEMPLATE](NATIVE-TEMPLATE.md).

### Boundary native tại ngày 22/09/2026

- Mục tiêu là duyệt thiết kế, điều hướng và thao tác mẫu trên điện thoại trước khi triển khai nghiệp vụ native đầy đủ. Các acceptance web ở dưới không mặc nhiên là kết quả đạt của Flutter.
- Trong scope: hai không gian Clinic/Care, Patient 360, form lịch/tư vấn/buổi, catalog 115 sản phẩm, nháp → duyệt → Care, thu tiền và follow-up minh họa; nhận diện Pema và preview nhiều kích thước.
- Catalog lấy từ Excel người dùng cung cấp; 46 hồ sơ snapshot tổng hợp, không phải bản sao clinical aggregate đầy đủ. Lịch/lâm sàng/follow-up/cart/đơn/tiền và CSKH note/escalation tách theo patient ID trong phiên; selection Care/Clinic riêng.
- Ngoài scope vòng này: sync với web, database/API, auth/RBAC, lịch chống trùng thật, ledger thanh toán, camera/upload, PDF/in/share, push và AI thật.
- DoD vòng template: mã Flutter build được; ghi rõ màn/tác vụ/giới hạn; phân biệt test đã chạy và checklist chờ duyệt. Hoàn tất kỹ thuật không đồng nghĩa chủ sản phẩm đã duyệt thiết kế hoặc native production đã sẵn sàng.
- Cần chốt tiếp: Clinic/Care là hai app hay một app theo role; nghiệp vụ nào phải chạy offline; ưu tiên backend, lịch, media hay in native sau duyệt.

Xem [ma trận parity và bằng chứng](22_NATIVE_PARITY_AND_VALIDATION.md) trước khi lập scope triển khai tiếp.

## Ngoài phạm vi hoặc để pilot sau

- Đăng nhập thật, RBAC thật, tenant isolation và đồng bộ nhiều thiết bị.
- Backend/API production, backup, phục hồi, migration và audit bất biến.
- Thanh toán ngân hàng, thẻ, hoàn tiền, hóa đơn điện tử và kế toán đầy đủ.
- Kho, mua sắm, HR, lương, marketing automation và CRM đa chi nhánh.
- SMS/Zalo/push thật và đặt lịch tự phục vụ từ Patient Mobile.
- Media production, signed URL, retention và import hồ sơ thật.
- AI model thật, chẩn đoán tự động, chấm điểm hiệu quả hoặc đổi phác đồ không có bác sĩ duyệt.
- Native iOS/Android production, tích hợp thiết bị và triển khai sản xuất; template thiết kế thuộc phạm vi duyệt.

## Actor và trách nhiệm

| Actor | Trách nhiệm |
|---|---|
| Lễ tân/điều phối | Tìm hồ sơ, đặt/xác nhận/check-in lịch, waitlist và nguồn lực |
| Bác sĩ | Đọc Patient 360, ghi tư vấn, duyệt kế hoạch/đơn thuốc, phản hồi nội dung lâm sàng |
| Điều dưỡng/chăm sóc | Ghi buổi, gửi aftercare, xem follow-up và chuyển việc cần bác sĩ |
| Thu ngân | Đối soát hóa đơn, phân bổ cọc, thu tiền và kiểm tra dư nợ |
| Người bệnh | Xem hành trình, hướng dẫn, đơn đã duyệt và gửi cập nhật/ảnh |
| Quản lý | Xem tải vận hành, dữ liệu mẫu và bằng chứng kiểm thử |

## Giả định

1. PB01 là prototype nội bộ, dữ liệu không phải hồ sơ y tế thật.
2. Một patient có thể có nhiều episode/plan; tiến độ buổi chỉ tăng khi session hoàn tất.
3. Dịch vụ danh mục là giá tham khảo; dịch vụ gắn patient giữ giá chốt và snapshot giảm giá.
4. Đơn nháp không phải hướng dẫn đã phát hành; chỉ đơn được bác sĩ duyệt mới lên Patient Mobile.
5. Tiền cọc và lần thu sau là ledger entry riêng; không trừ ngầm hoặc ghi nhận hai lần.
6. Demo dùng cùng origin và browser profile; reset localStorage sẽ khôi phục fixture.

## Câu hỏi mở cho pilot

- Mô hình chi nhánh, timezone, ca làm và phân quyền cụ thể của Pema?
- Trường bắt buộc cho consent, ảnh, đơn thuốc và thời hạn lưu?
- Quy tắc hủy/no-show, hoàn cọc, chuyển gói và gia hạn liệu trình?
- Kênh thông báo và SLA phản hồi D1/D3/D7?
- Ai duyệt mẫu AI, aftercare và thay đổi protocol?
- Khi nào cần kế toán, payment gateway hoặc Zalo?

## Quyết định nền

- Patient 360 nối bối cảnh; event/record gốc vẫn là nguồn sự thật.
- Output AI/clinical draft có nguồn, trạng thái nháp và người duyệt.
- Ảnh phải có consent; ảnh từ mobile vào hàng chờ review trước khi dùng.
- Không suy diễn trạng thái điều trị từ thanh toán hoặc trạng thái đơn thuốc.
- Thay đổi scope cập nhật lần lượt Scope → Spec → Module Map → Architecture và ghi SECTION_PROGRESS.

## Definition of Done PB01

- Flow chính trong SPEC-PB01 chạy được trên dataset giả lập.
- Dịch vụ → liệu trình → lịch → buổi → follow-up → mobile có liên kết kiểm tra được.
- Đơn nháp bị ẩn trên mobile; đơn duyệt hiển thị kèm reviewer/time.
- Cọc, thu một phần/toàn phần, hóa đơn chờ và chống overpayment được kiểm tra.
- UI không tràn ngang ở 1920×1020, 1440×900, 1280×720, 1024×768 và 390×844.
- Smoke/operations/data audit không có page error; screenshot evidence được lưu.
- README, AGENT và docs downstream khớp hành vi quan sát được.

## Ranh giới prototype và pilot

Prototype dùng vanilla HTML/JS, localStorage, synthetic data và AI mô phỏng để trả lời câu hỏi luồng có dễ hiểu và vận hành thử không. Pilot cần identity/RBAC, API/backend, database, object storage, audit/backup, consent/retention, notification adapter, template được duyệt và SOP ngoại lệ. PASS prototype không phải chứng nhận sẵn sàng lâm sàng hay pháp lý.


## Skill thiết kế dùng chung — 22/09/2026

Bổ sung gói hướng dẫn Pema Design trong repository để đồng nghiệp tái sử dụng nhận diện, luồng web/mobile/Flutter, responsive và phương pháp kiểm tra. Đây là tài sản hỗ trợ thiết kế, không mở rộng scope chức năng app. Hướng dẫn chia sẻ: [23_PEMA_DESIGN_SKILL](23_PEMA_DESIGN_SKILL.md).


## Mobile và Clinic shell — 22/09/2026

Đồng bộ mobile và điều hướng: tài chính mở trong Clinic shell; URL cũ chuyển tới cùng workspace. Thêm 10 hồ sơ tổng hợp P037–P046 theo 10 nhóm CSKH, bổ sung một lần và không sửa 36 hồ sơ hiện có. Patient Mobile dùng bước tiếp theo theo rule, không lộ ghi chú nội bộ. Flutter bổ sung phân vai demo, chọn bệnh nhân theo tình huống và tách state theo patient; CRM native vẫn là template độc lập, không sync localStorage.

UI review CSKH mobile: trạng thái Cần làm / Đã liên hệ / Chờ bác sĩ ở đầu màn; tìm kiếm và nút Lọc mở sheet 10 nhóm, không trải 10 chip lên home. Card đầu nằm trong 440px đầu ở viewport 360; lọc/trạng thái phải thực sự đổi danh sách. Widget `care_workspace.dart` dùng cùng PatientState, ghi chú nội bộ giữ tách Care.
