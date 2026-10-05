// WL · Đăng nhập, khung ứng dụng Next.js và Tin nhắn mẫu đã duyệt (Next.js only, W2 step W10). Owner: W10 director.
// Compositions kept local to this part (names start with wl): wlLogin (sign-in card), wlTemplate (TemplateCard: one approved message template), wlTemplatesPage, wlDashboardHead.
const wlNXW = 'Next.js › ';

// ---- sign-in (WL1-WL3): no shell, the card is centred ----
const wlLogin = (o = {}) => card({},
  img('Pema clinic & spa', { icon: 'spa', h: 72 }),
  h2('Đăng nhập CSKH', 'Chăm sóc khách hàng và trợ lý AI'),
  input('Email', o.email || ''),
  input('Mật khẩu', o.password || '', { suf: 'visibility', sufAria: 'Hiện nội dung' }),
  o.error ? errLine(o.error) : null,
  primary(o.busy ? 'Đang đăng nhập...' : 'Đăng nhập', { dis: !o.error, full: true }));

// ---- approved message templates (WL4-WL9) ----
const WL_TPL = [
  { key: 'nhac-tai-kham', title: 'Nhắc lịch tái khám', body: 'Chào {ten_khach}, phòng khám Pema nhắc chị đã đến hạn tái khám. Chị rảnh khung giờ nào trong tuần này để em sắp xếp lịch với bác sĩ ạ?', ok: '21/08/2026' },
  { key: 'hoi-tham-sau-thu-thuat', title: 'Hỏi thăm sau thủ thuật (D+1)', body: 'Chào {ten_khach}, hôm qua chị vừa làm thủ thuật tại Pema. Hôm nay da chị thế nào ạ? Nếu thấy đỏ rát tăng hoặc có chảy dịch, chị nhắn ngay để bác sĩ xem nhé.', ok: '21/08/2026' },
  { key: 'nhac-gui-anh-tien-trien', title: 'Nhắc gửi ảnh tiến triển (D+3)', body: 'Chào {ten_khach}, đã 3 ngày kể từ buổi làm da. Chị chụp 1 ảnh vùng da nơi đủ sáng và gửi lại để bác sĩ theo dõi nhé ạ.', ok: '08/09/2026' },
  { key: 'uu-dai-thang-10', title: 'Ưu đãi chăm sóc da tháng 10', body: 'Chào {ten_khach}, tháng này Pema có chương trình soi da miễn phí cho khách cũ. Chị muốn em giữ lịch không ạ?', promo: true },
  { key: 'nhac-lich-hen', title: 'Nhắc lịch hẹn ngày mai', body: 'Chào {ten_khach}, phòng khám Pema nhắc chị có lịch hẹn vào {gio_hen} ngày mai. Chị nhắn em nếu cần đổi lịch nhé.' }
];
// TemplateCard: heading, key and status badges, body, approval line and the buttons the role may use
const wlTemplate = (t, o = {}) => card({ comp: 'TemplateCard', g: 8 },
  row({ g: 8, jc: 'space-between' }, h2(t.title), sm(t.key), t.ok ? badge('Bác sĩ đã duyệt', 'success') : row({ g: 6 }, badge('Chờ bác sĩ duyệt', 'warning'), t.promo ? badge('Quảng bá', 'info') : null)),
  txt(t.body),
  row({ g: 8, jc: 'space-between' }, sm(t.ok ? 'Duyệt ' + t.ok + ' · Đang bật' : 'Chưa duyệt · Đang tắt'),
    o.read ? null : row({ g: 8 }, t.ok ? secondary('Tắt mẫu') : primary('Duyệt'), secondary('Sửa'))));
