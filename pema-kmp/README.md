# Pema KMP (Kotlin Multiplatform + Compose Multiplatform)

Bản viết lại app Pema (`flutter-template/`) bằng Kotlin Multiplatform, UI dùng chung Compose Multiplatform cho Android (và iOS — cần máy Mac để build).

## Cấu trúc
- `androidApp` — app Android (`com.pema.clinic.kmp`), `MainActivity` (edge-to-edge, `adjustResize`), icon, manifest.
- `composeApp` — `App.kt`: shell giống Flutter `PemaApp`/`AppRouter` (NavHost, guard vai trò → màn "không có quyền", route lạ → Hướng dẫn, `PaymentAlerts`, snackbar gốc `PemaMessenger`); `AppContainer.kt` (tạo store/repository).
- `core/common` — `Routes` (id ASCII + tiêu đề tiếng Việt, route có tham số `finance?tab=`, `guide`, `denied`), `AppNavigator`, Ktor client, `ApiConfig`.
- `core/ui` — design system dựng 1:1 từ canvas `Pema App redesign canvas/Pema App.dc.html`: màu/typography (Be Vietnam Pro), icon Material Symbols (font), block (hero, tile, metric, notice…), control, `DetailScaffold`/`PemaScaffold` (tránh bàn phím như Flutter `resizeToAvoidBottomInset`), `PemaBottomNav`, sheet/dialog; harness chụp màn hình JVM `shots/Shots.kt`.
- `core/hardware` — `PlatformServices` (camera, ảnh, in A5, gọi/mở link/chia sẻ, rung, thông báo); bản Android thật, iOS, và `FakePlatformServices` cho test.
- `shared` — domain + data port 1:1 từ Flutter: session, patients, catalog (46 hồ sơ, 115 sản phẩm), orders, billing, care (CareQueue, ReviewQueue), finance (Ktor). Thêm `shared/clinic`: mô hình dữ liệu web (`prototype/shared/data.js`, `operations-data.js`, `crm-*.js`, `care-finance.js`, `staff-context.js`) — `ClinicStore` với lịch hẹn/phòng/dịch vụ, theo dõi, CRM, hóa đơn, Patient 360 đầy đủ; seed khớp 46 hồ sơ của catalog (test parity).
- `feature/*` — workspace, schedule, patients, aftercare, orders, billing, care, finance, **operations** (mới: I1–I4, I8, I9). Mỗi feature có `commonTest` (logic) và `jvmTest` (ảnh so sánh với canvas). Ngoại lệ phụ thuộc: workspace nhúng `PatientSearch` (patients) và `CareQueue` (care), như Flutter. Màn web-only nằm trong file riêng: `patients/ClinicToolsScreens.kt` (I5, I7, I12), `patients/Patient360Clinical.kt` (J1–J5), `patients/Patient360Admin.kt` (J6–J11), `aftercare/FollowUpInbox.kt` (I6), `billing/InvoiceCashier.kt` (I10–I11), `billing/PatientDocuments.kt` (K2), `care/CareRecordScreen.kt` (I13), `schedule/PatientAppointments.kt` (K1); K3 là tab Hành trình của workspace.

Quy ước chi tiết: [CONVENTIONS.md](CONVENTIONS.md).

## Build & chạy (Windows PowerShell)
```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'; cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat :androidApp:assembleDebug        # APK: androidApp\build\outputs\apk\debug\androidApp-debug.apk
.\gradlew.bat :androidApp:installDebug         # cài lên thiết bị đang cắm
.\gradlew.bat jvmTest                          # logic + ảnh so sánh canvas trên JVM (192 test)
```
Hoặc mở thư mục `pema-kmp` trong Android Studio và chạy cấu hình `androidApp`.

Yêu cầu: Android SDK platform 37 (compileSdk 37, targetSdk 36, minSdk 24), JDK 17+ (JBR của Android Studio).

Tài chính gọi API `http://127.0.0.1:4174` (`BuildConfig.FINANCE_API`). Chạy API từ gốc repo: `python prototype/finance_server.py`, rồi trên máy thật/emulator: `adb reverse tcp:4174 tcp:4174`. Khi API tắt, màn tài chính hiện lỗi + "Thử lại".

