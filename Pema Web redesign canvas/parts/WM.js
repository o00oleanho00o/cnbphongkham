// WM · Inbox chia sẻ (package O, step O5; Next.js only). Owner: O5. Designed before it is built: step O6 builds these screens in pema-agent/frontend.
// Compositions kept local to this part (names start with wm). They use only blocks of base.js and borrow wj1* pieces of parts/WJ.js (channel panel).
// The notification screens (WM42-WM51) and the internal-notifier dialog (WM29) follow PLAN-AI01-O.md and the O3 recipe: PROVISIONAL until O3 merges.
const wmNXW = 'Next.js › ';

// The sidebar entry "Lịch trực" (O6 adds it to src/lib/nav.tsx, roles owner, manager, doctor, cs_staff). base.js is frozen (its text is part of the old-web canvas
// as well), so the entry is added here. WM is the last group: the frames of WJ-WL above were built before this line and keep their sidebar.
const wmRosterNav = ['/admin/roster', 'Lịch trực', 'event_available', '', 0, 'OMDC'];
NX_NAV.find(s => s[0] === 'Zalo & CSKH')[1].push(wmRosterNav);
NX_ITEMS.push(wmRosterNav);

// ---- sample data (synthetic): identities, operators, conversations ----
// Short codes are a hash sign plus 4 hex digits; the hash sign is joined at run time so the canvas check does not read them as hex colours.
const WM_H = '#';
const WM_LONG = 'Long';
const WM_BOT = 'Pema CSKH';
const WM_INT = 'Pema Nội bộ';
const wmCv = [
  { code: WM_H + '3F2A', name: people[0].name, pv: UPDATE, time: '09:12', unread: 2, ident: WM_LONG, holder: '' },
  { code: WM_H + '91C4', name: people[1].name, pv: 'Em gửi ảnh vùng da sau 3 ngày ạ.', time: '08:47', unread: 1, ident: WM_LONG, holder: '' },
  { code: WM_H + '7B05', name: people[2].name, pv: 'Chị muốn đổi lịch tái khám sang thứ Sáu.', time: '08:30', unread: 0, ident: WM_BOT, holder: '' },
  { code: WM_H + 'D210', name: 'Khách chưa gắn hồ sơ', pv: 'Cho mình hỏi soi da miễn phí còn không?', time: '08:05', unread: 1, ident: WM_BOT, holder: '' },
  { code: WM_H + '5E8B', name: people[3].name, pv: 'Cảm ơn bác sĩ, da em đỡ nhiều rồi.', time: 'Hôm qua', unread: 0, ident: WM_LONG, holder: 'Mai Anh' },
  { code: WM_H + 'A04C', name: people[4].name, pv: 'Em đã gửi ảnh mốc D+3 rồi ạ.', time: 'Hôm qua', unread: 0, ident: WM_LONG, holder: 'Hoàng Nam' }
];
const wmHolderLine = (c, me) => (!c.holder ? 'Chưa ai nhận' : c.holder === me ? 'Bạn đang giữ' : c.holder + ' đang giữ');
// one row of the list: code and identity over the name, preview, holder line and time, unread badge on the right
const wmRows = (items, me) => list(items.map(c => ({
  over: c.code + ' · ' + c.ident, t: c.name, sub: c.pv, sub2: wmHolderLine(c, me) + ' · ' + c.time,
  avatar: c.name.startsWith('Khách chưa') ? 'KH' : c.name.split(' ').slice(-2).map(v => v[0]).join(''), actions: c.unread ? [badge(c.unread + ' tin chưa đọc', 'brand', { dot: false })] : []
})), { box: true });

// ---- Inbox: list pane (tabs, identity filter, search, status chips) ----
const wmTabs = (on, n) => tabs([['Chờ nhận', n[0]], ['Của tôi', n[1]], ['Tất cả', n[2]]], on, { seg: true });
const wmFilters = (o = {}) => stack({ g: 12 },
  search('Tìm theo tên, mã hồ sơ hoặc nội dung'),
  row({ g: 8 }, secondary(o.ident || 'Tất cả danh tính', { ric: 'expand_more', aria: 'Lọc theo danh tính' })),
  chips([['Tất cả', 'sel'], 'Chờ duyệt', 'Chuyển nhân viên', 'Đang mở', 'Đã đóng']));
const wmSkeleton = n => stack({ g: 8 }, ...Array.from({ length: n }, () => img('Đang tải', { icon: 'hourglass_empty', h: 64 })));
const wmListPane = (o = {}) => card({ comp: 'ConversationList', g: 12 },
  wmTabs(o.tab || 0, o.counts || [4, 2, 6]), wmFilters(o),
  o.error ? notice('Không tải được danh sách hội thoại.', 'danger', { actions: [secondary('Thử lại')] }) : null,
  o.loading ? wmSkeleton(5) : null,
  o.empty ? empty(o.empty[0], o.empty[1], { icon: 'inbox' }) : null,
  o.items ? wmRows(o.items, o.me || '') : null);
const wmDetailEmpty = () => card({ comp: 'EmptyState' }, empty('Chọn một hội thoại', 'Tin khách gửi, nháp của trợ lý AI và ảnh khách gửi được gắn cờ chuyển nhân viên hiện ở đây.', { icon: 'forum' }));
const wmInbox = (o = {}) => [
  pageHead('Inbox', o.sub || '6 hội thoại · 2 có nháp chờ duyệt'),
  grid('minmax(0,1fr) minmax(0,1.5fr)', wmListPane(o), o.thread || wmDetailEmpty())
];
const wmQueue = wmCv.filter(c => !c.holder);
const wmMine = [{ ...wmCv[4], holder: 'Bạn' }];

// ---- Inbox: thread pane (holder banner, messages, composer) ----
const wmMsgs = () => bubbles(
  { text: UPDATE, time: '09:12', who: people[0].name },
  { text: 'Chào chị, em là Long của Pema. Chị cho em xin ảnh vùng da hiện tại để bác sĩ xem nhé ạ.', time: '09:20', mine: true, who: 'Hoàng Nam · qua Long' },
  { text: 'Dạ em gửi ảnh ạ.', time: '09:31', who: people[0].name, note: '[1 ảnh đính kèm - không hiển thị ở màn này]' });
