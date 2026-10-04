// WD · CSKH: hàng chờ CSKH hôm nay, hộp thoại Xử lý, protocol, kết quả, nhóm vòng đời, Theo dõi (Follow-up Inbox) và duyệt phản hồi (W3b-WD).
// Helpers below are local to this part (prefix wd) because every part shares one scope when the canvas is built.
const WD_OWNERS = ['CSKH Mai Anh', 'CSKH Thu', 'BS. Tâm', 'BS. Mai', 'BS. An', 'BS. Lan'];
const WD_GROUPS = [['Sau thủ thuật D+1', 6], ['D+3 cần ảnh', 4], ['D+7 bác sĩ review', 2], ['Đến hạn tái khám', 32], ['Quá hạn tái khám', 10], ['Vắng/hủy chưa đặt lại', 6], ['Nguy cơ bỏ liệu trình', 6], ['90 ngày chưa quay lại', 2], ['180 ngày chưa quay lại', 2], ['Sinh nhật trong tuần', 2]];
const WD_COLS = [['Khách hàng / bối cảnh', '1.35fr'], ['Lý do & bước đề xuất', '1.35fr'], ['Hạn xử lý', '0.8fr'], ['Phụ trách', '1.1fr'], ['', '104px']];

// One CSKH row: patient link + context + case badge | reason, step, priority | due + lateness | owner + last contact | Xử lý →
const wdRow = (p, sessions, paid, caseTxt, reason, step, due, late, owner) => [
  [lnk(p.name), sm(p.id + ' · Còn ' + sessions + ' buổi · ' + money(paid) + ' đã thu'), badge(caseTxt, 'neutral', { dot: false })],
  [strong(reason), sm(step), badge('Ưu tiên cao', 'warning')],
  [txt(due), sm(late)],
  [txt(owner), sm('Liên hệ gần nhất: Chưa thiết lập')],
  [primary('Xử lý →')]
];

const wdHead = () => pageHead('CSKH hôm nay', 'Từ dữ liệu khám đến việc cần làm · ngày demo 20/09/2026', [secondary('Xem protocol')], 'Pema · chăm sóc xuyên suốt');
const wdKpis = () => kpis(
  kpi('Việc CSKH toàn đội', '72', '46 khách cần chăm sóc', { chev: true, btn: true }),
  kpi('Quá hạn', '31', 'Ưu tiên gọi và xác nhận', { chev: true, btn: true }),
  kpi('Đã hoàn tất', '0', 'Có kết quả được ghi nhận', { chev: true, btn: true }),
  kpi('Đặt lịch sau CSKH', '0', 'Chưa đồng nghĩa đã quay lại', { chev: true, btn: true }));
const wdGroupsPanel = () => panel('Nhóm công việc', '', [],
  chips([['Tất cả · 72', 'sel']].concat(WD_GROUPS.map(([t, n]) => [t, '', n])), { vert: true }),
  notice('Theo dõi lâm sàng và CSKH là hai hàng đợi riêng. Phản hồi cần bác sĩ sẽ được chuyển sang Theo dõi.', 'info'));
const wdToolbar = (query) => row({ g: 12, ai: 'flex-end' },
  search('Tên hoặc mã hồ sơ…', { label: 'Tìm khách / lý do', w: 340, val: query }),
  select('Phụ trách', 'Tất cả nhân viên', { w: 200, opts: ['Tất cả nhân viên'].concat(WD_OWNERS) }),
  select('Thời hạn', 'Đến hạn + sinh nhật tuần', { w: 240, opts: ['Đến hạn + sinh nhật tuần', 'Tất cả, gồm đã hẹn lại'] }));