const wlTemplatesHead = (o = {}) => [
  pageHead('Tin nhắn mẫu đã duyệt', 'Văn bản bác sĩ đã duyệt, được dùng cho tin chăm sóc chủ động', o.read ? [] : [primary('Soạn mẫu mới')]),
  notice('Mẫu mới hoặc vừa sửa chưa được dùng cho đến khi bác sĩ duyệt. Tin quảng bá không gửi cho khách đã từ chối quảng bá, và sinh nhật không bao giờ tự động gửi.', 'info')
];
const wlTemplatesPage = (o = {}) => [wlTemplatesHead(o), ...WL_TPL.map(t => wlTemplate(t, o))];
const wlTplForm = (o = {}) => [
  input('Mã mẫu', o.key || '', { hint: o.key ? 'Mã không đổi được sau khi tạo.' : 'Ví dụ: nhac-tai-kham. Chữ thường, số, gạch ngang.', dis: !!o.key }),
  input('Tiêu đề', o.title || ''),
  textarea('Nội dung', o.body || '', { hint: (o.body ? o.body.length : 0) + '/2000 ký tự', lines: 4 }),
  check('Tin quảng bá', false, { desc: 'Hệ thống chặn gửi cho khách đã từ chối tin quảng bá. Không dùng để chăm sóc an toàn sau điều trị.' })
];

// ---- dashboard head (the content behind the shell states WL10, WL11, WL13) ----
const wlDashboardHead = () => [
  pageHead('Tổng quan', 'Hôm nay · 20/09/2026', [secondary('Mở điều phối lịch', { ric: 'arrow_forward' })]),
  h2('Lịch hẹn theo trạng thái', 'Trạng thái hiện tại của các lịch bắt đầu trong kỳ')
];
const wlTodayHead = () => [pageHead('Hôm nay', 'Việc chăm sóc cần xử lý trong ngày')];