const wmComposer = (o = {}) => stack({ g: 8 },
  o.err || null,
  textarea('', o.text || '', { ph: o.ph || 'Nhập tin trả lời khách...', lines: 2, dis: !!o.locked, hint: (o.text ? o.text.length : 0) + '/2000 · Tin do nhân viên soạn và gửi.' }),
  row({ g: 8, jc: 'space-between' }, sm('Khách thấy tin này từ "' + WM_LONG + '", không thấy tên nhân viên.'), primary('Gửi', { dis: !!o.locked || !o.text })));
const wmBannerFree = () => notice('Chưa có người phụ trách. Bấm Nhận để phụ trách hội thoại này; gửi tin trả lời cũng tự nhận.', 'info', { actions: [primary('Nhận')] });
const wmBannerMine = () => notice('Bạn đang phụ trách hội thoại này.', 'success', { actions: [secondary('Trả lại')] });
const wmBannerLocked = () => notice('Hoàng Nam đang trả lời — Tiếp quản?', 'warning', { actions: [primary('Tiếp quản')] });
const wmBannerRead = () => notice('Vai trò của bạn chỉ xem được hội thoại, không nhận hay trả lời được.', 'info');
const wmLockedPh = 'Hoàng Nam đang phụ trách. Tiếp quản để nhắn khách.';
const wmThread = (o = {}) => card({ comp: 'ThreadView', g: 12 },
  o.phone ? back('← Danh sách hội thoại') : null,
  row({ g: 12, jc: 'space-between', ai: 'flex-start' },
    stack({ g: 2 }, h2(o.name || people[0].name), sm('Xem hồ sơ ' + people[0].id + ' · ' + WM_LONG + ' · ' + WM_H + '3F2A'), o.view ? badge(o.view, 'neutral') : null),
    row({ g: 8, jc: 'flex-end' }, ...(o.buttons || []), secondary('Đang mở', { ric: 'expand_more', aria: 'Trạng thái hội thoại' }))),
  o.banner || null, wmMsgs(), wmComposer(o));
const wmBtnHistory = () => secondary('Lịch sử phụ trách');
const wmBtnAssign = () => secondary('Giao cho...', { aria: 'Giao hội thoại cho đồng nghiệp' });
const wmThreadPage = (o = {}) => wmInbox({ tab: o.tab || 0, counts: [4, 2, 6], items: o.items || wmQueue, me: o.me, thread: wmThread(o) });

// ---- Accounts: identities, limits, internal notifier ----
const wmAccCard = (a) => card({ comp: 'AccountCard', title: a.name, g: 6,
  aside: [badge(a.purpose, a.purpose === 'Nội bộ' ? 'neutral' : 'info', { dot: false }), ...a.badges.map(b => badge(b[0], b[1], { dot: b[2] !== false })), wj1Toggle('Bật account ' + a.name), ...(a.qr ? [secondary('Login QR', { sm: true })] : []), secondary('Sửa', { sm: true }), danger('Xóa', { sm: true })] },
  sm(a.sub),
  a.limit ? kv('Giới hạn đang áp dụng:', a.limit) : txt('Chỉ gửi thông báo cho nhân viên, không bao giờ nhắn cho khách.', { size: 's', tone: 'soft' }),
  a.duty ? kv('Đang trực:', a.duty) : null,
  row({ g: 8 }, secondary('Sửa danh tính', { sm: true }), a.duty ? secondary('Lịch trực', { sm: true }) : null));
const WM_ACCS = [
  { name: WM_LONG, purpose: 'Khách hàng', badges: [['Nick cá nhân', 'neutral', false], ['Đang chạy', 'success']], sub: 'long-ca-nhan · não: 🩺 CSKH Da liễu', limit: 'tối đa 5 tin chủ động/ngày · cách nhau 60–240 giây (theo kênh)', duty: 'Hoàng Nam 08:00–12:00', qr: true },
  { name: 'Pema CSKH (Zalo Bot)', purpose: 'Khách hàng', badges: [['Bot chính thức', 'neutral', false], ['Đang chạy', 'success']], sub: 'pema-bot · não: 🩺 CSKH Da liễu', limit: 'tối đa 10 tin chủ động/ngày · cách nhau 20–45 giây (riêng)', duty: 'Mai Anh 08:00–12:00' }
];
const WM_NOTIFIER = { name: WM_INT, purpose: 'Nội bộ', badges: [['Nick cá nhân', 'neutral', false], ['Đang chạy', 'success']], sub: 'noi-bo · gọi nhân viên và đăng nhóm Zalo của đội', limit: '', duty: '', qr: true };
const wmNotifierCard = (o = {}) => card({ comp: 'NotifierCard', title: 'Tài khoản thông báo nội bộ', g: 10,
  sub: 'Gọi nhân viên qua Zalo khi họ chưa mở thông báo và đăng nhóm Zalo của đội. Chỉ gửi cho nhân viên, không bao giờ nhắn cho khách.',
  aside: o.none ? [] : [badge('Đang chạy', 'success'), secondary('Cài đặt thông báo', { sm: true })] },
  o.none ? notice('Chưa có tài khoản thông báo nội bộ. Chuông Zalo và nhóm Zalo của đội bị bỏ qua; nhân viên chỉ nhận thông báo trong ứng dụng.', 'warning', { actions: [primary('Chọn tài khoản nội bộ')] })
    : facts(['Tài khoản', WM_INT], ['Chuông Zalo cho nhân viên', 'Bật'], ['Nhóm Zalo của đội', 'Đã đặt'], ['Chờ xác nhận trước khi gọi qua Zalo', '3 phút']));
