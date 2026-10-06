// WK · Agent chăm sóc (Next.js only, W2 step W10): quản trị /admin/care/*, hàng đợi /care/handoffs, trang agent của bệnh nhân /care/patients/[id]/*.
const wkNXW = 'Next.js › ';
const wkNote = (route, text) => wkNXW + route + ' · ' + text;

// ---- shared header of the four /admin/care pages: title, sub line and the 5-tab bar (aria "Quản trị agent chăm sóc") ----
const wkCareTabs = ['Kỹ năng và ca trực', 'Số trực 24/24', 'Ma trận ngưỡng', 'SLA và khung giờ', 'Cảnh báo'];
const wkCareHead = i => [pageHead('Agent chăm sóc', 'Người nhận yêu cầu, số trực, ngưỡng độ sâu và thời hạn trả lời'), tabs(wkCareTabs, i)];

// ---- compositions (no own markup) ----
// StaffCard (care-ui.tsx): name, "{vai trò} · đang giữ n/m cuộc trò chuyện", "Sửa", skill badges or "Chưa có kỹ năng", weekly shifts or "Chưa có ca". Used by WK1, WK3 (behind).
const wkStaffCard = (name, meta, skills, shifts) => card({ comp: 'StaffCard', g: 10 },
  row({ jc: 'space-between', ai: 'flex-start' }, stack({ g: 2 }, h3(name), sm(meta)), secondary('Sửa')),
  skills.length ? tags(...skills.map(s => badge(s, 'info', { dot: false }))) : sm('Chưa có kỹ năng'),
  shifts ? sm(shifts) : sm('Chưa có ca'));
// OnCallCard (on-call page): name, number, validity, status badges and "Sửa". Used by WK4, WK6, WK7/WK8 (behind).
const wkOnCallCard = (on) => card({ comp: 'OnCallCard' },
  row({ jc: 'space-between', ai: 'flex-start' }, stack({ g: 2 }, h3('Điều dưỡng trực (mẫu)'), txt('0000000001'), sm('Từ 21/08 09:00, không giới hạn')),
    row({ g: 8 }, badge(on ? 'Đang bật' : 'Đã tắt', on ? 'success' : 'neutral'), badge('Số mẫu để thử', 'warning'), secondary('Sửa'))));
// AlertCard (alerts page): kind badge, link to the patient's care timeline, optional detail and the time. Used by WK18, WK20.
const wkAlertCard = (kind, tone, name, time, detail) => card({ comp: 'AlertCard' },
  row({ jc: 'space-between', ai: 'center' }, stack({ g: 4 }, tags(badge(kind, tone)), row({ g: 6 }, lnk(name), detail ? txt(detail) : null)), sm(time)));
// HandoffCard (care handoffs): patient link, age and step, urgency and depth badges, bold reason, summary, needed skill, confidence, SLA, optional error and the two actions.
const wkDepthTone = { D1: 'neutral', D2: 'info', D3: 'warning', D4: 'danger', D5: 'danger' };
const wkHandoffCard = o => card({ comp: 'HandoffCard', g: 8, tint: o.urgent ? 'danger' : '', title: o.name, sub: o.meta, aside: [badge(o.urgent ? 'Khẩn' : 'Thường', o.urgent ? 'danger' : 'neutral'), badge(o.depth, wkDepthTone[o.depth.slice(0, 2)])] },
  txt(o.reason, { w: 'b', size: 'lg' }),
  txt(o.summary, { tone: 'soft' }),
  row({ g: 10 }, badge(o.need, 'neutral', { dot: false }), sm('Độ tin cậy của agent ' + o.conf), o.onCall ? badge('Đã tới số trực 24/24', 'warning') : null, o.suggest ? sm(o.suggest) : null, ico('schedule', { size: 16 }), txt(o.sla, { size: 's', tone: o.slaTone || 'soft' })),
  o.error ? notice(o.error, 'danger') : null,
  o.noActions ? null : row({ g: 8 }, primary('Nhận cuộc trò chuyện'), secondary('Từ chối')));

// ============ WK1-WK3 · Kỹ năng và ca trực ============
const wkWeek = 'T2 08:00-17:00 · T3 08:00-17:00 · T4 08:00-17:00 · T5 08:00-17:00 · T6 08:00-17:00';
const wkStaffPage = () => [wkCareHead(0), grid(2,
  wkStaffCard('Mai Anh', 'CSKH · đang giữ 1/6 cuộc trò chuyện', ['Đặt lịch', 'Khiếu nại', 'Thanh toán'], wkWeek),
  wkStaffCard('Đặng Minh Thư', 'CSKH · đang giữ 0/5 cuộc trò chuyện', ['Đặt lịch', 'Mụn', 'Nám'], 'T2 08:00-12:00 · T3 08:00-12:00 · T4 08:00-12:00 · T5 08:00-12:00 · T6 08:00-12:00 · T7 08:00-12:00'),
  wkStaffCard('BS. Lê Minh Tâm', 'Bác sĩ · đang giữ 1/3 cuộc trò chuyện', ['Y khoa (bác sĩ)', 'Laser', 'Mụn'], wkWeek),
  wkStaffCard('Nguyễn Thanh Hà', 'Chủ phòng khám · đang giữ 0/2 cuộc trò chuyện', ['Khiếu nại'], wkWeek))];
