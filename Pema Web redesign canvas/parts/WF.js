// WF · Thu ngân & lên đơn: thu ngân, thu tiền, lên đơn nhanh, tách đơn A5 (W3b-WF).
// Source of truth: design-specs/web/screens/WF1..WF10.md and the old-web shots (WF5/WF6 include the print-media captures).
// Names come from `people`, services and prices from `services`/`money()`; the product catalog values (code, name, unit, price)
// are the catalog's own data and stay as the old web shows them so that the cart totals add up.

// ---- shared pieces (prefixed wf so no other part collides) --------------------------------------------------
const wfDx = 'Nám · tăng sắc tố';
const wfDoctor = pt.doctor;
const wfDate = '20/9/2026';
const wfPatientOpt = pt.name + ' · ' + pt.id;
const wfRoutes = ['Đơn thuốc', 'Phiếu tư vấn', 'Không in', 'Cần phân loại'];
const wfNoteText = 'Sản phẩm chưa có loại trong Excel cần được phân loại. “Không in” chỉ loại khỏi phiếu, vẫn tính trong hóa đơn. Đơn nháp chưa xuất hiện trên app.';
const wfCatalogNote = '115 sản phẩm · 30 thuốc · 78 sản phẩm tư vấn · 7 cần phân loại';
// catalog rows as the picker lists them: [code, name, unit, group, route, price]
const wfCatalog = [
  ['H002', 'Desloratadine/Genepharm (Desloratadine 5 mg) Hộp 30 Viên - Viên - A', 'Viên', 'Thuốc', 'Đơn thuốc', 5500],
  ['H005', 'Cicaderm Cream 40ml - Kem làm mềm da, dưỡng ẩm, hỗ trợ làm đều màu da, mờ sẹo 40 ml - A', 'Hộp', 'Mỹ Phẩm', 'Phiếu tư vấn', 715000],
  ['H006', 'Heliocare Luminance Oral 60 Caps/ Viên uống sáng da - P', 'Hộp', 'TPCN', 'Phiếu tư vấn', 2808000],
  ['H007', 'Bio Phyto -1 Mild Facial Cleanser - Sữa rửa mặt làm sạch sâu 100ml - A', 'Chai', 'Mỹ Phẩm', 'Phiếu tư vấn', 660000],
  ['H008', 'Kem trị mụn NV ACTIPUR 3 EN 1 CARE 30ML - P', 'Hộp', 'Mỹ Phẩm', 'Phiếu tư vấn', 635000],
  ['H010', 'Bio Phyto -1 Mild Facial Cleanser - Sữa rửa mặt làm sạch sâu 500 ml - A', 'Tuýp', 'Mỹ Phẩm', 'Phiếu tư vấn', 2390000]
];
const wfProductList = () => list(wfCatalog.map(([code, name, unit, grp, route, price]) => ({ t: name, sub: code + ' · ' + unit + ' · ' + grp + ' · ' + route, actions: [strong(money(price))] })), { box: true });
const wfUsage = 'Bôi lớp mỏng, sáng và tối, 14 ngày';
// one cart line (article.order-line): head with remove, code line, qty + route, usage, product note, reason
const wfLine = (n, code, name, unit, price, route, usage) => stack({ g: 10 },
  grid('minmax(0,1fr) auto', strong(n + '. ' + name), secondary('×', { sm: true })),
  sm(code + ' · ' + unit + ' · ' + money(price)),
  grid(2, number('Số lượng (' + unit + ')', '1', { req: true }), select('Loại phiếu', route, { opts: wfRoutes })),
  textarea('Cách dùng / tần suất / thời gian', usage, { ph: 'Nhập hướng dẫn đã được bác sĩ chỉ định', lines: 2 }),
  input('Ghi chú sản phẩm'),
  input('Lý do đổi phân loại (nếu có)'));