const wmAccountsPage = (o = {}) => [
  pageHead('Tài khoản Zalo', 'Tài khoản Zalo của bot - mỗi account là một danh tính: khách chỉ thấy tên danh tính, không thấy tên nhân viên', [primary('Thêm account', { icon: 'add' })]),
  card({ title: 'Kênh gửi tin', sub: 'Cấu hình chung của từng kênh Zalo. Giới hạn riêng của từng danh tính ở dưới ghi đè giới hạn của kênh.' },
    grid(2,
      wj1Channel({ title: 'Tài khoản bot chính thức', pct: 30, sent: '3/10', cap: '10', min: '20', max: '90', from: '08:00', to: '20:00' }, {}),
      wj1Channel({ title: 'Tài khoản cá nhân', badges: [['Bridge đang chạy', 'success'], ['Chỉ gửi cho bạn bè', 'info']], pct: 20, sent: '1/5', cap: '5', min: '60', max: '240', from: '09:00', to: '18:00', warn: true }, {}))),
  h2('Danh tính', 'Khách hàng nhìn thấy tên của danh tính khi nhắn tin'),
  ...WM_ACCS.map(wmAccCard),
  o.none ? null : wmAccCard(WM_NOTIFIER),
  wmNotifierCard({ none: o.none })
];
const wmIdForm = (o = {}) => [
  input('Tên danh tính', WM_LONG, { hint: 'Tên khách nhìn thấy khi nhắn tin.' }),
  radio('Mục đích', [['Khách hàng · nhắn tin với khách', true], ['Nội bộ · chỉ gửi thông báo cho nhân viên', false]]),
  number('Tối đa tin chủ động mỗi ngày', '', { ph: 'Theo kênh: 5' }),
  grid(2, number('Cách nhau tối thiểu (giây)', o.min || '', { ph: 'Theo kênh: 60', err: o.minErr }), number('Cách nhau tối đa (giây)', o.max || '', { ph: 'Theo kênh: 240' })),
  sm('Để trống = dùng giới hạn của kênh.'),
  o.err ? errLine(o.err) : null
];

// ---- Roster: who covers which identity, week grid ----
const WM_ROLE_LEGEND = [['CSKH', 1], ['Bác sĩ', 2], ['Chủ phòng khám, quản lý', 3]];
const wmDayShift = (d) => {
  const base = { 'T2': [['08:00–12:00', 'Mai Anh', 'CSKH', 1], ['12:00–17:00', 'Hoàng Nam', 'CSKH', 1]], 'T3': [['08:00–12:00', 'Mai Anh', 'CSKH', 1], ['12:00–17:00', 'Hoàng Nam', 'CSKH', 1]], 'T4': [['08:00–12:00', 'Mai Anh', 'CSKH', 1], ['12:00–17:00', 'Hoàng Nam', 'CSKH', 1]],
    'T5': [['08:00–12:00', 'Mai Anh', 'CSKH', 1], ['12:00–17:00', 'Hoàng Nam', 'CSKH', 1]], 'T6': [['08:00–12:00', 'Mai Anh', 'CSKH', 1], ['12:00–17:00', 'Hoàng Nam', 'CSKH', 1]], 'T7': [['08:00–12:00', 'BS. Lê Minh Tâm', 'Bác sĩ', 2]], 'CN': [['08:00–12:00', 'Hoàng Nam', 'CSKH', 1]] };
  return base[d];
};
const wmWeek = (o = {}) => weekGrid({ legend: WM_ROLE_LEGEND, days: [['T2', '14/09'], ['T3', '15/09'], ['T4', '16/09'], ['T5', '17/09'], ['T6', '18/09'], ['T7', '19/09'], ['CN', '20/09']].map(([d, dt]) => {
  const items = o.empty ? [] : wmDayShift(d).map(([time, title, sub, svc]) => ({ time, title, sub, svc }));
  return { title: d + ', ' + dt, sub: items.length ? items.length + ' ca' : 'Chưa có ca', add: o.read ? '' : 'Thêm ca', items };
}) });
const wmRosterIds = (on = 0) => tabs([[WM_LONG], [WM_BOT]], on, { seg: true });
const wmDuty = (o = {}) => card({ comp: 'OnDutyCard', title: 'Đang trực bây giờ', sub: WM_LONG + ' · Chủ nhật 20/09/2026 · 09:00' },
  list([{ avatar: 'HN', t: 'Hoàng Nam', sub: 'CSKH · ca 08:00–12:00', actions: o.read ? [] : [secondary('Kết thúc ca', { sm: true })] }], { box: true }));
const wmRosterPage = (o = {}) => [
  pageHead('Lịch trực', 'Ai trực danh tính nào, khi nào. Hội thoại mới và khi hết ca được giao theo lịch này.', o.read ? [] : [primary('Thêm ca trực', { icon: 'add' })]),
  o.read ? notice('Bạn chỉ xem được lịch trực. Thêm, sửa ca và kết thúc ca là việc của chủ phòng khám và quản lý.', 'info') : null,
  wmRosterIds(0),
  o.error ? notice('Không tải được lịch trực.', 'danger', { actions: [secondary('Thử lại')] }) : [
    wmDuty(o),
    o.empty ? empty('Chưa có ca trực nào', 'Chưa ai trực danh tính này. Hội thoại mới vào hàng chờ và ai cũng nhận được.', { icon: 'event_busy', actions: o.read ? [] : [primary('Thêm ca trực')] })
      : card({ title: 'Tuần 14/09 – 20/09/2026', sub: 'Mỗi khối là một ca trực của một người; ca lặp theo thứ hiện ở mọi tuần.', aside: [secondary('Tuần trước', { sm: true }), secondary('Tuần sau', { sm: true })] }, wmWeek(o))]
];
const wmShiftForm = (o = {}) => [
  select('Danh tính', WM_LONG),
  select('Người trực', o.who || 'Hoàng Nam · CSKH'),
  radio('Kiểu lịch', [['Lặp theo thứ', !o.oneDay], ['Một ngày', !!o.oneDay]]),
  o.oneDay ? date('Ngày', '2026-09-22') : stack({ g: 6 }, lbl('Lặp vào các thứ'), chips([['Thứ 2', 'sel'], ['Thứ 3', 'sel'], ['Thứ 4', 'sel'], ['Thứ 5', 'sel'], ['Thứ 6', 'sel'], 'Thứ 7', 'CN'])),
  grid(2, time('Từ', o.from || '12:00'), time('Đến', o.to || '17:00')),
  sm(o.hint || 'Giờ đến nhỏ hơn giờ từ: ca kết thúc vào sáng hôm sau.'),
  input('Ghi chú', o.note || '', { ph: 'Ví dụ: trực thay Mai Anh', hint: 'Tối đa 200 ký tự.' }),
  o.err ? errLine(o.err) : null
];

