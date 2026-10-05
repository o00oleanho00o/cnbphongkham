// WJ (part 1) · Quản trị agent: Nhân viên, Tài khoản của tôi, Tổng quan AI, Phiên chat, Danh bạ, Bạn bè, Lịch hẹn của bot, Trí nhớ, Kho tri thức, Tài khoản Zalo (WJ1-WJ57; Next.js only, W2 step W10).
const wj1NXW = 'Next.js › ';

// ---- shared pieces ----
const wj1Pw = (label, o = {}) => input(label, o.val || '', { suf: 'visibility', sufAria: 'Hiện nội dung', hint: o.hint, desc: o.desc, ph: o.ph });
const wj1Pager = () => row({ g: 8 }, secondary('Trước', { dis: true }), txt('Trang 1'), secondary('Sau', { dis: true }));
const wj1AccountFilter = () => secondary('Tất cả account', { ric: 'expand_more', aria: 'Lọc theo account' });
const wj1Toolbar = (ph, o = {}) => row({ g: 12, jc: 'space-between' }, row({ g: 12 }, search(ph, { w: 288 }), o.noAccount ? null : wj1AccountFilter()), wj1Pager());
const wj1Who = (name, sub, ini) => cell([avatar(ini || name.replace('BS. ', '').charAt(0)), txt([[name, 'b'], '\n', [sub, 'sm soft']])], { row: true });
const wj1Toggle = (aria, on = true) => btn('', 'quiet', { ico: true, icon: on ? 'toggle_on' : 'toggle_off', aria });

// ---- Nhân viên (/admin/users) ----
const wj1Staff = [
  ['BS. Lê Minh Tâm', 'doctor@pema.test', 'Bác sĩ', false, '20/09 09:00', '24/03/2026'],
  ['BS. Trương Hoài An', 'bsan@pema.test', 'Bác sĩ', false, '18/09 09:00', '22/06/2026'],
  ['Bùi Ngọc Lan', 'lan@pema.test', 'Lễ tân', true, '12/07 09:00', '24/11/2025'],
  ['Đặng Minh Thư', 'thu@pema.test', 'CSKH', false, 'Chưa đăng nhập', '22/07/2026'],
  ['Mai Anh', 'cs@pema.test', 'CSKH', false, '20/09 08:10', '23/04/2026'],
  ['Nguyễn Thanh Hà', 'owner@pema.test', 'Chủ phòng khám', false, '20/09 09:00', '23/01/2026', true],
  ['Phạm Quốc Việt', 'manager@pema.test', 'Quản lý', false, '20/09 06:00', '04/03/2026'],
  ['Võ Ngọc Trâm', 'reception@pema.test', 'Lễ tân', false, '15/09 09:00', '23/05/2026']
];
const wj1StaffRow = ([name, email, role, locked, last, created, self], manage) => {
  const who = wj1Who(name + (self ? ' (Bạn)' : ''), email, name.replace('BS. ', '').charAt(0));
  const acts = self ? [secondary('Sửa', { sm: true, aria: 'Sửa ' + name })] : [
    secondary('Sửa', { sm: true, aria: 'Sửa ' + name }),
    secondary('Đặt lại mật khẩu', { sm: true, aria: 'Đặt lại mật khẩu của ' + name }),
    locked ? secondary('Mở khóa', { sm: true, aria: 'Mở khóa tài khoản của ' + name }) : danger('Khóa', { sm: true, aria: 'Khóa tài khoản của ' + name })];
  const base = [who, [badge(role, 'info', { dot: false })], [badge(locked ? 'Đã khóa' : 'Đang hoạt động', locked ? 'danger' : 'success')], last, created];
  return manage ? [...base, cell(acts, { row: true })] : base;
};
const wj1UsersHead = manage => pageHead('Nhân viên', 'Tài khoản đăng nhập của phòng khám: vai trò, trạng thái và mật khẩu', manage ? [primary('Thêm nhân viên', { icon: 'add' })] : []);
const wj1UsersFilters = q => [
  search('Tìm theo họ tên hoặc email', { label: 'Tìm nhân viên', val: q, w: 448 }),
  chips([['Mọi vai trò', 'sel'], 'Chủ phòng khám', 'Quản lý', 'Bác sĩ', 'CSKH', 'Lễ tân']),
  chips([['Mọi trạng thái', 'sel'], 'Đang hoạt động', 'Đã khóa'])
];
const wj1UsersTable = manage => table(
  manage ? ['Nhân viên', ['Vai trò', '140px'], ['Trạng thái', '150px'], ['Đăng nhập cuối', '150px'], ['Ngày tạo', '110px'], ['Thao tác', '1.1fr']] : ['Nhân viên', 'Vai trò', 'Trạng thái', 'Đăng nhập cuối', 'Ngày tạo'],
  wj1Staff.map(s => wj1StaffRow(s, manage)));
const wj1UsersPage = () => [wj1UsersHead(true), ...wj1UsersFilters(''), wj1UsersTable(true)];

// ---- Tổng quan AI (/admin/overview) ----
const wj1OverviewBody = (o = {}) => [
  pageHead('Tổng quan', 'Trạng thái bot và mức dùng LLM'),
  o.noLlm ? notice('Thiếu API key, tên model hoặc base URL.', 'warning', { title: 'Chưa cấu hình LLM - bot chưa trả lời được tin nhắn nào', actions: [quiet('Nhập ở trang Cấu hình')] }) : null,
  kpis(kpi('Tin nhắn hôm nay', '53', '', { icon: 'chat' }), kpi('Lượt agent hôm nay', o.empty ? '0' : '29', '', { icon: 'bolt' }),
    kpi('Token hôm nay', o.empty ? '0' : '46.980', o.empty ? '0 vào / 0 ra' : '40.600 vào / 6.380 ra', { icon: 'memory' }), kpi('Phiên chat', '5', '', { icon: 'chat_bubble' })),
  card({ title: 'Tình trạng hệ thống', sub: 'Bot đang chạy ra sao và giữ bao nhiêu dữ liệu', aside: [badge('Python 3.12 · vmock', 'neutral', { dot: false })] },
    grid(3, stat('Uptime', '1d 1h 0m', 'Thời gian hoạt động'), stat('Múi giờ', 'Asia/Ho_Chi_Minh', 'Ngày và trần mỗi ngày tính theo múi giờ này'), stat('Accounts online', '2 / 2', 'Tài khoản đang online'), stat('Phiên chat', '5', 'Phiên hội thoại của trợ lý AI')),
    eyebrow('Kênh'), tags(badge('Pema CSKH (Zalo Bot)', 'success'), badge('Zalo lễ tân (cá nhân)', 'success'))),
  o.empty ? null : card({ title: 'Mức sử dụng', sub: 'Theo dõi hoạt động 7 ngày gần nhất', aside: [secondary('Lượt dùng', { sm: true }), quiet('Token', { sm: true }), secondary('7 ngày qua', { icon: 'schedule', ric: 'expand_more', aria: 'Khoảng thời gian của biểu đồ' })] },
    grid(3, stat('Tổng lượt', '218'), stat('Tổng token', '353.160'), stat('Trung bình/ngày', '50.451')),
    row({ g: 16 }, sm('40'), sm('30'), sm('20'), sm('10'), sm('0')),
    bars(['09-14', 25, 62], ['09-15', 35, 88], ['09-16', 27, 68], ['09-17', 36, 90], ['09-18', 28, 70], ['09-19', 38, 95], ['09-20', 29, 72]),
    sm('Đưa chuột lên từng cột để xem cả số lượt lẫn số token của ngày đó.'))
];

