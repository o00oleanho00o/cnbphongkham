package com.pema.clinic.feature.aftercare

import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.patient
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FollowUpInboxLogicTest {
    @Test
    fun metricsAndFiltersMatchWebFollowups() {
        val state = ClinicSeed.initial()

        val all = followUpInboxState(state)
        assertEquals(5, all.openCount)
        assertEquals(3, all.doctorCount)
        assertEquals(2, all.missedCount)
        assertEquals(2, all.imageCount)
        assertEquals(1, all.urgentCount)
        assertEquals(1, all.overdueCount)
        assertEquals(5, all.rows.size)

        val images = followUpInboxState(state, filter = FollowUpInboxFilter.Image)
        assertEquals(listOf("F001", "F005"), images.rows.map { it.id })

        val symptoms = followUpInboxState(state, filter = FollowUpInboxFilter.Urgent)
        assertEquals(listOf("F002"), symptoms.rows.map { it.id })

        val overdue = followUpInboxState(state, filter = FollowUpInboxFilter.Overdue)
        assertEquals(listOf("F003"), overdue.rows.map { it.id })
    }

    @Test
    fun doctorOnlySeesOwnedPatientsLikeStaffOwns() {
        val state = ClinicSeed.initial()
        val staff = StaffContext(role = "doctor", name = "BS. Tâm", doctorId = "D0", doctorName = "BS. Tâm")
        val doctor = followUpInboxState(
            state,
            staff = staff,
        )

        assertTrue(doctor.rows.isNotEmpty())
        assertTrue(doctor.rows.all { row -> staff.owns(state.patient(row.patientId), state) })
    }

    @Test
    fun shortDayMonthMatchesInboxSubtext() {
        assertEquals("20/9", shortDayMonth("2026-09-20T08:42:00"))
    }
}
