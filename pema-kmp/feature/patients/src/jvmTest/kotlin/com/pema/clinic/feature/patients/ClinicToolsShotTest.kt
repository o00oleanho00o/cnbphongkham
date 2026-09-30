package com.pema.clinic.feature.patients

import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.shared.clinic.ClinicSeed
import com.pema.clinic.shared.clinic.patient
import kotlin.test.Test

class ClinicToolsShotTest {
    @Test
    fun i5NewPatient() {
        shotVsCanvas("I5") {
            DetailScaffold(title = Routes.appBarTitleOf(Routes.NewPatient), onBack = {}) {
                NewPatientScreen(
                    state = NewPatientUiState(),
                    onChange = {},
                    onCreate = {},
                )
            }
        }
    }

    @Test
    fun i7PhotoStudio() {
        val clinic = ClinicSeed.initial()
        shotVsCanvas("I7") {
            DetailScaffold(title = Routes.appBarTitleOf(Routes.PhotoStudio), onBack = {}) {
                PhotoStudioScreen(
                    state = photoStudioState(clinic.patient("P001")),
                    onViewChange = {},
                    onToggleCompare = {},
                    onAddPhoto = {},
                )
            }
        }
    }

    @Test
    fun i12AskQuery() {
        val clinic = ClinicSeed.initial()
        shotVsCanvas("I12") {
            DetailScaffold(title = Routes.appBarTitleOf(Routes.AskQuery), onBack = {}) {
                AskQueryScreen(
                    state = askQueryState(clinic),
                    onQueryChange = {},
                    onPreset = {},
                    onOpenPatient = {},
                )
            }
        }
    }
}
