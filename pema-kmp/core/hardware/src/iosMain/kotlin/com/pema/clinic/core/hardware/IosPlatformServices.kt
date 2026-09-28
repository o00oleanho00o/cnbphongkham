package com.pema.clinic.core.hardware

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.toComposeImageBitmap
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlinx.cinterop.CValue
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.addressOf
import kotlinx.cinterop.useContents
import kotlinx.cinterop.usePinned
import kotlinx.coroutines.suspendCancellableCoroutine
import org.jetbrains.skia.Image
import platform.CoreGraphics.CGRectMake
import platform.CoreGraphics.CGSize
import platform.CoreGraphics.CGSizeMake
import platform.Foundation.NSData
import platform.Foundation.NSDate
import platform.Foundation.NSFileManager
import platform.Foundation.NSTemporaryDirectory
import platform.Foundation.NSURL
import platform.Foundation.writeToFile
import platform.UIKit.UIActivityViewController
import platform.UIKit.UIApplication
import platform.UIKit.UIImpactFeedbackGenerator
import platform.UIKit.UIImpactFeedbackStyleLight
import platform.UIKit.UIImage
import platform.UIKit.UIImageJPEGRepresentation
import platform.UIKit.UIImagePickerController
import platform.UIKit.UIImagePickerControllerDelegateProtocol
import platform.UIKit.UIImagePickerControllerOriginalImage
import platform.UIKit.UIGraphicsImageRenderer
import platform.UIKit.UIGraphicsImageRendererFormat
import platform.UIKit.UIMarkupTextPrintFormatter
import platform.UIKit.UINavigationControllerDelegateProtocol
import platform.UIKit.UINotificationFeedbackGenerator
import platform.UIKit.UINotificationFeedbackTypeSuccess
import platform.UIKit.UINotificationFeedbackTypeWarning
import platform.UIKit.UIPrintInfo
import platform.UIKit.UIPrintInfoOutputGeneral
import platform.UIKit.UIPrintInteractionController
import platform.UIKit.UIViewController
import platform.UserNotifications.UNAuthorizationOptionAlert
import platform.UserNotifications.UNAuthorizationOptionBadge
import platform.UserNotifications.UNAuthorizationOptionSound
import platform.UserNotifications.UNMutableNotificationContent
import platform.UserNotifications.UNNotificationRequest
import platform.UserNotifications.UNUserNotificationCenter
import platform.darwin.NSObject
import platform.posix.memcpy

@Composable
actual fun rememberPlatformServices(): PlatformServices = remember {
    PlatformServices(
        camera = IosCameraService(),
        images = IosImageLoader(),
        printer = IosPrinter(),
        launcher = IosLauncher(),
        haptics = IosHaptics(),
        notifier = IosNotifier(),
    )
}

private const val MAX_PHOTO_EDGE = 1600.0
private const val JPEG_QUALITY = 0.85

private object IosCameraState {
    var delegate: PemaImagePickerDelegate? = null
}

private class IosCameraService : CameraService {
    override suspend fun isAvailable(): Boolean =
        UIImagePickerController.isSourceTypeAvailable(platform.UIKit.UIImagePickerControllerSourceTypeCamera)

    override suspend fun capture(): CapturedPhoto? {
        if (IosCameraState.delegate != null) throw HardwareFailure("Đang mở camera.")
        if (!isAvailable()) throw HardwareFailure("Thiết bị này không có camera.")
        val host = topViewController() ?: throw HardwareFailure("Thiết bị này không có camera.")

        return suspendCancellableCoroutine { continuation ->
            val picker = UIImagePickerController()
            picker.sourceType = platform.UIKit.UIImagePickerControllerSourceTypeCamera
            val delegate = PemaImagePickerDelegate(continuation)
            IosCameraState.delegate = delegate
            picker.delegate = delegate
            continuation.invokeOnCancellation {
                IosCameraState.delegate = null
                picker.dismissViewControllerAnimated(true, completion = null)
            }
            host.presentViewController(picker, animated = true, completion = null)
        }
    }

