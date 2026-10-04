// WB · Vận hành: tổng quan, hôm nay, lịch. WB1 is the W3a proof screen (dashboard); WB2-WB9 by W3b-WB.

// ---- shared pieces of the WB screens (data only, built from the block helpers) ----
const WB_STATUS_TILES = [['Chưa đến', 31], ['Đang chờ', 0], ['Đang khám/điều trị', 0], ['Hoàn tất', 0], ['Đã hủy', 0], ['Vắng hẹn', 0]];
const WB_TODAY_COLS = [['Giờ', '52px'], ['Mã KH · bệnh nhân', '1.15fr'], ['Liên hệ', '0.95fr'], ['Nội dung', '1.2fr'], ['Trạng thái', '1.45fr'], ['Bác sĩ', '0.7fr'], ['Người tạo', '0.7fr'], ['Giá lịch dự kiến', '0.95fr'], ['Tiếp đón', '1.7fr']];
const wbRow = (i, st, bs, acts) => {
  const x = people[i], s = services[i % 4];
  return [strong(['08:00', '08:00', '09:00', '09:00', '10:00', '10:00', '11:00', '11:00'][i % 8]), [lnk(x.name), sm(x.id)], [txt(x.phone), sm(x.age + ' tuổi')], [txt(s.name), sm(x.groupLabel || 'Nám · tăng sắc tố')], [badge(st[0], st[1])], bs, 'Lễ tân', money(s.price), cell(acts, { row: true })];
};
// today body: invoice tile, filters, table of the demo day and pagination. o.empty = WB4 (filter "Đã hủy" matches nothing).
const wbToday = o => [
  pageHead('Hôm nay tại Pema', 'Tiếp đón theo từng lịch hẹn · dữ liệu tổng hợp 20/09/2026', [primary('Đặt lịch mới', { icon: 'add' })], 'Pema · chăm sóc xuyên suốt'),
  panel('', '', [],
    grid(4, stat('Tổng lịch', '31'), stat('Đã đến', '0'), ...WB_STATUS_TILES.map(([t, n]) => secondary(n + ' ' + t, { full: true }))),
    hr(),
    row({ g: 14, ai: 'center' }, txt(money(13500000), { size: 'sub', w: 'b' }), sm('Phát sinh hóa đơn hôm nay'))),
  panel('', '', [],
    row({ g: 12, ai: 'flex-end' },
      search('Tìm nhanh khách…', { label: 'Tên / mã KH / liên hệ', w: 360 }),
      select('Trạng thái', o.empty ? 'Đã hủy' : 'Tất cả trạng thái', { w: 240, opts: ['Tất cả trạng thái', 'Chưa đến', 'Đã xác nhận', 'Đang chờ', 'Đang khám/điều trị', 'Hoàn tất', 'Đã hủy', 'Vắng hẹn'] }),
      select('Bác sĩ', 'Tất cả bác sĩ', { w: 220, opts: ['Tất cả bác sĩ', ...doctors.map(d => d.name)] })),
    table(WB_TODAY_COLS, o.empty ? [] : [
      wbRow(0, ['Chưa đến', 'info'], 'BS. Tâm', [primary('Check-in'), secondary('Vắng')]),
      wbRow(1, ['Chưa đến', 'info'], 'BS. Mai', [primary('Check-in'), secondary('Vắng')]),
      wbRow(2, ['Đã xác nhận', 'info'], 'BS. Tâm', [primary('Check-in'), secondary('Vắng')]),
      wbRow(3, ['Đang chờ', 'warning'], 'BS. An', [primary('Mời vào phòng')]),
      wbRow(4, ['Đang khám/điều trị', 'brand'], 'BS. Tâm', [secondary('Mở 360')]),
      wbRow(5, ['Hoàn tất', 'success'], 'BS. Lan', [secondary('Mở 360')]),
      wbRow(6, ['Đã hủy', 'neutral'], 'BS. Lan', [secondary('Mở 360')]),
      wbRow(7, ['Vắng hẹn', 'danger'], 'BS. Tâm', [secondary('Mở 360')])
    ]),
    o.empty && txt('Không có lịch phù hợp.'),
    row({ g: 12, ai: 'center', jc: 'space-between' }, txt(o.empty ? '0 lịch · Trang 1/1 · 25 dòng/trang' : '31 lịch · Trang 1/2 · 25 dòng/trang'), row({ g: 8 }, secondary('← Trước'), secondary('Sau →'))))
];
const wbTodayBehind = () => wbToday({}).slice(0, 2);

