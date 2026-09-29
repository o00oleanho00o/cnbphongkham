# Pema iOS

Ứng dụng iOS chỉ gồm lớp vỏ SwiftUI (`iOSApp.swift`, `ContentView.swift`) hiển thị `MainViewController()` từ framework Kotlin `ComposeApp`.

- `project.yml`: cấu hình [XcodeGen](https://github.com/yonaskolb/XcodeGen). `iosApp.xcodeproj` được sinh ra từ file này và không commit.
- Bước pre-build gọi `./gradlew :composeApp:embedAndSignAppleFrameworkForXcode` để biên dịch framework `ComposeApp` và chép compose resources vào app.

## Build trên GitHub Actions (không cần Mac)
Workflow `.github/workflows/ios-kmp.yml` chỉ chạy khi bấm tay (không tự chạy khi push, để tiết kiệm thời gian build): vào tab **Actions → iOS build (pema-kmp) → Run workflow**, chọn nhánh và `target`:

- `simulator` (mặc định): artifact `Pema-simulator.zip` (thư mục `Pema.app` đã nén, dùng cho iOS Simulator). Tải lên [Appetize.io](https://appetize.io) (Apps → Upload, chọn iOS) để chạy trong trình duyệt. Dùng gói Free (30 phút/tháng) nên nhớ đóng phiên khi xong.
- `device`: artifact `Pema-unsigned.ipa` (IPA chưa ký cho iPhone thật).

Cả hai đều tải thẳng từ mục Artifacts, không cần giải nén thêm.

Cài lên iPhone từ Windows: mở `Pema-unsigned.ipa` bằng [Sideloadly](https://sideloadly.io) và đăng nhập Apple ID để ký. Với Apple ID miễn phí, app dùng được 7 ngày. Muốn phát qua TestFlight thì cần tài khoản Apple Developer và thêm bước ký/upload.

## Trên máy Mac
```sh
brew install xcodegen
cd pema-kmp/iosApp && xcodegen generate && open iosApp.xcodeproj
```
Chọn Team trong Signing & Capabilities rồi Run.

## Kiểm tra code iOS trên Windows
Kotlin 2.4 biên dịch được klib iOS trên Windows (chưa link được app):
```powershell
.\gradlew.bat :composeApp:compileKotlinIosArm64 "-Pkotlin.native.enableKlibsCrossCompilation=true"
```