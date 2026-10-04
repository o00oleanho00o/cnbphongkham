// WE · Ảnh, bác sĩ & phòng, dịch vụ (W3b-WE). WE1-WE2 studio, WE3-WE4 doctors, rooms and room blocks, WE5-WE6 services.
// Helpers local to this part are prefixed WE_ so they cannot clash with another group's part.
const WE_STUDIO_HEAD = pageHead('Ảnh trước / sau', 'Ảnh theo cùng view và mốc điều trị giúp bác sĩ xem tiến triển trong ngữ cảnh.', [secondary('Nhập ảnh', { icon: 'add' })], 'Pema Digital Clinic');
const WE_ANGLES = ['Chính diện', 'Má trái', 'Má phải'];
const WE_ALIGN = 'Chưa có ảnh upload ở góc này. Hai ảnh dưới đây là minh họa tổng hợp. Chưa kiểm định căn chỉnh ảnh; bác sĩ kiểm tra điều kiện chụp trước khi so sánh.';
const WE_META = 'Metadata: vùng Mặt; góc Chính diện; mốc buổi minh họa; đồng ý chăm sóc: có ghi nhận. Không suy ra hiệu quả y khoa từ các ảnh minh họa.';
const WE_TOOLBAR = mode => row({ g: 20, jc: 'space-between', ai: 'center' },
  h3('Before / After Studio', pt.name + ' · Nám · tăng sắc tố'),
  row({ g: 8, jc: 'flex-end' }, select('Góc ảnh so sánh', WE_ANGLES[0], { opts: WE_ANGLES, hint: 'Chính diện · Má trái · Má phải', w: 200 }), secondary(mode), primary('Thêm ảnh', { icon: 'add' })));

// Doctors: load of the shown day (old operations-ui.js resources(): lịch, phút điều trị, ca 540 phút).
const WE_LOAD = [[8, 240], [8, 360], [7, 315], [8, 360]];
const WE_DOCTOR_CARDS = grid({ cols: 'repeat(auto-fill,minmax(380px,1fr))', colsn: '1fr', g: 20 }, ...doctors.map((d, i) =>
  card({ title: d.name, sub: d.spec + ' · lịch ngày 20/9/2026', aside: [ico('stethoscope', { size: 24, tone: 'info' })] },
    bars(['08:00–18:00', 'Nghỉ 12:00–13:00', Math.min(100, WE_LOAD[i][1] / 540 * 100), 'info']),
    list([{ t: WE_LOAD[i][0] + ' lịch · ' + WE_LOAD[i][1] + ' phút điều trị / 540 phút ca', actions: [secondary('Xem lịch bác sĩ')] }], { plain: true }))));
const WE_RESOURCES = [
  pageHead('Bác sĩ & phòng', 'Ca làm việc và khoảng khóa được kiểm tra khi đặt hoặc dời lịch.', [primary('Khóa phòng', { icon: 'add' })], 'Vận hành · dữ liệu giả lập'),
  row({ g: 10, ai: 'flex-end' }, date('Ngày xem tải lịch', '2026-09-20', { w: 180 })),
  WE_DOCTOR_CARDS,
  panel('Khoảng khóa phòng', 'Thêm khoảng khóa nếu không vướng lịch hiện tại', [],
    table(['Phòng', 'Ngày', 'Thời gian', 'Lý do', ['', '120px']],
      [[rooms[2].name, '21/9/2026', '14:00–15:00', 'Bảo trì thiết bị laser', [secondary('Gỡ khóa')]]],
      { foot: 'Khi chưa có khoảng khóa, bảng hiện một dòng: "Không có khoảng khóa."' }))
];

// Services: price, duration and buffer of the sample services; the 4th is paused to show both statuses.
const WE_BUFFER = [0, 15, 15, 15];
const WE_SERVICE_CARDS = grid({ cols: 'repeat(auto-fill,minmax(380px,1fr))', colsn: '1fr', g: 20 }, ...services.map((s, i) =>
  card({ title: s.name, aside: [ico('favorite', { size: 22, tone: 'info' }), i === 3 ? badge('Tạm ngưng', 'warning') : badge('Đang dùng', 'success')] },
    h2(money(s.price)),
    list([{ t: s.mins + ' phút điều trị', sub: WE_BUFFER[i] + ' phút chuẩn bị phòng', actions: [secondary('Chỉnh dịch vụ')] }], { plain: true }))));
