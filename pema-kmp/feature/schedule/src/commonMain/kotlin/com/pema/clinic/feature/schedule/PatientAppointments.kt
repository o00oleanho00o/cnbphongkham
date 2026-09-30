package com.pema.clinic.feature.schedule

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.Gap
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.Appointment
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.ClinicPatient
import com.pema.clinic.shared.clinic.confirmPatientAttendance
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.viDate

fun NavGraphBuilder.patientAppointmentsGraph(deps: FeatureDeps) {
    composable(Routes.PatientAppointments) {
        PatientAppointmentsRoute(deps)
    }
}

@Immutable
internal data class PatientAppointmentHeroUiState(
    val id: String,
    val title: String,
    val sub: String,
    val confirmed: Boolean,
) {
    val confirmText: String get() = if (confirmed) "Đã xác nhận lịch hẹn" else "Xác nhận tôi sẽ đến"
    val confirmEnabled: Boolean get() = !confirmed
    val confirmedMessage: String get() =
        "Lịch hẹn ngày ${title.substringAfter("· ").trim()} lúc ${title.substringBefore("·").trim()} đã được xác nhận. Hẹn gặp bạn tại Pema."
}

@Immutable
internal data class PatientAppointmentTileUiState(
    val id: String,
    val title: String,
    val sub: String,
    val icon: String,
)

@Immutable
internal data class PatientAppointmentsUiState(
    val title: String = Routes.appBarTitleOf(Routes.PatientAppointments),
    val upcoming: PatientAppointmentHeroUiState?,
    val scheduled: List<PatientAppointmentTileUiState>,
    val past: List<PatientAppointmentTileUiState>,
)

@Composable
private fun PatientAppointmentsRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinicState by deps.clinicStore.state.collectAsStateWithLifecycle()
    val patientId = remember(session) { deps.sessionStore.selectedPatientId() }
    val state = buildPatientAppointmentsState(clinicState, patientId)
    val messenger = rememberPemaMessenger()

    PatientAppointmentsScreen(
        state = state,
        onConfirm = {
            try {
                val result = deps.clinicStore.confirmPatientAttendance(patientId, state.upcoming?.id)
                messenger.show(result.toast)
            } catch (error: ClinicError) {
                messenger.show(error.message ?: "Không thể xác nhận lịch hẹn")
            }
        },
        onOpenPast = { deps.navigator.go(Routes.ProgressPhotos) },
    )
}

internal fun buildPatientAppointmentsState(
    state: ClinicState,
    patientId: String,
): PatientAppointmentsUiState {
    val patient = state.patient(patientId)
    val activeAppointments = state.operations.appointments
        .filter { it.patient == patient.id && it.activeForPatient() && it.status != "completed" && it.date >= DAY }
        .sortedWith(compareBy<Appointment> { it.date }.thenBy { it.time })
    val upcoming = activeAppointments.firstOrNull()?.let { appointment ->
        PatientAppointmentHeroUiState(
            id = appointment.id,
            title = "${appointment.time} · ${viDate(appointment.date)}",
            sub = "${serviceName(state, appointment)} · ${doctorName(state, appointment)}",
            confirmed = appointment.status == "confirmed",
        )
    }
    return PatientAppointmentsUiState(
        upcoming = upcoming,
        scheduled = activeAppointments.map { appointment ->
            PatientAppointmentTileUiState(
                id = appointment.id,
                title = "${viDate(appointment.date)} · ${appointment.time}",
                sub = "${serviceName(state, appointment)} · ${appointment.duration} phút · ${doctorName(state, appointment)}",
                icon = "calendar_today",
            )
        },
        past = patient.pastSessionTiles(),
    )
}

@Composable
internal fun PatientAppointmentsScreen(
    state: PatientAppointmentsUiState,
    onConfirm: () -> Unit,
    onOpenPast: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaSection("Sắp tới")
        val upcoming = state.upcoming
        if (upcoming == null) {
            PemaEmpty("Chưa có lịch hẹn", icon = "calendar_month")
            Gap(8)
            PemaPrimary("Xác nhận tôi sẽ đến", onClick = null)
        } else {
            PemaHero(upcoming.title, upcoming.sub, "calendar_month")
            Gap(8)
            PemaPrimary(upcoming.confirmText, onClick = if (upcoming.confirmEnabled) onConfirm else null)
            if (upcoming.confirmed) PemaNotice(upcoming.confirmedMessage)
        }

        PemaSection("Các lịch đã đặt")
        if (state.scheduled.isEmpty()) {
            PemaEmpty("Chưa có lịch đã đặt.", icon = "calendar_today")
        } else {
            state.scheduled.forEach { item ->
                PemaTile(item.title, item.sub, item.icon, onClick = null)
            }
        }

        PemaSection("Lịch đã qua")
        if (state.past.isEmpty()) {
            PemaEmpty("Chưa có lịch đã qua.", icon = "check_circle")
        } else {
            state.past.forEach { item ->
                PemaTile(item.title, item.sub, item.icon, onClick = onOpenPast)
            }
        }
        PemaNotice("Cần đổi lịch, hãy nhắn cho đội ngũ Pema trước ít nhất 4 giờ.")
    }
}

private fun serviceName(state: ClinicState, appointment: Appointment): String =
    state.operations.services.find { it.id == appointment.service }?.name ?: appointment.service

private fun doctorName(state: ClinicState, appointment: Appointment): String =
    state.operations.doctors.find { it.id == appointment.doctor }?.name ?: appointment.doctor

private fun Appointment.activeForPatient(): Boolean = status !in setOf("cancelled", "missed")

private fun ClinicPatient.pastSessionTiles(): List<PatientAppointmentTileUiState> =
    sessions.sortedByDescending { it.date }.mapIndexed { index, session ->
        PatientAppointmentTileUiState(
            id = session.id,
            title = "Buổi ${completed - index} · ${session.type}",
            sub = "${viDate(session.date)} · Đã hoàn tất",
            icon = "check_circle",
        )
    }
