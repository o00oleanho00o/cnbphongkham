package com.pema.clinic.feature.aftercare

import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.FeatureDeps

fun NavGraphBuilder.aftercareGraph(deps: FeatureDeps) {
    composable(Routes.HomeCare) { HomeCareRoute(deps) }
    composable(Routes.SendUpdate) { SendUpdateRoute(deps) }
    composable(Routes.FollowUpReply) { FollowUpReplyRoute(deps) }
    composable(Routes.Privacy) { PrivacyRoute() }
}
