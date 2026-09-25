# Pema KMP (Kotlin Multiplatform + Compose Multiplatform)

Bản viết lại app Pema (`flutter-template/`) bằng Kotlin Multiplatform, UI dùng chung Compose Multiplatform cho Android (và iOS — cần máy Mac để build).

## Cấu trúc
- `androidApp` — app Android (`com.pema.clinic.kmp`), `MainActivity` (edge-to-edge, `adjustResize`), icon, manifest.
- `composeApp` — `App.kt`: shell giống Flutter `PemaApp`/`AppRouter` (NavHost, guard vai trò → màn "không có quyền", route lạ → Hướng dẫn, `PaymentAlerts`, snackbar gốc `PemaMessenger`); `AppContainer.kt` (tạo store/repository).
- `core/common` — `Routes` (id ASCII + tiêu đề tiếng Việt, route có tham số `finance?tab=`, `guide`, `denied`), `AppNavigator`, Ktor client, `ApiConfig`.
- `core/ui` — design system dựng 1:1 từ canvas `Pema App redesign canvas/Pema App.dc.html`: màu/typography (Be Vietnam Pro), icon Material Symbols (font), block (hero, tile, metric, notice…), control, `DetailScaffold`/`PemaScaffold` (tránh bàn phím như Flutter `resizeToAvoidBottomInset`), `PemaBottomNav`, sheet/dialog; harness chụp màn hình JVM `shots/Shots.kt`.
- `core/hardware` — `PlatformServices` (camera, ảnh, in A5, gọi/mở link/chia sẻ, rung, thông báo); bản Android thật, iOS, và `FakePlatformServices` cho test.
- `shared` — domain + data port 1:1 từ Flutter: session, patients, catalog (46 hồ sơ, 115 sản phẩm), orders, billing, care (CareQueue, ReviewQueue), finance (Ktor).
- `feature/*` — workspace, schedule, patients, aftercare, orders, billing, care, finance. Mỗi feature có `commonTest` (logic) và `jvmTest` (ảnh so sánh với canvas). Ngoại lệ phụ thuộc: workspace nhúng `PatientSearch` (patients) và `CareQueue` (care), như Flutter.

Quy ước chi tiết: [CONVENTIONS.md](CONVENTIONS.md).

## Build & chạy (Windows PowerShell)
```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'; cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat :androidApp:assembleDebug        # APK: androidApp\build\outputs\apk\debug\androidApp-debug.apk
.\gradlew.bat :androidApp:installDebug         # cài lên thiết bị đang cắm
.\gradlew.bat jvmTest                          # logic + ảnh so sánh canvas trên JVM (107 test)
```
Hoặc mở thư mục `pema-kmp` trong Android Studio và chạy cấu hình `androidApp`.

Yêu cầu: Android SDK platform 37 (compileSdk 37, targetSdk 36, minSdk 24), JDK 17+ (JBR của Android Studio).

Tài chính gọi API `http://127.0.0.1:4174` (`BuildConfig.FINANCE_API`). Chạy API từ gốc repo: `python prototype/finance_server.py`, rồi trên máy thật/emulator: `adb reverse tcp:4174 tcp:4174`. Khi API tắt, màn tài chính hiện lỗi + "Thử lại".

## So sánh với design canvas
`jvmTest` của mỗi feature (và `composeApp` cho màn F17 chặn quyền) render màn hình 390×844dp (×2) và ghép cạnh ảnh canvas: `<module>/build/shots/<ID>-vs.png` (trái canvas, phải KMP). Ảnh canvas lấy từ `-Dpema.refDir=…` hoặc biến môi trường `PEMA_REF_DIR`. Khác biệt được chấp nhận: logo Pema thật thay chữ "pema" placeholder, dữ liệu mẫu thật (46 hồ sơ) thay dữ liệu minh họa của canvas.

## Trạng thái
- Đã port toàn bộ màn hình và logic của Flutter theo canvas: 55 màn nhóm A–H đều có ảnh so sánh khớp canvas; build Android xanh, 107/107 test pass.
- Nhóm I, J, K của canvas (27 màn "bổ sung từ web · chưa có trong Flutter") **chưa port** — nằm ngoài phạm vi chuyển 1:1 từ Flutter.
- Đã chạy trên emulator Android 14: Clinic (5 tab), Bác sĩ, CSKH, Kế toán (2 tab), Pema Care (4 tab); đặt lịch, lên đơn, Patient 360, gửi cập nhật → bác sĩ phản hồi, tài chính 4 tab + bảng giá với API thật; không crash.
- Camera native (TakePicture + FileProvider, xoay EXIF, 1600px/JPEG 85) đã viết nhưng **chưa kiểm thử trên máy thật** (hoãn theo yêu cầu).
- iOS: target đã khai báo, code `iosMain` chưa được build (cần macOS + Xcode).
