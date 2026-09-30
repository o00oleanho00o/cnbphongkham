package com.pema.clinic.feature.patients

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.shared.clinic.ClinicStore
import kotlin.test.Test

class Patient360AdminShotTest {
    private val clinic = ClinicStore().state.value

    @Test fun j6PatientFinance() { shotVsCanvas("J6") { WithBack { PatientFinanceScreen(buildPatientFinanceState(clinic, "P001", true), onOpenCashier = {}) } } }

    @Test fun j7PatientCrm() { shotVsCanvas("J7") { WithBack { PatientCrmScreen(buildPatientCrmState(clinic, "P001"), canEditExpected = true, onSetExpectedVisit = { _, _, _ -> }) } } }

    @Test fun j8PatientHistory() { shotVsCanvas("J8") { WithBack { PatientHistoryScreen(buildPatientHistoryState(clinic, "P001")) } } }

    @Test fun j9PatientMessage() { shotVsCanvas("J9") { WithBack { PatientMessageScreen(buildPatientFormState(clinic, "P001"), onSend = {}) } } }

    @Test fun j10PatientNotes() { shotVsCanvas("J10") { WithBack { PatientNotesScreen(buildPatientFormState(clinic, "P001"), onSave = { _, _ -> }) } } }

    @Test fun j11HomeCareSend() { shotVsCanvas("J11") { WithBack { HomeCareSendScreen(buildPatientFormState(clinic, "P001"), onSend = {}) } } }

    @Composable
    private fun WithBack(content: @Composable () -> Unit) {
        CompositionLocalProvider(LocalOnBack provides {}, content = content)
    }
}
