package com.pema.clinic.feature.operations

import com.pema.clinic.shared.clinic.AppointmentInput
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.CrmInput
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.addDays
import com.pema.clinic.shared.clinic.crmQueue
import com.pema.clinic.shared.clinic.prepareCrmBooking
import com.pema.clinic.shared.clinic.saveAppointment
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class OperationsLogicTest {
    private val state = ClinicStore().state.value

    @Test
    fun dashboardNumbersMatchSeededWebDashboard() {
        val ui = dashboardState(state)

        assertEquals("31", ui.todayAppointments)
        assertEquals("0/0", ui.arrivedAndWaiting)
        assertEquals("0", ui.missed)
        assertEquals("13.500.000 ₫", ui.invoiceTotal)
        assertEquals("46", ui.carePatients)
        assertEquals("10", ui.overduePatients)
        assertEquals("8", ui.atRiskPatients)
        assertEquals(3, ui.careRows.size)
    }

    @Test
    fun receptionFilterUsesWebStatusBuckets() {
        val appointments = state.operations.appointments.filter { it.date == DAY }

        assertEquals(31, applyReceptionFilter(appointments, ReceptionFilter.All).size)
        assertEquals(31, applyReceptionFilter(appointments, ReceptionFilter.NotArrived).size)
        assertEquals(0, applyReceptionFilter(appointments, ReceptionFilter.Waiting).size)
        assertEquals(0, applyReceptionFilter(appointments, ReceptionFilter.Missed).size)
    }

    @Test
    fun scheduleGroupsAppointmentsByRoomAndKeepsCounts() {
        val ui = roomScheduleState(state, DAY, "all")

        val roomsByName = ui.sections.associate { it.roomName to it.count }
        assertEquals(8, roomsByName["Khám da liễu"])
        assertEquals(8, roomsByName["Tư vấn chuyên sâu"])
        assertEquals(7, roomsByName["Laser & thủ thuật"])
        assertEquals(8, roomsByName["Chăm sóc da"])
        assertTrue(ui.notice.contains("6 lịch chờ xếp"))
    }

    @Test
    fun bookingSlotValidityComesFromDomainValidation() {
        val ui = appointmentFormState(
            state = state,
            id = null,
            patient = "P001",
            serviceId = "S0",
            doctorId = "D0",
            roomId = "R0",
            date = addDays(DAY, 2),
            selectedSlot = "10:30",
        )

        assertFalse(ui.slots.first { it.time == "09:00" }.valid)
        assertTrue(ui.slots.first { it.time == "10:30" }.valid)
        assertNotNull(findFirstValidSlot(state, ui))
    }

    @Test
    fun crmTaskBookingPathMarksTaskBookedAfterAppointmentSave() {
        val store = ClinicStore()
        val task = store.state.value.crmQueue(allDates = true).first { it.type != "birthday" }
        val input = CrmInput(
            channel = "Gọi điện",
            outcome = "booked",
            owner = task.owner,
            note = "Khách đồng ý đặt lịch theo tư vấn CSKH.",
            nextActionType = "book",
        )
        store.prepareCrmBooking(task.id, input, task.patientId, StaffContext(role = "care", name = "Mai Anh"))
        val form = appointmentFormState(
            state = store.state.value,
            id = null,
            patient = task.patientId,
            serviceId = "S0",
            doctorId = "D0",
            roomId = "R0",
            date = addDays(DAY, 2),
            selectedSlot = "10:30",
        )
        val slot = findFirstValidSlot(store.state.value, form) ?: error("Expected a valid slot")

        val appointment = store.saveAppointment(
            AppointmentInput(
                patient = task.patientId,
                service = form.service,
                doctor = form.doctor,
                room = form.room,
                date = form.date,
                time = slot,
                crmTaskId = task.id,
                crmInput = crmBookingInput(store, store.state.value, task.id),
            ),
        )

        val updatedTask = store.state.value.crmTasks.first { it.id == task.id }
        assertEquals("resolved", updatedTask.status)
        assertEquals("booked", updatedTask.resolution)
        assertEquals(appointment.id, updatedTask.relatedAppointmentId)
        assertTrue(store.state.value.crmActivities.any { it.taskId == task.id && it.relatedAppointmentId == appointment.id })
    }
}