const wkShiftDay = (day, on) => card({ v: 'soft', g: 8 },
  row({ jc: 'space-between' }, strong(day), quiet('Thêm ca')),
  on ? row({ g: 8 }, time(day + ', ca 1, bắt đầu', '08:00', { w: 150 }), txt('đến'), time(day + ', ca 1, kết thúc', '17:00', { w: 150 }), danger('Xóa', { sm: true })) : sm('Nghỉ'));

// ============ WK4-WK8 · Số trực 24/24 ============
const wkOnCallPage = (o = {}) => [wkCareHead(1),
  o.warn ? notice('Chưa có số trực nào đang bật. Chuỗi chuyển giao không có điểm cuối, hãy thêm số trực ngay.', 'danger') : null,
  row({ jc: 'flex-end' }, primary('Thêm số trực')),
  o.none ? empty('Chưa có số trực', 'Phòng khám cung cấp số Zalo trực 24/24; nhập ở đây.') : wkOnCallCard(!o.warn)];

// ============ WK9-WK14 · Ma trận ngưỡng ============
const wkDepths = { D1: 'D1 · Hành chính', D2: 'D2 · Chăm sóc chuẩn', D3: 'D3 · Triệu chứng nhẹ', D4: 'D4 · Phán đoán y khoa' };
const wkSignals = [['Mặc định', 'D4'], ['Khách VIP', 'D2'], ['Tiền sử phức tạp', 'D3'], ['Từng khiếu nại', 'D3'], ['Đang chờ việc của bác sĩ', 'D3'], ['Trong cửa sổ sau thủ thuật', 'D3'],
  ['Ngoài giờ làm việc', 'D3'], ['Khách muốn gặp người', 'D2'], ['Khách bực bội', 'D2'], ['Hỏi lặp lại', 'D2'], ['Câu trả lời trước bị từ chối', 'D2'], ['Mức khẩn', 'D4']];
const wkMsgTypes = ['Nhắc lịch theo mẫu', 'Hướng dẫn chăm sóc theo mẫu', 'Xác nhận lịch hẹn', 'Trả lời từ kho tri thức'];
// o: approved (state WK10), readonly (WK11), invalid (WK12)
const wkMatrixPage = (o = {}) => {
  const d = !!o.readonly;
  return [wkCareHead(2),
    row({ jc: 'space-between' }, badge(o.approved ? 'Bác sĩ đã duyệt' : 'Chờ bác sĩ duyệt', o.approved ? 'success' : 'warning'),
      o.approved ? secondary('Đặt lại chờ duyệt') : primary('Bác sĩ duyệt', { dis: !!o.invalid })),
    o.approved ? null : notice('Các số dưới đây là mặc định tạm thời. Bác sĩ quyết định ngưỡng cuối cùng; trước đó agent vẫn chạy theo các số này nhưng không coi là đã được duyệt.', 'warning'),
    d ? notice('Bạn chỉ xem được ma trận, không chỉnh được.', 'info') : null,
    card({ title: 'Khi nào agent nhờ người', sub: 'Từ độ sâu nào thì chuyển cho người, theo từng tín hiệu. Chọn mức thấp nhất áp dụng.' },
      grid(3, input('Ngưỡng tin cậy của agent', o.invalid ? '5' : '0.6', { dis: d, hint: 'Dưới ngưỡng thì chuyển cho người (0 đến 1)' }), input('Cửa sổ sau thủ thuật (giờ)', '48', { dis: d }),
        input('Số lần hỏi lặp lại', '2', { dis: d, hint: 'Hỏi cùng một câu từng này lần thì tính là lặp' })),
      select('Khách chưa xác minh danh tính chỉ được trả lời tới', wkDepths.D1, { dis: d }),
      list(wkSignals.map(([t, dp]) => ({ t, actions: [btn(wkDepths[dp], 'secondary', { ric: 'expand_more', dis: d, aria: 'Chuyển cho người từ độ sâu, tín hiệu ' + t })] })))),
    card({ title: 'Agent được tự gửi gì', sub: 'Số lần bác sĩ duyệt mà không sửa trước khi một loại tin được lên L2' },
      grid(2, input('Ngưỡng tin cậy để tự trả lời', '0.85', { dis: d, hint: 'L2 chỉ tự trả lời khi độ tin cậy từ ngưỡng này (0 đến 1)' }), check('Xác nhận lịch hẹn khách đã chọn chạy ở L1', false, { dis: d })),
      matrix(['Loại tin', ['Lên L2 sau (lần)', '160px'], ['Mở cho D3', '120px']], wkMsgTypes.map((m, i) => [m, mxIn('Lên L2 sau bao nhiêu lần, ' + m, String(3 + (i % 3))), mxCk('Mở cho D3, ' + m, i === 1)]), { foot: '7 loại tin' })),
    o.invalid ? notice('Ngưỡng tin cậy của agent là số từ 0 đến 1.', 'info') : null,
    d ? null : row({ g: 8 }, primary('Lưu ma trận', { dis: true }), secondary('Bỏ thay đổi', { dis: !o.invalid }))];
};