const wfTotal = value => row({ jc: 'space-between' }, txt('Tổng tiền dự kiến', { size: 's', tone: 'soft' }), txt(value, { size: 'sec', w: 'b', tone: 'heading' }));
// body of the quick-order dialog (WF3, WF4, WF9, WF10); `search` is the typed query, `results` the left column, `cart` the card content
const wfOrderForm = ({ locked, search, results, cart }) => [
  grid(2, select('Bệnh nhân', wfPatientOpt, { dis: !!locked }), select('Bác sĩ phụ trách', wfDoctor, { opts: doctors.map(d => d.name) })),
  input('Chẩn đoán / nội dung tư vấn', wfDx),
  grid('minmax(0,1fr) minmax(300px,0.85fr)',
    stack({ g: 12 }, input('Tìm mã hoặc tên sản phẩm', search || '', { ph: 'Ví dụ: H002, Cicaderm, TPCN' }), notice(wfCatalogNote, 'info'), results),
    card({ title: 'Nội dung đơn', sub: 'Nhập cách dùng trước khi bác sĩ duyệt' }, ...cart)),
  textarea('Dặn dò chung', '', { lines: 2 }),
  notice(wfNoteText, 'info')
];
const wfOrderFooter = [secondary('Hủy'), primary('Lưu nháp & xem tách đơn')];
const wfOrderOpts = () => ({ eyebrow: 'Lên đơn từ danh mục Excel', w: 1040, nav: 'cashier', footer: wfOrderFooter, behind: wfBehind() });

// the cashier page itself: heading, 4 tiles, banner, invoice list with paging, order history
const wfCashierHead = () => pageHead('Thu ngân', 'Thu tiền và lên đơn nhanh theo mẫu PEMA.', [primary('Lên đơn nhanh', { icon: 'add' })], 'Vận hành · dữ liệu giả lập');
const wfTiles = () => kpis(kpi('Tổng hóa đơn', '48', 'Dữ liệu giả lập'), kpi('Đã thu', money(61650000), 'Tổng lũy kế'), kpi('Còn phải thu', money(11250000), 'Không thu trùng'), kpi('Catalog sản phẩm', '115', 'Từ danhsach.xlsx'));
const wfBanner = () => card({ title: 'Lên đơn theo mẫu PEMA', sub: 'Thuốc vào Đơn thuốc; mỹ phẩm, TPCN và loại khác vào Phiếu tư vấn. Bản in A5 dọc.', aside: [primary('Mở form lên đơn nhanh →')], v: 'soft' });
const wfPaid = () => badge('Đã thanh toán', 'success');
const wfInvoices = () => panel('Hóa đơn & thanh toán', '', [chip('Tất cả', 'sel'), chip('Còn phải thu'), chip('Đã thanh toán')],
  table([['Hóa đơn / bệnh nhân', '1.7fr'], ['Dịch vụ / đơn nhanh', '1.3fr'], ['Tổng tiền', '1fr', 'r'], ['Đã thu', '1fr', 'r'], ['Còn lại', '1fr', 'r'], ['', '120px']], [
    [[strong(people[0].name), sm('HD-0001 · 2026-09-06')], 'Buổi chăm sóc / điều trị', money(1200000), money(1200000), money(0), [wfPaid()]],
    [[strong(people[0].name), sm('HD-DEMO-001 · 2026-09-20')], 'Tái khám & đánh giá', money(300000), money(150000), money(150000), [primary('Thu tiền', { sm: true })]],
    [[strong(people[1].name), sm('HD-0002 · 2026-09-06')], 'Buổi chăm sóc / điều trị', money(1500000), money(1500000), money(0), [wfPaid()]],
    [[strong(people[1].name), sm('HD-DEMO-002 · 2026-09-20')], 'Tư vấn da liễu', money(500000), money(0), money(500000), [primary('Thu tiền', { sm: true })]],
    [[strong(people[2].name), sm('HD-0003 · 2026-09-06')], 'Buổi chăm sóc / điều trị', money(1800000), money(1800000), money(0), [wfPaid()]],
    [[strong(people[2].name), sm('HD-DEMO-003 · 2026-09-20')], 'Laser theo chỉ định', money(2500000), money(0), money(2500000), [primary('Thu tiền', { sm: true })]]
  ]),
  row({ jc: 'space-between' }, txt('48 hóa đơn · Trang 1/4'), row(secondary('← Trước', { dis: true }), secondary('Sau →'))));
const wfHistory = () => panel('Đơn thuốc & phiếu tư vấn', 'Nháp → bác sĩ duyệt → in và hiển thị trên app', [],
  list([
    { t: people[0].name, sub: wfDate + ' · 2 sản phẩm · Bản nháp', actions: [secondary('Xem / in'), secondary('Sửa nháp')] },
    { t: people[1].name, sub: '19/9/2026 · 1 sản phẩm · Đã duyệt', actions: [secondary('Xem / in')] }
  ], { box: true }),
  empty('Chưa có đơn từ catalog.', 'Hiện thay cho danh sách khi chưa có đơn nào.', { icon: 'receipt_long' }));
const wfBehind = () => [wfCashierHead(), wfTiles(), wfBanner(), wfInvoices()];

