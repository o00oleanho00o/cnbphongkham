---
name: pema-canvas-to-kmp-compose
description: Chuyển màn hình Pema từ Flutter/web và design canvas sang KMP + Compose Multiplatform theo 1:1 về nghiệp vụ lẫn hình ảnh. Dùng khi được yêu cầu port Flutter sang KMP/Compose, dựng màn Compose theo Pema App canvas, hoặc kiểm tra độ khớp KMP với canvas. Không dùng để sửa canvas; dùng pema-web-to-canvas khi cần cập nhật canvas.
---

# Pema canvas → KMP + Compose Multiplatform

KMP app nằm ở `pema-kmp/`; Flutter nguồn ở `flutter-template/`; canvas nguồn giao diện ở `Pema App redesign canvas/Pema App.dc.html`.

Mục tiêu là **port 1:1**, không phải dựng một UI “tương tự”:

| Nguồn | Quyết định |
|---|---|
| Flutter `flutter-template/lib/` | nghiệp vụ, dữ liệu, điều kiện theo vai trò, field, nút, trạng thái, route, sheet, dialog, snackbar |
| Canvas | màu, typography, khoảng cách, radius, kích thước, thứ bậc thị giác và trạng thái tham chiếu |
| Pema web | chỉ dùng để port các màn được ghi là web-only trong canvas (I/J/K) hoặc khi yêu cầu rõ |

Không suy diễn tính năng từ canvas. Canvas I/J/K có thể là web-only: kiểm tra trước khi tuyên bố KMP đã đủ màn.

Đọc trước:

1. `pema-kmp/CONVENTIONS.md`
2. `AGENT.md`
3. `.agents/skills/pema-design/SKILL.md` và `references/visual-system.md`
4. `.claude/skills/pema-web-to-canvas/SKILL.md` nếu phạm vi có Pema web hoặc canvas.

## 1. Phân loại phạm vi trước khi code

Liệt kê mã màn canvas và truy ngược từng mã về nguồn:

- **A–H** hiện là các màn mirror Flutter; port nếu source Flutter có route/tab/trạng thái tương ứng.
- **I** vận hành Clinic từ web, **J** Patient 360 web đầy đủ, **K** Pema Care web: là phạm vi riêng, không coi là hoàn thành chỉ vì A–H đã xong.
- Mỗi modal, sheet, error/empty/loading state là một màn cần kiểm chứng nếu canvas có mã riêng.

Lập bảng tối thiểu:

| Mã | Tên | Nguồn logic | Module KMP | Route/trạng thái | Kiểm chứng |
|---|---|---|---|---|---|
| F4 | Lên đơn | Flutter `quick_order` | `feature:orders` | `Routes.QuickOrder` | JVM shot + Android |

Không bắt đầu feature agent trước khi bảng này rõ ràng. Tránh hai lỗi từng gặp: global bottom nav tưởng tượng và UI đẹp nhưng mất logic Flutter.

## 2. Chuẩn bị ảnh canvas

Canvas cung cấp ảnh đối chiếu, không cần chạy Flutter để chụp reference.

```powershell
cd E:\Desktop\cnbphongkham\design-viewer
npm run dev

cd E:\Desktop\cnbphongkham
node .claude\skills\pema-web-to-canvas\scripts\canvas.cjs list
node <duong-dan-session>\files\shots.cjs <thu-muc-ngoai-repo>\ref
```

- `shots.cjs` render từng canvas ID với bezel ở 390×844dp, density 2.
- Không commit ảnh reference hoặc artifact screenshot.
- Dùng `shotVsCanvas("F4") { ... }` trong `jvmTest`; ảnh ghép nằm tại `<module>/build/shots/F4-vs.png` (canvas trái, KMP phải).
- Nếu canvas thay đổi, tạo lại reference trước khi hiệu chỉnh KMP.

## 3. Thiết kế kiến trúc trước khi port

Giữ ranh giới module:

| Module | Trách nhiệm |
|---|---|
| `core:common` | route ID ASCII, `AppNavigator`, API config |
| `core:ui` | token canvas, font Be Vietnam Pro, block chung, scaffold, sheet, snackbar, screenshot harness |
| `core:hardware` | expect/actual camera, gallery, in/invoker, haptic; fake cho test |
| `shared` | model, repository/store, state business từ Flutter provider |
| `feature:*` | composable route/screen và block riêng |
| `composeApp` | NavHost, route guard, app container, root messenger |

Ưu tiên port domain/store trước UI. So dữ liệu JSON Flutter với KMP: số hồ sơ, sản phẩm, role/sample data và business rule phải khớp.

`Routes` chỉ dùng ID ASCII ổn định. Chuỗi tiếng Việt là title/display text, không phải route; URL/route có dấu, dấu cách, `&` hoặc ký tự đặc biệt dễ hỏng navigation.

## 4. Dựng core UI từ canvas trước

Không cho từng feature tự tạo bảng màu/card/navigation. Port token và block dùng chung đầu tiên:

- màu Pema `blue #0B4F94`, `navy #083A6E`, `sky #3CAAE5`, `ink #17324D`, `muted #5D7184`, `paper #F4F8FB`, `line #E0EAF2`;
- Be Vietnam Pro từ compose resources;
- heading, section, hero, metric, tile, notice, action/card/input/chip;
- `DetailScaffold` có app bar/back/max width và `PemaScaffold` có bottom nav/IME;
- icon cùng một họ Material; surface/touch target theo canvas.

