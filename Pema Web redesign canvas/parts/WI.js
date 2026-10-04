// WI · Patient Mobile web (parts WI.js and WI2.js are merged into this group). Owner: W6c-WI-1 (home, appointments, journey, progress, care).
// Use mob(id, name, note, activeTab, blocks, o) and the Patient Mobile blocks of base.js (see references/blocks-web.md section 9).

// The home page (old `patient.js#home`) is the same page for every care group: greeting, one next-step card chosen by the group, the journey hero,
// "Lịch hẹn tiếp theo", the three quick actions when no CSKH task is left, and "Đơn & phiếu đã duyệt". Only the data differs, so these ids share this builder.
const wi1Home = (p, o) => [
  mobTitle('Hôm nay của bạn', 'Chào ' + p.name.split(' ').pop()),
  o.step ? card({ title: o.step[0] }, txt(o.step[1]), primary(o.step[2] || 'Gửi cập nhật')) : null,
  hero(o.plan || 'Kế hoạch chăm sóc da cá nhân', 'Buổi ' + o.done + ' / ' + o.total + ' · Cập nhật ' + o.upd, 'route', { over: 'Hành trình đang tiếp diễn', small: true, rail: [o.done, o.total], actions: [light('Xem hành trình →')] }),
  card({ title: 'Lịch hẹn tiếp theo', aside: [quiet('Xem tất cả')] },
    o.when
      ? appt({ day: o.when[0], month: 'Tháng 09', lines: [o.when[1], p.doctor + ' · ' + o.when[2]] })
      : appt({ none: true, lines: ['Chưa có lịch hẹn · Liên hệ Pema để đặt lịch', p.doctor + ' · Theo dõi da sau điều trị'] })),
  o.tasks ? card({ title: 'Việc hôm nay', aside: [badge('Pema đồng hành', 'brand', { dot: false })] }, quick(['favorite', 'Chăm sóc', 'Hướng dẫn tại nhà'], ['photo_library', 'Ảnh tiến trình', 'So sánh mốc'], ['chat_bubble', 'Gửi cập nhật', 'Nhắn Pema'])) : null,
  o.rx ? rx({ sections: [{ title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] }] }) : rx()
];

