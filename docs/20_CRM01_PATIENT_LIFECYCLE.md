# CRM01 — Clinic Replacement + Patient Lifecycle

> **Hiện trạng Mobile CRM02 (22/09/2026):** tài chính trong Clinic shell, 46 hồ sơ mẫu/10 nhóm chăm sóc; Flutter phân workspace và tách state theo patient. Các mô tả state chung hoặc chưa có native CRM phía dưới là baseline trước bản mở rộng này. Xem [hướng dẫn cập nhật](25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).


Ngày triển khai: 22/09/2026. Mốc nghiệp vụ demo: **20/09/2026**, độc lập ngày máy.

## Mục tiêu và phạm vi

Đạt parity các luồng khám cốt lõi trước, sau đó nối dữ liệu khám với chăm sóc chủ động. Patient 360 là hồ sơ chung; mỗi bộ phận có không gian làm việc riêng. Đây là prototype chạy được bằng vanilla JS/localStorage, không phải chứng nhận đủ thay VTTECH trong vận hành thật.

Giữ bản mới nhất của dự án gồm catalog/đơn A5, Flutter template và tài chính PB02. CRM01 chỉ mở rộng Clinic Web và Patient Mobile web; không viết lại Flutter hoặc commission engine. PB02 vẫn có API/SQLite riêng, không bị chuyển về localStorage.

## Tài khoản và cách tổ chức công việc

Chọn **Tài khoản demo** trên thanh đầu trang. Vai trò lưu trong phiên tab, không yêu cầu mật khẩu giả.

| Tài khoản | Điểm bắt đầu | Công việc | Ranh giới |
|---|---|---|---|
| BS. Tâm — Chủ phòng khám | Tổng quan | Toàn phòng khám, hiệu quả CSKH, đi vào tài chính PB02 | Góc quản trị riêng, không mặc định áp cho mọi bác sĩ |
| BS. Tâm/Mai/An/Lan — Bác sĩ | Không gian bác sĩ | Lịch được phân công, hồ sơ phụ trách, lâm sàng, inbox, doanh số cá nhân | Không có CSKH toàn đội, thu ngân, cấu hình dịch vụ |
| Mai Anh/Thu — CSKH | CSKH hôm nay | Nhận việc, xem bối cảnh, ghi kết quả, đặt lại lịch, chuyển bác sĩ | Không duyệt chẩn đoán/đơn, không thu tiền hay xem dashboard tài chính phòng khám |
| Kế toán | Thu ngân | Hóa đơn, thu tiền, mở đối soát/tiền thủ thuật PB02 | Không có hàng đợi CSKH hoặc tác vụ lâm sàng |

BS. Tâm có thể xem toàn bộ bằng vai chủ và chuyển sang bác sĩ để tập trung khám. Không gian là phân vai UI/command demo; người có quyền truy cập browser vẫn có thể đọc/sửa dữ liệu hoặc đổi role. Pilot cần tài khoản nhân viên thật, server authorization, nhật ký đăng nhập, quyền theo cơ sở và truy cập theo hồ sơ.

## Mapping thay thế VTTECH

| Nhóm nghiệp vụ tham chiếu | Pema hiện tại | Phần chưa tuyên bố parity |
|---|---|---|
| Lịch trong ngày nhiều dòng | Appointment-based reception, tìm/lọc bác sĩ/trạng thái, 25 dòng/trang, sticky header, scroll bảng, check-in/mời vào | Test 200 dòng là tải UI cô lập, không phải 200 lịch hợp lệ với bốn phòng/bác sĩ |
| Lịch cá nhân | Day/week, bác sĩ/phòng, conflict/buffer/waitlist | Chưa có calendar tháng, ca nghỉ đa cơ sở production |
| Hồ sơ đa tab | Tổng quan, Tư vấn/tiền sử/chẩn đoán, Kế hoạch, Buổi, Ảnh, Dịch vụ & tài chính, CRM & CSKH, Lịch sử | Không clone 15 tab; bảo hiểm, loyalty, bệnh án điện tử pháp lý, trả kết quả có chữ ký chưa triển khai |
| Dịch vụ/liệu trình | Giá chốt, giảm giá, tiến độ, hóa đơn liên kết, người phụ trách | Chưa thẻ trả trước/combo engine hoàn chỉnh |
| Đơn thuốc | Draft → bác sĩ duyệt → Patient Mobile; lên đơn catalog, in A5 tách loại | Chưa tồn kho/cấp thuốc và chứng từ kế toán production |
| Tài chính | Hóa đơn/cọc/phiếu thu; PB02 tài chính và tiền thủ thuật riêng | MISA, hoàn tiền, kế toán pháp định chưa tích hợp |
| CRM | Rule → task → interaction → booking → check-in → đo kết quả | Zalo/Pancake/Pushsale/SMS/MISA chỉ là boundary cho pilot |