// ---- Phiên chat AI (/admin/sessions) ----
const wj1Sessions = [
  ['Nguyễn Thu Hà', 'u-demo-001', 'Pema CSKH (Zalo Bot)', 'Chat riêng', '18', '20/09 08:48', true],
  ['Trần Minh Anh', 'u-demo-002', 'Pema CSKH (Zalo Bot)', 'Chat riêng', '7', '20/09 08:35', false],
  ['Khách chưa gắn hồ sơ', 'u-demo-004', 'Pema CSKH (Zalo Bot)', 'Chat riêng', '2', '20/09 07:00', true],
  ['Lễ tân Trâm', 'u-demo-021', 'Zalo lễ tân (cá nhân)', 'Chat riêng', '64', '20/09 06:00', true],
  ['Nhóm điều phối phòng khám', 'g-demo-001', 'Zalo lễ tân (cá nhân)', 'Nhóm', '240', '19/09 09:00', true]
];
const wj1SessionsHead = () => pageHead('Phiên chat AI', 'Mỗi cuộc trò chuyện (chat riêng hoặc nhóm) là một phiên; ngữ cảnh trò chuyện của trợ lý AI giữ ở đây. Có thể chứa dữ liệu bệnh nhân: chỉ nhân viên được phân quyền xem.');
const wj1SessionCols = ['Tên', 'Account', 'Loại', 'Tin nhắn', 'Tin cuối', 'Bot', ['', '120px']];
const wj1SessionRow = ([name, id, acc, kind, n, last, on]) => [
  wj1Who(name, id), [badge(acc, 'neutral', { dot: false })], [badge(kind, kind === 'Nhóm' ? 'warning' : 'info', { dot: false })], n, last,
  [wj1Toggle(on ? 'Bot đang bật - bấm để tắt' : 'Bot đang tắt - bấm để bật', on)],
  cell([quiet('Xem', { sm: true }), btn('', 'danger', { ico: true, icon: 'delete', aria: 'Xóa hẳn session này', sm: true })], { row: true })
];
const wj1SessionsPage = () => [wj1SessionsHead(), wj1Toolbar('Tìm theo tên hoặc thread ID...'), table(wj1SessionCols, wj1Sessions.map(wj1SessionRow))];
const wj1SessionTabs = on => tabs(['Hội thoại', 'Trace agent'], on);
const wj1SessionDetailHead = () => row({ g: 12, jc: 'space-between' }, stack({ g: 2 }, strong('Nguyễn Thu Hà'), sm('18 tin')), secondary('Đóng'));
const wj1Chat = () => bubbles(
  { who: 'Nguyễn Thu Hà', text: 'Chào phòng khám, em là Hà, hôm qua em làm laser.', time: '17/09 09:00' },
  { text: 'Chào chị, em là trợ lý của phòng khám. Chị cần hỗ trợ gì về chăm sóc da sau laser ạ?', time: '17/09 09:01', mine: true },
  { who: 'Nguyễn Thu Hà', text: 'Da em hơi đỏ, em chụp gửi ạ.', note: '[1 ảnh đính kèm - không hiển thị ở màn này]', time: '20/09 08:48' });
const wj1Runs = [
  ['2 step - 1.680 token', '20/09 08:55'], ['3 step - 1.822 token', '20/09 08:08'], ['4 step - 1.964 token', '20/09 07:21'], ['3 step - 2.248 token', '20/09 05:47'], ['4 step - 2.390 token', '20/09 05:00'],
  ['2 step - 2.532 token', '20/09 04:13'], ['4 step - 2.816 token', '20/09 02:39'], ['2 step - 2.958 token', '20/09 01:52'], ['3 step - 3.100 token', '20/09 01:05']
];
const wj1RunButtons = () => wj1Runs.map(([a, b]) => trace({ label: a + ' ' + b }));
const wj1ConfirmSession = [secondary('Xóa bản tóm tắt'), danger('Xóa sạch ngữ cảnh')];

// ---- Danh bạ, Bạn bè ----
const wj1Contacts = [
  ['Nguyễn Thu Hà', 'Pema CSKH (Zalo Bot)', 'u-demo-001', '18', '21/08 09:00', '20/09 08:48'],
  ['Trần Minh Anh', 'Pema CSKH (Zalo Bot)', 'u-demo-002', '7', '02/09 10:15', '20/09 08:35'],
  ['Khách chưa gắn hồ sơ', 'Pema CSKH (Zalo Bot)', 'u-demo-004', '2', '20/09 06:50', '20/09 07:00'],
  ['Lễ tân Trâm', 'Zalo lễ tân (cá nhân)', 'u-demo-021', '64', '01/08 08:00', '20/09 06:00'],
  ['Nhóm điều phối phòng khám', 'Zalo lễ tân (cá nhân)', 'g-demo-001', '240', '01/08 08:05', '19/09 09:00']
];
const wj1ContactsHead = () => pageHead('Danh bạ', 'Tự thu thập từ mọi tin nhắn đến, kể cả người trợ lý AI không trả lời');
const wj1ContactCols = ['Tên', 'Account', 'User ID', 'Số tin', 'Lần đầu', 'Gần nhất', ['', '60px']];
const wj1ContactsPage = () => [wj1ContactsHead(), wj1Toolbar('Tìm theo tên hoặc user ID...'), table(wj1ContactCols, wj1Contacts.map(([n, a, u, c, f, l]) => [
  wj1Who(n, ''), [badge(a, 'neutral', { dot: false })], u, c, f, l, [btn('', 'danger', { ico: true, icon: 'delete', aria: 'Xóa danh bạ', sm: true })]]))];
const wj1FriendsHead = () => pageHead('Bạn bè', 'Duyệt yêu cầu kết bạn và xem danh sách bạn (chỉ nick cá nhân đang chạy)');
const wj1AccountPicker = label => secondary(label, { ric: 'expand_more', aria: 'Chọn tài khoản' });
const wj1FriendNote = () => sm('Chỉ hiện yêu cầu tới TỪ KHI bật tính năng và bot đang chạy - Zalo không cho lấy lại yêu cầu cũ.');
const wj1Pending = () => table(['', 'Tên', 'Lời nhắn', 'Nhận lúc', ['', '120px']], [
  [[avatar('H')], 'Hải Yến (mẫu)', 'Chào phòng khám, mình muốn hỏi lịch.', '08:40:00 20/9/2026', cell([btn('', 'quiet', { ico: true, icon: 'check', aria: 'Chấp nhận', sm: true }), btn('', 'danger', { ico: true, icon: 'close', aria: 'Từ chối', sm: true })], { row: true })],
  [[avatar('B')], 'Bảo Ngọc (mẫu)', 'Mình là khách cũ của phòng khám.', '08:41:30 20/9/2026', cell([btn('', 'quiet', { ico: true, icon: 'check', aria: 'Chấp nhận', sm: true }), btn('', 'danger', { ico: true, icon: 'close', aria: 'Từ chối', sm: true })], { row: true })]
], { });
const wj1FriendList = () => table(['', 'Tên', 'User ID'], [[[avatar('M')], 'Mai Linh (mẫu)', 'u-demo-031'], [[avatar('T')], 'Thu Trang (mẫu)', 'u-demo-032'], [[avatar('P')], 'Phương Vy (mẫu)', 'u-demo-033']]);
const wj1FriendsPage = () => [wj1FriendsHead(), wj1AccountPicker('Zalo lễ tân (cá nhân)'), wj1FriendNote(), h2('Chờ duyệt (2)'), wj1Pending(),
  row({ g: 12, jc: 'space-between' }, h2('Danh sách bạn (3)'), secondary('Làm mới')), wj1FriendList()];

// ---- Lịch hẹn của bot (/admin/schedules) ----
const wj1JobCard = (title, badges, line, errText, runBtns) => card({ comp: 'ScheduleJobCard', g: 10 },
  row({ g: 8 }, strong(title), tags(...badges)), sm(line), errText ? notice(errText, 'danger') : null,
  row({ g: 8 }, wj1Toggle('Đang bật - bấm để tắt'), secondary('Chạy thử ngay', { sm: true }), secondary('Lịch sử', { sm: true }), secondary('Sửa', { sm: true }), danger('Xóa', { sm: true })));