Khi assets của thư viện không vào APK, kiểm tra convention plugin:

```kotlin
android {
    androidResources { enable = true }
}
```

Không thay token canvas bằng palette “sáng tạo” khác. Chụp ít nhất một workspace/hero/reference trước khi chạy feature waves.

## 5. Port navigation và role flow 1:1

Flutter có push-navigation: Workspace là điểm vào; bottom nav thuộc workspace theo role, không phải nav toàn cục áp lên mọi route.

App shell cần:

1. Bắt đầu từ Workspace.
2. `NavHost` đăng ký route feature.
3. `resolveRoute()` áp quyền như Flutter: route bị chặn mở trang `DeniedScreen`; route lạ mở `GuideScreen`.
4. Giữ tab/nhóm/filter có thể quay lại bằng `rememberSaveable`.
5. Route có tham số (như finance tab) phải được parse và đi qua `Routes`.
6. `PaymentAlerts` bọc ở cấp app nếu Flutter bọc ở cấp app.

Luôn đối chiếu role và `allows()` Flutter trước khi làm menu. Kiểm tra riêng owner, doctor, care, accountant và patient/care mode.

## 6. Triển khai feature theo đợt

Chỉ dùng agent song song khi module/file ownership không chồng lấp. Mỗi agent phải nhận đủ:

- đường dẫn source Flutter và mã canvas của feature;
- danh sách field/nút/role/state cần giữ;
- API/block `core:ui` được phép dùng;
- file/module được sở hữu;
- yêu cầu viết `commonTest` cho logic, `jvmTest` cho ảnh;
- yêu cầu build feature trước khi bàn giao.

Agent không được tự đổi `App.kt`, `Routes`, build logic, `FeatureDeps` hoặc `core:ui`; báo integration áp dụng thay đổi. Sau đợt, integration xử lý dependency chéo và full build.

## 7. Vòng kiểm chứng ảnh bắt buộc

Mỗi canvas ID được port:

```kotlin
@Test
fun f4QuickOrder() {
    shotVsCanvas("F4") {
        QuickOrderScreen(state = previewState, onEvent = {})
    }
}
```

Quy trình:

1. Render shot 390×844dp ×2.
2. Mở `*-vs.png`; kiểm tra text overflow, gutter, radius, font, icon, sheet/scrim và fixed bottom bar.
3. Sửa cho đến khi bố cục khớp; không chỉ nhìn test pass.
4. Test đầy đủ state có canvas: default, filter, sheet/dialog, empty/error, role-specific.

Khác biệt chỉ được chấp nhận khi có lý do rõ ràng, ví dụ logo Pema thật thay placeholder hoặc sample data nguồn thật thay demo canvas.

## 8. Kiểm chứng Android thật (bắt buộc)

JVM shot không phát hiện lifecycle, keyboard, bundle saver, asset packaging, navigation pop hoặc nested scroll.

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat jvmTest :androidApp:assembleDebug --console=plain -q

$adb='E:\apdata\platform-tools\adb.exe'
& $adb devices -l
& $adb -s <serial> install -r androidApp\build\outputs\apk\debug\androidApp-debug.apk
& $adb -s <serial> shell monkey -p com.pema.clinic.kmp -c android.intent.category.LAUNCHER 1
```

Walk each role and critical action (mở tab → route con → lưu → back → snackbar). Clear logcat before run, then inspect crash buffer. Với emulator đa-display, dùng đúng display ID trong `screencap`.

Nếu MIUI báo `INSTALL_FAILED_USER_RESTRICTED`, không cố bypass: người dùng phải chấp nhận cài qua USB hoặc chép APK và cài trực tiếp từ thiết bị.

## 9. Bẫy Compose đã xác nhận trên Android

| Vấn đề | Cách xử lý |
|---|---|
| Snackbar mất khi `save → back()` | Dùng `rememberPemaMessenger().show()` từ scope gốc cung cấp ở `App.kt`; scope `rememberCoroutineScope()` của màn bị hủy khi pop |
| Tab/filter/query mất sau route con | Dùng `rememberSaveable` |
| Data class/enum custom crash khi save state | Cung cấp `listSaver` hoặc `mapSaver`, không lưu trực tiếp object không Bundle-compatible |
| Crash trong bottom sheet | Không lồng hai `verticalScroll`; chỉ một vùng cuộn |
| Keyboard che nội dung/snackbar | `PemaScaffold` đệm IME; Android manifest `windowSoftInputMode="adjustResize"`; không thêm IME padding trùng |
| Font/logo/resource thiếu trong APK | Bật `androidResources.enable = true` trong module library |
| Build Gradle lock | Đợi 30–60 giây và chạy lại; không chạy nhiều Gradle full-build đồng thời |

## 10. Kết thúc

1. Chạy `jvmTest :androidApp:assembleDebug`, đếm test/failure từ XML.
2. Cài và launch APK trên Android thật hoặc emulator; lưu evidence screenshot ngoài repo.
3. So coverage table: nêu chính xác nhóm/mã đã port, nhóm web-only chưa port và giới hạn camera/iOS.
4. Cập nhật `pema-kmp/README.md` và `CONVENTIONS.md` nếu thay đổi quy ước hoặc phạm vi.
5. Nếu sửa Pema web hiển thị, thêm entry `Chờ chuyển` trong `.claude/skills/pema-web-to-canvas/web-changes.md`; không cập nhật canvas trừ khi được yêu cầu.
6. Không commit ảnh build, APK, database local, screenshot hoặc file tạm.

