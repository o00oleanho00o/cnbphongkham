# Quy ước pema-kmp (KMP + Compose Multiplatform)

Bản port của `flutter-template/` (Flutter) sang Kotlin Multiplatform.
- **Nghiệp vụ, chữ hiển thị, luồng màn hình**: code Flutter là nguồn chuẩn — port 1:1 (mọi field, nút, điều kiện bật/tắt, snackbar, dialog, sheet, hiển thị theo vai trò).
- **Giao diện**: design canvas `Pema App redesign canvas/Pema App.dc.html` (vẽ từ Flutter) là nguồn chuẩn — CSS của từng block (kích thước, padding, bo góc, màu, cỡ/độ đậm chữ) và ảnh tham chiếu từng màn (A1…H9).

## Module & quyền sở hữu

| Module | Nội dung | Chủ sở hữu |
|---|---|---|
| `core:common` | `Routes` (id ASCII + `Routes.titleOf(id)` = tên route Flutter, `finance(tab)`, `guide(title)`, `denied(title)`), `AppNavigator`, `AsyncUiState`, `ApiConfig`, Ktor `HttpClientFactory` | integration |
| `core:ui` | Design system dựng 1:1 từ CSS canvas: `PemaColors`, `PemaTheme`/`PemaType` (Be Vietnam Pro), `PemaIcon` (font Material Icons như Flutter `Icons.*`), block (`PemaHeading`, `PemaHero`, `PemaMetrics`, `PemaActions`, `PemaTile`, `PemaNotice`, `PemaPrimary`…), control (nút, field, dropdown, chip, checkbox), `DetailScaffold`, `PemaMainTopBar`, `PemaBottomNav`, sheet/dialog/snackbar, `LocalPhoto`, `moneyFormat`; jvmMain: harness chụp màn `shots/Shots.kt` | integration |
| `core:hardware` | `PlatformServices` (camera, images, printer, launcher, haptics, notifier), `LocalPlatformServices`, `FakePlatformServices` | hardware |
| `shared` | domain + state port 1:1 từ provider Flutter (session, catalog, patients, orders, billing, care, review queue, finance) | domain |
| `feature:<x>` | màn hình + ViewModel + block riêng của feature | agent của feature đó |
| `composeApp` | `App.kt` (NavHost, `_RouteGuard`, fallback Guide, snackbar, `PaymentAlerts` bọc navigator), `AppContainer.kt` | integration |
| `androidApp` | `MainActivity` (edge-to-edge), manifest, icon | integration |

Quy tắc:
- Feature chỉ dùng `core:*` và `shared`. Ngoại lệ như Flutter: `feature:workspace` nhúng `CareQueue` (`feature:care`) và `PatientSearch` (`feature:patients`); app shell gọi `PaymentAlerts` (`feature:finance`).
- Không sửa file ngoài phần mình sở hữu. Cần đổi `FeatureDeps`, `AppContainer`, `App.kt`, `Routes`, `core:ui` hay build file → ghi vào báo cáo, integration sẽ áp dụng.
- Mỗi feature xuất `fun NavGraphBuilder.<name>Graph(deps: FeatureDeps)` và đăng ký `composable(Routes.X)` cho các route của mình. Điều hướng luôn qua `deps.navigator.go(...)`: shell tự áp guard vai trò (màn "Tác vụ không thuộc không gian hiện tại…"), route lạ → Guide, `/finance` + trang con không bị guard (như Flutter).

## Thêm một màn hình
1. `feature/<x>/src/commonMain/kotlin/com/pema/clinic/feature/<x>/<Name>Screen.kt` — `@Composable` stateless nhận state + callback (để test chụp màn cấp state giả được), cộng một `…Route(vm)` bọc ViewModel.
2. ViewModel: `class <Name>ViewModel(...) : androidx.lifecycle.ViewModel()`, state là `StateFlow<...>` bất biến (`data class`), sự kiện là hàm. Tạo trong graph: `viewModel { <Name>ViewModel(deps) }`.
3. Đọc state bằng `collectAsStateWithLifecycle()`.
4. Tiêu đề: `DetailScaffold(title = Routes.titleOf(Routes.X))` — nút back lấy từ `LocalOnBack` do shell cấp.
5. Điều hướng: `deps.navigator.go(Routes.Y)` / `back()` / `openFinance(tab)`. Snackbar: `LocalPemaSnackbar.current.showSnackbar(...)`.
6. Phần cứng: `deps.platform` / `LocalPlatformServices.current`. Test dùng `FakePlatformServices`.

## Giao diện: bám canvas
- Chỉ dùng token trong `PemaColors` và kiểu chữ `PemaType.*` (đã gồm font Be Vietnam Pro). Không tự đặt màu/cỡ chữ khác canvas.
- Icon: `PemaIcon("tên_material")` — Flutter `Icons.x_outlined` → `PemaIcon("x")`, `Icons.x` → `PemaIcon("x", filled = true)`.
- Block riêng của feature (thẻ đơn, phiếu A5, hàng CSKH, thẻ tài chính…) dựng trong module feature theo CSS của block đó trong canvas.
- **Vòng so ảnh bắt buộc**: trong `jvmTest` của module gọi `shotVsCanvas("F4") { QuickOrderScreen(state, …) }` → `build/shots/F4-vs.png` = ảnh canvas (trái) | bản Compose (phải). Xem ảnh, sửa đến khi khớp. Ảnh tham chiếu lấy từ thư mục `-Dpema.refDir=` / biến môi trường `PEMA_REF_DIR` (mặc định: thư mục `ref` trong session).