const wj1Jobs = (o = {}) => [
  wj1JobCard('Nhắc tái khám tuần sau', [badge('Nhắn tin', 'neutral', { dot: false }), badge('Quy tắc chăm sóc', 'neutral', { dot: false }), badge('Một lần', 'neutral', { dot: false }), o.err ? badge('Lỗi', 'danger') : badge('Chưa chạy lần nào', 'neutral')],
    'Pema CSKH (Zalo Bot) · u-demo-005 · Lần kế tiếp: 09:00 22-09', o.err ? 'Zalo trả lỗi khi gửi tin: kênh tạm thời không gửi được.' : ''),
  wj1JobCard('Tóm tắt việc cuối ngày', [badge('Agent', 'neutral', { dot: false }), badge('Nhân viên đặt', 'neutral', { dot: false }), badge('Cron: 30 17 * * 1-6', 'neutral', { dot: false }), o.err ? badge('Đang bị chặn', 'warning') : badge('Thành công', 'success')],
    'Zalo lễ tân (cá nhân) · Lễ tân Trâm · Lần kế tiếp: 14:00 20-09 · Chạy gần nhất: 14:00 19-09', o.err ? 'Công tắc khẩn của kênh đang bật nên lịch này không chạy.' : ''),
  wj1JobCard('Nhắc kiểm tra kho vật tư', [badge('Nhắn tin', 'neutral', { dot: false }), badge('Do trợ lý AI đặt', 'neutral', { dot: false }), badge('Mỗi 10080 phút', 'neutral', { dot: false }), badge('Lỗi', 'danger')],
    'Zalo lễ tân (cá nhân) · u-demo-022 · Lần kế tiếp: 09:00 23-09 · Chạy gần nhất: 09:00 16-09', 'Tài khoản chưa đăng nhập (cần quét QR lại).')
];
const wj1SchedulesHead = () => pageHead('Lịch hẹn', 'Bot tự nhắn theo lịch: nhắc hẹn hoặc chạy 1 lượt agent - xem, sửa, chạy thử ngay không cần chat', [primary('Thêm lịch hẹn', { icon: 'add' })]);
const wj1SchedulesPage = o => [wj1SchedulesHead(), wj1AccountFilter(), ...wj1Jobs(o)];
const wj1SchForm = (o = {}) => [
  o.add ? select('Account', 'Pema CSKH (Zalo Bot)') : null,
  o.add ? select('Cuộc trò chuyện (đích gửi, không đổi được sau khi tạo)', '-') : null,
  o.add ? notice('Tài khoản này dùng hồ sơ Kênh bệnh nhân: lịch chỉ được gửi tin từ mẫu đã được bác sĩ duyệt (loại Nhắn tin). Job chạy agent chỉ soạn nháp để người duyệt, không tự gửi.', 'info') : null,
  o.add ? select('Loại job', 'Nhắn tin (không tốn lượt LLM)') : null,
  input('Tên', o.name || '', { ph: 'vd: Nhắc họp 15h' }),
  textarea('Nội dung gửi', o.payload || '', { ph: 'vd: Nhớ họp với anh Nam lúc 3h chiều nhé', lines: 3 }),
  select('Kiểu lịch', 'Một lần'),
  grid(2, date('Ngày (giờ Asia/Ho_Chi_Minh)', o.date || ''), time('Giờ (giờ Asia/Ho_Chi_Minh)', o.time || ''))
];

// ---- Trí nhớ ----
const wj1Memory = [
  ['Thích được nhắc lịch trước một ngày bằng tin nhắn ngắn.', 'Zalo lễ tân (cá nhân)', 'u-demo-021', 'Chat riêng', '11/09 09:00'],
  ['Nhóm điều phối họp giao ca lúc 8 giờ sáng thứ hai hằng tuần.', 'Zalo lễ tân (cá nhân)', 'g-demo-001', 'Nhóm', '14/09 08:30']
];
const wj1MemoryHead = () => pageHead('Trí nhớ', 'Điều trợ lý AI ghi nhớ qua công cụ save_memory - điều học ở chat riêng không bao giờ dùng trong nhóm. Với hồ sơ Kênh bệnh nhân, nội dung từ bệnh nhân không được tự ghi nhớ.');

// ---- Kho tri thức ----
const wj1KbHead = () => pageHead('Kho tri thức', 'Tài liệu nạp ở đây được cắt đoạn để agent tra cứu qua công cụ kb_search - nạp xong phải GÁN cho agent thì bot mới đọc được', [secondary('Thử tìm'), secondary('Hướng dẫn'), primary('Thêm nguồn')]);
const wj1KbCols = ['Tên', ['Định dạng', '90px'], ['Trạng thái', '110px'], ['Agent đang dùng', '130px'], ['Bác sĩ duyệt', '170px'], ['Số đoạn', '70px'], ['Dung lượng', '90px'], ['Ngày', '100px'], ['', '1.1fr']];
const wj1KbSrc = [
  ['Hướng dẫn chăm sóc da sau laser', 'docx', 'Sẵn sàng', '2 agent', true, '3', '47,1 KB', '31/08 09:00'],
  ['Dấu hiệu cần liên hệ phòng khám', 'Gõ tay', 'Sẵn sàng', '1 agent', true, '2', '1,2 KB', '02/09 10:00'],
  ['Bảng giá dịch vụ (nháp)', 'xlsx', 'Sẵn sàng', '1 agent', false, '6', '18,4 KB', '05/09 09:30'],
  ['Quy trình nhắc tái khám', 'pdf', 'Sẵn sàng', '1 agent', false, '4', '96,0 KB', '08/09 14:00'],
  ['Phiếu quét (ảnh chụp)', 'pdf', 'Hỏng', 'Chưa gán', false, '0', '312,5 KB', '10/09 15:20'],
  ['Bắt đầu theo vai trò', 'Gõ tay', 'Sẵn sàng', 'Chưa gán', false, '1', '0,8 KB', '12/09 08:00', 'Hướng dẫn · Tất cả'],
  ['CSKH chủ động: xử lý việc hôm nay', 'Gõ tay', 'Sẵn sàng', 'Chưa gán', false, '2', '1,5 KB', '12/09 08:05', 'Hướng dẫn · CSKH'],
  ['Hồ sơ và Patient 360', 'Gõ tay', 'Sẵn sàng', 'Chưa gán', false, '2', '1,9 KB', '12/09 08:10', 'Hướng dẫn · Bác sĩ']
];
const wj1KbRow = ([name, fmt, st, ag, ok, n, size, date, guide], o = {}) => {
  const failed = st === 'Hỏng' || o.fail;
  const status = o.fail && st === 'Sẵn sàng' ? 'Hỏng' : st;
  const nameCell = [strong(name), failed ? txt('Không đọc được nội dung file (định dạng không hỗ trợ).', { size: 'l', tone: 'danger' }) : null, failed ? sm('Đã thử 1 lần') : null, guide ? badge(guide, 'info', { dot: false }) : null].filter(Boolean);
  const approve = o.doctor ? [txt(ok ? 'Đã duyệt' : 'Chưa duyệt', { size: 'l' })]
    : [btn('', 'quiet', { ico: true, icon: ok ? 'toggle_on' : 'toggle_off', aria: ok ? 'Bỏ chữ ký duyệt của bác sĩ' : 'Bác sĩ xác nhận nguồn này đúng để trợ lý trả lời bệnh nhân' }), txt(ok ? 'Đã duyệt' : 'Chưa duyệt', { size: 'l' })];
  const acts = [failed || o.retry ? quiet('Xử lý lại', { icon: 'refresh', sm: true }) : null, o.doctor ? null : quiet('Nhãn hướng dẫn', { sm: true, aria: 'Nhãn hướng dẫn' }), quiet('Xem đoạn', { icon: 'visibility', sm: true }), danger('Xóa', { sm: true })].filter(Boolean);
  return [nameCell, fmt, [badge(status, status === 'Hỏng' ? 'danger' : status === 'Sẵn sàng' ? 'success' : 'warning')],
    [quiet(o.doctor ? '-' : ag === 'Chưa gán' ? 'Chưa gán' : ag, { icon: ag === 'Chưa gán' && !o.doctor ? 'warning' : 'group', sm: true, aria: 'Đổi agent đọc được nguồn này' })],
    cell(approve, { row: true }), n, size, date, cell(acts, { row: true })];
};
const wj1KbTable = (o = {}) => table(wj1KbCols, wj1KbSrc.map((s, i) => wj1KbRow(o.mixed && i === 1 ? [...s.slice(0, 2), 'Đang xử lý', ...s.slice(3)] : o.mixed && i === 2 ? [...s.slice(0, 2), 'Chờ xử lý', ...s.slice(3)] : s, i === 0 ? { doctor: o.doctor, ...(o.first || {}) } : { doctor: o.doctor })));
const wj1KbFilter = q => row({ g: 12, jc: 'space-between' }, search('Tìm theo tên nguồn...', { w: 288, val: q }), wj1Pager());
const wj1KbPage = (o = {}) => [wj1KbHead(), wj1KbFilter(''), wj1KbTable(o)];
const wj1KbSheetHead = (title, sub) => row({ g: 12, jc: 'space-between' }, stack({ g: 2 }, strong(title), sub ? sm(sub) : null), secondary('Đóng'));
const wj1KbAddTabs = on => tabs(['Tải file lên', 'Gõ nội dung'], on);

