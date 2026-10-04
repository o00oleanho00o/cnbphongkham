// WC · Hồ sơ & Patient 360 (W3b-WC): patient list, its empty state and create dialog, the 8 Patient 360 tabs, the draft state,
// the six Patient 360 dialogs/modals and the two states of a freshly created profile. Labels and sentences are the old web's, verbatim;
// names, numbers and money are the canvas sample data (people, services, money()).

const wcFirst = p => p.name.split(' ').slice(-1)[0];
const wcCare = 'Phụ trách: CSKH Thu · Có thể chăm sóc theo kế hoạch';
const wcBrief = p => p.name + ', ' + p.age + ' tuổi, quay lại để đánh giá nám · tăng sắc tố. Đã hoàn tất 2/5 buổi của liệu trình kiểm soát sắc tố. Lần gần nhất: 6/9/2026. Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo. Có 1 mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo. Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch.';
const wcDraft = 'Bản nháp ghi chú · 20/9/2026: Đáp ứng tốt, da dịu hơn. Đáp ứng cần được đối chiếu với ảnh mốc và phản hồi của người bệnh. Kế hoạch tiếp theo cần bác sĩ xác nhận.';
const wcPhotoNote = 'Ảnh minh họa tổng hợp cho prototype. Ảnh lâm sàng thật cần gắn vùng chụp, tư thế, thời điểm và đồng ý sử dụng.';
// a profile created in the "Thêm người bệnh" dialog (WC3): synthetic, not in `people`
const wcNew = { id: 'P047', name: 'Trần Bảo Châu', doctor: 'BS. Tâm', age: 28, init: 'BC' };

// Patient 360 header for the freshly created profile: same structure as patientHead() (base.js) with the old web's own meta line.
const wcNewHead = tabIndex => [
  quiet('← Danh sách bệnh nhân'),
  card({ v: 'hero' },
    row({ g: 20, jc: 'space-between', ai: 'center' },
      row({ g: 16, ai: 'center' }, avatar(wcNew.init, { size: 'lg' }),
        stack({ g: 4 }, eyebrow('Hồ sơ ' + wcNew.id + ' · Chưa có lịch hôm nay'), h1(wcNew.name),
          txt(wcNew.age + ' tuổi · Chưa xác nhận · Chưa nhập · Bác sĩ phụ trách: ' + wcNew.doctor, { size: 's', tone: 'soft' }),
          tags(badge('Nám · tăng sắc tố', 'brand', { dot: false }), badge('⚠ Cần khai thác tiền sử', 'warning', { dot: false })))),
      row({ g: 8, jc: 'flex-end' }, secondary('AI brief', { icon: 'auto_awesome' }), secondary('Nhắn tin'), primary('Ghi buổi điều trị', { icon: 'add' })))),
  tabs(P360_TABS, tabIndex)
];

// "Bước tiếp theo" summary card (PemaCRMUI.summary) under the tab bar of the Tổng quan and CRM tabs
const wcSummary = (o = {}) => card({ v: 'soft', g: 10 },
  row({ g: 16, jc: 'space-between', ai: 'flex-start' },
    stack({ g: 4 }, eyebrow('Bước tiếp theo'), h3(o.title || 'Dự kiến quay lại 20/9/2026'), sm(o.sub || 'Lịch hẹn đã xác nhận với phòng khám · Lịch đã đặt')),
    stack({ g: 6 }, tags(badge(o.status || 'Đang điều trị', 'info', { dot: false })), sm(wcCare))),
  row({ g: 8 }, secondary('CRM & CSKH'), secondary('Sửa ngày dự kiến')));

