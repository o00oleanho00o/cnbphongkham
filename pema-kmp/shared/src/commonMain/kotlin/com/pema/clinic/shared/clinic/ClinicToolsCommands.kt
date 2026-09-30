package com.pema.clinic.shared.clinic

import androidx.compose.runtime.Immutable

@Immutable
data class NewClinicPatientInput(
    val name: String,
    val age: String = "28",
    val concern: String = "Nám · tăng sắc tố",
)

@Immutable
data class FollowUpResolution(
    val followUp: FollowUp,
    val patient: ClinicPatient,
    val reply: String,
)

fun ClinicStore.createPatient(input: NewClinicPatientInput): ClinicPatient = transact { state ->
    val name = input.name.trim()
    if (name.isEmpty()) throw ClinicError("Nhập tên người bệnh")
    val id = "P" + (state.patients.size + 1).toString().padStart(3, '0')
    val patient = ClinicPatient(
        id = id,
        name = name,
        age = input.age.toIntOrNull()?.takeIf { it != 0 } ?: 28,
        gender = "Chưa xác nhận",
        phone = "Chưa nhập",
        concern = input.concern.trim().ifEmpty { "Theo dõi da" },
        plan = "Chờ bác sĩ thiết lập kế hoạch",
        procedure = "Tư vấn ban đầu",
        total = 1,
        completed = 0,
        doctor = "BS. Tâm",
        lastVisit = null,
        next = "2026-09-21",
        time = "10:30",
        status = "Đặt hẹn",
        alerts = listOf("Cần khai thác tiền sử"),
        consent = false,
        photoConsent = false,
        aftercare = "Chưa có hướng dẫn được duyệt.",
        meds = emptyList(),
        notes = "",
        events = emptyList(),
        messages = emptyList(),
        sessions = emptyList(),
        invoices = emptyList(),
    )
    state.copy(
        selected = id,
        patients = state.patients + patient,
    ).log("Tạo hồ sơ mới", id) to patient
}

fun ClinicStore.resolveFollowUp(
    id: String,
    reply: String? = null,
    staff: StaffContext = StaffContext(),
): FollowUpResolution = transact { state ->
    staff.assertCan("clinical")
    val followUp = state.followups.find { it.id == id } ?: throw ClinicError("Không tìm thấy follow-up.")
    val patient = state.patient(followUp.patient)
    val message = reply?.trim()?.takeIf { it.isNotEmpty() } ?: if (followUp.priority == "urgent") {
        "Đội ngũ Pema đã tiếp nhận phản hồi. Bác sĩ sẽ liên hệ theo quy trình của phòng khám."
    } else {
        "Pema đã xem cập nhật của bạn và ghi nhận vào hành trình điều trị."
    }
    val nextFollowUps = state.followups.map { item ->
        if (item.id == id) item.copy(status = "resolved") else item
    }
    val title = if (reply.isNullOrBlank()) "Follow-up đã được xử lý" else "Bác sĩ đã xem và phản hồi"
    val action = if (reply.isNullOrBlank()) "Xử lý follow-up" else "Duyệt follow-up và gửi phản hồi"
    val detail = if (reply.isNullOrBlank()) {
        "Đã xem ${followUp.type.lowercase()} và gửi phản hồi tới người bệnh."
    } else {
        message
    }
    val withMessage = state.copy(followups = nextFollowUps).updatePatient(patient.id) {
        it.copy(messages = it.messages + PatientMessage("clinic", message, "20/09 · vừa xong"))
    }
    val nextState = withMessage
        .addEvent(patient.id, "followup", title, detail, by = staff.name)
        .log(action, patient.id)
    val resolved = nextState.followups.first { it.id == id }
    nextState to FollowUpResolution(resolved, nextState.patient(patient.id), message)
}