    override suspend fun discard(photo: CapturedPhoto) {
        val file = NSURL.fileURLWithPath(photo.path)
        val dir = NSURL.fileURLWithPath(photosDir())
        if (file.URLByDeletingLastPathComponent?.standardizedURL?.path == dir.standardizedURL?.path) {
            NSFileManager.defaultManager.removeItemAtURL(file, error = null)
        }
    }
}

private class PemaImagePickerDelegate(
    private val continuation: kotlinx.coroutines.CancellableContinuation<CapturedPhoto?>,
) : NSObject(), UIImagePickerControllerDelegateProtocol, UINavigationControllerDelegateProtocol {
    override fun imagePickerControllerDidCancel(picker: UIImagePickerController) {
        picker.dismissViewControllerAnimated(true) { finish(null) }
    }

    override fun imagePickerController(
        picker: UIImagePickerController,
        didFinishPickingMediaWithInfo: Map<Any?, *>,
    ) {
        val image = didFinishPickingMediaWithInfo[UIImagePickerControllerOriginalImage] as? UIImage
        picker.dismissViewControllerAnimated(true) {
            if (image == null) {
                finish(null)
            } else {
                runCatching { processIosPhoto(image) }
                    .onSuccess { finish(it) }
                    .onFailure { finish(it) }
            }
        }
    }

    private fun finish(value: Any?) {
        IosCameraState.delegate = null
        if (!continuation.isActive) return
        when {
            value is Throwable -> continuation.resumeWithException(value)
            value == null || value is CapturedPhoto -> continuation.resume(value as CapturedPhoto?)
            else -> continuation.resumeWithException(HardwareFailure("Không xử lý được ảnh"))
        }
    }
}

private class IosImageLoader : ImageLoader {
    override suspend fun load(path: String, maxHeightPx: Int): ImageBitmap? {
        val image = UIImage(contentsOfFile = path) ?: return null
        val rendered = image.downscaledToMaxHeight(maxHeightPx.toDouble()) ?: return null
        val data = UIImageJPEGRepresentation(rendered, 1.0) ?: return null
        return Image.makeFromEncoded(data.toByteArray()).toComposeImageBitmap()
    }
}

private class IosPrinter : Printer {
    override suspend fun printA5(title: String, lines: List<String>): Boolean {
        val formatter = UIMarkupTextPrintFormatter(markupText = buildPrintHtml(title, lines))
        val info = UIPrintInfo.printInfo()
        info.outputType = UIPrintInfoOutputGeneral
        info.jobName = title.ifBlank { "Pema" }
        val controller = UIPrintInteractionController.sharedPrintController()
        controller.printInfo = info
        controller.printFormatter = formatter
        controller.presentAnimated(true, completionHandler = null)
        return true
    }
}

private class IosLauncher : Launcher {
    override fun dial(phone: String) {
        open("tel:$phone")
    }

    override fun openUrl(url: String) {
        open(url)
    }

    override fun share(text: String) {
        val host = topViewController() ?: return
        val controller = UIActivityViewController(activityItems = listOf(text), applicationActivities = null)
        host.presentViewController(controller, animated = true, completion = null)
    }

    private fun open(value: String) {
        NSURL.URLWithString(value)?.let { UIApplication.sharedApplication.openURL(it) }
    }
}

private class IosHaptics : Haptics {
    override fun tap() {
        UIImpactFeedbackGenerator(style = UIImpactFeedbackStyleLight).impactOccurred()
    }

    override fun success() {
        UINotificationFeedbackGenerator().notificationOccurred(UINotificationFeedbackTypeSuccess)
    }

    override fun warning() {
        UINotificationFeedbackGenerator().notificationOccurred(UINotificationFeedbackTypeWarning)
    }
}

private class IosNotifier : Notifier {
    override suspend fun requestPermission(): Boolean = suspendCancellableCoroutine { continuation ->
        val options = UNAuthorizationOptionAlert or UNAuthorizationOptionSound or UNAuthorizationOptionBadge
        UNUserNotificationCenter.currentNotificationCenter()
            .requestAuthorizationWithOptions(options) { granted, error ->
                if (error != null) continuation.resume(false) else continuation.resume(granted)
            }
    }

