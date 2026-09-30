package com.example.pema_native_template

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import androidx.core.content.FileProvider
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.min

/**
 * Opens the system camera app and returns a downscaled, upright JPEG.
 *
 * No CAMERA permission is declared: ACTION_IMAGE_CAPTURE runs in the camera
 * app, and declaring the permission would force a runtime prompt. Re-encoding
 * drops all EXIF metadata, including GPS, before the photo reaches Dart.
 */
class PemaCamera(private val activity: Activity) : MethodChannel.MethodCallHandler {
    companion object {
        const val CHANNEL = "pema/camera"
        private const val REQUEST = 7301
        private const val MAX_EDGE = 1600
        private const val QUALITY = 85
        private const val STATE_RAW = "pema.camera.raw"
    }

    private var pending: MethodChannel.Result? = null
    private var raw: File? = null
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    private val photoDir: File
        get() = File(activity.cacheDir, "photos").apply { mkdirs() }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "isAvailable" -> result.success(
                activity.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)
            )
            "capture" -> capture(result)
            "delete" -> {
                val path = call.argument<String>("path")
                val file = path?.let(::File)
                result.success(file != null && file.parentFile == photoDir && file.delete())
            }
            else -> result.notImplemented()
        }
    }

    private fun capture(result: MethodChannel.Result) {
        if (pending != null) {
            result.error("busy", "Camera đang mở", null)
            return
        }
        val file = File.createTempFile("raw_", ".jpg", photoDir)
        val uri = FileProvider.getUriForFile(
            activity,
            "${activity.packageName}.pema.fileprovider",
            file,
        )
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            .putExtra(MediaStore.EXTRA_OUTPUT, uri)
            .addFlags(
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION
            )
        // Some camera apps only honour the grant when the URI is in ClipData.
        intent.clipData = ClipData.newRawUri("", uri)
        if (intent.resolveActivity(activity.packageManager) == null) {
            file.delete()
            result.error("no_camera", "Thiết bị không có ứng dụng camera", null)
            return
        }
        pending = result
        raw = file
        try {
            activity.startActivityForResult(intent, REQUEST)
        } catch (e: ActivityNotFoundException) {
            pending = null
            raw = null
            file.delete()
            result.error("no_camera", "Thiết bị không có ứng dụng camera", null)
        }
    }

    /** Returns true when the result belonged to the camera request. */
    fun onActivityResult(requestCode: Int, resultCode: Int): Boolean {
        if (requestCode != REQUEST) return false
        val result = pending
        val file = raw
        pending = null
        raw = null
        if (result == null) {
            // The activity was recreated while the camera was open; the Dart
            // call that started it is gone, so discard the capture.
            file?.delete()
            return true
        }
        if (resultCode != Activity.RESULT_OK || file == null || file.length() == 0L) {
            file?.delete()
            result.success(null)
            return true
        }
        worker.execute {
            try {
                val photo = process(file)
                main.post { result.success(photo) }
            } catch (e: Exception) {
                file.delete()
                main.post { result.error("process_failed", e.message ?: "Không xử lý được ảnh", null) }
            }
        }
        return true
    }

    fun saveState(out: Bundle) {
        raw?.let { out.putString(STATE_RAW, it.path) }
    }

    fun restoreState(state: Bundle?) {
        state?.getString(STATE_RAW)?.let { raw = File(it) }
    }

    fun dispose() = worker.shutdown()

    private fun process(source: File): Map<String, Any> {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(source.path, bounds)
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_EDGE) sample *= 2
        val decoded = BitmapFactory.decodeFile(
            source.path,
            BitmapFactory.Options().apply { inSampleSize = sample },
        ) ?: error("Không đọc được ảnh")

        val rotation = when (
            ExifInterface(source.path).getAttributeInt(
                ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_NORMAL,
            )
        ) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        val scale = min(1f, MAX_EDGE.toFloat() / max(decoded.width, decoded.height))
        val bitmap = if (scale < 1f || rotation != 0f) {
            val matrix = Matrix().apply {
                postScale(scale, scale)
                postRotate(rotation)
            }
            Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        } else {
            decoded
        }

        val out = File(photoDir, "pema_${System.currentTimeMillis()}.jpg")
        FileOutputStream(out).use { bitmap.compress(Bitmap.CompressFormat.JPEG, QUALITY, it) }
        val width = bitmap.width
        val height = bitmap.height
        if (bitmap !== decoded) decoded.recycle()
        bitmap.recycle()
        source.delete()
        return mapOf(
            "path" to out.path,
            "width" to width,
            "height" to height,
            "bytes" to out.length(),
        )
    }
}
