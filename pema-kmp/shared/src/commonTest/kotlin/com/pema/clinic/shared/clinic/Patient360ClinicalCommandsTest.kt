package com.pema.clinic.shared.clinic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class Patient360ClinicalCommandsTest {
    private val doctor = StaffContext(role = "owner", name = "BS. Tâm", doctorId = "D0", doctorName = "BS. Tâm")

    @Test
    fun consultDraftRequiresInputThenApprovesEditedEvent() {
        val store = ClinicStore()
        val before = store.state.value
        assertEquals(
            "Hãy nhập vài ý chính trước",
            assertFailsWith<ClinicError> { store.generateConsultDraft("P001", " ", doctor) }.message,
        )
        assertEquals(before, store.state.value)

        val draft = store.generateConsultDraft("P001", "Da ổn hơn", doctor).draft
        assertTrue(draft.startsWith("Bản nháp ghi chú · 20/9/2026: Da ổn hơn"))
        assertEquals(draft, store.patient("P001").notes)

        store.approveConsultDraft("P001", "$draft Đã chỉnh.", doctor)
        val patient = store.patient("P001")
        assertEquals("", patient.notes)
        assertEquals("Ghi chú tư vấn đã được duyệt", patient.events.first().title)
        assertEquals("Duyệt ghi chú tư vấn", store.state.value.audit.first().action)
    }

    @Test
    fun aiBriefApprovalIsClinicalOnlyAndAudited() {
        val store = ClinicStore()
        assertEquals(
            "Brief không được để trống",
            assertFailsWith<ClinicError> { store.approveAiBrief("P001", "", doctor) }.message,
        )
        store.approveAiBrief("P001", "Brief đã được bác sĩ chỉnh.", doctor)
        assertEquals("Brief AI đã được duyệt", store.patient("P001").events.first().title)
        assertEquals("Duyệt brief AI mô phỏng", store.state.value.audit.first().action)
    }

    @Test
    fun planEditRejectsTotalBelowCompletedAndKeepsStateAtomic() {
        val store = ClinicStore()
        val before = store.state.value
        assertEquals(
            "Tên và số buổi chưa hợp lệ",
            assertFailsWith<ClinicError> { store.updateTreatmentPlan("P001", PlanEditInput("Kế hoạch mới", 1), doctor) }.message,
        )
        assertEquals(before, store.state.value)

        store.updateTreatmentPlan("P001", PlanEditInput("Phục hồi & chăm sóc da", 6), doctor)
        val patient = store.patient("P001")
        assertEquals("Phục hồi & chăm sóc da", patient.plan)
        assertEquals(6, patient.total)
        assertEquals("Điều chỉnh kế hoạch", patient.events.first().title)
    }

    @Test
    fun sessionRecordUsesExactWebValidationMessagesAndUpdatesCrm() {
        val store = ClinicStore()
        assertEquals(
            "Hãy ghi đánh giá trước buổi",
            assertFailsWith<ClinicError> { store.recordTreatmentSession("P001", validSession(note = ""), doctor) }.message,
        )
        assertEquals(
            "Hãy nhập hướng dẫn chăm sóc sau buổi",
            assertFailsWith<ClinicError> { store.recordTreatmentSession("P001", validSession(aftercare = ""), doctor) }.message,
        )
        assertEquals(
            "Ngày buổi phải hợp lệ, từ buổi trước đến ngày demo 20/09/2026.",
            assertFailsWith<ClinicError> { store.recordTreatmentSession("P001", validSession(date = "2026-09-21"), doctor) }.message,
        )
        assertEquals(
            "Cần xác nhận đồng ý ảnh khi lưu ảnh mốc",
            assertFailsWith<ClinicError> { store.recordTreatmentSession("P001", validSession(hasPhoto = true, photoConsent = false), doctor) }.message,
        )

        val beforeFollowups = store.state.value.followups.size
        val session = store.recordTreatmentSession("P001", validSession(protocolId = "laser-co2", hasPhoto = false), doctor)
        val patient = store.patient("P001")
        assertEquals(3, patient.completed)
        assertEquals(DAY, patient.lastVisit)
        assertEquals(session.id, patient.sessions.last().id)
        assertEquals("service_protocol", patient.crm.expectedVisitSource)
        assertEquals("Đánh giá D+30 sau Laser CO2", patient.crm.expectedVisitReason)
        assertTrue(store.state.value.followups.size > beforeFollowups)
        assertNotEquals(emptyList(), store.state.value.crmQueue(patient = "P001", allDates = true).filter { it.type in setOf("d1", "d3", "d7") })
    }

    private fun validSession(
        date: String = DAY,
        note: String = "Da ổn",
        aftercare: String = "Dưỡng ẩm và chống nắng.",
        protocolId: String? = null,
        hasPhoto: Boolean = false,
        photoConsent: Boolean = true,
    ): TreatmentSessionInput = TreatmentSessionInput(
        date = date,
        type = "Laser CO2 theo chỉ định",
        note = note,
        aftercare = aftercare,
        region = "Mặt",
        view = "Chính diện",
        protocolId = protocolId,
        nextVisit = addDays(date, 30),
        hasPhoto = hasPhoto,
        photoConsent = photoConsent,
    )
}
