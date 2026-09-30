package com.pema.clinic.feature.aftercare

import androidx.compose.runtime.saveable.SaverScope
import com.pema.clinic.core.hardware.CapturedPhoto
import com.pema.clinic.core.hardware.FakeCameraService
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Photo kept across Android recreation: recovered result attaches, saved draft restores. */
class SendUpdateRecoveryTest {
    @Test
    fun recoveredPhotoReplacesAndDiscardsThePreviousOne() = runTest {
        val camera = FakeCameraService()
        val draft = SendUpdateDraft(initialPhoto = photo("old"))
        draft.attach(photo("new"), camera)
        assertEquals("/cache/photos/new.jpg", draft.photo?.path)
        assertEquals(listOf("/cache/photos/old.jpg"), camera.discarded.map { it.path })
    }

    @Test
    fun draftSurvivesSaveAndRestore() {
        val draft = SendUpdateDraft(initialText = "Da đỡ đỏ", initialConsent = true, initialPhoto = photo("a"))
        val saved = with(SendUpdateDraft.Saver) { SaverScope { true }.save(draft) }!!
        val restored = SendUpdateDraft.Saver.restore(saved)!!
        assertEquals("Da đỡ đỏ", restored.text)
        assertTrue(restored.consent)
        assertEquals(photo("a"), restored.photo)
        assertTrue(restored.canSend)
    }

    private fun photo(name: String) = CapturedPhoto("/cache/photos/$name.jpg", 1200, 1600, 240_000)
}
