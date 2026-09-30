package com.pema.clinic.feature.billing

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.Invoice
import com.pema.clinic.shared.clinic.careFinanceSummary
import com.pema.clinic.shared.clinic.money
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.viDate

fun NavGraphBuilder.patientDocumentsGraph(deps: FeatureDeps) {
    composable(Routes.PatientDocuments) {
        PatientDocumentsRoute(deps)
    }
}

@Immutable
internal data class PatientDocumentTileUiState(
    val id: String,
    val title: String,
    val sub: String,
    val icon: String,
)

@Immutable
internal data class PatientDocumentsUiState(
    val title: String = Routes.appBarTitleOf(Routes.PatientDocuments),
    val invoices: List<PatientDocumentTileUiState>,
    val aftercare: List<PatientDocumentTileUiState>,
    val prescriptions: List<PatientDocumentTileUiState>,
)

@Composable
private fun PatientDocumentsRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinicState by deps.clinicStore.state.collectAsStateWithLifecycle()
    val patientId = remember(session) { deps.sessionStore.selectedPatientId() }
    val state = buildPatientDocumentsState(clinicState, patientId)
    PatientDocumentsScreen(
        state = state,
        onOpenAftercare = { deps.navigator.go(Routes.HomeCare) },
        onOpenPrescription = { deps.navigator.go(Routes.Prescriptions) },
    )
}

internal fun buildPatientDocumentsState(
    state: ClinicState,
    patientId: String,
): PatientDocumentsUiState {
    val patient = state.patient(patientId)
    val finance = state.careFinanceSummary(patientId)
    val aftercare = if (patient.aftercare.isBlank()) {
        emptyList()
    } else {
        listOf(
            PatientDocumentTileUiState(
                id = "aftercare-${patient.id}",
                title = "Hướng dẫn chăm sóc sau buổi",
                sub = "Đã duyệt · ${viDate(patient.lastVisit)}",
                icon = "description",
            ),
        )
    }
    return PatientDocumentsUiState(
        invoices = patient.invoices.map { invoice ->
            PatientDocumentTileUiState(
                id = invoice.id,
                title = invoice.label,
                sub = invoice.patientStatusLine(),
                icon = "receipt_long",
            )
        },
        aftercare = aftercare,
        prescriptions = finance.prescriptions
            .filter { it.status == "approved" }
            .map { prescription ->
                PatientDocumentTileUiState(
                    id = prescription.id,
                    title = "${prescription.id} · ${prescription.doctor}",
                    sub = prescription.items.joinToString(" · ") { it.name },
                    icon = "medication",
                )
            },
    )
}

@Composable
internal fun PatientDocumentsScreen(
    state: PatientDocumentsUiState,
    onOpenAftercare: (() -> Unit)?,
    onOpenPrescription: (() -> Unit)?,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaSection("Hóa đơn của bạn")
        if (state.invoices.isEmpty()) {
            PemaEmpty("Chưa có hóa đơn trong demo.", icon = "receipt_long")
        } else {
            state.invoices.forEach { item ->
                PemaTile(item.title, item.sub, item.icon, onClick = null)
            }
        }

        PemaSection("Hướng dẫn đã gửi")
        if (state.aftercare.isEmpty()) {
            PemaEmpty("Chưa có hướng dẫn đã duyệt.", icon = "description")
        } else {
            state.aftercare.forEach { item ->
                PemaTile(item.title, item.sub, item.icon, onClick = onOpenAftercare)
            }
        }

        PemaSection("Đơn & phiếu đã duyệt")
        if (state.prescriptions.isEmpty()) {
            PemaEmpty("Chưa có đơn hoặc phiếu đã duyệt.", icon = "medication")
        } else {
            state.prescriptions.forEach { item ->
                PemaTile(item.title, item.sub, item.icon, onClick = onOpenPrescription)
            }
        }
    }
}

private fun Invoice.patientStatusLine(): String = when {
    paid -> "$id · ${viDate(date)} · Đã thanh toán\n${money(amount)}"
    received > 0 -> "$id · ${viDate(date)} · Đã thu một phần · còn ${money(due)}"
    else -> "$id · ${viDate(date)} · Chờ thanh toán\n${money(amount)}"
}
