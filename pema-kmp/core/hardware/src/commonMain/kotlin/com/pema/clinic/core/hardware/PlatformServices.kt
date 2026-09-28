package com.pema.clinic.core.hardware

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.ImageBitmap
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

data class CapturedPhoto(val path: String, val width: Int, val height: Int, val bytes: Long)
class HardwareFailure(message: String) : Exception(message)

/**
 * Photo capture. Photos are resized to max 1600px, JPEG 85, EXIF/GPS stripped, stored in the
 * app cache (`photos/`). `null` = user cancelled.
 */
interface CameraService {
    suspend fun isAvailable(): Boolean
    suspend fun capture(): CapturedPhoto?
    /** Pick an existing photo (system photo picker, no storage permission). */
    suspend fun pick(): CapturedPhoto? = throw HardwareFailure("Thiết bị này chưa hỗ trợ chọn ảnh.")
    /**
     * Photos whose result arrived after the screen was recreated (rotation, or Android killed the
     * app while the camera/picker was open). Each photo is delivered once, to one collector.
     */
    fun recoveredPhotos(): Flow<CapturedPhoto> = emptyFlow()
    suspend fun discard(photo: CapturedPhoto)
}
interface ImageLoader { suspend fun load(path: String, maxHeightPx: Int): ImageBitmap? }
interface Printer { suspend fun printA5(title: String, lines: List<String>): Boolean }
interface Launcher { fun dial(phone: String); fun openUrl(url: String); fun share(text: String) }
interface Haptics { fun tap(); fun success(); fun warning() }
interface Notifier { suspend fun requestPermission(): Boolean; fun notify(id: Int, title: String, body: String) }
class PlatformServices(val camera: CameraService, val images: ImageLoader, val printer: Printer, val launcher: Launcher, val haptics: Haptics, val notifier: Notifier)
@Composable expect fun rememberPlatformServices(): PlatformServices
/** Defaults to fakes so previews and JVM screenshot tests work without a platform. */
val LocalPlatformServices = staticCompositionLocalOf<PlatformServices> { FakePlatformServices() }