const WE_SERVICES = [
  pageHead('Danh mục dịch vụ', 'Giá và thời lượng dùng cho lịch mới. Lịch đã đặt giữ giá và thời lượng tại lúc đặt.', [], 'Vận hành · dữ liệu giả lập'),
  WE_SERVICE_CARDS
];

const WE = [
  page('WE1', 'Ảnh trước / sau', WEB + 'studio · bố cục như app I7 ở cỡ web; web có thêm nút "Nhập ảnh", "So sánh trượt", ô "Phóng to" và dòng metadata; ảnh chỉ là minh họa tổng hợp, không chấm hiệu quả · chưa có trên Next.js', 'studio', [
    WE_STUDIO_HEAD,
    card({ g: 16 },
      WE_TOOLBAR('So sánh trượt'),
      hr(),
      notice(WE_ALIGN, 'info'),
      photos([{ label: 'MINH HỌA TRƯỚC', meta: 'Chính diện · đồng ý chăm sóc: có ghi nhận' }, { label: 'MINH HỌA SAU', meta: 'Chính diện · đồng ý chăm sóc: có ghi nhận' }], { n: 2 }),
      box('info', row({ g: 16, jc: 'space-between' }, range('Phóng to', '1×', 0, { w: 260 }), tags(badge('Cùng góc khai báo · không tự căn chỉnh', 'neutral', { dot: false })))),
      notice(WE_META, 'info'))
  ]),
  page('WE2', 'Ảnh trước / sau · so sánh trượt', WEB + 'studio › So sánh trượt · một ảnh với lớp ảnh "trước" cắt theo thanh trượt; nút đổi thành "Đặt cạnh nhau"; hai thanh "Phóng to" và "Vị trí so sánh"; ảnh minh họa, không chấm hiệu quả · chưa có trên Next.js', 'studio', [
    WE_STUDIO_HEAD,
    card({ g: 16 },
      WE_TOOLBAR('Đặt cạnh nhau'),
      hr(),
      notice(WE_ALIGN, 'info'),
      photos([{ label: 'Trước ← → Sau', meta: 'Chính diện · đồng ý chăm sóc: có ghi nhận', slider: true }], { n: 1 }),
      box('info', row({ g: 16, jc: 'space-between' }, range('Phóng to', '1×', 0, { w: 260 }), range('Vị trí so sánh', '50', 50, { w: 260 }))),
      notice(WE_META, 'info'))
  ], { state: true }),
  page('WE3', 'Bác sĩ & phòng', WEB + 'resources · thẻ bác sĩ có ca làm, giờ nghỉ, tải lịch theo ngày và bảng khoảng khóa phòng; app F14 chỉ liệt kê bác sĩ và một dòng khóa phòng · chưa có trên Next.js', 'resources', WE_RESOURCES),
  dlg('WE4', 'Khóa thời gian phòng', WEB + 'resources › Khóa phòng · chỉ chủ phòng khám (quyền cấu hình); app I8 cùng các trường · chưa có trên Next.js', [
    select('Phòng', rooms[0].name, { opts: rooms.map(r => r.name), open: true, w: 560 }),
    date('Ngày', '2026-09-20'),
    grid(2, time('Từ', '14:00'), time('Đến', '15:00')),
    input('Lý do', 'Bảo trì thiết bị')
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'resources', behind: WE_RESOURCES, footer: [primary('Lưu khoảng khóa')] }),
  page('WE5', 'Dịch vụ', WEB + 'services · thẻ dịch vụ có giá, phút điều trị, phút chuẩn bị phòng và trạng thái; web sửa được (chủ phòng khám), app F13 chỉ đọc; thẻ thứ 4 để "Tạm ngưng" nhằm hiện đủ hai trạng thái · chưa có trên Next.js', 'services', WE_SERVICES),
  dlg('WE6', 'Chỉnh dịch vụ', WEB + 'services › Chỉnh dịch vụ · chỉ chủ phòng khám (quyền cấu hình); app I9 cùng các trường · chưa có trên Next.js', [
    input('Tên dịch vụ', services[0].name),
    grid(2, number('Điều trị (phút)', String(services[0].mins)), number('Chuẩn bị (phút)', '0'),
      number('Giá (VND)', String(services[0].price)), select('Trạng thái', 'Đang dùng', { opts: ['Đang dùng', 'Tạm ngưng'], open: true }))
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'services', behind: WE_SERVICES, footer: [primary('Lưu dịch vụ')] })
];
