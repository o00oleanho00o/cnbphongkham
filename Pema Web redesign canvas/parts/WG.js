// WG · Tài chính PB02 (W3b-WG). Source: prototype/finance/finance.js (PemaFinance), mounted in the clinic shell. WG1-WG5 are the owner pages and
// tabs, WG6-WG7 the doctor projection, WG8 the accountant projection, WG9 the API-down state. Names, ids and money come from base.js; the wording
// (rate snapshots: "Tỷ lệ lưu theo từng lượt. Đổi chính sách không tính lại lịch sử."; the performing doctor is chosen in the entry form, never
// taken from the record owner) is the old web's, verbatim.

const wgMonth = '2026-09';
const wgHeroSub = 'Kỳ ' + wgMonth + ' · Doanh số thực hiện và tiền đã thu được theo dõi riêng.';
const wgPeriod = badge('Đang đối soát', 'neutral', { dot: false });
const wgRecon = 'Tỷ lệ lưu theo từng lượt. Đổi chính sách không tính lại lịch sử. Khoản theo thực thu được đóng băng khi chốt kỳ.';

// "Đóng góp của đội ngũ" / "Chi tiết của tôi": one status bar per doctor (name, count + approved fee, revenue; bar = share of the period revenue).
const wgTeam = rowsOf => bars(...rowsOf.map(([d, n, fee, rev, pct]) => [d.name + ' · ' + n + ' lượt · Tiền thủ thuật ' + money(fee), money(rev), pct, 'info']));
const wgTeamRows = [[doctors[0], 3, 90000, 900000, 7], [doctors[1], 3, 225000, 1500000, 11], [doctors[2], 3, 1440000, 7200000, 55], [doctors[3], 3, 432000, 3600000, 27]];
const wgRecPanel = () => panel('Việc cần đối soát', '', [],
  facts(['Lượt chờ kế toán duyệt', '0'], ['Tiền chờ duyệt', money(0)]),
  sm(wgRecon),
  secondary('Mở bảng tiền thủ thuật →'));

// "Bảng tiền thủ thuật": 6 columns. `acts` per row: 'void' (Hủy), 'approve' (Duyệt + Hủy), '' (no button: doctor view or an already voided row).
const wgCols = [['Ngày / Hồ sơ', '0.8fr'], ['Thủ thuật / Bác sĩ', '1.3fr'], ['Doanh số phân bổ', '0.9fr'], ['Cơ sở × tỷ lệ', '1.1fr'], ['Tiền thủ thuật', '0.9fr'], ['Trạng thái', '1.9fr']];
const wgStatus = { approved: ['Đã duyệt', 'success'], pending: ['Chờ duyệt', 'warning'], void: ['Đã hủy', 'danger'] };
const wgBasis = { net: 'Giá sau giảm', list: 'Giá niêm yết', collected: 'Theo thực thu' };
const wgRow = (date, p, s, d, revenue, base, rate, basis, fee, status, acts) => [
  date + '\n' + p.id, s.name + '\n' + d.name, money(revenue), money(base) + ' × ' + rate + '%\n' + wgBasis[basis], [strong(money(fee))],
  cell([badge(wgStatus[status][0], wgStatus[status][1], { dot: false }), ...(acts === 'approve' ? [secondary('Duyệt', { sm: true })] : []), ...(acts ? [secondary('Hủy', { sm: true })] : [])], { row: true })
];
const wgOwnerRows = [
  wgRow('2026-09-01', people[0], services[0], doctors[0], 300000, 300000, 10, 'net', 30000, 'approved', 'void'),
  wgRow('2026-09-02', people[1], services[1], doctors[1], 500000, 500000, 15, 'net', 75000, 'approved', 'void'),
  wgRow('2026-09-03', people[2], services[2], doctors[2], 2400000, 2400000, 20, 'net', 480000, 'approved', 'void'),
  wgRow('2026-09-18', people[3], services[3], doctors[3], 1200000, 1200000, 12, 'net', 144000, 'pending', 'approve'),
  wgRow('2026-09-19', people[4], services[2], doctors[0], 2500000, 2500000, 20, 'list', 500000, 'pending', 'approve'),
  wgRow('2026-09-19', people[5], services[0], doctors[1], 300000, 300000, 10, 'collected', 30000, 'void', '')
];
const wgDoctorRows = [
  wgRow('2026-09-02', people[1], services[1], doctors[1], 500000, 500000, 15, 'net', 75000, 'approved', ''),
  wgRow('2026-09-05', people[5], services[0], doctors[1], 300000, 300000, 10, 'net', 30000, 'approved', ''),
  wgRow('2026-09-09', people[9], services[2], doctors[1], 700000, 700000, 20, 'net', 120000, 'approved', '')
];
const wgTableHead = () => row({ g: 12, jc: 'space-between', ai: 'center' },
  row({ g: 12, ai: 'center' }, h2('Bảng tiền thủ thuật • ' + wgMonth), wgPeriod),
  secondary('Xuất CSV cho Excel'));
