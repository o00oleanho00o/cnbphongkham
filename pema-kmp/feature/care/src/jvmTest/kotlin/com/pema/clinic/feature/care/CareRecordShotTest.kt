package com.pema.clinic.feature.care

import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.crmQueue
import kotlin.test.Test

class CareRecordShotTest {
    @Test
    fun i13CareRecord() {
        val clinic = ClinicStore().state.value
        val task = clinic.crmQueue(allDates = true, rule = "d1").firstOrNull() ?: clinic.crmQueue(allDates = true).first()
        val state = buildCareRecordState(clinic, task.patientId).copy(
            defaultOutcome = "booked",
            taskOwner = "CSKH Mai Anh",
        )
        shotVsCanvas("I13") {
            CompositionLocalProvider(LocalOnBack provides {}) {
                CareRecordScreen(state = state, onSave = {})
            }
        }
    }
}