// ---- /me/notifications (PROVISIONAL until O3) ----
const wmMeCards = (o = {}) => [
  pageHead('Thông báo của tôi', 'Cách Pema báo cho bạn khi có hội thoại cần nhận, bị tiếp quản hoặc hết ca'),
  card({ title: 'Trong ứng dụng', sub: 'Chuông trên thanh trên và trang Inbox cập nhật ngay.', aside: [badge('Luôn bật', 'success')] }, sm('Thông báo trong ứng dụng không tắt được.')),
  card({ title: 'Đẩy lên điện thoại', sub: 'Thông báo tới ứng dụng Pema trên điện thoại.', aside: [badge(o.push ? 'Đã đăng ký' : 'Chưa đăng ký', o.push ? 'success' : 'neutral')] },
    o.push ? list([{ icon: 'smartphone', t: 'Điện thoại của tôi', sub: 'iOS · hoạt động 20/09', actions: [secondary('Hủy đăng ký', { sm: true })] }], { box: true })
      : sm('Chưa có thiết bị nào đăng ký. Ứng dụng Pema trên điện thoại sẽ đăng ký thiết bị khi bạn đăng nhập; hiện chưa có bản nhận thông báo đẩy.')),
  card({ title: 'Chuông Zalo', sub: 'Pema nhắn bạn qua Zalo khi bạn chưa mở thông báo sau 3 phút.', aside: [badge(o.linked ? 'Đã liên kết' : 'Chưa liên kết', o.linked ? 'success' : 'neutral')] },
    o.noInternal ? notice('Phòng khám chưa cấu hình tài khoản thông báo nội bộ nên chưa liên kết Zalo được. Bạn vẫn nhận thông báo trong ứng dụng.', 'warning') : null,
    o.linked ? kv('Đồng ý nhận thông báo:', 'ngày 20/09/2026') : sm('Liên kết Zalo cá nhân để Pema gọi bạn khi bạn chưa mở thông báo sau 3 phút.'),
    sm('Tin chỉ có mã hội thoại, tên danh tính và đường dẫn, không có tên khách.'),
    o.linked ? secondary('Hủy liên kết') : primary('Liên kết Zalo', { dis: !!o.noInternal })),
  card({ title: 'Giờ yên tĩnh', sub: 'Không đổ chuông Zalo trong khoảng giờ này.' },
    check('Bật giờ yên tĩnh', o.quiet !== false, { desc: 'Tin khẩn vẫn đổ chuông.' }),
    grid(2, time('Từ', '22:00'), time('Đến', '06:00')), primary('Lưu')),
  notice('Mọi lần nhận, tiếp quản và hết ca được đăng lên nhóm Zalo của đội để cả đội thấy ai giữ hội thoại nào. Bạn không cần cài đặt gì cho nhóm này.', 'info')
];
const wmLinkBody = (o = {}) => [
  txt('Gửi mã dưới đây cho tài khoản "' + WM_INT + '" trên Zalo để Pema biết đây là tài khoản của bạn.'),
  code(o.expired ? 'PEMA-7K3Q  (đã hết hạn)' : 'PEMA-7K3Q'),
  list(['Mở Zalo trên điện thoại.', 'Gửi mã này cho tài khoản "' + WM_INT + '".', 'Chờ vài giây: trang này tự cập nhật.'], { plain: true, ordered: true }),
  o.expired ? errLine('Mã đã hết hạn. Tạo mã mới và gửi lại.') : sm('Mã dùng một lần, còn hiệu lực 09:12.')
];

