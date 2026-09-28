package com.pema.clinic.core.hardware

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import android.print.PrintAttributes
import android.print.PrintManager
import android.provider.MediaStore
import android.view.HapticFeedbackConstants
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.ManagedActivityResultLauncher
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.FileOutputStream
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
actual fun rememberPlatformServices(): PlatformServices {
    val context = LocalContext.current
    val view = LocalView.current
    var pendingRawPath by rememberSaveable { mutableStateOf<String?>(null) }
    val cameraCoordinator = remember { AndroidCameraCoordinator() }
    val notificationCoordinator = remember { AndroidPermissionCoordinator() }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture(),
    ) { success -> cameraCoordinator.complete(success) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> notificationCoordinator.complete(granted) }

    return remember(context, view, cameraLauncher, permissionLauncher) {
        PlatformServices(
            camera = AndroidCameraService(
                context = context,
                coordinator = cameraCoordinator,
                getPendingRawPath = { pendingRawPath },
                setPendingRawPath = { pendingRawPath = it },
                launcher = cameraLauncher,
            ),
            images = AndroidImageLoader(),
            printer = AndroidPrinter(context),
            launcher = AndroidLauncher(context),
            haptics = AndroidHaptics(view),
            notifier = AndroidNotifier(context, notificationCoordinator, permissionLauncher),
        )
    }
}

private const val MAX_PHOTO_EDGE = 1600
private const val JPEG_QUALITY = 85

private const val CAMERA_URI_FLAGS = Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION

private class AndroidCameraCoordinator {
    private var deferred: CompletableDeferred<Boolean>? = null

    @Synchronized
    fun begin(next: CompletableDeferred<Boolean>): Boolean {
        if (deferred != null) return false
        deferred = next
        return true
    }

    @Synchronized
    fun complete(success: Boolean) {
        deferred?.takeIf { !it.isCompleted }?.complete(success)
    }

    @Synchronized
    fun clear(expected: CompletableDeferred<Boolean>) {
        if (deferred === expected) deferred = null
    }
}

private class AndroidCameraService(
    private val context: Context,
    private val coordinator: AndroidCameraCoordinator,
    private val getPendingRawPath: () -> String?,
    private val setPendingRawPath: (String?) -> Unit,
    private val launcher: ManagedActivityResultLauncher<Uri, Boolean>,
) : CameraService {
    private val appContext: Context = context.applicationContext

    override suspend fun isAvailable(): Boolean = withContext(Dispatchers.Default) {
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        appContext.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) &&
            intent.resolveActivity(appContext.packageManager) != null
    }

    override suspend fun capture(): CapturedPhoto? {
        if (!isAvailable()) throw HardwareFailure("Thiết bị này không có camera.")

        val result = CompletableDeferred<Boolean>()
        val (rawFile, rawUri) = withContext(Dispatchers.Main.immediate) {
            if (!coordinator.begin(result)) throw HardwareFailure("Đang mở camera.")

            getPendingRawPath()?.let { File(it).takeIf(File::exists)?.delete() }
            val file = File.createTempFile("raw_", ".jpg", photoDir())
            val uri = FileProvider.getUriForFile(
                appContext,
                "${appContext.packageName}.pema.fileprovider",
                file,
            )
            setPendingRawPath(file.absolutePath)
            try {
                appContext.grantCameraUriPermissions(uri)
                launcher.launch(uri)
            } catch (error: ActivityNotFoundException) {
                coordinator.clear(result)
                appContext.revokeCameraUriPermissions(uri)
                setPendingRawPath(null)
                file.delete()
                throw HardwareFailure("Thiết bị này không có camera.")
            } catch (error: IllegalStateException) {
                coordinator.clear(result)
                appContext.revokeCameraUriPermissions(uri)
                setPendingRawPath(null)
                file.delete()
                throw error
            }
            file to uri
        }

        return try {
            val accepted = result.await()
            if (!accepted || rawFile.length() == 0L) {
                rawFile.delete()
                null
            } else {
                withContext(Dispatchers.Default) { processRawPhoto(appContext, rawFile) }
            }
        } finally {
            coordinator.clear(result)
            appContext.revokeCameraUriPermissions(rawUri)
            setPendingRawPath(null)
        }
    }

    override suspend fun discard(photo: CapturedPhoto) {
        withContext(Dispatchers.IO) {
            val file = File(photo.path)
            if (isInsidePhotosDir(file, photoDir())) file.delete()
        }
    }

    private fun photoDir(): File = File(appContext.cacheDir, "photos").apply { mkdirs() }
}