// ---- order review (A5) pieces -------------------------------------------------------------------------------
const wfReviewBtns = (o = {}) => [
  secondary('In đơn thuốc', { dis: !o.ready }), secondary('In phiếu tư vấn', { dis: !o.ready }), secondary('In tất cả', { dis: !o.ready }),
  ...(o.approve === false ? [] : [primary('Bác sĩ duyệt & gửi app', { dis: !!o.approveDis })]),
  secondary('Về thu ngân')
];
const wfSheet = (kind, item, draft, usage) => {
  const rx = kind === 'rx';
  return stack({ g: 10 },
    h((rx ? 'ĐƠN THUỐC' : 'PHIẾU TƯ VẤN') + ' · 1 sản phẩm', '', { lvl: 4 }),
    a5({
      title: rx ? 'ĐƠN THUỐC' : 'PHIẾU TƯ VẤN', draft: draft ? 'BẢN NHÁP — CHỜ BÁC SĨ DUYỆT' : '',
      rows: [['Họ tên:', pt.name], ['Tuổi:', pt.age + ' · Nữ'], ['Mã hồ sơ:', pt.id], ['Ngày:', wfDate], ['Chẩn đoán / nội dung tư vấn:', wfDx, true]],
      items: [{ t: '1. ' + item[0], qty: '× 1 ' + item[1], use: usage }],
      note: rx ? 'Mang theo đơn này khi tái khám. Kiểm tra thuốc trước khi nhận.' : 'Mang theo phiếu này khi tái khám. Kiểm tra sản phẩm trước khi nhận.',
      signDate: 'Ngày ' + wfDate, signRole: rx ? 'Bác sĩ khám' : 'Bác sĩ tư vấn', signName: wfDoctor
    }));
};
const wfRx = [wfCatalog[0][1], 'Viên'], wfCons = [wfCatalog[1][1], 'Hộp'];
const wfSheets = draft => grid(2, wfSheet('rx', wfRx, draft, wfUsage), wfSheet('cons', wfCons, draft, wfUsage));
const WF_STATUS_DRAFT = 'Bản nháp · Bác sĩ phụ trách: ' + wfDoctor + ' · A5 dọc 148 × 210 mm · 2 sản phẩm';
const wfHead = (sub, btns) => pageHead('Tách đơn – ' + pt.name, sub, btns);