const WM = [
  // ---- Inbox: queue, tabs, filters ----
  npage('WM1', 'Inbox · Chờ nhận', wmNXW + '/inbox · ba tab "Chờ nhận / Của tôi / Tất cả", lọc theo danh tính, hàng chờ là hội thoại chưa ai nhận (ở 390 trang thật chỉ hiện danh sách, khung này vẽ thêm ô "Chọn một hội thoại" bên dưới)', '/inbox',
    wmInbox({ tab: 0, counts: [4, 2, 6], items: wmQueue }), { nx: 'cs_staff' }),
  npage('WM2', 'Inbox · Của tôi', wmNXW + '/inbox · tab "Của tôi": hội thoại mình đang giữ, dòng người giữ ghi "Bạn đang giữ"', '/inbox',
    wmInbox({ tab: 1, counts: [4, 1, 6], items: wmMine, me: 'Bạn' }), { nx: 'cs_staff', state: true }),
  npage('WM3', 'Inbox · Tất cả · lọc theo danh tính', wmNXW + '/inbox · tab "Tất cả" với danh tính "Long": mọi hội thoại của một danh tính, thấy người đang giữ', '/inbox',
    wmInbox({ tab: 2, counts: [4, 2, 6], ident: WM_LONG, items: wmCv.filter(c => c.ident === WM_LONG) }), { nx: 'owner', state: true }),
  npage('WM4', 'Inbox · hàng chờ trống', wmNXW + '/inbox · tab "Chờ nhận" không có hội thoại nào', '/inbox',
    wmInbox({ tab: 0, counts: [0, 2, 6], empty: ['Không có hội thoại nào đang chờ nhận', 'Hội thoại mới chưa có người phụ trách sẽ hiện ở đây.'], sub: '6 hội thoại · 0 có nháp chờ duyệt' }), { nx: 'cs_staff', state: true }),
  npage('WM5', 'Inbox · đang tải', wmNXW + '/inbox · danh sách đang tải: khung xương 5 dòng', '/inbox',
    wmInbox({ tab: 0, counts: ['', '', ''], loading: true, sub: '0 hội thoại · 0 có nháp chờ duyệt' }), { nx: 'cs_staff', state: true }),
  npage('WM6', 'Inbox · lỗi tải', wmNXW + '/inbox · không tải được danh sách: thông báo lỗi và nút "Thử lại" trên danh sách', '/inbox',
    wmInbox({ tab: 0, counts: ['', '', ''], error: true, sub: '0 hội thoại · 0 có nháp chờ duyệt' }), { nx: 'cs_staff', state: true }),

  // ---- Inbox: thread ----
  npage('WM7', 'Hội thoại · chưa có người phụ trách', wmNXW + '/inbox?c= · hội thoại chưa ai nhận: thông báo "Chưa có người phụ trách" với nút "Nhận"; khung soạn tin mở, gửi tin cũng tự nhận', '/inbox',
    wmThreadPage({ banner: wmBannerFree(), buttons: [wmBtnHistory()], text: 'Dạ chào chị, em là Long của Pema.' }), { nx: 'cs_staff', state: true }),
  npage('WM8', 'Hội thoại · tôi đang phụ trách', wmNXW + '/inbox?c= · mình đang giữ: "Bạn đang phụ trách hội thoại này." với "Trả lại", "Lịch sử phụ trách"; quản lý đang xem chỉ đọc (không khóa)', '/inbox',
    wmThreadPage({ tab: 1, items: wmMine, me: 'Bạn', banner: wmBannerMine(), buttons: [wmBtnHistory()], view: 'Phạm Quốc Việt đang xem' }), { nx: 'cs_staff', state: true }),
  npage('WM9', 'Hội thoại · đồng nghiệp đang trả lời · soạn tin bị khóa', wmNXW + '/inbox?c= · hội thoại do Hoàng Nam giữ: "Hoàng Nam đang trả lời — Tiếp quản?" với nút "Tiếp quản"; khung soạn tin khóa. Chủ phòng khám và quản lý còn có "Giao cho..."', '/inbox',
    wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnAssign(), wmBtnHistory()], locked: true, ph: wmLockedPh, view: 'Hoàng Nam đang trả lời' }), { nx: 'manager', state: true }),
  npage('WM10', 'Hội thoại · điện thoại · chưa có người phụ trách', wmNXW + '/inbox?c= · 390: hội thoại là màn con có nút "Danh sách hội thoại", nút "Nhận" ở thông báo', '/inbox',
    [wmThread({ phone: true, banner: wmBannerFree(), buttons: [], text: '' })], { nx: 'cs_staff', state: true, frames: PHONE_FRAME }),
  npage('WM11', 'Hội thoại · điện thoại · soạn tin bị khóa', wmNXW + '/inbox?c= · 390: "Hoàng Nam đang trả lời — Tiếp quản?" và khung soạn tin khóa', '/inbox',
    [wmThread({ phone: true, banner: wmBannerLocked(), buttons: [], locked: true, ph: wmLockedPh })], { nx: 'cs_staff', state: true, frames: PHONE_FRAME }),
  npage('WM12', 'Hội thoại · đã bị tiếp quản', wmNXW + '/inbox?c= · đang mở hội thoại thì có người tiếp quản: toast "Đã bị tiếp quản", thông báo đổi sang "Hoàng Nam đang trả lời — Tiếp quản?", khung soạn tin khóa, chữ đang gõ vẫn còn', '/inbox',
    wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh, text: 'Dạ chào chị, em xem ảnh rồi ạ. Chị cho em hỏi' }), { nx: 'cs_staff', state: true, toast: 'Đã bị tiếp quản' }),
  npage('WM13', 'Hội thoại · gửi bị chặn (thread_locked)', wmNXW + '/inbox?c= · bấm "Gửi" khi đồng nghiệp vừa nhận: báo "Tin chưa gửi. Nội dung bạn soạn vẫn còn." và "Hoàng Nam đang trả lời — Tiếp quản?"', '/inbox',
    wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh, text: 'Dạ em gửi chị hướng dẫn chăm sóc da sau thủ thuật ạ.',
      err: notice('Tin chưa gửi. Nội dung bạn soạn vẫn còn.', 'danger', { actions: [primary('Tiếp quản')] }) }), { nx: 'cs_staff', state: true }),
  npage('WM14', 'Hội thoại · vừa đổi người phụ trách', wmNXW + '/inbox?c= · nhận hoặc tiếp quản với bản cũ: "Hội thoại vừa được cập nhật, đã tải lại." rồi hiện người giữ mới', '/inbox',
    wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh, err: notice('Hội thoại vừa được cập nhật, đã tải lại.', 'info') }), { nx: 'cs_staff', state: true }),
  npage('WM15', 'Hội thoại · không có quyền nhận', wmNXW + '/inbox?c= · lễ tân chỉ xem: không có nút "Nhận" và khung soạn tin, chỉ có thông báo vai trò', '/inbox',
    wmInbox({ tab: 2, counts: [4, 0, 6], items: wmCv, thread: card({ comp: 'ThreadView', g: 12 },
      row({ g: 12, jc: 'space-between', ai: 'flex-start' }, stack({ g: 2 }, h2(people[0].name), sm('Xem hồ sơ ' + people[0].id + ' · ' + WM_LONG + ' · ' + WM_H + '3F2A'))), wmBannerRead(), wmMsgs()) }), { nx: 'reception', state: true }),
  npage('WM16', 'Hội thoại · đang tải', wmNXW + '/inbox?c= · khung hội thoại đang tải: tiêu đề và tin nhắn dạng khung xương, các nút nhận, trả lại, tiếp quản chưa hiện', '/inbox',
    wmInbox({ tab: 0, items: wmQueue, thread: card({ comp: 'ThreadView', g: 12 }, wmSkeleton(3), textarea('', '', { ph: 'Nhập tin trả lời khách...', lines: 2, dis: true })) }), { nx: 'cs_staff', state: true }),

  // ---- Inbox: dialogs ----
  ndlg('WM17', 'Nhận hội thoại này?', wmNXW + '/inbox · hộp xác nhận "Nhận": người nhận là người duy nhất nhắn khách qua danh tính, cả đội thấy trên nhóm Zalo', [
    txt('Bạn sẽ là người phụ trách và là người duy nhất nhắn khách qua "' + WM_LONG + '" cho đến khi trả lại hoặc có người tiếp quản. Cả đội thấy trên nhóm Zalo.')], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ banner: wmBannerFree(), buttons: [wmBtnHistory()] }), w: 480, footer: [secondary('Hủy'), primary('Nhận')] }),
  ndlg('WM18', 'Tiếp quản hội thoại', wmNXW + '/inbox · hộp thoại "Tiếp quản": lý do bắt buộc (chỉ nhân viên xem), báo cho người đang giữ và nhóm Zalo', [
    textarea('Lý do tiếp quản', 'Chị khách cần bác sĩ xem ảnh ngay, Nam đang bận ca.', { lines: 3, hint: 'Chỉ nhân viên xem được lý do; khách không thấy. Tối đa 500 ký tự.' }),
    notice('Hoàng Nam, bạn và nhóm Zalo của đội sẽ nhận thông báo.', 'info')], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh }), w: 520, sub: 'Hoàng Nam đang phụ trách hội thoại ' + WM_H + '3F2A.', footer: [secondary('Hủy'), primary('Tiếp quản')] }),
  ndlg('WM19', 'Tiếp quản hội thoại', wmNXW + '/inbox · "Tiếp quản" chưa nhập lý do: ô lý do báo lỗi, nút "Tiếp quản" tắt', [
    textarea('Lý do tiếp quản', '', { lines: 3, err: 'Hãy nhập lý do tiếp quản.', hint: 'Chỉ nhân viên xem được lý do; khách không thấy. Tối đa 500 ký tự.' }),
    notice('Hoàng Nam, bạn và nhóm Zalo của đội sẽ nhận thông báo.', 'info')], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh }), w: 520, sub: 'Hoàng Nam đang phụ trách hội thoại ' + WM_H + '3F2A.', footer: [secondary('Hủy'), primary('Tiếp quản', { dis: true })] }),
  ndlg('WM20', 'Trả lại hội thoại', wmNXW + '/inbox · hộp thoại "Trả lại": về hàng chờ hoặc trả lại cho trợ lý AI, kèm ghi chú bàn giao', [
    radio('Trả lại cho', [['Về hàng chờ · ai cũng nhận được; hội thoại hiện ở tab Chờ nhận.', true], ['Trả lại cho trợ lý AI · trợ lý tiếp tục phụ trách. Chỉ trả được khi bệnh nhân đang ở trạng thái nhân viên xử lý.', false]]),
    textarea('Ghi chú bàn giao', '', { lines: 3, hint: 'Trợ lý đọc ghi chú này ở các lượt sau. Thông tin cá nhân được che trước khi lưu. Tối đa 500 ký tự.' })], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ tab: 1, items: wmMine, me: 'Bạn', banner: wmBannerMine(), buttons: [wmBtnHistory()] }), w: 560, sub: WM_H + '3F2A · ' + WM_LONG, footer: [secondary('Hủy'), primary('Trả lại')] }),
  ndlg('WM21', 'Trả lại hội thoại', wmNXW + '/inbox · trả lại cho trợ lý AI chưa được: thông báo của máy chủ, hội thoại giữ nguyên, "Về hàng chờ" vẫn dùng được', [
    radio('Trả lại cho', [['Về hàng chờ · ai cũng nhận được; hội thoại hiện ở tab Chờ nhận.', false], ['Trả lại cho trợ lý AI · trợ lý tiếp tục phụ trách. Chỉ trả được khi bệnh nhân đang ở trạng thái nhân viên xử lý.', true]]),
    textarea('Ghi chú bàn giao', 'Khách đã ổn, trợ lý nhắc tái khám sau 2 tuần.', { lines: 3, hint: 'Trợ lý đọc ghi chú này ở các lượt sau. Thông tin cá nhân được che trước khi lưu. Tối đa 500 ký tự.' }),
    notice('Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được.', 'warning')], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ tab: 1, items: wmMine, me: 'Bạn', banner: wmBannerMine(), buttons: [wmBtnHistory()] }), w: 560, sub: WM_H + '3F2A · ' + WM_LONG, footer: [secondary('Hủy'), primary('Trả lại')] }),
  ndlg('WM22', 'Giao hội thoại cho đồng nghiệp', wmNXW + '/inbox · chủ phòng khám và quản lý giao hội thoại cho người khác hoặc đưa về hàng chờ', [
    select('Người phụ trách', 'Mai Anh · CSKH', { hint: 'Danh sách gồm chủ phòng khám, quản lý, bác sĩ và CSKH đang hoạt động. Chọn "Bỏ người phụ trách (về hàng chờ)" để ai cũng nhận được.' }),
    notice('Người đang giữ, người được giao và nhóm Zalo của đội sẽ nhận thông báo.', 'info')], {
    nx: 'manager', nav: '/inbox', behind: wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnAssign(), wmBtnHistory()], locked: true, ph: wmLockedPh }), w: 480, sub: WM_H + '3F2A · ' + WM_LONG, footer: [secondary('Hủy'), primary('Giao')] }),
  ndlg('WM23', 'Lịch sử phụ trách', wmNXW + '/inbox · lịch sử ai giữ hội thoại, mới nhất ở trên; lý do tiếp quản chỉ nhân viên thấy', [
    timeline(
      { date: '20/09 09:40', title: 'Hoàng Nam tiếp quản từ Mai Anh', detail: 'Lý do: Chị khách cần bác sĩ xem ảnh ngay, Mai Anh đang bận ca.', by: 'Hoàng Nam', icon: 'swap_horiz', tone: 'warning' },
      { date: '20/09 09:14', title: 'Mai Anh nhận hội thoại', detail: '', by: 'Mai Anh', icon: 'person_add', tone: 'success' },
      { date: '19/09 17:02', title: 'Hết ca: Hoàng Nam trả hội thoại về hàng chờ', detail: '', by: 'Hệ thống', icon: 'logout', tone: '' })], {
    nx: 'cs_staff', nav: '/inbox', behind: wmThreadPage({ tab: 2, items: wmCv, banner: wmBannerLocked(), buttons: [wmBtnHistory()], locked: true, ph: wmLockedPh }), w: 520, sub: WM_H + '3F2A · ' + WM_LONG, footer: [secondary('Đóng')] }),

  // ---- Accounts: identities ----
  npage('WM24', 'Tài khoản Zalo · danh tính và giới hạn gửi', wmNXW + '/admin/accounts · mỗi account là một danh tính: nhãn "Khách hàng" hoặc "Nội bộ", giới hạn đang áp dụng, người đang trực; thẻ "Tài khoản thông báo nội bộ". Không có ô nào chứa mật khẩu, token hay mã QR', '/admin/accounts',
    wmAccountsPage(), { nx: 'owner' }),
  npage('WM25', 'Tài khoản Zalo · chưa có tài khoản thông báo nội bộ', wmNXW + '/admin/accounts · chưa có danh tính nội bộ: thẻ thông báo nội bộ báo chuông Zalo và nhóm Zalo bị bỏ qua', '/admin/accounts',
    wmAccountsPage({ none: true }), { nx: 'owner', state: true }),
  ndlg('WM26', 'Sửa danh tính', wmNXW + '/admin/accounts · hộp thoại danh tính: tên, mục đích, giới hạn riêng (để trống = theo kênh); không có ô nào cho khóa đăng nhập', wmIdForm(), {
    nx: 'owner', nav: '/admin/accounts', behind: wmAccountsPage(), w: 560, sub: WM_LONG + ' · Zalo cá nhân', footer: [secondary('Hủy'), primary('Lưu')] }),
  ndlg('WM27', 'Sửa danh tính', wmNXW + '/admin/accounts · giới hạn không hợp lệ: khoảng nghỉ tối thiểu lớn hơn tối đa, nút Lưu tắt', wmIdForm({ min: '300', max: '240', minErr: 'Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa.' }), {
    nx: 'owner', nav: '/admin/accounts', behind: wmAccountsPage(), w: 560, sub: WM_LONG + ' · Zalo cá nhân', footer: [secondary('Hủy'), primary('Lưu', { dis: true })] }),
  ndlg('WM28', 'Sửa danh tính', wmNXW + '/admin/accounts · đổi sang "Nội bộ" bị từ chối vì còn hội thoại gắn với danh tính; biểu mẫu vẫn mở', wmIdForm({ err: 'Không đổi được: còn hội thoại đang gắn với danh tính này.' }), {
    nx: 'owner', nav: '/admin/accounts', behind: wmAccountsPage(), w: 560, sub: WM_LONG + ' · Zalo cá nhân', footer: [secondary('Hủy'), primary('Lưu')] }),
  ndlg('WM29', 'Cài đặt thông báo', wmNXW + '/admin/accounts · (tạm, chờ O3) công tắc chuông Zalo, nhóm Zalo của đội, đẩy điện thoại và thời gian chờ xác nhận; không hiện mã nhóm hay token', [
    check('Chuông Zalo cho nhân viên', true, { desc: 'Gọi nhân viên qua tài khoản "' + WM_INT + '" khi họ chưa mở thông báo.' }),
    check('Đăng nhóm Zalo của đội', true, { desc: 'Nhóm Zalo của đội: Đã đặt.' }),
    check('Đẩy lên điện thoại', false, { desc: 'Chưa bật: cần khóa dịch vụ đẩy của phòng khám.' }),
    number('Chờ xác nhận trước khi gọi qua Zalo (phút)', '3')], {
    nx: 'owner', nav: '/admin/accounts', behind: wmAccountsPage(), w: 560, sub: 'Áp dụng cho cả phòng khám', footer: [secondary('Hủy'), primary('Lưu')] }),

  // ---- Roster ----
  npage('WM30', 'Lịch trực', wmNXW + '/admin/roster · lịch trực theo danh tính: ai đang trực, lưới tuần Thứ 2 đến Chủ nhật, thêm ca; mục "Lịch trực" mới trong menu "Zalo & CSKH"', '/admin/roster',
    wmRosterPage(), { nx: 'manager' }),
  npage('WM31', 'Lịch trực · chỉ xem', wmNXW + '/admin/roster · bác sĩ và CSKH chỉ đọc: không có "Thêm ca trực", "Thêm ca", "Kết thúc ca"', '/admin/roster',
    wmRosterPage({ read: true }), { nx: 'cs_staff', state: true }),
  npage('WM32', 'Lịch trực · chưa có ca', wmNXW + '/admin/roster · danh tính chưa có ca nào: hội thoại mới vào hàng chờ, ai cũng nhận được', '/admin/roster',
    wmRosterPage({ empty: true }), { nx: 'manager', state: true }),
  npage('WM33', 'Lịch trực · lỗi tải', wmNXW + '/admin/roster · không tải được lịch: thông báo lỗi và nút "Thử lại"', '/admin/roster',
    wmRosterPage({ error: true }), { nx: 'manager', state: true }),
  ndlg('WM34', 'Thêm ca trực', wmNXW + '/admin/roster · hộp thoại thêm ca lặp theo thứ: danh tính, người trực, các thứ, giờ từ đến, ghi chú', wmShiftForm(), {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 560, footer: [secondary('Hủy'), primary('Thêm ca')] }),
  ndlg('WM35', 'Thêm ca trực', wmNXW + '/admin/roster · "Một ngày" chọn ngày cụ thể; ca 22:00 đến 06:00 kết thúc vào sáng hôm sau', wmShiftForm({ oneDay: true, from: '22:00', to: '06:00', hint: 'Ca kết thúc vào 06:00 sáng hôm sau.', note: 'Trực đêm lễ' }), {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 560, footer: [secondary('Hủy'), primary('Thêm ca')] }),
  ndlg('WM36', 'Thêm ca trực', wmNXW + '/admin/roster · giờ từ trùng giờ đến: dòng lỗi "Giờ bắt đầu và giờ kết thúc phải khác nhau."', wmShiftForm({ from: '12:00', to: '12:00', err: 'Giờ bắt đầu và giờ kết thúc phải khác nhau.' }), {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 560, footer: [secondary('Hủy'), primary('Thêm ca')] }),
  ndlg('WM37', 'Sửa ca trực', wmNXW + '/admin/roster · sửa ca đã có: điền sẵn giá trị, nút "Xóa ca" bên trái', wmShiftForm({ who: 'Mai Anh · CSKH', from: '08:00', to: '12:00' }), {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 560, footer: [danger('Xóa ca'), secondary('Hủy'), primary('Lưu')] }),
  ndlg('WM38', 'Sửa ca trực', wmNXW + '/admin/roster · ca vừa được người khác sửa: "Ca trực vừa được người khác sửa. Đã tải lại."', [
    notice('Ca trực vừa được người khác sửa. Đã tải lại.', 'info'), ...wmShiftForm({ who: 'Mai Anh · CSKH', from: '08:00', to: '11:30' })], {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 560, footer: [danger('Xóa ca'), secondary('Hủy'), primary('Lưu')] }),
  ndlg('WM39', 'Xóa ca trực này?', wmNXW + '/admin/roster · hộp xác nhận xóa ca; hội thoại đang giữ không bị đổi', [
    txt('Mai Anh sẽ không còn được xếp trực "' + WM_LONG + '" vào các giờ này. Hội thoại đang giữ không bị đổi.')], {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 440, footer: [secondary('Hủy'), danger('Xóa ca')] }),
  ndlg('WM40', 'Kết thúc ca của Mai Anh?', wmNXW + '/admin/roster · hộp xác nhận kết thúc ca: hội thoại đang mở chuyển cho người đang trực hoặc về hàng chờ', [
    txt('Các hội thoại đang mở của Mai Anh chuyển cho người đang trực danh tính đó; nếu không có ai trực, chuyển về hàng chờ. Cả hai bên và nhóm Zalo nhận thông báo.')], {
    nx: 'manager', nav: '/admin/roster', behind: wmRosterPage(), w: 480, footer: [secondary('Hủy'), danger('Kết thúc ca')] }),
  npage('WM41', 'Kết thúc ca · kết quả', wmNXW + '/admin/roster · sau khi kết thúc ca: toast số hội thoại đã chuyển, về hàng chờ, bỏ qua', '/admin/roster',
    wmRosterPage(), { nx: 'manager', state: true, toast: 'Đã kết thúc ca: 4 hội thoại chuyển người trực, 1 về hàng chờ, 0 bỏ qua.' }),

  // ---- /me/notifications (PROVISIONAL until O3) ----
  npage('WM42', 'Thông báo của tôi', wmNXW + '/me/notifications · (tạm, chờ O3) trong ứng dụng, đẩy điện thoại, chuông Zalo, giờ yên tĩnh; không có trong menu, mở từ chuông và tên người dùng', '/me/notifications',
    wmMeCards({ linked: true }), { nx: 'cs_staff', crumb: 'Thông báo của tôi' }),
  npage('WM43', 'Thông báo của tôi · chưa liên kết Zalo', wmNXW + '/me/notifications · (tạm, chờ O3) thẻ "Chuông Zalo" chưa liên kết: nút "Liên kết Zalo"', '/me/notifications',
    wmMeCards({}), { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi' }),
  ndlg('WM44', 'Liên kết Zalo', wmNXW + '/me/notifications · (tạm, chờ O3) mã dùng một lần để gửi cho tài khoản nội bộ trên Zalo, tự cập nhật khi nhận được', wmLinkBody(), {
    nx: 'cs_staff', nav: '/me/notifications', behind: wmMeCards({}), w: 480, sub: 'Mã chỉ dùng được một lần', footer: [secondary('Đóng')] }),
  ndlg('WM45', 'Liên kết Zalo', wmNXW + '/me/notifications · (tạm, chờ O3) mã đã hết hạn: dòng lỗi và nút "Tạo mã mới"', wmLinkBody({ expired: true }), {
    nx: 'cs_staff', nav: '/me/notifications', behind: wmMeCards({}), w: 480, sub: 'Mã chỉ dùng được một lần', footer: [secondary('Đóng'), primary('Tạo mã mới')] }),
  npage('WM46', 'Thông báo của tôi · đã liên kết Zalo', wmNXW + '/me/notifications · (tạm, chờ O3) liên kết xong: toast "Đã liên kết Zalo." và thẻ "Đã liên kết"', '/me/notifications',
    wmMeCards({ linked: true }), { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi', toast: 'Đã liên kết Zalo.' }),
  ndlg('WM47', 'Hủy liên kết Zalo?', wmNXW + '/me/notifications · (tạm, chờ O3) hộp xác nhận hủy liên kết chuông Zalo', [
    txt('Pema sẽ không gọi bạn qua Zalo nữa. Bạn vẫn nhận thông báo trong ứng dụng.')], {
    nx: 'cs_staff', nav: '/me/notifications', behind: wmMeCards({ linked: true }), w: 440, footer: [secondary('Giữ liên kết'), danger('Hủy liên kết')] }),
  npage('WM48', 'Thông báo của tôi · đã đăng ký điện thoại', wmNXW + '/me/notifications · (tạm, chờ O3) đã có một thiết bị nhận thông báo đẩy: dòng thiết bị và nút "Hủy đăng ký"', '/me/notifications',
    wmMeCards({ linked: true, push: true }), { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi' }),
  npage('WM49', 'Thông báo của tôi · giờ yên tĩnh', wmNXW + '/me/notifications · (tạm, chờ O3) đã lưu giờ yên tĩnh 22:00 đến 06:00; tin khẩn vẫn đổ chuông', '/me/notifications',
    wmMeCards({ linked: true }), { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi', toast: 'Đã lưu giờ yên tĩnh.' }),
  npage('WM50', 'Thông báo của tôi · chưa có tài khoản nội bộ', wmNXW + '/me/notifications · (tạm, chờ O3) phòng khám chưa cấu hình tài khoản thông báo nội bộ: nút "Liên kết Zalo" tắt', '/me/notifications',
    wmMeCards({ noInternal: true }), { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi' }),
  npage('WM51', 'Thông báo của tôi · đang tải và lỗi', wmNXW + '/me/notifications · (tạm, chờ O3) không tải được cài đặt: thông báo lỗi và "Thử lại"; khi đang tải là khung xương ba thẻ', '/me/notifications', [
    pageHead('Thông báo của tôi', 'Cách Pema báo cho bạn khi có hội thoại cần nhận, bị tiếp quản hoặc hết ca'),
    notice('Không tải được cài đặt thông báo.', 'danger', { actions: [secondary('Thử lại')] }), wmSkeleton(3)], { nx: 'cs_staff', state: true, crumb: 'Thông báo của tôi' })
];
