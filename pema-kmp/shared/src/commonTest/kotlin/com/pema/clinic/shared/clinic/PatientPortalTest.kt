package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PatientPortalTest {
    @Test
    fun confirmAttendanceMatchesPatientMobileCommand() {
        val store = ClinicStore()

        val result = store.confirmPatientAttendance("P001")

        assertEquals("Đã xác nhận lịch hẹn", result.toast)
        assertEquals("A0-0", result.appointmentId)
        val state = store.state.value
        assertEquals("confirmed", state.operations.appointments.first { it.id == "A0-0" }.status)
        val patient = state.patient("P001")
        assertEquals(
            "Lịch hẹn ngày 20/9/2026 lúc 08:00 đã được xác nhận. Hẹn gặp bạn tại Pema.",
            patient.messages.last().text,
        )
        assertEquals("Người bệnh đã xác nhận lịch hẹn", patient.events.first().title)
        assertEquals("Pema Care Team", patient.events.first().by)
    }

    @Test
    fun journeyTimelineReturnsRecentPatientEventsInWebOrder() {
        val patient = ClinicSeed.initial().patient("P001")

        val timeline = patientJourneyTimeline(patient)

        assertEquals("2/5 buổi · tiến độ số buổi, không phải mức cải thiện da", timeline.heroSubText)
        assertEquals(4, timeline.recentCount)
        assertEquals("Cập nhật gần đây · 4 mốc", timeline.sectionTitle)
        assertEquals(
            listOf(
                "13/9/2026|Cập nhật tại nhà đã được xem|chat_bubble",
                "6/9/2026|Hoàn tất buổi 2/5|check_circle",
                "6/9/2026|Bộ ảnh theo dõi · chính diện|photo_camera",
            ),
            timeline.updates.map { "${it.dateLabel}|${it.title}|${it.icon}" },
        )
        assertTrue(timeline.updates.first().detail.contains("Đỏ nhẹ"))
    }
}