const WF = [
  page('WF1', 'Thu ngân', WEB + 'cashier · bố cục như app I10/F11/D1; web có thêm ô "Catalog sản phẩm", banner "Lên đơn theo mẫu PEMA", lọc hóa đơn, phân trang 12 dòng/trang và khối "Đơn thuốc & phiếu tư vấn"; tên và số liệu là dữ liệu tổng hợp · chưa có trên Next.js', 'cashier', [
    wfCashierHead(), wfTiles(), wfBanner(), wfInvoices(), wfHistory()
  ]),

  dlg('WF2', 'Thu tiền · ' + people[0].name, WEB + 'cashier › Thu tiền · hộp thoại nhỏ như app I11/F12 (số tiền, phương thức, xác nhận); nút "Xác nhận thu tiền" nằm dưới các trường · chưa có trên Next.js', [
    notice('HD-DEMO-001 · Còn lại ' + money(150000), 'info'),
    number('Số tiền (VND)', '150000'),
    select('Phương thức', 'Tiền mặt', { opts: ['Tiền mặt', 'Chuyển khoản'] }),
    row(primary('Xác nhận thu tiền'))
  ], { eyebrow: 'Pema · vận hành', nav: 'cashier', behind: wfBehind() }),

  dlg('WF3', 'Tạo đơn thuốc / phiếu tư vấn', WEB + 'cashier › Lên đơn nhanh · hộp thoại rộng như app F4: chọn sản phẩm trong danh mục Excel 115 dòng (hiện 6 dòng đầu, danh sách cuộn), giỏ "Nội dung đơn" đang trống · chưa có trên Next.js',
    wfOrderForm({ results: wfProductList(), cart: [empty('Chọn sản phẩm ở danh sách.'), wfTotal(money(0))] }), wfOrderOpts()),

  dlg('WF4', 'Tạo đơn thuốc / phiếu tư vấn', WEB + 'cashier › Lên đơn nhanh · đã chọn 2 sản phẩm (một thuốc, một mỹ phẩm), mỗi dòng có số lượng, loại phiếu, cách dùng, ghi chú, lý do đổi phân loại; như app F5 · chưa có trên Next.js',
    wfOrderForm({
      results: wfProductList(),
      cart: [
        wfLine(1, 'H002', wfCatalog[0][1], 'Viên', 5500, 'Đơn thuốc', wfUsage),
        wfLine(2, 'H005', wfCatalog[1][1], 'Hộp', 715000, 'Phiếu tư vấn', wfUsage),
        wfTotal(money(720500))
      ]
    }), wfOrderOpts()),

  page('WF5', 'Tách đơn · bản nháp', WEB + 'order-review · trang độc lập /order-review/ (mở tab mới, không có thanh bên); canvas vẽ trong khung ứng dụng vì Next.js /orders/[id] nằm trong khung; hai phiếu A5 cạnh nhau như app F6/F7 mở rộng, thêm bản in (print media) · chưa có trên Next.js', 'cashier', [
    wfHead(WF_STATUS_DRAFT, wfReviewBtns({ ready: false })),
    wfSheets(true),
    card({ title: 'Bản in (print media)', sub: 'Khi bấm in: thanh công cụ, nhãn mục và vùng lỗi bị ẩn; đơn chưa duyệt không in phiếu' },
      notice('BẢN NHÁP — chưa được bác sĩ duyệt để phát hành.', 'warning'),
      notice('Đơn nháp cần bác sĩ duyệt trước khi in.', 'info'))
  ]),

  page('WF6', 'Tách đơn · đã duyệt', WEB + 'order-review · sau khi bác sĩ duyệt: nút in bật, dấu nháp biến mất, không còn nút duyệt; bản in là hai phiếu A5 liền nhau, chữ đen · chưa có trên Next.js', 'cashier', [
    wfHead('Đã duyệt bởi ' + wfDoctor + ' · A5 dọc 148 × 210 mm · 2 sản phẩm', wfReviewBtns({ ready: true, approve: false })),
    wfSheets(false),
    card({ title: 'Bản in (print media)', sub: 'Khi bấm in: mỗi bộ phiếu một trang, chữ và đường kẻ đen, logo xám; không có thanh công cụ' },
      list([
        { t: 'ĐƠN THUỐC', sub: 'Phiếu A5 dọc, không dấu nháp' },
        { t: 'PHIẾU TƯ VẤN', sub: 'Phiếu A5 dọc, không dấu nháp' }
      ], { box: true }))
  ], { state: true }),

  page('WF7', 'Tách đơn · sản phẩm cần phân loại', WEB + 'order-review · sản phẩm chưa có loại: cảnh báo trên đầu, chỉ còn phiếu thuốc, nút duyệt và nút in bị khóa; app F5 không có trạng thái này · chưa có trên Next.js', 'cashier', [
    wfHead(WF_STATUS_DRAFT, wfReviewBtns({ ready: false, approveDis: true })),
    notice('Cần phân loại 1 sản phẩm: Triluma Ấn 15g trị nám - O. Mở “Sửa nháp” trong hồ sơ hoặc thu ngân để xử lý.', 'warning'),
    grid(2, wfSheet('rx', wfRx, true, 'Chưa nhập cách dùng'))
  ], { state: true }),

  page('WF8', 'Tách đơn · thiếu mã đơn', WEB + 'order-review · mở trang không kèm mã bệnh nhân và mã đơn: chỉ có thanh công cụ (nút in bị khóa) và dòng lỗi · chưa có trên Next.js', 'cashier', [
    pageHead('Tách đơn', '', [secondary('In đơn thuốc', { dis: true }), secondary('In phiếu tư vấn', { dis: true }), secondary('In tất cả', { dis: true }), secondary('Về thu ngân')]),
    notice('Thiếu mã bệnh nhân hoặc mã đơn.', 'danger')
  ], { state: true }),

  dlg('WF9', 'Sửa đơn nháp', WEB + 'cashier › Sửa nháp · hộp thoại lên đơn mở trên đơn nháp có sẵn, bệnh nhân bị khóa, như app F5 · chưa có trên Next.js',
    wfOrderForm({
      locked: true,
      results: wfProductList(),
      cart: [wfLine(1, 'H002', wfCatalog[0][1], 'Viên', 5500, 'Đơn thuốc', wfUsage), wfTotal(money(5500))]
    }), { ...wfOrderOpts(), behind: [wfCashierHead(), wfHistory()] }),

  dlg('WF10', 'Tạo đơn thuốc / phiếu tư vấn', WEB + 'cashier › Lên đơn nhanh · tìm "zzzz" không có kết quả: cột danh sách báo không tìm thấy, giỏ vẫn trống; như app F4 · chưa có trên Next.js',
    wfOrderForm({
      search: 'zzzz',
      results: empty('Không tìm thấy sản phẩm phù hợp.'),
      cart: [empty('Chọn sản phẩm ở danh sách.'), wfTotal(money(0))]
    }), wfOrderOpts())
];