// Variants the old table can show but one frame cannot: period badges, the empty row.
const wgVariants = () => stack({ g: 8 },
  sm('Trạng thái kỳ (huy hiệu cạnh tiêu đề): đổi theo kỳ, hiện đúng một huy hiệu'),
  tags(badge('Đang đối soát', 'neutral', { dot: false }), badge('Đã chốt tháng', 'info', { dot: false }), badge('Đã chi', 'success', { dot: false })),
  sm('Khi chưa có lượt trong kỳ, bảng chỉ có một dòng: "Chưa có lượt thủ thuật trong kỳ này."'));
const wgEntryFields = () => [
  grid(3,
    select('Hồ sơ', people[0].name + ' · ' + people[0].id, { hint: 'Một lựa chọn cho mỗi hồ sơ' }),
    select('Thủ thuật', services[0].name),
    date('Ngày thực hiện', '2026-09-20', { req: true, hint: 'Không chọn ngày sau hôm nay' }),
    number('Giá niêm yết', '300000', { req: true }),
    number('Giảm giá', '0', { req: true }),
    select('Gắn hóa đơn đã có', 'Tạo hóa đơn mới cho lượt này', { hint: 'Hoặc một hóa đơn đã có của hồ sơ' }),
    input('Ghi chú hoàn tất', '', { req: true, ph: 'Đã thực hiện, chờ đối soát' })),
  h3('Ai thực hiện và được ghi nhận?'),
  sm('Tổng tỷ trọng doanh số 100%. Tỷ lệ tiền của mỗi người tính trực tiếp trên cơ sở chính sách; tổng không quá 100%.'),
  grid('minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)', select('Bác sĩ chính', doctors[0].name), number('Tỷ trọng doanh số %', '100'), number('Tỷ lệ tiền thủ thuật %', '10')),
  grid('minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)', select('Người phối hợp (tùy chọn)', 'Không có'), number('Tỷ trọng doanh số %', '0'), number('Tỷ lệ tiền thủ thuật %', '0')),
  primary('Ghi nhận • Chờ duyệt')
];
const wgOverviewMetrics = () => kpis(
  kpi('Doanh số thực hiện', money(13200000), 'Theo ngày hoàn tất thủ thuật'),
  kpi('Thực thu trong tháng', money(11000000), 'Theo ngày phiếu thu'),
  kpi('Công nợ hiện tại', money(1250000), 'Tất cả hóa đơn, không chỉ trong tháng'),
  kpi('Tiền thủ thuật đã duyệt', money(2187000), 'Không phải lợi nhuận phòng khám'));
const wgOverviewBody = () => split(
  [panel('Đóng góp của đội ngũ', '', [], wgTeam(wgTeamRows))],
  [wgRecPanel()], { cols: 'minmax(0,1.5fr) minmax(0,1fr)' });
const wgDocTabs = ['Tổng quan', 'Tiền thủ thuật'];