const wj1MemoryCols = ['Fact', 'Account', 'Về', 'Học từ', 'Lúc', ['', '90px']];
const wj1MemoryRows = () => wj1Memory.map(([f, a, w, k, t]) => [f, [badge(a, 'neutral', { dot: false })], w, [badge(k, k === 'Nhóm' ? 'warning' : 'info', { dot: false })], t, [danger('Xóa', { sm: true })]]);
const wj1Chunk = (path, text) => card({ comp: 'KbChunkCard', v: 'soft', g: 6 }, strong(path), txt(text, { size: 's' }));
const wj1Step = (n, title, ...paras) => stack({ g: 6 }, h4(n + '. ' + title), ...paras);
const wj1Guide = () => [
  wj1Step(1, 'Nạp tài liệu',
    txt(['Bấm ', ['Thêm nguồn', 'b'], ' để tải file lên hoặc gõ tay nội dung. Kéo thả file thẳng vào bảng cũng được.']),
    txt([['Nhận file', 'b'], ' ', ['.docx, .xlsx, .pdf, .txt, .md', 'b'], '. Bot đọc CHỮ trong file - PDF chụp ảnh hoặc scan không có lớp chữ thì đọc ra rỗng.']),
    txt(['Chất lượng tốt nhất là ', ['.docx', 'b'], ': bot giữ được cấu trúc tiêu đề nên mỗi đoạn trích ra mang theo đường dẫn kiểu "Chính sách > Đổi trả > Điều kiện", trả lời sát ngữ cảnh hơn. PDF không có cấu trúc đó.'])),
  wj1Step(2, 'Gán nguồn cho agent - BƯỚC BẮT BUỘC',
    txt([['Nạp xong', 'b'], ' ', ['chưa đủ', 'b'], '. Trạng thái "Sẵn sàng" chỉ có nghĩa là đã cắt đoạn xong, không có nghĩa là bot đọc được.']),
    txt([['Mặc định', 'b'], ' ', ['không agent nào', 'b'], ' đọc được nguồn mới - đây là chủ đích, để agent này không vô tình đọc tài liệu nạp cho agent khác.']),
    txt(['Bấm ', ['Gán', 'b'], ' ở cột "Agent đang dùng" và chọn agent. Nguồn chưa gán ai sẽ hiện cảnh báo ở cột đó. Gán được cả ở trang Agents khi sửa từng agent.'])),
  wj1Step(3, 'Khi nào bot tra kho',
    txt(['Bot tự quyết định, không cần ai ra lệnh. Nó tra khi câu hỏi thuộc về tài liệu nội bộ: ', ['chính sách, bảng giá, quy trình, hướng dẫn, thông tin công ty', 'b'], '. Câu trả lời có dẫn tên nguồn để đối chiếu.']),
    txt('Ví dụ tra kho: "Bảng giá gói doanh nghiệp bao nhiêu?", "Chính sách đổi trả thế nào?", "Công ty có những dịch vụ gì?", "Địa chỉ và hotline?".'),
    txt('Ví dụ KHÔNG tra kho: hỏi tin tức, tỷ giá, thời tiết (đi tra web), tán gẫu, nhờ soạn văn bản hay vẽ ảnh.'),
    txt(['Nếu bot trả lời chung chung thay vì lấy từ tài liệu, kiểm hai chỗ trước: nguồn đã gán cho ĐÚNG agent đang chat chưa, và bấm ', ['Xem đoạn', 'b'], ' để soi bot thật sự đọc ra gì từ file đó.'])),
  wj1Step(4, 'Bác sĩ duyệt nguồn (Pema)',
    txt(['Tài liệu y khoa chỉ nên được dùng để trả lời bệnh nhân sau khi bác sĩ xác nhận đúng. Cột ', ['Bác sĩ duyệt', 'b'], ' ghi chữ ký đó.']),
    txt(['Agent dùng hồ sơ ', ['Kênh bệnh nhân', 'b'], ' chỉ trả lời từ nguồn đã được duyệt - máy chủ kiểm tra điều này, màn hình chỉ báo đúng tình trạng. Nguồn chưa duyệt vẫn dùng được cho trợ lý nội bộ.'])),
  wj1Step(5, 'Kiểm tra khi kết quả không như ý',
    txt([['Xem đoạn', 'b'], ' hiện đúng nội dung bot đọc được. Bảng Excel lộn cột, PDF ra chữ rác, file thiếu phần cuối - nhìn ở đây là thấy ngay.']),
    txt('Sửa tài liệu rồi thì xóa nguồn cũ và nạp lại. Lưu ý xóa nguồn sẽ gỡ nó khỏi mọi agent đang dùng, gán lại sau khi nạp bản mới.'))
];
// ---- Tài khoản Zalo (/admin/accounts) ----
const wj1PanicText = 'Công tắc khẩn DỪNG MỌI tin nhắn chủ động của kênh này (nhắc lịch, chăm sóc, tin theo lịch) cho tới khi tắt. Tin trả lời khách vừa nhắn tới không bị công tắc này chặn.';
const wj1Channel = (c, o = {}) => card({ comp: 'ChannelSettingsCard', title: c.title, aside: [...(c.badges || []).map(b => badge(b[0], b[1], { dot: b[2] !== false })), wj1Toggle('Bật kênh ' + c.title, !c.off)], g: 10 },
  o.panic ? notice('CÔNG TẮC KHẨN ĐANG BẬT lúc 20/09 08:40 - mọi tin chủ động của kênh này đang bị chặn. Lý do: Tạm dừng tin chủ động để kiểm tra nội dung.', 'danger') : null,
  prog(c.pct, { label: 'Đã gửi chủ động hôm nay ' + c.sent }),
  input('Trần tin chủ động mỗi ngày (0-1000)', c.cap, { ph: 'Không giới hạn', dis: c.off }),
  grid(2, input('Cách nhau tối thiểu (giây, 0-3600)', c.min, { dis: c.off }), input('Cách nhau tối đa (giây, 0-3600)', c.max, { dis: c.off }), time('Khung giờ gửi: từ', c.from, { dis: c.off }), time('Khung giờ gửi: đến', c.to, { dis: c.off })),
  c.warn ? notice('Kênh zalo_personal dùng nick Zalo thật qua giao thức không chính thức: gửi chủ động nhiều hoặc dồn dập CÓ THỂ khiến Zalo KHÓA tài khoản. Giữ trần mỗi ngày thấp, khoảng cách giữa các tin dài và khung giờ gửi hẹp.', 'warning') : null,
  primary('Lưu cấu hình', { dis: !(o.stale && c.title === 'Tài khoản bot chính thức') }),
  hr(), strong('Công tắc khẩn'), sm(wj1PanicText),
  o.panic ? secondary('Tắt công tắc khẩn') : danger('Bật công tắc khẩn'));
