package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class Patient360AdminCommandsTest {
    @Test
    fun clinicMessageAddsPatientMessageEventAndAudit() {
        val store = ClinicStore()
        val before = store.patient("P001").messages.size

        val message = store.sendPatientMessage("P001", "  Theo dõi da theo hướng dẫn.  ", StaffContext(role = "doctor", name = "BS. Tâm"))

        val patient = store.patient("P001")
        assertEquals("Theo dõi da theo hướng dẫn.", message.text)
        assertEquals(before + 1, patient.messages.size)
        assertEquals(message, patient.messages.last())
        assertEquals("Đã gửi tin nhắn", patient.events.first().title)
        assertEquals("Gửi tin nhắn người bệnh", store.state.value.audit.first().action)
    }

    @Test
    fun clinicMessageRequiresClinicalRoleAndContent() {
        val store = ClinicStore()

        assertFailsWith<ClinicError> {
            store.sendPatientMessage("P001", "Xin chào", StaffContext(role = "care", name = "Thu"))
        }
        assertFailsWith<ClinicError> {
            store.sendPatientMessage("P001", "   ", StaffContext(role = "doctor", name = "BS. Tâm"))
        }
    }

    @Test
    fun patientFactsSplitAlertsAndSaveConsent() {
        val store = ClinicStore()

        store.savePatientFacts("P001", "Da nhạy cảm\n \nDị ứng retinoid", photoConsent = false)

        val patient = store.patient("P001")
        assertEquals(listOf("Da nhạy cảm", "Dị ứng retinoid"), patient.alerts)
        assertEquals(false, patient.photoConsent)
        assertEquals("Cập nhật cảnh báo/đồng ý ảnh", store.state.value.audit.first().action)
    }

    @Test
    fun homeCareInstructionsSaveApprovedTextAndEvent() {
        val store = ClinicStore()

        store.saveHomeCareInstructions("P001", "Làm sạch dịu nhẹ\nChống nắng SPF 50+", StaffContext(role = "owner", name = "BS. Tâm"))

        val patient = store.patient("P001")
        assertEquals("Làm sạch dịu nhẹ\nChống nắng SPF 50+", patient.aftercare)
        assertEquals("Đã gửi hướng dẫn chăm sóc", patient.events.first().title)
        assertTrue(store.state.value.audit.first().action.contains("Gửi hướng dẫn"))
    }
}
