// WA · Khung & điều hướng. WA1 is the W3a proof screen (the owner shell); WA2-WA4 are filled by W3b-WA.
// W6c-OPS helper (local to this part, prefix wa): the dashboard body that WA5-WA9 draw behind the shell states (same blocks as WB1).
function waDash() {
  return [
    pageHead('Chào buổi sáng, BS. Tâm', 'Vận hành hôm nay và chăm sóc khách hàng · mốc demo 20/09/2026', [secondary('Lịch hôm nay →'), primary('Mở CSKH hôm nay')], 'Pema · chăm sóc xuyên suốt'),
    kpis(
      kpi('Lịch hôm nay', '12', '', { actions: [quiet('Mở tiếp đón →')] }),
      kpi('Đã đến / đang chờ', '3', '', { unit: '/ 3', actions: [quiet('Bàn giao phòng khám →')] }),
      kpi('Vắng hẹn', '1', '', { actions: [secondary('Xử lý vắng hẹn')] }),
      kpi('Phát sinh hôm nay', money(13500000), '', { actions: [quiet('Hóa đơn, không phải thực thu →')] })),
    kpis(
      kpi('Khách cần CSKH', '10', '12 việc đến hạn', { chev: true }),
      kpi('Quá ngày dự kiến', '2', 'Cần hỗ trợ chọn lịch', { chev: true }),
      kpi('Nguy cơ mất khách', '3', 'Quá hạn hoặc bỏ dở', { chev: true }),
      kpi('Liệu trình bỏ dở', '1', 'Còn buổi, >45 ngày', { chev: true })),
    grid('minmax(0,1.65fr) minmax(300px,1fr)',
      panel('Ưu tiên chăm sóc', 'Từ dữ liệu khám và lịch hẹn, có người phụ trách', [secondary('Tất cả →')],
        table(['Khách hàng', ['Việc tiếp theo', '1.2fr'], 'Phụ trách', ['', '88px']], people.slice(0, 5).map((x, i) => [
          [lnk(x.name), sm(x.id)], [txt(x.groupLabel), sm((14 + i) + '/9/2026')], 'CSKH Mai Anh', [secondary('Xử lý')]
        ]))),
      panel('Hiệu quả CSKH', 'Kết quả thực từ hoạt động đã lưu', [],
        facts(['Việc đã hoàn tất', '4'], ['Liên hệ thành công', '75%', { sub: '3/4 lần liên hệ' }], ['Lịch đặt sau CSKH', '2'], ['Đã quay lại thực tế', '1'], ['Việc quá hạn', '5']),
        secondary('Xem nhật ký kết quả'),
        notice('Khách đặt lịch chưa được tính là đã quay lại. Chỉ ghi nhận quay lại khi check-in sau CSKH.'))),
    panel('Vòng đời khách hàng', 'Một hồ sơ, nhiều lần chăm sóc', [],
      grid(5, secondary('3 Khách mới', { full: true }), secondary('2 Khách quay lại', { full: true }), secondary('9 Đang điều trị', { full: true }), secondary('1 Lâu chưa quay lại', { full: true }), secondary('1 Đã quay lại sau CSKH', { full: true })))
  ];
}