## Màn web-only (canvas I/J/K)
- Logic theo `prototype/` (web), không phải Flutter; dữ liệu lấy từ `deps.clinicStore` (`shared/clinic`). Lệnh mới viết thành extension `ClinicStore.xxx()` trong `shared/clinic/<Feature>Commands.kt` dùng `transact` (lỗi = `ClinicError` với câu tiếng Việt của web).
- Quyền: `Session.allows` theo `staff-context.js` (`pages` + `capabilities`); nút cần quyền (clinical/billing/config) ẩn theo `session.staffContext().can(...)`.
- Không đổi hình của màn A–H khi thêm lối vào: thêm mục ở cuối màn, hoặc tham số callback tùy chọn (mặc định `null` = ẩn) để shot Flutter giữ nguyên.
- Tiêu đề route phải duy nhất trong `Routes.titles` (dùng cho `idOf`); nếu app bar cần trùng tên màn khác thì khai báo trong `appBarTitles` và dùng `Routes.appBarTitleOf`.

## Mobile-first & hiệu năng
- Thiết kế cho điện thoại dọc 360–412dp; vùng chạm ≥ 48dp; `LazyColumn`/`LazyRow` cho danh sách, có `key`.
- State `@Immutable`/`data class`, list là `List` bất biến; tránh tính toán nặng trong composable (dùng `remember`/`derivedStateOf` hoặc ViewModel).
- Không block main thread; IO qua `suspend` + `Dispatchers.Default`/Ktor.
- Chữ tiếng Việt giữ nguyên như Flutter. **File phải lưu UTF-8** (không dùng PowerShell `Set-Content`/`Out-File` mặc định — dùng tool create/edit hoặc `[IO.File]::WriteAllText(p, t, (New-Object Text.UTF8Encoding($false)))`).

## Bẫy Compose đã gặp trên thiết bị (JVM shot không bắt được)
- FAB trong `DetailScaffold`/`LazyDetailScaffold` đã được đệm theo thanh điều hướng hệ thống; đừng tự đặt FAB ngoài slot `floatingActionButton` (sẽ bị thanh điều hướng che).
- Emulator "Resizable" sau nhiều lần `am force-stop` có thể giữ focus input cũ → phím Back gây ANR "does not have a focused window" sau khi đóng sheet. Đó là lỗi trạng thái emulator (khởi động lại emulator là hết), không phải lỗi app — kiểm tra `dumpsys input` FocusRequests trước khi sửa code.
- Snackbar hiện trước/sau `back()` (lưu → quay lại): dùng `rememberPemaMessenger().show(msg)` (scope gốc trong `App.kt`, như Flutter `ScaffoldMessenger`). `rememberCoroutineScope()` của màn bị hủy khi pop → mất thông báo.
- State tab/bộ lọc/ô tìm kiếm của màn có thể bị route khác che: `rememberSaveable` (NavHost bỏ `remember` của màn bị che). Kiểu không vào được Bundle (data class, enum lồng) phải có `listSaver`/`mapSaver`, nếu không Android crash khi chuyển màn.
- Không lồng `verticalScroll` trong `PemaBottomSheet`/`ModalBottomSheet` (crash); chỉ một lớp cuộn.
- Bàn phím: `PemaScaffold` đã tự đệm theo IME (giống `resizeToAvoidBottomInset`) và manifest dùng `adjustResize`; không tự thêm `imePadding()` lần nữa.
- Tài nguyên `composeResources` trong module thư viện cần `androidResources.enable = true` (đã bật trong convention plugin).

## Lệnh Gradle (PowerShell, Windows)
```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'; cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat :feature:<x>:compileAndroidMain --console=plain -q     # biên dịch 1 feature
.\gradlew.bat :feature:<x>:jvmTest --console=plain -q                # test commonTest trên JVM
.\gradlew.bat :shared:jvmTest --tests "com.pema.clinic.shared.<area>*" --console=plain -q
.\gradlew.bat :androidApp:assembleDebug --console=plain -q           # APK (integration)
```
- Nhiều agent chạy song song: nếu gặp "Timeout waiting to lock" / "Gradle daemon busy" → đợi 30–60s rồi chạy lại.
- iOS target được khai báo nhưng không build được trên Windows — không cần chạy.
- Thiết bị: `E:\apdata\platform-tools\adb.exe`, điện thoại `08031a5f0407`, package `com.pema.clinic.kmp`.

## Thư viện có sẵn (commonMain)
Compose 1.12.1 (runtime/foundation/material3 1.9.0/ui/components-resources), navigation-compose 2.9.2, lifecycle-viewmodel-compose 2.10.0, coroutines, kotlinx-serialization-json, kotlinx-datetime (dùng `kotlin.time.Clock`/`Instant` + `@OptIn(ExperimentalTime::class)`), Ktor 3.6 (+ `ktor-client-mock` cho test). Test: `kotlin.test`.
