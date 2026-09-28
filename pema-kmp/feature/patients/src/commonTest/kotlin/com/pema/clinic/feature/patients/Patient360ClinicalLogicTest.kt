package com.pema.clinic.feature.patients

import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.patient
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class Patient360ClinicalLogicTest {
    @Test
    fun planMilestonesShowLatestCompletedAndNextWithoutFutureNoise() {
        assertEquals(
            listOf(
                PlanMilestone("Buổi 2 · Đã hoàn tất", "Đã ghi nhận ảnh và hướng dẫn chăm sóc", "check_circle"),
                PlanMilestone("Buổi 3 · Tiếp theo", "Cần đánh giá da trước khi thực hiện", "radio_button_checked"),
            ),
            planMilestones(completed = 2, total = 5),
        )
        assertEquals(
            listOf(PlanMilestone("Buổi 1 · Tiếp theo", "Cần đánh giá da trước khi thực hiện", "radio_button_checked")),
            planMilestones(completed = 0, total = 3),
        )
    }

    @Test
    fun planOverviewComputesCriteriaAndClinicalVisibilityFromPatientState() {
        val patient = ClinicSeed.initial().patient("P001")
        val ownerState = planOverviewState(patient, StaffContext(role = "owner"))
        assertEquals("Chính diện · 2/5", ownerState.photoCriterion)
        assertEquals("Chưa gửi", ownerState.reportedOutcome)
        assertEquals(patient.doctor, ownerState.doctor)
        assertTrue(ownerState.canClinical)

        val careState = planOverviewState(patient, StaffContext(role = "care", name = "Mai Anh", doctorId = null, doctorName = null))
        assertFalse(careState.canClinical)
    }

    @Test
    fun sessionNoticeAndProtocolMatchWebClinicalRules() {
        val patient = ClinicSeed.initial().patient("P001")
        assertTrue(sessionNotice(patient).startsWith("Buổi 3/5 · BS. Tâm\nHồ sơ có cảnh báo:"))
        assertEquals("Laser CO2 · D+1 / D+3 / D+7 / D+30", defaultProtocol(patient))
        assertEquals(patient.procedure, defaultSessionType(patient))
    }
}
