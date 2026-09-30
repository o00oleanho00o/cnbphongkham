package com.pema.clinic.shared.clinic

/** Sends a clinic-authored message that appears in the patient-facing Pema Care thread. */
fun ClinicStore.sendPatientMessage(
    patientId: String,
    text: String,
    staff: StaffContext = StaffContext(),
): PatientMessage {
    staff.assertCan("clinical")
    val body = text.trim()
    if (body.isEmpty()) throw ClinicError("Hãy nhập nội dung tin nhắn.")
    return transact { state ->
        state.patient(patientId)
        val message = PatientMessage("clinic", body, "20/09 · 10:20")
        val next = state.updatePatient(patientId) { patient ->
            patient.copy(messages = patient.messages + message)
        }
            .addEvent(patientId, "message", "Đã gửi tin nhắn", "Đội ngũ Pema đã phản hồi qua patient app.", staff.name, DAY)
            .log("Gửi tin nhắn người bệnh", patientId)
        next to message
    }
}

/** Saves the remembered alerts and care-photo consent from the Patient 360 edit modal. */
fun ClinicStore.savePatientFacts(
    patientId: String,
    alertsText: String,
    photoConsent: Boolean,
    staff: StaffContext = StaffContext(),
) {
    staff.assertCan("clinical")
    transact { state ->
        state.patient(patientId)
        val alerts = alertsText
            .lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .toList()
        val next = state.updatePatient(patientId) { patient ->
            patient.copy(alerts = alerts, photoConsent = photoConsent)
        }.log("Cập nhật cảnh báo/đồng ý ảnh", patientId)
        next to Unit
    }
}

/** Saves doctor-approved home-care instructions for the patient app. */
fun ClinicStore.saveHomeCareInstructions(
    patientId: String,
    instructions: String,
    staff: StaffContext = StaffContext(),
) {
    staff.assertCan("clinical")
    val body = instructions.trim()
    if (body.isEmpty()) throw ClinicError("Hãy nhập hướng dẫn")
    transact { state ->
        state.patient(patientId)
        val next = state.updatePatient(patientId) { patient ->
            patient.copy(aftercare = body)
        }
            .addEvent(patientId, "care", "Đã gửi hướng dẫn chăm sóc", body, staff.name, DAY)
            .log("Gửi hướng dẫn chăm sóc", patientId)
        next to Unit
    }
}