const WG = [
  // WG1 · owner overview
  fin('WG1', 'Tài chính & tiền thủ thuật · Tổng quan', WEB + 'finance › Tổng quan (chủ phòng khám) · web là trang riêng (hero, 4 thẻ số, đóng góp của đội ngũ, việc cần đối soát); app H1 là thẻ tóm tắt ngắn · chưa có trên Next.js', 0, [
    hero('Một màn hình, nắm rõ dòng tiền', wgHeroSub, 'account_balance_wallet', { over: 'BS. TÂM • TỔNG QUAN ĐIỀU HÀNH', actions: [wgPeriod] }),
    wgOverviewMetrics(),
    wgOverviewBody()
  ]),

  // WG2 · Tiền thủ thuật (entry form collapsed, table with the owner's buttons)
  fin('WG2', 'Tài chính · Tiền thủ thuật', WEB + 'finance › Tiền thủ thuật (chủ) · ô "+ Ghi nhận lượt thủ thuật đã hoàn tất" đang thu gọn; Duyệt, Hủy, Chốt tháng, Xác nhận đã chi, Xuất CSV · hộp hỏi lý do, xác nhận chốt và mã chứng từ là hộp thoại của trình duyệt · chưa có trên Next.js', 1, [
    card({}, row({ g: 8, ai: 'center' }, ico('chevron_right'), strong('+ Ghi nhận lượt thủ thuật đã hoàn tất'))),
    card({ v: 'soft', title: 'Nội dung của ô khi mở', sub: 'Các trường có sẵn trong trang nhưng ẩn khi thu gọn (xem WG3)' }, ...wgEntryFields()),
    card({},
      wgTableHead(),
      table(wgCols, wgOwnerRows),
      row({ g: 12 }, primary('Chốt tháng đã kết thúc')),
      hr(),
      wgVariants(),
      sm('Khi kỳ đã chốt (Đã chốt tháng), nút cuối bảng đổi thành:'),
      row({ g: 12 }, primary('Xác nhận đã chi')))
  ], { toast: 'Đã ghi nhận thành công' }),

  // WG3 · entry form open
  fin('WG3', 'Tài chính · Ghi lượt thủ thuật đã hoàn tất', WEB + 'finance › Tiền thủ thuật, ô ghi nhận đang mở · bác sĩ thực hiện chọn trong form, không lấy từ người quản lý hồ sơ · chưa có trên Next.js', 1, [
    disc('+ Ghi nhận lượt thủ thuật đã hoàn tất', ...wgEntryFields()),
    card({}, wgTableHead(), table(wgCols, wgOwnerRows.slice(0, 3)), row({ g: 12 }, primary('Chốt tháng đã kết thúc')))
  ], { state: true }),

  // WG4 · rates
  fin('WG4', 'Tài chính · Chính sách tỷ lệ', WEB + 'finance › Chính sách tỷ lệ · mỗi thủ thuật một dòng có phiên bản; tỷ lệ lưu theo từng lượt, không tính lại lịch sử · chưa có trên Next.js', 2, [
    card({ title: 'Chính sách theo thủ thuật' },
      sm('Áp dụng cho lượt tạo sau khi lưu. Người phối hợp có thể được kế toán phân bổ riêng tại lượt thực hiện.'),
      ...[[services[0], 10], [services[1], 15], [services[2], 20], [services[3], 12]].flatMap(([s, r]) => [
        row({ g: 16, jc: 'space-between', ai: 'center' },
          stack({ g: 2 }, strong(s.name), sm('Phiên bản 1')),
          row({ g: 12, ai: 'flex-end' }, select('Cơ sở', 'Giá sau giảm', { w: 170 }), number('Tỷ lệ %', String(r), { req: true, w: 110 }), secondary('Lưu tỷ lệ'))),
        hr()]),
      sm('Cơ sở tính có 3 lựa chọn: Giá sau giảm · Giá niêm yết · Theo thực thu.'),
      sm('Bác sĩ xem tỷ lệ trên các lượt của mình; chính sách chung thuộc kế toán. (nội dung thay cho các form khi đăng nhập bác sĩ)'))
  ]),

  // WG5 · receipts and notifications
  fin('WG5', 'Tài chính · Phiếu thu & thông báo', WEB + 'finance › Phiếu thu & thông báo · thu tiền hóa đơn tài chính còn nợ, giao dịch trong kỳ, thông báo cho chủ phòng khám; hóa đơn web cũ thu tại Thu ngân · chưa có trên Next.js', 3, [
    split(
      [panel('Thu tiền khách hàng', '', [],
        select('Hóa đơn còn nợ', people[0].id + ' · ' + money(150000) + ' · FIN-HD-1', { w: 420 }),
        grid(2, number('Số thu', '150000', { req: true }), select('Phương thức', 'Tiền mặt', { hint: 'Tiền mặt · Chuyển khoản' })),
        primary('Xác nhận thu'),
        sm('Phiếu thu mới đồng bộ với app khi đang mở. Hóa đơn web cũ thu tại Thu ngân Clinic; không thu lại ở đây.'),
        h3('Giao dịch trong kỳ'),
        list([[people[11], '2026-09-12', 'Chuyển khoản', 1200000], [people[10], '2026-09-11', 'Tiền mặt', 2400000], [people[9], '2026-09-10', 'Chuyển khoản', 250000], [people[8], '2026-09-09', 'Tiền mặt', 300000], [people[7], '2026-09-08', 'Chuyển khoản', 1200000]]
          .map(([p, d, m, a]) => ({ t: p.id, sub: d + ' · ' + m, actions: [strong(money(a))] }))),
        sm('Khi chưa có phiếu thu: "Chưa có phiếu thu." và nút "Xác nhận thu" bị tắt.'),
        secondary('Xác nhận thu', { dis: true }))],
      [panel('Thông báo của chủ phòng khám', '', [],
        txt('Thanh toán thành công sẽ xuất hiện tại đây và trên app BS. Tâm.'),
        hr(),
        sm('Khi đã có thông báo: tiêu đề, nội dung, giờ; nút "Đã đọc" cho thông báo chưa đọc, chữ "Đã đọc" cho thông báo đã đọc.'),
        list([
          { t: 'Thanh toán thành công', sub: 'Phiếu thu ' + people[11].id + ' · ' + money(1200000) + ' · Chuyển khoản', sub2: '2026-09-12 10:30', actions: [secondary('Đã đọc', { sm: true })] },
          { t: 'Thanh toán thành công', sub: 'Phiếu thu ' + people[10].id + ' · ' + money(2400000) + ' · Tiền mặt', sub2: '2026-09-11 15:05', actions: [sm('Đã đọc')] }
        ]),
        hr(),
        sm('Tài khoản kế toán: "Kế toán không đọc inbox của chủ."'),
        sm('Tài khoản bác sĩ không vào được tab này: "Tài khoản bác sĩ không xem thu tiền toàn phòng khám."'))],
      { cols: 'minmax(0,1.5fr) minmax(0,1fr)' })
  ]),

  // WG6 · doctor overview
  fin('WG6', 'Doanh số của tôi · Tổng quan (bác sĩ)', WEB + 'finance › Tổng quan, tài khoản bác sĩ · hero "GÓC NHÌN CÁ NHÂN", 3 thẻ, chỉ 2 tab (Tổng quan, Tiền thủ thuật); menu đổi tên thành "Doanh số của tôi" · chưa có trên Next.js', 0, [
    hero('Công việc được ghi nhận, thu nhập rõ ràng', wgHeroSub, 'account_balance_wallet', { over: 'GÓC NHÌN CÁ NHÂN', actions: [wgPeriod] }),
    kpis(
      kpi('Doanh số của tôi', money(1500000), 'Theo ngày hoàn tất thủ thuật'),
      kpi('Tiền chờ duyệt', money(0), 'Chưa tính vào khoản đã duyệt'),
      kpi('Tiền thủ thuật đã duyệt', money(225000), 'Không phải lợi nhuận phòng khám')),
    split([panel('Chi tiết của tôi', '', [], wgTeam([[doctors[1], 3, 225000, 1500000, 100]]))], [wgRecPanel()], { cols: 'minmax(0,1.5fr) minmax(0,1fr)' })
  ], { role: 'doctor-mai', state: true, tabs: wgDocTabs }),

  // WG7 · doctor work table
  fin('WG7', 'Doanh số của tôi · Tiền thủ thuật (bác sĩ)', WEB + 'finance › Tiền thủ thuật, tài khoản bác sĩ · không có form ghi nhận, nút Duyệt, Hủy, Chốt tháng; chỉ xem lượt của mình và Xuất CSV · chưa có trên Next.js', 1, [
    card({}, wgTableHead(), table(wgCols, wgDoctorRows)),
    box({ tone: 'info', title: 'Các tab bác sĩ không thấy (nội dung thay thế, không vào được từ giao diện)' },
      sm('Chính sách tỷ lệ: "Bác sĩ xem tỷ lệ trên các lượt của mình; chính sách chung thuộc kế toán."'),
      sm('Phiếu thu & thông báo: "Tài khoản bác sĩ không xem thu tiền toàn phòng khám."'))
  ], { role: 'doctor-mai', state: true, tabs: wgDocTabs }),

  // WG8 · accountant overview
  fin('WG8', 'Tài chính · Tổng quan (kế toán)', WEB + 'finance › Tổng quan, tài khoản kế toán · hero "KẾ TOÁN • ĐỐI SOÁT", đủ 4 tab; app D1 là trang chủ "Đối soát & thu ngân" 3 thẻ, web vào Thu ngân rồi mở Tài chính từ menu · chưa có trên Next.js', 0, [
    hero('Một màn hình, nắm rõ dòng tiền', wgHeroSub, 'account_balance_wallet', { over: 'KẾ TOÁN • ĐỐI SOÁT', actions: [wgPeriod] }),
    wgOverviewMetrics(),
    wgOverviewBody()
  ], { role: 'accountant', state: true }),

  // WG9 · finance API down
  fin('WG9', 'Tài chính · Chưa kết nối dữ liệu', WEB + 'finance › trạng thái lỗi khi máy chủ tài chính (cổng 4174) không trả lời · không tab nào được chọn; thanh trên cùng đổi thành "Tài chính chờ kết nối · thử lại" · chưa có trên Next.js', -1, [
    notice('Chưa kết nối dữ liệu tài chính: Failed to fetch. Chạy python prototype/finance_server.py rồi thử lại.', 'danger'),
    txt('Đang tải dữ liệu…')
  ], { state: true, fin: 'Tài chính chờ kết nối · thử lại' })
];
