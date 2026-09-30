package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ClinicToolsCommandsTest {
    @Test
    fun createPatientUsesWebValidationIdAndDefaults() {
        val store = ClinicStore()

        assertEquals(
            "Nhập tên người bệnh",
            assertFailsWith<ClinicError> { store.createPatient(NewClinicPatientInput("   ")) }.message,
        )

        val patient = store.createPatient(NewClinicPatientInput("  Nguyễn Demo  ", age = "0", concern = ""))
        assertEquals("P047", patient.id)
        assertEquals("Nguyễn Demo", patient.name)
        assertEquals(28, patient.age)
        assertEquals("Theo dõi da", patient.concern)
        assertEquals("Chờ bác sĩ thiết lập kế hoạch", patient.plan)
        assertEquals("Tư vấn ban đầu", patient.procedure)
        assertEquals("Đặt hẹn", patient.status)
        assertEquals("2026-09-21", patient.next)
        assertEquals("10:30", patient.time)
        assertEquals(listOf("Cần khai thác tiền sử"), patient.alerts)
        assertEquals("P047", store.state.value.selected)
        assertEquals("Tạo hồ sơ mới", store.state.value.audit.first().action)
    }

    @Test
    fun resolveFollowUpRequiresClinicalRoleAndAddsReplyEventAudit() {
        val store = ClinicStore()

        assertEquals(
            "Tài khoản Mai Anh không có tác vụ này. Chuyển đúng không gian làm việc.",
            assertFailsWith<ClinicError> {
                store.resolveFollowUp("F001", staff = StaffContext(role = "care", name = "Mai Anh"))
            }.message,
        )
        assertEquals("open", store.state.value.followups.first { it.id == "F001" }.status)

        val result = store.resolveFollowUp(
            "F001",
            reply = "Pema đã xem cập nhật và ghi nhận vào hành trình.",
            staff = StaffContext(role = "doctor", name = "BS. Tâm", doctorId = "D0"),
        )

        assertEquals("resolved", result.followUp.status)
        assertEquals("Pema đã xem cập nhật và ghi nhận vào hành trình.", result.reply)
        assertEquals("clinic", result.patient.messages.last().from)
        assertEquals("Bác sĩ đã xem và phản hồi", result.patient.events.first().title)
        assertEquals("Duyệt follow-up và gửi phản hồi", store.state.value.audit.first().action)
    }

    @Test
    fun resolveFollowUpUsesWebDefaultUrgentReply() {
        val store = ClinicStore()
        val result = store.resolveFollowUp("F002")

        assertTrue(result.reply.contains("Bác sĩ sẽ liên hệ"))
        assertEquals("resolved", store.state.value.followups.first { it.id == "F002" }.status)
        assertEquals("Follow-up đã được xử lý", result.patient.events.first().title)
    }
}
