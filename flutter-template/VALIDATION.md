# Validation • 22/09/2026

- Flutter 3.47.5 / Dart 3.13.4, Windows host.
- `flutter analyze`: No issues found.
- `flutter test --reporter expanded`: 6 tests passed.
- Catalog/state: 115 products, 7 UNRESOLVED, missing usage blocks approval, draft-to-approved replaces original order, patient order/receipt isolation.
- Widget layout: home plus 12 detail routes, populated order/cart at 360, 390, 430, 768 logical pixels; no Flutter exceptions/overflow reported.
- Widget interaction: catalog item tap updates cart; review button opens order review.
- `flutter build web --base-href /native-preview/ --no-web-resources-cdn`: succeeded.
- Visual browser review: Clinic home and Care home at 390×844 in native-review frame; role switch bottom sheet verified. Local assets load and content remains above bottom navigation.
- `git diff --check`: no whitespace errors.

Limits: browser preview and widget tests only. No Android/iOS physical device, native camera, print/PDF or production integration verification. Build emits a CupertinoIcons font warning from adaptive framework paths; this template uses Material outlined icons, visually checked in the reviewed screens.


## PB02 — 22/09/2026

Flutter analyze PASS; 12 tests PASS (6 baseline + 2 finance controller + 4 viewport finance screens/forms); web build PASS, copied to preview. Browser verified finance overview and notifications for 100.000 from finance web and 50.000 from legacy cashier via shared API. Evidence: [finance validation](../demo-assets/screenshots/finance/validation.json). Physical devices/background push not tested or configured.


## Mobile CRM02 và CSKH redesign — 22/09/2026

Flutter analyze: No issues found; 17 tests PASS, build preview PASS. Browser kiểm 360×800, 390×844, 430×932, 768×1024: khách đầu y=334; filter D3 → hồ sơ P038 → lưu liên hệ → Đã liên hệ chạy được, không pageerror. [Tổng hợp bằng chứng](../demo-assets/screenshots/mobile-crm02/validation-summary.json), [native browser](../demo-assets/screenshots/mobile-crm02/native-review-results.json). Chưa kiểm thiết bị thật.


## Riverpod state layer — 23/09/2026

`DemoStore`/`FinanceController` thay bằng provider `riverpod_generator` 4.0.9 (`flutter_riverpod` 3.4.3) trong `lib/state/`; hành vi giữ nguyên. `flutter analyze`: No issues found. `flutter test`: 18 PASS (17 cũ viết lại theo ProviderContainer + 1 mới: thông báo thanh toán owner vẫn hiện khi đang mở màn con, vì Riverpod 3 tạm dừng listener của route bị che). `build-preview.ps1` (có build_runner) PASS. Browser 390×844 trên preview + finance API: owner home có doanh số API; thêm H002 hai lần gộp 1 dòng/SL 2; giảm/tăng SL; bác sĩ duyệt DN-1 đúng hướng dẫn; thu ngân thu đủ 11.000 ₫; Care P001 chỉ thấy đơn đã duyệt; đổi sang BS. Mai chọn hồ sơ của BS. Mai; CSKH D3 → P038 → Đã liên hệ. Không pageerror. Chưa kiểm thiết bị thật.

`riverpod_lint` 3.1.9 bật qua `plugins:` trong `analysis_options.yaml`. `dart analyze`: No issues found; file thử vi phạm (runApp thiếu ProviderScope, BuildContext trong provider) được báo `missing_provider_scope` và `avoid_build_context_in_providers`, sau đó đã xóa. `flutter analyze` không chạy plugin nên dùng `dart analyze` cho kiểm tra này.