## Spec/prompt từng màn (`design-specs/`, MCP `pema-design`)
Mỗi màn A1…K3 có spec lưu sẵn ở [`design-specs/screens/<ID>.md`](../design-specs/README.md): nguồn logic (Flutter/web), route + file + composable KMP, bố cục block → Compose, câu bắt buộc, quy tắc, khác biệt được chấp nhận, bẫy đã gặp và prompt. Đọc spec thay vì đọc lại web/canvas; qua MCP `pema-design` (đăng ký sẵn trong `.mcp.json` / `.vscode/mcp.json`) dùng `get_screen`, `get_screen_image`, prompt `port_screen`. Điều học được khi chuyển đổi ghi vào `design-specs/notes.json` (hoặc tool `record_note`). Task `designSpecs` tự sinh lại sau `jvmTest`.

## So sánh với design canvas
`jvmTest` của mỗi feature (và `composeApp` cho màn F17 chặn quyền) render màn hình 390×844dp (×2) và ghép cạnh ảnh canvas: `<module>/build/shots/<ID>-vs.png` (trái canvas, phải KMP). Khác biệt được chấp nhận: logo Pema thật thay chữ "pema" placeholder, dữ liệu mẫu thật (46 hồ sơ) thay dữ liệu minh họa của canvas.

### Ảnh chụp design (`design-ref/`) — tự động, không cần chụp tay
Ảnh canvas dùng để so sánh được tạo từ `Pema App redesign canvas/Pema App.dc.html` bằng script [`canvas-shots.cjs`](../.claude/skills/pema-canvas-to-kmp-compose/scripts/canvas-shots.cjs) và lưu ở `pema-kmp/design-ref/<ID>.png` (A1…K3, mỗi ảnh là một màn kèm khung điện thoại, 780×1690 px).

**Cài một lần** (máy mới):
```powershell
cd E:\Desktop\cnbphongkham\design-viewer; npm install
npx -y playwright@latest install chromium
```

**Dùng hằng ngày:** chỉ cần chạy test như bình thường — `jvmTest` tự chạy task `canvasRefs` trước:
```powershell
.\gradlew.bat jvmTest                       # tự tạo/cập nhật design-ref rồi tạo các ảnh *-vs.png
.\gradlew.bat :feature:orders:jvmTest       # một module: ảnh ở feature\orders\build\shots\
```
- Canvas không đổi → bỏ qua ngay (Gradle up-to-date; script kiểm tra mã băm trong `design-ref/manifest.json`, ~0,1 giây).
- Sửa `Pema App.dc.html` → lần chạy sau tự chụp lại cả 82 màn (~25 giây). Script tự bật design-viewer (cổng 4180) nếu chưa chạy và tự tắt khi xong.

