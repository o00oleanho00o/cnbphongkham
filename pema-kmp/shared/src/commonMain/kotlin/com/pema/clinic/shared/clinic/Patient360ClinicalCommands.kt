package com.pema.clinic.shared.clinic

import androidx.compose.runtime.Immutable

@Immutable
data class ConsultDraftResult(val draft: String)

@Immutable
data class PlanEditInput(val name: String, val total: Int)

@Immutable
data class TreatmentSessionInput(
    val date: String,
    val type: String,
    val note: String,
    val aftercare: String,
    val region: String,
    val view: String,
    val protocolId: String?,
    val nextVisit: String?,
    val hasPhoto: Boolean,
    val photoConsent: Boolean,
)

/** Web `generate-note`: creates a doctor-editable draft, but does not write a clinical event yet. */
fun ClinicStore.generateConsultDraft(patientId: String, input: String, staff: StaffContext = StaffContext()): ConsultDraftResult {
    staff.assertCan("clinical")
    return transact { state ->
        val patient = state.patient(patientId)
        if (!staff.owns(patient, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        val text = input.trim()
        if (text.isEmpty()) throw ClinicError("Hãy nhập vài ý chính trước")
        val draft = "Bản nháp ghi chú · ${viDate(DAY)}: $text " +
            "Đáp ứng cần được đối chiếu với ảnh mốc và phản hồi của người bệnh. " +
            "Kế hoạch tiếp theo cần bác sĩ xác nhận."
        val next = state.updatePatient(patientId) { it.copy(notes = draft) }
            .log("Tạo bản nháp ghi chú", patientId)
        next to ConsultDraftResult(draft)
    }
}

/** Web `approve-note`: stores the edited draft as a timeline event and clears the transient draft. */
fun ClinicStore.approveConsultDraft(patientId: String, editedDraft: String, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("clinical")
    transact { state ->
        val patient = state.patient(patientId)
        if (!staff.owns(patient, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        val text = editedDraft.trim()
        if (text.isEmpty()) throw ClinicError("Bản nháp không được để trống")
        val next = state
            .addEvent(patientId, "consult", "Ghi chú tư vấn đã được duyệt", text, patient.doctor, DAY)
            .updatePatient(patientId) { it.copy(notes = "") }
            .log("Duyệt ghi chú tư vấn", patientId)
        next to Unit
    }
}

/** Web `approve-brief`: records the doctor-approved AI brief with audit/source context. */
fun ClinicStore.approveAiBrief(patientId: String, briefText: String, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("clinical")
    transact { state ->
        val patient = state.patient(patientId)
        if (!staff.owns(patient, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        val text = briefText.trim()
        if (text.isEmpty()) throw ClinicError("Brief không được để trống")
        val next = state
            .addEvent(patientId, "consult", "Brief AI đã được duyệt", text, patient.doctor, DAY)
            .log("Duyệt brief AI mô phỏng", patientId)
        next to Unit
    }
}

/** Web `save-plan`: renames the active plan and updates the expected total without touching completed sessions. */
fun ClinicStore.updateTreatmentPlan(patientId: String, input: PlanEditInput, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("clinical")
    transact { state ->
        val patient = state.patient(patientId)
        if (!staff.owns(patient, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        val name = input.name.trim()
        if (name.isEmpty() || input.total < patient.completed || input.total > 20) {
            throw ClinicError("Tên và số buổi chưa hợp lệ")
        }
        val next = state.updatePatient(patientId) { it.copy(plan = name, total = input.total) }
            .addEvent(patientId, "plan", "Điều chỉnh kế hoạch", "$name · ${input.total} buổi dự kiến", patient.doctor, DAY)
            .log("Điều chỉnh kế hoạch", patientId)
            .deriveCrmTasks(state.crmTasks)
        next to Unit
    }
}

/** Web `save-session`: saves one treatment session, sends aftercare and refreshes CRM protocol follow-ups. */
fun ClinicStore.recordTreatmentSession(patientId: String, input: TreatmentSessionInput, staff: StaffContext = StaffContext()): TreatmentSessionRecord {
    staff.assertCan("clinical")
    return transact { state ->
        val patient = state.patient(patientId)
        if (!staff.owns(patient, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        if (patient.completed >= patient.total) throw ClinicError("Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch trước khi thêm buổi mới.")
        val note = input.note.trim()
        val aftercare = input.aftercare.trim()
        if (note.isEmpty()) throw ClinicError("Hãy ghi đánh giá trước buổi")
        if (aftercare.isEmpty()) throw ClinicError("Hãy nhập hướng dẫn chăm sóc sau buổi")
        if (!dateOk(input.date) || input.date > DAY || (patient.lastVisit != null && input.date < patient.lastVisit)) {
            throw ClinicError("Ngày buổi phải hợp lệ, từ buổi trước đến ngày demo 20/09/2026.")
        }
        if (input.hasPhoto && !input.photoConsent) throw ClinicError("Cần xác nhận đồng ý ảnh khi lưu ảnh mốc")

        val session = TreatmentSessionRecord(
            id = "S-${patient.id}-${patient.sessions.size + 1}",
            date = input.date,
            type = input.type.ifBlank { patient.procedure },
            note = note,
            reviewed = true,
            view = input.view,
            region = input.region,
            image = if (input.hasPhoto) "placeholder" else "",
            aftercare = aftercare,
            protocolId = input.protocolId,
        )
        var next = state.updatePatient(patientId) { current ->
            current.copy(
                completed = current.completed + 1,
                lastVisit = input.date,
                aftercare = aftercare,
                photoConsent = current.photoConsent || input.photoConsent,
                sessions = current.sessions + session,
                messages = current.messages + PatientMessage(
                    from = "clinic",
                    text = "Pema đã cập nhật hướng dẫn chăm sóc sau buổi: $aftercare",
                    date = "20/09 · vừa xong",
                ),
                crm = current.crm.copy(
                    recommendationAt = input.nextVisit?.takeIf { dateOk(it) } ?: addDays(input.date, 30),
                    expectedVisitSource = "doctor_recommendation",
                    expectedVisitReason = "Bác sĩ hẹn đánh giá sau buổi",
                ),
            )
        }
        next = next
            .addEvent(patientId, "session", "Hoàn tất buổi ${patient.completed + 1}/${patient.total}", "${session.type}. $note", patient.doctor, input.date)
            .addEvent(patientId, "care", "Đã gửi hướng dẫn sau buổi", aftercare, patient.doctor, input.date)
        if (!input.hasPhoto) {
            next = next.copy(
                followups = listOf(
                    FollowUp(
                        id = "F-${patient.id}-${patient.sessions.size + 1}",
                        patient = patientId,
                        type = "Thiếu ảnh mốc đánh giá",
                        priority = "missing",
                        symptom = "Buổi điều trị vừa lưu chưa có ảnh mốc.",
                        date = "${DAY}T09:00:00+07:00",
                        image = null,
                        status = "open",
                        owner = "Điều dưỡng Hương",
                    ),
                ) + next.followups,
            )
        }
        val appointments = next.operations.appointments.map { appointment ->
            if (appointment.patient == patientId && appointment.date == input.date && appointment.status in setOf("arrived", "in_progress")) {
                appointment.copy(status = "completed")
            } else {
                appointment
            }
        }
        next = next.copy(operations = next.operations.copy(appointments = appointments))
            .sync(patientId)
            .log("Ghi buổi điều trị", patientId)
            .deriveCrmTasks(next.crmTasks)
        next to session
    }
}