## Expected Next Visit

`patient.crm` lưu source, owner, first contact, recommendationAt, expectedNextVisitAt, lý do, nguồn, overdueDays, lifecycleStage, riskLevel, lastContactAt, nextActionAt/type, marketingOptOut và mốc tái kích hoạt.

Ngày hẹn thực tế sắp tới ưu tiên khuyến nghị. Hủy lịch quay về khuyến nghị; không giả định hủy là đã khám. Bác sĩ chỉnh ngày dự kiến ở Patient 360 hoặc khi ghi buổi. Protocol Laser CO2 gợi D+30 sau buổi; ngày hiển thị có nguồn rõ. `overdueDays = max(0, ngày demo − ngày dự kiến)`.

Khách có nguy cơ nếu chưa có lịch mới và quá hạn >7 ngày hoặc còn buổi mà >45 ngày chưa điều trị. Khách được đặt lịch lại vẫn chưa được tính đã quay lại: check-in ngày thực tế của demo mới ghi `reactivatedAt`.

## Protocol và tự sinh công việc

`crm-data.js` sở hữu fixture/clock/migration; `crm-automation.js` sở hữu rule, task và read model. UI không tự tính lại công thức.

| Trigger/điều kiện | Hạn | Hành động |
|---|---|---|
| Session có protocol Laser CO2 hoàn tất | D+1 | Hỏi tình trạng |
| Cùng session | D+3 | Mời gửi cập nhật/ảnh có consent qua Patient Mobile |
| Cùng session | D+7 | Bác sĩ review; không tự duyệt ảnh |
| Cùng session | D+30 | Expected next visit; đến/quá hạn vào queue |
| Expected visit hôm nay/quá ngày | Ngày dự kiến | Xác nhận hoặc giúp đặt lại lịch |
| Hủy/no-show ít nhất 24h và không có lịch mới | Sau sự kiện | Recall |
| Còn buổi, >45 ngày chưa session, chưa đặt lại | D+45 | Nguy cơ bỏ liệu trình |
| Chưa visit 90/180 ngày, chưa đặt lại | D+90/D+180 | Reconnect; 180 thay nhóm 90 |
| Sinh nhật trong 7 ngày | Ngày sinh nhật | Chăm sóc, bao gồm đổi năm |

Task D+1/D+3/D+7 được tạo với hạn tương lai ngay khi hoàn tất session; chọn **Tất cả, gồm đã hẹn lại** để xem. Queue mặc định chỉ đến hạn và sinh nhật tuần. Rule chỉ tạo tác vụ nhân viên, không gửi ra ngoài. Chạy lại lúc render/command, không có scheduler khi browser đóng.

Khóa idempotency là rule + patient + source event. Task resolved giữ lại nên refresh không tạo trùng. Nguồn đổi (đã có lịch mới, mốc mới, opt-out marketing) chuyển task không còn phù hợp sang superseded, có lý do. Mốc D1/D3/D7 chỉ áp session có protocol đã chọn, không suy mọi lần khám đều là laser.

Opt-out chặn reconnect/sinh nhật. Việc lâm sàng không bị xóa ngầm; nhân viên cần theo SOP liên hệ an toàn. Khách có triệu chứng/khiếu nại được chuyển sang Follow-up Inbox đang mở, có source activity, chưa review.

## Xử lý CSKH và bàn giao

