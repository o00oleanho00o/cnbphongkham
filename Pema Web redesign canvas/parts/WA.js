// WA · Khung & điều hướng. WA1 is the W3a proof screen (the owner shell); WA2-WA4 are filled by W3b-WA.
const WA = [
  // The shell is drawn by page() itself (sidebar by role, top bar, 390 top bar + tab bar); the content area is a placeholder here.
  page('WA1', 'Khung ứng dụng · Chủ phòng khám', WEB + 'app shell · sidebar 3 nhóm 13 mục, thanh trên (đường dẫn, tài khoản demo, tìm bệnh nhân, thông báo, đặt lại); danh sách tài khoản mở sẵn, liên kết "Đến nội dung chính" hiện khi focus', 'dashboard', [
    img('Vùng nội dung trang: mỗi trang vẽ ở nhóm WB–WH', { icon: 'web_asset', h: 320 })
  ], { state: true, pickerOpen: true, skip: true })
];