const WL = [
  bare('WL1', 'Đăng nhập CSKH', wlNXW + '/login · trang đăng nhập, không có khung ứng dụng · chưa nhập gì: nút "Đăng nhập" tắt', [wlLogin()]),
  bare('WL2', 'Đăng nhập CSKH · đang đăng nhập', wlNXW + '/login · đã nhập email và mật khẩu, nút chuyển thành "Đang đăng nhập..." và tắt', [wlLogin({ email: 'owner@pema.test', password: '••••••••', busy: true })], { state: true }),
  bare('WL3', 'Đăng nhập CSKH · sai mật khẩu', wlNXW + '/login · câu báo lỗi "Sai email hoặc mật khẩu." dưới ô mật khẩu, nút đăng nhập bật lại', [wlLogin({ email: 'owner@pema.test', password: '••••••••••••', error: 'Sai email hoặc mật khẩu.' })], { state: true }),

  npage('WL4', 'Tin nhắn mẫu đã duyệt', wlNXW + '/templates · chủ phòng khám: soạn, sửa, bật/tắt; mẫu mới chờ bác sĩ duyệt', '/templates', wlTemplatesPage(), { nx: 'owner' }),
  npage('WL5', 'Tin nhắn mẫu đã duyệt · chỉ xem', wlNXW + '/templates · vai trò CSKH chỉ đọc: không có nút "Soạn mẫu mới", "Tắt mẫu", "Duyệt", "Sửa"', '/templates', wlTemplatesPage({ read: true }), { nx: 'cs_staff', state: true }),
  npage('WL6', 'Tin nhắn mẫu đã duyệt · chưa có mẫu', wlNXW + '/templates · danh sách trống', '/templates', [
    wlTemplatesHead(), empty('Chưa có mẫu nào', 'Soạn mẫu đầu tiên và nhờ bác sĩ duyệt.', { icon: 'description' })], { nx: 'owner', state: true }),
  ndlg('WL7', 'Soạn mẫu tin nhắn', wlNXW + '/templates · hộp thoại: mẫu mới, nút "Lưu mẫu" tắt cho đến khi đủ mã, tiêu đề và nội dung', wlTplForm(), {
    nx: 'owner', nav: '/templates', behind: wlTemplatesPage(), w: 640, sub: 'Mẫu chỉ được dùng cho tin chủ động sau khi bác sĩ duyệt', footer: [secondary('Hủy'), primary('Lưu mẫu', { dis: true })] }),
  ndlg('WL8', 'Sửa mẫu tin nhắn', wlNXW + '/templates · hộp thoại: sửa mẫu "Nhắc lịch tái khám", mã mẫu bị khóa', wlTplForm({ key: WL_TPL[0].key, title: WL_TPL[0].title, body: WL_TPL[0].body }), {
    nx: 'owner', nav: '/templates', behind: wlTemplatesPage(), w: 640, sub: 'Mẫu chỉ được dùng cho tin chủ động sau khi bác sĩ duyệt', footer: [secondary('Hủy'), primary('Lưu mẫu')] }),
  ndlg('WL9', 'Duyệt mẫu này?', wlNXW + '/templates · hộp xác nhận của bác sĩ trước khi bật mẫu quảng bá', [
    txt('Bạn xác nhận nội dung mẫu "Ưu đãi chăm sóc da tháng 10" đúng và an toàn để gửi cho khách. Mẫu sẽ được bật ngay.')], {
    nx: 'doctor', nav: '/templates', behind: wlTemplatesPage(), w: 480, footer: [secondary('Hủy'), primary('Duyệt mẫu')] }),

  npage('WL10', 'Khung · menu quản trị (chủ phòng khám)', wlNXW + '(app shell) · sidebar theo quyền: chủ phòng khám thấy mọi mục, mục chưa có là chữ xám "(sắp có)"', '/dashboard', wlDashboardHead(), { nx: 'owner', state: true }),
  npage('WL11', 'Khung · menu bác sĩ', wlNXW + '(app shell) · bác sĩ: chỉ có "Ma trận ngưỡng" trong nhóm Care agent, không có Tài chính', '/dashboard', wlDashboardHead(), { nx: 'doctor', state: true }),
  npage('WL12', 'Khung · menu CSKH', wlNXW + '(app shell) · CSKH: có "Yêu cầu chuyển giao" và "Hàng đợi duyệt", không có mục quản trị care', '/today', wlTodayHead(), { nx: 'cs_staff', state: true }),
  npage('WL13', 'Khung · menu lễ tân', wlNXW + '(app shell) · lễ tân: không có Hàng đợi duyệt và Care agent', '/dashboard', wlDashboardHead(), { nx: 'reception', state: true }),
  npage('WL14', 'Khung · menu trống (bệnh nhân)', wlNXW + '(app shell) · tài khoản bệnh nhân không có menu nhân viên, không có ô tìm và chuông', '/today', [], { nx: 'patient', state: true, crumb: 'Hôm nay' }),
  bare('WL15', 'Khung · đang tải phiên', wlNXW + '(app shell) · chưa biết phiên: chỉ có thanh tiến trình "Đang tải"', [prog(45, { label: 'Đang tải' })], { state: true }),
  bare('WL16', 'Khung · không tải được phiên', wlNXW + '(app shell) · máy chủ không trả lời', [empty('Không tải được phiên làm việc', 'Máy chủ tạm thời không trả lời. Hãy thử lại sau.', { icon: 'cloud_off', actions: [primary('Thử lại')] })], { state: true }),
  npage('WL17', 'Khung · không có quyền xem màn này', wlNXW + '(app shell) · CSKH mở một màn không thuộc quyền: thẻ "Bạn không có quyền xem màn này"', '', [
    empty('Bạn không có quyền xem màn này', 'Vai trò hiện tại không được cấp quyền. Liên hệ chủ phòng khám hoặc quản lý nếu cần.', { icon: 'lock' })], { nx: 'cs_staff', state: true, crumb: 'Nhân viên' }),
  npage('WL18', 'Khung · điện thoại · thanh tab', wlNXW + '(app shell) · 390: header với nút menu và tên phòng khám, thanh tab Việc · Hồ sơ · Inbox · Duyệt · Chờ tôi · Menu', '/today', wlTodayHead(), { nx: 'cs_staff', state: true, frames: ['390x844'] }),
  npage('WL19', 'Khung · điện thoại · ngăn menu', wlNXW + '(app shell) · 390: ngăn menu mở (nút "Đóng menu"), nền tối phía sau', '/today', wlTodayHead(), { nx: 'cs_staff', state: true, frames: ['390x844'], drawer: true })
];
