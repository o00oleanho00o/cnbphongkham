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