// care-finance.js: "Dịch vụ & liệu trình", "Đơn thuốc" and "Đơn thuốc & phiếu tư vấn" under every tab except CRM and Lịch sử
const wcLinked = () => [
  grid('minmax(0,1.35fr) minmax(360px,1fr)',
    panel('Dịch vụ & liệu trình', 'Giá chốt, số buổi và liên kết thu ngân', [primary('＋ Thêm dịch vụ')],
      card({ v: 'soft', g: 8 }, eyebrow('LIỆU TRÌNH HIỆN TẠI · LP-P001'), h3(services[2].name),
        txt([['2/5 buổi', 'b'], ' · ' + money(12000000) + ' sau giảm']), badge('Đang thực hiện', 'info', { dot: false }), prog(40),
        txt(['Đã thu ', [money(5350000), 'b']]), sm('Còn ' + money(6650000))),
      txt(['Tiền cọc đã phân bổ ', [money(4000000), 'b']]),
      quiet('Mở thu ngân →')),
    panel('Đơn thuốc', 'Chỉ đơn đã duyệt mới xuất hiện trên Patient Mobile', [secondary('＋ Tạo đơn nháp')],
      row({ g: 12, jc: 'space-between', ai: 'flex-start' }, stack({ g: 2 }, eyebrow('DT-P001 · 6/9/2026'), h3('Đơn đã duyệt')), badge('Đã duyệt', 'success', { dot: false })),
      notice('Chăm sóc và phục hồi sau buổi điều trị', 'info'),
      list([
        { t: 'Cicaderm Cream 40ml', sub: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' },
        { t: 'Fudareus B 15g', sub: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }
      ], { box: true }),
      sm('Đã duyệt bởi BS. Tâm · người bệnh có thể xem trên app'))),
  panel('Đơn thuốc & phiếu tư vấn', 'Nháp → bác sĩ duyệt → in và hiển thị trên app', [], empty('Chưa có đơn từ catalog.', '', { icon: 'receipt_long' }))
];

// patient list blocks, shared by WC1, WC2 and the page behind WC3
const wcConcerns = ['Nám · tăng sắc tố', 'Mụn viêm', 'Thâm sau viêm', 'Đỏ da / nhạy cảm', 'Sẹo sau mụn', 'Trẻ hóa da', 'Theo dõi da sau điều trị'];
const wcProgress = [[2, 5], [2, 4], [3, 4], [2, 3], [1, 5], [2, 3], [3, 5]];
const wcListHead = () => pageHead('Tìm bệnh nhân', 'Tìm theo tên, mã hồ sơ, số điện thoại hoặc mối quan tâm.', [primary('Hồ sơ mới', { icon: 'add' })]);
const wcSearch = (value, count) => row({ g: 12, ai: 'flex-end' },
  search('Ví dụ: Nguyễn Thu Hà, P001, nám...', { label: 'Tìm tên, mã hoặc số điện thoại', w: 640, val: value }), badge(count, 'neutral', { dot: false }));
const wcFilters = () => chips([['Tất cả', 'sel'], 'Đang điều trị', 'Tái khám tuần này', 'Có cảnh báo']);
const wcTable = () => table(['Bệnh nhân', ['Mối quan tâm', '1.1fr'], ['Hành trình', '1fr'], ['Bác sĩ', '0.7fr'], ['Lần gần nhất', '0.8fr'], ['Hẹn tiếp theo', '0.8fr'], ['', '88px']],
  people.slice(0, 7).map((x, i) => [
    cell([avatar(x.init, { size: 'sm' }), lnk(x.name), sm(x.id + ' · ' + x.age + ' tuổi · ' + x.phone)], { row: true }),
    [badge(wcConcerns[i], 'brand', { dot: false })],
    [prog(wcProgress[i][0] / wcProgress[i][1] * 100, { label: wcProgress[i][0] + '/' + wcProgress[i][1] })],
    x.doctor, i === 4 ? '16/8/2026' : '6/9/2026', '20/9/2026\n' + (i < 4 ? '08:00' : '09:00'), [secondary('Mở →')]
  ]), { foot: 'Hiển thị 7 trong 46 hồ sơ · bấm vào một dòng hoặc "Mở →" để vào Patient 360' });

// the "Hành trình" panel and the milestone photos of the Tổng quan tab
const wcJourney = (p, done, total, events) => panel('Hành trình của ' + wcFirst(p), 'Toàn bộ sự kiện được nối theo thời gian, có nguồn và người phụ trách', [badge(done + '/' + total + ' buổi', 'neutral', { dot: false })],
  row({ jc: 'space-between' }, strong(done ? 'Liệu trình kiểm soát sắc tố' : 'Chờ bác sĩ thiết lập kế hoạch'), txt('MỐC ' + done + ' / ' + total, { size: 'l', tone: 'info', w: 'b' })),
  prog(done / total * 100),
  events.length ? timeline(...events) : null);
const wcMilestone = () => panel('Ảnh mốc gần nhất', 'Chính diện · đã đồng ý sử dụng trong chăm sóc', [quiet('Mở studio →')],
  photos([{ label: 'Trước buổi 1', meta: '23/07' }, { label: 'Gần nhất', meta: '23/08' }], { n: 2 }),
  notice(wcPhotoNote, 'info'));
const wcAiBrief = text => card({ v: 'ai', eyebrow: 'Pema AI · bản nháp để bác sĩ duyệt', title: 'Brief trước buổi hẹn', g: 10 }, txt(text), secondary('Xem & chỉnh sửa →'));
const wcFacts = (p, next, consent) => panel('Thông tin cần nhớ', '', [quiet('Sửa')],
  facts(['Mối quan tâm', 'Nám · tăng sắc tố'], ['Bác sĩ', p.doctor], ['Buổi tiếp theo', next], ['Tiền sử dị ứng', 'Chưa ghi nhận'], ['Đồng ý ảnh', consent]));

const WC = [
  // ---- patient list ----
  page('WC1', 'Tìm bệnh nhân', WEB + 'patients · tiêu đề "Tìm bệnh nhân" (app A3 là "Hồ sơ người bệnh"), chip đếm "46 hồ sơ" và 4 chip lọc; bảng 7 cột có thanh hành trình và nút "Mở →"; tên và mã là dữ liệu tổng hợp', 'patients', [
    wcListHead(), wcSearch('', '46 hồ sơ'), wcFilters(), panel('', '', [], wcTable())
  ]),
  page('WC2', 'Tìm bệnh nhân · không có hồ sơ', WEB + 'patients · tìm "zzzz": chip đếm "0 hồ sơ" và trạng thái rỗng với nút "Xóa tìm kiếm"', 'patients', [
    wcListHead(), wcSearch('zzzz', '0 hồ sơ'), wcFilters(),
    panel('', '', [], empty('Không tìm thấy hồ sơ', 'Thử tên, mã hồ sơ hoặc mối quan tâm khác.', { icon: 'search', actions: [secondary('Xóa tìm kiếm')] }))
  ], { state: true }),
  dlg('WC3', 'Thêm người bệnh', WEB + 'patients › modal "Hồ sơ mới" (data-modal=patient) · app I5 là màn "Hồ sơ mới" đầy đủ; web chỉ có 3 trường', [
    grid(2, input('Họ và tên', '', { ph: 'Nguyễn ...' }), number('Tuổi', '28')),
    input('Mối quan tâm', 'Nám · tăng sắc tố')
  ], { eyebrow: 'Hồ sơ mới · demo', nav: 'patients', behind: [wcListHead(), wcSearch('', '46 hồ sơ'), wcFilters(), panel('', '', [], wcTable())], footer: [primary('Tạo hồ sơ')] }),

  // ---- Patient 360 tabs ----
  tab('WC4', 'Patient 360 · Tổng quan', WEB + 'patients › Patient 360 › Tổng quan · app F1 là danh sách thẻ dọc; web gộp hero, thanh tab, 3 chỉ số, hành trình, ảnh mốc, AI brief, thông tin cần nhớ và các khối dịch vụ/đơn thuốc trên một trang rộng', 0, [
    wcSummary(),
    grid('minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr)', stat('Liệu trình hiện tại', 'Liệu trình kiểm soát sắc tố'), stat('Buổi đã hoàn tất', '2', '', { unit: '/ 5 buổi' }), stat('Hẹn tiếp theo', '20/9/2026')),
    split([
      wcJourney(pt, 2, 5, [
        { date: '13/9/2026 · Cập nhật tại nhà', title: 'Cập nhật tại nhà đã được xem', detail: 'Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo.', by: 'Ghi nhận bởi Điều dưỡng Hương', icon: 'chat_bubble', tone: 'success' },
        { date: '6/9/2026 · Điều trị', title: 'Hoàn tất buổi 2/5', detail: services[2].name + '. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.', by: 'Ghi nhận bởi BS. Tâm', icon: 'medical_services' },
        { date: '6/9/2026 · Ảnh lâm sàng', title: 'Bộ ảnh theo dõi · chính diện', detail: 'Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.', by: 'Ghi nhận bởi Điều dưỡng Hương', icon: 'photo_camera' },
        { date: '26/6/2026 · Kế hoạch', title: 'Bắt đầu liệu trình kiểm soát sắc tố', detail: 'Mục tiêu và lịch đánh giá đã được trao đổi với người bệnh.', by: 'Ghi nhận bởi BS. Tâm', icon: 'flag' }
      ]),
      wcMilestone()
    ], [
      wcAiBrief(wcBrief(pt)),
      wcFacts(pt, '20/9/2026', 'Đã xác nhận'),
      panel('Chăm sóc tại nhà', '', [quiet('Sửa')], list([
        { t: 'Sữa rửa mặt dịu nhẹ', sub: 'Sáng & tối · theo hướng dẫn đã duyệt', icon: 'auto_awesome' },
        { t: 'Dưỡng ẩm phục hồi', sub: 'Sau làm sạch · dùng lượng phù hợp', icon: 'auto_awesome' },
        { t: 'Chống nắng SPF 50+', sub: 'Buổi sáng · thoa lại theo hướng dẫn', icon: 'auto_awesome' }
      ]))
    ]),
    wcLinked()
  ]),

  tab('WC5', 'Patient 360 · Tư vấn', WEB + 'patients › Patient 360 › Tư vấn · app J1/F2 là một cột; web có 2 cột "Tư vấn lâm sàng" và "Bản nháp của Pema AI", cộng form tiền sử & chẩn đoán do bác sĩ ghi nhận', 1, [
    panel('Tiền sử & chẩn đoán', 'Bác sĩ ghi nhận, không dùng AI tự chẩn đoán', [],
      grid(2, textarea('Tiền sử đã khai thác', '', { req: true }), textarea('Khám / chẩn đoán do bác sĩ xác nhận', '', { req: true })),
      secondary('Bác sĩ lưu nhận định')),
    grid('minmax(0,1.45fr) minmax(0,1fr)',
      panel('Tư vấn lâm sàng', '20/9/2026 · Bản ghi có người duyệt', [badge('Đang soạn', 'brand', { dot: false })],
        notice('AI chỉ tạo bản nháp. Bác sĩ cần xem, sửa và xác nhận trước khi lưu vào hồ sơ.', 'warning'),
        textarea('Ghi chú ngắn / transcript mô phỏng', '', { ph: 'Ví dụ: Da ổn hơn, đỏ giảm sau 2 ngày...', lines: 4 }),
        primary('Tạo bản nháp ghi chú', { icon: 'auto_awesome' })),
      panel('Bản nháp của Pema AI', 'Được tạo từ các sự kiện trên hồ sơ', [],
        card({ v: 'soft', title: 'Chưa có bản nháp' }, txt('Nhập vài ý chính bên trái để Pema tạo bản nháp có cấu trúc.')))),
    wcLinked()
  ]),
  tab('WC6', 'Patient 360 · Tư vấn · bản nháp ghi chú', WEB + 'patients › Patient 360 › Tư vấn sau "Tạo bản nháp ghi chú": bản nháp sửa được, nút "Duyệt & lưu vào Patient 360" và toast; "AI chỉ là bản nháp" - bác sĩ phải duyệt', 1, [
    panel('Tiền sử & chẩn đoán', 'Bác sĩ ghi nhận, không dùng AI tự chẩn đoán', [],
      grid(2, textarea('Tiền sử đã khai thác', '', { req: true }), textarea('Khám / chẩn đoán do bác sĩ xác nhận', '', { req: true })),
      secondary('Bác sĩ lưu nhận định')),
    grid('minmax(0,1.45fr) minmax(0,1fr)',
      panel('Tư vấn lâm sàng', '20/9/2026 · Bản ghi có người duyệt', [badge('Đang soạn', 'brand', { dot: false })],
        notice('AI chỉ tạo bản nháp. Bác sĩ cần xem, sửa và xác nhận trước khi lưu vào hồ sơ.', 'warning'),
        textarea('Ghi chú ngắn / transcript mô phỏng', wcDraft, { ph: 'Ví dụ: Da ổn hơn, đỏ giảm sau 2 ngày...', lines: 4 }),
        primary('Tạo bản nháp ghi chú', { icon: 'auto_awesome' })),
      panel('Bản nháp của Pema AI', 'Được tạo từ các sự kiện trên hồ sơ', [],
        card({ v: 'soft', title: 'Bản nháp đã tạo · chờ duyệt' }, textarea('Chỉnh sửa bản nháp', wcDraft, { lines: 4 })),
        primary('Duyệt & lưu vào Patient 360', { icon: 'check' }))),
    wcLinked()
  ], { state: true, toast: 'Đã tạo bản nháp — hãy kiểm tra trước khi duyệt' }),

  tab('WC7', 'Patient 360 · Kế hoạch', WEB + 'patients › Patient 360 › Kế hoạch · app J3 chỉ liệt kê buổi; web thêm "Bộ tiêu chí theo dõi" (Ảnh mốc, Patient reported outcome, Người duyệt, Nhắc hẹn) và câu hỏi cho buổi tới', 2, [
    grid('minmax(0,1.45fr) minmax(0,1fr)',
      panel('Liệu trình kiểm soát sắc tố', 'Kế hoạch đang hoạt động · tạo 26/06/2026', [secondary('Chỉnh sửa')],
        card({ v: 'soft', g: 8 }, h4('Mục tiêu điều trị'),
          txt('Giảm biểu hiện nám · tăng sắc tố, theo dõi đáp ứng qua từng mốc ảnh và bảo đảm người bệnh hiểu chăm sóc tại nhà.'), prog(40, { label: '2/5 buổi' })),
        list([
          { t: 'Buổi 1 · Đã hoàn tất', sub: 'Đã ghi nhận ảnh và hướng dẫn chăm sóc.', actions: [badge('Đã xong', 'success', { dot: false })] },
          { t: 'Buổi 2 · Đã hoàn tất', sub: 'Đã ghi nhận ảnh và hướng dẫn chăm sóc.', actions: [badge('Đã xong', 'success', { dot: false })] },
          { t: 'Buổi 3 · Tiếp theo', sub: 'Cần đánh giá da trước khi thực hiện.', actions: [badge('Sắp tới', 'info', { dot: false })] },
          { t: 'Buổi 4 · Dự kiến', sub: 'Mốc dự kiến theo đáp ứng của người bệnh.', actions: [badge('Chưa mở', 'neutral', { dot: false })] },
          { t: 'Buổi 5 · Dự kiến', sub: 'Mốc dự kiến theo đáp ứng của người bệnh.', actions: [badge('Chưa mở', 'neutral', { dot: false })] }
        ])),
      stack({ g: 16 },
        panel('Bộ tiêu chí theo dõi', '', [], facts(['Ảnh mốc', 'Chính diện · 3/5'], ['Patient reported outcome', 'Chưa gửi'], ['Người duyệt', pt.doctor], ['Nhắc hẹn', 'Đang bật'])),
        card({ v: 'soft', title: 'Khoảnh khắc cần hỏi ở buổi tới' }, txt('“Đỏ kéo dài bao lâu sau lần trước? Có thay đổi gì trong chăm sóc tại nhà không?”')))),
    wcLinked()
  ]),

  tab('WC8', 'Patient 360 · Buổi điều trị', WEB + 'patients › Patient 360 › Buổi điều trị · app J5/F3; web có form ghi buổi 10 trường (ngày, loại, protocol, tái khám, đánh giá, hướng dẫn, vùng/góc chụp, ảnh mốc, đồng ý ảnh), gợi ý kiểm tra cảnh báo và danh sách buổi đã ghi; tab bị ẩn với CSKH và kế toán', 3, [
    grid('minmax(0,1.45fr) minmax(0,1fr)',
      panel('Ghi buổi điều trị', 'Tạo sự kiện mới cho ' + pt.name, [badge('3/5 dự kiến', 'brand', { dot: false })],
        grid(2, date('Ngày', '2026-09-20'), select('Loại buổi', 'Chăm sóc & laser theo chỉ định', { opts: ['Chăm sóc & laser theo chỉ định', 'Tái khám đánh giá', 'Chăm sóc phục hồi'] })),
        grid(2, select('Protocol chăm sóc', 'Theo khuyến nghị bác sĩ', { opts: ['Theo khuyến nghị bác sĩ', 'Laser CO2 · D+1 / D+3 / D+7 / D+30'] }), date('Ngày dự kiến tái khám', '2026-10-20')),
        textarea('Đánh giá trước buổi', '', { ph: 'Tình trạng da, phản hồi, quyết định của bác sĩ...', lines: 4 }),
        textarea('Hướng dẫn chăm sóc gửi sau buổi', 'SPF 50+ mỗi sáng; thoa lại theo hướng dẫn', { lines: 2 }),
        grid(2, select('Vùng chụp', 'Mặt', { opts: ['Mặt', 'Cổ', 'Vùng khác'] }), select('Góc chụp', 'Chính diện', { opts: ['Chính diện', 'Má trái', 'Má phải'] })),
        file('Ảnh mốc', 'Chọn tệp (png, jpeg, webp)', { hint: 'Thêm ảnh chính diện hoặc vùng điều trị. Prototype tự kiểm tra loại tệp và kích thước.' }),
        check('Người bệnh đã có đồng ý phù hợp cho ảnh chăm sóc.', true),
        primary('Lưu buổi điều trị', { icon: 'check' })),
      stack({ g: 16 },
        card({ v: 'ai', eyebrow: 'Gợi ý kiểm tra', title: 'Trước khi lưu' }, txt('Hồ sơ có cảnh báo: Da nhạy cảm, Theo dõi đỏ da sau điều trị. Hãy xác nhận trước khi thực hiện.')),
        panel('Các buổi đã ghi', '', [], list([{ t: 'Hoàn tất buổi 2/5', sub: services[2].name + '. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.', sub2: '6/9/2026 · ' + pt.doctor, icon: 'check_circle' }])))),
    wcLinked()
  ]),

  tab('WC9', 'Patient 360 · Ảnh trước / sau', WEB + 'patients › Patient 360 › Ảnh trước / sau · app I7; web có Before / After Studio với chọn góc, "So sánh trượt" (đổi chế độ thành "Đặt cạnh nhau"), "Thêm ảnh", thu phóng và metadata; chỉ ảnh minh họa tổng hợp có đánh dấu, không chấm hiệu quả', 4, [
    card({ g: 12 },
      row({ g: 16, jc: 'space-between', ai: 'flex-end' }, h3('Before / After Studio', pt.name + ' · Nám · tăng sắc tố'),
        row({ g: 8, ai: 'flex-end' }, select('Góc ảnh so sánh', 'Chính diện', { w: 180, opts: ['Chính diện', 'Má trái', 'Má phải'] }), secondary('So sánh trượt'), primary('Thêm ảnh', { icon: 'add' }))),
      notice('Chưa có ảnh upload ở góc này. Hai ảnh dưới đây là minh họa tổng hợp. Chưa kiểm định căn chỉnh ảnh; bác sĩ kiểm tra điều kiện chụp trước khi so sánh.', 'info'),
      photos([{ label: 'MINH HỌA TRƯỚC' }, { label: 'MINH HỌA SAU' }], { n: 2 }),
      box('info', range('Phóng to', '1×', 0), badge('Cùng góc khai báo · không tự căn chỉnh', 'neutral', { dot: false })),
      notice('Metadata: vùng Mặt; góc Chính diện; mốc buổi minh họa; đồng ý chăm sóc: có ghi nhận. Không suy ra hiệu quả y khoa từ các ảnh minh họa.', 'info')),
    wcLinked()
  ]),

  tab('WC10', 'Patient 360 · Dịch vụ & tài chính', WEB + 'patients › Patient 360 › Dịch vụ & tài chính · app J6; web có bảng hóa đơn của một người bệnh (Hóa đơn, Dịch vụ, Phát sinh, Đã thu, Còn lại), thông báo cọc chưa phân bổ và các khối liệu trình; chưa có route Next.js', 5, [
    panel('Hóa đơn của ' + pt.name, 'Giá trị phát sinh, tiền đã thu và dư nợ; không suy hoàn tất điều trị', [secondary('Mở thu ngân →')],
      table(['Hóa đơn', 'Dịch vụ', ['Phát sinh', '1fr', 'r'], ['Đã thu', '1fr', 'r'], ['Còn lại', '1fr', 'r']], [
        ['HD-0001\n6/9/2026', 'Buổi chăm sóc / điều trị', money(1200000), money(1200000), money(0)],
        ['HD-0002\n16/8/2026', 'Buổi chăm sóc / điều trị', money(1500000), money(1500000), money(0)]
      ], { foot: '2 hóa đơn của hồ sơ này' }),
      notice('Tiền cọc còn chưa phân bổ: ' + money(0) + '. Cọc đã phân bổ được thể hiện riêng trong liệu trình bên dưới.', 'info')),
    wcLinked()
  ]),

  tab('WC11', 'Patient 360 · CRM & CSKH', WEB + 'patients › Patient 360 › CRM & CSKH · app J7/C5; web gồm thẻ "Bước tiếp theo", "Bối cảnh chăm sóc", "Việc còn mở" và "Lịch sử CSKH"; không có khối dịch vụ/đơn thuốc ở tab này', 6, [
    wcSummary(),
    grid('minmax(0,1.65fr) minmax(300px,1fr)',
      panel('Bối cảnh chăm sóc', 'Dữ liệu từ hồ sơ và liệu trình', [],
        facts(['Nguồn khách', 'Giới thiệu'], ['Tiếp xúc đầu tiên', '26/6/2026'], ['Khám gần nhất', '6/9/2026'], ['Liệu trình', 'Liệu trình kiểm soát sắc tố · còn 3 buổi'], ['Kết quả CSKH gần nhất', 'Chưa liên hệ'], ['Bước tiếp', 'Chưa thiết lập · Theo hàng đợi']),
        row({ g: 8 }, secondary('Sửa ngày dự kiến'), secondary('Xem liệu trình'), secondary('Toàn bộ lịch sử →'))),
      panel('Việc còn mở', '1 việc gắn với hồ sơ', [],
        row({ g: 16, jc: 'space-between' }, stack({ g: 2 }, strong('Đến hạn tái khám'), sm('20/9/2026 · CSKH Thu')), primary('Xử lý')))),
    panel('Lịch sử CSKH', 'Sự kiện gốc, người ghi nhận và liên kết công việc', [], empty('Chưa có hoạt động CSKH được ghi nhận.', '', { icon: 'forum' }))
  ], { status: 'Đặt hẹn' }),

  tab('WC12', 'Patient 360 · Lịch sử', WEB + 'patients › Patient 360 › Lịch sử · app J8; web gộp lịch hẹn, sự kiện hồ sơ, hoạt động CSKH và thu tiền thành một dòng thời gian (giờ, tiêu đề, chi tiết, người ghi nhận · nguồn)', 7, [
    panel('Lịch sử hợp nhất', 'Sự kiện gốc, người ghi nhận và liên kết công việc', [], timeline(
      { date: '2026-09-26 09:00', title: 'Lịch hẹn · Đặt hẹn', detail: 'Lịch giả lập để thử điều phối', by: 'Lễ tân · A6-6', icon: 'event' },
      { date: '2026-09-13', title: 'Cập nhật tại nhà đã được xem', detail: 'Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo.', by: 'Điều dưỡng Hương · Hồ sơ', icon: 'chat_bubble', tone: 'success' },
      { date: '2026-09-06', title: 'Hoàn tất buổi 2/5', detail: services[2].name + '. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.', by: 'BS. Tâm · Hồ sơ', icon: 'medical_services' },
      { date: '2026-09-06', title: 'Bộ ảnh theo dõi · chính diện', detail: 'Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.', by: 'Điều dưỡng Hương · Hồ sơ', icon: 'photo_camera' },
      { date: '2026-09-06', title: 'Thu tiền · ' + money(1200000), detail: 'HD-0001 · Chuyển khoản', by: 'Thu ngân · TT-0001', icon: 'payments' },
      { date: '2026-06-26', title: 'Bắt đầu liệu trình kiểm soát sắc tố', detail: 'Mục tiêu và lịch đánh giá đã được trao đổi với người bệnh.', by: 'BS. Tâm · Hồ sơ', icon: 'flag' }))
  ]),

  // ---- Patient 360 modals and dialogs (drawn over the Patient 360 header) ----
  dlg('WC13', 'Brief trước buổi hẹn', WEB + 'Patient 360 › modal "AI brief" (data-modal=note) · app J2; bản nháp AI phải được bác sĩ xem, sửa và duyệt', [
    card({ v: 'soft', title: pt.name + ' · Liệu trình kiểm soát sắc tố' }, textarea('Brief mô phỏng · sửa trước khi duyệt', wcBrief(pt), { lines: 6 })),
    notice('Nguồn: Patient 360, events đã ghi nhận, follow-up đang mở. Bác sĩ cần xác nhận trước khi dùng trong chăm sóc.', 'info')
  ], { eyebrow: 'Pema AI · bản nháp', nav: 'patients', behind: patientHead(pt, 0), footer: [secondary('Sao chép'), primary('Duyệt & lưu brief')] }),
  dlg('WC14', 'Gửi cập nhật', WEB + 'Patient 360 › modal "Nhắn tin" (data-modal=message) · tiêu đề "Gửi cập nhật" với dòng trên "Tin nhắn · tên"; Next.js là hộp trả lời của /inbox', [
    textarea('Nội dung', 'Chào bạn ' + wcFirst(pt) + ', Pema đã xem cập nhật của bạn. Da đang được theo dõi theo kế hoạch.', { lines: 4 })
  ], { eyebrow: 'Tin nhắn · ' + pt.name, nav: 'patients', behind: patientHead(pt, 0), footer: [primary('Gửi tin nhắn')] }),
  dlg('WC15', 'Thông tin cần nhớ', WEB + 'Patient 360 › modal "Sửa" ở khối Thông tin cần nhớ (data-modal=edit)', [
    textarea('Cảnh báo · mỗi dòng một mục', 'Da nhạy cảm\nTheo dõi đỏ da sau điều trị', { lines: 3 }),
    check('Có đồng ý sử dụng ảnh chăm sóc', true)
  ], { nav: 'patients', behind: patientHead(pt, 0), footer: [primary('Lưu thông tin')] }),
  dlg('WC16', 'Chăm sóc tại nhà', WEB + 'Patient 360 › modal "Sửa" ở khối Chăm sóc tại nhà (data-modal=care) · hướng dẫn đã duyệt mới gửi patient app', [
    textarea('Hướng dẫn đã duyệt cho người bệnh', 'SPF 50+ mỗi sáng; thoa lại theo hướng dẫn', { lines: 3 })
  ], { nav: 'patients', behind: patientHead(pt, 0), footer: [primary('Duyệt & gửi patient app')] }),
  dlg('WC17', 'Điều chỉnh kế hoạch', WEB + 'Patient 360 › Kế hoạch › modal "Chỉnh sửa" (data-modal=plan-edit)', [
    input('Tên kế hoạch', 'Liệu trình kiểm soát sắc tố'),
    number('Tổng số buổi dự kiến', '5')
  ], { nav: 'patients', behind: patientHead(pt, 2), footer: [primary('Lưu kế hoạch')] }),
  dlg('WC18', 'Ngày dự kiến quay lại', WEB + 'Patient 360 › "Sửa ngày dự kiến" (data-crm=expected) · app J7', [
    date('Ngày bác sĩ/CSKH khuyến nghị', '2026-09-20', { req: true }),
    input('Lý do', 'Bác sĩ hẹn đánh giá', { req: true }),
    select('Nguồn', 'Bác sĩ khuyến nghị', { opts: ['Bác sĩ khuyến nghị', 'Protocol dịch vụ', 'Kế hoạch điều trị', 'Chăm sóc sau điều trị'] }),
    notice('Nếu đã có lịch thực tế, Patient 360 ưu tiên ngày lịch đó. Khuyến nghị vẫn được giữ khi hủy lịch.', 'info')
  ], { nav: 'patients', behind: patientHead(pt, 0), footer: [primary('Lưu ngày dự kiến')] }),
  dlg('WC19', 'Thêm dịch vụ vào liệu trình', WEB + 'Patient 360 › "＋ Thêm dịch vụ" (careAction=add-service) · chỉ chủ phòng khám và kế toán (quyền billing) có nút này; chưa có route Next.js', [
    select('Dịch vụ', services[0].name + ' · ' + money(services[0].price) + '/buổi', { opts: services.map(s => s.name + ' · ' + money(s.price) + '/buổi') }),
    grid(2, number('Số buổi', '3'), number('Giảm giá (₫)', '0')),
    notice('Giá đã chốt được lưu trên hồ sơ; thay đổi danh mục sau này không làm đổi liệu trình đã đăng ký.', 'info')
  ], { eyebrow: 'Patient 360 · dịch vụ', nav: 'patients', behind: patientHead(pt, 0), footer: [primary('Lưu dịch vụ')] }),

  // ---- a freshly created profile (empty variants) ----
  page('WC20', 'Patient 360 · hồ sơ vừa tạo', WEB + 'patients › "Tạo hồ sơ" › Patient 360 Tổng quan của hồ sơ trống: chưa có kế hoạch, buổi hay hóa đơn, cảnh báo "Cần khai thác tiền sử", "Chờ bác sĩ thiết lập kế hoạch"; toast "Đã tạo hồ sơ demo"', 'patients', [
    wcNewHead(0),
    wcSummary({ title: 'Dự kiến quay lại 21/9/2026', sub: 'Bác sĩ hẹn đánh giá · Bác sĩ khuyến nghị', status: 'Khách mới' }),
    grid('minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr)', stat('Liệu trình hiện tại', 'Chờ bác sĩ thiết lập kế hoạch'), stat('Buổi đã hoàn tất', '0', '', { unit: '/ 1 buổi' }), stat('Hẹn tiếp theo', '21/9/2026')),
    split([wcJourney(wcNew, 0, 1, []), wcMilestone()], [
      wcAiBrief(wcNew.name + ', ' + wcNew.age + ' tuổi, quay lại để đánh giá nám · tăng sắc tố. Đã hoàn tất 0/1 buổi của chờ bác sĩ thiết lập kế hoạch. Lần gần nhất: Chưa ghi nhận. Chưa có cập nhật sau điều trị. Không có mục theo dõi đang mở. Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch.'),
      wcFacts(wcNew, '21/9/2026', 'Chưa có đồng ý'),
      panel('Chăm sóc tại nhà', '', [quiet('Sửa')])
    ]),
    wcLinked()
  ], { state: true, toast: 'Đã tạo hồ sơ demo' }),
  page('WC21', 'Patient 360 · Lịch sử · chưa có hoạt động', WEB + 'patients › Patient 360 › Lịch sử của hồ sơ vừa tạo: trạng thái rỗng "Chưa có hoạt động CSKH được ghi nhận."; toast "Đã tạo hồ sơ demo"', 'patients', [
    wcNewHead(7),
    panel('Lịch sử hợp nhất', 'Sự kiện gốc, người ghi nhận và liên kết công việc', [], empty('Chưa có hoạt động CSKH được ghi nhận.', '', { icon: 'forum' }))
  ], { state: true, toast: 'Đã tạo hồ sơ demo' })
];