// ---- W6c-REST: ids WF11-WF25 (error and variant states of the cashier, the quick-order dialog and the A5 review page) ----------------
// Source: design-specs/web/screens/WF11..WF25.md and the old-web shots. Appended with WF.push so the frames above stay as they were.
const wfStatusDraft = n => 'Bản nháp · Bác sĩ phụ trách: ' + wfDoctor + ' · A5 dọc 148 × 210 mm · ' + n + ' sản phẩm';
const wfStatusDone = 'Đã duyệt bởi ' + wfDoctor + ' · A5 dọc 148 × 210 mm · 2 sản phẩm';
// "Không in (1): …" line of #review-excluded: plain text, the line is not a boxed notice in the old page
const wfExcludedLine = () => txt('Không in (1): ' + wfCatalog[0][1] + ' — Không cần in. Vẫn tính trong hóa đơn.');
// review page without the approve button (accountant, or an approved order) and with every print button disabled or enabled
const wfPrintBtns = ready => [secondary('In đơn thuốc', { dis: !ready }), secondary('In phiếu tư vấn', { dis: !ready }), secondary('In tất cả', { dis: !ready }), secondary('Về thu ngân')];
// the print-media card of WF6, reused by WF19 for the "-print" shots (two sheets one after the other, no toolbar, no draft mark)
const wfPrintCard = () => card({ title: 'Bản in (print media)', sub: 'Khi bấm in: mỗi bộ phiếu một trang, chữ và đường kẻ đen, logo xám; không có thanh công cụ' },
  list([
    { t: 'ĐƠN THUỐC', sub: 'Phiếu A5 dọc, không dấu nháp' },
    { t: 'PHIẾU TƯ VẤN', sub: 'Phiếu A5 dọc, không dấu nháp' }
  ], { box: true }));

// cashier page variants (WF21, WF22, WF24, WF25): same page as WF1, the list of invoices and the order history change
const wfFinLink = 'Tài chính chờ kết nối · thử lại';
const wfTiles2 = (total, collected, due) => kpis(kpi('Tổng hóa đơn', String(total), 'Dữ liệu giả lập'), kpi('Đã thu', money(collected), 'Tổng lũy kế'), kpi('Còn phải thu', money(due), 'Không thu trùng'), kpi('Catalog sản phẩm', '115', 'Từ danhsach.xlsx'));
const wfInvCols = [['Hóa đơn / bệnh nhân', '1.7fr'], ['Dịch vụ / đơn nhanh', '1.3fr'], ['Tổng tiền', '1fr', 'r'], ['Đã thu', '1fr', 'r'], ['Còn lại', '1fr', 'r'], ['', '120px']];
const wfInvRow = (p, code, date, svc, total, got) => [[strong(p.name), sm(code + ' · ' + date)], svc, money(total), money(got), money(total - got), total > got ? [primary('Thu tiền', { sm: true })] : [wfPaid()]];
// invoice created by the quick order: service cell = "Đơn sản phẩm · n dòng", order code and the quiet "In tách đơn" link
const wfOrderInvRow = (lines, total) => [[strong(people[0].name), sm('HD-7F3A9C · 2026-09-20')], ['Đơn sản phẩm · ' + lines + ' dòng', sm('OD-B21E40 ·'), quiet('In tách đơn', { sm: true })], money(total), money(0), money(total), [primary('Thu tiền', { sm: true })]];
const wfInvPager = (text, prevDis, nextDis) => row({ jc: 'space-between' }, txt(text), row(secondary('← Trước', { dis: prevDis }), secondary('Sau →', { dis: nextDis })));
const wfInvPanel = (sel, rows, text, o = {}) => panel('Hóa đơn & thanh toán', '', [chip('Tất cả', sel === 0 ? 'sel' : ''), chip('Còn phải thu', sel === 1 ? 'sel' : ''), chip('Đã thanh toán', sel === 2 ? 'sel' : '')],
  table(wfInvCols, rows, o.empty ? { empty: o.empty } : {}),
  wfInvPager(text, true, !!o.nextDis));
