// WB · Vận hành: tổng quan, hôm nay, lịch. WB1 is the W3a proof screen (dashboard); WB2-WB9 are filled by W3b-WB.
const WB = [
  page('WB1', 'Tổng quan', WEB + 'dashboard · bố cục như app I1/A1 ở cỡ web; web có thêm KPI "Quá ngày dự kiến", "Liệu trình bỏ dở" và hai khối "Hiệu quả CSKH", "Vòng đời khách hàng"; tên và số liệu là dữ liệu tổng hợp', 'dashboard', [
    pageHead('Chào buổi sáng, BS. Tâm', 'Vận hành hôm nay và chăm sóc khách hàng · mốc demo 20/09/2026', [secondary('Lịch hôm nay →'), primary('Mở CSKH hôm nay')], 'Pema · chăm sóc xuyên suốt'),
    kpis(
      kpi('Lịch hôm nay', '12', '', { actions: [quiet('Mở tiếp đón →')] }),
      kpi('Đã đến / đang chờ', '3', '', { unit: '/ 3', actions: [quiet('Bàn giao phòng khám →')] }),
      kpi('Vắng hẹn', '1', '', { actions: [secondary('Xử lý vắng hẹn')] }),
      kpi('Phát sinh hôm nay', money(13500000), '', { actions: [quiet('Hóa đơn, không phải thực thu →')] })),
    kpis(
      kpi('Khách cần CSKH', '10', '12 việc đến hạn', { chev: true }),
      kpi('Quá ngày dự kiến', '2', 'Cần hỗ trợ chọn lịch', { chev: true }),
      kpi('Nguy cơ mất khách', '3', 'Quá hạn hoặc bỏ dở', { chev: true }),
      kpi('Liệu trình bỏ dở', '1', 'Còn buổi, >45 ngày', { chev: true })),
    grid('minmax(0,1.65fr) minmax(300px,1fr)',
      panel('Ưu tiên chăm sóc', 'Từ dữ liệu khám và lịch hẹn, có người phụ trách', [secondary('Tất cả →')],
        table(['Khách hàng', ['Việc tiếp theo', '1.2fr'], 'Phụ trách', ['', '88px']], people.slice(0, 5).map((x, i) => [
          [lnk(x.name), sm(x.id)], [txt(x.groupLabel), sm((14 + i) + '/9/2026')], 'CSKH Mai Anh', [secondary('Xử lý')]
        ]))),
      panel('Hiệu quả CSKH', 'Kết quả thực từ hoạt động đã lưu', [],
        facts(['Việc đã hoàn tất', '4'], ['Liên hệ thành công', '75%', { sub: '3/4 lần liên hệ' }], ['Lịch đặt sau CSKH', '2'], ['Đã quay lại thực tế', '1'], ['Việc quá hạn', '5']),
        secondary('Xem nhật ký kết quả'),
        notice('Khách đặt lịch chưa được tính là đã quay lại. Chỉ ghi nhận quay lại khi check-in sau CSKH.'))),
    panel('Vòng đời khách hàng', 'Một hồ sơ, nhiều lần chăm sóc', [],
      grid(5, secondary('3 Khách mới', { full: true }), secondary('2 Khách quay lại', { full: true }), secondary('9 Đang điều trị', { full: true }), secondary('1 Lâu chưa quay lại', { full: true }), secondary('1 Đã quay lại sau CSKH', { full: true })))
  ])
];
