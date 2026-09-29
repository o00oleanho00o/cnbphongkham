# Pema iOS

Ứng dụng iOS chỉ gồm lớp vỏ SwiftUI (`iOSApp.swift`, `ContentView.swift`) hiển thị `MainViewController()` từ framework Kotlin `ComposeApp`.

- `project.yml`: cấu hình [XcodeGen](https://github.com/yonaskolb/XcodeGen). `iosApp.xcodeproj` được sinh ra từ file này và không commit.
- Bước pre-build gọi `./gradlew :composeApp:embedAndSignAppleFrameworkForXcode` để biên dịch framework `ComposeApp` và chép compose resources vào app.

## Build trên GitHub Actions (không cần Mac)
Workflow `.github/workflows/ios-kmp.yml` chỉ chạy khi bấm tay (không tự chạy khi push, để tiết kiệm thời gian build): vào tab **Actions → iOS build (pema-kmp) → Run workflow**, chọn nhánh rồi chạy. Kết quả là artifact `Pema-unsigned.ipa` (IPA chưa ký, tải thẳng, không cần giải nén).

Cài lên iPhone từ Windows: tải artifact, mở `Pema-unsigned.ipa` bằng [Sideloadly](https://sideloadly.io) và đăng nhập Apple ID để ký. Với Apple ID miễn phí, app dùng được 7 ngày. Muốn phát qua TestFlight thì cần tài khoản Apple Developer và thêm bước ký/upload.

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