// schedule body: view 0 = day board by room, 1 = 7-day list. Right column "Chờ xếp lịch".
const WB_WAIT = [['Có thể đến trong ngày', 0], ['Ưu tiên buổi chiều', 1], ['Có thể đến trong ngày', 2], ['Ưu tiên buổi chiều', 3], ['Có thể đến trong ngày', 0], ['Ưu tiên buổi chiều', 1]];
// Room 1 has 30-minute visits and free half hours (dashed "Đặt lịch" slots), room 2 is free from 11:00; the other rooms book 45 minutes + a 15-minute buffer (hatched block, "· +15′ đệm").
const wbBoard = () => board({
  from: 8, to: 12, hh: 112,
  rooms: rooms.map((r, i) => {
    const bk = [], slots = [];
    for (let h = 0; h < 4; h++) {
      if (i === 1 && h === 3) { slots.push({ start: '11:00', mins: 30 }, { start: '11:30', mins: 30 }); continue; } // room 2 is free from 11:00
      const p = people[(i * 4 + h) % 12], sv = services[(i + h) % 4];
      bk.push({ start: (8 + h) + ':00', mins: i === 0 ? 30 : 45, buf: i > 0 ? 15 : 0, title: p.name, sub: sv.name, sub2: doctors[(i + h) % 4].name + ' · Đặt hẹn', svc: sv.svc });
      if (i === 0) slots.push({ start: (8 + h) + ':30', mins: 30 });
    }
    return { name: r.name, sub: [8, 8, 7, 8][i] + ' lịch · ' + r.sub, bk, slots };
  })
});
const wbWeek = () => weekGrid({
  days: ['CN, 20/09', 'Thứ 2, 21/09', 'Thứ 3, 22/09', 'Thứ 4, 23/09', 'Thứ 5, 24/09', 'Thứ 6, 25/09', 'Thứ 7, 26/09'].map((d, i) => ({
    title: d, sub: [31, 8, 8, 8, 6, 5, 4][i] + ' lịch', add: 'Đặt lịch',
    items: [0, 1, 2].map(j => ({ time: hm(480 + j * 60) + '–' + hm(480 + j * 60 + (j === 0 ? 30 : 45)), title: people[(i + j * 3) % 12].name, sub: services[(i + j) % 4].name, svc: (i + j) % 4 }))
  }))
});
const wbSchedule = view => [
  pageHead('Điều phối lịch', 'Xếp theo phòng, ca bác sĩ và thời lượng. Kéo lịch hoặc mở chi tiết để dời.', [primary('Đặt lịch', { icon: 'add' })]),
  kpis(kpi('Lịch trong ngày', '31'), kpi('Thời gian điều trị', '1275′'), kpi('Chờ xếp lịch', '6'), kpi('Khoảng khóa', '0')),
  row({ g: 10, ai: 'flex-end' },
    secondary('←'), date('Ngày bắt đầu', '2026-09-20', { w: 170 }), secondary('→'), secondary('Mốc demo'),
    tabs(['Ngày', '7 ngày'], view, { seg: true }),
    select('Bác sĩ', 'Tất cả bác sĩ', { w: 180, opts: ['Tất cả bác sĩ', ...doctors.map(d => d.name)] }),
    select('Phòng', 'Tất cả phòng', { w: 200, opts: ['Tất cả phòng', ...rooms.map(r => r.name)] })),
  grid('minmax(0,1fr) 250px',
    panel(view ? '20/9/2026 — 26/9/2026' : '20/9/2026', '08:00–18:00 · bước kéo 30 phút · nhấp thẻ để chỉnh giờ chính xác', [badge(view ? 'Theo ngày' : 'Theo phòng')], view ? wbWeek() : wbBoard()),
    panel('Chờ xếp lịch', 'Chọn hồ sơ để tìm giờ phù hợp', [],
      ...WB_WAIT.map(([note, s], i) => card({ v: 'soft', g: 8 }, row({ g: 8, ai: 'center' }, avatar(people[i].init), strong(people[i].name)), txt(note), sm(services[s].name), secondary('Xếp lịch →'))),
        notice('Màu thẻ phân biệt dịch vụ. Lịch hủy được giữ trong nhật ký; thời gian đệm vẫn chiếm phòng.', 'info')))
];
const wbScheduleBehind = () => wbSchedule(0).slice(0, 2);

