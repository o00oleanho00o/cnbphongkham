// WI2 · Patient Mobile web, second part (merged into group WI by the build). Owner: W6c-WI-2 (send, messages, docs, profile, privacy, every modal and state).
const WI2 = [
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
  ], { state: true, toast: 'Đã xác nhận lịch hẹn' })
];
