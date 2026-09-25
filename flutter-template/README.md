# Pema Native • template duyệt thiết kế

## Tài chính dùng API chung (PB02)

Chạy `python prototype/finance_server.py` từ gốc repo; trong Clinic mở Tài chính phòng khám hoặc chuông thông báo. Owner/kế toán/bác sĩ có projection riêng, dữ liệu SQLite chung với web. Đây là ngoại lệ đối với state phiên của PB01 bên dưới. [Nghiệp vụ/cách chạy](../docs/24_FINANCE_AND_PROCEDURE_FEES.md). Chưa có auth thật hoặc push nền.


Flutter Material 3 cho Android/iOS. Bản trình duyệt được build từ cùng Dart/widget tree để duyệt giao diện trước. Không dùng WebView bọc website.

## Chạy

```sh
flutter pub get
dart run build_runner build --delete-conflicting-outputs   # sinh các file *.g.dart của provider
flutter run -d chrome
flutter test
dart analyze   # gồm riverpod_lint (khai báo trong analysis_options.yaml)
flutter build web --base-href /native-preview/
```

Android: `flutter run -d <device-id>` sau khi có Android SDK/emulator. iOS cần macOS/Xcode. Bản duyệt browser chưa thay thế kiểm thử bàn phím, camera, safe-area và gesture trên điện thoại thật.

## Kiến trúc thư mục (feature-first)

Chia theo tính năng trước, chia tầng sau. Mỗi feature tự đóng gói data, domain và presentation của nó.

```text
lib/
├── main.dart                 # bootstrap: nạp catalog, ProviderScope + overrides
├── app.dart                  # PemaApp: MaterialApp, theme, router, PaymentAlerts
├── core/                     # dùng chung toàn app, không phụ thuộc feature
│   ├── network/              # ApiConfig (PEMA_FINANCE_API), httpClientProvider
│   ├── router/               # AppRoutes (tên route), AppRouter (route → screen + guard), context.openRoute
│   ├── theme/                # AppColors, AppTheme.light
│   ├── utils/                # money(), context.toast()
│   └── widgets/              # DetailScaffold, PemaBottomNav, block heading/tile/notice/primary...
└── features/
    ├── catalog/              # catalog bundle trong assets
    ├── session/              # vai trò, Clinic/Care, hồ sơ đang chọn
    ├── patients/             # PatientState theo hồ sơ, Patient 360, tư vấn, kế hoạch, buổi điều trị
    ├── orders/               # lên đơn, kiểm tra đơn, đơn thuốc, phiếu A5
    ├── billing/              # thu ngân, receipts
    ├── schedule/             # đặt lịch, chi tiết lịch, dịch vụ, bác sĩ & phòng
    ├── aftercare/            # chăm sóc tại nhà, gửi cập nhật, phản hồi, quyền riêng tư
    ├── customer_care/        # hàng chờ CSKH, liên hệ khách hàng
    ├── finance/              # tài chính dùng API chung (PB02)
    └── workspace/            # màn chính theo vai trò, hướng dẫn
        ├── data/
        │   ├── datasources/  # nói chuyện với nguồn dữ liệu: HTTP, asset, local storage
        │   └── repositories/ # *_repository_impl.dart: cài đặt interface của domain
        ├── domain/
        │   ├── models/       # model immutable + copyWith
        │   └── repositories/ # interface trừu tượng (abstract class)
        └── presentation/
            ├── providers/    # Riverpod @riverpod / @Riverpod(keepAlive: true) + *.g.dart
            ├── screens/      # mỗi route một màn
            └── widgets/      # widget riêng của feature
```

Quy ước:

- Luồng phụ thuộc: `screen → provider/notifier → repository (interface) → repository impl → datasource`. `domain/` không import Flutter UI hoặc `data/`. Tầng `data/` chỉ có ở feature thực sự có I/O (catalog, finance); feature chỉ có state trong phiên thì chỉ cần `domain/models` và `presentation/`.
- Provider viết bằng `riverpod_generator`. State cần sống suốt phiên dùng `@Riverpod(keepAlive: true)`; provider suy diễn (derived) dùng `@riverpod`. Sau khi sửa phải chạy `dart run build_runner build --delete-conflicting-outputs` và commit `*.g.dart`.
- Feature chỉ import `core/`, hoặc `domain`/`providers` của feature khác. Nối route với màn làm trong `core/router/app_router.dart`. Có hai ngoại lệ đã biết. `workspace` là shell ghép màn chính nên dùng widget của feature khác. Patient 360 mở trực tiếp `ProcedureForm` của finance, vì form cần tham số.
- Điều hướng: `context.openRoute(AppRoutes.x)` và `context.openFinance(tab)`. Guard `session.allows(route)` nằm trong `AppRouter.page`, screen không tự kiểm tra lại.
- Thêm tác vụ mới:
  1. Khai báo tên route trong `AppRoutes`.
  2. Tạo `features/<feature>/presentation/screens/<ten>_screen.dart`, dùng `DetailScaffold`.
  3. Thêm một nhánh vào `AppRouter._screen`.
  4. Nếu role nào được mở route này, cập nhật `Session.allows`.
  5. Thêm test trong `test/`.

