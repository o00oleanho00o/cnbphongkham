package com.pema.clinic

import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import kotlin.test.Test

class ShellShotTest {
    @Test
    fun f17DeniedCashierForDoctor() {
        shotVsCanvas("F17") {
            CompositionLocalProvider(LocalOnBack provides {}) {
                DeniedScreen("Thu ngân")
            }
        }
    }
}
