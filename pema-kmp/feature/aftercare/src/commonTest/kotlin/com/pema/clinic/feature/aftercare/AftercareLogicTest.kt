package com.pema.clinic.feature.aftercare

import com.pema.clinic.core.hardware.CameraService
import com.pema.clinic.core.hardware.CapturedPhoto
import com.pema.clinic.core.hardware.HardwareFailure
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class AftercareLogicTest {
    @Test
    fun homeCareAcknowledgementMatchesFlutter() {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val id = catalog.catalog().profiles.first().id

        assertFalse(patients.of(id).acknowledged)
        patients.acknowledgeInstructions(id)

        assertTrue(patients.of(id).acknowledged)
        assertEquals("Đã xác nhận đã đọc", if (patients.of(id).acknowledged) "Đã xác nhận đã đọc" else "Tôi đã đọc hướng dẫn")
    }

    @Test
    fun capturedPhotoNeedsConsentAndIsAttachedToUpdate() = runTest {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val id = catalog.catalog().profiles.first().id
        val camera = QueueCamera(photo("a"), photo("b"))
        val draft = SendUpdateDraft()

        draft.text = "Da đỡ đỏ"
        assertTrue(draft.canSend)
        assertNull(draft.capture(camera))
        assertFalse(draft.canSend)

        assertNull(draft.capture(camera))
        assertEquals(listOf("/cache/photos/a.jpg"), camera.discarded)

        draft.consent = true
        assertTrue(draft.submit(patients, id, camera))
        assertEquals(listOf("/cache/photos/b.jpg"), patients.of(id).photos)
        assertEquals(listOf("Da đỡ đỏ"), patients.of(id).updates)
        assertEquals(listOf("/cache/photos/b.jpg"), camera.saved)

        draft.dispose(camera)
        assertEquals(listOf("/cache/photos/a.jpg"), camera.discarded)
    }

    @Test
    fun cameraFailureRemovePhotoAndUnsentDisposeMatchFlutter() = runTest {
        val failing = QueueCamera(HardwareFailure("Thiết bị này chưa hỗ trợ chụp ảnh."))
        val failedDraft = SendUpdateDraft()

        assertEquals("Thiết bị này chưa hỗ trợ chụp ảnh.", failedDraft.capture(failing))
        assertNull(failedDraft.photo)

        val camera = QueueCamera(photo("a"), photo("b"))
        val draft = SendUpdateDraft()
        assertNull(draft.capture(camera))
        draft.consent = true
        draft.removePhoto(camera)
        assertNull(draft.photo)
        assertFalse(draft.consent)
        assertEquals(listOf("/cache/photos/a.jpg"), camera.discarded)

        assertNull(draft.capture(camera))
        draft.dispose(camera)
        assertEquals(listOf("/cache/photos/a.jpg", "/cache/photos/b.jpg"), camera.discarded)
    }

    @Test
    fun followUpReplyValidationAndResponseMatchFlutter() {
        assertFalse(canSendReply("   "))
        assertTrue(canSendReply("Dịu hơn, tiếp tục dưỡng ẩm."))

        val state = com.pema.clinic.shared.patients.PatientState(
            sessions = 2,
            appointment = "10:30",
            day = "2026-09-22",
        ).withDoctorReply("Dịu hơn, tiếp tục dưỡng ẩm.")

        assertEquals("Dịu hơn, tiếp tục dưỡng ẩm.", state.response)
    }

    @Test
    fun reviewQueueListsOnlyDoctorsProfilesNeedingReview() = runTest {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val session = SessionStore(catalog)
        val review = ReviewQueue(catalog, patients, session, backgroundScope)

        session.enterStaff("doctor", "BS. Mai")
        runCurrent()
        var queue = review.profiles()
        assertTrue(queue.all { it.doctor == "BS. Mai" })

        val quiet = catalog.catalog().profiles.first { it.doctor == "BS. Mai" && it !in queue }
        patients.update(quiet.id) { it.copy(updates = listOf("Da đỡ đỏ")) }
        runCurrent()

        queue = review.profiles()
        assertContains(queue, quiet)
    }
}

private class QueueCamera(vararg results: Any?) : CameraService {
    private val pending = results.toMutableList()
    val discarded = mutableListOf<String>()
    val saved = mutableListOf<String>()

    override suspend fun isAvailable(): Boolean = true

    override suspend fun capture(): CapturedPhoto? {
        val next = pending.removeAt(0)
        if (next is Throwable) throw next
        return next as CapturedPhoto?
    }

    override suspend fun discard(photo: CapturedPhoto) {
        discarded += photo.path
    }

    override fun markSaved(path: String) {
        saved += path
    }
}

private fun photo(name: String) = CapturedPhoto(
    path = "/cache/photos/$name.jpg",
    width = 1200,
    height = 1600,
    bytes = 240_000,
)