private class AndroidImageLoader : ImageLoader {
    override suspend fun load(path: String, maxHeightPx: Int): ImageBitmap? = withContext(Dispatchers.IO) {
        val file = File(path)
        if (!file.exists() || !file.isFile) return@withContext null

        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return@withContext null

        val sample = if (maxHeightPx > 0) {
            var value = 1
            while (bounds.outHeight / (value * 2) >= maxHeightPx) value *= 2
            value
        } else {
            1
        }
        BitmapFactory.decodeFile(
            file.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = sample },
        )?.asImageBitmap()
    }
}

private class AndroidPrinter(private val context: Context) : Printer {
    override suspend fun printA5(title: String, lines: List<String>): Boolean = withContext(Dispatchers.Main.immediate) {
        val printManager = context.getSystemService(Context.PRINT_SERVICE) as? PrintManager
            ?: return@withContext false
        val webView = WebView(context)
        retainedWebViews.add(webView)
        val html = buildReceiptHtml(title, lines)
        val completion = CompletableDeferred<Boolean>()
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String?) {
                runCatching {
                    val adapter = view.createPrintDocumentAdapter(title.ifBlank { "Pema" })
                    val attributes = PrintAttributes.Builder()
                        .setMediaSize(PrintAttributes.MediaSize.ISO_A5)
                        .setColorMode(PrintAttributes.COLOR_MODE_COLOR)
                        .setMinMargins(PrintAttributes.Margins.NO_MARGINS)
                        .build()
                    printManager.print(title.ifBlank { "Pema" }, adapter, attributes)
                }.onSuccess {
                    completion.complete(true)
                }.onFailure {
                    completion.complete(false)
                }
                view.postDelayed({
                    retainedWebViews.remove(view)
                    view.destroy()
                }, 60_000L)
            }
        }
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
        completion.await()
    }

    private fun buildReceiptHtml(title: String, lines: List<String>): String {
        val body = lines.joinToString(separator = "") { "<li>${escapeHtml(it)}</li>" }
        return """
            <!doctype html>
            <html><head><meta charset="utf-8">
            <style>
            @page { size: A5; margin: 14mm; }
            body { font-family: sans-serif; color: #102033; }
            h1 { font-size: 20px; margin: 0 0 12px; }
            li { font-size: 13px; margin: 7px 0; }
            </style></head><body>
            <h1>${escapeHtml(title)}</h1><ul>$body</ul>
            </body></html>
        """.trimIndent()
    }

    private companion object {
        val retainedWebViews = mutableSetOf<WebView>()
    }
}

private class AndroidLauncher(private val context: Context) : Launcher {
    override fun dial(phone: String) {
        context.startSafely(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Uri.encode(phone)}")))
    }

    override fun openUrl(url: String) {
        context.startSafely(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }

    override fun share(text: String) {
        val send = Intent(Intent.ACTION_SEND)
            .setType("text/plain")
            .putExtra(Intent.EXTRA_TEXT, text)
        context.startSafely(Intent.createChooser(send, null))
    }
}

private class AndroidHaptics(private val view: View) : Haptics {
    override fun tap() {
        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
    }

    override fun success() {
        view.performHapticFeedback(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                HapticFeedbackConstants.CONFIRM
            } else {
                HapticFeedbackConstants.LONG_PRESS
            },
        )
    }

    override fun warning() {
        view.performHapticFeedback(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                HapticFeedbackConstants.REJECT
            } else {
                HapticFeedbackConstants.LONG_PRESS
            },
        )
    }
}

