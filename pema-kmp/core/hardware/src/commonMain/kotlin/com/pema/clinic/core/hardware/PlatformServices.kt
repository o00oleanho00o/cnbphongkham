package com.pema.clinic.core.hardware

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.ImageBitmap

data class CapturedPhoto(val path: String, val width: Int, val height: Int, val bytes: Long)
class HardwareFailure(message: String) : Exception(message)
interface CameraService { suspend fun isAvailable(): Boolean; suspend fun capture(): CapturedPhoto?; suspend fun discard(photo: CapturedPhoto) }
interface ImageLoader { suspend fun load(path: String, maxHeightPx: Int): ImageBitmap? }
interface Printer { suspend fun printA5(title: String, lines: List<String>): Boolean }
interface Launcher { fun dial(phone: String); fun openUrl(url: String); fun share(text: String) }
interface Haptics { fun tap(); fun success(); fun warning() }
interface Notifier { suspend fun requestPermission(): Boolean; fun notify(id: Int, title: String, body: String) }
class PlatformServices(val camera: CameraService, val images: ImageLoader, val printer: Printer, val launcher: Launcher, val haptics: Haptics, val notifier: Notifier)
@Composable expect fun rememberPlatformServices(): PlatformServices
/** Defaults to fakes so previews and JVM screenshot tests work without a platform. */
val LocalPlatformServices = staticCompositionLocalOf<PlatformServices> { FakePlatformServices() }
