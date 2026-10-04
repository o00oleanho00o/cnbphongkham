// blocks.js: the block gallery ("Pema Web blocks.dc.html", ids WA9xx). Every block and helper of base.js is drawn at least once, at
// 1440, 1920 and 390, so a group agent sees what a call produces before using it. It is not part of "Pema Web.dc.html".
const WA = [
  page('WA901', 'Blocks · text, buttons, badges, chips, tabs, notices, facts, fields', 'h/h1-h4, txt/sm/lbl/strong/kv/eyebrow, btn variants, badge tones, chip/chips, tabs and segmented tabs, notice tones with actions, facts, every field type', 'dashboard', [
    pageHead('pageHead title', 'subtitle under the title', [secondary('Secondary'), primary('Primary', { icon: 'add' })], 'EYEBROW'),
    grid(2,
      card({ title: 'Text', sub: 'txt, sm, lbl, strong, kv, eyebrow, h1-h4' },
        eyebrow('eyebrow'), h1('h1 page title'), h2('h2 section'), h3('h3 card title', 'with a sub line'), h4('h4 small heading'),
        txt('txt body text'), sm('sm small grey text'), lbl('lbl label text'), strong('strong text'),
        kv('Họ tên:', pt.name), txt([['Mixed ', 'b'], 'parts with ', ['danger', 'danger b'], ' and ', ['small', 'sm']])),
      card({ title: 'Buttons and inline', sub: 'btn variants, badge tones, chip, avatar, ico, prog' },
        row(primary('primary'), secondary('secondary'), danger('danger'), btn('dangers', 'dangers'), quiet('quiet →'), lnk('link')),
        row(primary('with icon', { icon: 'check' }), secondary('trailing', { ric: 'arrow_forward' }), secondary('disabled', { dis: true }), secondary('small', { sm: true }), iconBtn('notifications')),
        row(badge('neutral'), badge('brand', 'brand'), badge('info', 'info'), badge('success', 'success'), badge('warning', 'warning'), badge('danger', 'danger'), badge('no dot', 'neutral', { dot: false })),
        row(chip('chip'), chip('selected', 'sel', 4), chip('disabled', 'dis'), avatar('BT'), avatar('LK', { size: 'sm' }), ico('favorite'), ico('check_circle', { tone: 'success' })),
        prog(40, { label: 'prog 40%' }), prog(70, { tone: 'success' }))),
    grid(2,
      card({ title: 'Chips and tabs' },
        chips(['Tất cả', ['Quá hạn', 'sel', 4], ['Vắng hẹn', '', 2], ['Đã khóa', 'dis']]),
        chips([['Tất cả · 72', 'sel'], ['Sau thủ thuật D+1', '', 6], ['D+3 cần ảnh', '', 4]], { vert: true }),
        tabs(['Tổng quan', ['Tiền thủ thuật', 3], 'Chính sách tỷ lệ', 'Phiếu thu'], 1), tabs(['Ngày', '7 ngày'], 0, { seg: true })),
      card({ title: 'Notices and facts' },
        notice('info notice with the old web text verbatim', 'info'), notice('warning notice', 'warning', { title: 'Title line' }), notice('notice with a title, text and bullets', 'info', { title: 'Notice title', items: ['First bullet', 'Second bullet'], itemsTitle: 'Bullet list title' }),
        notice('danger notice', 'danger'), notice('success notice with actions', 'success', { actions: [primary('Tìm hồ sơ →'), secondary('Xem lịch →')] }),
        facts(['Mối quan tâm', 'Nám · tăng sắc tố'], ['Liên hệ thành công', '75%', { sub: '3/4 lần liên hệ' }], ['Đồng ý ảnh', 'Đã xác nhận']))),
    card({ title: 'Fields', sub: 'input, select (open), date, time, month, number, textarea, check, radio, search, file, range' },
      grid(3,
        input('Text', 'Giá trị', { req: true, hint: 'Hint under the field' }), select('Select', 'BS. Tâm', { opts: doctors.map(d => d.name) }), select('Select open', 'BS. Tâm', { open: true, opts: ['BS. Tâm', 'BS. Mai'] }),
        date('Date', '2026-09-20'), time('Time', '08:00'), month('Month', '2026-09'),
        number('Number', '300000', { err: 'Error message' }), input('Placeholder', '', { ph: 'Ví dụ: H002, Cicaderm' }), search('Tìm bệnh nhân...', { label: 'Search' })),
      grid(2, textarea('Textarea', 'Bôi lớp mỏng, sáng và tối, 14 ngày', { lines: 3 }), stack(check('Checkbox on', true), check('Checkbox off', false), radio('Radio', ['Đơn thuốc', 'Phiếu tư vấn', 'Không in'], 'Đơn thuốc'))),
      grid(2, file('File', 'Thêm ảnh chính diện hoặc vùng điều trị'), range('Range', '1.4×', 40)))
  ]),
  page('WA902', 'Blocks · table, list, timeline, kpis, bars, empty, stat', 'table with every cell shape (becomes cards at 390), list variants, timeline, kpis, bars, empty, stat, legend', 'dashboard', [
    kpis(kpi('Tile', '12', 'note', { icon: 'event' }), kpi('Tile with button', '3', '', { actions: [quiet('Mở →')] }), kpi('Tone', '5', 'cảnh báo', { tone: 'warning' }), kpi('Unit', '3', '', { unit: '/ 5' }), kpi('Chevron', '46', '72 việc', { chev: true })),
    panel('table', 'columns with widths, text + small lines, link, badge, buttons, right-aligned money', [secondary('Xuất CSV')],
      table(['Khách hàng', ['Dịch vụ', '1.3fr'], ['Trạng thái', '1.4fr'], ['Tổng tiền', '110px', 'r'], ['', '110px']], people.slice(0, 4).map((x, i) => [
        [lnk(x.name), sm(x.id + ' · ' + x.doctor)], 'Tái khám & đánh giá\n' + (20 + i) + '/9/2026', cell([badge(i % 2 ? 'Đã thanh toán' : 'Còn phải thu', i % 2 ? 'success' : 'warning'), btn('Hủy', 'secondary', { sm: true })], { row: true }), money(300000 * (i + 1)), [primary('Thu tiền', { sm: true })]
      ]), { foot: '4 hóa đơn · Trang 1/1' })),
    grid(2,
      panel('list', 'icon / avatar / number rows with actions', [],
        list([{ t: people[0].name, sub: people[0].id, avatar: people[0].init, actions: [secondary('Xếp lịch →', { sm: true })] }, { t: 'Row with icon', sub: 'sub line', sub2: 'second sub line', icon: 'event', actions: [badge('Đang chờ', 'info')] }])),
      panel('list box / ordered / plain', '', [], list([{ t: 'Boxed row', sub: 'sub' }, { t: 'Boxed row 2', sub: 'sub' }], { box: true }), list(['Bước một', 'Bước hai', 'Bước ba'], { ordered: true, plain: true }))),
    grid(2,
      panel('timeline', '', [], timeline({ date: '13/9/2026 · Cập nhật tại nhà', title: 'Cập nhật tại nhà đã được xem', detail: UPDATE, by: 'Ghi nhận bởi Điều dưỡng Hương', icon: 'chat_bubble' }, { date: '6/9/2026 · Buổi điều trị', title: 'Hoàn tất buổi 2/5', icon: 'check_circle', tone: 'success' }, { date: '1/9/2026 · Kế hoạch', title: 'Điều chỉnh kế hoạch', icon: 'edit_calendar', tone: 'warning' })),
      panel('bars, stat, legend', '', [], bars(['Đã đặt', 12, 60], ['Đã đến', 6, 30, 'success'], ['Vắng hẹn', 2, 10, 'danger']), grid(3, stat('Liệu trình hiện tại', 'Kiểm soát sắc tố'), stat('Buổi đã hoàn tất', '2', '', { unit: '/ 5 buổi' }), stat('Hẹn tiếp theo', '20/9/2026')), legend())),
    empty('empty title', 'empty hint with the action that fixes it', { icon: 'inbox', actions: [primary('Hồ sơ mới', { icon: 'add' })] })
  ]),
  page('WA903', 'Blocks · board, weekGrid, photos, a5, hero, img, containers', 'week/board rooms × time, weekGrid, photos (placeholders), a5 print preview, hero, img, box, disc, split', 'dashboard', [
    panel('board (alias week)', '08:00–12:00 · bước 30 phút', [badge('Theo phòng')], board({ from: 8, to: 12, hh: 64, rooms: rooms.map((r, i) => ({ ...r, bk: [{ start: '08:00', mins: 30, title: people[i].name, sub: services[i].name, sub2: doctors[i].name + ' · Đặt hẹn', svc: i }, { start: '09:30', mins: 45, buf: 15, title: people[i + 4].name, sub: services[(i + 1) % 4].name, sub2: doctors[(i + 1) % 4].name + ' · Đặt hẹn', svc: (i + 1) % 4 }], slots: [{ start: '08:30', mins: 30 }] })) })),
    panel('weekGrid', '', [], weekGrid({ days: ['CN, 20/09', 'T2, 21/09', 'T3, 22/09', 'T4, 23/09', 'T5, 24/09', 'T6, 25/09', 'T7, 26/09'].map((d, i) => ({ title: d, sub: (i + 2) + ' lịch', add: 'Đặt lịch', items: [{ time: '08:00–08:30', title: people[i].name, sub: 'Tái khám & đánh giá', svc: i % 4 }] })) })),
    grid(3,
      panel('card tint', 'tint: 0-3 = service, or a tone name', [], card({ tint: 1, title: 'tint 1 (brand)' }, txt('a service card')), card({ tint: 2, title: 'tint 2 (success)' }, txt('a service card')), card({ tint: 'warning', title: 'tint warning' }, txt('a service card'))),
      panel('photos', 'placeholders only', [], photos([{ label: 'Trước buổi 1', meta: '23/07' }, { label: 'Chưa có ảnh', empty: true }], { n: 2 }), photos([{ label: 'So sánh trượt', slider: true }], { n: 1 })),
      panel('a5', 'order print preview', [], a5({ title: 'ĐƠN THUỐC', draft: 'BẢN NHÁP — CHỜ BÁC SĨ DUYỆT', rows: [['Họ tên:', pt.name], ['Tuổi:', pt.age + ' · Nữ'], ['Mã hồ sơ:', pt.id], ['Ngày:', '20/9/2026'], ['Chẩn đoán:', 'Nám · tăng sắc tố', true]], items: [{ t: '1. Desloratadine 5 mg Hộp 30 Viên', qty: '× 1 Viên', use: 'Bôi lớp mỏng, sáng và tối, 14 ngày' }], note: 'Mang theo đơn này khi tái khám.', signDate: 'Ngày 20/9/2026', signRole: 'Bác sĩ khám', signName: 'BS. Tâm' })),
      stack({ g: 16 }, hero('Hero title', 'Hero subtitle', 'spa', { actions: [secondary('Action')] }), img('img placeholder', { h: 120 }),
        box({ tone: 'warning', title: 'box title' }, txt('box is a container: rich callouts'), row(badge('badge', 'warning'), secondary('Action', { sm: true }))))),
    disc('+ disc: Ghi nhận lượt thủ thuật đã hoàn tất', grid(3, input('Hồ sơ', 'Nguyễn Thu Hà · P001'), select('Thủ thuật', 'Tái khám & đánh giá'), number('Giá niêm yết', '300000'))),
    split([panel('split main', '1.65fr', [], txt('main column'))], [panel('split aside', '1fr', [], txt('aside column'))]),
    code('code block\nmonospace')
  ]),
  tab('WA904', 'Blocks · tab() Patient 360', 'tab(id, name, note, tabIndex, blocks): back link, hero card, 8 tabs', 1, [panel('Tab content', '', [], txt('Blocks of the tab go under the tab bar.'))]),
  fin('WA905', 'Blocks · fin() finance', 'fin(id, name, note, tabIndex, blocks, { role, title, tabs, eyebrow }): finance header and tabs', 1, [panel('Bảng tiền thủ thuật', '', [badge('Đang đối soát')], txt('Finance content.'))], { role: 'accountant' }),
  page('WA906', 'Blocks · page() options: role care, toast, narrow drawer', 'page options: role (sidebar by role), toast, drawer (390 only), fin override, state', 'crm', [pageHead('CSKH hôm nay', 'role care sees 4 menu items', [secondary('Xem protocol')])], { role: 'care-maianh', toast: 'Đã khôi phục dữ liệu demo', drawer: true }),
  dlg('WA907', 'Blocks · dlg() dialog', 'dlg(id, title, note, blocks, { eyebrow, sub, w, footer, nav, behind, role })', [
    row(badge('Đặt hẹn'), secondary('Xác nhận lịch'), secondary('Check-in')),
    grid(2, select('Bệnh nhân', 'Nguyễn Thu Hà'), select('Dịch vụ', 'Tái khám & đánh giá'), date('Ngày', '2026-09-20'), time('Giờ', '08:00')),
    notice('30 phút điều trị + 0 phút chuẩn bị · 300.000 ₫ · theo lịch đã đặt')
  ], { eyebrow: 'Pema · vận hành', w: 720, nav: 'schedule', footer: [secondary('Hủy'), primary('Lưu thay đổi')] })
];
