package com.pema.clinic.feature.care

import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.CrmInput
import com.pema.clinic.shared.clinic.crmQueue
import com.pema.clinic.shared.clinic.prepareCrmBooking
import com.pema.clinic.shared.clinic.resolveCrmTask
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class CareRecordLogicTest {
    @Test
    fun careRecordStateUsesSelectedPatientOpenTask() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first()
        val state = buildCareRecordState(store.state.value, task.patientId)

        assertEquals(task.patientId, state.patientId)
        assertEquals(task.id, state.taskId)
        assertTrue(state.groupLabel.isNotBlank())
        assertTrue(state.remainingSessions >= 0)
    }

    @Test
    fun resolvingNonBookingOutcomeRecordsActivityAndClosesTask() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first { it.type != "birthday" }
        val activity = store.resolveCrmTask(
            task.id,
            CrmInput(
                channel = "Gọi điện",
                outcome = "no_need",
                owner = task.owner,
                note = "Đã liên hệ, khách chưa có nhu cầu quay lại.",
                nextActionType = "call",
            ),
        )

        assertEquals(task.id, activity.taskId)
        assertEquals("no_need", activity.outcome)
        assertNotNull(store.state.value.crmTasks.first { it.id == task.id }.resolvedAt)
    }

    @Test
    fun bookedOutcomeIsGuardedForAppointmentFormInsteadOfResolvingImmediately() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first()
        val input = CrmInput("Gọi điện", "booked", task.owner, "Khách đồng ý đặt lịch.", nextActionType = "book")

        assertFailsWith<ClinicError> { store.resolveCrmTask(task.id, input) }
        store.prepareCrmBooking(task.id, input, task.patientId)
        assertEquals("open", store.state.value.crmTasks.first { it.id == task.id }.status)
    }
}
