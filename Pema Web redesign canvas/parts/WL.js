// WL · Đăng nhập, khung ứng dụng Next.js và Tin nhắn mẫu đã duyệt (Next.js only, W2 step W10). Owner: W10 director.
const NXW = 'Next.js › ';
const WL = [
  bare('WL1', 'Đăng nhập CSKH', NXW + '/login · trang đăng nhập, không có khung ứng dụng · chưa nhập gì: nút "Đăng nhập" tắt',
    [card({}, img('Pema clinic & spa', { icon: 'spa', h: 72 }), h2('Đăng nhập CSKH', 'Chăm sóc khách hàng và trợ lý AI'),
      input('Email', '', { w: 0 }), input('Mật khẩu', '', { suf: 'visibility' }), iconBtn('visibility', { aria: 'Hiện nội dung', sm: true }), primary('Đăng nhập', { dis: true, full: true }))]),
  npage('WL10', 'Khung · menu quản trị (chủ phòng khám)', NXW + '(app shell) · sidebar theo quyền, thanh trên, nội dung của /dashboard', '/dashboard', [
    pageHead('Tổng quan', 'Hôm nay · 20/09/2026', [secondary('Mở điều phối lịch', { ric: 'arrow_forward' })]),
    h2('Lịch hẹn theo trạng thái', 'Trạng thái hiện tại của các lịch bắt đầu trong kỳ')
  ], { nx: 'owner', state: true })
];