// ============ WK15-WK17 · SLA và khung giờ ============
const wkTimingPage = (o = {}) => {
  const d = !!o.readonly;
  return [wkCareHead(3), tags(badge('Chờ bác sĩ duyệt', 'warning')),
    card({ title: 'Thời hạn trả lời (SLA)', sub: 'Quá hạn thì yêu cầu chuyển cho người kế tiếp trong chuỗi' },
      grid(3, input('Khẩn (phút)', o.invalid ? '999' : '5', { dis: d }), input('Thường (phút)', '30', { dis: d }), input('Chuỗi tối đa (người)', '5', { dis: d, hint: 'Tính cả số trực 24/24 ở cuối' }))),
    card({ title: 'Ngoài giờ làm việc', sub: 'Yêu cầu từ độ sâu này trở lên đi thẳng tới số trực; nhẹ hơn thì chờ đầu ca kế tiếp' },
      row(btn(wkDepths.D3, 'secondary', { ric: 'expand_more', dis: d, aria: 'Đi thẳng tới số trực từ độ sâu' }))),
    card({ title: 'Khung giờ gửi tin', sub: 'Agent chỉ gửi tin trong khung giờ này; tin ngoài khung được xếp hàng tới giờ mở' },
      txt('08:00 đến 20:00', { w: 'b', size: 'sec' }),
      row({ g: 3 }, sm('Múi giờ'), sm('Asia/Ho_Chi_Minh'), sm('. Khung giờ chỉnh ở'), lnk('cài đặt kênh Zalo'), sm('.'))),
    o.invalid ? notice('SLA khẩn từ 1 đến 240 phút, SLA thường từ 1 đến 1440 phút, chuỗi từ 2 đến 10 người.', 'info') : null,
    d ? null : row(primary('Lưu', { dis: !!o.invalid }))];
};

// ============ WK18-WK20 · Cảnh báo agent ============
const wkAlertsPage = (o = {}) => [wkCareHead(4),
  o.offline ? notice('Mất kết nối cập nhật trực tiếp. Danh sách tự làm mới mỗi 30 giây, hệ thống sẽ nối lại khi có thể.', 'warning') : null,
  o.none ? empty('Chưa có cảnh báo nào', 'Khi agent bị hạ mức, gặp cờ đỏ hoặc dùng số trực, cảnh báo hiện ở đây.') : [
    wkAlertCard('Cờ đỏ', 'danger', 'Võ Ngọc Trâm', '20/09 08:58'),
    wkAlertCard('Đã dùng số trực 24/24', 'warning', 'Đặng Gia Linh', '20/09 08:19'),
    wkAlertCard('Khách không phản hồi nhiều lần', 'neutral', 'Ngô Mỹ Duyên', '19/09 09:00'),
    wkAlertCard('Agent bị hạ mức tự chủ', 'info', 'Nguyễn Thu Hà', '17/09 09:00', '· Đổi mức tự chủ của agent')]];

// ============ WK21-WK27 · Yêu cầu đang chờ tôi ============
const wkCardYen = (o = {}) => wkHandoffCard({ name: 'Lê Hoàng Yến', meta: 'Mở 18 phút trước · bước 1/3 trong chuỗi', depth: 'D3 · Triệu chứng nhẹ', reason: 'Khách bực bội',
  summary: 'Khách phàn nàn về thời gian chờ buổi hẹn trước và hỏi về hoàn phí. Giọng điệu không hài lòng.', need: 'Cần: Khiếu nại', conf: '81%', sla: 'Còn 12 phút', ...o });
const wkCardAnh = () => wkHandoffCard({ name: 'Trần Minh Anh', meta: 'Mở 6 phút trước · bước 1/3 trong chuỗi', depth: 'D2 · Chăm sóc chuẩn', reason: 'Khách muốn gặp người',
  summary: 'Khách hỏi lại lần thứ hai về lịch tái khám sau laser và nói muốn gặp nhân viên. Chưa có dấu hiệu bất thường.', need: 'Cần: Đặt lịch', conf: '72%', sla: 'Còn 24 phút' });
const wkCardLinh = () => wkHandoffCard({ name: 'Đặng Gia Linh', meta: 'Mở 41 phút trước · bước 2/2 trong chuỗi', urgent: true, depth: 'D4 · Phán đoán y khoa', reason: 'Câu hỏi vượt ngưỡng độ sâu',
  summary: 'Khách hỏi về tác dụng phụ của thuốc đang dùng. Hai người đầu chuỗi chưa phản hồi.', need: 'Cần: Y khoa (bác sĩ)', conf: '88%', onCall: true, suggest: 'BS. Lê Minh Tâm gợi ý bạn nhận', sla: 'Quá hạn 6 phút', slaTone: 'danger', noActions: true });
const wkCardTram = () => wkHandoffCard({ name: 'Võ Ngọc Trâm', meta: 'Mở 2 phút trước · bước 1/2 trong chuỗi', urgent: true, depth: 'D5 · Dấu hiệu nguy hiểm', reason: 'Dấu hiệu nguy hiểm (cờ đỏ)',
  summary: 'Khách báo sưng tăng và đau nhiều sau thủ thuật hôm qua. Cờ đỏ được phát hiện trước khi gọi mô hình.', need: 'Cần: Y khoa (bác sĩ)', conf: '95%', sla: 'Còn 3 phút', slaTone: 'warning', noActions: true });
