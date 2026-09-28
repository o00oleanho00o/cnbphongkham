package com.pema.clinic.core.hardware

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AndroidPhotoMathTest {
    @Test
    fun sampleSizeIsLargestPowerOfTwoThatKeepsDecodeReasonable() {
        assertEquals(1, computeInSampleSize(1600, 1200, 1600))
        assertEquals(2, computeInSampleSize(4000, 3000, 1600))
        assertEquals(4, computeInSampleSize(8000, 6000, 1600))
    }

    @Test
    fun targetSizePreservesAspectRatioAndDoesNotUpscale() {
        assertEquals(PhotoSize(1600, 1200), targetSize(4000, 3000, 1600))
        assertEquals(PhotoSize(1200, 1600), targetSize(3000, 4000, 1600))
        assertEquals(PhotoSize(640, 480), targetSize(640, 480, 1600))
    }

    @Test
    fun insidePhotosDirRequiresDirectCanonicalParent() {
        val root = createTempDir(prefix = "pema_photos_test")
        try {
            val photos = File(root, "photos").apply { mkdirs() }
            val inside = File(photos, "pema.jpg")
            val nested = File(File(photos, "nested").apply { mkdirs() }, "pema.jpg")
            val sibling = File(root, "photos_evil/pema.jpg")

            assertTrue(isInsidePhotosDir(inside, photos))
            assertFalse(isInsidePhotosDir(nested, photos))
            assertFalse(isInsidePhotosDir(sibling, photos))
        } finally {
            root.deleteRecursively()
        }
    }
}
