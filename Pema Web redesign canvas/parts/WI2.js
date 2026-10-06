// WI2 · Patient Mobile web, second part (merged into group WI by the build). Owner: W6c-WI-2 (send, messages, docs, profile, privacy, every modal and state).
// Shared pieces of the WI2 frames (names start with wi2 / WI2_ so they cannot clash with another part).
const WI2_NEW = { id: 'P047', name: 'Nguyễn Thử Nghiệm', init: 'TN', age: 28, phone: 'Chưa nhập', doctor: doctors[0].name, group: '', groupLabel: '' }; // profile created in the clinic web (WI26, WI27, WI30, WI41, WI42)
const WI2_EMERGENCY = 'Tin nhắn được gửi tới đội ngũ chăm sóc. Đây không phải kênh cấp cứu.';
const WI2_RX1 = { title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] };
const WI2_GROUPS = ['Tất cả hồ sơ', 'Sau thủ thuật D+1', 'D+3 cần ảnh', 'D+7 bác sĩ review', 'Đến hạn tái khám', 'Quá hạn tái khám', 'Vắng/hủy chưa đặt lại', 'Nguy cơ bỏ liệu trình', '90 ngày chưa quay lại', '180 ngày chưa quay lại', 'Sinh nhật trong tuần'];
const WI2_EVENTS = [
  { kind: 'followup', date: '13/9/2026', title: 'Cập nhật tại nhà đã được xem', detail: 'Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo.' },
  { kind: 'done', date: '6/9/2026', title: 'Hoàn tất buổi 2/5', detail: 'Chăm sóc & laser theo chỉ định. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.' },
  { kind: 'photo', date: '6/9/2026', title: 'Bộ ảnh theo dõi · chính diện', detail: 'Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.' },
  { kind: 'done', date: '26/6/2026', title: 'Bắt đầu liệu trình kiểm soát sắc tố', detail: 'Mục tiêu và lịch đánh giá đã được trao đổi với người bệnh.' }
];
const WI2_ROUTINE = [
  { icon: 'auto_awesome', t: 'Sữa rửa mặt dịu nhẹ', sub: 'Sáng & tối · theo hướng dẫn đã duyệt' },
  { icon: 'auto_awesome', t: 'Dưỡng ẩm phục hồi', sub: 'Sau làm sạch · dùng lượng phù hợp' },
  { icon: 'auto_awesome', t: 'Chống nắng SPF 50+', sub: 'Buổi sáng · thoa lại theo hướng dẫn' }
];
// Journey screen (Hành trình): summary card, photo shortcut, "Cập nhật gần đây" card. o: plan, label, pct, count, events (none = empty line), more ("Xem thêm lịch sử").
const wi2Journey = o => [
  h1('Hành trình của bạn'),
  card({}, eyebrow('Đang điều trị'), h2(o.plan), stepper(o.label, o.pct, 'Tiến độ số buổi, không phải mức cải thiện da.')),
  list([{ icon: 'photo_library', t: 'Ảnh trước & sau', sub: 'Xem các mốc ảnh trong hành trình', chev: true }], { box: true }),
  card({ title: 'Cập nhật gần đây', aside: [badge(o.count, 'neutral', { dot: false })] }, o.events ? events(...o.events) : sm('Chưa có sự kiện trong hành trình.'), o.more ? quiet('Xem thêm lịch sử') : null)
];
// Send-update screen (Gửi cập nhật cho Pema): msg = text of the draft, up = options of upload().
const wi2Send = (msg, up) => [
  back('← Chăm sóc tại nhà'),
  h1('Gửi cập nhật cho Pema'),
  card({},
    textarea('Bạn đang cảm thấy thế nào?', msg, { ph: 'Ví dụ: Da hơi khô ở hai má từ tối qua...' }),
    upload(up),
    check('Tôi đồng ý để đội ngũ Pema xem ảnh này cho mục đích chăm sóc.', false),
    primary('Gửi cho Pema', { full: true }),
    notice(WI2_EMERGENCY, 'info'))
];
// Care screen (Chăm sóc tại nhà): routine = care rows (null for a new patient), readBtn = the acknowledge button.
const wi2Care = (eyebrowText, routine, readBtn) => [
  back('← Trang chủ'),
  h1('Chăm sóc tại nhà'),
  card({}, eyebrow(eyebrowText), h2('Mỗi ngày một chút dịu dàng.'),
    routine ? [txt('SPF 50+ mỗi sáng; thoa lại theo hướng dẫn', { tone: 'soft' }), list(routine, { sq: true })] : sm('Chưa có hướng dẫn được duyệt.')),
  card({ title: 'Khi nào cần nhắn Pema?' },
    txt('Nếu bạn thấy phản ứng bất thường, khó chịu kéo dài hoặc cần hỏi cách chăm sóc, hãy gửi cập nhật trong ứng dụng. Đội ngũ sẽ xem và phản hồi theo quy trình của phòng khám.'),
    row({ g: 10 }, readBtn, primary('Gửi cập nhật →')))
];
// Docs screen (Tài liệu & hóa đơn): invoices = doc-rows (empty = the flat empty line), guideDate, rxBlock = the "Đơn & phiếu đã duyệt" card.
const wi2Docs = (invoices, guideDate, rxBlock) => [
  back('← Hồ sơ'),
  h1('Tài liệu & hóa đơn'),
  card({ title: 'Hóa đơn của bạn' }, invoices.length ? list(invoices, { sq: true }) : empty('Chưa có hóa đơn trong demo.', '', { flat: true })),
  card({ title: 'Hướng dẫn đã gửi' }, list([{ icon: 'photo_camera', t: 'Hướng dẫn chăm sóc sau buổi', sub: 'Hướng dẫn đã duyệt · ' + guideDate, chev: true }], { sq: true })),
  rxBlock
];
// Profile screen (Hồ sơ): p = the patient, consent = subtitle of the privacy row, rxBlock = the "Đơn & phiếu đã duyệt" card.
const wi2Profile = (p, consent, rxBlock) => [
  h1('Hồ sơ'),
  card({}, row({ g: 13 }, avatar(p.init, { size: 'lg' }), stack({ g: 2 }, h3(p.name), sm(p.age + ' tuổi · ' + p.phone + ' · ' + p.id))),
    notice('Bạn đang xem trải nghiệm patient app của hồ sơ demo. Tài khoản và dữ liệu thật sẽ cần xác thực riêng.', 'info')),
  card({}, list([
    { icon: 'description', t: 'Tài liệu & hóa đơn', sub: 'Xem lịch sử thanh toán và hướng dẫn', chev: true },
    { icon: 'auto_awesome', t: 'Chăm sóc tại nhà', sub: 'Hướng dẫn của kế hoạch hiện tại', chev: true },
    { icon: 'verified_user', t: 'Quyền riêng tư', sub: 'Ảnh chăm sóc: ' + consent, chev: true }
  ], { sq: true })),
  card({ title: 'Đổi hồ sơ demo' },
    select('Nhóm tài khoản mẫu', 'Tất cả hồ sơ', { opts: WI2_GROUPS }),
    select('Chọn người bệnh tổng hợp', p.name + ' · ' + p.id, { opts: people.slice(0, 8).map(x => x.name + ' · ' + x.id) }),
    sm('Chỉ dùng để trình diễn trải nghiệm liên thông; không đại diện đăng nhập thật.')),
  rxBlock
];