### Quy tắc performance (Riverpod)

- **Chỉ watch đúng thứ cần**:
  - Dùng `ref.watch(p.select((s) => s.field))` khi chỉ cần một field. Nên trả về `bool`, `int` hoặc `String`, vì `select` so sánh bằng `==`, còn List/Map mới tạo luôn bị coi là khác.
  - Ví dụ: `_RouteGuard` chỉ nghe `session.allows(route)`; Patient 360 chỉ nghe điều kiện ghi nhận thủ thuật.
- **Rebuild nhỏ nhất có thể**: phần UI đổi thường xuyên tách thành `ConsumerWidget` riêng. Ví dụ: badge thông báo `_UnreadBadge` và tile doanh số `_FinanceSummaryTile` trong `workspace_screen.dart`, để polling tài chính không rebuild cả màn chính.
- **Không phát state trùng**:
  - `FinanceNotifier.refresh` bỏ qua response giống hệt lần trước (`DeepCollectionEquality`), nên poll 4 giây một lần không gây rebuild.
  - Provider dẫn xuất trả về List thì viết dạng class và override `updateShouldNotify` (xem `PatientOrders`).
- **`const`**: `analysis_options.yaml` bật nhóm lint `prefer_const_*`. `dart analyze` phải sạch.
- **autoDispose mặc định**: provider dẫn xuất dùng `@riverpod`. Chỉ state phiên, HTTP client và finance polling mới dùng `keepAlive: true`.
- **Tham số family ổn định**: tham số là `String`/`int` (ví dụ `patientStateProvider(id)`, `patientOrdersProvider(id)`). Không truyền List/Map tạo mới trong `build`.
- **Giữ dữ liệu cũ khi tải lại**: refresh không xóa `data` cũ, chỉ cập nhật khi có kết quả mới. Riêng khi đổi vai trò tài chính thì xóa có chủ đích, để không lộ projection của vai trò trước.
- **Đo, đừng đoán**:
  - Chạy `flutter run --profile -d <device-id>` và mở DevTools. Tab Performance xem frame; bật "Track widget rebuilds" để đếm rebuild.
  - Không đo performance trên bản debug.

## Build APK Android để cài thử

Kiểm tra điện thoại đã bật **USB debugging** và được Flutter nhận diện:

```powershell
flutter devices
```

Trong lúc phát triển, chạy trực tiếp để có hot reload:

```powershell
flutter run -d <device-id>
```

Để thử nghiệm gần với bản phát hành, ưu tiên APK `release`: chạy nhanh và nhỏ hơn
APK `debug`. Build riêng theo kiến trúc giúp giảm thêm dung lượng:

```powershell
cd E:\Desktop\cnbphongkham\flutter-template
flutter pub get
flutter build apk --release --split-per-abi
```

Các APK được tạo trong `build\app\outputs\flutter-apk\`:

| Kiến trúc thiết bị | File APK |
|---|---|
| ARM64, đa số điện thoại Android hiện nay | `app-arm64-v8a-release.apk` |
| ARM 32-bit, điện thoại cũ | `app-armeabi-v7a-release.apk` |
| x86-64, chủ yếu máy giả lập | `app-x86_64-release.apk` |

Xem kiến trúc của thiết bị trong kết quả `flutter devices`, sau đó cài APK phù
hợp. Ví dụ cho thiết bị `android-arm64`:

```powershell
& "E:\apdata\platform-tools\adb.exe" -s <device-id> install -r `
  "build\app\outputs\flutter-apk\app-arm64-v8a-release.apk"
```

Đường dẫn Android SDK trên máy khác có thể không phải `E:\apdata`. Tìm đường
dẫn ở dòng **Android SDK at** bằng `flutter doctor -v`, rồi dùng
`<android-sdk>\platform-tools\adb.exe`.