const wkHandoffHead = scope => [pageHead('Yêu cầu đang chờ tôi', 'Agent nhờ người nhận khi cuộc trò chuyện vượt mức nó được tự xử lý'), chips([['Chờ tôi', scope === 0 ? 'sel' : ''], ['Tất cả đang mở', scope === 1 ? 'sel' : '']])];
// o: all (WK22), none (WK23), urgentFirst (WK24), error (WK25), offline (WK27)
const wkHandoffPage = (o = {}) => [
  o.offline ? notice('Mất kết nối cập nhật trực tiếp. Danh sách tự làm mới mỗi 30 giây, hệ thống sẽ nối lại khi có thể.', 'warning') : null,
  wkHandoffHead(o.all ? 1 : 0),
  o.none ? empty('Không có yêu cầu nào đang chờ bạn', 'Khi agent cần người, yêu cầu hiện ở đây kèm tóm tắt và thời hạn trả lời.')
    : stack({ g: 12 }, o.all ? [wkCardLinh(), wkCardTram()] : null,
      o.urgentFirst ? wkCardYen({ urgent: true, reason: 'Dấu hiệu nguy hiểm (cờ đỏ)', conf: '40%', onCall: true }) : wkCardYen(o.error ? { error: 'Yêu cầu này đã có người nhận hoặc đã đóng.' } : {}), wkCardAnh())];

// ============ WK28-WK39 · Agent chăm sóc của bệnh nhân (/care/patients/[id]/*) ============
const wkLevelTone = { L0: 'neutral', L1: 'info', L2: 'info' };
const wkPatientHead = (o, tabIdx) => [
  pageHead(o.name || 'Agent chăm sóc', 'Agent làm gì, đang giữ gì, đang chờ ai', [o.control && badge(o.control[0], o.control[1]), o.level && badge(o.level, wkLevelTone[o.level.slice(0, 2)]), quiet('Hồ sơ bệnh nhân')].filter(Boolean)),
  tabs(['Dòng thời gian', 'Trả lại cho agent', 'Nói với agent'], tabIdx)];
const wkStaffHold = { name: 'Bùi Khánh Vy', control: ['Nhân viên phụ trách', 'info'], level: 'L2 · Trả lời có nguồn' };
const wkAgentHold = { name: 'Nguyễn Thu Hà', control: ['Agent phụ trách', 'success'], level: 'L0 · Chỉ soạn nháp' };
const wkAct = (date, badges, text, subtext) => [sm(date), stack({ g: 4 }, tags(...badges), txt(text), subtext ? sm(subtext) : null)];
// o: kind 'staff' (WK28) | 'agent' (WK29) | 'seeking' (WK30) | 'empty' (WK31)
const wkTimelinePage = (o = {}) => {
  const kind = o.kind || 'staff';
  const head = kind === 'staff' ? wkStaffHold : kind === 'seeking' ? { ...wkStaffHold, control: ['Đang tìm người nhận', 'warning'] } : wkAgentHold;
  const status = kind === 'agent' ? [stat('Người phụ trách', 'Agent'), stat('Từ lúc', '21/08 09:00'), stat('Mức tự chủ hiện tại', 'L0 · Chỉ soạn nháp'), stat('Mức gốc của agent', 'L2 · Trả lời có nguồn'), stat('Đang hạ tạm thời', 'L0 · Chỉ soạn nháp, đến 23/09 09:00')]
    : kind === 'empty' ? [stat('Người phụ trách', 'Agent'), stat('Từ lúc', '21/08 09:00'), stat('Mức tự chủ hiện tại', 'L2 · Trả lời có nguồn'), stat('Mức gốc của agent', 'L2 · Trả lời có nguồn')]
    : [stat('Người phụ trách', kind === 'seeking' ? 'Chưa có, đang hỏi người nhận' : 'Mai Anh'), stat('Từ lúc', '20/09 07:00'), stat('Mức tự chủ hiện tại', 'L2 · Trả lời có nguồn'), stat('Mức gốc của agent', 'L2 · Trả lời có nguồn')];
  const activity = kind === 'agent' ? [wkAct('20/09 07:00', [badge('Agent đã gửi', 'success'), badge('D1 · Hành chính', 'neutral')], 'Nhắc lịch theo mẫu'),
      wkAct('19/09 07:00', [badge('Người đã duyệt', 'info'), badge('D2 · Chăm sóc chuẩn', 'info')], 'Trả lời từ kho tri thức', 'Mai Anh · Duyệt, không sửa.'),
      wkAct('17/09 09:00', [badge('Mức tự chủ', 'warning')], 'Đổi mức tự chủ của agent', 'Hạ mức có thời hạn khi trả lại cho agent.')]
    : [wkAct('20/09 07:00', [badge('Chuyển trạng thái', 'neutral')], 'Nhân viên nhận cuộc trò chuyện', 'Mai Anh'),
      wkAct('20/09 06:00', [badge('Chuyển trạng thái', 'neutral'), badge('D3 · Triệu chứng nhẹ', 'warning')], 'Agent nhờ người nhận cuộc trò chuyện'),
      wkAct('20/09 06:00', [badge('Đang giữ lại', 'warning')], 'Nhắc lịch theo mẫu'),
      wkAct('19/09 09:00', [badge('Agent đã gửi', 'success'), badge('D1 · Hành chính', 'neutral')], 'Hướng dẫn chăm sóc theo mẫu')];
  const empty4 = kind === 'empty';
  return [wkPatientHead(head, 0),
    card({ title: 'Trạng thái', sub: 'Ai đang phụ trách cuộc trò chuyện này' }, grid(2, ...status)),
    card({ title: 'Nháp đang chờ người duyệt', sub: 'Agent không gửi những tin này khi chưa có người duyệt' }, sm('Không có nháp nào đang chờ.')),
    card({ title: 'Nhắc đang tạm dừng', sub: 'Khi nhân viên giữ cuộc trò chuyện, agent không gửi nhắc theo lịch; khi trả lại, agent rà soát lại' },
      kind === 'staff' || kind === 'seeking' ? card({ v: 'soft', g: 8 }, row({ jc: 'space-between' }, badge('Đã tạm dừng', 'warning'), sm('Đến hạn 20/09 06:00')),
        txt('Chào anh/chị, đến hẹn tái khám theo lịch. Anh/chị muốn đặt giờ nào ạ?'), row(secondary('Sao chép để gửi tay'))) : sm('Không có nhắc nào bị tạm dừng.')),
    card({ title: 'Agent đã làm gì', sub: 'Mới nhất ở trên' }, empty4 ? sm('Chưa có hoạt động nào.') : grid({ cols: '110px minmax(0,1fr)', colsn: '1fr', g: 12 }, ...activity)),
    card({ title: 'Agent nhớ gì về khách', sub: 'Chỉ là thói quen và dặn dò, không có hồ sơ y khoa' },
      kind === 'agent' ? list([{ t: 'Khách thích nhận tin vào buổi tối, sau 18 giờ.', actions: [badge('Từ khách', 'info')] }, { t: 'Gọi khách bằng chị, không dùng tên riêng.', actions: [badge('Nhân viên dặn', 'success')] }]) : sm('Chưa có ghi nhớ nào.'))];
};
const wkReleaseLevels = ['Giữ mức hiện tại của agent', 'Hạ xuống L0 · Chỉ soạn nháp trong một thời gian', 'Hạ xuống L1 · Tin mẫu đã duyệt trong một thời gian', 'Hạ xuống L2 · Trả lời có nguồn trong một thời gian'];
const wkReleasePage = (o = {}) => [wkPatientHead(o.head || wkStaffHold, 1),
  o.block ? notice(o.block, 'info') : card({ g: 14 },
    textarea('Ghi chú bàn giao', '', { lines: 3, hint: 'Agent đọc ghi chú này ở các lượt sau. Thông tin cá nhân được che trước khi lưu.' }),
    txt('Mức tự chủ sau khi trả lại', { w: 'b', size: 's' }),
    stack({ g: 8 }, wkReleaseLevels.map((l, i) => radio('', [l], l === (o.lowered ? wkReleaseLevels[1] : wkReleaseLevels[0]) ? l : '', { }))),
    o.lowered ? input('Số ngày áp dụng', '7', { w: 112, hint: 'Sau thời hạn này agent tự về mức gốc. Tối đa 30 ngày.' }) : null,
    notice(o.lowered ? 'Hệ quả: Trong 7 ngày agent chỉ làm ở mức L0 (mọi tin chỉ là nháp chờ người duyệt), sau đó tự về mức L2.' : 'Hệ quả: Agent tiếp tục ở mức L2 (trả lời câu hỏi thường gặp có nguồn trích dẫn). Nhắc lịch đã tạm dừng được rà soát, chỉ gửi lại khi còn phù hợp.', 'info'),
    row(primary('Trả lại cho agent')))];