const WI = [
  mob('WI1', 'Trang chủ', WEB + 'patient mobile · home · mở /patient-mobile/: thẻ bước tiếp theo (Đến mốc tái khám), hero hành trình với thanh buổi, Lịch hẹn tiếp theo, Đơn & phiếu đã duyệt; thanh dưới 5 tab · app E1 chỉ có 4 tab và hero khác', 'home', [
    mobTitle('Hôm nay của bạn', 'Chào ' + pt.name.split(' ').pop()),
    card({ title: 'Đến mốc tái khám' }, txt('Xem lịch đã đặt hoặc nhắn Pema để chọn thời gian.'), primary('Xem lịch hẹn')),
    hero('Liệu trình kiểm soát sắc tố', 'Buổi 2 / 5 · Cập nhật 6/9/2026', 'route', { over: 'Hành trình đang tiếp diễn', small: true, rail: [2, 5], actions: [light('Xem hành trình →')] }),
    card({ title: 'Lịch hẹn tiếp theo', aside: [quiet('Xem tất cả')] },
      appt({ day: '20', month: 'Tháng 09', lines: ['Chủ Nhật, 20/09 · 08:00', doctors[0].name + ' · Nám · tăng sắc tố'] })),
    rx({ sections: [{ title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] }] })
  ]),
  mob('WI2', 'Lịch hẹn', WEB + 'patient mobile · appointments · mở từ thanh dưới "Lịch hẹn": Sắp tới (chip Đã đặt lịch, nút Xác nhận tôi sẽ đến), Các lịch đã đặt, Lịch đã qua, lưu ý đổi lịch trước ít nhất 4 giờ · app K1 là ô lối vào, câu lưu ý bắt đầu bằng "Nếu bạn cần đổi lịch"', 'appointments', [
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
  ]),
  mob('WI3', 'Hành trình', WEB + 'patient mobile · journey · mở từ thanh dưới "Hành trình": tóm tắt liệu trình với số buổi (không phải mức cải thiện da), lối tắt Ảnh trước & sau, Cập nhật gần đây (3 mốc, bấm để mở) và Xem thêm lịch sử · app có H1-H3 riêng, không có thanh số buổi này', 'journey', [
    h1('Hành trình của bạn'),
    card({ g: 10 },
      eyebrow('Đang điều trị'),
      h2('Liệu trình kiểm soát sắc tố'),
      stepper('2/5 buổi', 40, 'Tiến độ số buổi, không phải mức cải thiện da.')),
    list([{ icon: 'photo_library', t: 'Ảnh trước & sau', sub: 'Xem các mốc ảnh trong hành trình', chev: true }], { box: true }),
    card({ title: 'Cập nhật gần đây', aside: [badge('4 mốc', 'neutral', { dot: false })] },
      events(
        { kind: 'followup', date: '13/9/2026', title: 'Cập nhật tại nhà đã được xem', detail: 'Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo.' },
        { kind: 'done', date: '6/9/2026', title: 'Hoàn tất buổi 2/5', detail: 'Chăm sóc & laser theo chỉ định. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.' },
        { kind: 'photo', date: '6/9/2026', title: 'Bộ ảnh theo dõi · chính diện', detail: 'Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.' }),
      quiet('Xem thêm lịch sử', { full: true }))
  ]),
  mob('WI4', 'Tin nhắn', WEB + 'patient mobile · messages · mở từ thanh dưới "Tin nhắn": thẻ Pema Care Team (chip Đang hỗ trợ), tin nhắn của đội ngũ kèm giờ, nút Gửi tin nhắn mở màn gửi cập nhật; không có ô soạn tin và không có câu "không phải kênh cấp cứu" (câu đó ở màn gửi cập nhật) · app E3 có lưu ý và hai ô Bạn / Đội ngũ Pema', 'messages', [
    back('← Trang chủ'),
    h1('Tin nhắn'),
    card({ title: 'Pema Care Team', aside: [badge('Đang hỗ trợ', 'success')] },
      bubbles({ text: 'Chào bạn, Pema đã lưu hướng dẫn chăm sóc của buổi điều trị gần nhất. Bạn có thể gửi cập nhật bất cứ lúc nào.', time: '13/09 · 09:15' }),
      primary('Gửi tin nhắn', { icon: 'add', full: true }))
  ]),
  mob('WI5', 'Hồ sơ', WEB + 'patient mobile · profile · mở từ thanh dưới "Hồ sơ" hoặc nút avatar: thẻ hồ sơ demo, ba dòng (Tài liệu & hóa đơn, Chăm sóc tại nhà, Quyền riêng tư), Đổi hồ sơ demo (hai ô chọn), Đơn & phiếu đã duyệt · app E4 có bốn dòng và nhãn khác, quyền riêng tư là dòng bật/tắt chứ không có màn riêng', 'profile', [
    h1('Hồ sơ'),
    card({},
      row({ g: 13, ai: 'center' }, avatar(pt.init, { size: 'lg' }), stack({ g: 2 }, h3(pt.name), txt(pt.age + ' tuổi · ' + pt.phone + ' · ' + pt.id, { size: 'l', tone: 'soft' }))),
      notice('Bạn đang xem trải nghiệm patient app của hồ sơ demo. Tài khoản và dữ liệu thật sẽ cần xác thực riêng.', 'info')),
    card({}, list([
      { icon: 'description', t: 'Tài liệu & hóa đơn', sub: 'Xem lịch sử thanh toán và hướng dẫn', chev: true },
      { icon: 'auto_awesome', t: 'Chăm sóc tại nhà', sub: 'Hướng dẫn của kế hoạch hiện tại', chev: true },
      { icon: 'verified_user', t: 'Quyền riêng tư', sub: 'Ảnh chăm sóc: đã đồng ý', chev: true }
    ], { sq: true })),
    card({ title: 'Đổi hồ sơ demo' },
      select('Nhóm tài khoản mẫu', 'Tất cả hồ sơ', { opts: ['Tất cả hồ sơ', 'Sau thủ thuật D+1', 'D+3 cần ảnh', 'D+7 bác sĩ review', 'Đến hạn tái khám', 'Quá hạn tái khám', 'Vắng/hủy chưa đặt lại', 'Nguy cơ bỏ liệu trình', '90 ngày chưa quay lại', '180 ngày chưa quay lại', 'Sinh nhật trong tuần'] }),
      select('Chọn người bệnh tổng hợp', pt.name + ' · ' + pt.id, { opts: people.map(x => x.name + ' · ' + x.id) }),
      txt('Chỉ dùng để trình diễn trải nghiệm liên thông; không đại diện đăng nhập thật.', { size: 'l', tone: 'soft' })),
    rx({ sections: [{ title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] }] })
  ]),
  mob('WI6', 'Tiến độ số buổi & ảnh', WEB + 'patient mobile · progress · từ Hành trình "Ảnh trước & sau" hoặc ô Ảnh tiến trình: So sánh mốc ảnh (chip Chính diện, hai khung Trước / Gần nhất, mỗi khung có tem MINH HỌA TỔNG HỢP), lưu ý chụp cùng góc và ánh sáng, thẻ Gửi ảnh cập nhật; thanh dưới sáng "Hành trình" · app G5 là "Theo dõi bằng hình ảnh", ba ô và một nút', 'progress', [
    back('← Hành trình'),
    h1('Tiến độ số buổi & ảnh'),
    card({ title: 'So sánh mốc ảnh', aside: [badge('Chính diện', 'brand', { dot: false })] },
      photos([{ label: 'Trước' }, { label: 'Gần nhất' }], { n: 2, sq: true }),
      notice('Cùng góc chụp, cùng ánh sáng giúp bác sĩ xem thay đổi trong bối cảnh. Không dùng ảnh này để tự chẩn đoán.', 'info')),
    card({ title: 'Gửi ảnh cập nhật' },
      txt('Gửi ảnh kèm mô tả để đội ngũ Pema xem và phản hồi.'),
      primary('Gửi ảnh cập nhật →'))
  ]),
  mob('WI7', 'Chăm sóc tại nhà', WEB + 'patient mobile · care · từ Hồ sơ "Chăm sóc tại nhà" hoặc ô Chăm sóc: hướng dẫn đã duyệt (Sau buổi điều trị, ba dòng theo thuốc), thẻ Khi nào cần nhắn Pema? với Tôi đã đọc hướng dẫn và Gửi cập nhật →; thanh dưới sáng "Hành trình" · app G1 có ba ô khác và nút "Gửi cập nhật cho Pema"', 'care', [
    back('← Trang chủ'),
    h1('Chăm sóc tại nhà'),
    card({ g: 10 },
      eyebrow('Sau buổi điều trị · 6/9/2026'),
      h2('Mỗi ngày một chút dịu dàng.'),
      txt('SPF 50+ mỗi sáng; thoa lại theo hướng dẫn', { tone: 'soft' }),
      list([
        { icon: 'auto_awesome', t: 'Sữa rửa mặt dịu nhẹ', sub: 'Sáng & tối · theo hướng dẫn đã duyệt' },
        { icon: 'auto_awesome', t: 'Dưỡng ẩm phục hồi', sub: 'Sau làm sạch · dùng lượng phù hợp' },
        { icon: 'auto_awesome', t: 'Chống nắng SPF 50+', sub: 'Buổi sáng · thoa lại theo hướng dẫn' }
      ], { sq: true })),
    card({ title: 'Khi nào cần nhắn Pema?' },
      txt('Nếu bạn thấy phản ứng bất thường, khó chịu kéo dài hoặc cần hỏi cách chăm sóc, hãy gửi cập nhật trong ứng dụng. Đội ngũ sẽ xem và phản hồi theo quy trình của phòng khám.', { size: 's' }),
      row({ g: 10 }, secondary('Tôi đã đọc hướng dẫn'), primary('Gửi cập nhật →')))
  ]),
  mob('WI8', 'Gửi cập nhật cho Pema', WEB + 'patient mobile · send · từ Chăm sóc tại nhà "Gửi cập nhật →": Bạn đang cảm thấy thế nào? (ô nhập), thêm ảnh (Chọn ảnh PNG/JPEG/WebP, tối đa 2,5 MB), ô đồng ý cho đội ngũ xem ảnh, Gửi cho Pema, lưu ý không phải kênh cấp cứu; thanh dưới sáng "Hành trình" · app G2 dùng ảnh mẫu và nút Gửi cập nhật bị khóa đến khi đồng ý', 'send', [
    back('← Chăm sóc tại nhà'),
    h1('Gửi cập nhật cho Pema'),
    card({},
      textarea('Bạn đang cảm thấy thế nào?', '', { ph: 'Ví dụ: Da hơi khô ở hai má từ tối qua...', lines: 4 }),
      upload({}),
      check('Tôi đồng ý để đội ngũ Pema xem ảnh này cho mục đích chăm sóc.', false),
      primary('Gửi cho Pema', { full: true }),
      notice('Tin nhắn được gửi tới đội ngũ chăm sóc. Đây không phải kênh cấp cứu.', 'info'))
  ]),
  mob('WI9', 'Tài liệu & hóa đơn', WEB + 'patient mobile · docs · từ Hồ sơ: Hóa đơn của bạn, Hướng dẫn đã gửi, Đơn & phiếu đã duyệt; thanh dưới sáng "Hồ sơ" (docs là màn con của Hồ sơ)', 'docs', [
    back('← Hồ sơ'),
    h1('Tài liệu & hóa đơn'),
    card({ title: 'Hóa đơn của bạn' }, list([
      { icon: 'description', t: 'Buổi chăm sóc / điều trị', sub: 'HD-0001 · 2026-09-06 · Đã thanh toán', actions: [strong(money(1200000))] },
      { icon: 'description', t: 'Tái khám & đánh giá', sub: 'HD-DEMO-001 · 2026-09-20 · Đã thu một phần · còn ' + money(150000), actions: [strong(money(300000))] }
    ], { sq: true })),
    card({ title: 'Hướng dẫn đã gửi' }, list([{ icon: 'photo_camera', t: 'Hướng dẫn chăm sóc sau buổi', sub: 'Hướng dẫn đã duyệt · 6/9/2026', chev: true }], { sq: true })),
    rx({ sections: [{ title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] }] })
  ]),
  mob('WI10', 'Trang chủ · Sau thủ thuật D+1', WEB + 'patient mobile · home · nhóm Sau thủ thuật D+1: thẻ bước tiếp theo "Hôm nay bạn cảm thấy thế nào?" với Gửi cập nhật; chưa có lịch hẹn nên ô lịch ghi "Chọn lịch"; Đơn & phiếu đã duyệt "Chưa có" · app E1 chỉ vẽ nhóm D+1 với câu khác', 'home',
    wi1Home(people[0], { step: ['Hôm nay bạn cảm thấy thế nào?', 'Gửi tình trạng sau buổi điều trị để đội ngũ Pema theo dõi.'], done: 3, total: 6, upd: '19/9/2026' }), { patient: people[0] }),
  mob('WI11', 'Trang chủ · D+3 cần ảnh', WEB + 'patient mobile · home · nhóm D+3 cần ảnh: thẻ "Cập nhật ảnh tiến triển" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[1], { step: ['Cập nhật ảnh tiến triển', 'Bạn có thể gửi ảnh cùng mô tả và đồng ý cho bác sĩ xem.'], done: 3, total: 6, upd: '17/9/2026' }), { patient: people[1] }),
  mob('WI12', 'Trang chủ · D+7 bác sĩ review', WEB + 'patient mobile · home · nhóm D+7 bác sĩ review: thẻ "Cùng bác sĩ xem lại tiến triển" với Gửi cập nhật; phản hồi sẽ ở Tin nhắn; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[2], { step: ['Cùng bác sĩ xem lại tiến triển', 'Gửi cập nhật để bác sĩ đánh giá; phản hồi sẽ ở Tin nhắn.'], done: 3, total: 6, upd: '13/9/2026' }), { patient: people[2] }),
  mob('WI13', 'Trang chủ · Quá hạn tái khám', WEB + 'patient mobile · home · nhóm Quá hạn tái khám: thẻ "Sắp xếp lần tái khám tiếp theo" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[4], { step: ['Sắp xếp lần tái khám tiếp theo', 'Nhắn Pema nếu bạn cần hỗ trợ chọn lịch phù hợp.'], done: 3, total: 6, upd: '7/8/2026' }), { patient: people[4] }),
  mob('WI14', 'Trang chủ · Vắng/hủy chưa đặt lại', WEB + 'patient mobile · home · nhóm Vắng/hủy chưa đặt lại: thẻ "Chọn lại một lịch hẹn phù hợp" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[5], { step: ['Chọn lại một lịch hẹn phù hợp', 'Đội ngũ Pema sẽ hỗ trợ bạn sắp xếp lại.'], done: 3, total: 6, upd: '16/8/2026' }), { patient: people[5] }),
  mob('WI15', 'Trang chủ · Nguy cơ bỏ liệu trình', WEB + 'patient mobile · home · nhóm Nguy cơ bỏ liệu trình: thẻ "Tiếp tục kế hoạch chăm sóc" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[6], { step: ['Tiếp tục kế hoạch chăm sóc', 'Trao đổi với Pema về các buổi còn lại của bạn.'], done: 3, total: 6, upd: '22/7/2026' }), { patient: people[6] }),
  mob('WI16', 'Trang chủ · 90 ngày chưa quay lại', WEB + 'patient mobile · home · nhóm 90 ngày chưa quay lại: thẻ "Pema sẵn sàng đồng hành" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[7], { step: ['Pema sẵn sàng đồng hành', 'Nhắn nhu cầu hiện tại để đội ngũ hỗ trợ.'], done: 3, total: 6, upd: '17/6/2026' }), { patient: people[7] }),
  mob('WI17', 'Trang chủ · 180 ngày chưa quay lại', WEB + 'patient mobile · home · nhóm 180 ngày chưa quay lại: thẻ "Kết nối lại với Pema" với Gửi cập nhật; chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[8], { step: ['Kết nối lại với Pema', 'Chia sẻ nhu cầu để được hỗ trợ trước khi hẹn khám.'], done: 3, total: 6, upd: '19/3/2026' }), { patient: people[8] }),
  mob('WI18', 'Trang chủ · Sinh nhật trong tuần', WEB + 'patient mobile · home · nhóm Sinh nhật trong tuần: thẻ "Một lời chúc từ Pema" với nút Mở tin nhắn (mở Tin nhắn, không phải màn gửi cập nhật); chưa có lịch hẹn · app E1 chỉ vẽ nhóm D+1', 'home',
    wi1Home(people[9], { step: ['Một lời chúc từ Pema', 'Chúc bạn đón tuổi mới thật nhiều sức khỏe.', 'Mở tin nhắn'], done: 3, total: 6, upd: '10/9/2026' }), { patient: people[9] }),
  mob('WI19', 'Trang chủ · đơn thuốc chờ duyệt (chưa hiện trên app)', WEB + 'patient mobile · home · nhóm Đến hạn tái khám, đơn thuốc đang chờ bác sĩ duyệt: thẻ "Đến mốc tái khám" với Xem lịch hẹn; ô Đơn & phiếu đã duyệt vẫn "Chưa có" vì đơn chưa duyệt không bao giờ hiện cho bệnh nhân · app E1 không có trạng thái này', 'home',
    wi1Home(people[3], { step: ['Đến mốc tái khám', 'Xem lịch đã đặt hoặc nhắn Pema để chọn thời gian.', 'Xem lịch hẹn'], plan: 'Theo dõi mụn & chăm sóc tại nhà', done: 2, total: 4, upd: '6/9/2026', when: ['20', 'Chủ Nhật, 20/09 · 08:00', 'Mụn viêm'] }), { patient: people[3] }),
  mob('WI20', 'Trang chủ · việc hôm nay (không còn việc CSKH)', WEB + 'patient mobile · home · hồ sơ không còn việc CSKH nên không có thẻ bước tiếp theo: thay bằng thẻ "Việc hôm nay" (chip Pema đồng hành) với ba lối tắt Chăm sóc, Ảnh tiến trình, Gửi cập nhật; có đơn đã duyệt · app E1 luôn có hàng lối tắt với "Đơn đã duyệt" thay cho "Ảnh tiến trình"', 'home',
    wi1Home(pt, { plan: 'Liệu trình kiểm soát sắc tố', done: 2, total: 5, upd: '6/9/2026', when: ['20', 'Chủ Nhật, 20/09 · 08:00', 'Nám · tăng sắc tố'], tasks: true, rx: true })),
  mob('WI21', 'Trang chủ · hồ sơ vừa tạo', WEB + 'patient mobile · home · hồ sơ vừa tạo: kế hoạch chờ bác sĩ thiết lập (Buổi 0 / 1, "Chưa ghi nhận"), lịch hẹn đã đặt, thẻ Việc hôm nay, chưa có đơn đã duyệt · app E1 không có trạng thái này', 'home',
    wi1Home(people[10], { plan: 'Chờ bác sĩ thiết lập kế hoạch', done: 0, total: 1, upd: 'Chưa ghi nhận', when: ['21', 'Thứ Hai, 21/09 · 10:30', 'Nám · tăng sắc tố'], tasks: true }), { patient: people[10] })
];