const wdPager = (text) => row({ g: 12, jc: 'space-between' }, txt(text), row({ g: 8 }, secondary('← Trước'), secondary('Sau →')));
const wdQueueRows = () => [
  wdRow(people[0], 2, 2100000, '08 · Sinh nhật tuần này', 'Sau thủ thuật D+1', 'Hỏi tình trạng sau thủ thuật', '14/9/2026', 'Trễ 6 ngày', 'CSKH Mai Anh'),
  wdRow(people[1], 3, 0, 'D+7 bác sĩ review', 'Sau thủ thuật D+1', 'Hỏi tình trạng sau thủ thuật', '14/9/2026', 'Trễ 6 ngày', 'CSKH Thu'),
  wdRow(people[0], 2, 2100000, '08 · Sinh nhật tuần này', 'D+3 cần ảnh', 'Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile', '16/9/2026', 'Trễ 4 ngày', 'CSKH Mai Anh'),
  wdRow(people[2], 1, 1500000, '02 · D+3 gửi ảnh', 'D+3 cần ảnh', 'Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile', '16/9/2026', 'Trễ 4 ngày', 'CSKH Thu'),
  wdRow(people[3], 4, 3200000, '01 · Sau Laser CO2 D+1', 'Sau thủ thuật D+1', 'Hỏi tình trạng sau thủ thuật', '19/9/2026', 'Trễ 1 ngày', 'BS. Tâm'),
  wdRow(people[4], 2, 800000, 'D+3 cần ảnh', 'D+7 bác sĩ review', 'Chuyển bác sĩ xem ảnh và phản hồi', '20/9/2026', 'Đến hạn hôm nay', 'BS. Mai'),
  wdRow(people[5], 1, 600000, 'Sau thủ thuật D+1', 'Sau thủ thuật D+1', 'Hỏi tình trạng sau thủ thuật', '20/9/2026', 'Đến hạn hôm nay', 'CSKH Mai Anh')
];
// Queue body shared by WD1, WD8 and the dialogs drawn over it.
const wdQueue = () => [
  wdHead(), wdKpis(),
  grid('238px minmax(0,1fr)', wdGroupsPanel(),
    panel('Danh sách cần chăm sóc', '72 việc · không gửi tin tự động', [], wdToolbar(''), table(WD_COLS, wdQueueRows()), wdPager('72 việc · Trang 1/6')))
];
const wdQueueEmpty = () => [
  wdHead(), wdKpis(),
  grid('238px minmax(0,1fr)', wdGroupsPanel(),
    panel('Danh sách cần chăm sóc', '0 việc · không gửi tin tự động', [], wdToolbar('zzzz'), table(WD_COLS, []),
      empty('Không có việc phù hợp. Thử nhóm khác hoặc xem các việc đã hẹn lại.'), wdPager('0 việc · Trang 1/1')))
];

// Follow-up Inbox cards: [dot flag, title, patient, text, date + owner, attachment chip?]
const wdFollowCards = () => [
  ['link', 'Ảnh cần bác sĩ xem', people[0].name, 'Đỏ nhẹ đã giảm, không đau. Em gửi ảnh trước buổi hẹn.', '20/9/2026   •   Giao: BS. Tâm', true],
  ['danger', 'Phản hồi triệu chứng', people[5].name, 'Rát tăng lên sau chăm sóc, muốn được phòng khám gọi lại.', '20/9/2026   •   Giao: BS. Tâm', false],
  ['warning', 'Quá hạn phản hồi 3 ngày', people[4].name, 'Chưa có phản hồi kiểm tra sau buổi điều trị.', '17/9/2026   •   Giao: CSKH Thu', false],
  ['soft', 'Thiếu ảnh mốc đánh giá', people[6].name, 'Chưa lưu bộ ảnh chính diện của buổi 2.', '20/9/2026   •   Giao: CSKH Mai Anh', false],
  ['link', 'Kiểm tra chăm sóc ngày 2', people[9].name, 'Da ổn, hơi khô. Đã dùng dưỡng ẩm như hướng dẫn.', '20/9/2026   •   Giao: BS. Tâm', true]
].map(([dot, title, who, text, meta, attach]) => card({ v: 'panel', g: 8 },
  row({ g: 16, jc: 'space-between', ai: 'center' },
    stack({ g: 4 },
      txt([['● ', dot], [title + ' · ' + who, 'b']]),
      txt(text),
      attach ? row({ g: 12 }, sm(meta), badge('Ảnh đính kèm', 'neutral', { dot: false })) : sm(meta)),
    row({ g: 8 }, secondary('Mở'), primary('Xử lý', { icon: 'check' })))));
const wdFollow = () => [
  pageHead('Follow-up Inbox', 'Một hàng đợi cho ảnh bệnh nhân gửi, triệu chứng và các mốc bị bỏ sót.', [], 'Pema Digital Clinic'),
  kpis(kpi('Đang mở', '5', 'tất cả nhóm', { icon: 'tune' }), kpi('Cần bác sĩ', '3', 'ảnh và triệu chứng', { icon: 'tune' }), kpi('Mốc bị bỏ sót', '2', 'cần giao người phụ trách', { icon: 'tune' })),
  chips([['Tất cả', 'sel', 5], ['Ảnh', '', 2], ['Triệu chứng', '', 1], ['Quá hạn', '', 1]]),
  wdFollowCards()
];

const wdDash = () => [
  pageHead('Chào buổi sáng, BS. Tâm', 'Vận hành hôm nay và chăm sóc khách hàng · mốc demo 20/09/2026', [secondary('Lịch hôm nay →'), primary('Mở CSKH hôm nay')], 'Pema · chăm sóc xuyên suốt'),
  kpis(kpi('Lịch hôm nay', '12'), kpi('Đã đến / đang chờ', '3', '', { unit: '/ 3' }), kpi('Vắng hẹn', '1'), kpi('Phát sinh hôm nay', money(13500000))),
  panel('Vòng đời khách hàng', 'Một hồ sơ, nhiều lần chăm sóc', [],
    grid(5, secondary('3 Khách mới', { full: true }), secondary('2 Khách quay lại', { full: true }), secondary('9 Đang điều trị', { full: true }), secondary('1 Lâu chưa quay lại', { full: true }), secondary('1 Đã quay lại sau CSKH', { full: true })))
];

