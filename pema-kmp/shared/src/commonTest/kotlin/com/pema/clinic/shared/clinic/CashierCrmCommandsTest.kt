package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CashierCrmCommandsTest {
    @Test
    fun prepareCrmBookingUsesTheSameGuardAsAppointmentCompletion() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first()
        val input = CrmInput(
            channel = "Gọi điện",
            outcome = "booked",
            owner = task.owner,
            note = "Khách đồng ý đặt lịch theo tư vấn CSKH.",
            nextActionType = "book",
        )

        store.prepareCrmBooking(task.id, input, task.patientId, StaffContext(role = "care", name = "Mai Anh"))

        assertTrue(store.state.value.crmTasks.any { it.id == task.id && it.status == task.status })
    }

    @Test
    fun prepareCrmBookingRejectsWrongPatientAndMissingNote() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first()
        val input = CrmInput("Gọi điện", "booked", task.owner, "Đồng ý đặt lịch", nextActionType = "book")

        assertFailsWith<ClinicError> { store.prepareCrmBooking(task.id, input, "P999") }
        assertFailsWith<ClinicError> {
            store.prepareCrmBooking(task.id, input.copy(note = ""), task.patientId)
        }
    }
}
