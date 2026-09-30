package com.pema.clinic.feature.patients

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.brief
import com.pema.clinic.shared.clinic.patient
import kotlin.test.Test

class Patient360ClinicalShotTest {
    private val state = ClinicSeed.initial()
    private val patient = state.patient("P001")

    @Test
    fun j1ClinicalHistory() {
        shotVsCanvas("J1") {
            WithBack {
                ClinicalHistoryScreen(
                    state = ClinicalHistoryUiState(
                        patientName = patient.name,
                        history = patient.clinical?.history ?: "Da nhạy cảm, từng đỏ da sau laser.",
                        diagnosis = patient.clinical?.diagnosis.orEmpty(),
                        transcript = "",
                        draft = "",
                    ),
                    onHistoryChange = {},
                    onDiagnosisChange = {},
                    onTranscriptChange = {},
                    onDraftChange = {},
                    onSaveClinical = {},
                    onGenerateDraft = {},
                    onApproveDraft = {},
                )
            }
        }
    }

    @Test
    fun j2AiBrief() {
        shotVsCanvas("J2") {
            WithBack {
                AiBriefScreen(
                    state = AiBriefUiState(patient.name, patient.plan, brief(state, patient)),
                    onTextChange = {},
                    onCopy = {},
                    onApprove = {},
                )
            }
        }
    }

    @Test
    fun j3PlanOverview() {
        shotVsCanvas("J3") {
            WithBack { PlanOverviewScreen(planOverviewState(patient, StaffContext()), onEdit = {}) }
        }
    }

    @Test
    fun j4PlanEdit() {
        shotVsCanvas("J4") {
            WithBack {
                PlanEditScreen(
                    state = PlanEditUiState(patient.plan, patient.total.toString(), patient.completed),
                    onNameChange = {},
                    onTotalChange = {},
                    onSave = {},
                )
            }
        }
    }

    @Test
    fun j5SessionRecord() {
        shotVsCanvas("J5") {
            WithBack {
                SessionRecordScreen(
                    state = SessionRecordUiState(
                        notice = sessionNotice(patient),
                        sessionType = "Chăm sóc & laser theo chỉ định",
                        protocol = "Laser CO2 · D+1 / D+3 / D+7 / D+30",
                        nextVisit = "2026-10-06",
                        region = "Mặt",
                        view = "Chính diện",
                        consent = true,
                    ),
                    onTypeChange = {},
                    onProtocolChange = {},
                    onRegionChange = {},
                    onViewChange = {},
                    onConsentChange = {},
                    onNextVisitClick = {},
                    onAddPhoto = {},
                    onSave = {},
                )
            }
        }
    }

    @Composable
    private fun WithBack(content: @Composable () -> Unit) {
        CompositionLocalProvider(LocalOnBack provides {}, content = content)
    }
}
