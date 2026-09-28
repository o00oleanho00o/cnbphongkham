package com.pema.clinic.core.hardware

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow

class FakeCameraService(
    private var available: Boolean = true,
    private var nextPhoto: CapturedPhoto? = CapturedPhoto("fake://photo.jpg", 1024, 768, 64_000),
) : CameraService {
    val discarded = mutableListOf<CapturedPhoto>()
    /** Emit here to simulate a photo recovered after the screen was recreated. */
    val recovered = kotlinx.coroutines.channels.Channel<CapturedPhoto>(kotlinx.coroutines.channels.Channel.UNLIMITED)
    fun setAvailable(value: Boolean) { available = value }
    fun setNextPhoto(photo: CapturedPhoto?) { nextPhoto = photo }
    override suspend fun isAvailable(): Boolean = available
    override suspend fun capture(): CapturedPhoto? = nextPhoto
    override suspend fun pick(): CapturedPhoto? = nextPhoto
    override fun recoveredPhotos(): Flow<CapturedPhoto> = recovered.receiveAsFlow()
    override suspend fun discard(photo: CapturedPhoto) { discarded += photo }
}

class FakeImageLoader : ImageLoader {
    override suspend fun load(path: String, maxHeightPx: Int) = null
}

class FakePrinter : Printer {
    val jobs = mutableListOf<Pair<String, List<String>>>()
    override suspend fun printA5(title: String, lines: List<String>): Boolean {
        jobs += title to lines
        return true
    }
}

class FakeLauncher : Launcher {
    val actions = mutableListOf<String>()
    override fun dial(phone: String) { actions += "dial:$phone" }
    override fun openUrl(url: String) { actions += "url:$url" }
    override fun share(text: String) { actions += "share:$text" }
}

class FakeHaptics : Haptics {
    var taps = 0
    var successes = 0
    var warnings = 0
    override fun tap() { taps++ }
    override fun success() { successes++ }
    override fun warning() { warnings++ }
}

class FakeNotifier : Notifier {
    val notifications = mutableListOf<Triple<Int, String, String>>()
    override suspend fun requestPermission(): Boolean = true
    override fun notify(id: Int, title: String, body: String) { notifications += Triple(id, title, body) }
}

fun FakePlatformServices(camera: FakeCameraService = FakeCameraService()): PlatformServices = PlatformServices(
    camera = camera,
    images = FakeImageLoader(),
    printer = FakePrinter(),
    launcher = FakeLauncher(),
    haptics = FakeHaptics(),
    notifier = FakeNotifier(),
)
