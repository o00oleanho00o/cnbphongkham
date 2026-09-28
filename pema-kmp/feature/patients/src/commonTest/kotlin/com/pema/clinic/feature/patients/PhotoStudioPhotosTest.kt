package com.pema.clinic.feature.patients

import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.TreatmentSessionRecord
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Web `photos(p)`: real session images for the selected view; first = before, last = after. */
class PhotoStudioPhotosTest {
    private val base = ClinicStore().patient("P001")

    @Test
    fun illustrationsWhenNoRealPhotosForTheView() {
        val state = photoStudioState(base, "Chính diện")
        assertNull(state.before)
        assertNull(state.after)
        assertEquals(0, state.photoCount)
        assertTrue(state.notice.startsWith("Chưa kiểm định căn chỉnh ảnh"))
    }

    @Test
    fun realPhotosAreFilteredByViewInSessionOrder() {
        val patient = base.copy(
            sessions = base.sessions + listOf(
                TreatmentSessionRecord("a", "2026-09-06", "Laser", view = "Chính diện", image = "/p/a.jpg"),
                TreatmentSessionRecord("b", "2026-09-13", "Laser", view = "Má trái", image = "/p/b.jpg"),
                TreatmentSessionRecord("c", "2026-09-20", "Laser", view = "Chính diện", image = "/p/c.jpg"),
            ),
        )
        val state = photoStudioState(patient, "Chính diện")
        assertEquals("/p/a.jpg", state.before?.path)
        assertEquals("/p/c.jpg", state.after?.path)
        assertEquals(2, state.photoCount)
        assertTrue(state.notice.startsWith("2 ảnh gắn với buổi điều trị, lọc cùng góc khai báo: Chính diện."))
        assertEquals("/p/b.jpg", photoStudioState(patient, "Má trái").after?.path)
    }
}
