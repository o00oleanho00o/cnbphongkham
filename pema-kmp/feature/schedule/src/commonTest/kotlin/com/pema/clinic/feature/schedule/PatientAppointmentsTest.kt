package com.pema.clinic.feature.schedule

import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.confirmPatientAttendance
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PatientAppointmentsTest {
    @Test
    fun buildsPatientSideAppointmentsFromSelectedClinicPatient() {
        val ui = buildPatientAppointmentsState(ClinicSeed.initial(), "P001")

        assertEquals("Lịch hẹn", ui.title)
        assertEquals("08:00 · 20/9/2026", ui.upcoming!!.title)
        assertEquals("Tái khám & đánh giá · BS. Tâm", ui.upcoming.sub)
        assertEquals("20/9/2026 · 08:00", ui.scheduled.first().title)
        assertEquals("Tái khám & đánh giá · 30 phút · BS. Tâm", ui.scheduled.first().sub)
        assertTrue(ui.scheduled.size >= 2)
        assertTrue(ui.past.first().title.startsWith("Buổi 2 ·"))
        assertEquals("6/9/2026 · Đã hoàn tất", ui.past.first().sub)
    }

    @Test
    fun confirmedAppointmentDisablesPrimaryAndShowsConfirmedText() {
        val store = ClinicStore()
        store.confirmPatientAttendance("P001")

        val ui = buildPatientAppointmentsState(store.state.value, "P001")

        assertTrue(ui.upcoming!!.confirmed)
        assertFalse(ui.upcoming.confirmEnabled)
        assertEquals("Đã xác nhận lịch hẹn", ui.upcoming.confirmText)
        assertEquals(
            "Lịch hẹn ngày 20/9/2026 lúc 08:00 đã được xác nhận. Hẹn gặp bạn tại Pema.",
            ui.upcoming.confirmedMessage,
        )
    }
}
