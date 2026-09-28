package com.pema.clinic.core.hardware

import java.io.File
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

internal data class PhotoSize(val width: Int, val height: Int)

internal fun computeInSampleSize(width: Int, height: Int, maxEdge: Int): Int {
    if (width <= 0 || height <= 0 || maxEdge <= 0) return 1
    var sample = 1
    val longest = max(width, height)
    while (longest / (sample * 2) >= maxEdge) {
        sample *= 2
    }
    return sample
}

internal fun targetSize(width: Int, height: Int, maxEdge: Int): PhotoSize {
    require(width > 0 && height > 0) { "Image size must be positive." }
    if (maxEdge <= 0) return PhotoSize(width, height)
    val longest = max(width, height)
    val scale = min(1f, maxEdge.toFloat() / longest)
    return PhotoSize(
        width = (width * scale).roundToInt().coerceAtLeast(1),
        height = (height * scale).roundToInt().coerceAtLeast(1),
    )
}

internal fun isInsidePhotosDir(file: File, photosDir: File): Boolean {
    return runCatching {
        file.canonicalFile.parentFile == photosDir.canonicalFile
    }.getOrDefault(false)
}
