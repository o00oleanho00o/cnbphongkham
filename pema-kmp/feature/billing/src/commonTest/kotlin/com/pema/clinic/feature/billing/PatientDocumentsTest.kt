package com.pema.clinic.feature.billing

import com.pema.clinic.shared.clinic.ClinicSeed
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PatientDocumentsTest {
    @Test
    fun buildsInvoicesAftercareAndApprovedPrescriptionsForPatient() {
        val ui = buildPatientDocumentsState(ClinicSeed.initial(), "P001")

        assertEquals("Tài liệu & hóa đơn", ui.title)
        assertEquals(
            listOf(
                "Buổi chăm sóc / điều trị|HD-0001 · 6/9/2026 · Đã thanh toán\n1.200.000 ₫",
                "Tái khám & đánh giá|HD-DEMO-001 · 20/9/2026 · Đã thu một phần · còn 150.000 ₫",
            ),
            ui.invoices.map { "${it.title}|${it.sub}" },
        )
        assertEquals("Hướng dẫn chăm sóc sau buổi", ui.aftercare.single().title)
        assertEquals("Đã duyệt · 6/9/2026", ui.aftercare.single().sub)
        assertEquals("DT-P001 · BS. Tâm", ui.prescriptions.single().title)
        assertTrue(ui.prescriptions.single().sub.contains("Cicaderm Cream 40ml"))
    }

    @Test
    fun hidesDraftPrescriptionsFromPatientDocuments() {
        val ui = buildPatientDocumentsState(ClinicSeed.initial(), "P002")

        assertTrue(ui.prescriptions.isEmpty())
    }
}
