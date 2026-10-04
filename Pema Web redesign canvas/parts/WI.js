// WI · Patient Mobile web (parts WI.js and WI2.js are merged into this group). Owner: W6c-WI-1 (home, appointments, journey, progress, care).
// Use mob(id, name, note, activeTab, blocks, o) and the Patient Mobile blocks of base.js (see references/blocks-web.md section 9).
const WI = [
  mob('WI1', 'Trang chủ', WEB + 'patient mobile · home · mở /patient-mobile/: thẻ bước tiếp theo (Đến mốc tái khám), hero hành trình với thanh buổi, Lịch hẹn tiếp theo, Đơn & phiếu đã duyệt; thanh dưới 5 tab · app E1 chỉ có 4 tab và hero khác', 'home', [
    mobTitle('Hôm nay của bạn', 'Chào ' + pt.name.split(' ').pop()),
    card({ title: 'Đến mốc tái khám' }, txt('Xem lịch đã đặt hoặc nhắn Pema để chọn thời gian.'), primary('Xem lịch hẹn')),
    hero('Liệu trình kiểm soát sắc tố', 'Buổi 2 / 5 · Cập nhật 6/9/2026', 'route', { over: 'Hành trình đang tiếp diễn', small: true, rail: [2, 5], actions: [light('Xem hành trình →')] }),
    card({ title: 'Lịch hẹn tiếp theo', aside: [quiet('Xem tất cả')] },
      appt({ day: '20', month: 'Tháng 09', lines: ['Chủ Nhật, 20/09 · 08:00', doctors[0].name + ' · Nám · tăng sắc tố'] })),
    rx({ sections: [{ title: 'DT-P001 · 6/9/2026', sub: 'Bác sĩ ' + doctors[0].name, lines: [{ name: 'Cicaderm Cream 40ml', use: 'Bôi lớp mỏng vùng cần chăm sóc · Sáng và tối · 14 ngày' }, { name: 'Fudareus B 15g', use: 'Bôi theo vùng bác sĩ đã dặn · Buổi tối · 7 ngày' }] }] })
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
  ])
];
