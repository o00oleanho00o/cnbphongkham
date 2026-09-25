# Pema KMP (Kotlin Multiplatform + Compose Multiplatform)

Bản viết lại app Pema (`flutter-template/`) bằng Kotlin Multiplatform, UI dùng chung Compose Multiplatform cho Android (và iOS — cần máy Mac để build).

## Cấu trúc
- `androidApp` — app Android (`com.pema.clinic.kmp`), `MainActivity`, icon, manifest.
- `composeApp` — `App.kt` (NavHost + bottom nav + guard vai trò), `AppContainer.kt` (tạo store/repository).
- `core/common` — `Routes` (id ASCII + tiêu đề tiếng Việt), `AppNavigator`, Ktor client, `ApiConfig`.
- `core/ui` — theme, `DetailScaffold`, `PemaCard`, `PemaBottomNav`, `LocalPhoto`, `moneyFormat`.
- `core/hardware` — `PlatformServices` (camera, ảnh, in A5, gọi/mở link/chia sẻ, rung, thông báo); bản Android thật, iOS, và `FakePlatformServices` cho test.
- `shared` — domain + data: session, patients, catalog, orders, billing, care (CareQueue, ReviewQueue), finance (Ktor).
- `feature/*` — workspace, schedule, patients, aftercare, orders, billing, care, finance. Feature không phụ thuộc nhau.

Quy ước chi tiết: [CONVENTIONS.md](CONVENTIONS.md).

## Build & chạy (Windows PowerShell)
```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'; cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat :androidApp:assembleDebug        # APK: androidApp\build\outputs\apk\debug\androidApp-debug.apk
.\gradlew.bat :androidApp:installDebug         # cài lên thiết bị đang cắm
.\gradlew.bat jvmTest                          # toàn bộ test commonTest trên JVM (40 test)
```
Hoặc mở thư mục `pema-kmp` trong Android Studio và chạy cấu hình `androidApp`.

Yêu cầu: Android SDK platform 37 (compileSdk 37, targetSdk 36, minSdk 24), JDK 17+ (JBR của Android Studio).

Tài chính gọi API `http://127.0.0.1:4174` (`BuildConfig.FINANCE_API`). Trên máy thật/emulator chạy trước: `adb reverse tcp:4174 tcp:4174`.

## Trạng thái
- Đã port toàn bộ màn hình của Flutter; build Android xanh, 40/40 test pass, đã smoke test 8 tab trên emulator (không crash).
- Camera native (TakePicture + FileProvider, xoay EXIF, 1600px/JPEG 85) đã viết nhưng **chưa kiểm thử trên máy thật**.
- iOS: target đã khai báo, code `iosMain` chưa được build (cần macOS + Xcode).