const WD = [
  page('WD1', 'CSKH hôm nay', WEB + 'crm · hàng chờ CSKH: 4 KPI bấm được, danh sách nhóm công việc theo quy tắc, bộ lọc Phụ trách và Thời hạn, bảng 12 việc/trang; app C1-C4 chỉ có 3 nhóm và danh sách ngắn; tên, mã hồ sơ và số liệu là dữ liệu tổng hợp', 'crm', wdQueue(), { badge: '5' }),

  dlg('WD2', 'Chăm sóc · ' + people[0].name, WEB + 'dialog crm → Xử lý · hộp thoại thay cho màn đầy đủ C6/I13; nút gửi đổi thành "Tiếp tục → Đặt lịch" khi kết quả là đặt lịch, rồi mở hộp thoại đặt lịch (WB7); tên khách và số liệu là dữ liệu tổng hợp', [
    card({ v: 'soft', g: 8 },
      row({ g: 18, jc: 'space-between', ai: 'center' },
        stack({ g: 6 },
          tags(badge('Sau thủ thuật D+1', 'warning')),
          txt([['Theo dõi mụn & chăm sóc tại nhà · Còn '], ['2 buổi', 'b']]),
          sm('Khám: 13/9/2026 · Dự kiến: 20/9/2026 · Quá hạn 0 ngày'),
          sm('Liên hệ gần nhất: Chưa thiết lập · Chưa ghi nhận')),
        secondary('Patient 360 →'))),
    notice('Ghi nhận cuộc gọi/tin nhắn mô phỏng. Không gửi Zalo/SMS hoặc thực hiện cuộc gọi thật.', 'info'),
    grid(2,
      select('Kênh liên hệ', 'Gọi điện', { opts: ['Gọi điện', 'Zalo', 'SMS', 'Ghi chú nội bộ'] }),
      select('Kết quả', 'Gọi lại sau', { opts: ['Không nghe máy', 'Gọi lại sau', 'Đã liên hệ, chưa có nhu cầu', 'Đang bận, hẹn gọi lại', 'Đồng ý đặt lịch', 'Muốn bác sĩ tư vấn', 'Có phản hồi sau điều trị', 'Khiếu nại', 'Không muốn nhận CSKH', 'Sai số / không liên hệ được'] })),
    textarea('Nội dung / kết quả trao đổi', '', { req: true, ph: 'Ghi cụ thể kết quả và điều đã thống nhất với khách…', lines: 2 }),
    grid(2,
      date('Ngày giờ tiếp theo (nếu cần)', '', { ph: 'mm/dd/yyyy --:-- --' }),
      select('Hành động tiếp theo', 'Gọi lại', { opts: ['Gọi lại', 'Bác sĩ xem', 'Đặt lịch', 'Nhắn chăm sóc'] }),
      select('Phụ trách', 'CSKH Mai Anh', { opts: WD_OWNERS }),
      select('Ưu tiên', 'Ưu tiên cao', { opts: ['Ưu tiên cao', 'Thông thường', 'Chăm sóc'] })),
    hr(),
    row({ g: 14 }, primary('Lưu kết quả chăm sóc'), sm('Đồng ý đặt lịch sẽ mở form lịch trước khi hoàn tất.'))
  ], { w: 760, nav: 'crm', behind: wdQueue(), badge: '5' }),

  dlg('WD3', 'Protocol chăm sóc mẫu', WEB + 'dialog crm → Xem protocol · mẫu quy tắc chăm sóc chờ chủ phòng khám duyệt; không có màn tương ứng trong app', [
    sm('Hoàn tất Laser CO2 → D+1 hỏi tình trạng → D+3 yêu cầu ảnh → D+7 bác sĩ review → D+30 dự kiến tái khám.'),
    list([
      { t: 'Sau thủ thuật D+1', sub: 'Hỏi tình trạng sau thủ thuật', sub2: 'Hoàn tất buổi → 1 ngày → tạo việc cho CSKH' },
      { t: 'D+3 cần ảnh', sub: 'Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile', sub2: 'Hoàn tất buổi → 3 ngày → tạo việc cho CSKH' },
      { t: 'D+7 bác sĩ review', sub: 'Chuyển bác sĩ xem ảnh và phản hồi', sub2: 'Hoàn tất buổi → 7 ngày → tạo việc cho bác sĩ' },
      { t: 'Đến hạn tái khám', sub: 'Xác nhận kế hoạch tái khám', sub2: 'Ngày dự kiến → 0 ngày → tạo việc cho CSKH' },
      { t: 'Quá hạn tái khám', sub: 'Hỏi trở ngại và hỗ trợ đặt lại lịch', sub2: 'Ngày dự kiến → 1 ngày → tạo việc cho CSKH' },
      { t: 'Vắng/hủy chưa đặt lại', sub: 'Liên hệ hỗ trợ chọn lịch mới', sub2: 'Hủy/vắng hẹn → 1 ngày → tạo việc cho CSKH' },
      { t: 'Nguy cơ bỏ liệu trình', sub: 'Trao đổi về các buổi còn lại', sub2: 'Còn buổi → 45 ngày → tạo việc cho CSKH' },
      { t: '90 ngày chưa quay lại', sub: 'Hỏi thăm nhu cầu chăm sóc', sub2: 'Lần khám gần nhất → 90 ngày → tạo việc cho CSKH' },
      { t: '180 ngày chưa quay lại', sub: 'Chăm sóc lại khách cũ', sub2: 'Lần khám gần nhất → 180 ngày → tạo việc cho CSKH' },
      { t: 'Sinh nhật trong tuần', sub: 'Chúc mừng sinh nhật, không gửi tự động', sub2: 'Ngày sinh → 7 ngày → tạo việc cho CSKH' }
    ]),
    notice('Ngưỡng và nội dung là mẫu cần chủ phòng khám duyệt trước pilot. Không tự gửi tin hoặc tự duyệt y khoa.', 'info')
  ], { w: 760, nav: 'crm', behind: wdQueue(), badge: '5' }),

  dlg('WD4', 'Kết quả chăm sóc đã ghi', WEB + 'dialog crm → KPI "Đã hoàn tất" / "Đặt lịch sau CSKH" · trạng thái chưa có kết quả nào được ghi; khi đã có kết quả, hộp thoại liệt kê khách, kết quả, ghi chú, người ghi, thời gian và lịch hẹn liên quan', [
    empty('Chưa có kết quả. Bắt đầu từ CSKH hôm nay.')
  ], { w: 760, nav: 'crm', behind: wdQueue(), badge: '5' }),

  dlg('WD5', 'Đang điều trị', WEB + 'dialog dashboard → ô vòng đời · tiêu đề là tên giai đoạn (5 giai đoạn), mỗi khách một dòng với "Mở hồ sơ" (mở tab CRM); chưa có trong app; danh sách mẫu hiển thị 12 khách, bản gốc có 42', [
    list(people.map(x => ({ t: x.name, actions: [secondary('Mở hồ sơ')] })))
  ], { w: 760, nav: 'dashboard', behind: wdDash(), badge: '5' }),

  page('WD6', 'Theo dõi', WEB + 'followups · menu "Theo dõi" mở hộp thư "Follow-up Inbox" (app I6/A4 đặt tên "Theo dõi", mốc thứ ba là "Bỏ sót"); thẻ chấm màu theo mức ưu tiên (xanh ảnh, đỏ triệu chứng, vàng quá hạn, tím thiếu mốc); khung thẻ ngoài bị bỏ để đủ chỗ lồng; tên khách là dữ liệu tổng hợp', 'followups', wdFollow(), { badge: '5' }),

  dlg('WD7', people[0].name, WEB + 'dialog followups → Mở / Xử lý · duyệt phản hồi trước khi đóng mục (app F10); ảnh bệnh nhân là khung minh họa tổng hợp, không dùng ảnh thật', [
    txt('Đỏ nhẹ đã giảm, không đau. Em gửi ảnh trước buổi hẹn.', { size: 's', tone: 'soft' }),
    photos([{ label: '' }], { n: 1 }),
    textarea('Phản hồi sau khi xem · bác sĩ cần chỉnh sửa', 'Pema đã xem cập nhật và ghi nhận vào hành trình. Bạn hãy tiếp tục theo hướng dẫn đã được bác sĩ duyệt.', { lines: 3 }),
    primary('Duyệt, phản hồi & đóng mục')
  ], { w: 620, eyebrow: 'Ảnh / phản hồi chưa duyệt · BS. Tâm', nav: 'followups', behind: wdFollow(), badge: '5' }),

  page('WD8', 'CSKH hôm nay · không có việc phù hợp', WEB + 'crm · tìm kiếm không khớp việc nào: bảng giữ tiêu đề cột và hiện một dòng trống, bộ đếm "0 việc · Trang 1/1"; các trạng thái trống khác (không còn việc CSKH mở, Inbox đã sạch, đã xếp hết danh sách chờ) không có kịch bản trong web cũ', 'crm', wdQueueEmpty(), { state: true, badge: '5' })
];
