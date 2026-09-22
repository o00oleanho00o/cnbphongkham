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