private class AndroidPermissionCoordinator {
    private var deferred: CompletableDeferred<Boolean>? = null

    @Synchronized
    fun begin(next: CompletableDeferred<Boolean>): Boolean {
        if (deferred != null) return false
        deferred = next
        return true
    }

    @Synchronized
    fun complete(granted: Boolean) {
        deferred?.takeIf { !it.isCompleted }?.complete(granted)
    }

    @Synchronized
    fun clear(expected: CompletableDeferred<Boolean>) {
        if (deferred === expected) deferred = null
    }
}

private class AndroidNotifier(
    private val context: Context,
    private val coordinator: AndroidPermissionCoordinator,
    private val launcher: ManagedActivityResultLauncher<String, Boolean>,
) : Notifier {
    override suspend fun requestPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            return true
        }

        val result = CompletableDeferred<Boolean>()
        return withContext(Dispatchers.Main.immediate) {
            if (!coordinator.begin(result)) return@withContext false
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
            try {
                result.await()
            } finally {
                coordinator.clear(result)
            }
        }
    }

    @SuppressLint("MissingPermission")
    override fun notify(id: Int, title: String, body: String) {
        ensureChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(context.applicationInfo.icon.takeIf { it != 0 } ?: android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(id, notification) }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Thông báo Pema", NotificationManager.IMPORTANCE_DEFAULT),
        )
    }

    private companion object {
        const val CHANNEL_ID = "pema_alerts"
    }
}

private fun processRawPhoto(context: Context, source: File): CapturedPhoto {
    try {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(source.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) error("Không đọc được ảnh")

        val decoded = BitmapFactory.decodeFile(
            source.absolutePath,
            BitmapFactory.Options().apply {
                inSampleSize = computeInSampleSize(bounds.outWidth, bounds.outHeight, MAX_PHOTO_EDGE)
            },
        ) ?: error("Không đọc được ảnh")

        val rotation = exifRotation(source)
        val scale = targetSize(decoded.width, decoded.height, MAX_PHOTO_EDGE)
            .let { it.width.toFloat() / decoded.width.toFloat() }
        val bitmap = if (rotation != 0f || scale < 1f) {
            val matrix = Matrix().apply {
                postScale(scale, scale)
                postRotate(rotation)
            }
            Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        } else {
            decoded
        }

        val output = File(File(context.cacheDir, "photos").apply { mkdirs() }, "pema_${System.currentTimeMillis()}.jpg")
        FileOutputStream(output).use { stream ->
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, stream)) {
                error("Không lưu được ảnh")
            }
        }
        val photo = CapturedPhoto(
            path = output.absolutePath,
            width = bitmap.width,
            height = bitmap.height,
            bytes = output.length(),
        )
        if (bitmap !== decoded) decoded.recycle()
        bitmap.recycle()
        return photo
    } finally {
        source.delete()
    }
}

private fun exifRotation(source: File): Float = when (
    ExifInterface(source.absolutePath).getAttributeInt(
        ExifInterface.TAG_ORIENTATION,
        ExifInterface.ORIENTATION_NORMAL,
    )
) {
    ExifInterface.ORIENTATION_ROTATE_90 -> 90f
    ExifInterface.ORIENTATION_ROTATE_180 -> 180f
    ExifInterface.ORIENTATION_ROTATE_270 -> 270f
    else -> 0f
}


private fun Context.grantCameraUriPermissions(uri: Uri) {
    val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
    packageManager.queryIntentActivities(intent, PackageManager.MATCH_DEFAULT_ONLY).forEach { match ->
        grantUriPermission(match.activityInfo.packageName, uri, CAMERA_URI_FLAGS)
    }
}

private fun Context.revokeCameraUriPermissions(uri: Uri) {
    runCatching { revokeUriPermission(uri, CAMERA_URI_FLAGS) }
}

private fun Context.startSafely(intent: Intent) {
    val safeIntent = if (this is Activity) intent else intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    runCatching { startActivity(safeIntent) }
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