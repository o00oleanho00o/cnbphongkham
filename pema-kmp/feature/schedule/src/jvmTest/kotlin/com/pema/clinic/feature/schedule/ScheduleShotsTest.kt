package com.pema.clinic.feature.schedule

import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import kotlin.test.Test

class ScheduleShotsTest {
    @Test
    fun f8Booking() {
        shotVsCanvas("F8") {
            BookingScreen(
                state = BookingUiState(
                    patientName = "Nguyễn Thu Hà",
                    day = "22/9/2026",
                    appointment = "10:30",
                    confirmed = false,
                ),
                onDayPicked = {},
                onSlotClick = {},
                onConfirm = {},
                onBack = {},
            )
        }
    }

    @Test
    fun f9AppointmentDetail() {
        shotVsCanvas("F9") {
            AppointmentScreen(
                state = AppointmentUiState(
                    title = Routes.titleOf(Routes.AppointmentDetail),
                    patientName = "Nguyễn Thu Hà",
                    appointment = "10:30",
                    day = "22/9/2026",
                    confirmed = false,
                    showClinicActions = true,
                ),
                onConfirmAttendance = {},
                onReschedule = {},
                onOpenPatient360 = {},
                onBack = {},
            )
        }
    }

    @Test
    fun f13Services() {
        shotVsCanvas("F13") {
            ServicesScreen(onServiceClick = {}, onBack = {})
        }
    }

    @Test
    fun f14Resources() {
        shotVsCanvas("F14") {
            ResourcesScreen(onResourceClick = {}, onBack = {})
        }
    }

    @Test
    fun g3MyAppointments() {
        shotVsCanvas("G3") {
            AppointmentScreen(
                state = AppointmentUiState(
                    title = Routes.titleOf(Routes.MyAppointments),
                    patientName = "Nguyễn Thu Hà",
                    appointment = "10:30",
                    day = "22/9/2026",
                    confirmed = false,
                    showClinicActions = false,
                ),
                onConfirmAttendance = {},
                onReschedule = {},
                onOpenPatient360 = {},
                onBack = {},
            )
        }
    }
}