const WA = [
  // The shell is drawn by page() itself (sidebar by role, top bar, 390 top bar + tab bar); the content area is a placeholder here.
  page('WA1', 'Khung ứng dụng · Chủ phòng khám', WEB + 'app shell · sidebar 3 nhóm 13 mục, thanh trên (đường dẫn, tài khoản demo, tìm bệnh nhân, thông báo, đặt lại); danh sách tài khoản mở sẵn, liên kết "Đến nội dung chính" hiện khi focus; liên kết tài chính có 3 trạng thái ("Tài chính đã đồng bộ", "Đang đồng bộ tài chính…", "Tài chính chờ kết nối · thử lại"); "Đặt lại" hỏi confirm "Đặt lại dữ liệu demo?" rồi báo "Đã khôi phục dữ liệu demo"; ô tìm chỉ chạy khi Enter', 'dashboard', [
    img('Vùng nội dung trang: mỗi trang vẽ ở nhóm WB–WH', { icon: 'web_asset', h: 320 })
  ], { state: true, pickerOpen: true, skip: true }),

  // Care shell: 4 menu items (Điều phối lịch, Tìm bệnh nhân, CSKH hôm nay, Hướng dẫn), finance link (as in the old shot), no bell in the old web, lands on "CSKH hôm nay".
  page('WA2', 'Khung · CSKH (trang chủ CSKH hôm nay)', WEB + 'app shell · vai CSKH (Mai Anh, Thu): sidebar 4 mục (Điều phối lịch, Tìm bệnh nhân, CSKH hôm nay, Hướng dẫn), có liên kết tài chính, không có chuông (chuông chỉ có ở chủ phòng khám và bác sĩ); liên kết "Đến nội dung chính" hiện khi focus; vào thẳng "CSKH hôm nay". Nội dung đầy đủ của trang vẽ ở nhóm WD', 'crm', [
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
  page('WA3', 'Khung · Kế toán (trang chủ Thu ngân)', WEB + 'app shell · vai Kế toán: sidebar 4 mục (Tìm bệnh nhân, Thu ngân, Tài chính & tiền thủ thuật, Hướng dẫn), có liên kết tài chính, không có chuông (chuông chỉ có ở chủ phòng khám và bác sĩ); liên kết "Đến nội dung chính" hiện khi focus; vào thẳng "Thu ngân". Nội dung đầy đủ của trang vẽ ở nhóm WF', 'cashier', [
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
  ], { state: true, toast: 'Đã cập nhật hàng đợi' }),

  // ---- W6c-OPS: shell states of the owner dashboard (native dialogs, skip link, finance sync) and the native review page ----
  // Native confirm() raised by the reset icon; the page behind is the dashboard the shot shows. Accepting it toasts "Đã khôi phục dữ liệu demo".
  page('WA5', 'Đặt lại dữ liệu demo (hộp xác nhận)', WEB + 'app shell · biểu tượng "Đặt lại" trên thanh trên mở hộp xác nhận của trình duyệt "Đặt lại dữ liệu demo?" (OK / Cancel); bấm OK khôi phục dữ liệu demo, quay về hồ sơ P001 và Tổng quan rồi báo "Đã khôi phục dữ liệu demo"; hộp thoại gốc do trình duyệt vẽ, canvas chú thích đúng văn bản để dựng lại bằng hộp thoại của Next.js', 'dashboard', waDash(), { state: true, native: native('confirm', 'Đặt lại dữ liệu demo?') }),

  // The account picker is a native <select>; the open list is drawn by the browser, the eight options are recorded in the manifest.
  page('WA6', 'Chọn tài khoản demo (danh sách của trình duyệt)', WEB + 'app shell · ô "Tài khoản demo" là <select> gốc: danh sách mở do trình duyệt vẽ nên canvas vẽ đủ 8 tùy chọn theo thứ tự (chủ phòng khám, 4 bác sĩ, 2 CSKH, kế toán); chọn một tài khoản tải lại khung theo vai (WA1, WA2, WA3, WB2); app A6 chọn vai ở màn hình riêng', 'dashboard', waDash(), {
    state: true,
    native: native('select', '', { options: ['BS. Tâm · Chủ phòng khám', 'BS. Tâm · Bác sĩ điều trị', 'BS. Mai · Bác sĩ điều trị', 'BS. An · Bác sĩ điều trị', 'BS. Lan · Bác sĩ điều trị', 'Mai Anh · CSKH', 'Thu · CSKH', 'Kế toán · Đối soát & thu ngân'] })
  }),

  // First Tab press: the skip link appears at the top left of the content column.
  page('WA7', 'Liên kết "Đến nội dung chính" (khi focus bàn phím)', WEB + 'app shell · bấm Tab lần đầu thì liên kết "Đến nội dung chính" hiện ở góc trên trái cột nội dung (khi không focus thì ẩn); app không có vì giao diện cảm ứng, web giữ làm điểm dừng Tab đầu tiên; phần còn lại như WB1', 'dashboard', waDash(), { state: true, skip: true }),

  // finance-bridge.js: the finance API is unreachable, so the topbar link reads "Tài chính chờ kết nối · thử lại" (WA1 shows "Tài chính đã đồng bộ").
  page('WA8', 'Khung · liên kết đồng bộ tài chính chờ kết nối', WEB + 'app shell · liên kết nhỏ trước các nút của thanh trên đọc "Tài chính chờ kết nối · thử lại" khi API tài chính không phản hồi (WA1: "Tài chính đã đồng bộ"); bấm vào mở trang tài chính; app H7 chưa có trạng thái này', 'dashboard', waDash(), { state: true, fin: 'Tài chính chờ kết nối · thử lại' }),

  // The request to the finance API is pending: the link reads "Đang đồng bộ tài chính…" until the 7 s timeout turns it into WA8.
  page('WA9', 'Khung · liên kết đang đồng bộ tài chính', WEB + 'app shell · liên kết đồng bộ đọc "Đang đồng bộ tài chính…" trong lúc yêu cầu tới API tài chính còn treo, quá 7 giây chuyển sang WA8; trang vẫn thao tác được; app không có trạng thái chờ này', 'dashboard', waDash(), { state: true, fin: 'Đang đồng bộ tài chính…' }),

  // Standalone page of the old prototype (native-review/index.html, no clinic shell); the canvas draws it in the shell frame as WF5/WF8 do. The iframe shows the server 404 page.
  page('WA10', 'Duyệt template native Flutter (trang xem trước)', WEB + 'native-review (trang độc lập, chỉ vào được bằng URL, không có thanh bên) · cột trái: logo, tiêu đề, thẻ "FLUTTER TEMPLATE • REVIEW 01", ô chọn "Kích thước duyệt" (4 cỡ), 4 bước duyệt, liên kết "Mở app toàn màn hình ↗" và ghi chú; cột phải: khung điện thoại viền xanh đậm chứa iframe ../native-preview/ (thư mục này không có trong prototype nên khung hiện trang lỗi 404 của máy chủ); dưới 800 px các bước đánh số bị ẩn và khung chiếm hết chiều ngang; canvas vẽ trong khung ứng dụng như WF5 · chưa có trên Next.js', 'dashboard', [
    grid('minmax(0,320px) minmax(0,1fr)',
      stack({ g: 14 },
        img('Pema · clinic & spa', { icon: 'spa', h: 64 }),
        h1('Chăm sóc liên tục. Trải nghiệm native.'),
        eyebrow('FLUTTER TEMPLATE • REVIEW 01'),
        txt('Bản Flutter thật để duyệt bố cục, điều hướng và luồng nghiệp vụ trên điện thoại.', { tone: 'soft' }),
        select('Kích thước duyệt', 'Điện thoại · 390 × 844', { opts: ['Điện thoại · 390 × 844', 'Điện thoại nhỏ · 360 × 800', 'Điện thoại lớn · 430 × 932', 'Tablet · 768 × 1024'] }),
        h2('Bắt đầu duyệt'),
        list(['Clinic → Hồ sơ → Patient 360.', 'Thêm → Lên đơn nhanh → chọn sản phẩm → kiểm tra và duyệt.', 'Nút Clinic ở header → Pema Care → xem đơn đã duyệt.', 'Care gửi cập nhật → Clinic Theo dõi → phản hồi.'], { ordered: true, plain: true }),
        secondary('Mở app toàn màn hình ↗'),
        sm('Lâm sàng dùng dữ liệu mẫu trong phiên. Tài chính Clinic đã dùng API chung với web; camera, PDF/in, AI và push nền chưa tích hợp. Chuyển kích thước giữ nguyên app đang mở.')),
      card({ v: 'soft', g: 8 },
        h2('Error response'),
        txt('Error code: 404'),
        txt('Message: File not found.'),
        txt('Error code explanation: 404 - Nothing matches the given URI.')))
  ])
];