Nếu Android báo xung đột chữ ký (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`), gỡ bản
cũ trước khi cài lại. Lệnh này xóa cả dữ liệu ứng dụng:

```powershell
& "<android-sdk>\platform-tools\adb.exe" -s <device-id> uninstall com.example.pema_native_template
```

Không cần chạy `flutter clean` cho mỗi lần build; chỉ dùng khi Gradle/build cache
gặp lỗi. Cấu hình hiện tại ký bản `release` bằng debug key, chỉ phù hợp cài thử
nội bộ. Trước khi phát hành lên Google Play phải tạo release keystore riêng và
đổi `applicationId` khỏi `com.example.pema_native_template`.

## Hai không gian

- Clinic: Hôm nay / Lịch hẹn / Hồ sơ / Theo dõi / Thêm.
- Care: Trang chủ / Hành trình / Tin nhắn / Hồ sơ.
- Nút Clinic/Care ở header mở bottom sheet đổi không gian. Đây là bộ chuyển vai trò để duyệt, không phải xác thực.

## Mạch duyệt

1. Clinic → Hồ sơ → Patient 360 → check-in → tư vấn → kế hoạch → hoàn tất buổi.
2. Lịch hẹn → đặt/dời → chọn ngày/giờ → xác nhận. Slot 09:00 khóa minh họa xung đột; chưa phải scheduler đầy đủ.
3. Thêm → Lên đơn nhanh → tìm mã/tên trong 115 sản phẩm → kiểm tra đơn → số lượng/hướng dẫn/phân loại → nháp hoặc bác sĩ duyệt.
4. Care → Hồ sơ → Đơn thuốc & tư vấn: chỉ thấy đơn đã duyệt cho hồ sơ đang chọn.
5. Care → Gửi cập nhật → nội dung/ảnh mẫu/consent → Clinic Theo dõi → phản hồi → Care Tin nhắn.
6. Thu ngân → xem dư nợ theo đơn → xác nhận thu mẫu. Thu tiền không tự hoàn tất buổi.

## Tính nhất quán với web

Logo và font Be Vietnam Pro lấy từ assets hiện tại, kèm OFL. Primary #0B4F94, navy #083A6E, accent #3CAAE5, nền #F4F8FB. Giữ trạng thái draft/approved, phân loại PRESCRIPTION/CONSULTATION/UNRESOLVED từ catalog web; không phân loại thuốc theo tên.

Màn điện thoại dùng danh sách, màn con và bottom sheet. Patient 360 có các mục mở riêng thay vì bảng dày hoặc nhiều panel nối dài. Touch target theo Material; SafeArea, back navigation, date picker và form là widget native.

## Giới hạn vòng duyệt

State trong bộ nhớ của phiên template, chưa sync với localStorage web/backend. 46 hồ sơ snapshot tổng hợp, state lâm sàng/lịch/follow-up/cart tách theo patient, selection Care/Clinic riêng. Catalog sản phẩm là dữ liệu Excel được người dùng cung cấp, không phải dữ liệu sản phẩm giả lập.

Ảnh tiến triển/camera, AI, quyền riêng tư, cảnh báo nguồn lực và phiếu A5 là template. Chưa xuất PDF/in native, chưa gửi notification/payment thật, chưa RBAC, chưa lưu bền vững. Bố cục phiếu A5 để duyệt hai nhóm; không phải đầu ra in đã nghiệm thu.

Thiết kế chi tiết và mapping: [NATIVE-TEMPLATE.md](../docs/NATIVE-TEMPLATE.md).

## Tài liệu triển khai và kiểm tra

- [Runbook](../docs/21_NATIVE_RUNBOOK.md): SDK/PATH, fresh clone, `build-preview.ps1`, static server, đồng bộ catalog và xử lý lỗi preview.
- [Ma trận web/native](../docs/22_NATIVE_PARITY_AND_VALIDATION.md): hành vi thực tế, state theo patient và selection riêng, giới hạn thu ngân/A5/media, kiểm thử đã chạy và checklist còn mở.
- [Bản đồ tài liệu](../docs/README.md): Scope → Spec → Module Map → Architecture; [quy tắc đóng góp](../AGENT.md).

Build dành cho URL review dùng `./build-preview.ps1` (Flutter phải ở PATH), thay cho việc chỉ build mà chưa copy output. `prototype/native-preview/` không được commit. Validation hiện có gồm 20 test; cả bốn widget viewport đều height 844, chưa thay thế kiểm tra device hoặc toàn bộ flow Care.


Header nay chọn Chủ / Bác sĩ / CSKH / Kế toán / Care, mỗi vai trò có màn bắt đầu riêng. Care → Hồ sơ chọn nhóm tài khoản. CRM native là template độc lập web, chưa rule engine động. [Hướng dẫn mới](../docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md).
