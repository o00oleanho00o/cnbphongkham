# Vận hành template Flutter

> **Hiện trạng Mobile CRM02 (22/09/2026):** tài chính trong Clinic shell, 46 hồ sơ mẫu/10 nhóm chăm sóc; Flutter phân workspace và tách state theo patient. Các mô tả state chung hoặc chưa có native CRM phía dưới là baseline trước bản mở rộng này. Xem [hướng dẫn cập nhật](25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).


Cập nhật 22/09/2026. Áp dụng cho bản duyệt thiết kế; không triển khai hệ thống lâm sàng thật.

## Chọn đúng ứng dụng

| URL tại localhost:4173 | Công nghệ / dữ liệu |
|---|---|
| `/clinic-web/`, `/patient-mobile/` | HTML/JS, chia sẻ localStorage cùng origin/profile |
| `/native-review/` | Trang HTML chứa khung duyệt Flutter, không tự build app |
| `/native-preview/` | Flutter Web build từ Dart; state Riverpod trong bộ nhớ, độc lập web |

Khung review có 390×844, 360×800, 430×932 và 768×1024. Đây là logical viewport để duyệt, không mô phỏng đầy đủ OS/bàn phím/gesture thiết bị.

## Fresh clone và build trên Windows

Máy hiện tại đã dùng Flutter 3.47.5 / Dart 3.13.4 tại `C:\Users\email\.cache\pema-flutter-sdk`. Đường dẫn này là cấu hình máy, không phải dependency được commit. Trên máy khác cài Flutter và kiểm tra `flutter --version`, `flutter doctor`.

Từ thư mục gốc repository, trong PowerShell:

```powershell
# Chỉ cần dòng PATH này nếu dùng SDK đã có trên máy hiện tại.
$env:Path = "C:\Users\email\.cache\pema-flutter-sdk\bin;$env:Path"
Set-Location flutter-template
flutter pub get
dart run build_runner build
dart analyze   # gồm riverpod_lint; flutter analyze không chạy plugin
flutter test --reporter expanded
./build-preview.ps1
Set-Location ../prototype
python -m http.server 4173 --bind 127.0.0.1
```

Script chạy pub get, `dart run build_runner build`, `flutter build web --base-href /native-preview/ --no-web-resources-cdn`, rồi copy `build/web/*` sang `prototype/native-preview/`. Build output bị git-ignore; fresh clone phải build trước khi mở [Native review](http://127.0.0.1:4173/native-review/). Không mở bằng file://, không sửa JS đã compile để thay hành vi app.

Khi sửa provider trong `lib/state/`, chạy `dart run build_runner watch` song song để cập nhật `*.g.dart`; file sinh ra được commit để fresh clone chạy test ngay. Khi phát triển có thể dùng `flutter run -d chrome` trong `flutter-template`; đây là dev server riêng, không tự cập nhật preview ở cổng 4173. Sau sửa Dart/assets phải build lại để duyệt URL 4173.

Android cần Android SDK và device/emulator: `flutter devices`, `flutter run -d <device-id>`. iOS cần macOS/Xcode. Các lệnh này là hướng dẫn tiếp theo, chưa phải bằng chứng đã chạy trên thiết bị.

## Cập nhật catalog

Nguồn là workbook `data/danhsach.xlsx`, không chỉnh bundle Flutter tách biệt. Chạy từ gốc repo:

```powershell
python prototype/import-product-catalog.py
python prototype/import-product-catalog.py --check
Copy-Item prototype/shared/product-catalog.json flutter-template/assets/products.json
Get-FileHash prototype/shared/product-catalog.json, flutter-template/assets/products.json -Algorithm SHA256
```

Hai hash phải bằng nhau. Snapshot hiện tại: 115 dòng, 30 PRESCRIPTION, 78 CONSULTATION, 7 UNRESOLVED. Không tự suy loại thuốc từ tên; giữ dòng chưa phân loại để review. Nếu workbook thay đổi hợp lệ, cập nhật count expectation trong test/tài liệu theo dữ liệu mới, không ép import giữ số cũ. Chạy analyze/test/build lại sau cập nhật bundle.

## Reset và xử lý sự cố

| Hiện tượng | Kiểm tra / xử lý |
|---|---|
| Review có khung nhưng app 404 | Build preview; xác nhận `prototype/native-preview/index.html` tồn tại và server chạy từ `prototype` |
| Màn trắng hoặc asset 404 | Kiểm tra base-href `/native-preview/`, copy đủ build/web, xem console/network và hard refresh |
| Xem code mới nhưng preview cũ | Build/copy lại; dev server Flutter khác static preview |
| Cổng 4173 đã dùng | Mở URL kiểm tra server hiện có; không khởi động trùng hoặc dừng tiến trình không rõ chủ sở hữu |
| Dữ liệu mất khi tải lại | Đúng giới hạn memory store; không dùng browser refresh để kiểm tra persistence |
| Web và Flutter khác trạng thái | Hai runtime độc lập; không có bridge/API sync |
| Đổi bệnh nhân thấy cùng lịch/tin nhắn | Build lại preview; state đã tách theo patient, chạy mobile_roles_test để kiểm regression |
| Thiếu Flutter trong PATH | Thêm SDK hợp lệ vào PATH; kiểm tra `flutter --version` trước build |

## Bàn giao

Ghi version SDK, commit, lệnh/kết quả kiểm tra, viewport và route thực sự đã xem. Lưu chứng cứ mới riêng, không ghi đè lịch sử web để gọi là bằng chứng native. [Ma trận kiểm thử](22_NATIVE_PARITY_AND_VALIDATION.md) và [mapping màn](NATIVE-TEMPLATE.md) là checklist bàn giao.


## Bổ sung tài chính PB02

[Module tài chính và tiền thủ thuật](24_FINANCE_AND_PROCEDURE_FEES.md) dùng API :4174/SQLite chung cho web và Flutter. Role là mô phỏng, thông báo foreground; không áp mô tả memory-only của PB01 cho PB02. Chạy API riêng, không coi HTTP local là triển khai production.


Bundle tài khoản mẫu: chạy `node prototype/export-native-patients.cjs` trước build khi fixture CRM thay đổi; `--check` kiểm snapshot. Không xuất từ localStorage có dữ liệu thử.