    override fun notify(id: Int, title: String, body: String) {
        val content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        val request = UNNotificationRequest.requestWithIdentifier(
            identifier = id.toString(),
            content = content,
            trigger = null,
        )
        UNUserNotificationCenter.currentNotificationCenter().addNotificationRequest(request, withCompletionHandler = null)
    }
}

private fun processIosPhoto(image: UIImage): CapturedPhoto {
    val rendered = image.downscaledToMaxEdge(MAX_PHOTO_EDGE) ?: throw HardwareFailure("Không xử lý được ảnh")
    val data = UIImageJPEGRepresentation(rendered, JPEG_QUALITY) ?: throw HardwareFailure("Không xử lý được ảnh")
    val dir = photosDir()
    val path = "$dir/pema_${(NSDate().timeIntervalSince1970 * 1000).toLong()}.jpg"
    if (!data.writeToFile(path, atomically = true)) throw HardwareFailure("Không lưu được ảnh")
    val size = rendered.size.readSize()
    return CapturedPhoto(path = path, width = size.first, height = size.second, bytes = data.length.toLong())
}

private fun photosDir(): String {
    val path = NSTemporaryDirectory().trimEnd('/') + "/photos"
    NSFileManager.defaultManager.createDirectoryAtPath(
        path = path,
        withIntermediateDirectories = true,
        attributes = null,
        error = null,
    )
    return path
}

private fun UIImage.downscaledToMaxEdge(maxEdge: Double): UIImage? {
    val size = this.size.readDoubleSize()
    val scale = min(1.0, maxEdge / max(size.first, size.second))
    return redraw(CGSizeMake((size.first * scale).roundToInt().toDouble(), (size.second * scale).roundToInt().toDouble()))
}

private fun UIImage.downscaledToMaxHeight(maxHeight: Double): UIImage? {
    if (maxHeight <= 0.0) return this
    val size = this.size.readDoubleSize()
    val scale = min(1.0, maxHeight / size.second)
    return redraw(CGSizeMake((size.first * scale).roundToInt().toDouble(), (size.second * scale).roundToInt().toDouble()))
}

private fun UIImage.redraw(target: CValue<CGSize>): UIImage? {
    val format = UIGraphicsImageRendererFormat.defaultFormat()
    format.scale = 1.0
    return UIGraphicsImageRenderer(size = target, format = format).imageWithActions {
        this@redraw.drawInRect(CGRectMake(0.0, 0.0, target.readDoubleSize().first, target.readDoubleSize().second))
    }
}

private fun CValue<CGSize>.readSize(): Pair<Int, Int> = useContents {
    width.roundToInt() to height.roundToInt()
}

private fun CValue<CGSize>.readDoubleSize(): Pair<Double, Double> = useContents { width to height }

private fun topViewController(): UIViewController? {
    var top = UIApplication.sharedApplication.keyWindow?.rootViewController
    while (top?.presentedViewController != null) top = top.presentedViewController
    return top
}

private fun buildPrintHtml(title: String, lines: List<String>): String {
    val items = lines.joinToString(separator = "") { "<li>${escapeHtml(it)}</li>" }
    return """
        <!doctype html>
        <html><head><meta charset="utf-8">
        <style>body{font-family:-apple-system,sans-serif;color:#102033}h1{font-size:20px}li{font-size:13px;margin:7px 0}</style>
        </head><body><h1>${escapeHtml(title)}</h1><ul>$items</ul></body></html>
    """.trimIndent()
}

private fun escapeHtml(value: String): String = buildString(value.length) {
    value.forEach { char ->
        append(
            when (char) {
                '<' -> "&lt;"
                '>' -> "&gt;"
                '&' -> "&amp;"
                '"' -> "&quot;"
                '\'' -> "&#39;"
                else -> char.toString()
            },
        )
    }
}

@OptIn(ExperimentalForeignApi::class)
private fun NSData.toByteArray(): ByteArray {
    val count = length.toInt()
    if (count == 0) return ByteArray(0)
    val result = ByteArray(count)
    result.usePinned { pinned -> memcpy(pinned.addressOf(0), bytes, length) }
    return result
}