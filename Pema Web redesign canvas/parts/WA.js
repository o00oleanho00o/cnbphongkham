// WA · Khung & điều hướng. WA1 is the W3a proof screen (the owner shell); WA2-WA4 are filled by W3b-WA.
const WA = [
  // The shell is drawn by page() itself (sidebar by role, top bar, 390 top bar + tab bar); the content area is a placeholder here.
  page('WA1', 'Khung ứng dụng · Chủ phòng khám', WEB + 'app shell · sidebar 3 nhóm 13 mục, thanh trên (đường dẫn, tài khoản demo, tìm bệnh nhân, thông báo, đặt lại); danh sách tài khoản mở sẵn, liên kết "Đến nội dung chính" hiện khi focus; liên kết tài chính có 3 trạng thái ("Tài chính đã đồng bộ", "Đang đồng bộ tài chính…", "Tài chính chờ kết nối · thử lại"); "Đặt lại" hỏi confirm "Đặt lại dữ liệu demo?" rồi báo "Đã khôi phục dữ liệu demo"; ô tìm chỉ chạy khi Enter', 'dashboard', [
    img('Vùng nội dung trang: mỗi trang vẽ ở nhóm WB–WH', { icon: 'web_asset', h: 320 })
  ], { state: true, pickerOpen: true, skip: true }),

  // Care shell: 4 menu items (Điều phối lịch, Tìm bệnh nhân, CSKH hôm nay, Hướng dẫn), finance link (as in the old shot), no bell in the old web, lands on "CSKH hôm nay".
  page('WA2', 'Khung · CSKH (trang chủ CSKH hôm nay)', WEB + 'app shell · vai CSKH (Mai Anh, Thu): sidebar 4 mục (Điều phối lịch, Tìm bệnh nhân, CSKH hôm nay, Hướng dẫn), có liên kết tài chính, không có chuông (khung vẽ chuông ở mọi vai: xem open items); liên kết "Đến nội dung chính" hiện khi focus; vào thẳng "CSKH hôm nay". Nội dung đầy đủ của trang vẽ ở nhóm WD', 'crm', [
    sp(36),
    pageHead('CSKH hôm nay', 'Từ dữ liệu khám đến việc cần làm · ngày demo 20/09/2026', [secondary('Xem protocol')]),
    kpis(
      kpi('Việc CSKH toàn đội', '12', '10 khách cần chăm sóc', { chev: true }),
      kpi('Quá hạn', '5', 'Ưu tiên gọi và xác nhận', { chev: true }),
      kpi('Đã hoàn tất', '4', 'Có kết quả được ghi nhận', { chev: true }),
      kpi('Đặt lịch sau CSKH', '2', 'Chưa đồng nghĩa đã quay lại', { chev: true })),
    img('Nhóm công việc, bộ lọc và danh sách việc: vẽ ở nhóm WD', { icon: 'web_asset', h: 220 })
  ], { role: 'care-maianh', state: true, skip: true, fin: 'Tài chính đã đồng bộ' }),

  // Accountant shell: 4 menu items (Tìm bệnh nhân, Thu ngân, Tài chính & tiền thủ thuật, Hướng dẫn), finance link, no bell, lands on "Thu ngân".
  page('WA3', 'Khung · Kế toán (trang chủ Thu ngân)', WEB + 'app shell · vai Kế toán: sidebar 4 mục (Tìm bệnh nhân, Thu ngân, Tài chính & tiền thủ thuật, Hướng dẫn), có liên kết tài chính, không có chuông (khung vẽ chuông ở mọi vai); liên kết "Đến nội dung chính" hiện khi focus; vào thẳng "Thu ngân". Nội dung đầy đủ của trang vẽ ở nhóm WF', 'cashier', [
    sp(36),
    pageHead('Thu ngân', 'Thu tiền và lên đơn nhanh theo mẫu PEMA.', [primary('Lên đơn nhanh', { icon: 'add' })]),
    kpis(
      kpi('Tổng hóa đơn', '12', 'Dữ liệu giả lập'),
      kpi('Đã thu', money(8400000), 'Tổng lũy kế'),
      kpi('Còn phải thu', money(2100000), 'Không thu trùng'),
      kpi('Catalog sản phẩm', '96', 'Từ danhsach.xlsx')),
    img('Lên đơn theo mẫu PEMA và bảng hóa đơn: vẽ ở nhóm WF', { icon: 'web_asset', h: 220 })
  ], { role: 'accountant', state: true, skip: true }),

  // Toast: div.toast appended to body, removed after 2800 ms. Reached from "Hôm nay" → Check-in; the page behind is the reception list.
  page('WA4', 'Thông báo nổi (toast)', WEB + 'toast · hiện góc dưới phải trên trang "Hôm nay" sau Check-in hoặc Vắng (không mở hộp thoại), tự biến mất sau 2,8 giây; sau Check-in dòng chuyển sang "Bắt đầu". Trang phía sau chỉ để minh họa, đầy đủ ở WB3', 'today', [
    pageHead('Hôm nay tại Pema', 'Tiếp đón theo từng lịch hẹn · dữ liệu tổng hợp 20/09/2026', [primary('Đặt lịch mới', { icon: 'add' })], 'Pema · chăm sóc xuyên suốt'),
    kpis(
      kpi('Tổng lịch', '12'), kpi('Đã đến', '2'), kpi('Chưa đến', '8'), kpi('Đang chờ', '1')),
    kpis(
      kpi('Đang khám/điều trị', '1'), kpi('Hoàn tất', '0'), kpi('Đã hủy', '0'), kpi('Vắng hẹn', '0', '', { tone: 'neutral' })),
    row({ g: 10 }, txt(money(13500000), { size: 'sub', w: 'b' }), sm('Phát sinh hóa đơn hôm nay')),
    panel('', '', [],
      grid(3, search('Tìm nhanh khách…', { label: 'Tên / mã KH / liên hệ' }), select('Trạng thái', 'Tất cả trạng thái'), select('Bác sĩ', 'Tất cả bác sĩ')),
      table(['Giờ', 'Mã KH · Bệnh nhân', 'Nội dung', 'Trạng thái', 'Bác sĩ · Người tạo', ['Giá lịch dự kiến', '', 'r'], ['Tiếp đón', '200px']], [
        ['08:00', [lnk(people[0].name), sm(people[0].id + ' · ' + people[0].phone + ' · ' + people[0].age + ' tuổi')], 'Tái khám & đánh giá\nNám · tăng sắc tố', [badge('Đã đến', 'info')], 'BS. Tâm\nLễ tân', money(300000), [primary('Bắt đầu')]],
        ['08:00', [lnk(people[1].name), sm(people[1].id + ' · ' + people[1].phone + ' · ' + people[1].age + ' tuổi')], 'Tư vấn da liễu\nMụn viêm', [badge('Đang chờ', 'warning')], 'BS. Mai\nLễ tân', money(500000), [primary('Mời vào phòng')]],
        ['08:00', [lnk(people[2].name), sm(people[2].id + ' · ' + people[2].phone + ' · ' + people[2].age + ' tuổi')], 'Laser theo chỉ định\nThăm sau viêm', [badge('Chưa đến', 'neutral')], 'BS. An\nLễ tân', money(2500000), cell([primary('Check-in'), secondary('Vắng')], { row: true })],
        ['09:00', [lnk(people[3].name), sm(people[3].id + ' · ' + people[3].phone + ' · ' + people[3].age + ' tuổi')], 'Chăm sóc theo chỉ định\nĐỏ da / nhạy cảm', [badge('Chưa đến', 'neutral')], 'BS. Lan\nLễ tân', money(1200000), cell([primary('Check-in'), secondary('Vắng')], { row: true })]
      ]))
  ], { state: true, toast: 'Đã cập nhật hàng đợi' })
];
