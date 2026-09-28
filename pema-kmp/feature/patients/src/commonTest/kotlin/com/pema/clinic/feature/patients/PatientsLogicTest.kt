package com.pema.clinic.feature.patients

import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.FinanceSummary
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PatientsLogicTest {
    @Test
    fun patientSearchUsesFlutterOwnsNameAndSyntheticIdFiltering() {
        val catalog = sampleCatalog()
        val ownerRows = patientSearchRows(catalog, Session(), "")
        assertEquals(catalog.profiles.size, ownerRows.size)
        assertEquals("P001", ownerRows.first().code)

        val doctorRows = patientSearchRows(catalog, Session(staffRole = "doctor", staffDoctor = "BS. Tâm"), "")
        assertTrue(doctorRows.isNotEmpty())
        assertTrue(doctorRows.all { it.profile.doctor == "BS. Tâm" })

        assertTrue(patientSearchRows(catalog, Session(staffRole = "doctor", staffDoctor = "BS. Tâm"), "p002").isEmpty())
        val maiRows = patientSearchRows(catalog, Session(staffRole = "doctor", staffDoctor = "BS. Mai"), "p002")
        assertEquals(listOf("P002"), maiRows.map { it.code })

        val firstNameToken = catalog.profiles.first().name.lowercase().takeLast(4)
        assertEquals(catalog.profiles.first().id, patientSearchRows(catalog, Session(), firstNameToken).first().profile.id)
    }

    @Test
    fun treatmentCompletionRequiresRecordHandoverAndRemainingSessions() {
        val patient = PatientState(sessions = 2, appointment = "10:30", day = "2026-09-22")
        assertFalse(canCompleteTreatmentSession(patient, totalSessions = 5, record = "", handoverChecked = true))
        assertFalse(canCompleteTreatmentSession(patient, totalSessions = 5, record = "Hoàn tất", handoverChecked = false))
        assertTrue(canCompleteTreatmentSession(patient, totalSessions = 5, record = "Hoàn tất", handoverChecked = true))
        assertFalse(canCompleteTreatmentSession(patient.copy(sessions = 5), totalSessions = 5, record = "Hoàn tất", handoverChecked = true))
    }

    @Test
    fun progressPhotosUseFlutterBeforeAndLatestSlotRules() {
        assertEquals(ProgressPhotoSlots(before = null, latest = null), progressPhotoSlots(emptyList()))
        assertEquals(ProgressPhotoSlots(before = null, latest = "one.jpg"), progressPhotoSlots(listOf("one.jpg")))
        assertEquals(
            ProgressPhotoSlots(before = "old.jpg", latest = "new.jpg"),
            progressPhotoSlots(listOf("old.jpg", "new.jpg")),
        )
    }

    @Test
    fun procedureRecordCardIsFinanceOwnerOrAccountantOnly() {
        val loaded = FinanceState(role = "owner", data = financeSnapshot())
        assertTrue(shouldShowProcedureRecordCard(Session(), loaded))
        assertTrue(shouldShowProcedureRecordCard(Session(staffRole = "accountant"), loaded.copy(role = "accountant")))
        assertFalse(shouldShowProcedureRecordCard(Session(staffRole = "doctor"), loaded.copy(role = "doctor")))
        assertFalse(shouldShowProcedureRecordCard(Session(careMode = true), loaded))
        assertFalse(shouldShowProcedureRecordCard(Session(), FinanceState()))
        assertNull(FinanceState().data)
    }

    private fun financeSnapshot(): FinanceSnapshot = FinanceSnapshot(
        month = "2026-09",
        today = "2026-09-22",
        periodStatus = "open",
        summary = FinanceSummary(revenue = 1_000_000, fee = 100_000, pending = 0, collected = 500_000, debt = 500_000),
    )
}
