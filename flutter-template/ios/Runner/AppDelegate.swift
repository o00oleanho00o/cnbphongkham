import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "PemaCameraPlugin") {
      PemaCameraPlugin.register(with: registrar)
    }
  }
}

/// Native side of the `pema/camera` channel; mirrors PemaCamera.kt on Android.
/// Re-drawing the photo makes it upright, downscales it to 1600 px and drops
/// all EXIF metadata (including GPS) before it reaches Dart.
final class PemaCameraPlugin: NSObject, FlutterPlugin, UIImagePickerControllerDelegate,
  UINavigationControllerDelegate
{
  private static let maxEdge: CGFloat = 1600
  private static let quality: CGFloat = 0.85
  private var pending: FlutterResult?

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "pema/camera", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(PemaCameraPlugin(), channel: channel)
  }

  private var photoDir: URL {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(
      "photos", isDirectory: true)
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "isAvailable":
      result(UIImagePickerController.isSourceTypeAvailable(.camera))
    case "capture":
      capture(result)
    case "delete":
      guard let args = call.arguments as? [String: Any], let path = args["path"] as? String else {
        result(false)
        return
      }
      let url = URL(fileURLWithPath: path)
      guard url.deletingLastPathComponent().standardizedFileURL == photoDir.standardizedFileURL
      else {
        result(false)
        return
      }
      result((try? FileManager.default.removeItem(at: url)) != nil)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func capture(_ result: @escaping FlutterResult) {
    guard pending == nil else {
      result(FlutterError(code: "busy", message: "Camera đang mở", details: nil))
      return
    }
    guard UIImagePickerController.isSourceTypeAvailable(.camera), let host = topViewController()
    else {
      result(FlutterError(code: "no_camera", message: "Thiết bị không có camera", details: nil))
      return
    }
    let picker = UIImagePickerController()
    picker.sourceType = .camera
    picker.delegate = self
    pending = result
    host.present(picker, animated: true)
  }

  func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
    picker.dismiss(animated: true)
    finish(nil)
  }

  func imagePickerController(
    _ picker: UIImagePickerController,
    didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
  ) {
    picker.dismiss(animated: true)
    guard let image = info[.originalImage] as? UIImage else {
      finish(nil)
      return
    }
    let dir = photoDir
    DispatchQueue.global(qos: .userInitiated).async {
      let photo = PemaCameraPlugin.process(image, into: dir)
      DispatchQueue.main.async {
        self.finish(
          photo
            ?? FlutterError(code: "process_failed", message: "Không xử lý được ảnh", details: nil))
      }
    }
  }

  private func finish(_ value: Any?) {
    let result = pending
    pending = nil
    result?(value)
  }

  private static func process(_ image: UIImage, into dir: URL) -> [String: Any]? {
    let scale = min(1, maxEdge / max(image.size.width, image.size.height))
    let size = CGSize(
      width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
    let format = UIGraphicsImageRendererFormat.default()
    format.scale = 1
    let upright = UIGraphicsImageRenderer(size: size, format: format).image { _ in
      image.draw(in: CGRect(origin: .zero, size: size))
    }
    guard let data = upright.jpegData(compressionQuality: quality) else { return nil }
    let url = dir.appendingPathComponent("pema_\(Int(Date().timeIntervalSince1970 * 1000)).jpg")
    do {
      try data.write(to: url, options: .atomic)
    } catch {
      return nil
    }
    return ["path": url.path, "width": Int(size.width), "height": Int(size.height), "bytes": data.count]
  }

  private func topViewController() -> UIViewController? {
    let windows = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
    var top = (windows.first { $0.isKeyWindow } ?? windows.first)?.rootViewController
    while let presented = top?.presentedViewController { top = presented }
    return top
  }
}