const wkTellPage = (head = wkStaffHold) => [wkPatientHead(head, 2),
  card({ g: 12 }, textarea('Lời dặn cho agent', '', { lines: 4, hint: 'Agent đọc lời dặn ở các lượt sau. Đây là thói quen hoặc ưu tiên của khách, không thay được mức tự chủ hay việc duyệt tin.' }), row(primary('Lưu lời dặn'))),
  card({ title: 'Lời dặn đã lưu', sub: 'Của nhân viên cho agent của khách này' }, sm('Chưa có lời dặn nào.'))];

const WK = [
  npage('WK1', 'Kỹ năng và ca trực', wkNote('/admin/care/staff', 'tab 1 của quản trị agent chăm sóc: một thẻ mỗi nhân viên, 2 cột'), '/admin/care/staff', wkStaffPage(), { nx: 'owner' }),
  npage('WK2', 'Kỹ năng và ca trực · chưa có hồ sơ', wkNote('/admin/care/staff', 'chưa có hồ sơ nhân viên: trạng thái trống thay cho các thẻ'), '/admin/care/staff',
    [wkCareHead(0), empty('Chưa có hồ sơ nhân viên nào', 'Hồ sơ được tạo khi nhân viên được thêm vào hệ thống.')], { nx: 'owner', state: true }),
  ndlg('WK3', 'Mai Anh', wkNote('/admin/care/staff', 'hộp thoại Sửa hồ sơ: kỹ năng, sức chứa, ngôn ngữ và ca trực theo tuần; trang Kỹ năng và ca trực nằm phía sau'), [
    txt('Kỹ năng', { w: 'b' }),
    row({ g: 8 }, check('Chung', false), check('Y khoa (bác sĩ)', false), check('Đặt lịch', true), check('Thanh toán', true), check('Khiếu nại', true), check('Mụn', false), check('Nám', false), check('Laser', false)),
    input('Thêm kỹ năng khác', '', { hint: 'Mã viết thường, không dấu, cách nhau bằng dấu phẩy (ví dụ: tiem_filler).' }),
    grid(2, input('Số cuộc trò chuyện cùng lúc', '6', { w: 112 }), input('Ngôn ngữ', 'vi', { hint: 'Mã ngôn ngữ, ví dụ: vi, en' })),
    txt('Ca trực trong tuần', { w: 'b' }),
    sm('Giờ theo múi giờ phòng khám. Giờ kết thúc sớm hơn giờ bắt đầu nghĩa là ca kéo sang sáng hôm sau.'),
    wkShiftDay('Thứ hai', true), wkShiftDay('Thứ ba', true), wkShiftDay('Thứ tư', true), wkShiftDay('Thứ năm', true), wkShiftDay('Thứ sáu', true), wkShiftDay('Thứ bảy', false), wkShiftDay('Chủ nhật', false)
  ], { nx: 'owner', nav: '/admin/care/staff', behind: wkStaffPage(), sub: 'Kỹ năng, ca trực và sức chứa dùng để chọn người nhận', w: 720, footer: [secondary('Hủy'), primary('Lưu')] }),

  npage('WK4', 'Số trực 24/24', wkNote('/admin/care/on-call', 'tab 2: số Zalo trực 24/24, điểm cuối của chuỗi chuyển giao; một thẻ mỗi số'), '/admin/care/on-call', wkOnCallPage(), { nx: 'owner' }),
  npage('WK5', 'Số trực 24/24 · chưa có số trực', wkNote('/admin/care/on-call', 'chưa có số trực nào: thông báo chuỗi không có điểm cuối và trạng thái trống'), '/admin/care/on-call', wkOnCallPage({ warn: true, none: true }), { nx: 'owner', state: true }),
  npage('WK6', 'Số trực 24/24 · không có số nào đang bật', wkNote('/admin/care/on-call', 'có số trực nhưng đã tắt: cùng thông báo, thẻ mang nhãn "Đã tắt"'), '/admin/care/on-call', wkOnCallPage({ warn: true }), { nx: 'owner', state: true }),
  ndlg('WK7', 'Thêm số trực', wkNote('/admin/care/on-call', 'hộp thoại Thêm số trực: các ô trống, "Đang bật" đã chọn; trang Số trực 24/24 nằm phía sau'), [
    input('Số Zalo trực', '', { hint: '8 đến 15 chữ số, có thể bắt đầu bằng +.' }), input('Người phụ trách', ''),
    grid(2, input('Có hiệu lực từ', '', { ph: 'mm/dd/yyyy --:-- --', suf: 'calendar_month' }), input('Đến (để trống: không giới hạn)', '', { ph: 'mm/dd/yyyy --:-- --', suf: 'calendar_month' })),
    check('Đang bật', true)
  ], { nx: 'owner', nav: '/admin/care/on-call', behind: wkOnCallPage(), sub: 'Số Zalo trực 24/24 luôn là điểm cuối của chuỗi chuyển giao', w: 560, footer: [secondary('Hủy'), primary('Lưu')] }),
  ndlg('WK8', 'Sửa số trực', wkNote('/admin/care/on-call', 'hộp thoại Sửa số trực của số mẫu: thông báo "số mẫu để thử", người phụ trách và giờ hiệu lực đã có; trang Số trực 24/24 nằm phía sau'), [
    notice('Đây là số mẫu để thử. Hãy nhập số trực thật do phòng khám cung cấp trước khi dùng thật.', 'warning'),
    input('Số Zalo trực', '', { hint: '8 đến 15 chữ số, có thể bắt đầu bằng +.' }), input('Người phụ trách', 'Điều dưỡng trực (mẫu)'),
    grid(2, input('Có hiệu lực từ', '08/21/2026 09:00 AM', { suf: 'calendar_month' }), input('Đến (để trống: không giới hạn)', '', { ph: 'mm/dd/yyyy --:-- --', suf: 'calendar_month' })),
    check('Đang bật', true)
  ], { nx: 'owner', nav: '/admin/care/on-call', behind: wkOnCallPage(), sub: 'Số Zalo trực 24/24 luôn là điểm cuối của chuỗi chuyển giao', w: 560, footer: [secondary('Hủy'), primary('Lưu')] }),

  npage('WK9', 'Ma trận ngưỡng', wkNote('/admin/care/matrix', 'tab 3: ma trận độ sâu × mức tự chủ, đang chờ bác sĩ duyệt; bác sĩ thấy nút "Bác sĩ duyệt"'), '/admin/care/matrix', wkMatrixPage(), { nx: 'doctor' }),
  npage('WK10', 'Ma trận ngưỡng · đã được bác sĩ duyệt', wkNote('/admin/care/matrix', 'đã duyệt: nhãn "Bác sĩ đã duyệt" và nút "Đặt lại chờ duyệt", không còn thông báo tạm thời'), '/admin/care/matrix', wkMatrixPage({ approved: true }), { nx: 'doctor', state: true }),
  npage('WK11', 'Ma trận ngưỡng · chỉ xem', wkNote('/admin/care/matrix', 'chỉ xem: mọi ô và nút chọn độ sâu bị tắt, không có nút lưu'), '/admin/care/matrix', wkMatrixPage({ readonly: true }), { nx: 'doctor', state: true }),
  npage('WK12', 'Ma trận ngưỡng · số không hợp lệ', wkNote('/admin/care/matrix', 'ngưỡng tin cậy nhập 5 (ngoài 0 đến 1): thông báo kiểm tra, "Bác sĩ duyệt" tắt, "Bỏ thay đổi" bật'), '/admin/care/matrix', wkMatrixPage({ invalid: true }), { nx: 'doctor', state: true }),
  ndlg('WK13', 'Duyệt ma trận này?', wkNote('/admin/care/matrix', 'hộp thoại xác nhận duyệt (người duyệt là bác sĩ); trang Ma trận ngưỡng nằm phía sau'), [
    txt('Các ngưỡng hiện tại được xác nhận là quyết định của bác sĩ. Hãy chắc rằng đã lưu mọi chỉnh sửa trước khi duyệt.', { tone: 'soft' })
  ], { nx: 'doctor', nav: '/admin/care/matrix', behind: wkMatrixPage(), w: 400, footer: [secondary('Hủy'), primary('Duyệt')] }),
  ndlg('WK14', 'Đặt lại về chờ duyệt?', wkNote('/admin/care/matrix', 'hộp thoại xác nhận đặt lại; ma trận đã duyệt nằm phía sau'), [
    txt('Ma trận sẽ hiện lại nhãn chờ bác sĩ duyệt.', { tone: 'soft' })
  ], { nx: 'doctor', nav: '/admin/care/matrix', behind: wkMatrixPage({ approved: true }), w: 400, footer: [secondary('Hủy'), primary('Đặt lại')] }),

  npage('WK15', 'SLA và khung giờ', wkNote('/admin/care/timing', 'tab 4: thời hạn trả lời, độ sâu ngoài giờ và khung giờ gửi tin'), '/admin/care/timing', wkTimingPage(), { nx: 'owner' }),
  npage('WK16', 'SLA và khung giờ · chỉ xem', wkNote('/admin/care/timing', 'chỉ xem: các ô tắt, không có nút "Lưu"'), '/admin/care/timing', wkTimingPage({ readonly: true }), { nx: 'owner', state: true }),
  npage('WK17', 'SLA và khung giờ · số không hợp lệ', wkNote('/admin/care/timing', 'SLA khẩn nhập 999: thông báo giới hạn, nút "Lưu" tắt'), '/admin/care/timing', wkTimingPage({ invalid: true }), { nx: 'owner', state: true }),

  npage('WK18', 'Cảnh báo agent', wkNote('/admin/care/alerts', 'tab 5: cờ đỏ, số trực 24/24, khách không phản hồi, agent bị hạ mức; mỗi dòng mở dòng thời gian của bệnh nhân'), '/admin/care/alerts', wkAlertsPage(), { nx: 'owner' }),
  npage('WK19', 'Cảnh báo agent · chưa có cảnh báo', wkNote('/admin/care/alerts', 'chưa có cảnh báo: trạng thái trống'), '/admin/care/alerts', wkAlertsPage({ none: true }), { nx: 'owner', state: true }),
  npage('WK20', 'Cảnh báo agent · mất kết nối trực tiếp', wkNote('/admin/care/alerts', 'thông báo mất kết nối cập nhật trực tiếp trên danh sách; tự làm mới mỗi 30 giây'), '/admin/care/alerts', wkAlertsPage({ offline: true }), { nx: 'owner', state: true }),

  npage('WK21', 'Yêu cầu đang chờ tôi', wkNote('/care/handoffs', 'hàng đợi chuyển giao của nhân viên CSKH: chip phạm vi, thẻ yêu cầu với "Nhận cuộc trò chuyện" và "Từ chối"'), '/care/handoffs', wkHandoffPage(), { nx: 'cs_staff' }),
  npage('WK22', 'Yêu cầu đang chờ tôi · tất cả đang mở', wkNote('/care/handoffs', 'chip "Tất cả đang mở": thêm hai thẻ khẩn không còn nút hành động'), '/care/handoffs', wkHandoffPage({ all: true }), { nx: 'cs_staff', state: true }),
  npage('WK23', 'Yêu cầu đang chờ tôi · chưa có yêu cầu', wkNote('/care/handoffs', 'không có yêu cầu nào: trạng thái trống'), '/care/handoffs', wkHandoffPage({ none: true }), { nx: 'cs_staff', state: true }),
  npage('WK24', 'Yêu cầu đang chờ tôi · thẻ khẩn đã tới số trực', wkNote('/care/handoffs', 'thẻ khẩn: nhãn "Khẩn", viền đỏ và nhãn "Đã tới số trực 24/24"'), '/care/handoffs', wkHandoffPage({ urgentFirst: true }), { nx: 'cs_staff', state: true }),
  npage('WK25', 'Yêu cầu đang chờ tôi · thẻ báo lỗi', wkNote('/care/handoffs', 'lỗi của backend hiện ngay trên thẻ khi có người nhận trước; danh sách tải lại'), '/care/handoffs', wkHandoffPage({ error: true }), { nx: 'cs_staff', state: true }),
  ndlg('WK26', 'Từ chối nhận cuộc trò chuyện', wkNote('/care/handoffs', 'hộp thoại Từ chối: lý do và đồng nghiệp gợi ý nhận thay; hàng đợi nằm phía sau'), [
    textarea('Lý do', '', { lines: 3, hint: 'Lý do giúp hệ thống chọn đúng người lần sau. Khách không thấy nội dung này.' }),
    select('Gợi ý đồng nghiệp nhận thay', 'Không gợi ý ai', { hint: 'Người được gợi ý sẽ được hỏi trước.' })
  ], { nx: 'cs_staff', nav: '/care/handoffs', behind: wkHandoffPage(), sub: 'Lê Hoàng Yến', w: 520, footer: [secondary('Quay lại'), primary('Gửi từ chối')] }),
  npage('WK27', 'Yêu cầu đang chờ tôi · mất kết nối trực tiếp', wkNote('/care/handoffs', 'thông báo mất kết nối cập nhật trực tiếp trên đầu danh sách; tự làm mới mỗi 30 giây'), '/care/handoffs', wkHandoffPage({ offline: true }), { nx: 'cs_staff', state: true }),

  npage('WK28', 'Agent chăm sóc của bệnh nhân · Dòng thời gian', wkNote('/care/patients/[id]/timeline', 'tab 1 của agent chăm sóc: trạng thái, nháp chờ duyệt, nhắc tạm dừng, việc agent đã làm, điều agent nhớ; nhân viên đang phụ trách'), '/care/handoffs', wkTimelinePage(), { nx: 'cs_staff' }),
  npage('WK29', 'Agent chăm sóc của bệnh nhân · agent phụ trách, đang hạ mức', wkNote('/care/patients/[id]/timeline', 'agent phụ trách, mức tự chủ tạm hạ xuống L0; không có nhắc tạm dừng, có hai ghi nhớ'), '/care/handoffs', wkTimelinePage({ kind: 'agent' }), { nx: 'cs_staff', state: true }),
  npage('WK30', 'Agent chăm sóc của bệnh nhân · đang tìm người nhận', wkNote('/care/patients/[id]/timeline', 'nhãn "Đang tìm người nhận", người phụ trách "Chưa có, đang hỏi người nhận"'), '/care/handoffs', wkTimelinePage({ kind: 'seeking' }), { nx: 'cs_staff', state: true }),
  npage('WK31', 'Agent chăm sóc của bệnh nhân · mục chưa có dữ liệu', wkNote('/care/patients/[id]/timeline', 'mọi mục chưa có dữ liệu: chữ xám thay cho danh sách'), '/care/handoffs', wkTimelinePage({ kind: 'empty' }), { nx: 'cs_staff', state: true }),
  npage('WK32', 'Agent chăm sóc của bệnh nhân · lỗi tải', wkNote('/care/patients/[id]/timeline', 'chỉ có tiêu đề dự phòng, thanh tab và thông báo lỗi kèm "Thử lại"'), '/care/handoffs',
    [wkPatientHead({}, 0), notice('Không tìm thấy bệnh nhân.', 'danger', { actions: [secondary('Thử lại')] })], { nx: 'cs_staff', state: true }),

  npage('WK33', 'Agent chăm sóc của bệnh nhân · Trả lại cho agent', wkNote('/care/patients/[id]/release', 'tab 2: ghi chú bàn giao, mức tự chủ sau khi trả lại và hệ quả do backend tính'), '/care/handoffs', wkReleasePage(), { nx: 'cs_staff' }),
  npage('WK34', 'Trả lại cho agent · hạ mức có hệ quả', wkNote('/care/patients/[id]/release', 'chọn hạ mức: hiện "Số ngày áp dụng" và hệ quả theo số ngày'), '/care/handoffs', wkReleasePage({ lowered: true }), { nx: 'cs_staff', state: true }),
  ndlg('WK35', 'Trả lại cho agent?', wkNote('/care/patients/[id]/release', 'hộp thoại xác nhận trả lại; biểu mẫu nằm phía sau'), [
    txt('Agent tiếp tục ở mức L2 (trả lời câu hỏi thường gặp có nguồn trích dẫn). Nhắc lịch đã tạm dừng được rà soát, chỉ gửi lại khi còn phù hợp.', { tone: 'soft' })
  ], { nx: 'cs_staff', nav: '/care/handoffs', behind: wkReleasePage(), w: 400, footer: [secondary('Hủy'), primary('Trả lại')] }),
  npage('WK36', 'Trả lại cho agent · không phải người đang giữ', wkNote('/care/patients/[id]/release', 'người không giữ cuộc trò chuyện chỉ thấy thông báo thay cho biểu mẫu'), '/care/handoffs',
    [wkPatientHead({ name: 'Hồ Thanh Tùng', control: ['Nhân viên phụ trách', 'info'], level: 'L1 · Tin mẫu đã duyệt' }, 1), notice('Chỉ người đang phụ trách cuộc trò chuyện mới trả lại cho agent được.', 'info')], { nx: 'cs_staff', state: true }),
  npage('WK37', 'Trả lại cho agent · agent đang phụ trách', wkNote('/care/patients/[id]/release', 'agent đang phụ trách: chưa có gì để trả lại, thông báo thay cho biểu mẫu'), '/care/handoffs',
    [wkPatientHead(wkAgentHold, 1), notice('Cuộc trò chuyện đang ở trạng thái "Agent phụ trách", chưa có gì để trả lại.', 'info')], { nx: 'cs_staff', state: true }),

  npage('WK38', 'Agent chăm sóc của bệnh nhân · Nói với agent', wkNote('/care/patients/[id]/tell-agent', 'tab 3: lời dặn cho agent (thói quen, ưu tiên của khách) và danh sách lời dặn đã lưu'), '/care/handoffs', wkTellPage(), { nx: 'cs_staff' }),
  npage('WK39', 'Nói với agent · chưa có lời dặn', wkNote('/care/patients/[id]/tell-agent', 'chưa có lời dặn nào đã lưu'), '/care/handoffs', wkTellPage(wkAgentHold), { nx: 'cs_staff', state: true })
];