const wj1Accounts = [
  ['P', 'Pema CSKH (Zalo Bot)', [['Bot chính thức', 'neutral', false], ['Kênh bệnh nhân', 'info', false], ['Đang chạy', 'success']], 'pema-bot · não: 🩺 CSKH Da liễu', []],
  ['Z', 'Zalo lễ tân (cá nhân)', [['Nick cá nhân', 'neutral', false], ['Trợ lý nhân viên', 'info', false], ['Đang chạy', 'success']], 'le-tan-ca-nhan · não: 🗂️ Trợ lý nội bộ', [secondary('Login QR', { sm: true })]]
];
const wj1AccountCard = ([ini, name, bs, sub, extra]) => card({ comp: 'AccountCard', title: name, g: 6,
  aside: [...bs.map(b => badge(b[0], b[1], { dot: b[2] !== false })), wj1Toggle('Bật account ' + name), ...extra, secondary('Sửa', { sm: true }), danger('Xóa', { sm: true })] }, sm(sub));
const wj1AccountsPage = (o = {}) => [
  pageHead('Tài khoản Zalo', 'Tài khoản Zalo của bot - mỗi account gắn một agent (não) và có policies riêng', [primary('Thêm account', { icon: 'add' })]),
  card({ title: 'Kênh gửi tin', sub: 'Cấu hình chung của từng kênh Zalo: bật/tắt, trần tin chủ động, khung giờ và công tắc khẩn' },
    o.stale ? notice('Cấu hình kênh vừa được người khác thay đổi nên đã tải lại bản mới nhất. Kiểm tra rồi lưu lại.', 'info') : null,
    grid(2,
      wj1Channel({ title: 'Tài khoản bot chính thức', pct: 30, sent: '3/10', cap: o.stale ? '15' : '10', min: '20', max: '90', from: '08:00', to: '20:00' }, o),
      wj1Channel({ title: 'Tài khoản cá nhân', badges: [['Bridge chờ quét QR', 'warning'], ['Chỉ gửi cho bạn bè', 'info']], pct: 0, sent: '0/5', cap: '5', min: '60', max: '240', from: '09:00', to: '18:00', warn: true }, {}),
      wj1Channel({ title: 'Zalo OA', badges: [['Bridge chưa cấu hình', 'neutral'], ['Chưa hỗ trợ', 'neutral']], off: true, pct: 0, sent: '0/không giới hạn', cap: '', min: '0', max: '0', from: '', to: '' }, {}))),
  o.none ? empty('Chưa có account nào - bấm "Thêm account", chọn tài khoản cá nhân (quét QR) hoặc tài khoản bot (nhập token)') : wj1Accounts.map(wj1AccountCard)
];