// booking form shared by WB7, WB8, WB9 (operations-ui.js edit): patient, 2-column grid, live preview line.
const wbBooking = o => [
  select('Bệnh nhân', people[0].name, { opts: people.slice(0, 8).map(x => x.name) }),
  grid(2,
    select('Dịch vụ', services[0].name, { opts: services.map(s => s.name) }),
    select('Bác sĩ', doctors[0].name, { opts: doctors.map(d => d.name) }),
    select('Phòng', rooms[0].name, { opts: rooms.map(r => r.name) }),
    date('Ngày', '2026-09-20'),
    time('Giờ', o.time),
    input('Ghi chú', o.note)),
  notice('30 phút điều trị + 0 phút chuẩn bị · ' + money(300000) + (o.tail || ''), 'info')
];

const WB = [
  page('WB1', 'Tổng quan', WEB + 'dashboard · bố cục như app I1/A1 ở cỡ web; web có thêm KPI "Quá ngày dự kiến", "Liệu trình bỏ dở" và hai khối "Hiệu quả CSKH", "Vòng đời khách hàng"; tên và số liệu là dữ liệu tổng hợp', 'dashboard', [
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
  ]),

  // WB2 · doctor home (crm-ui.js doctorHome): account BS. Mai sees only her own visits, no CSKH dashboard or clinic finance.
  page('WB2', 'Tổng quan · Bác sĩ', WEB + 'dashboard (tài khoản bác sĩ) · app B1/B2 là không gian bác sĩ dạng mobile; web thêm liên kết "Doanh số của tôi →" sang tài chính; ba KPI là nút mở danh sách; tên và giờ khám là dữ liệu tổng hợp', 'dashboard', [
    pageHead('Không gian bác sĩ · BS. Mai', 'Lịch cá nhân, hồ sơ phụ trách và phản hồi cần xem.', [secondary('Doanh số của tôi →'), primary('Lịch khám của tôi →')], 'Pema · chăm sóc xuyên suốt'),
    kpis(
      kpi('Lịch hôm nay', '8', 'Lịch theo tài khoản bác sĩ', { chev: true }),
      kpi('Hồ sơ phụ trách', '22', 'Patient 360 của bác sĩ', { chev: true }),
      kpi('Cần bác sĩ xem', '2', 'Phản hồi đang mở', { chev: true })),
    panel('Lịch khám của tôi', 'Không bao gồm dashboard CSKH hoặc tài chính toàn phòng khám', [],
      table(['Giờ', 'Bệnh nhân', 'Trạng thái', ['', '120px']], [
        ['08:00', people[1].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]],
        ['09:00', people[5].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]],
        ['10:00', people[9].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]],
        ['11:00', people[3].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]],
        ['13:00', people[8].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]],
        ['14:00', people[11].name, [badge('Chưa đến', 'info')], [secondary('Mở hồ sơ')]]
      ], { foot: '8 lịch khám của BS. Mai' }))
  ], { role: 'doctor-mai', state: true }),

  // WB3 · reception list of the demo day (crm-ui.js today)
  page('WB3', 'Hôm nay', WEB + 'today · app I2 chỉ có "Tổng lịch", "Đang chờ", "Hoàn tất" và chip trạng thái; web có 8 ô tiếp đón (6 ô là nút lọc), ô "Phát sinh hóa đơn hôm nay" (ẩn với bác sĩ), ba bộ lọc, bảng 9 cột, nút Check-in / Vắng / Mời vào phòng / Mở 360 theo trạng thái và phân trang 25 dòng; tên và số liệu là dữ liệu tổng hợp', 'today', wbToday({})),

  // WB4 · filter "Đã hủy" has no match: the table shows its empty row
  page('WB4', 'Hôm nay · lọc không có kết quả', WEB + 'today · ô trạng thái "Đã hủy" đang chọn nên danh sách chỉ còn dòng trống "Không có lịch phù hợp."; mọi phần khác như WB3', 'today', wbToday({ empty: true }), { state: true }),

  // WB5 · schedule, day board by room
  page('WB5', 'Điều phối lịch', WEB + 'schedule · app I3/A2 là dải tuần và danh sách ngày; web là lưới phòng × giờ (kéo thả bằng chuột), chú giải 4 màu dịch vụ và khối "Chờ xếp lịch"; khoảng đệm "15′ chuẩn bị phòng" là khối gạch chéo dưới thẻ lịch, ô trống có nút "Đặt lịch" nét đứt, ghi chú về màu thẻ nằm dưới "Chờ xếp lịch"; bác sĩ đăng nhập bị khóa bộ lọc bác sĩ', 'schedule', wbSchedule(0)),

  // WB6 · schedule, 7-day view
  page('WB6', 'Điều phối lịch · 7 ngày', WEB + 'schedule · nút "7 ngày" đang chọn, huy hiệu "Theo ngày", 7 cột ngày với số lịch, thẻ lịch và "Đặt lịch" cuối mỗi cột; văn bản "Chưa có lịch" của ngày trống chỉ có trong mã (mọi ngày demo đều có lịch)', 'schedule', wbSchedule(1), { state: true }),

  // WB7 · new booking dialog
  dlg('WB7', 'Đặt lịch hẹn', WEB + 'dialog · mở từ Hôm nay (Đặt lịch mới), Điều phối lịch (Đặt lịch, ô trống) và Xử lý CSKH; app I4/F8 là bottom sheet và dải tuần, web là một hộp thoại 8 trường kèm dòng tạm tính và "Tìm giờ trống"; dòng lỗi #ops-error rỗng cho tới khi vi phạm quy tắc nên không vẽ', [
    ...wbBooking({ time: '10:00', note: '' }),
    row({ g: 8 }, primary('Xác nhận đặt lịch'), secondary('Tìm giờ trống'))
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'today', behind: wbTodayBehind() }),

  // WB8 · booking details dialog
  dlg('WB8', 'Chi tiết lịch hẹn', WEB + 'dialog · từ thẻ lịch trong Điều phối lịch: chip trạng thái, Xác nhận lịch, Check-in, Patient 360 →, biểu mẫu đặt lịch (Lưu thay đổi, Tìm giờ trống) và phần hủy lịch có lý do; app F9 không có dòng tạm tính "theo lịch đã đặt"', [
    row({ g: 8, ai: 'center' }, badge('Đặt hẹn', 'neutral'), secondary('Xác nhận lịch'), secondary('Check-in'), secondary('Patient 360 →')),
    ...wbBooking({ time: '08:00', note: 'Lịch giả lập để thử điều phối', tail: ' · theo lịch đã đặt' }),
    row({ g: 8 }, primary('Lưu thay đổi'), secondary('Tìm giờ trống')),
    hr(),
    input('Lý do hủy', ''),
    row({ g: 8 }, btn('Hủy lịch hẹn', 'danger'))
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'schedule', behind: wbScheduleBehind() }),

  // WB9 · the same booking dialog opened from a waiting-list card: patient, service and note prefilled
  dlg('WB9', 'Đặt lịch hẹn', WEB + 'dialog · "Xếp lịch →" trên thẻ chờ xếp lịch mở đúng hộp thoại WB7 với bệnh nhân, dịch vụ và ghi chú lấy từ dòng chờ; lưu xong dòng đó rời danh sách chờ', [
    ...wbBooking({ time: '10:00', note: 'Có thể đến trong ngày' }),
    row({ g: 8 }, primary('Xác nhận đặt lịch'), secondary('Tìm giờ trống'))
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'schedule', behind: wbScheduleBehind() })
];
