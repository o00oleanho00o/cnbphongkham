package com.pema.clinic.feature.aftercare

import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.shared.clinic.ClinicSeed
import kotlin.test.Test

class FollowUpInboxShotTest {
    @Test
    fun i6FollowUpInbox() {
        val clinic = ClinicSeed.initial()
        shotVsCanvas("I6") {
            DetailScaffold(title = Routes.appBarTitleOf(Routes.FollowUpInbox), onBack = {}) {
                FollowUpInboxScreen(
                    state = followUpInboxState(clinic),
                    onFilter = {},
                    onOpen = {},
                )
            }
        }
    }
}