1. Tại CSKH hôm nay, chọn nhóm, người phụ trách, thời hạn; tìm tên/mã. Hàng có bối cảnh số buổi, tổng đã thu, lần liên hệ và hành động đề xuất.
2. Mở **Xử lý**: xem lần khám, liệu trình còn lại, expected visit và kết quả gần nhất.
3. Chọn Gọi điện/Zalo/SMS/Ghi chú nội bộ; ghi kết quả và nội dung thực tế của tình huống mô phỏng.
4. Không nghe máy/gọi lại/bận cần ngày giờ tiếp theo. Task chuyển rescheduled; giữ timeline và rời danh sách đến hạn nếu sang ngày sau.
5. Đồng ý đặt lịch mở form của module lịch, prefill đúng patient. Lưu qua kiểm tra bác sĩ/phòng/ca/buffer/patient. Khi lỗi hoặc đóng form, task chưa resolved.
6. Khi lịch lưu thành công, một transaction ghi appointment, activity, related task và ngày dự kiến. Không có trạng thái “đã chăm sóc thành công” trước khi lưu.

Kênh trong workspace chỉ ghi log, không có lệnh gửi Zalo/SMS hay gọi điện thật. Ghi chú CSKH nội bộ không tự xuất bản vào hướng dẫn người bệnh. Patient Mobile giữ đơn đã duyệt, lịch, aftercare và cập nhật có consent.

## Patient 360 và lịch sử

CRM & CSKH gom source, first contact, lần khám, người phụ trách, mốc dự kiến, risk, open/rescheduled tasks và activity. Lịch sử hợp nhất chiếu events lâm sàng, appointments, phiếu thu và CRM activities, có id/actor/ngày/record liên quan. Tư vấn có form tiền sử và nhận định/chẩn đoán do bác sĩ nhập và xác nhận; không có AI tự chẩn đoán.

Dịch vụ/đơn/in vẫn dùng panel và command PB01. `servicePlan.economics` mở boundary consultant/doctor/technician/serviceValue/commissionRuleId/consumables; field chưa biết để null, không suy đoán nhân viên hoặc đồng bộ tiền thủ thuật PB02 từ chủ hồ sơ.

## Chỉ số quản lý và định nghĩa

- Lịch hôm nay đếm appointment đúng ngày, gồm trạng thái, không đếm `patient.next`.
- Phát sinh đếm tổng hóa đơn tạo trong ngày; nhãn khác thực thu và giá dự kiến của lịch.
- Việc cần xử lý, đã hoàn tất, quá hạn tính từ task; khách cần chăm sóc deduplicate theo patient.
- Contact rate = lần liên hệ có kết quả khác không nghe máy/sai số ÷ tổng lần liên hệ ngoài ghi chú nội bộ. Đây là kết quả nhân viên ghi, không bằng chứng delivery provider.
- Booked-after-CSKH đếm activity có appointment. Reactivated chỉ có check-in thực tế sau tác vụ reconnect; không tính ngay lúc booking.
- Lifecycle: mới, quay lại, đang điều trị, dormant, reactivated. Card mở danh sách hồ sơ; card công việc mở queue hoặc activity.

## Tám câu chuyện sau reset

| Hồ sơ | Câu chuyện |
|---|---|
| P025 | Laser CO2 hôm qua → D+1 |
| P026 | Laser D+3 → gửi ảnh qua Patient Mobile → Follow-up Inbox |
| P027 | Quá ngày dự kiến 14 ngày |
| P028 | Vắng hẹn hai ngày, chưa hẹn lại |
| P029 | Còn 3/6 buổi, 60 ngày không quay lại |
| P030 | Khách cũ 180 ngày |
| P031 | Reconnect → đồng ý → tạo lịch |
| P032 | Sinh nhật trong tuần, đồng thời có D+7 review |

Mốc CRM01 ban đầu giữ 36 bệnh nhân, 84 appointment. Mobile CRM02 bổ sung 10 hồ sơ và một lịch vắng hẹn, thành 46 bệnh nhân/85 appointment khi seed mới. Những case chưa đặt lại có lịch chuyển vào lịch sử hủy/vắng; ngày demo còn 31 lịch active. Tests cũ đổi số kỳ vọng 36→31 ở lịch hôm nay và 21→18 ở week doctor D1; các kiểm tra xung đột/thanh toán vẫn giữ. Migration giữ nguyên hồ sơ người dùng: bổ sung CRM fields và 10 tài khoản tổng hợp một lần, tránh va chạm ID. Muốn tám case, dùng reset có chủ ý; reset xóa dữ liệu thử ở browser này, không reset SQLite PB02.

