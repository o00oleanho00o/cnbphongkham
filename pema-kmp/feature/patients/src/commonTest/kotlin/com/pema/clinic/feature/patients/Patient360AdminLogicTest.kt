package com.pema.clinic.feature.patients

import com.pema.clinic.shared.clinic.ClinicStore
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class Patient360AdminLogicTest {
    @Test
    fun financeStateUsesCareFinanceSummaryAndBillingGate() {
        val state = ClinicStore().state.value
        val finance = buildPatientFinanceState(state, "P001", canBilling = true)

        assertEquals("Nguyễn Minh Linh", finance.patientName)
        assertEquals("LP-P001 · Laser theo chỉ định", finance.plans.first().title)
        assertEquals("5.350.000 ₫", finance.plans.first().received)
        assertTrue(finance.invoices.any { it.canOpenCashier })
        assertFalse(buildPatientFinanceState(state, "P001", canBilling = false).invoices.any { it.canOpenCashier })
    }

    @Test
    fun crmStateShowsPatientContextAndOpenTasks() {
        val crm = buildPatientCrmState(ClinicStore().state.value, "P001")

        assertTrue(crm.notice.contains("BƯỚC TIẾP THEO"))
        assertEquals("Giới thiệu", crm.source)
        assertEquals("26/6/2026", crm.firstContact)
        assertTrue(crm.tasks.isNotEmpty())
    }

    @Test
    fun historyStateMergesAppointmentsEventsAndSortsNewestFirst() {
        val history = buildPatientHistoryState(ClinicStore().state.value, "P001")

        assertTrue(history.events.any { it.title.contains("Lịch hẹn") && it.icon == "event" })
        assertTrue(history.events.any { it.title.contains("Hoàn tất buổi") && it.icon == "medical_services" })
        assertTrue(history.events.size > ClinicStore().patient("P001").events.size)
    }

    @Test
    fun formsPrefillAlertsConsentAndHomeCareMedicationLines() {
        val form = buildPatientFormState(ClinicStore().state.value, "P001")

        assertTrue(form.alertsText.contains("Da nhạy cảm"))
        assertTrue(form.photoConsent)
        assertEquals(
            "Sữa rửa mặt dịu nhẹ\nDưỡng ẩm phục hồi\nChống nắng SPF 50+",
            form.homeCareText,
        )
    }
}