const WI2 = [
  mob('WI22', 'Lịch hẹn · chưa có lịch', WEB + 'patient mobile · appointments · hồ sơ demo chưa có lịch (nhóm "Quá hạn tái khám"): chip "Chưa có lịch", ô "Chọn lịch", nút "Xác nhận tôi sẽ đến" bị khóa, "Chưa có lịch đã đặt." · app K1 không có trạng thái trống', 'appointments', [
    back('← Trang chủ'),
    h1('Lịch hẹn'),
    card({ title: 'Sắp tới', aside: [badge('Chưa có lịch', 'brand', { dot: false })] },
      appt({ none: true, lines: ['Chưa có lịch hẹn · Liên hệ Pema để đặt lịch · Pema Clinic', doctors[0].name + ' · Theo dõi da sau điều trị'] }),
      primary('Xác nhận tôi sẽ đến', { full: true, dis: true })),
    card({ title: 'Các lịch đã đặt' }, sm('Chưa có lịch đã đặt.')),
    card({ title: 'Lịch đã qua' }, list([
      { icon: 'check', t: 'Buổi 3 · Chăm sóc theo chỉ định', sub: '7/8/2026 · Đã hoàn tất', chev: true },
      { icon: 'check', t: 'Tư vấn ban đầu', sub: '26/06/2026 · Đã hoàn tất', chev: true }
    ], { sq: true })),
    notice('Nếu bạn cần đổi lịch, hãy nhắn cho đội ngũ Pema trước ít nhất 4 giờ.', 'info')
  ], { state: true, patient: people[4] }),
  mob('WI23', 'Lịch hẹn · đã xác nhận', WEB + 'patient mobile · appointments · bấm "Xác nhận tôi sẽ đến": toast "Đã xác nhận lịch hẹn" (2,8 giây) trên thanh dưới; lịch hẹn đã đặt, lịch đã qua và lưu ý đổi lịch giữ nguyên', 'appointments', [
    back('← Trang chủ'),
    h1('Lịch hẹn'),
    card({ title: 'Sắp tới', aside: [badge('Đã đặt lịch', 'brand', { dot: false })] },
      appt({ day: '20', month: 'Tháng 09', lines: ['Chủ Nhật, 20/09 · 08:00 · Pema Clinic', doctors[0].name + ' · Nám · tăng sắc tố'] }),
      primary('Xác nhận tôi sẽ đến', { full: true })),
    card({ title: 'Các lịch đã đặt' }, list([
      { icon: 'calendar_month', t: '20/9/2026 · 08:00', sub: services[0].name + ' · ' + services[0].mins + ' phút', sub2: doctors[0].name },
      { icon: 'calendar_month', t: '26/9/2026 · 09:00', sub: services[2].name + ' · ' + services[2].mins + ' phút', sub2: doctors[2].name }
    ], { sq: true })),
    card({ title: 'Lịch đã qua' }, list([
      { icon: 'check', t: 'Buổi 2 · Chăm sóc & laser theo chỉ định', sub: '6/9/2026 · Đã hoàn tất', chev: true },
      { icon: 'check', t: 'Tư vấn ban đầu', sub: '26/06/2026 · Đã hoàn tất', chev: true }
    ], { sq: true })),
    notice('Nếu bạn cần đổi lịch, hãy nhắn cho đội ngũ Pema trước ít nhất 4 giờ.', 'info')
  ], { state: true, toast: 'Đã xác nhận lịch hẹn' }),
  mob('WI24', 'Hành trình · xem thêm lịch sử', WEB + 'patient mobile · journey · sau "Xem thêm lịch sử": cả bốn mốc hiện ra (mới nhất trên cùng), nút "Xem thêm lịch sử" biến mất, các dòng đóng', 'journey',
    wi2Journey({ plan: 'Liệu trình kiểm soát sắc tố', label: '2/5 buổi', pct: 40, count: '4 mốc', events: WI2_EVENTS }), { state: true }),
  mob('WI25', 'Hành trình · mở chi tiết', WEB + 'patient mobile · journey · dòng đầu mở (<details open>): câu chi tiết hiện dưới tiêu đề, "Xem thêm lịch sử" còn đó', 'journey',
    wi2Journey({ plan: 'Liệu trình kiểm soát sắc tố', label: '2/5 buổi', pct: 40, count: '4 mốc', events: [{ ...WI2_EVENTS[0], open: true }, WI2_EVENTS[1], WI2_EVENTS[2]], more: true }), { state: true }),
  mob('WI26', 'Hành trình · hồ sơ mới', WEB + 'patient mobile · journey · hồ sơ vừa tạo ở clinic web: "Chờ bác sĩ thiết lập kế hoạch", "0/1 buổi", "0 mốc", "Chưa có sự kiện trong hành trình." · app không có trạng thái trống', 'journey',
    wi2Journey({ plan: 'Chờ bác sĩ thiết lập kế hoạch', label: '0/1 buổi', pct: 0, count: '0 mốc' }), { state: true, patient: WI2_NEW }),
  mob('WI27', 'Tin nhắn · hồ sơ mới', WEB + 'patient mobile · messages · hồ sơ mới chưa có tin nhắn: chỉ có đầu thread "Pema Care Team" · "Đang hỗ trợ" và nút "Gửi tin nhắn", không có câu trạng thái trống', 'messages', [
    back('← Trang chủ'),
    h1('Tin nhắn'),
    card({ title: 'Pema Care Team', aside: [badge('Đang hỗ trợ', 'success')] }, primary('Gửi tin nhắn', { icon: 'add', full: true }))
  ], { state: true, patient: WI2_NEW }),
  mob('WI28', 'Tin nhắn · đã gửi cập nhật', WEB + 'patient mobile · messages · sau "Gửi cho Pema": chuyển sang Tin nhắn, tin của bạn bên phải "20/09 · vừa xong", toast "Đã gửi cập nhật tới đội ngũ Pema" · app G2 báo "vào hàng chờ"', 'messages', [
    back('← Trang chủ'),
    h1('Tin nhắn'),
    card({ title: 'Pema Care Team', aside: [badge('Đang hỗ trợ', 'success')] },
      bubbles({ text: 'Chào bạn, Pema đã lưu hướng dẫn chăm sóc của buổi điều trị gần nhất. Bạn có thể gửi cập nhật bất cứ lúc nào.', time: '13/09 · 09:15' }, { text: 'Da hơi khô ở hai má từ tối qua.', time: '20/09 · vừa xong', mine: true }),
      primary('Gửi tin nhắn', { icon: 'add', full: true }))
  ], { state: true, toast: 'Đã gửi cập nhật tới đội ngũ Pema' }),
  mob('WI29', 'Chăm sóc · đã đọc hướng dẫn', WEB + 'patient mobile · care · bấm "Đã đọc hướng dẫn": nút đổi thành "✓ Đã đọc hướng dẫn", toast "Đã ghi nhận bạn đã đọc hướng dẫn" · app G1 giữ "Tôi đã đọc hướng dẫn"', 'care',
    wi2Care('Sau buổi điều trị · 6/9/2026', WI2_ROUTINE, secondary('Đã đọc hướng dẫn', { icon: 'check' })), { state: true, toast: 'Đã ghi nhận bạn đã đọc hướng dẫn' }),
  mob('WI30', 'Chăm sóc · hồ sơ mới', WEB + 'patient mobile · care · hồ sơ mới: "Sau buổi điều trị · Chưa ghi nhận", không có dòng thuốc, "Chưa có hướng dẫn được duyệt." · app không có trạng thái trống', 'care',
    wi2Care('Sau buổi điều trị · Chưa ghi nhận', null, secondary('Tôi đã đọc hướng dẫn')), { state: true, patient: WI2_NEW }),
  mob('WI31', 'Gửi cập nhật · thiếu nội dung', WEB + 'patient mobile · send · bấm "Gửi cho Pema" khi chưa viết gì: toast "Hãy viết vài dòng cập nhật", không lưu gì · app G2 khóa nút thay vì báo', 'send',
    wi2Send('', {}), { state: true, toast: 'Hãy viết vài dòng cập nhật' }),
  mob('WI32', 'Gửi cập nhật · đã chọn ảnh', WEB + 'patient mobile · send · chọn ảnh tổng hợp: "Đã chọn: anh-demo.png (đã giữ trong phiên demo)", xem trước, ô đồng ý bỏ tick (mỗi ảnh hỏi đồng ý lại) · app G2 vẽ ảnh mẫu bằng nút', 'send',
    wi2Send('Da hơi khô ở hai má.', { file: 'anh-demo.png', preview: true }), { state: true }),
  mob('WI33', 'Gửi cập nhật · thiếu đồng ý ảnh', WEB + 'patient mobile · send · gửi kèm ảnh nhưng chưa tick: toast "Bạn cần đồng ý để Pema xem ảnh cập nhật", chữ và ảnh vẫn giữ làm bản nháp · app G2 khóa nút gửi', 'send',
    wi2Send('Da hơi khô ở hai má.', { file: 'anh-demo.png' }), { state: true, toast: 'Bạn cần đồng ý để Pema xem ảnh cập nhật' }),
  mob('WI34', 'Gửi cập nhật · tệp không hợp lệ', WEB + 'patient mobile · send · chọn tệp không phải ảnh: toast "Chỉ hỗ trợ PNG, JPEG hoặc WebP.", ảnh nháp bị xóa (lỗi khác: "Ảnh demo tối đa 2,5 MB.", "Tệp không phải ảnh hợp lệ.", "Không đọc được ảnh.") · app không có lỗi tệp', 'send',
    wi2Send('', {}), { state: true, toast: 'Chỉ hỗ trợ PNG, JPEG hoặc WebP.' }),
  mob('WI35', 'Tài liệu · hóa đơn chờ thanh toán', WEB + 'patient mobile · docs · hồ sơ P002: một hóa đơn "Đã thanh toán" và một "Chờ thanh toán"; thanh dưới sáng "Hồ sơ" · app G7 mở bằng "Khoản cần thanh toán"', 'docs',
    wi2Docs([
      { icon: 'description', t: 'Buổi chăm sóc / điều trị', sub: 'HD-0002 · 2026-09-06 · Đã thanh toán', actions: [strong(money(1500000))] },
      { icon: 'description', t: services[1].name, sub: 'HD-DEMO-002 · 2026-09-20 · Chờ thanh toán', actions: [strong(money(500000))] }
    ], '6/9/2026', rx()), { state: true, patient: people[1] }),
  mob('WI36', 'Tài liệu · chưa có hóa đơn', WEB + 'patient mobile · docs · hồ sơ chưa có hóa đơn: "Chưa có hóa đơn trong demo.", "Hướng dẫn đã gửi" vẫn có dòng, thẻ đơn & phiếu hiện "Chưa có" · app K2 luôn có hóa đơn', 'docs',
    wi2Docs([], '19/9/2026', rx()), { state: true }),
  mob('WI37', 'Tài liệu · đơn đã duyệt từ thu ngân', WEB + 'patient mobile · docs · phiếu đã duyệt ở thu ngân (WF6) hiện trong "Đơn & phiếu đã duyệt" cạnh đơn thuốc: ngày, "Đã duyệt bởi …", nhóm "Đơn thuốc" và "Phiếu tư vấn"; hóa đơn "Đơn sản phẩm · 2 dòng" chờ thanh toán (mã hóa đơn ngẫu nhiên, ở đây là mã giữ chỗ)', 'docs',
    wi2Docs([
      { icon: 'description', t: 'Đơn sản phẩm · 2 dòng', sub: 'HD-8ab4058e-d736-44a1-bdcd-bd5b896520d2 · 2026-09-20 · Chờ thanh toán', actions: [strong(money(720500))] },
      { icon: 'description', t: 'Buổi chăm sóc / điều trị', sub: 'HD-0001 · 2026-09-06 · Đã thanh toán', actions: [strong(money(1200000))] },
      { icon: 'description', t: 'Tái khám & đánh giá', sub: 'HD-DEMO-001 · 2026-09-20 · Đã thu một phần · còn ' + money(150000), actions: [strong(money(300000))] }
    ], '6/9/2026', rx({
      sections: [WI2_RX1, {
        title: '20/9/2026', sub: 'Đã duyệt bởi ' + doctors[0].name + ' · 20/9/2026',
        groups: [
          { heading: 'Đơn thuốc', lines: [{ name: 'Desloratadine/Genepharm (Desloratadine 5 mg) Hộp 30 Viên - Viên - A', qty: '1 Viên', use: 'Bôi lớp mỏng, sáng và tối, 14 ngày' }] },
          { heading: 'Phiếu tư vấn', lines: [{ name: 'Cicaderm Cream 40ml - Kem làm mềm da, dưỡng ẩm, hỗ trợ làm đều màu da, mờ sẹo 40 ml - A', qty: '1 Hộp', use: 'Bôi lớp mỏng, sáng và tối, 14 ngày' }] }
        ]
      }]
    })), { state: true }),
  mob('WI38', 'Hồ sơ · tắt đồng ý ảnh', WEB + 'patient mobile · profile · bấm dòng "Quyền riêng tư" (không có màn riêng): đồng ý ảnh chăm sóc bị tắt, dòng đọc "Ảnh chăm sóc: chưa đồng ý", toast "Đã tắt đồng ý ảnh chăm sóc trong demo", không hộp xác nhận', 'profile',
    wi2Profile(pt, 'chưa đồng ý', rx({ sections: [WI2_RX1] })), { state: true, toast: 'Đã tắt đồng ý ảnh chăm sóc trong demo' }),
  mob('WI39', 'Hồ sơ · bật lại đồng ý ảnh', WEB + 'patient mobile · profile · bấm "Quyền riêng tư" lần hai: đồng ý ảnh bật lại, dòng đọc "Ảnh chăm sóc: đã đồng ý", toast "Đã đồng ý ảnh cho chăm sóc trong demo"', 'profile',
    wi2Profile(pt, 'đã đồng ý', rx({ sections: [WI2_RX1] })), { state: true, toast: 'Đã đồng ý ảnh cho chăm sóc trong demo' }),
  mob('WI40', 'Hồ sơ · đổi hồ sơ demo', WEB + 'patient mobile · profile · chọn người bệnh khác trong "Chọn người bệnh tổng hợp": xóa bản nháp, lưu hồ sơ đã chọn, toast "Đã đổi hồ sơ demo"; ô nhóm tài khoản chỉ lọc danh sách, không toast', 'profile',
    wi2Profile(people[1], 'đã đồng ý', rx()), { state: true, toast: 'Đã đổi hồ sơ demo', patient: people[1] }),
  mob('WI41', 'Hồ sơ · hồ sơ mới', WEB + 'patient mobile · profile · hồ sơ vừa tạo ở clinic web (P047): "28 tuổi · Chưa nhập · P047", "Ảnh chăm sóc: chưa đồng ý", danh sách chọn có thêm hồ sơ mới', 'profile',
    wi2Profile(WI2_NEW, 'chưa đồng ý', rx()), { state: true, patient: WI2_NEW }),
  mob('WI42', 'Lịch hẹn · hồ sơ mới', WEB + 'patient mobile · appointments · hồ sơ mới: có ngày sắp tới (21/09 10:30, "Đã đặt lịch") nhưng "Chưa có lịch đã đặt.", lịch đã qua "Buổi 1 · Tư vấn ban đầu · Chưa ghi nhận"', 'appointments', [
    back('← Trang chủ'),
    h1('Lịch hẹn'),
    card({ title: 'Sắp tới', aside: [badge('Đã đặt lịch', 'brand', { dot: false })] },
      appt({ day: '21', month: 'Tháng 09', lines: ['Thứ Hai, 21/09 · 10:30 · Pema Clinic', doctors[0].name + ' · Nám · tăng sắc tố'] }),
      primary('Xác nhận tôi sẽ đến', { full: true })),
    card({ title: 'Các lịch đã đặt' }, sm('Chưa có lịch đã đặt.')),
    card({ title: 'Lịch đã qua' }, list([
      { icon: 'check', t: 'Buổi 1 · Tư vấn ban đầu', sub: 'Chưa ghi nhận · Đã hoàn tất', chev: true },
      { icon: 'check', t: 'Tư vấn ban đầu', sub: '26/06/2026 · Đã hoàn tất', chev: true }
    ], { sq: true })),
    notice('Nếu bạn cần đổi lịch, hãy nhắn cho đội ngũ Pema trước ít nhất 4 giờ.', 'info')
  ], { state: true, patient: WI2_NEW })
];