const wfBase3 = () => [wfInvRow(people[0], 'HD-0001', '2026-09-06', 'Buổi chăm sóc / điều trị', 1200000, 1200000), wfInvRow(people[0], 'HD-DEMO-001', '2026-09-20', 'Tái khám & đánh giá', 300000, 150000), wfInvRow(people[1], 'HD-0002', '2026-09-06', 'Buổi chăm sóc / điều trị', 1500000, 1500000), wfInvRow(people[1], 'HD-DEMO-002', '2026-09-20', 'Tư vấn da liễu', 500000, 0)];
const wfDueRows = () => [
  wfInvRow(people[0], 'HD-DEMO-001', '2026-09-20', 'Tái khám & đánh giá', 300000, 150000),
  wfInvRow(people[1], 'HD-DEMO-002', '2026-09-20', 'Tư vấn da liễu', 500000, 0),
  wfInvRow(people[2], 'HD-DEMO-003', '2026-09-20', 'Laser theo chỉ định', 2500000, 0),
  wfInvRow(people[3], 'HD-DEMO-004', '2026-09-20', 'Chăm sóc theo chỉ định', 1200000, 600000),
  wfInvRow(people[4], 'HD-DEMO-005', '2026-09-20', 'Tái khám & đánh giá', 300000, 0)
];
const wfHistoryRow = (status, n, editable) => panel('Đơn thuốc & phiếu tư vấn', 'Nháp → bác sĩ duyệt → in và hiển thị trên app', [],
  list([{ t: people[0].name, sub: wfDate + ' · ' + n + ' sản phẩm · ' + status, actions: [secondary('Xem / in'), ...(editable ? [secondary('Sửa nháp')] : [])] }], { box: true }));
const wfHistoryEmpty = () => panel('Đơn thuốc & phiếu tư vấn', 'Nháp → bác sĩ duyệt → in và hiển thị trên app', [], empty('Chưa có đơn từ catalog.', '', { flat: true }));
const wfCashier2 = (tiles, inv, history) => [wfCashierHead(), tiles, wfBanner(), inv, history];