const WJ = [
  npage('WJ1', 'Nhân viên', wj1NXW + '/admin/users · danh sách tài khoản đăng nhập, bộ lọc vai trò và trạng thái, thao tác của chủ phòng khám', '/admin/users', wj1UsersPage(), { nx: 'owner' }),
  npage('WJ2', 'Nhân viên · chỉ xem (quản lý)', wj1NXW + '/admin/users · quản lý chỉ xem: có ghi chú quyền, không có nút Thêm nhân viên và cột Thao tác', '/admin/users', [
    wj1UsersHead(false), notice('Bạn chỉ xem được danh sách. Thêm, sửa, khóa tài khoản và đặt lại mật khẩu là quyền của chủ phòng khám.', 'info'), ...wj1UsersFilters(''), wj1UsersTable(false)], { nx: 'manager', state: true }),
  npage('WJ3', 'Nhân viên · không có kết quả lọc', wj1NXW + '/admin/users · tìm "zzz": bảng được thay bằng trạng thái trống', '/admin/users', [
    wj1UsersHead(true), ...wj1UsersFilters('zzz'), empty('Không có nhân viên phù hợp', 'Đổi từ khóa hoặc bỏ bớt bộ lọc.')], { nx: 'owner', state: true }),
  ndlg('WJ4', 'Thêm nhân viên', wj1NXW + '/admin/users · hộp thoại thêm nhân viên, chưa nhập gì: nút Thêm nhân viên tắt', [
    input('Họ tên', '', { req: true }),
    input('Email đăng nhập', '', { hint: 'Dùng để đăng nhập, không trùng với nhân viên khác.' }),
    select('Vai trò', 'CSKH', { hint: 'Chăm sóc khách hàng: việc hôm nay, Inbox, duyệt tin thường.' }),
    wj1Pw('Mật khẩu ban đầu', { hint: 'Ít nhất 8 ký tự. Hãy báo mật khẩu cho nhân viên qua kênh riêng.' }),
    wj1Pw('Nhập lại mật khẩu')
  ], { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 520, sub: 'Tạo tài khoản và mật khẩu ban đầu; nhân viên đổi lại ở Tài khoản của tôi.', footer: [secondary('Hủy'), primary('Thêm nhân viên', { dis: true })] }),
  ndlg('WJ5', 'Thêm nhân viên', wj1NXW + '/admin/users · hộp thoại thêm nhân viên khi email đã có người dùng: báo lỗi ở cuối biểu mẫu', [
    input('Họ tên', 'Trần Thị Mẫu', { req: true }),
    input('Email đăng nhập', 'owner@pema.test', { hint: 'Dùng để đăng nhập, không trùng với nhân viên khác.' }),
    select('Vai trò', 'CSKH', { hint: 'Chăm sóc khách hàng: việc hôm nay, Inbox, duyệt tin thường.' }),
    wj1Pw('Mật khẩu ban đầu', { val: '••••••••••••', hint: 'Ít nhất 8 ký tự. Hãy báo mật khẩu cho nhân viên qua kênh riêng.' }),
    wj1Pw('Nhập lại mật khẩu', { val: '••••••••••••' }),
    notice('Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác.', 'info')
  ], { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 520, sub: 'Tạo tài khoản và mật khẩu ban đầu; nhân viên đổi lại ở Tài khoản của tôi.', footer: [secondary('Hủy'), primary('Thêm nhân viên')] }),
  ndlg('WJ6', 'Sửa nhân viên', wj1NXW + '/admin/users · hộp thoại sửa họ tên và vai trò; email không đổi được, nút Lưu tắt khi chưa thay đổi', [
    input('Họ tên', 'BS. Lê Minh Tâm', { req: true }),
    input('Email đăng nhập', 'doctor@pema.test', { dis: true }),
    select('Vai trò', 'Bác sĩ', { hint: 'Hồ sơ bệnh nhân mình phụ trách, duyệt nội dung lâm sàng.' })
  ], { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 520, sub: 'Đổi họ tên hoặc vai trò. Email đăng nhập không đổi được.', footer: [secondary('Hủy'), primary('Lưu thay đổi', { dis: true })] }),
  ndlg('WJ7', 'Sửa nhân viên', wj1NXW + '/admin/users · sửa tài khoản của chính mình: vai trò bị khóa, có câu giải thích', [
    input('Họ tên', 'Nguyễn Thanh Hà', { req: true }),
    input('Email đăng nhập', 'owner@pema.test', { dis: true }),
    select('Vai trò', 'Chủ phòng khám', { dis: true, hint: 'Bạn không thể tự đổi vai trò của chính mình.' })
  ], { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 520, sub: 'Đổi họ tên hoặc vai trò. Email đăng nhập không đổi được.', footer: [secondary('Hủy'), primary('Lưu thay đổi', { dis: true })] }),
  ndlg('WJ8', 'Đặt lại mật khẩu', wj1NXW + '/admin/users · hộp thoại đặt lại mật khẩu của một nhân viên, nút tắt khi chưa nhập đủ', [
    notice('BS. Lê Minh Tâm sẽ bị đăng xuất khỏi mọi thiết bị ngay và phải đăng nhập bằng mật khẩu mới. Hãy báo mật khẩu cho họ qua kênh riêng.', 'info'),
    wj1Pw('Mật khẩu mới', { hint: 'Ít nhất 8 ký tự.' }),
    wj1Pw('Nhập lại mật khẩu mới')
  ], { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 520, sub: 'BS. Lê Minh Tâm · doctor@pema.test', footer: [secondary('Hủy'), primary('Đặt lại mật khẩu', { dis: true })] }),
  ndlg('WJ9', 'Khóa tài khoản của BS. Lê Minh Tâm?', wj1NXW + '/admin/users · hộp xác nhận khóa tài khoản', [txt('Người này sẽ bị đăng xuất khỏi mọi thiết bị ngay và không đăng nhập được cho đến khi bạn mở khóa. Dữ liệu và nhật ký của họ được giữ nguyên.')],
    { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 400, footer: [secondary('Hủy'), danger('Khóa tài khoản')] }),
  ndlg('WJ10', 'Mở khóa tài khoản của Bùi Ngọc Lan?', wj1NXW + '/admin/users · hộp xác nhận mở khóa tài khoản', [txt('Người này đăng nhập lại được bằng mật khẩu hiện tại. Mọi phiên cũ đã bị đăng xuất khi khóa, nên họ cần đăng nhập mới.')],
    { nx: 'owner', nav: '/admin/users', behind: wj1UsersPage(), w: 400, footer: [secondary('Hủy'), primary('Mở khóa')] }),
  npage('WJ11', 'Tài khoản của tôi', wj1NXW + '/admin/auth · đổi mật khẩu của chính mình (chức năng đang chờ máy chủ), không có mục menu đang sáng', '/admin/auth', [
    pageHead('Tài khoản của tôi', 'Nguyễn Thanh Hà · Chủ phòng khám · Phòng khám Pema (dữ liệu mẫu)'),
    card({ title: 'Mật khẩu dashboard', sub: 'Đổi mật khẩu đăng nhập trang này. Đổi xong, mọi thiết bị khác đang đăng nhập sẽ bị đăng xuất.' },
      notice('Chức năng đổi mật khẩu đang chờ máy chủ cung cấp. Trong lúc này, nhờ chủ phòng khám đặt lại mật khẩu.', 'warning'),
      wj1Pw('Mật khẩu hiện tại', { ph: 'Nhập mật khẩu hiện tại' }),
      grid(2, wj1Pw('Mật khẩu mới', { ph: 'Nhập mật khẩu mới', desc: 'Tối thiểu 8 ký tự.' }), wj1Pw('Nhập lại mật khẩu mới', { ph: 'Nhập lại mật khẩu mới' })),
      primary('Đổi mật khẩu', { icon: 'lock', dis: true }))
  ], { nx: 'owner' }),
  npage('WJ12', 'Tổng quan AI', wj1NXW + '/admin/overview · tình trạng bot, mức dùng LLM trong ngày, tình trạng hệ thống và biểu đồ 7 ngày', '/admin/overview', wj1OverviewBody(), { nx: 'owner' }),
  npage('WJ13', 'Tổng quan AI · chưa cấu hình LLM', wj1NXW + '/admin/overview · thiếu API key, model hoặc base URL: thông báo cảnh báo trên đầu trang', '/admin/overview', wj1OverviewBody({ noLlm: true }), { nx: 'owner', state: true }),
  npage('WJ14', 'Tổng quan AI · chưa có số liệu sử dụng', wj1NXW + '/admin/overview · chưa có lượt agent hay token nào: bỏ phần Mức sử dụng', '/admin/overview', wj1OverviewBody({ empty: true }), { nx: 'owner', state: true }),
  npage('WJ15', 'Phiên chat AI', wj1NXW + '/admin/threads · danh sách phiên chat, bật tắt bot theo phiên, xem và xóa hẳn', '/admin/threads', wj1SessionsPage(), { nx: 'owner' }),
  ndlg('WJ16', 'Nguyễn Thu Hà', wj1NXW + '/admin/threads · ngăn bên phải "Hội thoại": tin nhắn của phiên, xóa bản tóm tắt hoặc xóa sạch ngữ cảnh (vẽ dạng hộp thoại)', [
    wj1SessionTabs(0), wj1Chat(), sm('Bot quên hẳn cuộc trò chuyện này và bắt đầu lại từ đầu. Lịch hẹn đang chờ vẫn giữ.')
  ], { nx: 'owner', nav: '/admin/threads', behind: wj1SessionsPage(), w: 560, sub: '18 tin', footer: wj1ConfirmSession }),
  npage('WJ17', 'Phiên chat AI · Session detail · Trace agent', wj1NXW + '/admin/threads · ngăn chi tiết, thẻ "Trace agent": mỗi lượt agent là một nút, bấm Xem để mở các bước', '/admin/threads', [
    ...wj1SessionsPage(),
    card({ title: 'Nguyễn Thu Hà', sub: '18 tin', aside: [secondary('Đóng')] }, wj1SessionTabs(1), ...wj1RunButtons())
  ], { nx: 'owner' }),
  ndlg('WJ18', 'Nguyễn Thu Hà', wj1NXW + '/admin/threads · ngăn chi tiết, thẻ "Trace agent" khi chưa có trace nào', [
    wj1SessionTabs(1), sm('Chưa có trace nào. Trace chỉ ghi từ lúc bật AGENT_TRACE_ENABLED, và tự dọn sau AGENT_TRACE_RETENTION_DAYS ngày.')
  ], { nx: 'owner', nav: '/admin/threads', behind: wj1SessionsPage(), w: 560, sub: '18 tin' }),
  ndlg('WJ19', 'Xóa cuộc trò chuyện "Nguyễn Thu Hà"?', wj1NXW + '/admin/threads · hộp xác nhận xóa hẳn một phiên', [txt('Xóa hẳn session này và toàn bộ 18 tin nhắn. Danh bạ vẫn được giữ. Không hoàn tác được.')],
    { nx: 'owner', nav: '/admin/threads', behind: wj1SessionsPage(), w: 400, footer: [secondary('Hủy'), danger('Xóa session')] }),
  ndlg('WJ20', 'Xóa bản tóm tắt này?', wj1NXW + '/admin/threads · hộp xác nhận xóa bản tóm tắt của phiên', [txt('Tin nhắn KHÔNG bị xóa. Bot sẽ tự viết lại bản tóm tắt từ đầu ở lần gộp tiếp theo, nên nó tốn thêm một lượt gọi model.')],
    { nx: 'owner', nav: '/admin/threads', behind: wj1SessionsPage(), w: 400, footer: [secondary('Hủy'), danger('Xóa')] }),
  ndlg('WJ21', 'Xóa sạch ngữ cảnh cuộc trò chuyện này?', wj1NXW + '/admin/threads · hộp xác nhận xóa sạch ngữ cảnh của phiên', [txt('Toàn bộ tin nhắn, bản tóm tắt, trace từng bước và ảnh đã tải của cuộc trò chuyện này sẽ bị xóa. Bot vẫn giữ những điều đã ghi nhớ về người này (xóa riêng ở trang Trí nhớ). Lịch hẹn đang chờ vẫn giữ nguyên. Không hoàn tác được.')],
    { nx: 'owner', nav: '/admin/threads', behind: wj1SessionsPage(), w: 400, footer: [secondary('Hủy'), danger('Xóa')] }),
  npage('WJ22', 'Phiên chat AI · chưa có phiên', wj1NXW + '/admin/threads · chưa có phiên nào: bảng chỉ có dòng trống', '/admin/threads', [wj1SessionsHead(), wj1Toolbar('Tìm theo tên hoặc thread ID...'), table(wj1SessionCols, [], { empty: 'Chưa có session nào' })], { nx: 'owner', state: true }),
  npage('WJ23', 'Danh bạ', wj1NXW + '/admin/contacts · người đã nhắn tới bot, tự thu thập từ mọi tin nhắn đến', '/admin/contacts', wj1ContactsPage(), { nx: 'owner' }),
  ndlg('WJ24', 'Xóa danh bạ "Nguyễn Thu Hà"?', wj1NXW + '/admin/contacts · hộp xác nhận xóa một dòng danh bạ', [txt('Chỉ xóa khỏi danh sách danh bạ, KHÔNG đụng lịch sử chat. Người này nhắn lại thì tự hiện lại.')],
    { nx: 'owner', nav: '/admin/contacts', behind: wj1ContactsPage(), w: 400, footer: [secondary('Hủy'), danger('Xóa danh bạ')] }),
  npage('WJ25', 'Danh bạ · chưa có danh bạ', wj1NXW + '/admin/contacts · chưa có contact nào: bảng chỉ có dòng trống', '/admin/contacts', [wj1ContactsHead(), wj1Toolbar('Tìm theo tên hoặc user ID...'), table(wj1ContactCols, [], { empty: 'Chưa có contact nào' })], { nx: 'owner', state: true }),
  npage('WJ26', 'Bạn bè', wj1NXW + '/admin/friends · duyệt yêu cầu kết bạn và danh sách bạn của nick cá nhân đang chạy', '/admin/friends', wj1FriendsPage(), { nx: 'owner' }),
  ndlg('WJ27', 'Từ chối kết bạn từ "Hải Yến (mẫu)"?', wj1NXW + '/admin/friends · hộp xác nhận từ chối một yêu cầu kết bạn', [txt('Yêu cầu sẽ bị xóa khỏi danh sách chờ.')],
    { nx: 'owner', nav: '/admin/friends', behind: wj1FriendsPage(), w: 400, footer: [secondary('Hủy'), danger('Từ chối')] }),
  npage('WJ28', 'Bạn bè · chưa có tài khoản cá nhân', wj1NXW + '/admin/friends · chưa có tài khoản Zalo cá nhân: cả hai bảng đều trống', '/admin/friends', [
    wj1FriendsHead(), notice('Chưa có tài khoản Zalo cá nhân nào. Tính năng bạn bè không áp dụng cho kênh bot.', 'info'), wj1AccountPicker('-'), wj1FriendNote(),
    h2('Chờ duyệt (0)'), table(['', 'Tên', 'Lời nhắn', 'Nhận lúc', ''], [], { empty: 'Không có yêu cầu nào đang chờ' }),
    row({ g: 12, jc: 'space-between' }, h2('Danh sách bạn (0)'), secondary('Làm mới')), table(['', 'Tên', 'User ID'], [], { empty: 'Chưa có bạn nào' })], { nx: 'owner', state: true }),
  npage('WJ29', 'Bạn bè · không lấy được danh sách bạn', wj1NXW + '/admin/friends · tài khoản chưa chạy hoặc là kênh bot: danh sách bạn trống kèm câu giải thích', '/admin/friends', [
    wj1FriendsHead(), wj1AccountPicker('Zalo lễ tân (cá nhân)'), wj1FriendNote(), h2('Chờ duyệt (2)'), wj1Pending(),
    row({ g: 12, jc: 'space-between' }, h2('Danh sách bạn (0)'), secondary('Làm mới')),
    notice('Tài khoản chưa chạy hoặc là kênh bot - tính năng bạn bè chỉ dùng cho nick cá nhân đang chạy.', 'warning'), table(['', 'Tên', 'User ID'], [])], { nx: 'owner', state: true }),
  npage('WJ30', 'Lịch hẹn của bot', wj1NXW + '/admin/schedules · các lịch tự động của bot: nhắn tin hoặc chạy một lượt agent; bật tắt, chạy thử, lịch sử, sửa, xóa', '/admin/schedules', wj1SchedulesPage(), { nx: 'owner' }),
  npage('WJ31', 'Lịch hẹn của bot · chưa có lịch', wj1NXW + '/admin/schedules · chưa có lịch hẹn nào', '/admin/schedules', [wj1SchedulesHead(), wj1AccountFilter(), empty('Chưa có lịch hẹn nào - bấm "Thêm lịch hẹn" hoặc nhờ bot đặt lịch qua chat')], { nx: 'owner', state: true }),
  npage('WJ32', 'Lịch hẹn của bot · job lỗi hoặc bị chặn', wj1NXW + '/admin/schedules · job báo lỗi gửi, bị chặn bởi công tắc khẩn hoặc tài khoản chưa đăng nhập', '/admin/schedules', wj1SchedulesPage({ err: true }), { nx: 'owner', state: true }),
  ndlg('WJ33', 'Thêm lịch hẹn', wj1NXW + '/admin/schedules · ngăn bên phải "Thêm lịch hẹn" (vẽ dạng hộp thoại): account, đích gửi, loại job, tên, nội dung, kiểu lịch, ngày giờ', wj1SchForm({ add: true }),
    { nx: 'owner', nav: '/admin/schedules', behind: wj1SchedulesPage(), w: 560, footer: [primary('Tạo lịch hẹn', { dis: true })] }),
  ndlg('WJ34', 'Thêm lịch hẹn', wj1NXW + '/admin/schedules · "Thêm lịch hẹn" với tài khoản dùng hồ sơ Kênh bệnh nhân: chỉ gửi tin từ mẫu đã duyệt', wj1SchForm({ add: true }),
    { nx: 'owner', nav: '/admin/schedules', behind: wj1SchedulesPage(), w: 560, footer: [primary('Tạo lịch hẹn', { dis: true })] }),
  ndlg('WJ35', 'Sửa: Nhắc tái khám tuần sau', wj1NXW + '/admin/schedules · ngăn bên phải "Sửa": đổi tên, nội dung, kiểu lịch, ngày giờ', wj1SchForm({ name: 'Nhắc tái khám tuần sau', payload: 'nhac-tai-kham', date: '2026-09-22', time: '09:00' }),
    { nx: 'owner', nav: '/admin/schedules', behind: wj1SchedulesPage(), w: 560, footer: [primary('Lưu thay đổi')] }),
  ndlg('WJ36', 'Lịch sử chạy - Nhắc tái khám tuần sau', wj1NXW + '/admin/schedules · ngăn bên phải "Lịch sử chạy" khi lịch chưa chạy lần nào', [sm('Chưa có lần chạy nào')],
    { nx: 'owner', nav: '/admin/schedules', behind: wj1SchedulesPage(), w: 560, sub: '0 lần gần nhất' }),
  ndlg('WJ37', 'Xóa lịch hẹn "Nhắc tái khám tuần sau"?', wj1NXW + '/admin/schedules · hộp xác nhận xóa lịch hẹn', [txt('Lịch sử chạy của lịch hẹn này cũng sẽ bị xóa theo, không khôi phục được.')],
    { nx: 'owner', nav: '/admin/schedules', behind: wj1SchedulesPage(), w: 400, footer: [secondary('Hủy'), danger('Xóa')] }),
  npage('WJ38', 'Trí nhớ', wj1NXW + '/admin/memory · những điều trợ lý AI đã ghi nhớ, tìm và xóa từng dòng', '/admin/memory', [wj1MemoryHead(), wj1Toolbar('Tìm trong nội dung hoặc subject ID...'), table(wj1MemoryCols, wj1MemoryRows())], { nx: 'owner' }),
  npage('WJ39', 'Trí nhớ · chưa ghi nhớ gì', wj1NXW + '/admin/memory · bot chưa ghi nhớ gì: bảng chỉ có dòng trống', '/admin/memory', [wj1MemoryHead(), wj1Toolbar('Tìm trong nội dung hoặc subject ID...'), table(wj1MemoryCols, [], { empty: 'Bot chưa ghi nhớ gì' })], { nx: 'owner', state: true }),
  npage('WJ40', 'Kho tri thức', wj1NXW + '/admin/kb · nguồn tri thức đã cắt đoạn: định dạng, trạng thái, agent đang dùng, chữ ký duyệt của bác sĩ', '/admin/kb', wj1KbPage(), { nx: 'owner' }),
  npage('WJ41', 'Kho tri thức · chưa có nguồn', wj1NXW + '/admin/kb · chưa có nguồn nào: bảng chỉ có dòng trống', '/admin/kb', [wj1KbHead(), table(wj1KbCols, [], { empty: 'Chưa có nguồn nào - bấm "Thêm nguồn" hoặc kéo thả file vào đây' })], { nx: 'owner', state: true }),
  npage('WJ42', 'Kho tri thức · không có kết quả tìm', wj1NXW + '/admin/kb · tìm "zzz" không khớp nguồn nào', '/admin/kb', [wj1KbHead(), wj1KbFilter('zzz'), table(wj1KbCols, [], { empty: 'Không có nguồn nào khớp "zzz"' })], { nx: 'owner', state: true }),
  npage('WJ43', 'Kho tri thức · kéo file vào bảng', wj1NXW + '/admin/kb · đang kéo file qua bảng: hiện vùng thả "Thả file để thêm nguồn"', '/admin/kb', [...wj1KbPage(), empty('Thả file để thêm nguồn', '', { icon: 'upload_file' })], { nx: 'owner', state: true }),
  npage('WJ44', 'Kho tri thức · nguồn hỏng và đang xử lý', wj1NXW + '/admin/kb · nguồn bị hỏng kèm lỗi và số lần thử, nút Xử lý lại; nguồn đang xử lý và chờ xử lý', '/admin/kb', [wj1KbHead(), wj1KbFilter(''), wj1KbTable({ first: { fail: true }, mixed: true })], { nx: 'owner', state: true }),
  npage('WJ45', 'Kho tri thức · vai trò không có quyền quản lý', wj1NXW + '/admin/kb · bác sĩ chỉ xem đoạn và xóa: không có nút gán agent hay chữ ký duyệt', '/admin/kb', wj1KbPage({ doctor: true }), { nx: 'doctor', state: true }),
  ndlg('WJ46', 'Thêm nguồn', wj1NXW + '/admin/kb · hộp thoại "Thêm nguồn", thẻ "Tải file lên": tên nguồn và vùng kéo thả file', [
    wj1KbAddTabs(0), input('Tên nguồn', '', { ph: 'vd: Chính sách đổi trả' }),
    file('File', 'Kéo thả file vào đây hoặc bấm để chọn file txt, md, docx, xlsx, pdf', { hint: 'Tối đa 7 MB mỗi file' })
  ], { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 560, footer: [primary('Thêm nguồn', { dis: true })] }),
  npage('WJ47', 'Kho tri thức · Thêm nguồn · gõ nội dung', wj1NXW + '/admin/kb · "Thêm nguồn", thẻ "Gõ nội dung": dán hoặc gõ nội dung cần bot tra cứu', '/admin/kb', [
    ...wj1KbPage(),
    card({ title: 'Thêm nguồn', aside: [secondary('Đóng')] }, wj1KbAddTabs(1), input('Tên nguồn', '', { ph: 'vd: Chính sách đổi trả' }), textarea('Nội dung', '', { ph: 'Dán hoặc gõ nội dung cần bot tra cứu...', lines: 4 }), primary('Thêm nguồn', { dis: true }))
  ], { nx: 'owner' }),
  ndlg('WJ48', 'Agent nào đọc được nguồn này', wj1NXW + '/admin/kb · gán nguồn cho agent: một công tắc cho mỗi agent, Lưu', [
    list([
      { avatar: '🩺', t: 'CSKH Da liễu', actions: [wj1Toggle('Bật tắt agent CSKH Da liễu', false)] },
      { avatar: '🗂️', t: 'Trợ lý nội bộ', actions: [wj1Toggle('Bật tắt agent Trợ lý nội bộ', false)] },
      { avatar: '📊', t: 'Báo cáo tuần', actions: [wj1Toggle('Bật tắt agent Báo cáo tuần', false)] }])
  ], { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 520, sub: 'Phiếu quét (ảnh chụp)', footer: [sm('Không agent nào đọc được nguồn này'), primary('Lưu')] }),
  ndlg('WJ49', 'Đoạn đã cắt - Hướng dẫn chăm sóc da sau laser', wj1NXW + '/admin/kb · các đoạn bot đọc ra từ file, mỗi đoạn kèm đường dẫn tiêu đề', [
    wj1Chunk('Chăm sóc da sau laser > Ngày đầu', 'Da có thể đỏ nhẹ, hơi rát trong 2 đến 3 ngày đầu. Dùng kem dưỡng ẩm dịu nhẹ theo hướng dẫn, không tự bóc vảy.'),
    wj1Chunk('Chăm sóc da sau laser > Chống nắng', 'Tránh nắng trực tiếp, dùng kem chống nắng phổ rộng mỗi ngày và che chắn khi ra ngoài.'),
    wj1Chunk('Chăm sóc da sau laser > Khi nào cần liên hệ', 'Liên hệ phòng khám ngay khi đỏ rát tăng dần, chảy dịch, chảy máu, sốt hoặc sưng nhiều.')
  ], { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 640, sub: '3 đoạn' }),
  ndlg('WJ50', 'Dùng Kho tri thức thế nào', wj1NXW + '/admin/kb · hướng dẫn 5 bước: nạp, gán nguồn cho agent, khi nào bot tra kho, bác sĩ duyệt, kiểm tra', wj1Guide(),
    { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 760 }),
  ndlg('WJ51', 'Hiện trong Hướng dẫn', wj1NXW + '/admin/kb · hộp thoại "Nhãn hướng dẫn": cho nhân viên đọc nguồn này ở mục Hướng dẫn', [
    check('Nhân viên đọc nguồn này ở mục Hướng dẫn', false, { desc: 'Nội dung viết bằng Markdown: tiêu đề `##`, danh sách, **đậm**. Bài chỉ để đọc; sửa nội dung bằng cách thêm nguồn mới.' }),
    input('Chủ đề hoặc vai trò', '', { dis: true, hint: 'Ví dụ: CSKH, Bác sĩ, Lễ tân. Dùng để nhóm và lọc bài.' })
  ], { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 520, sub: 'Hướng dẫn chăm sóc da sau laser', footer: [secondary('Hủy'), primary('Lưu')] }),
  ndlg('WJ52', 'Thử tìm trong kho', wj1NXW + '/admin/kb · xem agent sẽ trích đoạn nào cho một câu hỏi', [
    select('Agent', 'CSKH Da liễu'), input('Câu hỏi', '', { ph: 'Ví dụ: chăm sóc da sau laser cần lưu ý gì' })
  ], { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 560, sub: 'Xem agent sẽ trích đoạn nào cho một câu hỏi. Chỉ nguồn đã gán cho agent mới hiện.', footer: [primary('Tìm', { dis: true })] }),
  ndlg('WJ53', 'Xóa nguồn "Hướng dẫn chăm sóc da sau laser"?', wj1NXW + '/admin/kb · hộp xác nhận xóa nguồn', [txt('2 agent đang dùng nguồn này sẽ mất quyền tra cứu nội dung này ngay khi xóa. Toàn bộ đoạn đã cắt của nguồn này cũng bị xóa, không khôi phục được.')],
    { nx: 'owner', nav: '/admin/kb', behind: wj1KbPage(), w: 440, footer: [secondary('Hủy'), danger('Xóa')] }),
  npage('WJ54', 'Tài khoản Zalo', wj1NXW + '/admin/accounts · cấu hình từng kênh gửi tin (trần, khung giờ, công tắc khẩn) và danh sách account gắn agent', '/admin/accounts', wj1AccountsPage(), { nx: 'owner' }),
  npage('WJ55', 'Tài khoản Zalo · chưa có account', wj1NXW + '/admin/accounts · chưa có account nào: danh sách thay bằng câu hướng dẫn', '/admin/accounts', wj1AccountsPage({ none: true }), { nx: 'owner', state: true }),
  npage('WJ56', 'Tài khoản Zalo · công tắc khẩn đang bật', wj1NXW + '/admin/accounts · công tắc khẩn của kênh bot đang bật: thông báo đỏ và nút Tắt công tắc khẩn', '/admin/accounts', wj1AccountsPage({ panic: true }), { nx: 'owner', state: true }),
  npage('WJ57', 'Tài khoản Zalo · cấu hình kênh bị thay đổi', wj1NXW + '/admin/accounts · cấu hình kênh vừa được người khác đổi nên đã tải lại bản mới nhất', '/admin/accounts', wj1AccountsPage({ stale: true }), { nx: 'owner', state: true })
];
