package com.pema.clinic.feature.schedule

import com.pema.clinic.core.ui.shots.shotVsCanvas
import kotlin.test.Test

class PatientAppointmentsShotTest {
    @Test
    fun k1PatientAppointments() {
        shotVsCanvas("K1") {
            PatientAppointmentsScreen(
                state = PatientAppointmentsUiState(
                    upcoming = PatientAppointmentHeroUiState(
                        id = "A-K1",
                        title = "10:30 · 22/9/2026",
                        sub = "Tái khám & đánh giá · BS. Tâm",
                        confirmed = false,
                    ),
                    scheduled = listOf(
                        PatientAppointmentTileUiState(
                            id = "A-K1",
                            title = "22/9/2026 · 10:30",
                            sub = "Tái khám & đánh giá · 30 phút · BS. Tâm",
                            icon = "calendar_today",
                        ),
                        PatientAppointmentTileUiState(
                            id = "A-K2",
                            title = "06/10/2026 · 09:00",
                            sub = "Laser theo chỉ định · 45 phút · BS. An",
                            icon = "calendar_today",
                        ),
                    ),
                    past = listOf(
                        PatientAppointmentTileUiState(
                            id = "S-K1",
                            title = "Buổi 2 · Chăm sóc & laser",
                            sub = "6/9/2026 · Đã hoàn tất",
                            icon = "check_circle",
                        ),
                    ),
                ),
                onConfirm = {},
                onOpenPast = {},
                onBack = {},
            )
        }
    }
}