WF.push(
  // WF11 · quick order saved with no product: the dialog stays open, red line under the notice
  dlg('WF11', 'Tạo đơn thuốc / phiếu tư vấn', WEB + 'cashier › Lên đơn nhanh · bấm "Lưu nháp & xem tách đơn" khi chưa chọn sản phẩm: hộp thoại vẫn mở, giữ bệnh nhân, bác sĩ và chẩn đoán, dòng đỏ "Chọn ít nhất một sản phẩm." nằm trên hàng nút; như app F4 (app không có dòng lỗi này) · chưa có trên Next.js',
    [...wfOrderForm({ results: wfProductList(), cart: [empty('Chọn sản phẩm ở danh sách.'), wfTotal(money(0))] }), errLine('Chọn ít nhất một sản phẩm.')], wfOrderOpts()),

  // WF12 · one sheet, a prescription product only
  page('WF12', 'Tách đơn · chỉ có đơn thuốc', WEB + 'order-review · một sản phẩm thuốc: chỉ có phiếu ĐƠN THUỐC, không có phiếu tư vấn; trang độc lập vẽ trong khung ứng dụng như WF5 · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(1), wfReviewBtns({ ready: false })),
    grid(2, wfSheet('rx', wfRx, true, wfUsage))
  ], { state: true }),

  // WF13 · one sheet, a consultation product only
  page('WF13', 'Tách đơn · chỉ có phiếu tư vấn', WEB + 'order-review · một sản phẩm mỹ phẩm: chỉ có phiếu PHIẾU TƯ VẤN, không có phiếu thuốc; trang độc lập vẽ trong khung ứng dụng như WF5 · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(1), wfReviewBtns({ ready: false })),
    grid(2, wfSheet('cons', wfCons, true, wfUsage))
  ], { state: true }),

  // WF14 · a line routed to "Không in": the paragraph "Không in (1): …" above the only sheet
  page('WF14', 'Tách đơn · có sản phẩm "Không in"', WEB + 'order-review · một dòng chọn loại "Không in" kèm lý do: đoạn chữ "Không in (1): … — Không cần in. Vẫn tính trong hóa đơn." nằm trên phiếu tư vấn còn lại; app F5 không có loại "Không in" · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(2), wfReviewBtns({ ready: false })),
    wfExcludedLine(),
    grid(2, wfSheet('cons', wfCons, true, wfUsage))
  ], { state: true }),

  // WF15 · approve pressed with a line that has no usage: red line, the sheet prints the placeholder
  page('WF15', 'Tách đơn · lỗi khi duyệt (thiếu cách dùng)', WEB + 'order-review · bấm "Bác sĩ duyệt & gửi app" khi dòng chưa có cách dùng: dòng đỏ "Dòng 1: cần cách dùng trước khi duyệt." dưới thanh công cụ, phiếu in chữ "Chưa nhập cách dùng"; app F5 khóa nút duyệt thay vì báo lỗi · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(1), wfReviewBtns({ ready: false })),
    errLine('Dòng 1: cần cách dùng trước khi duyệt.'),
    grid(2, wfSheet('rx', wfRx, true, 'Chưa nhập cách dùng'))
  ], { state: true }),

  // WF16 · every line is "Không in": nothing to issue, no sheet at all
  page('WF16', 'Tách đơn · không có sản phẩm để phát hành', WEB + 'order-review · mọi dòng là "Không in": dòng đỏ "Đơn không có sản phẩm để phát hành.", đoạn "Không in (1)…", không có phiếu nào; app F5 không có trạng thái này · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(1), wfReviewBtns({ ready: false })),
    errLine('Đơn không có sản phẩm để phát hành.'),
    wfExcludedLine()
  ], { state: true }),

  // WF17 · stale link: patient code present, order code unknown
  page('WF17', 'Tách đơn · không tìm thấy đơn', WEB + 'order-review · mở liên kết cũ (có mã bệnh nhân, mã đơn không còn): tiêu đề "Tách đơn", ba nút in bị khóa, không có nút duyệt, dòng đỏ "Không tìm thấy đơn."; WF8 là trang mở không kèm mã nào · chưa có trên Next.js', 'cashier', [
    pageHead('Tách đơn', '', wfPrintBtns(false)),
    errLine('Không tìm thấy đơn.')
  ], { state: true }),

  // WF18 · accountant opens a draft: both sheets, no approve button, print buttons disabled
  page('WF18', 'Tách đơn · bản nháp · tài khoản không phải bác sĩ', WEB + 'order-review · tài khoản kế toán mở đơn nháp: thanh công cụ không có nút "Bác sĩ duyệt & gửi app" (thiếu quyền lâm sàng), ba nút in bị khóa, hai phiếu vẫn có dấu nháp; app F5 hiện ghi chú "Tài khoản bác sĩ mô phỏng" thay vì ẩn nút · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDraft(2), wfReviewBtns({ ready: false, approve: false })),
    wfSheets(true)
  ], { state: true, role: 'accountant' }),

  // WF19 · approved order, "In đơn thuốc" pressed: the native print dialog opens over the page (the -print shots show the print media)
  page('WF19', 'In đơn thuốc (hộp thoại in của trình duyệt)', WEB + 'order-review · sau khi duyệt bấm "In đơn thuốc", "In phiếu tư vấn" hoặc "In tất cả": trình duyệt mở hộp thoại in (window.print), không có chữ; hai phiếu A5 chữ đen một sau một ở bản in, như WF6; app F7 nói "In / chia sẻ PDF native sẽ nối sau khi duyệt template" · chưa có trên Next.js', 'cashier', [
    wfHead(wfStatusDone, wfPrintBtns(true)),
    wfSheets(false),
    wfPrintCard()
  ], { state: true, native: native('print') }),

  // WF20 · edit of a draft whose invoice was paid: the dialog refuses, the payment toast is still on the page
  dlg('WF20', 'Sửa đơn nháp', WEB + 'cashier › Sửa nháp · đơn đã thu tiền: lưu bị từ chối, hộp thoại giữ nguyên với bệnh nhân bị khóa và một dòng sản phẩm, dòng đỏ "Đơn đã thu tiền hoặc thiếu hóa đơn; không thể sửa.", thông báo "Đã ghi phiếu thu và cập nhật hóa đơn" của lần thu vừa rồi còn trên trang; app F4/F5 không có luồng sửa nháp · chưa có trên Next.js',
    [...wfOrderForm({ locked: true, results: wfProductList(), cart: [wfLine(1, 'H002', wfCatalog[0][1], 'Viên', 5500, 'Đơn thuốc', wfUsage), wfTotal(money(5500))] }), errLine('Đơn đã thu tiền hoặc thiếu hóa đơn; không thể sửa.')],
    { ...wfOrderOpts(), behind: [wfCashierHead(), wfHistory()], toast: 'Đã ghi phiếu thu và cập nhật hóa đơn' }),

  // WF21 · a draft order exists: new invoice row with the order code and "In tách đơn", history row with Xem / in + Sửa nháp
  page('WF21', 'Thu ngân · có đơn nháp', WEB + 'cashier · sau khi lưu một đơn nháp: hóa đơn mới ở đầu danh sách ("Đơn sản phẩm · 1 dòng", mã đơn, nút "In tách đơn"), còn 49 hóa đơn, dòng lịch sử "Bản nháp" có "Xem / in" và "Sửa nháp"; thanh trên "Tài chính chờ kết nối · thử lại" vì máy chủ tài chính bị chặn; app I10 không có lịch sử đơn · chưa có trên Next.js', 'cashier',
    wfCashier2(wfTiles2(49, 61650000, 11255500), wfInvPanel(0, [wfOrderInvRow(1, 5500), ...wfBase3()], '49 hóa đơn · Trang 1/5'), wfHistoryRow('Bản nháp', 1, true)),
    { state: true, fin: wfFinLink }),

  // WF22 · an approved order: only "Xem / in"
  page('WF22', 'Thu ngân · có đơn đã duyệt', WEB + 'cashier · đơn đã duyệt: dòng lịch sử "Đã duyệt" chỉ còn "Xem / in" (không còn "Sửa nháp"), hóa đơn đầu danh sách "Đơn sản phẩm · 2 dòng" kèm "In tách đơn"; so với WF21 cùng trang, khác nháp và đã duyệt · chưa có trên Next.js', 'cashier',
    wfCashier2(wfTiles2(49, 61650000, 11970500), wfInvPanel(0, [wfOrderInvRow(2, 720500), ...wfBase3()], '49 hóa đơn · Trang 1/5'), wfHistoryRow('Đã duyệt', 2, false)),
    { state: true, fin: wfFinLink }),

  // WF23 · payment amount error
  dlg('WF23', 'Thu tiền · ' + people[0].name, WEB + 'cashier › Thu tiền · nhập số tiền 0: hộp thoại giữ nguyên, dòng đỏ "Số tiền phải lớn hơn 0 và không vượt số còn lại." dưới nút "Xác nhận thu tiền", không ghi gì; như app I11 (app không có dòng lỗi) · chưa có trên Next.js', [
    notice('HD-DEMO-001 · Còn lại ' + money(150000), 'info'),
    number('Số tiền (VND)', '0'),
    select('Phương thức', 'Tiền mặt', { opts: ['Tiền mặt', 'Chuyển khoản'] }),
    row(primary('Xác nhận thu tiền')),
    errLine('Số tiền phải lớn hơn 0 và không vượt số còn lại.')
  ], { eyebrow: 'Pema · vận hành', nav: 'cashier', behind: wfBehind() }),

  // WF24 · filter "Còn phải thu": 12 invoices, one page, no order history
  page('WF24', 'Thu ngân · lọc "Còn phải thu"', WEB + 'cashier · lọc "Còn phải thu": chỉ các hóa đơn còn nợ (mọi dòng có "Thu tiền"), "12 hóa đơn · Trang 1/1" với hai nút phân trang đều tắt, ô tổng không đổi theo bộ lọc, lịch sử đơn báo "Chưa có đơn từ catalog."; lọc "Đã thanh toán" và nút phân trang chỉ đổi các dòng; app I10 có ba bộ lọc nhưng không phân trang · chưa có trên Next.js', 'cashier',
    wfCashier2(wfTiles2(48, 61650000, 11250000), wfInvPanel(1, wfDueRows(), '12 hóa đơn · Trang 1/1', { nextDis: true }), wfHistoryEmpty()),
    { state: true }),

  // WF25 · every invoice paid: empty row, 0 invoices, the last payment toast still visible
  page('WF25', 'Thu ngân · không có hóa đơn', WEB + 'cashier · sau khi thu hết 12 hóa đơn nợ, lọc "Còn phải thu" chỉ có dòng "Không có hóa đơn.", "0 hóa đơn · Trang 1/1", ô "Còn phải thu" 0 ₫, thông báo "Đã ghi phiếu thu và cập nhật hóa đơn" của lần thu cuối còn trên trang, lịch sử đơn vẫn "Chưa có đơn từ catalog."; app I10 không có trạng thái rỗng · chưa có trên Next.js', 'cashier',
    wfCashier2(wfTiles2(48, 72900000, 0), wfInvPanel(1, [], '0 hóa đơn · Trang 1/1', { empty: 'Không có hóa đơn.', nextDis: true }), wfHistoryEmpty()),
    { state: true, fin: wfFinLink, toast: 'Đã ghi phiếu thu và cập nhật hóa đơn' })
);
