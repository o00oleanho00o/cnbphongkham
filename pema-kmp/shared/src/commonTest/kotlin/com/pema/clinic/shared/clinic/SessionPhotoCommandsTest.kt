package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Web `save-session` with `#session-photo`: the photo becomes the session image; no photo → follow-up. */
class SessionPhotoCommandsTest {
    private val doctor = StaffContext(role = "doctor", name = "BS. Tâm", doctorId = "D0", doctorName = "BS. Tâm")

    @Test
    fun landmarkPhotoIsStoredOnTheSessionAndSkipsTheMissingPhotoFollowUp() {
        val store = ClinicStore()
        val before = store.state.value.followups.count { it.patient == "P001" && it.priority == "missing" }
        val session = store.recordTreatmentSession("P001", input(photoPath = "/cache/photos/pema_1.jpg"), doctor)
        assertEquals("/cache/photos/pema_1.jpg", session.image)
        assertEquals("Má trái", store.patient("P001").sessions.last().view)
        assertEquals(before, store.state.value.followups.count { it.patient == "P001" && it.priority == "missing" })
    }

    @Test
    fun sessionWithoutPhotoOpensMissingPhotoFollowUp() {
        val store = ClinicStore()
        store.recordTreatmentSession("P001", input(photoPath = null), doctor)
        val followUp = store.state.value.followups.first()
        assertEquals("Thiếu ảnh mốc đánh giá", followUp.type)
        assertTrue(store.patient("P001").sessions.last().image.isEmpty())
    }

    private fun input(photoPath: String?) = TreatmentSessionInput(
        date = DAY,
        type = "Chăm sóc & laser theo chỉ định",
        note = "Da ổn",
        aftercare = "Dưỡng ẩm và chống nắng.",
        region = "Mặt",
        view = "Má trái",
        protocolId = null,
        nextVisit = addDays(DAY, 30),
        hasPhoto = photoPath != null,
        photoConsent = true,
        photoPath = photoPath,
    )
}