**Chạy tay khi cần:**
```powershell
.\gradlew.bat canvasRefs                                                        # như trên, không chạy test
cd E:\Desktop\cnbphongkham
node .claude\skills\pema-canvas-to-kmp-compose\scripts\canvas-shots.cjs --force        # chụp lại tất cả
node .claude\skills\pema-canvas-to-kmp-compose\scripts\canvas-shots.cjs --only=I1,J3   # chỉ vài màn
node .claude\skills\pema-canvas-to-kmp-compose\scripts\canvas-shots.cjs --out=D:\ref   # thư mục khác
```
- `CANVAS_URL=http://...` dùng design-viewer đang chạy ở địa chỉ khác; `PEMA_REF_DIR` cho test đọc ảnh từ thư mục khác.
- Thiếu Node/Playwright/design-viewer: task chỉ cảnh báo, test vẫn chạy nhưng không có ảnh `-vs.png` (log in `shotVsCanvas: no canvas reference …`).
- `design-ref/` nằm trong `.gitignore` (khoảng 9 MB, tạo lại được) — không commit.
- Muốn tự xuất ảnh một màn / một nhóm / cả canvas bằng tay (PNG/JPG, 1x–3x): dùng nút **Xuất ảnh** trong Design Viewer — xem [README gốc › Design Viewer](../README.md#design-viewer--xem-design-canvas).

**Thêm ảnh so sánh cho màn mới:** trong `jvmTest` của module gọi
```kotlin
@Test
fun f4QuickOrder() {
    shotVsCanvas("F4") { QuickOrderScreen(state = …) }
}
```
rồi mở `<module>\build\shots\F4-vs.png` để đối chiếu với canvas.

## Trạng thái
- Đã port toàn bộ 82 màn của canvas: 55 màn A–H (Flutter, 1:1) và 27 màn I/J/K (bổ sung từ web: logic theo `prototype/`, giao diện theo canvas). Mỗi mã màn đều có ảnh so sánh `-vs.png`; build Android xanh, 192/192 test pass.
- Lối vào màn web: tab "Thêm"/màn chính của từng vai trò có mục "Vận hành phòng khám" (lọc theo quyền web `staff-context.js`); Patient 360 có mục "Patient 360 đầy đủ"; C6 có "Ghi nhận CSKH đầy đủ"; F13/F14 mở Chỉnh dịch vụ/Khóa phòng (chỉ chủ phòng khám); Trang chủ Care → Lịch hẹn (K1), Hồ sơ Care → Tài liệu & hóa đơn (K2).
- Khác biệt có chủ đích so với canvas: dữ liệu mẫu thật của web (P001 Nguyễn Minh Linh, ngày 20/9/2026) thay tên/ngày minh họa; tab Hành trình (K3) giữ 4 mục của Flutter E2 và thêm dòng thời gian + câu "tiến độ số buổi, không phải mức cải thiện da" của web.
- Dữ liệu demo chỉ nằm trong bộ nhớ tiến trình (`AppStores`, như tab web): xoay máy/quay về từ camera vẫn giữ; tắt hẳn app là về seed ban đầu.
- Đã chạy trên emulator Android 14: Clinic (5 tab), Bác sĩ, CSKH, Kế toán (2 tab), Pema Care (4 tab); đặt lịch, lên đơn, Patient 360, gửi cập nhật → bác sĩ phản hồi, tài chính 4 tab + bảng giá với API thật; màn web: tiếp đón check-in, đặt lịch hẹn, điều phối theo ngày, thu tiền (sheet), Patient 360 J1–J11 (lưu kế hoạch, nhắn tin → hiện ở Tin nhắn của người bệnh), CSKH C6 → I13 → đặt lịch, Care K1 xác nhận lịch, K2, K3; không crash.
- Camera & ảnh (Android; đã chạy trên emulator và điện thoại thật Xiaomi M2003J15SC, Android 12/MIUI, camera MIUI + photo picker Google — G2 → F10, J5 chụp/chọn ảnh, bỏ/chụp lại/hủy, app bị kill khi đang mở camera vẫn nhận lại ảnh):
  - Chụp bằng app camera hệ thống (`TakePicture` + FileProvider) hoặc chọn ảnh có sẵn bằng photo picker của Android — không cần quyền CAMERA/bộ nhớ. Ảnh được xoay theo EXIF, thu về cạnh dài 1600px, JPEG 85, bỏ toàn bộ EXIF/GPS, lưu ở `cache/photos/`. Khi tiến trình khởi động, ảnh của lần chạy trước bị xóa, trừ ảnh nháp được khôi phục cùng màn hình. Ảnh đã gửi hoặc lưu phải được báo bằng `CameraService.markSaved`, vì dữ liệu demo chứa nó mất khi tiến trình tắt.
  - Dùng ở: G2 Gửi cập nhật (người bệnh) → F10 Phản hồi và G5 Ảnh tiến triển (phòng khám); J5 Ghi buổi điều trị (ảnh mốc, cần đồng ý ảnh; lưu không ảnh → tạo việc "Thiếu ảnh mốc") → I7 Ảnh trước / sau hiện ảnh thật theo góc chụp, có "So sánh trượt" khi có 2 ảnh.
  - Android hủy/tạo lại activity khi đang mở camera (xoay máy, thiếu RAM): ảnh vẫn được nhận lại (`CameraService.recoveredPhotos()`), bản nháp G2 giữ chữ + ảnh; ảnh chưa gửi chỉ bị xóa khi đóng màn (`OnScreenCleared`).
  - Dữ liệu demo nằm trong `AppStores` (theo tiến trình app): xoay máy hay quay về từ camera không làm mất phiên làm việc. Nếu Android kill tiến trình khi đang ở camera, màn đang mở, bản nháp và không gian làm việc (vai trò, hồ sơ đang chọn) được khôi phục; dữ liệu demo đã sửa thì về seed.
  - iOS: `IosPlatformServices` có chụp ảnh (chưa build); chọn ảnh chưa có trên iOS.
- iOS: target đã khai báo, code `iosMain` chưa được build (cần macOS + Xcode).
