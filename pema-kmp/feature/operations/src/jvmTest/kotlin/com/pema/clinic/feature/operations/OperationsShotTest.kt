package com.pema.clinic.feature.operations

import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.addDays
import kotlin.test.Test

class OperationsShotTest {
    private val state = ClinicStore().state.value

    @Test
    fun i1Dashboard() {
        shotVsCanvas("I1") {
            OperationsDashboardScreen(state = dashboardState(state), onBack = {})
        }
    }

    @Test
    fun i2Reception() {
        shotVsCanvas("I2") {
            ReceptionScreen(state = receptionState(state), onBack = {})
        }
    }

    @Test
    fun i3RoomSchedule() {
        shotVsCanvas("I3") {
            RoomScheduleScreen(state = roomScheduleState(state, DAY, "all"), onBack = {})
        }
    }

    @Test
    fun i4AppointmentForm() {
        shotVsCanvas("I4") {
            AppointmentFormScreen(
                state = appointmentFormState(
                    state = state,
                    id = null,
                    patient = "P001",
                    serviceId = "S0",
                    doctorId = "D0",
                    roomId = "R0",
                    date = addDays(DAY, 2),
                    selectedSlot = "10:30",
                ),
                onBack = {},
            )
        }
    }

    @Test
    fun i8RoomBlock() {
        shotVsCanvas("I8") {
            RoomBlockScreen(
                state = roomBlockState(
                    state = state,
                    room = "R2",
                    date = addDays(DAY, 1),
                    start = "14:00",
                    end = "15:00",
                    reason = "Bảo trì thiết bị laser",
                ),
                onBack = {},
            )
        }
    }

    @Test
    fun i9ServiceEdit() {
        val service = state.operations.services.first { it.id == "S2" }
        shotVsCanvas("I9") {
            ServiceEditScreen(
                state = serviceEditState(
                    state = state,
                    id = service.id,
                    name = service.name,
                    duration = service.duration.toString(),
                    buffer = service.buffer.toString(),
                    price = service.price.toString(),
                    active = service.active,
                ),
                onBack = {},
            )
        }
    }
}
