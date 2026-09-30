package com.pema.clinic.shared.clinic

import androidx.compose.runtime.Immutable

/** Result of a patient-side portal command, including the toast copied from the web demo. */
@Immutable
data class PatientPortalCommandResult(
    val toast: String,
    val message: String,
    val appointmentId: String,
)

/** Patient-facing timeline row used by the Pema Care journey screen. */
@Immutable
data class PatientJourneyUpdate(
    val dateLabel: String,
    val title: String,
    val detail: String,
    val kind: String,
    val icon: String,
)

/** Pure patient-side journey projection for canvas K3. */
@Immutable
data class PatientJourneyTimeline(
    val heroSubText: String,
    val recentCount: Int,
    val updates: List<PatientJourneyUpdate>,
) {
    val sectionTitle: String get() = "Cập nhật gần đây · $recentCount mốc"
}

/**
 * Confirms the next active patient appointment from Pema Care.
 *
 * This mirrors `patient.js` confirm-attendance: status becomes `confirmed`, a patient-visible
 * message is appended, and the patient timeline receives "Người bệnh đã xác nhận lịch hẹn".
 */
fun ClinicStore.confirmPatientAttendance(
    patientId: String,
    appointmentId: String? = null,
): PatientPortalCommandResult = transact { state ->
    val patient = state.patient(patientId)
    val appointment = appointmentId
        ?.let { id -> state.operations.appointments.find { it.id == id && it.patient == patient.id } }
        ?: state.operations.appointments
            .filter { it.patient == patient.id && it.isActive() && it.status != "completed" && it.date >= DAY }
            .sortedWith(compareBy<Appointment> { it.date }.thenBy { it.time })
            .firstOrNull()
        ?: throw ClinicError("Chưa có lịch hẹn để xác nhận")

    if (!appointment.isActive() || appointment.status == "completed") {
        throw ClinicError("Không thể chuyển trạng thái lịch này.")
    }

    val time = appointment.time.ifBlank { "10:30" }
    val message = "Lịch hẹn ngày ${viDate(appointment.date)} lúc $time đã được xác nhận. Hẹn gặp bạn tại Pema."
    var next = state.copy(
        operations = state.operations.copy(
            appointments = state.operations.appointments.map {
                if (it.id == appointment.id) it.copy(status = "confirmed") else it
            },
        ),
    )
    next = next.updatePatient(patient.id) {
        it.copy(messages = it.messages + PatientMessage("clinic", message, "20/09 · vừa xong"))
    }.addEvent(
        patientId = patient.id,
        kind = "appointment",
        title = "Người bệnh đã xác nhận lịch hẹn",
        detail = "Xác nhận từ patient app.",
        by = "Pema Care Team",
        date = appointment.date,
    ).log("Xác nhận lịch hẹn từ patient app", patient.id)
        .deriveCrmTasks(next.crmTasks)

    next to PatientPortalCommandResult("Đã xác nhận lịch hẹn", message, appointment.id)
}

/**
 * Returns the exact patient-mobile "Hành trình · cập nhật" projection:
 * current event order, capped recent list, `d/M/yyyy` labels, count, and hero sub text.
 */
fun patientJourneyTimeline(patient: ClinicPatient, limit: Int = 3): PatientJourneyTimeline {
    val updates = patient.events
        .take(limit.coerceAtLeast(0))
        .map { event ->
            PatientJourneyUpdate(
                dateLabel = viDate(event.date),
                title = event.title,
                detail = event.detail,
                kind = event.kind,
                icon = when (event.kind) {
                    "photo" -> "photo_camera"
                    "followup" -> "chat_bubble"
                    "appointment" -> "event"
                    else -> "check_circle"
                },
            )
        }
    return PatientJourneyTimeline(
        heroSubText = "${patient.completed}/${patient.total} buổi · tiến độ số buổi, không phải mức cải thiện da",
        recentCount = patient.events.size,
        updates = updates,
    )
}
