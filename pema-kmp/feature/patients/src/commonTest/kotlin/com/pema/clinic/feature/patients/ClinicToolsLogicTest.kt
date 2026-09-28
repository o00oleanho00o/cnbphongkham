package com.pema.clinic.feature.patients

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.patient
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ClinicToolsLogicTest {
    @Test
    fun newPatientFormRequiresNameOnlyLikeWeb() {
        assertFalse(NewPatientUiState(name = "   ", age = "", concern = "").canCreate)
        assertTrue(NewPatientUiState(name = "Nguyễn Demo", age = "", concern = "").canCreate)
    }

    @Test
    fun photoStudioMetadataUsesSelectedViewAndConsent() {
        val patient = ClinicSeed.initial().patient("P001")
        val state = photoStudioState(patient, view = "Má trái", sliderMode = true)

        assertEquals("Má trái", state.view)
        assertTrue(state.sliderMode)
        assertEquals("Metadata: vùng Mặt · góc Má trái · đồng ý chăm sóc: có ghi nhận", state.metadata)
    }

    @Test
    fun askPemaMatchesWebPresetAndFreeTextSemantics() {
        val clinic = ClinicSeed.initial()

        val images = askPema("Ai có ảnh gửi sau laser đang chờ xem?", clinic)
        assertEquals("2 ảnh chờ bác sĩ xem", images.answer)
        assertEquals("Cách tính: mục Theo dõi loại Ảnh, trạng thái đang mở.", images.method)
        assertEquals(listOf("P001", "P007"), images.rows.map { it.patientId })
        assertEquals(Routes.FollowUpInbox, images.route)

        val plans = askPema("Có bao nhiêu kế hoạch đang chạy?", clinic)
        assertTrue(plans.answer.startsWith("Có "))
        assertTrue(plans.answer.contains("kế hoạch chưa hoàn tất"))
        assertEquals(Routes.Patient360, plans.route)

        val overdue = askPema("Ai quá hạn tái khám hơn 30 ngày?", clinic)
        assertTrue(overdue.answer.contains("hồ sơ có lần điều trị gần nhất hơn 30 ngày"))
        assertTrue(overdue.rows.isNotEmpty())
    }
}