## Demo 5 phút cho chủ phòng khám

**Phút 1:** chọn BS. Tâm — Chủ phòng khám, mở Tổng quan. Đi từ số khách cần chăm sóc tới việc cụ thể; giải thích phát sinh khác thực thu.

**Phút 2:** mở P029, CRM & CSKH. Xem còn ba buổi, lần khám và ngày dự kiến đã quá hạn. Mở Kế hoạch hoặc Lịch sử nếu cần bối cảnh.

**Phút 3:** chuyển Mai Anh — CSKH. Màn bắt đầu là hàng đợi công việc, không phải tài chính. Chọn 90 ngày chưa quay lại, mở P031.

**Phút 4:** chọn Đồng ý đặt lịch, nhập kết quả, tiếp tục form lịch. Chọn 27/09/2026 10:00, bác sĩ/phòng phù hợp; lưu. Kiểm lịch mới xuất hiện trên Patient Mobile khi chọn P031.

**Phút 5:** chuyển về chủ phòng khám. Booking tăng, task liên quan giảm, activity lưu. Đổi BS. Mai để thấy lịch và hồ sơ cá nhân, không dashboard CSKH/thu ngân. Nhấn mạnh “đã đặt lịch” chưa phải “đã quay lại”.

## Kiểm thử, bằng chứng và giới hạn

Domain: `node prototype/crm-test.cjs`. Browser flows A/B/C, ảnh D+3, role workspace, 35 tổ hợp layout, bảng 200 dòng: `node prototype/crm-browser-test.cjs`. Regression: check-linked, review-desktop, operations-test, smoke-final, data-audit, order-test và finance_test.py. Kết quả chạy và ảnh tại [crm01](../demo-assets/screenshots/crm01/crm-results.json), [domain](../demo-assets/screenshots/crm01/crm-domain-results.json). Trạng thái cuối ghi trong SECTION_PROGRESS.

Bảng 200 dòng được dựng riêng trong context test và reset sau kiểm; không dùng để chứng minh bốn bác sĩ có thể nhận 200 lịch dài 30–45 phút/ngày. Screenshot này ghi tải UI, không claim scheduling capacity. Review responsive ở 1920×1020, 1440×900, 1280×720, 1024×768 và 390×844; table cuộn trong container, không cuộn cả document.

Chưa có auth thật, đa thiết bị, job nền, tích hợp hệ thống ngoài, AI model thật, cấp thuốc/kho, bảo hiểm, loyalty hay native CRM. Chưa đo usability với nhân viên thật. Rule/threshold/consent và chính sách nhận định/chăm sóc cần xác nhận trước pilot. Cần outbox/idempotency server, version/concurrency, identity/RBAC, audit bền vững và nghiệm thu dữ liệu khi thay hệ thống đang vận hành.


## Review UI/UX và acceptance cuối

Đã xem trực tiếp ảnh dashboard, bảng tiếp đón, Patient 360 CRM, queue, workspace desktop/390px, timeline, form booking, mobile sau đặt lịch và các tài khoản. Giữ xanh Pema/Be Vietnam Pro; layout desktop dùng hết workspace, bảng tự cuộn; modal mobile cuộn riêng, không tràn trang. Sau review đã sửa vị trí cuộn khi chuyển tài khoản, ẩn nhóm menu rỗng, badge theo bác sĩ, phân biệt count toàn đội và bộ lọc nhân viên, đồng bộ trạng thái Patient 360 với appointment, và sửa projection đơn mobile theo identity. Bộ test CRM chạy lại sau chỉnh.

AC-CRM01–06: domain + browser queue/workspace/booking; AC-CRM07: metrics before/after trong Flow B/C; AC-CRM08: browser Flow A cùng linked/order/smoke regression; AC-CRM09: chuyển tài khoản và command denial trong browser. Đây là nghiệm thu kỹ thuật prototype, chưa phải usability study hoặc nghiệm thu thay thế hệ thống thật.
